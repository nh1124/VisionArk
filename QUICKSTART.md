# AI TaskManagement OS - Quick Start Guide

## 🚀 Start the Backend Server

### Option 1: Using the Batch Script (Windows)

Simply double-click `start_server.bat` or run:
```bash
start_server.bat
```

### Option 2: Manual Start

```bash
cd app/backend
pip install -r requirements.txt
python main.py
```

The server will start at **http://localhost:8000**

## 📚 Access API Documentation

Once the server is running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## ✅ Quick Health Check

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{"status": "healthy"}
```

## 🎯 Try It Out

### 1. Get Dashboard Data

```bash
curl http://localhost:8000/api/lbs/dashboard
```

### 2. Create Your First Task

```bash
curl -X POST http://localhost:8000/api/lbs/tasks \
  -H "Content-Type: application/json" \
  -d "{\"task_name\":\"Daily Exercise\",\"context\":\"health\",\"base_load_score\":1.5,\"rule_type\":\"WEEKLY\",\"mon\":true,\"wed\":true,\"fri\":true}"
```

### 3. Chat with Hub Agent

```bash
curl -X POST http://localhost:8000/api/agents/hub/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"What's my current workload?\"}"
```

### 4. Create a New Project (Spoke)

```bash
curl -X POST http://localhost:8000/api/agents/spoke/create \
  -H "Content-Type: application/json" \
  -d "{\"spoke_name\":\"my_project\"}"
```

## 📖 Full Documentation

See `README.md` for comprehensive API documentation and examples.

## 🐛 Troubleshooting

### Server won't start
- Check that port 8000 is not already in use
- Verify `GEMINI_API_KEY` is set in `.env` file
- Run `python test_simple.py` in `app/backend` for basic checks

### Database errors
- Delete `hub_data/lbs_master.db` and restart to regenerate

### Import errors
- Make sure you're in the `app/backend` directory when running scripts
- Reinstall dependencies: `pip install -r requirements.txt`

---

**Need help?** Check the walkthrough document for detailed implementation details.
