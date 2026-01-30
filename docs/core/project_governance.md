# Project Governance & Rules

VisionArk allows for project-specific governance and file organization rules. This ensures that different projects can maintain their own standards for file naming, structure, and lifecycle management without system-wide rigidity.

## Core Components

### 1. `.visionark/project_rules.json`
The source of truth for a project's governance. This file is hidden from the main `docs/` and `artifacts/` directories to keep the workspace clean.

#### Supported Rules
- **Naming Conventions**: `snake_case`, `PascalCase`, etc.
- **Required Metadata**: Mandatory header fields for markdown files.
- **Directory Structure**: Descriptions and purposes for project subdirectories.
- **`project_rules.json`**: The source of truth for a project's governance.
- **`mining_state.json`**: Internal metadata for tracking skill mining throttling and history.

### 2. Ruler Node (The Organizer)
The Ruler node is responsible for enforcing these rules. It:
- Loads rules using `get_project_rules`.
- Validates file structure and naming.
- Automates archiving based on project-specific lifecycles.
- Maintains the project index (`docs/INDEX.md`).

### 3. Orchestration & Delegation
The **Project/Orchestrator** node coordinates with the Ruler:
- **Rule Setup**: Translates user preferences into the configuration using `update_project_rules`.
- **Delegation**: Automatically triggers the Ruler node for organizational tasks and cleanup.
- **Watcher Integration**: File generation in sensitive directories triggers a Ruler check.

## Governance Tools

To enhance security and maintain configuration integrity, specialized tools are used for rule management instead of generic file operations.

- **`get_project_rules`**: Retrieves the current project rules.
- **`update_project_rules`**: Validates the proposed rules against a strict JSON schema before saving them to the hidden `.visionark/` directory.

## Usage

### Setting Rules
Users can set rules by instructing the Project node:
> "In this project, I want all research reports to use PascalCase and include an 'Impact' field in the metadata."

The Project node will then update the `.visionark/project_rules.json` file.

### Automated Organization
The Ruler node periodically or reactively (via Watchers) performs the following:
1. **Validation**: Checks newly created files against the project rules.
2. **Indexing**: Updates `docs/INDEX.md` with links and summaries of new files.
3. **Archiving**: Moves files marked as `completed` or `obsolete` to `docs/archive/` after the specified period.
