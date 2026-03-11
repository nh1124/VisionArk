from datetime import datetime, timedelta
import json
from typing import List, Dict, Any
from va_sdk import task_registry, sync_registry

@sync_registry.register("google_calendar")
def register_google_calendar():
    """Register Google Calendar for synchronization."""
    pass
from .client import get_google_calendar_client
from integrations._internal_services import get_lbs_client

@task_registry.register("sync_google_calendar")
async def sync_google_calendar(task: Any, db_session: Any):
    """
    Sync Google Calendar events with LBS tasks.
    Triggered by the worker.
    """
    user_id = task.user_id
    config = task.payload or {}
    calendar_id = config.get("calendar_id", "primary")
    
    # 1. Get Clients
    gc_client = await get_google_calendar_client(user_id, db_session)
    lbs_client = await get_lbs_client(user_id, db_session)
    
    # 2. Fetch External Events (Last 7 days to next 30 days)
    now = datetime.utcnow()
    time_min = now - timedelta(days=7)
    time_max = now + timedelta(days=30)
    events = await gc_client.list_events(calendar_id, time_min=time_min, time_max=time_max)
    
    # 3. Create/Update LBS Tasks from Events
    for event in events:
        # Check if this is a VA task already (exported from us)
        # Assuming we use Extended Properties 'visionark_id'
        ext_props = event.get("extendedProperties", {}).get("private", {})
        if ext_props.get("visionark_id"):
            continue # Skip our own tasks
            
        start = event.get("start", {}).get("dateTime") or event.get("start", {}).get("date")
        end = event.get("end", {}).get("dateTime") or event.get("end", {}).get("date")
        summary = event.get("summary", "No Title")
        
        # Estimate load based on keywords (simple version)
        load = 1.0
        lower_summary = summary.lower()
        if any(kw in lower_summary for kw in ["meeting", "1on1", "sync", " interview"]):
            load = 3.0
        elif any(kw in lower_summary for kw in ["break", "lunch", "move", "travel"]):
            load = 0.5
            
        # Register as a "Fixed" task in LBS
        # We need a way to link Google Event ID to LBS Task ID
        # For simplicity, we create a task with a specific context 'External'
        lbs_task_data = {
            "task_name": f"[External] {summary}",
            "context": "External",
            "active": False, # It's a hard constraint
            "target_date": start[:10],
            "base_load_score": load,
            "external_id": event.get("id"),
            "metadata": {
                "source": "google_calendar",
                "event_id": event.get("id")
            }
        }
        
        # Check if already exists in LBS (this part needs LBS search capability or local mapping)
        # For now, let's assume we create it if not found in a local ExternalIdentity mapping.
        await lbs_client.create_task(lbs_task_data)

@task_registry.register("export_to_google_calendar")
async def export_to_google_calendar(task: Any, db_session: Any):
    """
    Export VA tasks to Google Calendar.
    """
    import traceback
    try:
        user_id = task.user_id
        lbs_client = await get_lbs_client(user_id, db_session)
        gc_client = await get_google_calendar_client(user_id, db_session)
        
        # Fetch tasks for the next 7 days from LBS
        now = datetime.utcnow().date()
        for i in range(7):
            target_date = (now + timedelta(days=i)).isoformat()
            tasks = await lbs_client.list_tasks(target_date=target_date)
            
            for va_task in tasks:
                # DEBUG
                print(f"[DEBUG] Google Export: Task keys found: {list(va_task.keys())}")
                
                # Only export active VA tasks (not external imports)
                if va_task.get("context") == "External":
                    continue
                    
                metadata = va_task.get("metadata") or {}
                va_intent = metadata.get("va_intent") or {}
                
                start_t = va_task.get('start_time') or '09:00:00'
                end_t = va_task.get('end_time') or '10:00:00'
                
                # Basic check for HH:MM format (need HH:MM:SS)
                if len(start_t) == 5: start_t += ":00"
                if len(end_t) == 5: end_t += ":00"

                # Prepare Google Event Data
                event_data = {
                    "summary": f"[VA] {va_task['task_name']}",
                    "description": (va_task.get("notes") or "") + f"\n\nCognitive Load: {va_task.get('load', 1.0)}",
                    "start": {"dateTime": f"{target_date}T{start_t}Z"},
                    "end": {"dateTime": f"{target_date}T{end_t}Z"},
                    "extendedProperties": {
                        "private": {
                            "visionark_id": va_task["task_id"],
                        }
                    }
                }
                
                print(f"[DEBUG] Exporting to Google: {json.dumps(event_data)}")

                # --- Handle Intent: Generate Meeting Link ---
                params = None
                if va_intent.get("generate_meeting_link"):
                    event_data["conferenceData"] = {
                        "createRequest": {
                            "requestId": f"va_{va_task['task_id']}",
                            "conferenceSolutionKey": {"type": "hangoutsMeet"}
                        }
                    }
                    params = {"conferenceDataVersion": 1}

                # --- Handle Intent: Auto Invite ---
                invites = va_intent.get("auto_invite")
                if invites:
                    event_data["attendees"] = [{"email": email} for email in invites]
                    # Send notifications (Google default)
                    if not params: params = {}
                    params["sendUpdates"] = "all"

                # Check if already exported (mapping check)
                # For now, simplistic creation:
                try:
                    created_event = await gc_client.create_event("primary", event_data, params=params)
                    
                    # If we generated a link, save it back to LBS metadata
                    meeting_link = (created_event.get("conferenceData", {})
                                   .get("entryPoints", [{}])[0].get("uri"))
                    
                    if meeting_link:
                        # Update LBS metadata to store the link
                        metadata["meeting_link"] = meeting_link
                        await lbs_client.update_task(va_task["task_id"], {"metadata": metadata})

                except Exception as inner_e:
                    import logging
                    logging.error(f"Failed to export task {va_task['task_id']} to Google: {inner_e}")
    except Exception as outer_e:
        print("!!! CRITICAL ERROR IN export_to_google_calendar handler !!!")
        traceback.print_exc()
        raise outer_e
