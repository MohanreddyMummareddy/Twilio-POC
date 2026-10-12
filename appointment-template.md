# Appointment template draft

Name: `twilio_poc_by_mohan_appointment`
Language: English
Category: Utility (subject to provider review)

Message:

> Hello! This is Twilio_POC by Mohan. Your appointment is scheduled for {{1}} at {{2}}. Please reply to confirm or request a different time.

Example variables: `{"1":"21 July 2027","2":"3 PM"}`

This is a draft, not an approved or registered WhatsApp template. The supplied
Sandbox SID `HXb5b62575e6e4ff6129ad7c8efe1f983e` refers to Twilio's existing
appointment template; it will not send the branded message above. Trial accounts
may only use the provided templates. A branded template needs a supported account,
creation in Content Template Builder, and any required WhatsApp approval.

For the existing Sandbox template, set these in Render Environment:

```env
TWILIO_CONTENT_SID=HXb5b62575e6e4ff6129ad7c8efe1f983e
TWILIO_CONTENT_VARIABLES={"1":"12/1","2":"3pm"}
```

Save and redeploy. Incoming text then triggers this fixed template. It does not
send the custom HELLO/HELP reply. Leave `TWILIO_CONTENT_SID` blank to use plain text
on accounts that support it. The `/send` endpoint also uses the configured template
when template mode is enabled, instead of its supplied `body`.
