# Agent Skills System

Agent Skills are reusable packages of specialized domain knowledge and procedural instructions that can be "attached" to AI agents in VisionArk. Unlike raw LLM tools, Skills provide the **procedural intelligence** (the "how-to") for using those tools and navigating specific domains.

## Core Concept: "Pluggable Intelligence"

VisionArk uses a file-system-driven approach for skill management. Moving a skill directory into the system immediately registers it, allowing for easy distribution and versioning of AI capabilities.

---

## 1. Skill Definition (`SKILL.md`)

Each skill is defined in a directory within `core/backend/skills/`. The primary definition file is `SKILL.md`.

### Format Specification
`SKILL.md` uses YAML frontmatter for metadata and regular Markdown for instructions.

```markdown
---
name: "Competitor Analysis"
description: "Analyze competitor websites for UI/UX and business models"
id: "competitor-analysis-v1"
tools: ["search_web", "read_url_content"]
trigger_patterns: ["compare with*", "what does * do?"]
intents: ["research", "analysis"]
priority: 5
conflicts_with: ["daily-pilot-v1"]
tool_policy:
  allowlist: ["search_web", "read_url_content"]
  denylist: ["delete_task"]
  intent_map:
    research: ["search_web", "read_url_content"]
  retry:
    max_attempts: 2
    fallback_tools:
      search_web: ["deep_research"]
---

# Instructions
Follow these steps for a thorough analysis:
1. Search for the official website...
2. Evaluate the navigation structure...
...
```

- **Frontmatter Fields**:
    - `name`: Human-readable name.
    - `description`: Summary shown in the UI.
    - `id`: Unique identifier (kebab-case).
    - `tools`: Expected tools to be used with this skill.
    - `trigger_patterns`: (Optional) Keywords that suggest this skill is relevant.
    - `intents`: (Optional) Intent labels that can be used to select this skill at runtime.
    - `priority`: (Optional) Higher wins when resolving conflicts.
    - `conflicts_with`: (Optional) List of skill IDs/names to suppress when this skill is selected.
    - `tool_policy`: (Optional) Tool control metadata used for allow/deny, intent mapping, and fallbacks.

---

## 2. Technical Architecture

### Skill Registry (`registry.py`)
- **Discovery**: On system startup (lifespan), the `SkillRegistry` scans `core/backend/skills/` and `integrations/` recursively for `SKILL.md` files.
- **Sync**: It parses `SKILL.md` files and synchronizes them with the `skills` table in the database.
- **Persistence**: Database entries allow for user overrides and status toggling (Active/Inactive) via the UI.

### Skill Service (`skill_service.py`)
- **Node Association**: Skills are linked to specific agent nodes via the `node_skills` table.
- **Prompt Injection**: Before an agent is executed, the `SkillService` clones relevant active skills and appends their content to the agent's system prompt.
- **Intent Resolution**: If an intent is provided in the execution context, skills are filtered to intent-matching skills.
- **Conflict Handling**: Skills specify `conflicts_with` and `priority` to resolve overlaps. Higher priority skills suppress conflicting lower priority ones.
- **Tool Policy Merge**: `tool_policy` metadata is merged across resolved skills to enforce allow/deny/intent and fallback rules.

---

## 3. How to Add a New Skill

### Method A: Manual (Filesystem)
1. Create a folder in `core/backend/skills/[your-skill-id]/` OR in an integration folder like `core/backend/integrations/[name]/`.
2. Create a `SKILL.md` inside it following the format above.
3. Restart the backend or wait for the next sync cycle.

#### Integration Skills
Skills placed inside an integration folder are automatically discovered. If a skill folder is nested inside an integration, its ID will be prefixed (e.g., `line-auto-reply`).

### Method B: UI (Skill Editor)
1. Navigate to the **Skills** page in the VisionArk sidebar.
2. Click on a Draft skill or manage existing ones.
3. Edit the Markdown content and metadata directly in the browser.
4. Changes are saved to the database and take effect immediately for all agents using that skill.

---

## 4. Best Practices for Skill Writing

- **Be Procedural**: Give the agent numbered steps to follow.
- **Define Boundaries**: Tell the agent what *not* to do (e.g., "Do not share customer data during analysis").
- **Tool Context**: Explicitly mention which tools should be used for which steps.
- **Language**: Skills can be written in any language (Japanese, English, etc.), and the agent will adapt based on the system's localization settings.

---

## 5. Directory Structure
```text
core/backend/
├── skills/
│   ├── competitor-analysis/
│   │   └── SKILL.md
│   └── registry.py      # Logic for syncing FS to DB
├── integrations/
│   └── line/
│       └── SKILL.md     # Integration-embedded skill
├── services/
│   ├── skill_service.py # Logic for prompt injection
│   └── skill_mining.py  # Logic for dynamic learning
```

## 6. Dynamic Knowledge Acquisition (Skill Mining)

VisionArk includes a dynamic learning mechanism located in `skill_mining.py` that automatically extracts new skills from high-value user interactions.

### Mining Logic & Safeguards
To ensure high-quality skill generation and system stability, mining is governed by the following rules:

1. **Conservative Triggering (AES)**: Skill mining is not performed in real-time. Instead, it is enqueued as a `SYSTEM_SKILL_MINING` task in the **Automated Execution System (AES)**.
2. **Complexity Heuristics**: A skill is only drafted if the interaction meets complexity criteria:
    - **Multiple Tool Types**: Uses at least 2 distinct types of tools.
    - **Procedure Depth**: Involves at least 3 total tool calls.
3. **Project-based Throttling**: To prevent queue pressure, mining for a specific project is restricted to **once every 10 minutes**. This status is tracked in the project's hidden `.visionark/mining_state.json` file.
4. **Deduplication**: Before saving a new draft, the system checks for existing skills with the same name to avoid redundancy.

> **Note**: Mined skills may omit optional metadata like `intents`, `priority`, or `tool_policy`. These can be added or refined during review to enable runtime selection and tool control.

### Lifecycle of a Mined Skill
1. **Extraction**: The `SkillMiningService` uses an LLM (Gemini) to distill the "Procedural DNA" from the last 10 messages of an interaction.
2. **Drafting**: The extracted skill is saved to the database with `is_draft=True`.
3. **Review**: Users can see mined drafts in the Skills UI, where they can refine, approve (activate), or discard them.
