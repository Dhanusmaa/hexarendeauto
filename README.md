# HexaRenderAuto

Telegram automation bot powered by Telethon and configured for Render.

## Deploy to Render

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/Dhanusmaa/hexarendeauto)

Click the button above to deploy this repository directly to Render.

## Required Environment Variables

Render will ask for these values during Blueprint setup:

| Variable | Required | Description |
|---|---|---|
| `API_ID` | Yes | Telegram API ID |
| `API_HASH` | Yes | Telegram API Hash |
| `TELEGRAM_SESSION` | Yes | Telethon StringSession |

### API_ID and API_HASH

Get your Telegram API credentials from:

https://my.telegram.org/

Create an application and copy the API ID and API Hash into the matching Render environment variables.

### TELEGRAM_SESSION

`TELEGRAM_SESSION` must contain a valid Telethon **StringSession** for the Telegram account that runs this automation.

Do not put the session string in `Hexa.py`, `render.yaml`, or commit it to GitHub.

## Manual Render Deployment

1. Open Render.
2. Choose **New → Blueprint**.
3. Select `Dhanusmaa/hexarendeauto`.
4. Select the `main` branch.
5. Render detects `render.yaml`.
6. Enter:
   - `API_ID`
   - `API_HASH`
   - `TELEGRAM_SESSION`
7. Deploy.

## Render Configuration

Render uses:

- Runtime: Python
- Build command: `pip install -r requirements.txt`
- Start command: `python Hexa.py`
- Health check: `/health`
- Branch: `main`

The application starts a small HTTP health server on Render's `PORT` so the web service can report its status.

## Project Structure

```text
hexarendeauto/
├── Hexa.py
├── requirements.txt
├── render.yaml
├── .gitignore
└── README.md
```

## Security

Never commit Telegram secrets to GitHub.

If an API hash or Telegram session has previously been exposed in a public repository, regenerate the affected credentials/session before deploying.

Keep all secret values in Render Environment Variables.

## Notes

This project uses Telethon and connects as the Telegram account represented by the supplied StringSession.
