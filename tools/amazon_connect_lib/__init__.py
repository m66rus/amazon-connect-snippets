"""
amazon_connect_lib
==================

A Python helper library for AWS Lambda functions invoked by Amazon Connect
contact flows.

Quick start::

    from amazon_connect_lib import ConnectEvent, build_response, connect_handler

    # Option 1 — use the decorator (recommended)
    @connect_handler()
    def lambda_handler(event, context):
        # event is already a ConnectEvent here
        caller   = event.get_customer_number()
        channel  = event.get_channel()
        language = event.get_contact_attribute("language", default="en-US")
        return build_response(caller=caller or "", channel=channel, language=language)

    # Option 2 — construct manually
    def lambda_handler(event, context):
        ce = ConnectEvent(event)
        return build_response(queue=ce.get_queue_name() or "default")

Public API
----------
ConnectEvent        Wraps the raw Connect Lambda event dict.
get_ssm_parameter   Fetch + cache an SSM Parameter Store value.
bust_ssm_cache      Invalidate the SSM parameter cache.
get_connect_agent   Fetch + cache agent info for a contact via the Connect API.
bust_agent_cache    Invalidate the agent info cache.
build_response      Build a flat string-value dict for Connect.
build_error_response Build a structured error dict for Connect.
connect_handler     Decorator: wraps event in ConnectEvent, catches exceptions.
"""

from .event import (
    ConnectEvent,
    CHANNEL_VOICE,
    CHANNEL_CHAT,
    CHANNEL_TASK,
    INITIATION_INBOUND,
    INITIATION_OUTBOUND,
    INITIATION_TRANSFER,
    INITIATION_CALLBACK,
    INITIATION_API,
    INITIATION_QUEUE_TRANSFER,
    INITIATION_DISCONNECT,
)
from .utils import (
    get_ssm_parameter,
    bust_ssm_cache,
    get_connect_agent,
    bust_agent_cache,
    build_response,
    build_error_response,
    connect_handler,
)

__version__ = "1.0.0"

__all__ = [
    # Core class
    "ConnectEvent",
    # Channel constants
    "CHANNEL_VOICE",
    "CHANNEL_CHAT",
    "CHANNEL_TASK",
    # Initiation method constants
    "INITIATION_INBOUND",
    "INITIATION_OUTBOUND",
    "INITIATION_TRANSFER",
    "INITIATION_CALLBACK",
    "INITIATION_API",
    "INITIATION_QUEUE_TRANSFER",
    "INITIATION_DISCONNECT",
    # Utilities
    "get_ssm_parameter",
    "bust_ssm_cache",
    "get_connect_agent",
    "bust_agent_cache",
    "build_response",
    "build_error_response",
    "connect_handler",
]
