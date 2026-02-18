# Agent Skills System

Agent Skills are reusable packages of specialized domain knowledge and procedural instructions that can be "attached" to AI agents in VisionArk. Unlike raw LLM tools, Skills provide the **procedural intelligence** (the "how-to") for using those tools and navigating specific domains.

## Core Concept: "Pluggable Intelligence"

Skills are managed through two complementary channels:

1. **Static Skills** — Defined in code via `SKILL_DEFS` in `engine_setup.py` and registered at engine bootstrap time. These define tool-filtering groups (e.g., `investigation`, `document_creation`, `operation`).
2. **DB Skills** — Stored in the `skills` table and assigned to projects via the `project_skills` join table. These provide prompt-injected procedural instructions to augment agent behavior at runtime.

---

## 1. Authoritative Specification: `orchestration2`

All skill behavior is governed by the `orchestration2` engine:

### SkillDef (Source of Truth)
```python
class SkillDef(BaseModel):
    name: str
    description: str | None = None
    tools: list[str] = []        # Tool names this skill can access
    request_approval: bool = False
```

### SkillRegistry
- Located at `core/backend/domains/orchestration2/engine/registry/skill_registry.py`
- Manages `name → (SkillDef, impl)` mappings
- Used by `StepExecutor` to resolve tool visibility per step

### Engine Setup
- Located at `core/backend/domains/orchestration2/engine_setup.py`
- Registers static `SKILL_DEFS` at engine creation
- Loads DB skills via `_load_prompt_components()` and injects them into agent prompts
- Integration tools are dynamically added to the `operation` skill

---

## 2. DB Skill Model

Skills in the database use the `Skill` ORM model:

| Column | Type | Purpose |
|---|---|---|
| `id` | `VARCHAR(100)` | Unique identifier (kebab-case) |
| `name` | `VARCHAR(100)` | Human-readable name |
| `description` | `VARCHAR(500)` | Summary shown in UI |
| `content` | `TEXT` | Procedural instructions (Markdown) |
| `metadata_payload` | `JSON` | Additional metadata (e.g., `tools` list) |
| `is_active` | `BOOLEAN` | Active/inactive toggle |
| `is_draft` | `BOOLEAN` | Draft skills from skill mining |

### Project Assignment
- Skills are assigned to a project's main agent via the `project_skills` table (`agent_id → skill_id`)
- The API endpoint `/api/skills/project/{project_id}` manages these assignments

---

## 3. How to Add a New Skill

### Method A: Static Skill (Code)
Add a `SkillDef` entry to `SKILL_DEFS` in `engine_setup.py`:
```python
SkillDef(
    name="my_skill",
    description="What this skill does",
    tools=["tool_a", "tool_b"],
)
```

### Method B: DB Skill (UI)
1. Navigate to the **Skills** page in the VisionArk sidebar.
2. Create or edit a skill with Markdown content and metadata.
3. Assign the skill to a project via **Project Settings → Skills** tab.
4. The skill content will be injected into the agent's system prompt at runtime.

---

## 4. Best Practices for Skill Writing

- **Be Procedural**: Give the agent numbered steps to follow.
- **Define Boundaries**: Tell the agent what *not* to do (e.g., "Do not share customer data during analysis").
- **Tool Context**: Explicitly mention which tools should be used for which steps.
- **Language**: Skills can be written in any language (Japanese, English, etc.), and the agent will adapt based on the system's localization settings.

---

## 5. Dynamic Knowledge Acquisition (Skill Mining)

VisionArk includes a dynamic learning mechanism (`skill_mining.py`) that automatically extracts new skills from high-value user interactions.

### Mining Logic & Safeguards
1. **Conservative Triggering (AES)**: Skill mining is enqueued as a `SYSTEM_SKILL_MINING` task in the Automated Execution System (AES).
2. **Complexity Heuristics**: A skill is only drafted if the interaction uses ≥2 distinct tool types and ≥3 total tool calls.
3. **Project-based Throttling**: Mining is restricted to once every 10 minutes per project.
4. **Deduplication**: The system checks for existing skills with the same name before saving.

### Lifecycle of a Mined Skill
1. **Extraction**: The `SkillMiningService` uses an LLM to distill procedural knowledge from interactions.
2. **Drafting**: The extracted skill is saved to the database with `is_draft=True`.
3. **Review**: Users can see mined drafts in the Skills UI, where they can refine, approve (activate), or discard them.

---

## 6. Deprecated Components

> [!WARNING]
> The following components have been deprecated and removed as of 2026-02-18.
> See [ADR: Skills Deprecation](../decisions/ADR-skills-deprecation.md) for details.

| Component | Status | Replacement |
|---|---|---|
| `automation/skill_service.py` (`SkillService`) | **Removed** | orchestration2 `SkillDef` + prompt injection via `engine_setup.py` |
| `automation/skills/registry.py` (FS → DB sync) | **Removed** | Skills are managed via UI / API only |
| `node_skills` table | **Removed** | `project_skills` table (agent-based) |
| `/api/skills/node/{nodeId}` | **Never existed** | `/api/skills/project/{project_id}` |
