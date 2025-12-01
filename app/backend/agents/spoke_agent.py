"""
Spoke Agent - Project-specific execution agent
Handles task management within a specific project context
"""
from pathlib import Path
from datetime import datetime

from agents.base_agent import BaseAgent
from utils.paths import get_spoke_dir


class SpokeAgent(BaseAgent):
    """Spoke agent for project-specific work"""
    def __init__(self, spoke_name: str):
        super().__init__(agent_type="spoke", context_name=spoke_name)
        self.spoke_name = spoke_name
        self.spoke_dir = get_spoke_dir(spoke_name)
        
        # Set up chat log path
        self.chat_log_path = self.spoke_dir / "chat.log"
        
        # Load conversation history if exists
        self._load_history()
    
    def _load_history(self):
        """Load conversation history from chat.log"""
        if not self.chat_log_path.exists():
            return
        
        try:
            with open(self.chat_log_path, 'r', encoding='utf-8') as f:
                current_role = None
                current_content = []
                
                for line in f:
                    line = line.strip()
                    if line.startswith("User:"):
                        if current_role:
                            self.conversation_history.append({
                                "role": current_role,
                                "content": "\n".join(current_content)
                            })
                        current_role = "user"
                        current_content = [line[5:].strip()]
                    elif line.startswith("Assistant:"):
                        if current_role:
                            self.conversation_history.append({
                                "role": current_role,
                                "content": "\n".join(current_content)
                            })
                        current_role = "assistant"
                        current_content = [line[10:].strip()]
                    elif line and current_role:
                        current_content.append(line)
                
                # Add last message
                if current_role and current_content:
                    self.conversation_history.append({
                        "role": current_role,
                        "content": "\n".join(current_content)
                    })
        except Exception as e:
            print(f"Failed to load history: {e}")
    
    def _save_history(self):
        """Save conversation history to chat.log"""
        try:
            with open(self.chat_log_path, 'w', encoding='utf-8') as f:
                for msg in self.conversation_history:
                    role_label = "User" if msg["role"] == "user" else "Assistant"
                    f.write(f"{role_label}: {msg['content']}\n\n")
        except Exception as e:
            print(f"Failed to save history: {e}")
    
    def chat_with_artifacts(self, user_message: str) -> str:
        """
        Chat with context about project artifacts
        """
        # List available artifacts
        artifacts_dir = self.spoke_dir / "artifacts"
        refs_dir = self.spoke_dir / "refs"
        
        artifacts = list(artifacts_dir.glob("*")) if artifacts_dir.exists() else []
        refs = list(refs_dir.glob("*")) if refs_dir.exists() else []
        
        context_info = f"""
## Project Artifacts Available
- **Artifacts**: {len(artifacts)} files
- **References**: {len(refs)} files

---

User Message: {user_message}
"""
        
        # Use parent chat() method
        response = self.chat(context_info)
        
        # Save history after each exchange
        self._save_history()
        
        return response
