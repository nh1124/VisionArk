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
   `https://<your-visionark-domain>/api/line/webhook`
   *(This is the universal webhook for the Shared App model).*
3. Enable **Use webhook**.
4. (Optional) Disable "Auto-reply messages" and "Greeting messages" in the LINE Official Account Manager settings to let VisionArk handle all interactions.

## Multi-User Support (Sharing a Bot)

VisionArk supports sharing a single LINE bot among multiple users. When an unknown user messages the bot, they receive a "Linking Invitation".

### Account Linking Flow
1. **Invite**: The bot detects a new user and sends an invitation link valid for 15 minutes.
2. **Link**: The user clicks the link, which directs them to `https://<domain>/integrations/line/link?token=...`.
3. **Confirm**: The user logs into VisionArk (if not already) and confirms the link.
4. **Active**: Once linked, messages from that user are routed to their personal VisionArk projects.

## Features

- **Multi-User Support**: Multiple VisionArk users can link their accounts to a single shared LINE bot.
- **Dedicated Projects**: For every unique LINE user, a dedicated VisionArk project is automatically created (e.g., `LINE: User Name`).
- **Identity Mapping**: Uses `ExternalIdentity` to bridge LINE user IDs with VisionArk users.
- **Core Isolation**: The linking mechanism is built into the integration layer using `ServiceRegistry.config`, ensuring the core VisionArk architecture remains untouched.

## Developer Notes

- Webhook implementation: `core/backend/integrations/line/api.py`
- Account Linking Page: `core/frontend/app/integrations/line/link/page.tsx`
- Outgoing message handlers: `core/backend/integrations/line/handlers.py`
- SDK Registries used: `task_registry` (for `line_reply`), `reply_registry` (for real-time responses).
