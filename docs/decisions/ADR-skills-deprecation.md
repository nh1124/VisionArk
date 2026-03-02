# ADR: Deprecation of Legacy Skill Components

- **Date**: 2026-02-18 (追記: 2026-02-20)
- **Status**: Accepted
- **Context**: [skills_refactor_assessment_20260217.md](../proposals/skills_refactor_assessment_20260217.md), [Skill_refactoring.md](../proposals/Skill_refactoring.md)

## Decision

Deprecate and remove the following legacy skill components in favor of the `orchestration2` engine's `SkillDef` / `SkillRegistry`:

| Removed Component | Reason |
|---|---|
| `domains/automation/skill_service.py` | Unused — zero imports across the entire codebase. Intent/priority/conflict/tool_policy logic is not connected to orchestration2 execution. |
| `domains/automation/skills/registry.py` | Filesystem-based `SKILL.md → DB` sync with incorrect search paths. Replaced by UI/API skill management. |
| `domains/automation/skills/__init__.py` (`init_skills()`) | Entry point for the removed registry sync. Called from `main.py` and `worker.py` lifespan hooks. |

## Rationale

1. **Single source of truth**: `orchestration2` defines skill behavior via `SkillDef(name, description, tools, request_approval)` and `SkillRegistry`. The legacy `SkillService` used a different model (`metadata_payload` with `intent/priority/conflicts/tool_policy`) that was never connected to the execution path.

2. **No functional loss**: `SkillService` had zero imports — it was dead code. The `init_skills()` filesystem sync can be replaced by the existing UI/API for skill management.

3. **Frontend alignment**: The settings page referenced `/api/skills/node/{nodeId}` which never existed in the backend. Migrated to the existing `/api/skills/project/{project_id}` endpoints.

## Consequences (2026-02-18)

- Skills are managed exclusively via the Skills UI and `/api/skills` API endpoints.
- Filesystem-based `SKILL.md` files under `domains/automation/skills/` are no longer auto-synced to DB. Existing DB entries remain functional.
- `engine_setup.py` continues to load DB skills for prompt injection via `_load_prompt_components()`.
- Skill Mining (`skill_mining.py`) remains functional and writes directly to the DB `skills` table.

---

## 追記: Phase 1 完了 (2026-02-20)

orchestration2 正本化方針（[Skill_refactoring.md](../proposals/Skill_refactoring.md)）に基づき、以下を追加で廃止した。

| 廃止コンポーネント | 理由 |
|---|---|
| `/api/skills` router (`api/skills.py`) | DB CRUD 経路を停止し、orchestration2 のみを正本とする |
| `prompt_context_loader.fetch_project_skills()` | DB skill 取得を停止 |
| `project_engine_builder.py` の 7b DB skills ブロック | DB skill を engine に登録する経路を停止 |
| `prompt_context_loader.load_prompt_components()` の `skills_text` 注入 | DB skill content をプロンプトに注入する経路を停止 |
| Frontend Skills ページ (`app/skills/page.tsx`, `SkillEditor.tsx`) | `/api/skills` 依存 UI を廃止案内ページに置換 |
| `integrations/line/SKILL.md` の runtime 参照 | integration は tool 提供のみに責務限定 |

**現状 (Phase 1)**: skill は `orchestration2/config/skills/default_skills.py` の `SkillDef` のみで解決される。DB skills / `/api/skills` / filesystem `SKILL.md` は実行経路から除去済み。

---

## 追記: Phase D 完了 — DB 正本化 (2026-03-02)

提案書 [tool_skill_db_refactor_report.md](../proposals/tool_skill_db_refactor_report.md) に基づき Phase A〜D を実施。

### 変更内容

| 変更 | 詳細 |
|------|------|
| `tool_registry` テーブル新規追加 | 全 tool の metadata を DB に保持。`origin_type(core\|integration\|upload)`, `is_active`, `status`, `version_hash` 等を管理 |
| `skill_registry` 拡張 | `origin_type`, `status`, `is_active`, `version_hash`, `artifact_*` 列を追加 |
| `definition_refresh_service.py` 新規 | core / integration の tool・skill 定義を DB に upsert するサービス。`refresh_core_sync` (sync) と `refresh_all` / `refresh_integrations` (async) を提供 |
| `integrations/loader.py` 拡張 | `load_integration_skills()` を追加。`get_skill_defs()` を持つ integration から `SkillDef` を収集 |
| `project_engine_builder.py` — スキル DB ロード化 | `dynamic_skills` を `SKILL_DEFS` 直接参照から `skill_registry` DB ロードに切り替え。DB 未作成時は `SKILL_DEFS` にフォールバック |
| `project_engine_builder.py` — ツール is_active フィルタ | core tools を `tool_registry.is_active=True` でフィルタして登録。未 seed ユーザーはリクエスト時に lazy seed |
| `tool_reflection.py` — operation append 廃止 | integration tools の `operation` skill への per-request 追記を削除。DB refresh 時に `_update_operation_skill` で DB を正本更新する方式に移行 |
| `/api/definitions` ルーター新規 | `POST /api/definitions/refresh[/core\|/integrations]`, `GET /api/definitions/tools\|skills` を追加 |
| `seed.py` 更新 | `_seed_skills` を `refresh_core_sync` 呼び出しに置き換え。`tool_registry` も user 作成時に seed される |

### 現状 (Phase D)

- **DB が正本**: `skill_registry` と `tool_registry` の `is_active=True` 行が runtime での tool/skill 登録の根拠となる。
- **integration skills**: `get_skill_defs()` を持つ integration (例: `ms_tools` → `ms_office` skill) は refresh 時に DB 登録され、engine に反映される。
- **operation skill**: integration tools の追加は DB refresh 時に確定。per-request の runtime append は廃止。
- **フォールバック**: DB が空（未 seed）の場合は `SKILL_DEFS` / 全 core tools にフォールバックし、backward compatibility を維持。
- **upload (Phase E)**: artifact 保存・validation・activation フローは未実装。`status`, `artifact_*` 列は Phase E で使用予定。
