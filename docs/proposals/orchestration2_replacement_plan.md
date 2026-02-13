# Orchestration2 Connection & Replacement Plan

This report outlines the strategy for connecting the new `orchestration2` system to the existing VisionArk backend, replacing the legacy `orchestration` (v1/v4) components.

## 1. 置き換え対象箇所の把握 (Identification of Replacement Points)

### A. API入口 (API Entry Point)
- **現状**: `/api/agents/project/{project_id}/chat` が `QueueManager.enqueue` を呼び、`TaskType.USER_MESSAGE` を発行。
- **課題**: `TaskType.USER_MESSAGE` は既存の `ProjectNode` に直結している。

### B. Worker / Queue タスク語彙 (Task Vocabulary)
- **現状**: `TaskType` は `USER_MESSAGE`, `NODE_EXECUTION`, `AI_ROUTING`, `APPROVAL_EXECUTION` 等。
- **課題**: これらは `ProjectNode` や `NodeFactory` 前提のロジックに紐付いている。

### C. Node実行ハブ (Node Execution Hub)
- **現状**: `ProjectNode` が `chat_with_tools` を呼び、`ReasoningEngine` がループを回す。
- **課題**: 新システムでは `Orchestrator` + `StepExecutor` がこの役割を担う。

### D. Tool / Skill 制約ロジック (Skill/Tool Constraints)
- **現状**: `SkillService` が `NodeSkill` テーブルを参照し、`tool_policy` をマージ。
- **課題**: 新システムでは `AgentDef` が `Skills` を持ち、`SkillDef` が `Tools` を定義する。

### E. Approvalフロー (Approval Flow)
- **現状**: `ApprovalService` が `APPROVAL_EXECUTION` タスクを発行し、Worker が実行。
- **課題**: 新システムでは `RunRecord` に `pending_approval_ids` を持ち、`approval_request` で再開する。

### F. 会話履歴・観測性 (History & Observability)
- **現状**: `ChatMessage`, `ChatSubMessage`, `ToolUsage` テーブル。
- **課題**: `run_id`, `step_id` などの `orchestration2` 特有のメタ情報が不足している。

---

## 2. どのように置き換えるか (Replacement Strategy)

### A & B. 統合入口とタスク追加
1.  **New Task Type**: `TaskType.RUN_EXECUTION` を追加。
2.  **API Adapter**: `chat_with_project` 内部で、`project_id` に紐付いた `agent_id` を解決し、`RUN_EXECUTION` として Enqueue する。
3.  **互換性**: レスポンスの `task_id` は `run_id` と同等として扱う（薄い Wrapper インターフェース）。

### C. Node実行の置換
1.  `Worker._process_task` に `RUN_EXECUTION` のハンドラを追加。
2.  ハンドラ内で `AgentEngine.execute_run` を呼び出す。
3.  `orchestration2` の `Store` 実装として、既存の `ChatMessage` / `ChatSubMessage` に書き込む `SQLAlchemyStore` を開発する。

### D. Skill / Tool ロジックの移行
1.  `AgentDef` 構築時に、既存の `nodes` 及び `node_skills` から情報をインポートするアダプターを作成。
2.  中期的には `agent_skills` テーブルへのマイグレーションを実施。

### E. Approvalフローの刷新
1.  `ApprovalRequest` テーブルに `run_id` カラムを追加。
2.  既存の Approval API を `AgentEngine.approval_request` を呼ぶように修正。
3.  `RunRecord` の中断・再開機能を `Store` を通じて永続化。

### F. 履歴テーブルの拡張
1.  `ChatSubMessage` に `run_id`, `step_id` を追加。
2.  `ToolUsage` に `event_type` (call/result) を追記できるよう拡張。
3.  `ReasoningEngine` の `SubMessage` 資産をそのまま `orchestration2` の `OrchestrationEvent` としてマッピング。

---

## 3. Worker 実装に必要な追加情報 (Additional Info for Agent Implementation)

エージェントが自律的に置き換え処理を行うために、以下の情報/コンポーネントを準備する必要があります。

1.  **Mapping Layer**: `project_id` (Legacy) と `agent_id` (v2) のマッピング定義。
    - 最初は `Project.id == Node.id (node_type='PROJECT')` を `agent_id` として扱う。
2.  **SQLAlchemyStore**: `orchestration2.interfaces.Store` の具象クラス。
    - これが既存 DB テーブルへの Bridge となる。
3.  **Migration Script**: `node_skills` から `AgentDef/SkillDef` 形式へデータを変換するスクリプト。
4.  **Compatibility Layer**: `ReasoningEngine` の出力を `RunResponse` に変換する、またはその逆のユーティリティ。

---

作成場所: `@docs/proposals/orchestration2_replacement_plan.md`
