"""
Utilities for Amazon Connect Lambda functions:

  - SSM Parameter Store helper with warm-start caching
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
