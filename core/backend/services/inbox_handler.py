"""
Inbox handler for Push protocol and async message processing
Implements <meta-action> parsing and queue management from BLUEPRINT.md Section 4.1-4.2
"""
from datetime import datetime
from typing import Dict, List, Optional
import xml.etree.ElementTree as ET
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.database import InboxQueue
from services.lbs_client import LBSClient


class InboxHandler:
    """Handle <meta-action> messages from Spokes to Hub (per-user)"""
    
    def __init__(self, db_session: AsyncSession, user_id: str = None):
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
    
    async def push_to_inbox(self, source_project_id: str, meta_action_xml: str) -> Optional[int]:
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
            source_project_id=source_project_id,
            message_type=message_type,
            payload=parsed,
            is_processed=False,
            received_at=datetime.utcnow()
        )
        
        self.session.add(inbox_msg)
        await self.session.commit()
        
        return inbox_msg.id
    
    async def get_pending_messages(self) -> List[InboxQueue]:
        """Fetch all unprocessed messages from inbox for this user"""
        stmt = select(InboxQueue).filter(InboxQueue.is_processed == False)
        if self.user_id:
            stmt = stmt.filter(InboxQueue.user_id == self.user_id)
        
        result = await self.session.execute(stmt.order_by(InboxQueue.received_at.desc()))
        return result.scalars().all()

    async def process_message(self, message_id: int, action: str) -> bool:
        """
        Process an inbox message (accept/reject)
        """
        from datetime import date
        result = await self.session.execute(select(InboxQueue).filter(
            InboxQueue.id == message_id,
            InboxQueue.user_id == self.user_id,
            InboxQueue.is_processed == False
        ))
        msg = result.scalars().first()
        
        if not msg:
            return False
        
        if action == "accept":
            # Apply LBS updates if present
            lbs_updates = msg.payload.get("lbs_updates", [])
            if lbs_updates:
                client = LBSClient(user_id=self.user_id)
                for update_data in lbs_updates:
                    try:
                        if update_data["action"] == "complete":
                            await client.toggle_task_completion(
                                update_data["id"], 
                                update_data.get("due_date", date.today().isoformat()),
                                status=True
                            )
                    except Exception as e:
                        print(f"Failed to apply LBS update: {e}")
        
        msg.is_processed = True
        msg.processed_at = datetime.utcnow()
        await self.session.commit()
        return True


def extract_meta_actions_from_chat(chat_response: str) -> List[str]:
    """
    Extract all <meta-action> blocks from AI chat response
    Returns list of XML strings
    """
    import re
    pattern = r'(<meta-action[^>]*>.*?</meta-action>)'
    matches = re.findall(pattern, chat_response, re.DOTALL)
    return matches
