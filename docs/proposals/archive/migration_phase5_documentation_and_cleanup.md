# Migration Phase 5: Documentation & Cleanup

**Goal**: Ensure the codebase and documentation accurately reflect the new Orchestration2 architecture and that no hidden legacy "Node" code remains.

**Reference**: `docs/reports/node_to_orchestration2_residue_report.md` (Section 2 - Proposal 6)

## Plan

### 1. Update Documentation
- **Target**: `README.md`
    - Replace "Project-Node Architecture" diagrams/text.
    - Describe "Project-Agent-Skill" or "Orchestration Graph" architecture.
- **Target**: `docs/core/orchestration2_engine.md` (if exists)
    - Ensure it is the primary reference.
- **Target**: Create `docs/glossary.md` (Optional but recommended)
    - Map old terms to new (Node -> Agent/Profile).

### 2. Final Code Sweep
- **Tool**: `grep` / `rg`
- **Query**: `Node`, `node_id`, `enqueue_node_task`, `domains.orchestration` (legacy path).
- **Action**:
    - Delete any unused files found in `core/backend/domains/orchestration/` (if strictly legacy).
    - Remove commented-out legacy code.

### 3. Dependency Check
- Verify `requirements.txt` or `pyproject.toml` if any libraries were only used by legacy code (unlikely, but good to check).

## Verification
- Fresh clone & install.
- Read through README.
- `rg "Node"` returns minimal/no results (except perhaps in `AST` or `NodeJS` context, but not `infrastructure.node`).
