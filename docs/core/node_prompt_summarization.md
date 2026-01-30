# VisionArk: Node Prompt Construction Report

This report summarizes how prompts are constructed for various nodes within the VisionArk system. Understanding this layered architecture is key to enhancing node efficiency and refining their behavioral patterns.

## 1. The Layered Prompt Architecture

VisionArk uses a **4-layer "Prompt Layering" strategy**. When a node is executed, its system prompt is dynamically assembled from these layers to provide a balance of global consistency and specialized expertise.

### Layer 1: Global Identity (Foundation)
- **Source**: `core/backend/assets/prompts/system/global.md`
- **Purpose**: Establishes the "Co-Pilot" persona and core behavioral constraints.
- **Key Elements**:
    - **Unified Interaction Model**: Explains `ask_node` (Command) vs. `subscribe_to_intent` (Subscription).
    - **Core Philosophy**: "Execute with Insight", "Contextual Intelligence", and "Explicit State Management".
    - **Protocols**: Strict rules for time handling, file operations, and response structuring.

### Layer 2: Specialized Role (Domain Expertise)
- **Source**: `core/backend/assets/prompts/roles/{role_name}.md` (Static) or Database `Node.system_prompt` (Dynamic).
- **Purpose**: Defines the specific mission and logic for the node.
- **Hierarchy**: The system prioritizes **Database prompts** over Markdown files, allowing project-specific "personalization" of nodes without code changes.

### Layer 3: Dynamic Tool Definitions (Capability)
- **Source**: Auto-generated from the node's `self.tools` list.
- **Purpose**: Injects the names and descriptions of available tools into the prompt.
- **Mechanism**: Calls `tool.declaration()` for each registered tool to provide the LLM with up-to-date documentation on its capabilities.

### Layer 4: Runtime Context (Intelligence)
- **Source**: Injected via `BaseNode.chat_with_tools` and specialized `on_execute` methods.
- **Key Elements**:
    - **Temporal**: Current Date & Time (Crucial for LBS and scheduling).
    - **User Profile**: Personal preferences and context data loaded from the user's settings.
    - **Knowledge retrieval**: Relevant snippets from the vector database (via `MemoryNode`).
    - **Team Roster**: A list of other active Node IDs and their descriptions (enables delegation).

---

## 2. Node-Specific Construction Logic

### A. The Router Node (System AI Router)
The Router's prompt is specifically tuned for **Meta-Cognition** and **Multicasting**.
- **Roster Injection**: Injects all System and Project nodes with their `semantic_interests` and `trigger_patterns`.
- **Constraint Injection**: Explicitly instructs the LLM to use `multicast_message` and avoid redundant notifications.
- **Status Awareness**: Injects a list of `already_triggered_node_ids` (from regex hooks) so the LLM doesn't double-route.

### B. The Project Node (Orchestrator)
The Project node focuses on **Long-term Management**.
- **Memory Context**: Injects summaries of previous sessions if the context was recently archived.
- **Roster Overview**: Provides a comprehensive team map including "Peer Projects" for cross-project collaboration.
- **Knowledge Core**: Heavily utilizes RAG (Retrieval-Augmented Generation) derived from the project's knowledge base.

### C. Member Nodes (Specialists)
Member nodes (Researcher, Planner, etc.) are optimized for **Dynamic Configuration**.
- **DB Priority**: Their prompts often reside entirely in the Database, allowing users to "instruct" their specialists via the UI.
- **Scope Locking**: Automatically scoped to the `project_id` and assigned a specific subset of tools.

---

## 3. Opportunities for Efficiency Refinement

Based on the current architecture, here are areas where prompt construction can be "brushed up":

1.  **Semantic Interest Mapping**: Enhancing the `RouterNode`'s roster injection with more granular interest descriptions could reduce "mistakes" in routing.
2.  **Tool usage "Small-Talk" Reduction**: Refining the Global Prompt to strictly minimize conversational filler during tool-heavy tasks can save output tokens.
3.  **Context Slicing**: Implementing more sophisticated context selection for the "Team Roster" (only showing relevant nodes based on intent) can reduce token overhead in the `ProjectNode`.
4.  **Prompt Templating**: Moving from string concatenation to a robust templating system (like Jinja2) would allow for safer and more complex logic within the prompts.

---
*Report generated on 2026-01-23*
