"""
Example Lambda function showing how to use amazon_connect_lib.

Deploy this file alongside the amazon_connect_lib/ package directory.
"""

import logging
import os

from amazon_connect_lib import (
    connect_handler,
    build_response,
    build_error_response,
    get_ssm_parameter,
)

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


@connect_handler(logger_instance=logger)
def lambda_handler(event, context):
    """
    'event' is a ConnectEvent here (the decorator wraps it automatically).

    This example reads caller info, a contact attribute, a flow parameter,
    and an SSM parameter, then returns them all to the contact flow.
    """

    # --- Channel and endpoint info ---
    channel = event.get_channel()                       # 'VOICE', 'CHAT', 'TASK'
    caller_number = event.get_customer_number()         # E.164 or None
    dialled_number = event.get_system_number()          # E.164 or None
    initiation = event.get_initiation_method()          # 'INBOUND', 'TRANSFER', etc.

    # --- Contact attributes set earlier in the flow ---
    language = event.get_contact_attribute("language", default="en-US")
    priority = event.get_contact_attribute("priority", default="normal")

    # --- Parameters passed by the Invoke Lambda block ---
    action = event.get_parameter("action", default="greet")

    # --- Queue the contact is currently in (may be None before routing) ---
    queue_name = event.get_queue_name() or "unqueued"

    # --- SSM Parameter Store (e.g. a feature flag or config value) ---
    # The value is cached in memory after the first Lambda warm invocation.
    greeting_msg = get_ssm_parameter("/myapp/connect/greetingMessage")

    logger.info(
        "Contact: id=%s channel=%s initiation=%s caller=%s dialled=%s queue=%s",
        event.get_contact_id(),
        channel,
        initiation,
        caller_number,
        dialled_number,
        queue_name,
    )

    # All values are coerced to strings by build_response.
    return build_response(
        channel=channel,
        callerNumber=caller_number or "",
        dialledNumber=dialled_number or "",
        initiationMethod=initiation,
        language=language,
        priority=priority,
        action=action,
        queueName=queue_name,
        greetingMessage=greeting_msg,
    )
