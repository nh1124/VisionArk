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
        roster_text = "### PROJECT ROSTER (Available Target Nodes)\n"
        roster_text += "| Node Name | Node ID | Description & Interests |\n"
        roster_text += "| :--- | :--- | :--- |\n"
        
        try:
            db_session = self.context.get("db_session")
            # a. System Nodes
            stmt_sys = select(Node).filter(Node.node_type == "SYSTEM")
            res_sys = await db_session.execute(stmt_sys)
            for n in res_sys.scalars():
                if n.id == self.id: continue # Prevent self-recursion
                
                meta = n.meta_payload or {}
                # EXCLUSION: Skip hidden nodes or the Router itself from discovery
                if meta.get("hidden") or n.role_name == "identity_router":
                    continue
                def extract_values(lst):
                    return [item.get("value") for item in lst if isinstance(item, dict) and item.get("value")]

                interests = extract_values(meta.get("semantic_interests", []))
                patterns = extract_values(meta.get("trigger_patterns", []))
                
                hook_details = []
                if interests: hook_details.append(f"Interests: {', '.join(interests)}")
                if patterns: hook_details.append(f"Regex: {', '.join(patterns)}")
                
                detail_text = "; ".join(hook_details) if hook_details else "N/A"
                roster_text += f"| {n.display_name} | `{n.id}` | {n.description} ({detail_text}) |\n"
            
            # b. Project Members
            if project_id:
                stmt_proj = select(Node).filter(Node.project_id == project_id)
                res_proj = await db_session.execute(stmt_proj)
                for n in res_proj.scalars():
                    if n.id == self.id: continue # Prevent self-recursion
                    if n.node_type != "SYSTEM":
                        meta = n.meta_payload or {}
                        # EXCLUSION: Skip hidden nodes
                        if meta.get("hidden"):
                            continue
                        def extract_values(lst):
                            return [item.get("value") for item in lst if isinstance(item, dict) and item.get("value")]

                        interests = extract_values(meta.get("semantic_interests", []))
                        patterns = extract_values(meta.get("trigger_patterns", []))
                        
                        hook_details = []
                        if interests: hook_details.append(f"Interests: {', '.join(interests)}")
                        if patterns: hook_details.append(f"Regex: {', '.join(patterns)}")
                        
                        detail_text = "; ".join(hook_details) if hook_details else "N/A"
                        roster_text += f"| {n.display_name} | `{n.id}` | {n.description} ({detail_text}) |\n"
        except Exception as e:
            print(f"[RouterNode] Error fetching roster: {e}")
            roster_text += "(Error fetching roster details)\n"

        # 2. Identify already notified nodes (from Router service context)
        already_triggered = self.context.get("already_triggered_node_ids", [])
        notified_text = ""
        if already_triggered:
            notified_text = f"\n\n> [!IMPORTANT]\n> The following Node IDs have **ALREADY** been notified via Regex hooks for this message: `{', '.join(already_triggered)}`.\n> The `multicast_message` tool will **FILTER THEM OUT** automatically unless you specifically need a redundant call (rare)."

        # 3. Load and Prepare Prompt
        system_prompt = await self.load_system_prompt(
            role_name=self.role_name, 
            components=["identity_router", "protocol_routing", "formatting"]
        )
        system_prompt += f"\n\n{roster_text}{notified_text}"
        system_prompt += "\n\nCRITICAL: Use the Node IDs provided in the table. Do NOT hallucinate node IDs. If you specify an ID not in the roster, the tool will fail."
        
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
