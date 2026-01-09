"""
LBS Condition Management Tools
Integrates with LBS Condition API for fatigue analysis.
"""
from typing import Optional, Dict
from datetime import datetime
import pytz
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from services.lbs_client import LBSClient
from models.database import ServiceRegistry
from utils.encryption import decrypt_string

async def _get_lbs_client(user_id: str, db: AsyncSession) -> Optional[LBSClient]:
    """Helper to initialize LBSClient for a user."""
    result = await db.execute(select(ServiceRegistry).filter(
        ServiceRegistry.user_id == user_id,
        ServiceRegistry.service_name == "lbs"
    ))
    service = result.scalars().first()
    if not service:
        return None
        
    api_key = None
    if service.api_key_encrypted:
        try:
            api_key = decrypt_string(service.api_key_encrypted)
        except Exception:
            pass
            
    return LBSClient(base_url=service.base_url, api_key=api_key)

def _get_today_jst() -> str:
    """Get current date in JST (YYYY-MM-DD)."""
    jst = pytz.timezone('Asia/Tokyo')
    return datetime.now(jst).strftime('%Y-%m-%d')

async def update_user_condition(
    cognitive_fatigue: int,
    target_date: Optional[str] = None,
    note: Optional[str] = None,
    user_id: str = None,
    session: AsyncSession = None,
    **kwargs
) -> str:
    """
    Set the user's fatigue level. 
    cognitive_fatigue: 0=Energetic, 3=Tired, 5=Limit
    """
    if not session or not user_id:
        return "Error: Database session or user_id missing"
        
    client = await _get_lbs_client(user_id, session)
    if not client:
        return "Error: LBS service not configured for this user"
        
    date_val = target_date or _get_today_jst()
    
    try:
        result = await client.update_condition(date_val, cognitive_fatigue, note)
        level_map = {0: "Energetic", 1: "Good", 2: "Normal", 3: "Tired", 4: "Very Tired", 5: "Limit"}
        level_str = level_map.get(cognitive_fatigue, str(cognitive_fatigue))
        return f"Successfully updated condition for {date_val}: {level_str}. LBS will adjust the schedule accordingly."
    except Exception as e:
        return f"Error updating condition: {str(e)}"

async def get_current_condition(
    target_date: Optional[str] = None,
    user_id: str = None,
    session: AsyncSession = None,
    **kwargs
) -> str:
    """Check the currently registered fatigue level."""
    if not session or not user_id:
        return "Error: Database session or user_id missing"
        
    client = await _get_lbs_client(user_id, session)
    if not client:
        return "Error: LBS service not configured for this user"
        
    date_val = target_date or _get_today_jst()
    
    try:
        result = await client.get_condition(date_val)
        level_map = {0: "Energetic", 1: "Good", 2: "Normal", 3: "Tired", 4: "Very Tired", 5: "Limit"}
        fatigue = result.get("cognitive_fatigue", 0)
        level_str = level_map.get(fatigue, str(fatigue))
        note = result.get("note")
        
        msg = f"Current condition for {date_val}: {level_str} (Level {fatigue})"
        if note:
            msg += f"\nNote: {note}"
        return msg
    except Exception as e:
        # LBS returns default Level 0 if not found, but handle 404/500 just in case
        return f"Information for {date_val}: No specific fatigue recorded (default: Energetic Lv0)."

async def reset_user_condition(
    target_date: Optional[str] = None,
    user_id: str = None,
    session: AsyncSession = None,
    **kwargs
) -> str:
    """Reset/Clear the fatigue level (back to healthy)."""
    if not session or not user_id:
        return "Error: Database session or user_id missing"
        
    client = await _get_lbs_client(user_id, session)
    if not client:
        return "Error: LBS service not configured for this user"
        
    date_val = target_date or _get_today_jst()
    
    try:
        await client.delete_condition(date_val)
        return f"Successfully reset/cleared condition for {date_val}. User is now considered to be in default healthy state (Lv0)."
    except Exception as e:
        return f"Error resetting condition: {str(e)}"
