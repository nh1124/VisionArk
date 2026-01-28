---
name: "Meeting Orchestrator"
description: "カレンダー予定の管理、会議の事前準備、および議事録のタスク化を行うスキル"
id: "meeting-orchestrator-v1"
tools: ["google_calendar", "search_knowledge", "save_artifact", "create_task"]
---

# Meeting Orchestrator Procedure

会議や打ち合わせの効率を最大化するために、以下の手順を自動化してください：

1. **予定の把握**:
   - `google_calendar` の `list_events` 的なツール（利用可能な場合）を用いて、直近の予定を確認します。
   - 会議のタイトルや参加者、概要から重要度を判断します。

2. **事前リサーチ**:
   - 会議のトピックに関連する過去の経緯を `search_knowledge` で検索します。
   - 関連するアーティファクトを確認し、必要な前提情報を整理します。

3. **アジェンダの提案**:
   - 会議前に、論点整理やアジェンダを `save_artifact` で作成し、ユーザーに共有します。

4. **議事録と決定事項の整理**:
   - 会議終了後（または対話コンテキストに基づき）、決定事項、保留事項、宿題（Next Actions）を整理します。
   - `save_artifact` で「議事録」を作成します。

5. **アクションアイテムのタスク化**:
   - 宿題事項を `create_task` でLBSに登録します。
   - 適切な期日や担当ノードへの振り分け（連携ツールがある場合）を提案してください。
