# Bug Fix - Hub Chat Error

## Issue
```
KeyError: 'cap' in hub_agent.py line 33
```

## Root Cause
The `calculate_daily_load()` method in `lbs_engine.py` was returning inconsistent dictionary structures:
- When tasks exist: includes `'cap'` key
- When NO tasks exist: missing `'cap'` key

This caused the Hub agent to crash when trying to format the status message on days with no scheduled tasks.

## Fix Applied
Added `"cap": cap` to the return dictionary in the empty tasks branch (line 165 of `lbs_engine.py`).

## Status
✅ Fixed. Restart the backend server to apply the fix:
```bash
# Stop current server (Ctrl+C)
# Restart
python app/backend/main.py
```

Then test the Hub chat again.
