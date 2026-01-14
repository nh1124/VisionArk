# VisionArk Project Summary

> **Purpose**: This document provides a quick reference for AI agents to understand the VisionArk project structure and implementation.

---

## 🎯 Overview

**VisionArk** is an **Exocortex** (externalized cognitive system) that manages:
- **State** - Current status of projects and tasks
- **Facts** - Knowledge and context
- **Episodes** - Activity logs
- **Load Balancing (LBS)** - Task scheduling and cognitive load management

The system implements a **Hub-Spoke model** where:
- **Hub Agent (PM)** - Central orchestrator for resource allocation and cross-project coordination
- **Spoke Agents** - Autonomous project-specific executors

---

## 📁 Root Directory Structure

```
VisionArk/
├── .env                    # Environment variables (API keys, DB connection)
├── .env.example            # Template for environment setup
├── LICENSE                 # Project license
├── README.md               # Getting started guide
├── start_service.bat       # Windows startup script
├── start_service.sh        # Linux startup script
│
├── core/                   # [MAIN APPLICATION]
│   ├── backend/            # Python FastAPI backend
│   └── frontend/           # Next.js (TypeScript) frontend
│
├── data/                   # [PERSISTENT STORAGE]
│   └── users/{user_id}/    # Per-user file storage
│       └── {node_name}/    # Per-node (Hub/Spoke) files
│
├── docs/                   # [DOCUMENTATION]
│   ├── Vision Ark System Design.md  # Complete system design document
│   ├── BLUEPRINT.md        # Detailed implementation blueprint
│   ├── lbs_system_design.md # Load Balancing System specification
│   └── quickstart.md       # Quick start guide
│
├── infra/                  # [INFRASTRUCTURE]
│   ├── docker-compose.yml  # Container orchestration
│   └── env_samples/        # Sample environment configurations
│
└── tests/                  # [TESTING]
    └── (test files)
```

---

## 🔧 Backend (`core/backend/`)

**Stack**: Python, FastAPI, SQLite (visionark.db), LangGraph

```
backend/
├── main.py                 # FastAPI entry point
├── config.py               # Settings (Pydantic BaseSettings)
├── visionark.db            # SQLite database
│
├── agents/                 # [AGENT LOGIC]
│   └── (Hub/Spoke agent implementations)
│
├── api/                    # [REST ENDPOINTS]
│   └── (Route definitions: auth, nodes, chat, files, lbs proxy)
│
├── llm/                    # [LLM INTEGRATION]
│   └── gemini_provider.py  # Gemini API wrapper
│
├── models/                 # [DB SCHEMAS]
│   └── (SQLAlchemy models: Users, Nodes, ChatSessions, Files)
│
├── services/               # [BUSINESS LOGIC]
│   └── (LBS client, RAG logic, external service integrations)
│
├── tools/                  # [AGENT TOOLS]
│   └── agent_tools.py      # Function calling tools for agents
│
└── utils/                  # [UTILITIES]
    └── (Encryption, helpers)
```

### Key API Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /auth/login` | User authentication (JWT) |
| `GET/POST /nodes` | Node (Hub/Spoke) management |
| `POST /chat/{node}` | Chat with agent (streaming) |
| `GET/POST /files` | File management |
| `/lbs/*` | Proxy to LBS microservice |
| `/commands/execute` | Server-side command execution |

---

## 🎨 Frontend (`core/frontend/`)

**Stack**: Next.js (App Router), TypeScript, TailwindCSS

```
frontend/
├── app/                    # [PAGES - App Router]
│   ├── page.tsx            # Home / Hub chat
│   ├── dashboard/          # LBS Dashboard
│   ├── hub/                # Hub agent interface
│   ├── spoke/[spokeName]/  # Dynamic Spoke pages
│   ├── inbox/              # Approval queue
│   └── api/                # API routes (proxies to backend)
│
├── components/             # [UI COMPONENTS]
│   ├── ChatInterface.tsx   # Main chat component
│   ├── MarkdownRenderer.tsx # Rich markdown display
│   ├── FilesSidebar.tsx    # File management UI
│   ├── HeatMapCalendar.tsx # LBS visualization
│   └── MobileSidebar.tsx   # Mobile navigation
│
├── lib/                    # [UTILITIES]
│   └── api.ts              # API client functions
│
└── hooks/                  # [REACT HOOKS]
    └── (Custom hooks)
```

---

## 🗄️ Database Schema (Core Tables)

| Table | Purpose |
|-------|---------|
| `USERS` | User accounts (login, password hash) |
| `NODES` | Hub/Spoke definitions (name, type, permissions) |
| `AGENT_PROFILES` | Agent configurations (system prompts) |
| `CHAT_SESSIONS` | Conversation sessions |
| `CHAT_MESSAGES` | Individual messages |
| `UPLOADED_FILES` | File metadata (with Gemini sync status) |
| `INBOX_QUEUE` | Async message buffer (Spoke → Hub) |
| `USER_SETTINGS` | User preferences (AI config, themes) |
| `SERVICE_REGISTRY` | External service connections (LBS, KC) |

---

## 🔑 Key Design Principles

1. **Explicit Control** - User approval required for important state changes
2. **Decentralized Execution** - Each Spoke operates as an independent context
3. **State over Memory** - SSOT via LBS/Knowledge Core, not chat history
4. **Replaceability** - Modular components (LLM, RAG, external services)

---

## 🚀 Startup Commands

**Windows**:
```batch
.\start_service.bat
```

**Linux/Docker**:
```bash
docker-compose -f infra/docker-compose.yml up --build
```

**Development (Individual)**:
```bash
# Backend
cd core/backend && python main.py

# Frontend
cd core/frontend && npm run dev
```

---

## 📡 External Services

| Service | Purpose | API |
|---------|---------|-----|
| **LBS Microservice** | Task scheduling, load calculation | REST API |
| **Knowledge Core (KC)** | Long-term user context (Facts/States) | REST API |
| **Gemini API** | LLM provider | Google AI SDK |
| **Microsoft Graph** | ToDo/Calendar sync (optional) | OAuth 2.0 |

---

## ⚡ Slash Commands

**Client-Side (Frontend)**:
- `/switch <node>` - Navigate to node
- `/hub` - Go to Hub
- `/inbox` - Open inbox
- `/clear` - Clear chat display

**Server-Side**:
- `/archive` - Rotate chat session
- `/task <title>` - Quick add task (Hub only)
- `/report [text]` - Send report to Hub (Spoke only)

---

*Generated for AI reference - See `docs/Vision Ark System Design.md` for complete specifications.*
