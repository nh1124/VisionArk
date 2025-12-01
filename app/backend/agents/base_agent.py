"""
Base agent class for Hub and Spoke agents
Implements system prompt composition and context management from BLUEPRINT Section 4.3
Now with multi-LLM provider support
"""
from typing import List, Dict
from pathlib import Path
from datetime import datetime

from llm import get_provider
from llm.base_provider import Message
from utils.paths import get_spoke_dir, get_hub_dir


class BaseAgent:
    """Base class for all AI agents in the system"""
    
    def __init__(self, agent_type: str, context_name: str = "hub"):
        self.agent_type = agent_type  # "hub" or "spoke"
        self.context_name = context_name
        self.conversation_history: List[Dict[str, str]] = []
        
        # Get LLM provider from factory (supports Gemini, OpenAI, etc.)
        self.llm = get_provider()
        
        # Build system prompt
        self.system_prompt = self._build_system_prompt()
    
    def _build_system_prompt(self) -> str:
        """
        F4.3.2: Prompt Composition Logic
        Layer 1 (Global) + Layer 2 (Agent-specific) + Layer 3 (Context-specific)
        """
        prompt_parts = []
        
        # Layer 1: Global assets
        global_prompt_path = Path("global_assets/system_prompt_global.md")
        if global_prompt_path.exists():
            prompt_parts.append(global_prompt_path.read_text())
        else:
            prompt_parts.append(self._get_default_global_prompt())
        
        # Layer 2: Agent-specific (Hub vs Spoke)
        if self.agent_type == "hub":
            prompt_parts.append(self._get_hub_prompt())
        elif self.agent_type == "spoke":
            prompt_parts.append(self._get_spoke_prompt())
        
        # Layer 3: Context-specific (for Spokes)
        if self.agent_type == "spoke":
            spoke_prompt_path = get_spoke_dir(self.context_name) / "system_prompt.md"
            if spoke_prompt_path.exists():
                prompt_parts.append(spoke_prompt_path.read_text())
        
        return "\n\n---\n\n".join(prompt_parts)
    
    def _get_default_global_prompt(self) -> str:
        """Default global prompt if file doesn't exist"""
        return """# AI TaskManagement OS - Global System Prompt

You are an AI agent within the Antigravity OS, a sophisticated task management system designed to minimize cognitive load.

## Core Principles
1. **Explicit Control**: Never make assumptions. Always ask for confirmation before major actions.
2. **State over Memory**: Important information is stored in the database, not just in conversation.
3. **Clarity**: Be concise, precise, and action-oriented.

## Output Format
- Use clear, professional language
- When citing tasks, use their IDs (T-xxxxx)
- Format dates as YYYY-MM-DD
- Always explain your reasoning briefly
"""
    
    def _get_hub_prompt(self) -> str:
        """Hub-specific prompt"""
        return """# Hub Agent (Project Manager Role)

You are the central orchestration agent (Hub) responsible for:
- Managing the LBS (Load Balancing System) across all projects
- Processing reports from Spoke agents
- Making strategic resource allocation decisions
- Preventing cognitive overload

## Your Responsibilities
1. Monitor daily and weekly load scores
2. Warn when capacity (CAP) is approaching or exceeded
3. Suggest task rescheduling when necessary
4. Process Inbox messages from Spokes
5. Provide high-level strategic guidance

## Communication Style
- Strategic and meta-level (don't get into project details)
- Data-driven (cite load scores, capacities)
- Proactive (warn about bottlenecks before they occur)
"""
    
    def _get_spoke_prompt(self) -> str:
        """Spoke-specific prompt"""
        return """# Spoke Agent (Execution Role)

You are a project-specific execution agent (Spoke) responsible for:
- Managing tasks within your assigned project context
- Executing detailed work
- Reporting progress to Hub when milestones are reached

## Your Responsibilities
1. Help with project-specific work
2. Track task completion
3. Generate <meta-action> reports for Hub when appropriate
4. Stay focused on your project domain

## Communication Style
- Detail-oriented and hands-on
- Project-specific expertise
- Collaborative and supportive
"""
    
    def chat(self, user_message: str) -> str:
        """
        Send a message and get a response
        Maintains conversation history
        """
        # Add user message to history
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })
        
        # Format messages for LLM
        messages = self.llm.format_messages(
            self.system_prompt,
            self.conversation_history[-10:]  # Keep last 10 messages
        )
        
        # Get response from LLM (now provider-agnostic!)
        response = self.llm.complete(messages)
        assistant_message = response.content
        
        # Add assistant response to history
        self.conversation_history.append({
            "role": "assistant",
            "content": assistant_message
        })
        
        return assistant_message
    
    def clear_history(self):
        """Clear conversation history (for context rotation)"""
        self.conversation_history = []
