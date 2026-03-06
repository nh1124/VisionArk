# Google Calendar Integration

This integration enables two-way sync between VisionArk (LBS) and Google Calendar.
It is designed so external calendar events can be treated as scheduling constraints in LBS.

## Shared App Model

This integration uses a shared app model.
A system administrator creates one Google Cloud app, and users authorize their own calendars through that app.

## Setup

### 1. Google Cloud Console

1. Create or select a project in [Google Cloud Console](https://console.cloud.google.com/).
2. Enable **Google Calendar API**.
3. Configure the OAuth consent screen.
4. Create an **OAuth 2.0 Client ID** (Web application).
5. Add redirect URI:
   - `http://localhost:8000/api/google-calendar/callback`

### 2. Environment Variables

Add these to `.env.core` (or `.env.local`):

```env
GOOGLE_CLIENT_ID=your_client_id_here
GOOGLE_CLIENT_SECRET=your_client_secret_here
GOOGLE_REDIRECT_URI=http://localhost:8000/api/google-calendar/callback
```

## Features

- OAuth2 authorization flow
- Import Google events into LBS task candidates
- Export VisionArk tasks/events to Google Calendar
- Agent tools for calendar read/write operations

## Developer Notes

- API routes: `core/backend/integrations/google_calendar/api.py`
- Sync logic: `core/backend/integrations/google_calendar/handlers.py`
- Client: `core/backend/integrations/google_calendar/client.py`
