"""
Utilities for Amazon Connect Lambda functions:

  - SSM Parameter Store helper with warm-start caching
  - Amazon Connect API helpers (agent info with caching)
  - Response builder (Connect expects a flat dict of string values)
  - ``connect_handler`` decorator that wraps the event in a ConnectEvent and
    handles unhandled exceptions gracefully
"""

import functools
import logging

from .event import ConnectEvent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SSM Parameter Store
# ---------------------------------------------------------------------------

_ssm_client = None          # lazy-initialised on first use
_SSM_CACHE: dict = {}       # module-level cache survives Lambda warm invocations


def _get_ssm_client(region=None):
    """Return a (possibly cached) SSM boto3 client."""
    global _ssm_client
    if _ssm_client is None:
        import boto3
        _ssm_client = boto3.client("ssm", region_name=region)
        logger.debug("SSM client created. region=%s", region)
    return _ssm_client


def get_ssm_parameter(name: str, decrypt: bool = True, region: str = None) -> str:
    """
    Fetch a parameter from AWS SSM Parameter Store.

    The result is cached in memory for the lifetime of the Lambda execution
    environment (i.e. across warm invocations).  The cache is not TTL-based;
    redeploy the Lambda or call :func:`bust_ssm_cache` to force a refresh.

    Parameters
    ----------
    name:
        The full SSM parameter path, e.g. ``'/myapp/db/password'``.
    decrypt:
        Whether to decrypt SecureString parameters.  Defaults to ``True``.
    region:
        AWS region override.  Defaults to the Lambda execution environment's
        region (``AWS_DEFAULT_REGION``).

    Returns
    -------
    str
        The parameter value as a string.

    Raises
    ------
    boto3 / botocore exceptions (e.g. ``ParameterNotFound``) are not caught
    here — let them propagate so the ``connect_handler`` decorator can record
    them and return a structured error response to the contact flow.
    """
    if name in _SSM_CACHE:
        logger.debug("SSM cache hit. name=%s", name)
        return _SSM_CACHE[name]

    client = _get_ssm_client(region=region)
    response = client.get_parameter(Name=name, WithDecryption=decrypt)
    value = response["Parameter"]["Value"]
    _SSM_CACHE[name] = value
    logger.debug("SSM parameter fetched and cached. name=%s", name)
    return value


def bust_ssm_cache(name: str = None):
    """
    Invalidate the SSM parameter cache.

    Parameters
    ----------
    name:
        If supplied, only that parameter is evicted.  If omitted, the entire
        cache is cleared.
    """
    global _SSM_CACHE
    if name is None:
        _SSM_CACHE.clear()
        logger.debug("SSM cache cleared entirely.")
    else:
        _SSM_CACHE.pop(name, None)
        logger.debug("SSM cache entry removed. name=%s", name)


# ---------------------------------------------------------------------------
# Amazon Connect API — agent info
# ---------------------------------------------------------------------------

_connect_client = None          # lazy-initialised on first use
_AGENT_CACHE: dict = {}         # keyed by contact_id; survives warm invocations


def _get_connect_client(region=None):
    """Return a (possibly cached) Amazon Connect boto3 client."""
    global _connect_client
    if _connect_client is None:
        import boto3
        _connect_client = boto3.client("connect", region_name=region)
        logger.debug("Connect client created. region=%s", region)
    return _connect_client


def get_connect_agent(instance_arn: str, contact_id: str, region: str = None) -> dict:
    """
    Return agent information for a connected contact via the Connect API.

    This makes two API calls — ``describe_contact`` to retrieve the agent ARN,
    then ``describe_user`` to retrieve the full agent profile — and caches the
    combined result by ``contact_id`` for the lifetime of the Lambda execution
    environment.

    .. note::
        Agent data is **only available after the contact has been connected to
        an agent**.  Calling this from a flow block that runs before routing
        (e.g. the initial inbound flow) will return ``None``.

        If you need agent attributes *inside* a whisper or hold flow without
        an API call, use :meth:`ConnectEvent.get_parameter` to read values that
        the flow has passed explicitly to the Lambda block (e.g. ``$.Agent.ARN``
        mapped to a parameter named ``agentArn``).

    Parameters
    ----------
    instance_arn:
        The Connect instance ARN, typically from
        :meth:`ConnectEvent.get_instance_arn`.
    contact_id:
        The contact to look up, typically from
        :meth:`ConnectEvent.get_contact_id`.
    region:
        AWS region override.  Defaults to the Lambda execution environment's
        region (``AWS_DEFAULT_REGION``).

    Returns
    -------
    dict or None
        A dict with the following keys (all strings), or ``None`` when no
        agent is assigned to the contact yet::

            {
                "arn":              "arn:aws:connect:...",
                "id":               "user-id-guid",
                "username":         "jsmith",
                "first_name":       "Jane",
                "last_name":        "Smith",
                "email":            "jsmith@example.com",   # may be empty
                "routing_profile_id": "routing-profile-guid",
                "routing_profile_arn": "arn:aws:connect:...",
                "hierarchy_group_id":  "group-guid",        # may be None
                "hierarchy_group_arn": "arn:aws:connect:...",  # may be None
            }

    Raises
    ------
    boto3 / botocore exceptions are not caught — let them propagate so the
    ``connect_handler`` decorator can convert them to a structured error
    response.
    """
    if contact_id in _AGENT_CACHE:
        logger.debug("Agent cache hit. contact_id=%s", contact_id)
        return _AGENT_CACHE[contact_id]

    # Extract the instance ID from the ARN
    # ARN format: arn:aws:connect:region:account:instance/<instance-id>
    instance_id = instance_arn.split("/")[-1]

    client = _get_connect_client(region=region)

    # Step 1: get the agent ARN from the contact record
    contact_response = client.describe_contact(
        InstanceId=instance_id,
        ContactId=contact_id,
    )
    agent_info = contact_response.get("Contact", {}).get("AgentInfo")
    if not agent_info:
        logger.debug("No agent assigned to contact yet. contact_id=%s", contact_id)
        _AGENT_CACHE[contact_id] = None
        return None

    agent_arn = agent_info.get("Id")   # Connect API returns the ARN in the "Id" field here
    if not agent_arn:
        _AGENT_CACHE[contact_id] = None
        return None

    # Step 2: describe the user to get the full profile
    # The agent ARN contains the user ID as the last path component
    user_id = agent_arn.split("/")[-1]
    user_response = client.describe_user(
        UserId=user_id,
        InstanceId=instance_id,
    )
    user = user_response.get("User", {})
    identity = user.get("IdentityInfo", {})
    routing = user.get("RoutingProfileId", "")

    # Resolve the routing profile ARN
    routing_profile_arn = ""
    routing_profile_id = routing.split("/")[-1] if routing else ""
    if routing_profile_id:
        try:
            rp_response = client.describe_routing_profile(
                InstanceId=instance_id,
                RoutingProfileId=routing_profile_id,
            )
            routing_profile_arn = (
                rp_response.get("RoutingProfile", {}).get("RoutingProfileArn", "")
            )
        except Exception:
            logger.debug("Could not resolve routing profile ARN. id=%s", routing_profile_id)

    hierarchy = user.get("HierarchyGroupId") or ""
    hierarchy_arn = ""
    hierarchy_id = hierarchy.split("/")[-1] if hierarchy else ""
    if hierarchy_id:
        try:
            hg_response = client.describe_user_hierarchy_group(
                HierarchyGroupId=hierarchy_id,
                InstanceId=instance_id,
            )
            hierarchy_arn = (
                hg_response.get("HierarchyGroup", {}).get("Arn", "")
            )
        except Exception:
            logger.debug("Could not resolve hierarchy group ARN. id=%s", hierarchy_id)

    result = {
        "arn":                  agent_arn,
        "id":                   user_id,
        "username":             user.get("Username", ""),
        "first_name":           identity.get("FirstName", ""),
        "last_name":            identity.get("LastName", ""),
        "email":                identity.get("Email", ""),
        "routing_profile_id":   routing_profile_id,
        "routing_profile_arn":  routing_profile_arn,
        "hierarchy_group_id":   hierarchy_id or None,
        "hierarchy_group_arn":  hierarchy_arn or None,
    }

    logger.debug(
        "Agent resolved. contact_id=%s username=%s", contact_id, result["username"]
    )
    _AGENT_CACHE[contact_id] = result
    return result


def bust_agent_cache(contact_id: str = None):
    """
    Invalidate the agent info cache.

    Parameters
    ----------
    contact_id:
        If supplied, only that contact's cached agent is evicted.
        If omitted, the entire cache is cleared.
    """
    global _AGENT_CACHE
    if contact_id is None:
        _AGENT_CACHE.clear()
        logger.debug("Agent cache cleared entirely.")
    else:
        _AGENT_CACHE.pop(contact_id, None)
        logger.debug("Agent cache entry removed. contact_id=%s", contact_id)


# ---------------------------------------------------------------------------
# Response builder
# ---------------------------------------------------------------------------

def build_response(**kwargs) -> dict:
    """
    Build a response dict for Amazon Connect.

    Amazon Connect's *Invoke AWS Lambda Function* block reads the return value
    as a flat mapping of string keys to string values.  This function coerces
    all values to ``str`` so the contact flow can use them in conditions and
    Set contact attributes blocks without type errors.

    .. warning::
        Booleans become ``'True'`` / ``'False'`` (Python's default
        ``str()`` representation).  If your flow needs lowercase ``'true'`` /
        ``'false'``, pass pre-formatted strings explicitly.

    Example::

        return build_response(
            status="200",
            queueName="SupportQueue",
            callbackEnabled="true",
        )
    """
    result = {k: str(v) for k, v in kwargs.items()}
    logger.debug("build_response: %s", result)
    return result


def build_error_response(error_code: str, message: str) -> dict:
    """
    Build a standardised error response for Amazon Connect.

    The contact flow can branch on ``$.Attributes.errorCode`` to route errors.

    Parameters
    ----------
    error_code:
        A short machine-readable code, e.g. ``'PARAMETER_NOT_FOUND'``.
    message:
        A human-readable description of the error.

    Returns
    -------
    dict
        ``{'errorCode': error_code, 'errorMessage': message}``
    """
    response = {"errorCode": str(error_code), "errorMessage": str(message)}
    logger.warning("build_error_response: %s", response)
    return response


# ---------------------------------------------------------------------------
# Lambda handler decorator
# ---------------------------------------------------------------------------

def connect_handler(logger_instance=None, raise_on_error: bool = False):
    """
    Decorator factory for Amazon Connect Lambda handlers.

    Wraps the decorated function so that:

    1. The raw ``event`` dict is replaced with a :class:`~event.ConnectEvent`
       instance before being passed to the function.
    2. Any unhandled exception is caught, logged, and converted to a
       structured :func:`build_error_response` dict rather than letting an
       uncaught traceback cause the contact flow to take a generic Error branch
       with no diagnostic data.

    The decorated function receives ``(connect_event: ConnectEvent, context)``
    **not** ``(event: dict, context)``.

    Parameters
    ----------
    logger_instance:
        A pre-configured :class:`logging.Logger`.  If ``None``, a logger named
        after the decorated function's module is created automatically.
    raise_on_error:
        When ``True``, exceptions are re-raised after logging instead of being
        converted to error responses.  Set this to ``True`` in unit tests so
        you can assert on raised exceptions directly.

    Example::

        from amazon_connect_lib import connect_handler, build_response

        @connect_handler()
        def lambda_handler(event, context):
            language = event.get_contact_attribute("language", default="en-US")
            queue = event.get_queue_name()
            return build_response(language=language, queue=queue or "")
    """
    def decorator(func):
        _log = logger_instance or logging.getLogger(func.__module__)

        @functools.wraps(func)
        def wrapper(event, context):
            connect_event = ConnectEvent(event)
            try:
                return func(connect_event, context)
            except Exception as exc:
                _log.exception("Unhandled exception in %s: %s", func.__name__, exc)
                if raise_on_error:
                    raise
                return build_error_response("UNHANDLED_EXCEPTION", str(exc))

        return wrapper
    return decorator
