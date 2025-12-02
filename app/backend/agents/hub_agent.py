"""
Hub Agent - Central orchestration agent
Implements hub-specific prompt loading, log paths, and LBS integration
"""
from pathlib import Path
from typing import List
from agents.base_agent import BaseAgent
from utils.paths import get_hub_dir
from models.message import Message, MessageRole, AttachedFile
from datetime import date


class HubAgent(BaseAgent):
    """Hub agent with Hub-specific logic and LBS integration"""
    
    def __init__(self):
        # Set hub_dir BEFORE calling super().__init__() 
        # because _load_history_from_log() needs it
        """
        Hub-specific chat with LBS context
        Adds meta_info about current load scores as formatted string
        """
        from services.lbs_engine import LBSEngine
        
        # Build LBS context as formatted string
        meta_info_str = None
        if db_session:
            try:
                engine = LBSEngine(db_session)
                today = date.today()
                
                # Get daily load
                daily_load = engine.get_daily_load(today)
                
                # Build formatted meta_info string
                meta_info_str = f"Load: {daily_load:.1f}/10.0 | Capacity: 10.0"
                
            except Exception as e:
                print(f"[Hub] Failed to load LBS context: {e}")
        
        # Create message with meta_info string
        msg = Message(
            role=MessageRole.USER,
            content=user_message,
            meta_info=meta_info_str  # String, not dict!
        )
        
        # Add to history
        self.conversation_history.append(msg)
        
        # Get LLM response
        if not self.system_prompt:
            self.system_prompt = self.load_system_prompt()
        
        llm_messages = [m.to_llm_message() for m in self.conversation_history]
        messages = self.llm.format_messages(self.system_prompt, llm_messages)
        response = self.llm.complete(messages)
        
        # Create assistant message
        assistant_msg = Message(
            role=MessageRole.ASSISTANT,
            content=response.content
        )
        self.conversation_history.append(assistant_msg)
        
        # Save to log
        self._save_to_log(msg)
        self._save_to_log(assistant_msg)
        
        return response.content
