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

---

## 2. Technical Architecture

### Skill Registry (`registry.py`)
- **Discovery**: On system startup (lifespan), the `SkillRegistry` scans `core/backend/skills/`.
- **Sync**: It parses `SKILL.md` files and synchronizes them with the `skills` table in the database.
- **Persistence**: Database entries allow for user overrides and status toggling (Active/Inactive) via the UI.

### Skill Service (`skill_service.py`)
- **Node Association**: Skills are linked to specific agent nodes via the `node_skills` table.
- **Prompt Injection**: Before an agent is executed, the `SkillService` (formerly in `va_sdk`) fetches all attached active skills and appends their content to the agent's system prompt.

### 2. Technical Architecture

The system resides entirely within the `core/backend/` logic to maintain a clean distinction between core internals and the external SDK.

- **Skill Registry**: Scans `skills/` and `integrations/` recursively for `SKILL.md` files.
- **Skill Service**: Located in `core/backend/services/skill_service.py`.

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
