# Asset Management & Dynamic Discovery Proposal

This report addresses the questions regarding dynamic sound detection and the overall organization of assets in VisionArk.

## 1. Dynamic Detection of Notification Sounds

Currently, the list of available sounds is hardcoded in the frontend `SettingsPage`. To make this dynamic:

### Proposed Architecture:
1. **Backend Extension**: Add a new endpoint `GET /api/settings/available-sounds`.
   - **Logic**: Use `os.listdir()` to scan the sound directory.
   - **Filter**: Only include `.mp3`, `.wav`, etc.
   - **Mapping**: Clean the filenames (e.g., `timer_chime.mp3` -> `Timer Chime`) for the UI display.

2. **Frontend Sync**:
   - The `SettingsPage` calls this endpoint on mount.
   - The `<select>` options are generated dynamically from the API response.

### Benefits:
- **Zero-Code Updates**: Simply dropping a new file into the sounds folder makes it immediately selectable in the UI.
- **Consistency**: The backend becomes the "Source of Truth" for what assets are available.

---

## 2. Global Asset Organization Proposal

As the project grows, managing assets (sounds, prompts, schemas, images) across separate service directories becomes difficult to maintain.

### Current State Analysis:
- **Frontend Assets**: `core/frontend/public/sounds` (Mixed with static web assets).
- **Backend Assets**: `core/backend/assets/prompts` (Coupled with backend code).
- **User Data**: `core/backend/data` (Persistent storage).

### Recommended Structure: "The Unified Assets Directory"

I propose moving all non-code assets to a top-level `shared/` or `assets/` directory that is mounted into both Backend and Frontend containers.

```text
/VisionArk
  ├── assets/                <-- NEW: Unified Asset Home
  │   ├── static/            (Exposed to web)
  │   │   ├── sounds/        (Notification sounds, UI clicks)
  │   │   ├── icons/         (Custom agent icons)
  │   │   └── brand/         (Logos, etc.)
  │   ├── templates/         (Usage by backend)
  │   │   ├── prompts/       (LLM System Prompts)
  │   │   └── emails/        (Notification templates)
  │   └── schemas/           (JSON validation schemas)
  ├── core/
  │   ├── backend/
  │   └── frontend/
  └── infra/                 (Docker/Nginx configs to route /assets)
```

### Implementation Steps:
1. **Docker Integration**: Use a named volume or bind mount to map `project/assets` to `/app/assets` in both containers.
2. **Nginx Routing**: Configure the frontend or a dedicated Nginx container to serve `/assets/static` directly.
3. **Asset Service**: Create a simple utility class in the backend to resolve paths to these assets (e.g., `AssetManager.get_prompt("orchestration")`).

### Benefits:
- **Centralized Management**: No more searching through nested folders to find a prompt or a sound.
- **Improved Portability**: Easier to move assets to a CDN or Cloud Storage (S3/GCS) in the future by just changing the `AssetManager` implementation.
- **Decoupling**: Static assets no longer bloating the frontend build/vcs if they become large.

---

## Next Steps
This is a research report only. Please review these proposals. If approved, we can create an implementation plan for:
1. The dynamic sound listing API.
2. The reorganization of the directory structure.
