# Proposal: Visibility Recovery (Thinking Process & Tool History)

## 1. 概要 (Overview)

**目的**: UI可視性の復旧。
現在、Backendの思考プロセスやツール実行履歴がFrontendで適切に表示されていない状況を改善する。
「Thinking Process + Tool Usage」の可視化を回復し、ユーザーがAIの挙動を理解できるようにする。

## 2. 現状の課題 (Current Issues)

-   **履歴の欠落**: DB/API/Frontendには `submessage` を表示する枠組みがあるが、Workerでの保存時に履歴が欠落している。
-   **保存ロジックの問題**: Workerの保存処理が `run_response.message.submessages` のみに依存しており、実行途中（`run.history`）で発生したTOOL_CALL/TOOL_RESULTが含まれにくい。
-   **ToolUsageの未保存**: `ToolUsage` レコードが保存されていないため、APIが返す `sub.tool_calls` が空になりやすい。

## 3. 提案内容 (Proposed Changes)

### 推奨改修

1.  **保存ロジックの変更**:
    -   Worker (`core/backend/app/worker.py`) の保存処理を修正し、`run_response.message` だけでなく、**Run全履歴**（またはこのターンで追加された全メッセージ）を保存対象とする。
2.  **完全な情報の永続化**:
    -   `ChatSubMessage` の `kind`, `run_id`, `step_id`, `meta_payload` を欠落なく保存する。
    -   `sub.tool_call` 情報から `ToolUsage` レコードも保存し、APIレスポンスの整合性をとる。
3.  **API/Frontend調整**:
    -   履歴APIで `tool_call` 本体（name, args, result等）を適切に返却する。

### 期待効果

-   Frontendの既存実装 (`sub_messages` 描画) を大きく変えることなく、データ側の修正だけで Thinking Process / Tool execution の表示が復活する見込み。

## 4. 変更スコープ (Scope of Changes)

-   `core/backend/app/worker.py` (保存ロジックの主改修)
-   `core/backend/api/agents.py` (Historyレスポンス調整)
-   `core/backend/shared/database.py` (DB操作メソッド確認)
-   `core/frontend/app/projects/[projectId]/page.tsx` (表示確認)
-   `core/frontend/components/MessageWithAttachments.tsx`

## 5. 改修難易度 (Difficulty & Priority)

-   **難易度**: 中〜高
-   **優先度**: 最優先 (最初に実施推奨)

保存経路での情報欠落が主因であり、Workerの保存ロジック見直しが必要。
DB保存形式・API返却・Frontend描画の3層の整合性を取る必要があり、テスト工数が比較的高くなる。
まず観測性（Observability）を回復させるため、この改修から着手することを推奨する。
