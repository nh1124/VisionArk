---
name: "Daily Pilot"
description: "毎朝の業務開始前に当日の負荷状況を把握し、一日のスケジュールを最適化するスキル"
id: "daily-pilot-v1"
tools: ["get_load_on_day", "list_tasks", "request_coordination"]
tool_policy:
  allowlist:
    - get_load_on_day
    - get_load_in_period
    - list_tasks
    - request_coordination
  denylist:
    - delete_task
  retry:
    max_attempts: 2
    fallback_tools:
      get_load_on_day:
        - get_load_in_period
intents:
  - daily_planning
priority: 10
conflicts_with:
  - workflow-engineer
---

# Daily Pilot Procedure

ユーザーが一日をスムーズに開始できるよう、毎朝（またはリクエスト時に）以下のナビゲーションを行ってください：

1. **認知負荷の確認**:
   - `get_load_on_day` を用いて、当日の予定タスクによる推定負荷を確認します。
   - 負荷が閾値を超えている（過密状態）かどうかを判定します。

2. **優先タスクの抽出**:
   - `list_tasks` で当日期限のタスク、および期限を過ぎている重要なタスクを抽出します。
   - ユーザーの集中力が必要な「重い」タスクを特定します。

3. **スケジュールの最適化提案**:
   - 負荷状況に基づき、実行順序の入れ替えや、いくつかのタスクの延期を提案します。
   - 隙間時間で行える「軽い」タスクの配分をアドバイスします。

4. **エージェント間調整（オプション）**:
   - 負荷が高すぎる場合、`request_coordination` を用いて他のノード（サブエージェント）に一部の作業を依頼することを提案します。

5. **デイリー・ブリーフィングの出力**:
   - 「今日フォーカスすべきこと」と「現在のステータス」を簡潔にまとめて出力します。
