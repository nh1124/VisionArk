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

### Layer 4: Project Context & Plan (Alignment)
- **Source**: `artifacts/PLAN.md` (injected via `project_plan` component).
- **Purpose**: Ensures all agents work within the agreed-upon goal, strategy, and constraints.
- **Mechanism**: The `BaseNode` automatically detects the `"project_plan"` component and injects the formatted contents of `PLAN.md` into the system prompt.

### Layer 5: Runtime Context (Intelligence)
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

### B. The Project Node (Orchestrator)
The Project node focuses on **Long-term Management**.
- **Plan Invariants**: Injects the `PLAN.md` to ensure its reasoning aligns with the project's master roadmap.
- **Memory Context**: Injects summaries of previous sessions if the context was recently archived.
- **Roster Overview**: Provides a comprehensive team map including "Peer Projects".

### C. Member Nodes (Specialists)
Member nodes (Researcher, Planner, etc.) are optimized for **Consistent Execution**.
- **Auto-Alignment**: Use the `project_plan` component by default to understand their current role within the larger strategy.
- **Scope Locking**: Automatically scoped to the `project_id` and assigned a specific subset of tools.

---

## 3. Automated Plan Enrichment (Post-Session Lifecycle)

VisionArk implements a "Self-Evolving Plan" mechanism that operates at the end of each session.

- **The `on_exit` Hook**: When a session concludes, the **Project Node** automatically searches for an active **Planner** node in the project roster.
- **Planner Delegation**: The Orchestrator uses `ask_node` to delegate the task of "Enriching the Master Plan".
- **Dynamic Updates**: The Planner analyzes the session's discoveries and decisions, then uses the `update_md_section` tool to update `Log`, `Current Status`, and `Recent Discoveries` in `PLAN.md`.

---

## 4. Opportunities for Efficiency Refinement

Based on the current architecture, here are areas where prompt construction can be "brushed up":

1.  **Semantic Interest Mapping**: Enhancing the `RouterNode`'s roster injection with more granular interest descriptions.
2.  **Context Slicing**: Implementing more sophisticated context selection for the "Team Roster" based on user intent.
3.  **Governance Integration**: Leveraging `.visionark/plan_policy.json` to allow the `Ruler` node to automatically flag prompt inconsistencies.

---
*Report updated on 2026-02-02*
