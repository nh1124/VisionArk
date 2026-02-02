# Integration Hub: UI & Configuration

The **Integration Hub** (Settings > Integrations) is driven by a `manifest.json` file located in each integration's folder.

## 1. The `manifest.json` Schema

The manifest provides metadata for the UI and defines which configuration fields are needed.

### Example
```json
{
  "id": "my_system",
  "name": "My System",
  "description": "Short description shown in the gallery.",
  "icon": "🔗",
  "category": "productivity",
  "authType": "api_key",
  "config_fields": [
    { 
      "key": "__api_key__", 
      "label": "API Secret", 
      "type": "password", 
      "description": "Your API key from the service provider." 
    },
    { 
      "key": "base_url", 
      "label": "API Endpoint", 
      "type": "text", 
      "default": "https://api.example.com" 
    }
  ],
  "setup_instructions": [
    { "step": 1, "title": "Create an App", "content": "Log in to the portal..." }
  ]
}
```

## 2. Special Configuration Keys

The system provides special mapping for some keys:
- **`__api_key__`**: Maps to `ServiceRegistry.api_key_encrypted`. This value is automatically encrypted by the backend.
- **`base_url`**: Maps to `ServiceRegistry.base_url`.

All other keys in `config_fields` are stored in the `ServiceRegistry.config` JSON field.

## 3. Setup Instructions

If the `setup_instructions` field is present, the Hub will render a dedicated **Setup Guide** within the configuration modal, reducing the need for external documentation.

---
> [!TIP]
> Use emojis or standard icons for the `icon` field to make your integration stand out in the Integration Hub gallery.
