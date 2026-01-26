# LINE Messaging API Integration

This integration allows VisionArk to communicate with users via LINE. It supports incoming messages (webhooks), automated replies, and dedicated project isolation per LINE user.

## Configuration

To enable the LINE integration, add an entry to the `service_registry` table for the user:

- **Service Name**: `line`
- **API Key**: Channel Access Token (Long-lived)
- **Config (JSON)**:
  ```json
  {
    "channel_secret": "YOUR_CHANNEL_SECRET"
  }
  ```

## Webhook Setup

1. In the [LINE Developers Console](https://developers.line.biz/), go to your Messaging API channel settings.
2. Set the **Webhook URL** to:
   `https://<your-visionark-domain>/api/line/<user_id>/webhook`
   *(Replace `<user_id>` with the UUID of the VisionArk user who owns the bot).*
3. Enable **Use webhook**.
4. (Optional) Disable "Auto-reply messages" and "Greeting messages" in the LINE Official Account Manager settings to let VisionArk handle all interactions.

## Features

- **Dedicated Projects**: For every unique LINE user that messages the bot, a dedicated VisionArk project is automatically created (e.g., `LINE: User Name`).
- **Identity Mapping**: LINE user IDs are mapped to VisionArk `ExternalIdentity` records, ensuring conversation continuity.
- **Rich AI Interactions**: Uses the core `ProjectNode` architecture to provide the same AI capabilities available in the web interface.

## Developer Notes

- Webhook implementation: `core/backend/integrations/line/api.py`
- Outgoing message handlers: `core/backend/integrations/line/handlers.py`
- SDK Registries used: `task_registry` (for `line_reply`), `reply_registry` (for real-time responses).
