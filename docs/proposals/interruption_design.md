# 推論システム 中断機能導入レポート

作成日: 2026-02-20  
対象: `core/backend/app/worker.py` / `core/backend/domains/orchestration2` / `core/backend/infrastructure/queue`

---

## 1. 現状の推論システムの概要

### 1-1. 実行の入口
- ユーザーのチャットは `POST /api/agents/project/{project_id}/chat` から `QueueManager.enqueue()` で Redis キューへ投入されます。
- Worker は `QueueManager.dequeue()` でタスクを取得し、`_handle_user_message()` から `project_id` がある場合に `_run_orchestration2()` を実行します。

### 1-2. 推論エンジンの本体
- `_run_orchestration2()` は `create_engine_for_project()` で `AgentEngine` を生成し、`engine.execute_run()` を同期的に await して完了まで待ちます。
- `AgentEngine.execute_run()` は `Orchestrator.run()` を呼び、グラフステップをループ実行します。
- role ステップでは `StepExecutor` から `GeminiEngine.run()` が呼ばれ、内部で「LLM呼び出し → ツール呼び出し → 履歴更新」のマルチターンループを持ちます。

### 1-3. 状態管理の現状
- orchestration2 側の Run は `SQLAlchemyStore` で DB 永続化され、`RunStatus` は `queued/running/waiting_approval/waiting_delegation/completed/failed` を持ちます（`cancelled` は未定義）。
- Queue 側は `QueueManager.cancel_task()` を持ち、Redis 上の `task:{task_id}` を `cancelled` に更新できます。
- ただし Worker／Orchestrator／GeminiEngine の実行ループに「キャンセル状態のポーリング」がないため、**現在の cancel は状態表示のみで、実行停止には連動しません**。

### 1-4. 既存 API のギャップ
- `GET /api/agents/tasks/{task_id}` は状態確認のみで、同ルータ内にある cancel 処理コードは `return` 後にあり実行されません（実質 API 未提供）。
- そのため現時点では、推論実行中のタスクを API から安全に中断する正式経路がありません。

---

## 2. 中断方法の実現方法

以下の 2 層構成が実運用上もっとも安全です。

### 2-1. レイヤーA: Worker タスク中断（即時停止レイヤー）

**目的**: ユーザー操作に対し、できるだけ早く実行を止める。

実装方針:
1. Worker に `self._running_tasks: dict[str, asyncio.Task]` を追加し、`task_id` と実行タスクを紐づける。
2. `cancel_task` API で `task_id` 指定時、Queue 状態を `cancelled` にすると同時に該当 `asyncio.Task.cancel()` を実行する。
3. `_process_task()` / `_run_orchestration2()` で `asyncio.CancelledError` を捕捉し、
   - Queue status を `cancelled`
   - DB へは「中断メッセージ」を保存（必要なら）
   - 後処理（active_task クリア）
   を保証する。

効果:
- Python レベルで待機中の coroutine を打ち切れるため、最短経路で停止可能。

注意点:
- 外部 API 呼び出し（Gemini SDK）や重いツール実行中は、キャンセル伝搬のタイミング次第で数秒〜数十秒遅延が残る可能性あり。

### 2-2. レイヤーB: Orchestration2 Run 中断（整合性レイヤー）

**目的**: 再開性・監査性を保った「正式な中断状態」を Run レベルで記録する。

実装方針:
1. `RunStatus` に `CANCELLED` を追加。
2. `AgentEngine` に `cancel_run(run_id)` を追加し、
   - DB の run status を `cancelled` に更新
   - 必要なら in-flight async task（`_async_tasks`）も cancel。
3. `Orchestrator._run_loop()` 冒頭と各 step 実行後で `run.status == CANCELLED` を確認し、ただちに終了。
4. `GeminiEngine` には `cancel(run_id)` または `is_cancelled(run_id)` 参照を導入し、turn ループごとに中断判定。

効果:
- 「Queue は cancelled だが Run は running」の不整合を解消。
- run/event ベースの可観測性・分析に中断データを取り込める。

### 2-3. 推奨仕様（UX 観点）
- 中断 API は **task_id 基準** と **run_id 基準** の両方を用意。
  - UI は task_id を持つことが多い
  - エンジン内部・運用分析では run_id が有効
- 中断レスポンスは idempotent（既に完了済みでも 200 で状態返却）。
- クライアント表示ステータスを `queued/processing/completed/failed/cancelled` に統一。

---

## 3. 変更スコープ

### 3-1. 必須変更（MVP）
1. **API 層**
   - `core/backend/api/agents.py`
   - `DELETE /api/agents/tasks/{task_id}`（新設 or 既存修正）
2. **Queue 層**
   - `core/backend/infrastructure/queue/manager.py`
   - cancel 後の状態整合（active_task cleanup の保証）
3. **Worker 層**
   - `core/backend/app/worker.py`
   - 実行中 task 管理・`CancelledError` ハンドリング

### 3-2. 推奨変更（Run 整合まで）
4. **Engine モデル/ループ**
   - `core/backend/domains/orchestration2/engine/models/common.py`（`RunStatus.CANCELLED`）
   - `core/backend/domains/orchestration2/engine/orchestration/orchestrator.py`（中断判定）
5. **Engine API**
   - `core/backend/domains/orchestration2/engine/agent_engine.py`（`cancel_run` 追加）
6. **Runtime**
   - `core/backend/domains/orchestration2/engine_runtime/gemini_engine.py`（turn単位の cooperative cancel）
7. **永続化**
   - `core/backend/domains/orchestration2/engine/store/sqlalchemy_store.py`（cancelled 保存互換）

### 3-3. 影響範囲（非機能）
- 監視: cancelled 件数・平均停止時間をメトリクス追加。
- テスト: 非同期キャンセルは flakiness が出やすいため、ユニット + 疑似統合（短い sleep を使う）を分離。
- 運用: タイムアウト停止（自動）とユーザー停止（手動）を区別してログ化。

---

## 4. 導入手順

### Phase 0: 仕様確定（0.5日）
1. task_id/run_id のどちらを主キーに UI 連携するか決定。
2. 「中断時にチャットへメッセージを残すか」を決定。
3. 完了済みタスク中断時のレスポンス仕様（idempotent）を確定。

### Phase 1: MVP（1〜2日）
1. API に cancel エンドポイントを実装。
2. Worker に実行中タスク管理を追加し `Task.cancel()` を有効化。
3. Queue status と active_task cleanup を統一。
4. 手動 E2E 確認（長文推論中に cancel → 数秒以内に cancelled 反映）。

**完了条件**
- 実行中タスクをユーザー操作で停止できる。
- 再試行で新規タスクが正常起動する（ゾンビ実行なし）。

### Phase 2: Run 整合（2〜3日）
1. `RunStatus.CANCELLED` 導入。
2. `AgentEngine.cancel_run()` 実装。
3. Orchestrator/GeminiEngine の cooperative cancel チェック追加。
4. cancelled run の保存・取得・表示を API へ反映。

**完了条件**
- Queue と Run の両方で cancelled が一致。
- 中断後に監査ログから停止ポイントが追える。

### Phase 3: 品質強化（1〜2日）
1. キャンセル遅延計測（API 受付〜実停止まで）。
2. 高頻度 cancel の耐久試験（連打・同時実行）。
3. メトリクス/アラート設定（cancel fail, stuck running）。

---

## 5. まとめ

- 現在の推論基盤は orchestration2 + GeminiEngine で構成され、DB 永続化は進んでいます。
- 一方で「中断」は Queue 状態更新に留まり、実行停止の制御が未接続です。
- 導入は **MVP（Worker cancel）→ Run 整合（orchestration2 cancel）** の段階実装が最小リスクです。
- この順序なら、短期でユーザー体験を改善しつつ、中長期で監査性・再開性を担保できます。
