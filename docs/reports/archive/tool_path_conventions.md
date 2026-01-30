# Agent Tool Path Conventions & Rules (STARDARDIZED)

This report summarizes the **standardized** path-handling logic across all agent tools in VisionArk.

## Unified Rule: Root-Relative Paths
As of 2026-01-20, all tools follow the **Project Root-Relative** path convention. This ensures that any path returned by a listing or generation tool can be used directly as input for reading, updating, or deleting tools.

## Projects Directory Structure
- `refs/`: Immutable reference materials.
- `files/`: User-uploaded files.
- `artifacts/`: AI-generated content.

---

## Tool-Specific Implementation

### 1. File Listing (`list_files`)
- **Return Format**: A list of project-relative paths (e.g., `["refs/manual.pdf", "artifacts/plans/v1.md"]`).
- **Behavior**: It recursively searches the target `sub_dir` but prefixes all results with the correct path from the root.

### 2. File Reading (`read_reference`)
- **Rule**: Flexible Search (Project Root prioritized).
- **Behavior**: It first checks the path exactly as provided (e.g., `artifacts/report.md`). If not found, it falls back to checking subfolders for legacy support, but agents are encouraged to use the full relative path.

### 3. Artifact Management (`save_artifact`, `delete_artifact`)
- **Input Rule**: Accepts paths starting with `artifacts/` (e.g., `artifacts/v1.md`).
- **Safety**: If the `artifacts/` prefix is omitted, it will automatically prepend it to ensure the file is saved in the correct project subdirectory.
- **Return Value**: Returns the actual relative path used (e.g., `artifacts/v1.md`).

### 4. Image Generation (`generate_image`)
- **Return Format**: `{"embed_path": "artifacts/filename.png", "path": "artifacts/filename.png"}`
- **Standard**: The returned path is ready to be used with `delete_artifact` or `read_reference`.

### 5. Mermaid Visualization (`generate_mermaid_visualizer`)
- **Implementation**: Saves diagrams to `artifacts/visuals/{title}.md`.

---

## Summary Matrix

| Tool | Input Path Style | Output Path Style | Comparison to Root |
| :--- | :--- | :--- | :--- |
| `list_files` | Sub-dir name | **Root Relative** | **Consistent** |
| `read_reference`| **Root Relative** | File Content | **Consistent** |
| `save_artifact` | **Root Relative** | **Root Relative** | **Consistent** |
| `delete_artifact`| **Root Relative** | **Root Relative** | **Consistent** |
| `generate_image` | N/A | **Root Relative** | **Consistent** |

---
*Standardization implemented on 2026-01-20.*
