"""Small WhatsApp text service; see HANDOFF.md for scope."""
import hmac
import json
import logging
import os
import re

from dotenv import load_dotenv
from flask import Flask, Response, current_app, jsonify, request
from requests.exceptions import RequestException
from twilio.base.exceptions import TwilioException, TwilioRestException
from twilio.http.http_client import TwilioHttpClient
from twilio.request_validator import RequestValidator
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse

load_dotenv()
WHATSAPP_ADDRESS = re.compile(r"whatsapp:\+[1-9]\d{6,14}\Z")


def build_reply(body, sender):
    command = body.strip().lower()
    if command in {"hi", "hello", "start"}:
        return "Hello! Send HELP to see available commands."
    if command == "help":
        return "Commands: HI, HELP, and STATUS."
    if command == "status":
        return f"Your message from {sender} was received. Service is running."
    return f"You said: {body.strip()}"[:1600]


def reply_to_whatsapp(to, body):
    config = current_app.config
    if not all(config.get(key) for key in (
        "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_WHATSAPP_FROM"
    )):
        raise RuntimeError("Twilio configuration is incomplete")
    if not WHATSAPP_ADDRESS.fullmatch(config["TWILIO_WHATSAPP_FROM"]):
        raise RuntimeError("Twilio sender configuration is invalid")
    message_options = {"body": body}
    if config.get("TWILIO_CONTENT_SID"):
        if not re.fullmatch(r"HX[0-9a-fA-F]{32}", config["TWILIO_CONTENT_SID"]):
            raise RuntimeError("Invalid template SID")
        try:
            variables = json.loads(config.get("TWILIO_CONTENT_VARIABLES", "{}"))
        except (ValueError, TypeError):
            raise RuntimeError("Invalid template variables") from None
        if not isinstance(variables, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in variables.items()
        ):
            raise RuntimeError("Invalid template variables")
        message_options = {
            "content_sid": config["TWILIO_CONTENT_SID"],
            "content_variables": json.dumps(variables),
        }
    client = Client(
        config["TWILIO_ACCOUNT_SID"], config["TWILIO_AUTH_TOKEN"],
        http_client=TwilioHttpClient(timeout=15),
    )
    return client.messages.create(
        to=to, from_=config["TWILIO_WHATSAPP_FROM"], **message_options
    ).sid


def create_app(test_config=None):
    application = Flask(__name__)
    application.logger.setLevel(logging.INFO)
    application.config.from_mapping(
        TWILIO_ACCOUNT_SID=os.getenv("TWILIO_ACCOUNT_SID", ""),
        TWILIO_AUTH_TOKEN=os.getenv("TWILIO_AUTH_TOKEN", ""),
        TWILIO_WHATSAPP_FROM=os.getenv("TWILIO_WHATSAPP_FROM", ""),
        TWILIO_CONTENT_SID=os.getenv("TWILIO_CONTENT_SID", ""),
        TWILIO_CONTENT_VARIABLES=os.getenv("TWILIO_CONTENT_VARIABLES", "{}"),
        VALIDATE_TWILIO_REQUESTS=os.getenv("VALIDATE_TWILIO_REQUESTS", "true").lower() != "false",
        PUBLIC_WEBHOOK_URL=os.getenv("PUBLIC_WEBHOOK_URL", ""),
        SEND_API_KEY=os.getenv("SEND_API_KEY", ""),
        MAX_CONTENT_LENGTH=64 * 1024,
    )
    if test_config:
        application.config.update(test_config)

    @application.before_request
    def log_webhook_received():
        if request.path == "/whatsapp" and request.method == "POST":
            application.logger.info("WhatsApp webhook received")

    @application.after_request
    def log_webhook_response(response):
        if request.path == "/whatsapp" and request.method == "POST":
            application.logger.info("WhatsApp webhook response: http_status=%s", response.status_code)
        return response

    def send_message(to, body):
        try:
            return jsonify(message_sid=reply_to_whatsapp(to, body)), 200
        except RuntimeError:
            return jsonify(error="Twilio configuration is incomplete or invalid"), 503
        except TwilioRestException as error:
            # Log only numeric diagnostics, never exception text or request data.
            code = error.code if isinstance(error.code, int) else None
            status = error.status if isinstance(error.status, int) else None
            application.logger.error(
                "Twilio message delivery failed: error_code=%s http_status=%s", code, status
            )
            return jsonify(error="Twilio message delivery failed"), 502
        except (TwilioException, RequestException):
            application.logger.error("Twilio message delivery failed: SDK or network error")
            return jsonify(error="Twilio message delivery failed"), 502

    @application.get("/health")
    def health():
        return jsonify(status="ok")

    @application.post("/whatsapp")
    def whatsapp():
        if application.config["VALIDATE_TWILIO_REQUESTS"]:
            token = application.config["TWILIO_AUTH_TOKEN"]
            if not token:
                return jsonify(error="Twilio signature validation is not configured"), 503
            # An explicit URL avoids trusting forwarded headers on public hosts.
            url = application.config["PUBLIC_WEBHOOK_URL"] or request.url
            if not RequestValidator(token).validate(
                url, request.form, request.headers.get("X-Twilio-Signature", "")
            ):
                return jsonify(error="Invalid Twilio signature"), 403
        sender = request.form.get("From", "")
        body = request.form.get("Body", "")
        if not WHATSAPP_ADDRESS.fullmatch(sender) or not body.strip() or len(body) > 1600:
            return jsonify(error="Valid WhatsApp From and text Body (1-1600 characters) are required"), 400
        response = MessagingResponse()
        response.message(build_reply(body, sender))
        return Response(str(response), mimetype="application/xml")

    @application.post("/send")
    def send():
        key = application.config["SEND_API_KEY"]
        if not key:
            return jsonify(error="Manual sending is disabled; configure SEND_API_KEY"), 503
        if not hmac.compare_digest(request.headers.get("Authorization", ""), f"Bearer {key}"):
            return jsonify(error="Unauthorized"), 401
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(error="A JSON object is required"), 400
        to, body = payload.get("to"), payload.get("body")
        if (not isinstance(to, str) or not WHATSAPP_ADDRESS.fullmatch(to)
                or not isinstance(body, str) or not body.strip() or len(body) > 1600):
            return jsonify(error="Valid WhatsApp to and text body (1-1600 characters) are required"), 400
        return send_message(to, body)

    return application


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")))
