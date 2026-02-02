# Unified Asset Management

VisionArk implements a unified asset management system to centralize static files, templates, and schemas across all containers.

## 1. Directory Structure

Assets are located at the project root in the `assets/` directory. This directory is shared across the backend, worker, and frontend services via Docker volume mounts.

```
assets/
├── static/
│   └── sounds/        # Notification sound files (.mp3, .wav)
├── templates/
│   └── prompts/       # LLM prompt templates and components
└── schemas/           # JSON schemas for tool validation
```

## 2. Docker Integration

The `assets/` directory is mounted into containers at the following locations:

- **Backend & Worker**: `/app/assets`
- **Frontend**: `/app/public/assets` (accessible as `/assets/` via browser)

### `docker-compose.yml` Configuration

```yaml
services:
  backend:
    volumes:
      - ../assets:/app/assets
  
  frontend:
    volumes:
      - ../assets/static:/app/public/assets
```

## 3. Backend Path Utilities

The `core/backend/utils/paths.py` utility provides helper functions to resolve asset paths correctly in both local development and Docker environments.

- `get_default_assets_dir()`: Returns the base assets directory.
- `get_prompts_dir()`: Returns the directory for LLM prompt templates.
- `get_static_assets_dir()`: Returns the directory for static assets (sounds, etc.).

## 4. Dynamic Sound Discovery

The system supports dynamic discovery of notification sounds. Any audio file added to `assets/static/sounds/` is automatically detected and made available in the user settings UI.

- **API Endpoint**: `GET /api/settings/sounds`
- **Logic**: The backend scans the directory, extracts filenames (stems), and returns them with human-readable labels.

## 5. Usage in Frontend

Static assets are served via the `/assets/` path. For example, a sound file `timer.mp3` located at `assets/static/sounds/timer.mp3` is accessible in the frontend at:
`http://localhost:3000/assets/sounds/timer.mp3`

---
*Last Updated: 2026-02-02*
