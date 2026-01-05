"""
Inbox handler for Push protocol and async message processing
Implements <meta-action> parsing and queue management from BLUEPRINT.md Section 4.1-4.2
"""
from datetime import datetime
from typing import Dict, List, Optional
import xml.etree.ElementTree as ET
import json
from sqlalchemy.orm import Session

from models.database import InboxQueue
from services.lbs_client import LBSClient


class InboxHandler:
    """Handle <meta-action> messages from Spokes to Hub (per-user)"""
    
    def __init__(self, db_session: Session, user_id: str = None):
        self.session = db_session
        self.user_id = user_id
    
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
            user_id=self.user_id,  # Include user_id for filtering
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
        """Fetch all unprocessed messages from inbox for this user"""
        query = self.session.query(InboxQueue).filter(
            InboxQueue.is_processed == False
        )
        if self.user_id:
            query = query.filter(InboxQueue.user_id == self.user_id)
        return query.order_by(InboxQueue.received_at.desc()).all()


def extract_meta_actions_from_chat(chat_response: str) -> List[str]:
    """
    Extract all <meta-action> blocks from AI chat response
    Returns list of XML strings
    """
    import re
    pattern = r'(<meta-action[^>]*>.*?</meta-action>)'
    matches = re.findall(pattern, chat_response, re.DOTALL)
    return matches
