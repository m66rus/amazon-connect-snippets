"""
Unit tests for amazon_connect_lib.

Run with:  python -m pytest tools/tests/ -v
No AWS credentials required — all AWS calls are mocked.
"""

import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Allow importing the library from one level up when running tests directly.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from amazon_connect_lib import (
    ConnectEvent,
    build_response,
    build_error_response,
    connect_handler,
    bust_ssm_cache,
    CHANNEL_VOICE,
    CHANNEL_CHAT,
    CHANNEL_TASK,
)
from amazon_connect_lib import utils as _utils


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_event(
    channel="VOICE",
    contact_id="contact-001",
    initial_contact_id="contact-001",
    previous_contact_id="",
    initiation_method="INBOUND",
    customer_address="+15550001111",
    system_address="+15559999999",
    attributes=None,
    parameters=None,
    queue_arn="arn:aws:connect:us-east-1:123456789012:instance/abc/queue/xyz",
    queue_name="SupportQueue",
    instance_arn="arn:aws:connect:us-east-1:123456789012:instance/abc",
):
    return {
        "Name": "ContactFlowEvent",
        "Details": {
            "ContactData": {
                "Channel": channel,
                "ContactId": contact_id,
                "InitialContactId": initial_contact_id,
                "PreviousContactId": previous_contact_id,
                "InitiationMethod": initiation_method,
                "InstanceARN": instance_arn,
                "CustomerEndpoint": {"Address": customer_address, "Type": "TELEPHONE_NUMBER"},
                "SystemEndpoint": {"Address": system_address, "Type": "TELEPHONE_NUMBER"},
                "Attributes": attributes or {},
                "Queue": {"ARN": queue_arn, "Name": queue_name},
                "MediaStreams": {
                    "Customer": {
                        "Audio": {
                            "StreamARN": "arn:aws:kinesisvideo:us-east-1:123456789012:stream/abc/000",
                            "StartTimestamp": "1609459200.0",
                            "StartFragmentNumber": "91343852333181432392682062622244200860992244078",
                        }
                    }
                },
            },
            "Parameters": parameters or {},
        },
    }


# ---------------------------------------------------------------------------
# ConnectEvent tests
# ---------------------------------------------------------------------------

class TestConnectEventChannel(unittest.TestCase):

    def test_get_channel_voice(self):
        ce = ConnectEvent(_make_event(channel="VOICE"))
        self.assertEqual(ce.get_channel(), "VOICE")

    def test_get_channel_chat(self):
        ce = ConnectEvent(_make_event(channel="CHAT"))
        self.assertEqual(ce.get_channel(), "CHAT")

    def test_get_channel_task(self):
        ce = ConnectEvent(_make_event(channel="TASK"))
        self.assertEqual(ce.get_channel(), "TASK")

    def test_is_voice(self):
        ce = ConnectEvent(_make_event(channel="VOICE"))
        self.assertTrue(ce.is_voice())
        self.assertFalse(ce.is_chat())
        self.assertFalse(ce.is_task())

    def test_is_chat(self):
        ce = ConnectEvent(_make_event(channel="CHAT"))
        self.assertTrue(ce.is_chat())
        self.assertFalse(ce.is_voice())

    def test_is_task(self):
        ce = ConnectEvent(_make_event(channel="TASK"))
        self.assertTrue(ce.is_task())
        self.assertFalse(ce.is_voice())


class TestConnectEventContactIds(unittest.TestCase):

    def test_get_contact_id(self):
        ce = ConnectEvent(_make_event(contact_id="abc-123"))
        self.assertEqual(ce.get_contact_id(), "abc-123")

    def test_get_initial_contact_id(self):
        ce = ConnectEvent(_make_event(initial_contact_id="abc-000"))
        self.assertEqual(ce.get_initial_contact_id(), "abc-000")

    def test_get_previous_contact_id_empty_string_returns_none(self):
        ce = ConnectEvent(_make_event(previous_contact_id=""))
        self.assertIsNone(ce.get_previous_contact_id())

    def test_get_previous_contact_id_returns_value(self):
        ce = ConnectEvent(_make_event(previous_contact_id="prev-456"))
        self.assertEqual(ce.get_previous_contact_id(), "prev-456")


class TestConnectEventInitiation(unittest.TestCase):

    def test_get_initiation_method(self):
        ce = ConnectEvent(_make_event(initiation_method="INBOUND"))
        self.assertEqual(ce.get_initiation_method(), "INBOUND")

    def test_is_inbound(self):
        ce = ConnectEvent(_make_event(initiation_method="INBOUND"))
        self.assertTrue(ce.is_inbound())
        self.assertFalse(ce.is_outbound())
        self.assertFalse(ce.is_transfer())

    def test_is_outbound(self):
        ce = ConnectEvent(_make_event(initiation_method="OUTBOUND"))
        self.assertTrue(ce.is_outbound())

    def test_is_transfer(self):
        ce = ConnectEvent(_make_event(initiation_method="TRANSFER"))
        self.assertTrue(ce.is_transfer())

    def test_is_transfer_queue_transfer(self):
        ce = ConnectEvent(_make_event(initiation_method="QUEUE_TRANSFER"))
        self.assertTrue(ce.is_transfer())

    def test_is_callback(self):
        ce = ConnectEvent(_make_event(initiation_method="CALLBACK"))
        self.assertTrue(ce.is_callback())


class TestConnectEventEndpoints(unittest.TestCase):

    def test_get_customer_number(self):
        ce = ConnectEvent(_make_event(customer_address="+15550001111"))
        self.assertEqual(ce.get_customer_number(), "+15550001111")

    def test_get_system_number(self):
        ce = ConnectEvent(_make_event(system_address="+15559999999"))
        self.assertEqual(ce.get_system_number(), "+15559999999")

    def test_get_customer_number_absent_returns_none(self):
        event = _make_event()
        del event["Details"]["ContactData"]["CustomerEndpoint"]
        ce = ConnectEvent(event)
        self.assertIsNone(ce.get_customer_number())

    def test_get_customer_number_empty_address_returns_none(self):
        ce = ConnectEvent(_make_event(customer_address=""))
        self.assertIsNone(ce.get_customer_number())

    def test_get_system_number_absent_returns_none(self):
        event = _make_event()
        del event["Details"]["ContactData"]["SystemEndpoint"]
        ce = ConnectEvent(event)
        self.assertIsNone(ce.get_system_number())


class TestConnectEventQueue(unittest.TestCase):

    def test_get_queue_arn(self):
        ce = ConnectEvent(_make_event(queue_arn="arn:aws:connect:us-east-1:123:instance/abc/queue/xyz"))
        self.assertEqual(ce.get_queue_arn(), "arn:aws:connect:us-east-1:123:instance/abc/queue/xyz")

    def test_get_queue_name(self):
        ce = ConnectEvent(_make_event(queue_name="SupportQueue"))
        self.assertEqual(ce.get_queue_name(), "SupportQueue")

    def test_get_queue_arn_absent_returns_none(self):
        event = _make_event()
        del event["Details"]["ContactData"]["Queue"]
        ce = ConnectEvent(event)
        self.assertIsNone(ce.get_queue_arn())

    def test_get_queue_name_empty_returns_none(self):
        event = _make_event()
        event["Details"]["ContactData"]["Queue"]["Name"] = ""
        ce = ConnectEvent(event)
        self.assertIsNone(ce.get_queue_name())


class TestConnectEventAttributes(unittest.TestCase):

    def test_get_contact_attribute_present(self):
        ce = ConnectEvent(_make_event(attributes={"language": "fr-FR"}))
        self.assertEqual(ce.get_contact_attribute("language"), "fr-FR")

    def test_get_contact_attribute_absent_returns_default(self):
        ce = ConnectEvent(_make_event(attributes={}))
        self.assertEqual(ce.get_contact_attribute("missing", default="en-US"), "en-US")

    def test_get_contact_attribute_absent_returns_none_by_default(self):
        ce = ConnectEvent(_make_event(attributes={}))
        self.assertIsNone(ce.get_contact_attribute("missing"))

    def test_get_all_attributes_returns_copy(self):
        attrs = {"a": "1", "b": "2"}
        ce = ConnectEvent(_make_event(attributes=attrs))
        result = ce.get_all_attributes()
        self.assertEqual(result, attrs)
        result["a"] = "mutated"
        # Original should not be affected
        self.assertEqual(ce.get_contact_attribute("a"), "1")


class TestConnectEventParameters(unittest.TestCase):

    def test_get_parameter_present(self):
        ce = ConnectEvent(_make_event(parameters={"action": "lookup"}))
        self.assertEqual(ce.get_parameter("action"), "lookup")

    def test_get_parameter_absent_returns_default(self):
        ce = ConnectEvent(_make_event(parameters={}))
        self.assertEqual(ce.get_parameter("missing", default="greet"), "greet")

    def test_get_all_parameters_returns_copy(self):
        params = {"x": "1"}
        ce = ConnectEvent(_make_event(parameters=params))
        result = ce.get_all_parameters()
        self.assertEqual(result, params)


class TestConnectEventMediaStreams(unittest.TestCase):

    def test_get_customer_audio_stream_arn(self):
        ce = ConnectEvent(_make_event())
        arn = ce.get_customer_audio_stream_arn()
        self.assertIn("kinesisvideo", arn)

    def test_get_customer_audio_stream_arn_absent_returns_none(self):
        event = _make_event()
        del event["Details"]["ContactData"]["MediaStreams"]
        ce = ConnectEvent(event)
        self.assertIsNone(ce.get_customer_audio_stream_arn())


class TestConnectEventRaw(unittest.TestCase):

    def test_raw_returns_original_event(self):
        event = _make_event()
        ce = ConnectEvent(event)
        self.assertIs(ce.raw(), event)


class TestConnectEventMissingDetails(unittest.TestCase):
    """ConnectEvent should not raise when the event is malformed / empty."""

    def test_empty_event(self):
        ce = ConnectEvent({})
        self.assertEqual(ce.get_channel(), "")
        self.assertEqual(ce.get_contact_id(), "")
        self.assertIsNone(ce.get_customer_number())
        self.assertIsNone(ce.get_queue_name())
        self.assertEqual(ce.get_all_attributes(), {})
        self.assertEqual(ce.get_all_parameters(), {})


# ---------------------------------------------------------------------------
# Response builder tests
# ---------------------------------------------------------------------------

class TestBuildResponse(unittest.TestCase):

    def test_string_values_passed_through(self):
        result = build_response(status="200", queueName="Support")
        self.assertEqual(result, {"status": "200", "queueName": "Support"})

    def test_non_string_values_coerced(self):
        result = build_response(count=42, flag=True, score=3.14)
        self.assertEqual(result["count"], "42")
        self.assertEqual(result["flag"], "True")
        self.assertEqual(result["score"], "3.14")

    def test_empty_response(self):
        result = build_response()
        self.assertEqual(result, {})


class TestBuildErrorResponse(unittest.TestCase):

    def test_error_response_keys(self):
        result = build_error_response("NOT_FOUND", "Parameter missing")
        self.assertEqual(result["errorCode"], "NOT_FOUND")
        self.assertEqual(result["errorMessage"], "Parameter missing")

    def test_error_values_coerced_to_string(self):
        result = build_error_response(404, RuntimeError("oops"))
        self.assertEqual(result["errorCode"], "404")
        self.assertEqual(result["errorMessage"], "oops")


# ---------------------------------------------------------------------------
# SSM helper tests
# ---------------------------------------------------------------------------

class TestGetSsmParameter(unittest.TestCase):

    def setUp(self):
        # Reset the module-level cache and client before each test
        bust_ssm_cache()
        _utils._ssm_client = None

    def _make_ssm_client(self, value="secret-value"):
        mock_client = MagicMock()
        mock_client.get_parameter.return_value = {
            "Parameter": {"Value": value}
        }
        return mock_client

    def test_fetches_parameter_from_ssm(self):
        mock_client = self._make_ssm_client("my-secret")
        with patch("amazon_connect_lib.utils._get_ssm_client", return_value=mock_client):
            from amazon_connect_lib import get_ssm_parameter
            result = get_ssm_parameter("/my/param")
        self.assertEqual(result, "my-secret")
        mock_client.get_parameter.assert_called_once_with(Name="/my/param", WithDecryption=True)

    def test_caches_result_on_second_call(self):
        mock_client = self._make_ssm_client("cached-value")
        with patch("amazon_connect_lib.utils._get_ssm_client", return_value=mock_client):
            from amazon_connect_lib import get_ssm_parameter
            get_ssm_parameter("/my/param")
            get_ssm_parameter("/my/param")
        # SSM should only be called once
        self.assertEqual(mock_client.get_parameter.call_count, 1)

    def test_bust_cache_clears_specific_key(self):
        mock_client = self._make_ssm_client("value")
        with patch("amazon_connect_lib.utils._get_ssm_client", return_value=mock_client):
            from amazon_connect_lib import get_ssm_parameter
            get_ssm_parameter("/my/param")
            bust_ssm_cache("/my/param")
            get_ssm_parameter("/my/param")
        self.assertEqual(mock_client.get_parameter.call_count, 2)

    def test_bust_cache_clears_all(self):
        mock_client = self._make_ssm_client("value")
        with patch("amazon_connect_lib.utils._get_ssm_client", return_value=mock_client):
            from amazon_connect_lib import get_ssm_parameter
            get_ssm_parameter("/my/param")
            get_ssm_parameter("/other/param")
            bust_ssm_cache()
            get_ssm_parameter("/my/param")
            get_ssm_parameter("/other/param")
        self.assertEqual(mock_client.get_parameter.call_count, 4)


# ---------------------------------------------------------------------------
# connect_handler decorator tests
# ---------------------------------------------------------------------------

class TestConnectHandlerDecorator(unittest.TestCase):

    def test_event_is_wrapped_in_connect_event(self):
        received = []

        @connect_handler()
        def handler(event, context):
            received.append(event)
            return {}

        handler(_make_event(), None)
        self.assertIsInstance(received[0], ConnectEvent)

    def test_return_value_is_passed_through(self):
        @connect_handler()
        def handler(event, context):
            return build_response(result="ok")

        result = handler(_make_event(), None)
        self.assertEqual(result, {"result": "ok"})

    def test_unhandled_exception_returns_error_response(self):
        @connect_handler()
        def handler(event, context):
            raise ValueError("something went wrong")

        result = handler(_make_event(), None)
        self.assertEqual(result["errorCode"], "UNHANDLED_EXCEPTION")
        self.assertIn("something went wrong", result["errorMessage"])

    def test_raise_on_error_re_raises(self):
        @connect_handler(raise_on_error=True)
        def handler(event, context):
            raise ValueError("boom")

        with self.assertRaises(ValueError):
            handler(_make_event(), None)

    def test_connect_event_methods_accessible(self):
        results = {}

        @connect_handler()
        def handler(event, context):
            results["channel"] = event.get_channel()
            results["caller"] = event.get_customer_number()
            results["queue"] = event.get_queue_name()
            return {}

        handler(_make_event(channel="VOICE", customer_address="+15550001111", queue_name="SupportQueue"), None)
        self.assertEqual(results["channel"], "VOICE")
        self.assertEqual(results["caller"], "+15550001111")
        self.assertEqual(results["queue"], "SupportQueue")


if __name__ == "__main__":
    unittest.main()
