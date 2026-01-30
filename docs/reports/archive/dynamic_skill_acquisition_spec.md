# Technical Specification: Dynamic Skill Acquisition

This document provides a concrete plan for implementing dynamic skill learning in VisionArk, moving beyond the current skeleton phase.

---

## 1. Implemented Features (Planned)

### A. The "Distiller" LLM Service
A specialized service within `SkillMiningService` that transforms raw interaction data into structured skills.
- **Input**: Conversation history, tool call logs, and outcome status.
- **Output**: A valid `SKILL.md` candidate (YAML + Markdown).
- **Core Logic**: Uses "Few-Shot Chain of Thought" prompting to identify repeatable procedural steps.

### B. AES (Automated Event System) Trigger
Integration with VisionArk's AES to detect "Learning Moments" and manage batch processing.
- **Handler**: Registered as `SYSTEM_SKILL_MINING` in `core/backend/services/aes_system_handlers.py`.
- **Registration**: The system automatically registers a daily recurring mining task during startup (`skills/__init__.py`) if one does not exist.
- **Service**: Consolidated within `SkillMiningService` in `skill_mining.py`.
- **Flow**: Both real-time and periodic mining share the same logic, ensuring consistent skill extraction across different triggers.
- **Complexity Trigger**: When multiple tool calls are successfully combined to reach a goal.

### C. Learning Hub (Front-End)
- **Draft Management**: A dedicated view to list AI-generated skill candidates.
- **Instruction Sandbox**: A way to test a draft skill on a test node before official promotion.

---

## 2. Execution Flow

The system supports two complementary execution flows: **Real-time Distillation** and **Periodic Distillation (AES)**.

### Flow A: Real-time Distillation (Worker-based)
Triggered immediately after a high-value interaction.
1. **Completion**: Worker finishes a `NODE_EXECUTION` task.
2. **Hook**: `_trigger_skill_mining` is called asynchronously.
3. **Analyze**: `SkillMiningService` checks if the task history contains enough complexity to be a skill.
4. **Draft**: If threshold met, a `Skill` record with `is_draft=True` is created.

### Flow B: Periodic Distillation (AES/Scheduler-based)
Triggered on a schedule (e.g., nightly) to find patterns across multiple sessions.
1. **Schedule**: AES triggers a `SYSTEM_MANAGEMENT` task at 2:00 AM.
2. **Scan**: `SkillMiningService` queries the `ChatMessage` and `ScheduledTask` tables for the past 24 hours.
3. **Batch Mining**: Groups similar successful tasks using vector similarity.
4. **Distill**: LLM summarizes the "Common Workflow" found across these tasks.
5. **Report**: The system creates a draft skill and notifies the user: *"I noticed you performed 'Report Formatting' 5 times today. Should I learn this as a skill?"*

---

## 3. Realization Methods

### A. Semantic Verification (Vector Store)
Before proposing a new skill, the system checks if a similar skill already exists.
- **Method**: Embed the proposed `description` and use `VectorStore` to search against existing active skills.
- **Goal**: Prevent duplicate skill bloat and prioritize refinement over duplication.

### B. Procedural Extraction Prompt
The prompt used for distillation is the most critical component.
```text
SYSTEM: You are a Senior Workflow Architect.
INPUT: [Tool Log] -> [Success Output]
TASK: Extract the procedural "DNA" of this success. 
Identify mandatory steps, optional branches, and required tools. 
Format as a VisionArk SKILL.md.
```

### C. Human-in-the-loop (HIL)
Dynamic learning is strictly **Draft -> Approve -> Active**.
- **Draft**: Saved only in DB.
- **Review**: User edits the Markdown in the Skills UI.
- **Promote**: On approval, the skill can optionally be written to `core/backend/skills/distilled/` as a static file to make it permanent and version-controllable.

---

## 4. Implementation Priority
1. **Success Filter**: Update `SkillMiningService` to only act on `COMPLETED` tasks with at least 2 tool calls.
2. **Distiller Prompt**: Implement the LLM call in `generate_draft_skill`.
3. **AES Hook**: Create a periodic scheduled task in the system to trigger batch mining.
4. **UI Approval Flow**: Enable the "Approve/Reject" buttons on the Skills page.
