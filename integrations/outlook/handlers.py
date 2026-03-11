from datetime import datetime, timedelta
from typing import List, Dict, Any
from va_sdk import task_registry, sync_registry

@sync_registry.register("outlook")
def register_outlook():
    """Register Outlook for synchronization."""
    pass
from .client import get_outlook_client
from integrations._internal_services import get_lbs_client

@task_registry.register("sync_outlook")
async def sync_outlook(task: Any, db_session: Any):
    user_id = task.user_id
    ol_client = await get_outlook_client(user_id, db_session)
    lbs_client = await get_lbs_client(user_id, db_session)
    
    now = datetime.utcnow()
    time_min = now - timedelta(days=7)
    time_max = now + timedelta(days=30)
    events = await ol_client.list_events(time_min=time_min, time_max=time_max)
    
    for event in events:
        # Avoid sync loops (simple check for [VA] in title)
        subject = event.get("subject", "No Title")
        if subject.startswith("[VA]"):
            continue
            
        start = event.get("start", {}).get("dateTime")
        
        lbs_task_data = {
            "task_name": f"[Outlook] {subject}",
            "context": "External",
            "active": False,
            "target_date": start[:10] if start else None,
            "base_load_score": 1.0, 
            "metadata": {"source": "outlook", "event_id": event.get("id")}
        }
        await lbs_client.create_task(lbs_task_data)

@task_registry.register("export_to_outlook")
async def export_to_outlook(task: Any, db_session: Any):
    """
    Export VA tasks to Outlook Calendar.
    """
    import traceback
    try:
        user_id = task.user_id
        lbs_client = await get_lbs_client(user_id, db_session)
        ol_client = await get_outlook_client(user_id, db_session)
        
        now = datetime.utcnow().date()
        for i in range(7):
            target_date = (now + timedelta(days=i)).isoformat()
            tasks = await lbs_client.list_tasks(target_date=target_date)
            
            for va_task in tasks:
                # DEBUG
                print(f"[DEBUG] Outlook Export: Task keys found: {list(va_task.keys())}")
                
                if va_task.get("context") == "External":
                    continue
                    
                metadata = va_task.get("metadata") or {}
                va_intent = metadata.get("va_intent") or {}
                
                event_data = {
                    "subject": f"[VA] {va_task['task_name']}",
                    "body": {
                        "contentType": "HTML",
                        "content": f"{(va_task.get('notes') or '')}<br><br>Cognitive Load: {va_task.get('load', 1.0)}"
                    },
                    "start": {
                        "dateTime": f"{target_date}T{va_task.get('start_time', '09:00:00')}",
                        "timeZone": "UTC"
                    },
                    "end": {
                        "dateTime": f"{target_date}T{va_task.get('end_time', '10:00:00')}",
                        "timeZone": "UTC"
                    }
                }

                # --- Handle Intent: Generate Meeting Link (Teams) ---
                if va_intent.get("generate_meeting_link"):
                    event_data["isOnlineMeeting"] = True
                    event_data["onlineMeetingProvider"] = "teamsForBusiness"

                # --- Handle Intent: Auto Invite ---
                invites = va_intent.get("auto_invite")
                if invites:
                    event_data["attendees"] = [
                        {"emailAddress": {"address": email}, "type": "required"} 
                        for email in invites
                    ]

                try:
                    created_event = await ol_client.create_event(event_data)
                    
                    # If we generated a link, save it back to LBS metadata
                    meeting_link = created_event.get("onlineMeeting", {}).get("joinUrl")
                    if meeting_link:
                        metadata["meeting_link"] = meeting_link
                        await lbs_client.update_task(va_task["task_id"], {"metadata": metadata})

                except Exception as inner_e:
                    import logging
                    logging.error(f"Failed to export task {va_task['task_id']} to Outlook: {inner_e}")
    except Exception as outer_e:
        print("!!! CRITICAL ERROR IN export_to_outlook handler !!!")
        traceback.print_exc()
        raise outer_e
