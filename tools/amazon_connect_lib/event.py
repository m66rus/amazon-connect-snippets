"""
ConnectEvent: a read-only wrapper around the Amazon Connect Lambda event dict.

Amazon Connect invokes a Lambda function with an event shaped like:

    {
        "Details": {
            "ContactData": {
                "Attributes": {},
                "Channel": "VOICE",
                "ContactId": "abc-123",
                "CustomerEndpoint": {"Address": "+1234567890", "Type": "TELEPHONE_NUMBER"},
                "InitialContactId": "abc-123",
                "InitiationMethod": "INBOUND",
                "InstanceARN": "arn:aws:connect:...",
                "PreviousContactId": "",
                "Queue": {"ARN": "arn:aws:connect:...", "Name": "BasicQueue"},
                "SystemEndpoint": {"Address": "+0987654321", "Type": "TELEPHONE_NUMBER"},
                "MediaStreams": {...}
            },
            "Parameters": {
                "myParam": "someValue"
            }
        },
        "Name": "ContactFlowEvent"
    }

This module has no AWS SDK dependency and can be imported in any environment.
"""

import logging

logger = logging.getLogger(__name__)

# Valid channel values returned by Amazon Connect
CHANNEL_VOICE = "VOICE"
CHANNEL_CHAT = "CHAT"
CHANNEL_TASK = "TASK"

# Valid initiation method values
INITIATION_INBOUND = "INBOUND"
INITIATION_OUTBOUND = "OUTBOUND"
INITIATION_TRANSFER = "TRANSFER"
INITIATION_CALLBACK = "CALLBACK"
INITIATION_API = "API"
INITIATION_QUEUE_TRANSFER = "QUEUE_TRANSFER"
INITIATION_DISCONNECT = "DISCONNECT"


class ConnectEvent:
    """
    Wraps the raw Amazon Connect Lambda event and exposes typed accessors.

    Usage::

        def lambda_handler(event, context):
            ce = ConnectEvent(event)
            channel = ce.get_channel()
            caller = ce.get_customer_number()
            lang = ce.get_contact_attribute("language", default="en-US")
            return build_response(greeting=f"Hello from {channel}")

    Note: Every accessor returns ``None`` (or the supplied ``default``) rather
    than raising ``KeyError`` when a field is absent.  This matches the
    defensive style used throughout the rest of this project.
    """

    def __init__(self, event: dict):
        """
        Parameters
        ----------
        event:
            The raw Lambda event dict passed in by Amazon Connect.
        """
        self._raw = event
        details = event.get("Details", {})
        self._contact_data = details.get("ContactData", {})
        self._parameters = details.get("Parameters", {})
        logger.debug("ConnectEvent initialised. ContactId=%s Channel=%s",
                     self._contact_data.get("ContactId"), self._contact_data.get("Channel"))

    # ------------------------------------------------------------------
    # Channel
    # ------------------------------------------------------------------

    def get_channel(self) -> str:
        """Return the contact channel: ``'VOICE'``, ``'CHAT'``, or ``'TASK'``."""
        return self._contact_data.get("Channel", "")

    def is_voice(self) -> bool:
        """Return ``True`` when the channel is VOICE."""
        return self.get_channel() == CHANNEL_VOICE

    def is_chat(self) -> bool:
        """Return ``True`` when the channel is CHAT."""
        return self.get_channel() == CHANNEL_CHAT

    def is_task(self) -> bool:
        """Return ``True`` when the channel is TASK."""
        return self.get_channel() == CHANNEL_TASK

    # ------------------------------------------------------------------
    # Contact identifiers
    # ------------------------------------------------------------------

    def get_contact_id(self) -> str:
        """Return the unique identifier for this contact leg."""
        return self._contact_data.get("ContactId", "")

    def get_initial_contact_id(self) -> str:
        """Return the ContactId of the first leg in the contact chain."""
        return self._contact_data.get("InitialContactId", "")

    def get_previous_contact_id(self):
        """
        Return the ContactId of the previous contact leg, or ``None``.

        Amazon Connect always includes this field but sets it to an empty string
        when there is no previous contact.  This method normalises that to
        ``None`` so callers do not need to check ``if prev and prev != ""``.
        """
        value = self._contact_data.get("PreviousContactId", "")
        return value if value else None

    # ------------------------------------------------------------------
    # Instance
    # ------------------------------------------------------------------

    def get_instance_arn(self) -> str:
        """Return the ARN of the Amazon Connect instance."""
        return self._contact_data.get("InstanceARN", "")

    # ------------------------------------------------------------------
    # Initiation
    # ------------------------------------------------------------------

    def get_initiation_method(self) -> str:
        """
        Return how the contact was initiated.

        Possible values: ``'INBOUND'``, ``'OUTBOUND'``, ``'TRANSFER'``,
        ``'CALLBACK'``, ``'API'``, ``'QUEUE_TRANSFER'``, ``'DISCONNECT'``.
        """
        return self._contact_data.get("InitiationMethod", "")

    def is_inbound(self) -> bool:
        """Return ``True`` when the contact was initiated inbound by the customer."""
        return self.get_initiation_method() == INITIATION_INBOUND

    def is_outbound(self) -> bool:
        """Return ``True`` when the contact was initiated as an outbound call."""
        return self.get_initiation_method() == INITIATION_OUTBOUND

    def is_transfer(self) -> bool:
        """Return ``True`` when the contact arrived via an agent or flow transfer."""
        return self.get_initiation_method() in (INITIATION_TRANSFER, INITIATION_QUEUE_TRANSFER)

    def is_callback(self) -> bool:
        """Return ``True`` when the contact is a callback."""
        return self.get_initiation_method() == INITIATION_CALLBACK

    # ------------------------------------------------------------------
    # Endpoints (phone numbers)
    # ------------------------------------------------------------------

    def get_customer_number(self):
        """
        Return the customer's phone number (E.164 format), or ``None``.

        ``None`` is returned when there is no CustomerEndpoint, which can
        happen for contacts initiated via the API or for some chat contacts.
        """
        endpoint = self._contact_data.get("CustomerEndpoint") or {}
        address = endpoint.get("Address", "")
        return address if address else None

    def get_customer_endpoint_type(self):
        """
        Return the customer endpoint type (e.g. ``'TELEPHONE_NUMBER'``), or ``None``.
        """
        endpoint = self._contact_data.get("CustomerEndpoint") or {}
        endpoint_type = endpoint.get("Type", "")
        return endpoint_type if endpoint_type else None

    def get_system_number(self):
        """
        Return the system (DNIS) phone number the customer dialled (E.164), or ``None``.
        """
        endpoint = self._contact_data.get("SystemEndpoint") or {}
        address = endpoint.get("Address", "")
        return address if address else None

    def get_system_endpoint_type(self):
        """
        Return the system endpoint type (e.g. ``'TELEPHONE_NUMBER'``), or ``None``.
        """
        endpoint = self._contact_data.get("SystemEndpoint") or {}
        endpoint_type = endpoint.get("Type", "")
        return endpoint_type if endpoint_type else None

    # ------------------------------------------------------------------
    # Queue
    # ------------------------------------------------------------------

    def get_queue_arn(self):
        """Return the ARN of the current queue, or ``None`` if not in a queue."""
        queue = self._contact_data.get("Queue") or {}
        arn = queue.get("ARN", "")
        return arn if arn else None

    def get_queue_name(self):
        """Return the name of the current queue, or ``None`` if not in a queue."""
        queue = self._contact_data.get("Queue") or {}
        name = queue.get("Name", "")
        return name if name else None

    # ------------------------------------------------------------------
    # Contact attributes (set by Set contact attributes blocks)
    # ------------------------------------------------------------------

    def get_contact_attribute(self, key: str, default=None):
        """
        Return the value of a contact attribute, or ``default`` if not set.

        Parameters
        ----------
        key:
            The attribute name as configured in the contact flow.
        default:
            Value returned when the attribute is absent.  Defaults to ``None``.
        """
        return self._contact_data.get("Attributes", {}).get(key, default)

    def get_all_attributes(self) -> dict:
        """Return a shallow copy of all contact attributes."""
        return dict(self._contact_data.get("Attributes", {}))

    # ------------------------------------------------------------------
    # Contact flow parameters (passed by the Invoke Lambda block)
    # ------------------------------------------------------------------

    def get_parameter(self, key: str, default=None):
        """
        Return a parameter passed from the contact flow's Lambda block.

        Parameters
        ----------
        key:
            The parameter name as configured in the Invoke Lambda Function block.
        default:
            Value returned when the parameter is absent.  Defaults to ``None``.
        """
        return self._parameters.get(key, default)

    def get_all_parameters(self) -> dict:
        """Return a shallow copy of all contact flow parameters."""
        return dict(self._parameters)

    # ------------------------------------------------------------------
    # Media streams (Kinesis Video Streams)
    # ------------------------------------------------------------------

    def get_customer_audio_stream_arn(self):
        """
        Return the Kinesis Video Stream ARN for the customer audio leg, or ``None``.

        Only present when live media streaming is enabled on the instance.
        """
        media = self._contact_data.get("MediaStreams", {})
        customer = media.get("Customer", {})
        audio = customer.get("Audio", {})
        arn = audio.get("StreamARN", "")
        return arn if arn else None

    # ------------------------------------------------------------------
    # Raw access
    # ------------------------------------------------------------------

    def raw(self) -> dict:
        """Return the original unmodified event dict."""
        return self._raw
