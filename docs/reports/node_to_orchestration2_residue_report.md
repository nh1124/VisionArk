# Node → orchestration2 移行 残滓レポート

作成日: 2026-02-13

## 前提
- DB はリセット可能（破壊的なスキーマ整理・命名整理が可能）
- 目標は、**保守性**と**engine の独立性維持**（VisionArk 固有要素は adapter 層へ閉じ込める）

---

## 1. 残滓の所在（Where）

## A. DB モデル層: `nodes` が中核概念として残っている
- `Project` が `nodes` リレーションを強く持つ。`Node` モデル自体に `PROJECT/MEMBER/SYSTEM` の分類が残る。
- `NodeSkill` が `node_id` に直接ぶら下がっており、スキル付与の主語が「project」ではなく「node」になっている。

**観測ポイント**
- `core/backend/shared/database.py` の `NodeType` / `Node` / `NodeSkill`。

**影響**
- orchestration2 の「graph + role + skill」モデルへ移行する際、Node 依存のデータモデルが境界を曖昧化。

---

## B. API 層: Project API 内部で Node を前提に扱っている
- `/api/agents/project/*` 系で、Project 作成時に main Node を必ず作る。
- Prompt 取得・更新 API が「main project Node」を主語にしている。
- 返却 payload に `node_id` が残っている。

**観測ポイント**
- `core/backend/api/agents.py` の `create_project`, `create_project_from_prompt`, `get/update_project_system_prompt`, `branch`。

**影響**
- クライアント契約（API contract）まで Node 依存が波及。
- 将来、engine 側の role/profile ストアに置き換える際に後方互換コストが高くなる。

---

## C. RAG API: 旧 Node 前提の検証ロジックが残存（かつ不整合）
- Project 存在確認で `select(Node.id).filter(Node.user_id == ... Node.id == project_id)` を使用。
- しかし本ファイルでは `Node` / `select` の import がなく、コード整合が崩れている。

**観測ポイント**
- `core/backend/api/rag.py` 全体の project existence check。

**影響**
- Node 前提ロジックが残るだけでなく、保守時のバグ源。
- Project 基準に統一されていないため、ドメイン境界がぶれる。

---

## D. Queue/Worker 境界: node-to-node 実行経路の残骸
- QueueManager に `enqueue_node_task(..., task_type=TaskType.NODE_EXECUTION)` が残る。
- 一方 `TaskType` enum には `NODE_EXECUTION` がなく、現行 worker の task 分岐とも噛み合わない。
- worker 内にも「Node usage」コメントが残る。

**観測ポイント**
- `core/backend/infrastructure/queue/manager.py`
- `core/backend/shared/database.py` の `TaskType`
- `core/backend/app/worker.py`

**影響**
- 使われるとランタイム不整合の可能性。
- orchestration2 の実行単位（run/agent）と queue タスク型の整合が取りにくい。

---

## E. Integration 層（LINE）: Project 初期化が Node 作成前提
- LINE の初回連携時に Project と同時に Orchestrator Node を作成。
- コメントにも `ProjectNode` という語が残る。

**観測ポイント**
- `integrations/line/api.py`

**影響**
- 外部連携が内部実装（Node）に直結。
- 将来のストア差し替え時に integration 修正範囲が広がる。

---

## F. ドキュメント/命名: Node 中心説明が混在
- README が Project-Node architecture を前面に説明。
- 一方、core ドキュメントでは orchestration2 が node-based orchestration の置換と明記。

**観測ポイント**
- `README.md`
- `docs/core/orchestration2_engine.md`

**影響**
- 新規開発者がどちらを正とすべきか迷う。
- 実装・設計・運用の共通言語がずれる。

---

## 2. orchestration2 適応のための変更提案（How）

## 方針（重要）
1. **engine はそのまま独立維持**（既存方針を厳守）
2. VisionArk 側は「Node 残滓吸収」ではなく、**project + orchestration2 + agents/skills** を主語にした新アーキテクチャへ**完全移行**する
3. API 契約は**互換期間を置かず一括移行**する（開発/試験段階のため、破壊的変更を許容）
4. 新アーキテクチャに合わない機能は **同時に削除** する（失敗時は git rollback 前提）

---

## 提案 1: DB 主語を `project agent profile` へ再定義

### 変更案
- `nodes` を廃止または縮退し、以下へ置換:
  - `project_agents`（project の実行プロファイル）
  - `project_skills`（project 単位 skill 紐付け）
- `node_type`, `parent_node_id` のような木構造概念を、必要最小限のみ残す（member が必要なら `project_members` に分離）。

### 期待効果
- データモデルが orchestration2 の「project context + role/skill」へ自然に一致。
- DB が engine モデルを汚染しない。

---

## 提案 2: API を `project_id`/`agent_key` 契約に一括再定義（後方互換なし）

### 変更案
- `/api/agents/project/create*` の response から `node_id` を削除（即時）。
- Prompt API は `ProjectPrompt`（または `ProjectProfile`）に対する CRUD に変更。
- `/api/skills/node/{node_id}` は `/api/skills/project/{project_id}` へ改名。
- 旧 Node 契約 endpoint は alias も残さず削除。

### 期待効果
- フロント・外部連携の契約が Node 実装から独立。
- 内部実装を交換しても API 安定性を保ちやすい。

---

## 提案 3: Queue タスク型を orchestration2 実行単位に合わせる

### 変更案
- `TaskType` を `USER_MESSAGE`, `SYSTEM_TASK`, `ORCHESTRATION_RUN` 等へ整理。
- `enqueue_node_task` を削除し、`enqueue_orchestration_run` に一本化。
- context のキーを `node_id` から `agent_id` / `project_id` / `run_id` に統一。

### 期待効果
- Worker 分岐と queue payload の整合が取れる。
- 監視/デバッグも run 単位で追跡しやすい。

---

## 提案 4: Integration には Provisioning Interface を挟む

### 変更案
- LINE など外部連携から直接 `Node(...)` を作るコードを削除。
- `ProjectProvisioningService`（例）を作り、
  - `create_project_workspace(...)`
  - `initialize_project_profile(...)`
  - `bind_external_identity(...)`
  を提供。

### 期待効果
- integration が内部スキーマに依存しない。
- DB リセット後の再構築・再実装が容易。

---

## 提案 5: RAG の project existence check を Project 基準に統一

### 変更案
- すべての RAG endpoint で `Project` テーブル確認へ統一。
- 共通 dependency（`ensure_project_access(identity, project_id, db)`）化して重複除去。

### 期待効果
- Node 前提の消滅。
- API の信頼性向上（不整合 import 問題の根絶）。

---

## 提案 6: 命名・ドキュメントを orchestration2 基準へ揃える

### 変更案
- README の「Project-Node architecture」を「Project + orchestration2 graph architecture」へ更新。
- docs の用語集を追加し、`Node(legacy)` / `ProjectProfile(current)` の対応表を明示。

### 期待効果
- 実装と文書の差分を縮小。
- チーム内の設計判断が速くなる。

---

## 3. DB リセット前提の推奨実行順

1. **削除対象の明確化**（Node 契約 endpoint / Node 専用 task / 不要 feature を先に列挙）
2. **DB スキーマ再定義**（`nodes` 依存構造を廃止し、project+agent/profile+skills へ）
3. **API 一括更新**（`project_id`/`agent_key` 契約へ統一、旧 endpoint は削除）
4. **Worker/Queue 一括更新**（orchestration2 run 主語へ変更）
5. **Integration 一括更新**（ProvisioningService 経由のみに制限）
6. **README・運用手順更新**
7. **失敗時は git で即ロールバックして再試行**

---

## 4. 一括移行時に同時削除すべき負債機能

- `core/backend/api/rag.py` の Node 前提チェック（`select(Node.id)...`）
- `enqueue_node_task` と Node-to-Node を前提にした queue API
- `agents.py` の `node_id` 返却
- `skills.py` の `/api/skills/node/{node_id}` 契約
- integration から直接 `Node(...)` を作る初期化コード

この削除を同時実施することで、移行後に Node 由来の分岐・例外処理・互換コードを残さず、保守負債を最小化できる。
