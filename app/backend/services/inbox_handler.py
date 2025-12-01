"""
Inbox handler for Push protocol and async message processing
Implements <meta-action> parsing and queue management from BLUEPRINT.md Section 4.1-4.2
"""
from datetime import datetime
from typing import Dict, List, Optional
import xml.etree.ElementTree as ET
import json
from sqlalchemy.orm import Session

from models.database import InboxQueue, Task, LBSDailyCache


class InboxHandler:
    """Handle <meta-action> messages from Spokes to Hub"""
    
    def __init__(self, db_session: Session):
        self.session = db_session
    
    def parse_meta_action(self, xml_string: str) -> Optional[Dict]:
        """
        Parse <meta-action> XML block into structured data
        Returns None if parsing fails
        """
        try:
            root = ET.fromstring(xml_string)
            
            if root.tag != "meta-action":
                return None
            
            action_type = root.get("type", "unknown")
            
            action_data = {
                "type": action_type,
                "target": root.findtext("target", "Hub"),
                "timestamp": root.findtext("timestamp", datetime.utcnow().isoformat()),
                "summary": root.findtext("summary", ""),
            }
            
            # Parse LBS updates
            lbs_update_elem = root.find("lbs_update")
            if lbs_update_elem is not None:
                action_data["lbs_updates"] = []
                for task_elem in lbs_update_elem.findall("task"):
                    task_update = {
                        "id": task_elem.get("id"),
                        "action": task_elem.get("action", "update"),
                        "status": task_elem.get("status"),
                        "name": task_elem.get("name"),
                        "due_date": task_elem.get("due_date"),
                        "load_score": task_elem.get("load_score"),
                    }
                    action_data["lbs_updates"].append(task_update)
            
            # Parse request
            request_elem = root.find("request")
            if request_elem is not None:
                action_data["request"] = request_elem.text
            
            # Parse artifacts
            artifacts_elem = root.find("artifacts")
            if artifacts_elem is not None:
                action_data["artifacts"] = [
                    f.get("path") for f in artifacts_elem.findall("file")
                ]
            
            return action_data
            
        except ET.ParseError as e:
            print(f"XML Parse Error: {e}")
            return None
    
    def push_to_inbox(self, source_spoke: str, meta_action_xml: str) -> Optional[int]:
        """
        Push a <meta-action> message to the inbox queue
        Returns queue ID if successful, None if parsing failed
        """
        parsed = self.parse_meta_action(meta_action_xml)
        if not parsed:
            return None
        
        message_type = parsed.get("type", "share_update")
        
        inbox_msg = InboxQueue(
            source_spoke=source_spoke,
            message_type=message_type,
            payload=parsed,
            is_processed=False,
            received_at=datetime.utcnow()
        )
        
        self.session.add(inbox_msg)
        self.session.commit()
        
        return inbox_msg.id
    
    def get_pending_messages(self) -> List[InboxQueue]:
        """Fetch all unprocessed messages from inbox"""
        return self.session.query(InboxQueue).filter(
            InboxQueue.is_processed == False
        ).order_by(InboxQueue.received_at.desc()).all()
    
    def process_message(self, message_id: int, action: str, user_edits: Optional[Dict] = None) -> bool:
        """
        Process an inbox message with accept/reject/edit action
        Returns True if successful
        """
        msg = self.session.query(InboxQueue).filter(InboxQueue.id == message_id).first()
        if not msg:
            return False
        
        try:
            if action == "accept":
                self._apply_lbs_updates(msg.payload, user_edits)
                msg.is_processed = True
                msg.processed_at = datetime.utcnow()
            
            elif action == "reject":
                msg.is_processed = True
                msg.processed_at = datetime.utcnow()
                msg.error_log = "Rejected by user"
            
            elif action == "edit_accept":
                if user_edits:
                    self._apply_lbs_updates(msg.payload, user_edits)
                    msg.is_processed = True
                    msg.processed_at = datetime.utcnow()
            
            self.session.commit()
            return True
            
        except Exception as e:
            msg.error_log = str(e)
            self.session.commit()
            return False
    
    def _apply_lbs_updates(self, payload: Dict, user_edits: Optional[Dict] = None) -> None:
        """Apply LBS database updates from payload"""
        lbs_updates = payload.get("lbs_updates", [])
        
        for update in lbs_updates:
            # Apply user edits if provided
            if user_edits and update["id"] in user_edits:
                update.update(user_edits[update["id"]])
            
            action = update.get("action", "update")
            
            if action == "create":
                # Create new task (simplified for MVP)
                from datetime import datetime, date
                import uuid
                
                new_task = Task(
                    task_id=f"T-{uuid.uuid4().hex[:8]}",
                    task_name=update.get("name", "Unnamed Task"),
                    context=payload.get("source_spoke", "unknown"),
                    base_load_score=float(update.get("load_score", 3.0)),
                    rule_type="ONCE",
                    due_date=date.fromisoformat(update.get("due_date")) if update.get("due_date") else None,
                    active=True
                )
                self.session.add(new_task)
            
            elif action == "update":
                task_id = update.get("id")
                task = self.session.query(Task).filter(Task.task_id == task_id).first()
                if task and update.get("status"):
                    # Update cache entries
                    self.session.query(LBSDailyCache).filter(
                        LBSDailyCache.task_id == task_id,
                        LBSDailyCache.status == "planned"
                    ).update({"status": update["status"]})
        
        self.session.commit()


def extract_meta_actions_from_chat(chat_response: str) -> List[str]:
    """
    Extract all <meta-action> blocks from AI chat response
    Returns list of XML strings
    """
    import re
    pattern = r'(<meta-action[^>]*>.*?</meta-action>)'
    matches = re.findall(pattern, chat_response, re.DOTALL)
    return matches
