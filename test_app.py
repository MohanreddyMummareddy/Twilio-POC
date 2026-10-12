from types import SimpleNamespace
from unittest.mock import Mock
from xml.etree import ElementTree

import pytest
from twilio.base.exceptions import TwilioException, TwilioRestException
from requests.exceptions import ConnectionError
from twilio.request_validator import RequestValidator

import app as module

REAL_REPLY_TO_WHATSAPP = module.reply_to_whatsapp

@pytest.fixture
def application():
    return module.create_app({
        "TESTING": True, "VALIDATE_TWILIO_REQUESTS": False,
        "SEND_API_KEY": "test-key", "TWILIO_AUTH_TOKEN": "test-token",
        "TWILIO_ACCOUNT_SID": "ACtest", "TWILIO_WHATSAPP_FROM": "whatsapp:+14155550100",
        "TWILIO_CONTENT_SID": "", "TWILIO_CONTENT_VARIABLES": "{}",
    })


@pytest.fixture(autouse=True)
def mock_send(monkeypatch):
    sender = Mock(return_value="SMtest")
    monkeypatch.setattr(module, "reply_to_whatsapp", sender)
    return sender


def test_health(application):
    assert application.test_client().get("/health").json == {"status": "ok"}


@pytest.mark.parametrize("text", ["hi", "hello", "start", " HI "])
def test_greeting(text):
    assert module.build_reply(text, "sender") == "Hello! Welcome to Twilio POC by Mohan. Send HELP to see available commands."


def test_commands():
    assert module.build_reply("HELP", "sender") == "Commands: HI, HELP, and STATUS."
    assert "sender" in module.build_reply("status", "sender")
    assert module.build_reply("A message", "sender") == "You said: A message"
    assert len(module.build_reply("x" * 1600, "sender")) == 1600


def test_webhook(application, mock_send):
    response = application.test_client().post("/whatsapp", data={
        "From": "whatsapp:+919999999999", "Body": "HELP",
    })
    assert response.status_code == 200
    assert response.mimetype == "application/xml"
    assert ElementTree.fromstring(response.data).find("Message").text == "Commands: HI, HELP, and STATUS."
    mock_send.assert_not_called()


def test_twiml_escapes_text_and_ignores_rest_template(application, mock_send):
    application.config.update(TWILIO_CONTENT_SID="HX" + "a" * 32,
        TWILIO_ACCOUNT_SID="", TWILIO_WHATSAPP_FROM="")
    response = application.test_client().post("/whatsapp", data={
        "From": "whatsapp:+919999999999", "Body": '<hello> & "world"',
    })
    assert response.status_code == 200
    root = ElementTree.fromstring(response.data)
    assert root.tag == "Response"
    assert root.find("Message").text == 'You said: <hello> & "world"'
    assert len(root.findall("Message")) == 1
    mock_send.assert_not_called()


@pytest.mark.parametrize("data", [{}, {"From": "whatsapp:+919999999999"},
    {"From": "sms:+919999999999", "Body": "hi"},
    {"From": "whatsapp:+919999999999", "Body": " "}])
def test_bad_webhook(application, mock_send, data):
    assert application.test_client().post("/whatsapp", data=data).status_code == 400
    mock_send.assert_not_called()


def test_signature_public_url(application, mock_send):
    application.config.update(VALIDATE_TWILIO_REQUESTS=True,
        PUBLIC_WEBHOOK_URL="https://example.com/whatsapp")
    data = {"From": "whatsapp:+919999999999", "Body": "hi"}
    client = application.test_client()
    assert client.post("/whatsapp", data=data).status_code == 403
    mock_send.assert_not_called()
    signature = RequestValidator("test-token").compute_signature("https://example.com/whatsapp", data)
    assert client.post("/whatsapp", data=data,
        headers={"X-Twilio-Signature": signature}).status_code == 200


def test_validation_enabled_by_default(monkeypatch):
    monkeypatch.delenv("VALIDATE_TWILIO_REQUESTS", raising=False)
    assert module.create_app().config["VALIDATE_TWILIO_REQUESTS"] is True


def test_missing_validation_token(application, mock_send):
    application.config.update(VALIDATE_TWILIO_REQUESTS=True, TWILIO_AUTH_TOKEN="")
    assert application.test_client().post("/whatsapp").status_code == 503
    mock_send.assert_not_called()


def test_manual_send(application, mock_send):
    response = application.test_client().post("/send", json={
        "to": "whatsapp:+919999999999", "body": "Hello",
    }, headers={"Authorization": "Bearer test-key"})
    assert response.status_code == 200
    mock_send.assert_called_once_with("whatsapp:+919999999999", "Hello")


@pytest.mark.parametrize("payload", [{}, [], {"to": 123, "body": "hi"},
    {"to": "whatsapp:+919999999999", "body": "x" * 1601}])
def test_bad_manual_send(application, mock_send, payload):
    assert application.test_client().post("/send", json=payload,
        headers={"Authorization": "Bearer test-key"}).status_code == 400
    mock_send.assert_not_called()


def test_manual_send_auth(application, mock_send):
    client = application.test_client()
    assert client.post("/send", json={}).status_code == 401
    application.config["SEND_API_KEY"] = ""
    assert client.post("/send", json={}).status_code == 503
    mock_send.assert_not_called()


@pytest.mark.parametrize("exception, status", [(TwilioException("private"), 502),
    (RuntimeError("private"), 503)])
def test_delivery_errors(application, mock_send, exception, status):
    mock_send.side_effect = exception
    response = application.test_client().post("/send", json={
        "to": "whatsapp:+919999999999", "body": "hi",
    }, headers={"Authorization": "Bearer test-key"})
    assert response.status_code == status
    assert "private" not in response.get_data(as_text=True)


def test_twilio_client(application, monkeypatch):
    # Restore the real helper while mocking the SDK, never contacting Twilio.
    client = Mock()
    client.messages.create.return_value = SimpleNamespace(sid="SMsdk")
    monkeypatch.setattr(module, "Client", Mock(return_value=client))
    with application.app_context():
        assert REAL_REPLY_TO_WHATSAPP("whatsapp:+919999999999", "Hello") == "SMsdk"
    client.messages.create.assert_called_once_with(to="whatsapp:+919999999999",
        from_="whatsapp:+14155550100", body="Hello")


def test_rest_error_logs_only_safe_diagnostics(application, mock_send, caplog):
    mock_send.side_effect = TwilioRestException(
        400, "https://private-url.example", msg="private-token private-message", code=63002
    )
    response = application.test_client().post("/send", json={
        "to": "whatsapp:+919999999999", "body": "private-body",
    }, headers={"Authorization": "Bearer test-key"})
    assert response.status_code == 502
    assert "error_code=63002 http_status=400" in caplog.text
    for private in ("private-token", "private-message", "private-url", "private-body", "+919999999999"):
        assert private not in caplog.text
        assert private not in response.get_data(as_text=True)


@pytest.mark.parametrize("exception", [TwilioException("private-token"), ConnectionError("private-token")])
def test_sdk_and_network_logs_are_safe(application, mock_send, caplog, exception):
    mock_send.side_effect = exception
    response = application.test_client().post("/send", json={
        "to": "whatsapp:+919999999999", "body": "hello",
    }, headers={"Authorization": "Bearer test-key"})

    assert response.status_code == 502
    assert "SDK or network error" in caplog.text
    assert "private-token" not in caplog.text


@pytest.mark.parametrize("validate, expected_status", [(False, 200), (True, 403)])
def test_webhook_arrival_and_response_logs(application, caplog, validate, expected_status):
    application.config["VALIDATE_TWILIO_REQUESTS"] = validate
    response = application.test_client().post("/whatsapp", data={
        "From": "whatsapp:+919999999999", "Body": "private-body",
    })
    assert response.status_code == expected_status
    assert "WhatsApp webhook received" in caplog.text
    assert f"WhatsApp webhook response: http_status={expected_status}" in caplog.text
    assert "private-body" not in caplog.text
    assert "+919999999999" not in caplog.text


def test_template_send(application, monkeypatch):
    application.config.update(TWILIO_CONTENT_SID="HXb5b62575e6e4ff6129ad7c8efe1f983e",
        TWILIO_CONTENT_VARIABLES='{"1":"12/1","2":"3pm"}')
    client = Mock()
    client.messages.create.return_value = SimpleNamespace(sid="SMtemplate")
    monkeypatch.setattr(module, "Client", Mock(return_value=client))
    with application.app_context():
        assert REAL_REPLY_TO_WHATSAPP("whatsapp:+919999999999", "hello") == "SMtemplate"
    options = client.messages.create.call_args.kwargs
    assert "body" not in options
    assert options["content_sid"] == application.config["TWILIO_CONTENT_SID"]
    import json
    assert json.loads(options["content_variables"]) == {"1": "12/1", "2": "3pm"}


@pytest.mark.parametrize("variables", ["invalid", "[]", '{"1":123}'])
def test_invalid_template_config(application, monkeypatch, variables):
    application.config.update(TWILIO_CONTENT_SID="HX" + "a" * 32,
        TWILIO_CONTENT_VARIABLES=variables)
    sdk = Mock()
    monkeypatch.setattr(module, "Client", sdk)
    with application.app_context(), pytest.raises(RuntimeError):
        REAL_REPLY_TO_WHATSAPP("whatsapp:+919999999999", "hello")
    sdk.assert_not_called()
