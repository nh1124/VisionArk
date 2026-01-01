# VisionArk

A sophisticated Hub-Spoke architecture task management system with LBS (Load Balancing System) and AI-powered orchestration. VisionArk provides a centralized management layer for complex task environments, utilizing AI to optimize workflows and cognitive load.

## 🏗️ Architecture

- **Hub**: Central PM agent managing LBS, resources, and cross-project coordination.
- **Spokes**: Project-specific execution agents (Research, Development, Life Admin, etc.).
- **LBS Engine**: Advanced cognitive load calculation, task expansion, and capacity management.
- **Inbox System**: Asynchronous message buffer for Spoke→Hub strategic communication.
- **User-Scoped Storage**: Multi-user support with isolated data directories and security.

## 🚀 Quick Start

### Docker (Recommended)

1. **Configure Environment**:
   ```bash
   cp .env.example .env
   # Edit .env and add your GEMINI_API_KEY
   ```

2. **Initialize and Start Services**:
   ```bash
   # On Windows
   .\start_service.bat
   
   # Or using Docker Compose directly
   docker-compose -f infra/docker-compose.yml up
   ```

3. **Access the Application**:
   - Frontend UI: [http://localhost:3000](http://localhost:3000)
   - Backend API: [http://localhost:8000](http://localhost:8000)
   - API Docs: [http://localhost:8000/docs](http://localhost:8000/docs)

## 🔐 Authentication & Identity

VisionArk uses JWT-based session authentication. Users can register and sign in through the frontend UI.

- **Developer Mode**: In `dev` mode, the system can fall back to a default user if no token is provided.
- **Production Mode**: Set `ATMOS_ENV=prod` and `ATMOS_REQUIRE_API_KEY=true` in `.env`.
- **API Access**: Use the `X-API-KEY` header for external service integrations.

## 📡 Core API Modules

### LBS (Load Balancing System)
- `GET /api/lbs/dashboard`: Daily and weekly workload metrics.
- `GET /api/lbs/tasks`: Comprehensive task management.
- `POST /api/lbs/calculate`: On-demand load calculation.

### Agents (AI Orchestration)
- `POST /api/agents/hub/chat`: Strategic coordination with the Hub agent.
- `POST /api/agents/spoke/{name}/chat`: Direct project execution with Spoke agents.
- `POST /api/agents/spoke/create`: Dynamic Spoke provisioning.

### Inbox (Push Protocol)
- `GET /api/inbox/pending`: Retrieve unprocessed meta-actions from Spokes.
- `POST /api/inbox/process`: Hub-directed triage and action acceptance.

## 🗄️ System Internals

### LBS Formula
VisionArk calculates cognitive load using a non-linear model:
```
Adjusted Load = Base + ALPHA × N^BETA + SWITCH_COST × max(U-1, 0)
```
- **Base**: Sum of individual task weights.
- **N**: Total task count.
- **U**: Number of unique contexts (Spokes).

### Directory Structure
```
VisionArk/
├── core/
│   ├── backend/           # FastAPI application & AI logic
│   └── frontend/          # Next.js web interface
├── data/
│   └── users/             # User-scoped data (isolated)
│       └── {user_id}/
│           ├── hub_data/  # User's databases & inbox
│           ├── spokes/    # User's project workspaces
│           └── global_assets/
├── infra/                 # Docker & deployment configs
└── start_service.bat      # Main entry point
```

## 🛠️ Technology Stack

- **Frontend**: Next.js, React, Tailwind CSS
- **Backend**: FastAPI, SQLAlchemy, Pydantic
- **AI**: Google Gemini (Vertex AI / AI Studio)
- **Database**: PostgreSQL (Production), SQLite (Dev/Local)
- **Containerization**: Docker & Docker Compose

## 🧪 Development

### Local Environment Setup
```bash
cd core/backend
pip install -r requirements.txt
python main.py
```

Check **BLUEPRINT.md** in the `docs` directory for the full architectural specification.

---
**Built with precision for Advanced Agentic Coding.**
