# Coding assistant handoff prompt

## Current implementation update — 12 October 2026

The user selected the legacy WhatsApp Sandbox. `POST /whatsapp` now returns
`application/xml` TwiML with a Message containing the custom reply, after Twilio
signature validation. It does not call the REST API or return a message SID.
The original REST-only webhook description below is historical and superseded.
The authenticated `/send` endpoint retains REST sending and optional ContentSid
template configuration. Sandbox replies are subject to the 24-hour service window;
Sandbox membership expires after three days. See the current README for setup.
 
You are taking over a small Flask application in the `Twilio_POC` repository. Read this document and inspect the source files before making changes.
 
## User's current goal
 
Build and test a simple WhatsApp text-messaging service using a Twilio trial account. The current scope is WhatsApp messaging only. Do not add voice agents, voice calls, complaint-platform integration, or unrelated features unless the user explicitly requests them later.
 
## What this application is
 
This repository is a standalone Flask web app that sits between Twilio WhatsApp and the user's code. It is not the separate platform that may exist elsewhere in the user's organization.
 
Current flow:
 
```text
WhatsApp user
    -> Twilio WhatsApp
    -> public HTTPS webhook: POST /whatsapp
    -> Flask app
    -> Twilio Messages API sends a text reply back to WhatsApp
```
 
## Current files
 
- `app.py`: Flask application and Twilio integration.
- `test_app.py`: automated tests.
- `requirements.txt`: Flask, Twilio SDK, dotenv, pytest, and Gunicorn.
- `.env.example`: safe configuration template. Never place real credentials here.
- `.env`: local secrets/configuration. Never commit or expose it.
- `render.yaml`: optional Render deployment configuration.
- `README.md`: user-facing setup and deployment instructions.
 
## Current endpoints
 
### `GET /health`
 
Returns:
 
```json
{"status": "ok"}
```
 
### `POST /whatsapp`
 
This is the inbound Twilio WhatsApp webhook. It expects Twilio form fields:
 
- `From`: WhatsApp sender, for example `whatsapp:+919876543210`.
- `Body`: incoming text.
 
It validates the Twilio signature when `VALIDATE_TWILIO_REQUESTS=true`. It creates a reply using `build_reply()` and sends that reply using the Twilio Messages API. It returns JSON containing the outbound message SID.
 
The app intentionally sends the reply through the Twilio REST API instead of returning TwiML XML. This was chosen because the current official Twilio trial “Try out WhatsApp” documentation says the trial flow has restrictions and direct TwiML XML responses are not supported.
 
### `POST /send`
 
Manual outbound test endpoint. It expects JSON:
 
```json
{
  "to": "whatsapp:+919876543210",
  "body": "Hello from the Flask app"
}
```
 
It sends the message using the configured Twilio WhatsApp sender.
 
## Current message behavior
 
`build_reply()` currently responds as follows:
 
- `hi`, `hello`, `start`: greeting.
- `help`: `Commands: HI, HELP, and STATUS.`
- `status`: confirms the sender and receipt.
- Any other text: echoes `You said: ...`.
 
Keep this behavior simple unless the user asks for a specific conversation design.
 
## Environment variables
 
Required for real Twilio API calls:
 
```env
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_FROM=whatsapp:+...
```
 
Other settings:
 
```env
VALIDATE_TWILIO_REQUESTS=true
PORT=5000
```
 
Use `VALIDATE_TWILIO_REQUESTS=false` only for local webhook tests that do not contain a genuine Twilio signature. Keep it `true` on a public deployment.
 
`TWILIO_WHATSAPP_FROM` must match the WhatsApp-enabled number shown in the user's Twilio **Messaging → WhatsApp → Try out WhatsApp** flow. Do not assume the old Sandbox number is correct.
 
Never ask the user to paste their Auth Token into chat. Never print secrets in logs, source code, README files, commits, or test output.
 
## Twilio trial setup assumptions
 
The user has a Twilio free trial account and is using the current **Try out WhatsApp** flow:
 
1. Twilio Console → Messaging → WhatsApp → Try out WhatsApp.
2. Link the user's personal WhatsApp phone using the displayed QR code or join message.
3. Choose the inbound/custom auto-reply configuration.
4. Configure a public HTTPS webhook ending in `/whatsapp`.
 
Twilio cannot reach `127.0.0.1`. A local Flask server is only testable by curl/PowerShell unless a public tunnel or public host is used.
 
Trial restrictions may apply to verified recipients, templates, and outbound messages.
 
## Deployment status and options
 
The repository is prepared for Gunicorn and contains `render.yaml`, but the user currently cannot use Render immediately and may be considering Azure or another company-approved host.
 
The production start command is:
 
```text
gunicorn app:app
```
 
Any host used for Twilio must provide:
 
- a publicly reachable HTTPS URL;
- inbound access to `POST /whatsapp`;
- outbound HTTPS access to Twilio's API;
- secure environment-variable configuration;
- a process running the Gunicorn command.
 
An internal company VM without public ingress will not work directly because Twilio cannot reach it. Azure App Service is generally simpler than an Azure VM because it provides a public HTTPS hostname, but company subscription/network policies may apply.
 
PythonAnywhere free hosting may be unsuitable because its free outbound internet access is restricted and the Twilio SDK may not work through its proxy. Verify the host's outbound access before recommending it.
 
## Testing
 
Run from the repository root:
 
```powershell
py -m pytest -q
```
 
The current test suite covers:
 
- health endpoint;
- message reply construction;
- inbound webhook calling the Twilio reply function;
- missing inbound fields;
- missing outbound fields.
 
Do not make tests call the real Twilio API. Mock `reply_to_whatsapp()` or the Twilio client.
 
Local manual test with signature validation disabled:
 
```powershell
$env:VALIDATE_TWILIO_REQUESTS='false'
py app.py
```
 
In another terminal:
 
```powershell
curl.exe -X POST http://127.0.0.1:5000/whatsapp `
  -d "Body=HELP" `
  -d "From=whatsapp:+919999999999"
```
 
This local test requires valid Twilio credentials and a configured `TWILIO_WHATSAPP_FROM` if the webhook actually sends through Twilio. Unit tests do not require valid credentials because the send function is mocked.
 
## Explicitly removed scope
 
The previous version had an experimental separate-platform integration. It was intentionally removed at the user's request. Do not reintroduce:
 
- voice-agent API calls;
- agent-name lists;
- complaint forwarding;
- native WhatsApp voice-call handling;
- Twilio Voice webhooks;
- platform API keys or platform environment variables;
- TwiML voice behavior.
 
If the user later requests a feature in one of these areas, first confirm the desired architecture and update the scope deliberately.
 
## Recommended next task
 
Help the user deploy this messaging-only Flask app to a public HTTPS host approved by their organization. Do not modify the application behavior unless deployment testing reveals a concrete issue. After deployment, help configure the Twilio inbound webhook URL and verify a real WhatsApp message exchange.
