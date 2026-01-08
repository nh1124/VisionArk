# VisionArk

> **⚠️ Experimental Personal OS**  
> This project is an experimental personal operating system.  
> Not production-ready. UX is optimized for the author.  
> Architecture may change without notice.

An AI-powered personal task management system built on a Hub-Spoke architecture. VisionArk combines LBS (Load Balancing System) workload management with multi-agent AI orchestration powered by Google Gemini.

---

## ✨ Core Features

### 🤖 AI Agent System
- **Hub Agent**: Central coordinator for strategic planning, cross-project oversight, and global task management
- **Spoke Agents**: Project-specific AI assistants with isolated contexts, custom prompts, and dedicated workspaces
- **Agent-to-Agent Communication**: Spokes can collaborate via `ask_spoke` tool with recursion depth limiting
- **Artifacts System**: Agents create and manage artifacts (documents, notes, plans) in their workspace

### 🧠 Agent Capabilities (Native Tools)
| Category | Tools |
|----------|-------|
| **Research** | `google_search`, `research_url`, `search_places` |
| **LBS/Tasks** | `create_task`, `list_tasks`, `complete_lbs_task`, `get_load_on_day` |
| **Knowledge** | `search_knowledge`, `ingest_knowledge` |
| **Files** | `save_artifact`, `read_artifact`, `list_files`, `upload_file_to_ai` |
| **Creation** | `generate_image`, `execute_code` |
| **Coordination** | `ask_spoke`, `request_coordination`, `check_inbox` |

### 📊 LBS (Load Balancing System)
- Cognitive load calculation with non-linear scaling
- Daily/weekly workload forecasting and heatmaps
- Task scheduling with multiple recurrence patterns (daily, weekly, monthly, interval)
- Per-task execution tracking and history

### 📁 Knowledge Core
- Semantic search and retrieval across agent memory
- Automatic ingestion of conversation context
- Per-agent scoped knowledge with global fallback

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                       Frontend (Next.js)                        │
│  Dashboard │ Hub Chat │ Spoke Chat │ Tasks │ Settings           │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────────────┐
│                       Backend (FastAPI)                         │
│  ┌────────┐  ┌────────────┐  ┌─────────────┐  ┌──────────────┐  │
│  │  Auth  │  │   Agents   │  │     LBS     │  │  Knowledge   │  │
│  │        │  │ Hub/Spokes │  │   Proxy     │  │    Core      │  │
│  └────────┘  └────────────┘  └─────────────┘  └──────────────┘  │
│                    │                 │                          │
│              ┌─────┴─────┐    ┌──────┴──────┐                   │
│              │  Gemini   │    │  External   │                   │
│              │   API     │    │ LBS Service │                   │
│              └───────────┘    └─────────────┘                   │
└─────────────────────────────────────────────────────────────────┘

Data Structure:
data/users/{user_id}/
├── hub_data/          # Hub agent's database, inbox, artifacts
├── spokes/{name}/     # Per-spoke files, artifacts, refs
└── global_assets/
```

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- Google Gemini API Key (AI Studio or Vertex AI)
- (Optional) External LBS microservice

### 1. Configure Environment
```bash
cp .env.example .env
# Edit .env and set:
#   GEMINI_API_KEY=your_api_key
#   ATMOS_ENV=dev
```

### 2. Start Services

**Windows (Recommended)**:
```bash
.\start_service.bat
```

**Or manually**:
```bash
# Backend
cd core/backend
pip install -r requirements.txt
python main.py

# Frontend (new terminal)
cd core/frontend
npm install
npm run dev
```

### 3. Access
- **UI**: http://localhost:3000
- **API Docs**: http://localhost:8000/docs

---

## 📡 API Overview

### Authentication
JWT-based session auth. Register and sign in via the frontend UI.
- Dev mode: Falls back to default user if no token provided
- Prod mode: Set `ATMOS_ENV=prod` and `ATMOS_REQUIRE_API_KEY=true`

### Key Endpoints

| Module | Endpoint | Description |
|--------|----------|-------------|
| **Agents** | `POST /api/agents/hub/chat` | Chat with Hub agent |
| | `POST /api/agents/spoke/{name}/chat` | Chat with a Spoke |
| | `POST /api/agents/spoke/create` | Create new Spoke |
| | `GET /api/agents/spoke` | List all Spokes |
| **LBS** | `GET /api/lbs/dashboard` | Workload overview |
| | `GET /api/lbs/tasks` | List tasks |
| | `POST /api/lbs/tasks` | Create task |
| | `POST /api/lbs/tasks/{id}/complete` | Mark task done |
| **Inbox** | `GET /api/inbox/pending` | Spoke→Hub messages |
| **Files** | `POST /api/files/upload` | Upload file |
| | `GET /api/agents/{node}/artifacts` | List agent artifacts |

---

## 🛠️ Technology Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 15, React 19, Tailwind CSS |
| Backend | FastAPI, SQLAlchemy (async), Pydantic |
| AI | Google Gemini (genai SDK), Native Function Calling |
| Database | SQLite (dev), PostgreSQL (prod) |
| Deployment | Docker & Docker Compose |

---

## 📁 Project Structure

```
VisionArk/
├── core/
│   ├── backend/           # FastAPI + AI agents
│   │   ├── agents/        # Hub, Spoke, Base agent classes
│   │   ├── api/           # REST endpoints
│   │   ├── services/      # LBS client, Knowledge Core, etc.
│   │   ├── tools/         # Agent tool implementations
│   │   └── llm/           # Gemini provider
│   └── frontend/          # Next.js application
│       ├── app/           # Pages (dashboard, hub, spokes, tasks)
│       └── components/    # UI components
├── data/                  # User data (gitignored)
├── docs/                  # Design docs, blueprints
├── infra/                 # Docker configs
└── start_service.bat      # Main entry point
```

---

## 📖 Documentation

- `docs/BLUEPRINT.md` - Full architectural specification
- `docs/Vision Ark System Design.md` - Detailed system design
- `docs/lbs_system_design.md` - LBS formula and logic
- `docs/quickstart.md` - Quick start guide

---

## ⚠️ Disclaimer

This is an experimental personal project:
- **Not production-ready** - May contain bugs and incomplete features
- **UX optimized for author** - Design choices reflect personal workflow
- **Architecture may change** - Breaking changes possible without deprecation

---

## 📄 License

This project is licensed under the [Apache License 2.0](LICENSE).

---

**Version**: 0.2.0 (Phase 2)
