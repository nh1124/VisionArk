from typing import Any, Dict, List, Optional
from nodes.system.generic_system_node import GenericSystemNode

class RouterNode(GenericSystemNode):
    """
    Intelligent System Router.
    Analyzes user intent and multicasts messages to relevant nodes.
    """
    role_name = "Router"
    display_name = "System AI Router"
    description = "Analyzes message patterns and multicasts tasks to specialized nodes using LLM analysis."
    default_tools = ["ask_node", "multicast_message"]

    async def on_execute(self, message: str) -> Any:
        """
        1. Fetch project roster.
        2. Load Router specific prompt.
        3. Inject roster into prompt.
        4. Analyze message intent via LLM.
        """
        from models.message import Message, MessageRole
        from models.database import Node
        from sqlalchemy import select
        
        # 1. Fetch Roster
        project_id = self.context.get("project_id")
        roster_text = "### PROJECT ROSTER (Target IDs)\n"
        
        try:
            db_session = self.context.get("db_session")
            # a. System Nodes
            stmt_sys = select(Node).filter(Node.node_type == "SYSTEM")
            res_sys = await db_session.execute(stmt_sys)
            for n in res_sys.scalars():
                interests = n.meta_payload.get("semantic_interests", []) if n.meta_payload else []
                interest_text = f" (Interests: {', '.join(interests)})" if interests else ""
                roster_text += f"- {n.display_name} (ID: {n.id}): {n.description}{interest_text}\n"
            
            # b. Project Members
            if project_id:
                stmt_proj = select(Node).filter(Node.project_id == project_id)
                res_proj = await db_session.execute(stmt_proj)
                for n in res_proj.scalars():
                    if n.node_type != "SYSTEM": # redundant check but safe
                        interests = n.meta_payload.get("semantic_interests", []) if n.meta_payload else []
                        interest_text = f" (Interests: {', '.join(interests)})" if interests else ""
                        roster_text += f"- {n.display_name} (ID: {n.id}): {n.description}{interest_text}\n"
        except Exception as e:
            print(f"[RouterNode] Error fetching roster: {e}")
            roster_text += "(Error fetching roster details)\n"

        # 2. Load and Prepare Prompt
        system_prompt = await self.load_system_prompt()
        system_prompt += f"\n\n{roster_text}"
        system_prompt += "\n\nCRITICAL: Use 'multicast_message' to notify multiple agents at once. Do NOT ask for node IDs; they are provided above."
        
        history = [
            Message(role=MessageRole.USER, content=f"Analyze and route the following message: '{message}'")
        ]
        
        print(f"[RouterNode] Analyzing routing for: {message[:50]}...")
        
        llm_response = await self.chat_with_tools(
            system_prompt=system_prompt,
            message_history=history,
            tool_context=self.context
        )
        
        return llm_response.content or "Routing analysis complete."
