# Bug Fix - Gemini Model Not Found

## Issue
```
google.api_core.exceptions.NotFound: 404 models/gemini-pro is not found for API version v1beta
```

## Root Cause
The model name `gemini-pro` has been deprecated by Google. The Gemini API has been updated and now uses different model names:
- `gemini-1.5-flash` (fast, efficient)
- `gemini-1.5-pro` (advanced reasoning)
- `gemini-2.0-flash-exp` (experimental)

## Fix Applied
Updated `base_agent.py` line 46:
```python
# Old (deprecated)
self.model = genai.GenerativeModel("gemini-pro")

# New (current)
self.model = genai.GenerativeModel("gemini-1.5-flash")
```

## Why gemini-1.5-flash?
- ✅ Fast response time (good for chat)
- ✅ Cost-effective
- ✅ Sufficient for MVP task management conversations
- ✅ Currently supported by Google

## Status
✅ Fixed. **Restart the backend server** to apply:
```bash
# Press Ctrl+C in backend terminal
# Then restart:
cd app\backend
python main.py
```

Or use: `.\start_server.bat`

## Alternative Models
If you need more advanced reasoning, you can change to:
```python
self.model = genai.GenerativeModel("gemini-1.5-pro")  # More capable but slower
```

---

**After restart**, the Hub chat should work without errors!
