# Twilio WhatsApp text service

A standalone Flask application following [HANDOFF.md](HANDOFF.md). It receives
WhatsApp text at `POST /whatsapp` and replies through the Twilio Messages API.
Commands: HI, HELLO, START, HELP, STATUS; other messages are echoed.

## Local setup (Windows PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` locally with your account SID, Auth Token, and the exact WhatsApp
sender shown in your Twilio Console. Never paste the Auth Token into chat or
commit `.env`. Set `SEND_API_KEY` to a private random token if you need `/send`.
It is disabled when the key is blank, and requires `Authorization: Bearer <key>`.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe app.py
curl.exe http://127.0.0.1:5000/health
```

Tests mock Twilio and need no credentials. For an unsigned local webhook test,
start the server with the following setting (real sends still require credentials):

```powershell
$env:VALIDATE_TWILIO_REQUESTS='false'
.\.venv\Scripts\python.exe app.py
```

In another terminal:

```powershell
curl.exe -X POST http://127.0.0.1:5000/whatsapp -d "Body=HELP" --data-urlencode "From=whatsapp:+919999999999"
```

`/send` takes JSON with `to` (for example `whatsapp:+919999999999`) and `body`.
Text must be nonempty and at most 1600 characters. Successful sends return
`{"message_sid":"SM..."}`. Errors return JSON with an `error` field.
Health reports that the process is running; it does not verify Twilio credentials.

## Public deployment and Twilio setup

Use an organization-approved Linux host with public HTTPS ingress and outbound
HTTPS access to Twilio. Install `requirements.txt` and start:

```sh
gunicorn --bind 0.0.0.0:${PORT:-5000} app:app
```

For Azure App Service, use a Python Linux app, configure the environment variables
in app settings, and set the startup command to `gunicorn --bind 0.0.0.0:8000 app:app`.
An optional Render configuration is included in `render.yaml`.

Set `VALIDATE_TWILIO_REQUESTS=true` and `PUBLIC_WEBHOOK_URL` to the exact external
HTTPS webhook URL, such as `https://your-host/whatsapp`. This is necessary behind
proxies when Flask sees an internal URL rather than the signed public URL.
Store credentials in the host's secret settings. Keep `/send` disabled unless needed.

In Twilio Console, open Messaging > WhatsApp > Try out WhatsApp, link your phone
using its displayed QR code or join instructions, and select the inbound/custom
auto-reply webhook configuration. Set its method to POST and URL to your public
`/whatsapp` URL. Use the sender shown there, not an assumed sandbox number.
Send HELP from the linked phone and verify the reply and Twilio message logs.
The server must be running and reachable: Twilio cannot reach `127.0.0.1`.

The trial flow restricts direct TwiML responses, so this app uses REST API replies.
Trial recipient, template, and outbound restrictions still apply. See Twilio's
[trial WhatsApp guide](https://www.twilio.com/docs/usage/trials/try-out-whatsapp)
and [request validation implementation](https://github.com/twilio/twilio-python/blob/main/twilio/request_validator.py).

This POC sends synchronously and does not persist webhook deduplication state.
Repeated webhook delivery can send repeated replies. A live WhatsApp exchange
requires configured credentials, an approved public host, and a linked recipient.
