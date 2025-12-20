# AI TaskManagement OS - MVP Backend

A Hub-Spoke architecture task management system with LBS (Load Balancing System) and AI-powered orchestration.

## 🏗️ Architecture

- **Hub**: Central PM agent managing LBS and cross-project coordination
- **Spokes**: Project-specific execution agents (research, finance, life admin, etc.)
- **LBS Engine**: Cognitive load calculation and task expansion
- **Inbox System**: Async message buffer for Spoke→Hub communication

## 🚀 Quick Start

### 1. Install Dependencies

```bash
cd app/backend
pip install -r requirements.txt
```

### 2. Set Environment Variables

The `.env` file should already contain:
```
GEMINI_API_KEY=your_gemini_api_key
```

### 3. Run Demo Script

Test the backend with sample data and AI agents:

```bash
cd app/backend
python demo.py
```

This will:
- Initialize the database with LBS configuration
- Create sample tasks (research, finance, thesis)
- Expand tasks and calculate load scores
- Test Hub and Spoke AI agents

### 4. Start API Server

```bash
cd app/backend
python main.py
```

Or with uvicorn:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Visit **http://localhost:8000/docs** for interactive API documentation.

## 🔐 Authentication

All API endpoints require authentication via API Key (in dev mode, a fallback is provided).

### Create an API Key

```bash
cd app/backend
python create_api_key.py create --user-id 00000000-0000-0000-0000-000000000001 --client-id my-client --name "My API Key"
```

**Save the generated key** - it's only shown once!

### Using the API Key

Include the `X-API-KEY` header in all requests:

```bash
curl -H "X-API-KEY: atmos_your_key_here" http://localhost:8200/api/lbs/tasks
```

### Dev Mode (Default)

- `ATMOS_REQUIRE_API_KEY=false` - API key optional, falls back to default user
- Warnings are logged when fallback is used

### Production Mode

Set in `.env`:
```
ATMOS_ENV=prod
ATMOS_REQUIRE_API_KEY=true
ATMOS_API_KEY_PEPPER=your-secure-random-secret
```

### Key Management

```bash
# List all keys
python create_api_key.py list

# Revoke a key
python create_api_key.py revoke <key-id>
```

### Frontend Auth UI

The web UI includes built-in authentication:

- **Sign In** (`/auth/signin`) - Enter your API key
- **Sign Up** (`/auth/signup`) - Create account and get new API key
- **Sign Out** - Button in top-right corner

On first visit, you'll be redirected to sign in. Create an account to get your API key.

## 📡 API Endpoints

### LBS (Load Balancing System)
- `GET /api/lbs/dashboard` - Dashboard data (today, weekly stats)
- `POST /api/lbs/tasks` - Create new task
- `PUT /api/lbs/tasks/{task_id}` - Update task
- `GET /api/lbs/tasks` - List all tasks
- `POST /api/lbs/exceptions` - Add task exception (SKIP/OVERRIDE)
- `GET /api/lbs/calculate/{date}` - Calculate load for specific date
- `POST /api/lbs/expand` - Manually trigger task expansion

### Inbox (Push Protocol)
- `GET /api/inbox/pending` - Fetch unprocessed messages
- `POST /api/inbox/push` - Push meta-action from Spoke
- `POST /api/inbox/process` - Process message (accept/reject/edit)
- `GET /api/inbox/count` - Get unread count

### Agents (AI Chat)
- `POST /api/agents/hub/chat` - Chat with Hub agent
- `POST /api/agents/spoke/{spoke_name}/chat` - Chat with Spoke agent
- `POST /api/agents/spoke/create` - Create new Spoke
- `GET /api/agents/spoke/list` - List all Spokes
- `DELETE /api/agents/spoke/{spoke_name}` - Archive Spoke

## 🗄️ Database Schema

### Tasks Table
- Complex recurrence rules: ONCE, WEEKLY, EVERY_N_DAYS, MONTHLY_DAY, MONTHLY_NTH_WEEKDAY
- Load scores (0.0-10.0)
- Context/Spoke tagging

### LBS Daily Cache
- Materialized view of expanded tasks
- Pre-calculated load scores
- Overflow flags (CAP exceeded)

### Inbox Queue
- Async message buffer
- XML-parsed meta-actions
- Processing status tracking

### System Config
- ALPHA: Urgency multiplier (default: 0.1)
- BETA: Task count penalty exponent (default: 1.2)
- CAP: Daily capacity limit (default: 8.0)
- SWITCH_COST: Context switching penalty (default: 0.5)

## 🧮 LBS Formula

```
Adjusted Load = Base + ALPHA × N^BETA + SWITCH_COST × max(U-1, 0)
```

Where:
- **Base**: Sum of task load scores
- **N**: Number of tasks
- **U**: Number of unique contexts (Spokes)
- **ALPHA, BETA, CAP, SWITCH_COST**: System config parameters

### Warning Levels
- 🟢 **SAFE**: < 6.0
- 🟡 **WARNING**: 6.0 - 8.0
- 🔴 **DANGER**: 8.0 - CAP
- 🟣 **CRITICAL**: > CAP

## 🤖 AI Agents

### Hub Agent
- PM role with strategic decision-making
- LBS-aware (auto-injects current load status)
- Inbox processing and triage
- Resource allocation recommendations

### Spoke Agent
- Project-specific execution
- Generates `<meta-action>` XML for Hub communication
- Artifact management
- Local refs integration (future: RAG)

### Example: Create a Spoke

```bash
curl -X POST http://localhost:8000/api/agents/spoke/create \
  -H "Content-Type: application/json" \
  -d '{
    "spoke_name": "thesis_writing",
    "custom_prompt": "You are an academic writing assistant for IMLEX master thesis."
  }'
```

### Example: Chat with Hub

```bash
curl -X POST http://localhost:8000/api/agents/hub/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is my workload status this week?"}'
```

## 📁 Directory Structure

```
AI_TaskManagement_OS/
├── global_assets/           # Layer 1: Global prompts & glossary
├── hub_data/               # Layer 2: Database & inbox
│   ├── lbs_master.db      # SQLite database
│   └── inbox/             # Message buffer
├── spokes/                 # Layer 3: Project workspaces
│   └── {spoke_name}/
│       ├── system_prompt.md
│       ├── artifacts/     # Generated outputs
│       └── refs/          # Reference materials
└── app/backend/           # Application code
    ├── models/            # Database models
    ├── services/          # LBS engine, inbox handler
    ├── agents/            # Hub & Spoke AI agents
    └── api/               # FastAPI routes
```

## 🧪 Testing

### Manual API Tests

1. **Create a task:**
```bash
curl -X POST http://localhost:8000/api/lbs/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "task_name": "Daily Exercise",
    "context": "health",
    "base_load_score": 1.0,
    "rule_type": "WEEKLY",
    "mon": true, "wed": true, "fri": true
  }'
```

2. **Get dashboard:**
```bash
curl http://localhost:8000/api/lbs/dashboard
```

3. **Calculate load for today:**
```bash
curl http://localhost:8000/api/lbs/calculate/$(date +%Y-%m-%d)
```

## 🔮 Next Steps (Future Phases)

- [ ] Frontend with Next.js (Dashboard, Inbox UI, Chat)
- [ ] RAG integration for refs/ directories (pgvector)
- [ ] Microsoft ToDo & Calendar sync
- [ ] Context rotation and log archiving
- [ ] Advanced visualization (heat maps, trend charts)

## 🐛 Troubleshooting

### Database locked error
- Stop any running instances of the app
- Delete `hub_data/lbs_master.db` and rerun `demo.py`

### Gemini API error
- Check that `GEMINI_API_KEY` is correctly set in `.env`
- Verify API quota and billing status

### Import errors
- Ensure you're in the `app/backend` directory
- Install all requirements: `pip install -r requirements.txt`

## 📚 Documentation

- **BLUEPRINT.md**: Full system specification
- API Docs: http://localhost:8000/docs (when server running)
- Global System Prompt: `global_assets/system_prompt_global.md`
- Glossary: `global_assets/glossary.json`

---

**Built with:** FastAPI • SQLAlchemy • Google Gemini • Python 3.10+
