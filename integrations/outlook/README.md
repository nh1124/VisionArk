# Outlook Calendar (Microsoft Graph) Integration

This integration enables two-way sync between VisionArk (LBS) and Microsoft Outlook Calendar.

## Shared App Model

This integration uses a shared app model.
A system administrator creates one Azure app registration, and users connect their own Outlook calendars through that app.

## Setup

### 1. Azure Portal / Entra ID

1. Create an app registration in [Azure Portal](https://portal.azure.com/).
2. Configure redirect URI:
   - `http://localhost:8000/api/outlook/callback`
3. Create a client secret.
4. Add Microsoft Graph delegated permissions:
   - `Calendars.ReadWrite`
   - `offline_access`

### 2. Environment Variables

Add these to `.env.core` (or `.env.local`):

```env
OUTLOOK_CLIENT_ID=your_client_id_here
OUTLOOK_CLIENT_SECRET=your_client_secret_here
OUTLOOK_REDIRECT_URI=http://localhost:8000/api/outlook/callback
```

## Features

- OAuth2 + Microsoft Graph integration
- Import Outlook events into VisionArk scheduling context
- Export VisionArk tasks/events to Outlook Calendar
- Agent tools for Outlook calendar operations

## Developer Notes

- API routes: `core/backend/integrations/outlook/api.py`
- Sync logic: `core/backend/integrations/outlook/handlers.py`
- Client: `core/backend/integrations/outlook/client.py`
