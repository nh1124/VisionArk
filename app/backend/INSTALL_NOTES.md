# Installation Notes

## Dependency Updates for MVP

The MVP backend has been simplified to use only essential dependencies:

### Removed (not needed for MVP):
- `langchain` - Not used in MVP (basic Gemini API calls only)
- `langchain-google-genai` - Direct google-generativeai used instead
- `langgraph` - Reserved for future phases
- `chromadb` - RAG integration planned for Phase 2
- `pypdf` - RAG integration planned for Phase 2

### Core Dependencies:
- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `sqlalchemy` - Database ORM
- `pydantic` - Data validation
- `pydantic-settings` - Config management (updated to >=2.3.0)
- `google-generativeai` - Gemini AI
- `numpy` + `pandas` - LBS calculations
- `python-dotenv` - Environment variables

## Installation

```bash
cd app/backend
pip install -r requirements.txt
```

## Running the Server

```bash
python main.py
```

Or with uvicorn directly:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Troubleshooting

### Dependency Conflicts
If you still see conflicts, create a clean virtual environment:

```bash
# Windows
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### Port Already in Use
If port 8000 is busy:
```bash
# Change port in main.py or use:
uvicorn main:app --port 8001
```
