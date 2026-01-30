# Roadmap: Dynamic Skill Learning & Mining

This document outlines the current implementation status and the future roadmap for VisionArk's "Skill Mining" system—the mechanism by which the system automatically learns and proposes new skills based on successful user interactions.

---

## 1. Current Implementation Status

As observed, the core infrastructure for Skill Mining is currently in a **Skeleton Phase**.

### What is implemented:
- **Background Hook**: `worker.py` now includes a `finally` block in `_process_task` that asynchronously triggers `_trigger_skill_mining`. This ensures that every high-level task is potentially evaluated without blocking the primary worker loop.
- **Service Skeleton**: `core/backend/services/skill_mining.py` exists and can be instantiated with a database session.
- **Draft Storage**: The `Skill` model supports an `is_draft` flag and an `is_active=False` default, allowing candidates to exist in the database without being used by agents until approved.

### What remains (Gaps):
- **Context Collection**: The logic to pull relevant message logs, tool call histories, and final outcomes is not yet fully defined.
- **Distillation Logic**: `analyze_task_for_skills` is currently a placeholder (`pass`).
- **Trigger Sensitivity**: Currently, it triggers on almost every message. It needs a "Success Filter" to only analyze tasks that achieved a positive outcome.

---

## 2. Future Implementation Phases

### Phase 1: Success Analytics (Short-Term)
The goal is to move from "trigger on every task" to "trigger on successful completion."
- **Feedback Loop**: Incorporate user "thumbs up" or system-detected success states (e.g., a scheduled task reaching `COMPLETED`).
- **Context Windowing**: Fetch the last $N$ turns of the conversation and the specific tool outputs that led to the success.

### Phase 2: The "Distiller" LLM (Mid-Term)
We will implement a specialized analysis prompt for a "Meta-Analyst" agent.
1. **Raw Log Input**: Provide the LLM with the raw tool logs and final response.
2. **Step Identification**: Ask the LLM: "What were the 3-5 repeatable steps taken here?"
3. **Drafting**: Use `generate_draft_skill` to create a `SKILL.md` candidate with a unique name and description.

### Phase 3: The Learning Hub UI (Mid-Term)
The `/skills` page will be enhanced with a "Drafts" or "Inbox" section.
- **Review Mode**: Users can see "The AI suggested a new skill: 'Market Trend Researcher' based on your activity yesterday."
- **Diff View**: Show the user exactly what instructions the AI proposed.
- **Promote to Static**: One-click approval to move the skill from many-to-many DB records to an actual `SKILL.md` in the filesystem (optional) or just activate it in the DB.

### Phase 4: Pattern Recognition across Users (Long-Term)
- **Frequent Pattern Detection**: Instead of mining single tasks, the system will analyze multiple tasks over a week to find recurring workflows that are *not yet* skills.
- **Cross-Node Learning**: If multiple different agents are performing similar sequences, the system suggests a global "Team Skill."

---

## 3. Realization Strategy

### The "Distillation" Loop
The system follows a cyclic loop to maintain quality:
1. **Execute**: Agent performs a complex task using general reasoning.
2. **Evaluate**: System detects a high-value success.
3. **Distill**: LLM summarizes the "how-to" into a structured Skill.
4. **Approve**: User refines and activates the skill.
5. **Specialize**: Subsequent agents use the Skill, becoming more efficient and predictable.

### Integration with Knowledge Core
Dynamic learning will also tap into the **Knowledge Core's time-series analysis**. By observing how data changes in response to agent actions (e.g., "Every time the user asks for X, the agent follows tool sequence A, B, C"), the system can identify "Behavioral Embeddings" that represent potential skills.

---

## 4. Technical Implementation Notes
- **Async Execution**: Mining should always run as an `asyncio.create_task` to ensure 0ms latency impact on the user.
- **Rate Limiting**: Analysis LLM calls should be throttled or run during "low-tide" periods (background processing) to manage API costs.
- **Privacy**: The mining service must respect `UserSession` boundaries so that skills learned in a private project do not leak into global or team-wide skill pools without explicit permission.
