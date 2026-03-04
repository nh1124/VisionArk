# Run Center 調査レポート

## 1. 現在の Run Center の実装と仕様

### 1-1. 実装の配置
- Run Center UI は **Native Desktop 専用**で、`core/native/desktop/src-ui/components/RunCenterView.tsx` に実装されている。
- Web フロント (`core/frontend`) 側は依然として `Job Center`（`/api/jobs` ベース）中心で、Run Center として統合された導線はない。

### 1-2. 現在のデータモデル（Backend）
- Run Center は以下3層モデルで構成される。
  - `agent_runs`（Run）
  - `run_executions`（実行イベント）
  - `run_approvals`（承認）
- 状態遷移は概ね以下。
  - Run: `queued | running | waiting_approval | completed | failed | canceled`
  - Execution: `pending | running | waiting_approval | succeeded | failed | rejected`

### 1-3. 現在の API 仕様
- `/api/runs` 配下に Run/Execution/Approval API がある。
  - Run 一覧・作成・更新
  - 実行追加・状態更新
  - 承認・拒否
  - Daemon 用の `pull` / `claim`
- Daemon は `/api/runs/pull` で `pending` execution を取得し、`claim` 後にローカルツール実行する。

### 1-4. 現在の UI 仕様（Native Desktop）
- 左: Run一覧（all/active/done）
- 中央: 選択 Run の execution タイムライン
- 右: 承認キュー（選択Runまたは全Run）
- 新規 Run 作成、承認/拒否操作は可能。
- 一方で「Run の停止/キャンセル」操作は UI 上に用意されていない。

### 1-5. 文言/ロケール
- UI は英語ラベル主体で作られているが、同一画面内に日本語文言（例: 承認ボタン、空状態メッセージ、日時フォーマット `ja-JP`）が混在している。
- そのため、英語デフォルト期待に対して UI が不統一になっている。

---

## 2. 問題点（今回の指摘との対応）

### 2-1. 「native連携でのみ機能し、通常agent動作は機能しない」
- 現実装では Run Center の run/execution は、Native daemon の `pull/claim/patch` フローで進む設計。
- 通常の agent 実行（chat/task 実行）は別系統（Web 側の task/cancel、orchestration 系）で動いており、Run Center 側の run に自動投影されない。
- 結果、Run Center は「Native 実行の可視化」には強いが、「通常 agent 実行の統合運用画面」にはなっていない。

### 2-2. 「なぜか日本語（englishがデフォルト）」
- RunCenterView 内で英語・日本語が混在し、日時フォーマットも `ja-JP` 固定。
- i18n 層を介さず文言直書きのため、デフォルト言語ポリシーと UI の実際が乖離している。

### 2-3. 「操作できるわけでもない（裏で動くものが見えるだけ）」
- 承認/拒否はできるが、運用上重要な以下操作が不足。
  - Run の停止/キャンセル
  - Execution の再試行
  - 強制失敗/スキップ
  - デバイス再ルーティング
- 監視中心 UI になっており、Run Center の「運用ハブ」としての実効性が不足。

### 2-4. アーキテクチャ上の分断
- Web 側には旧 Job Center が残存し、Native 側には Run Center が存在する二重運用。
- 同じ「実行管理」の概念が UI/データで分断され、ユーザー視点で意味が重複・不統一。

---

## 3. 改善案

### 3-1. 方針
Run Center を「Native監視画面」から「全 agent 実行の統合オペレーションセンター」に拡張する。

### 3-2. 必須改善（短期）
1. **言語統一（英語デフォルト）**
   - RunCenterView の文言を i18n キー化。
   - `toLocaleString("ja-JP")` をユーザー設定ロケール準拠へ変更。
2. **停止操作の追加**
   - Run ヘッダに `Stop Run` を追加（`PATCH /api/runs/{id}` で `canceled`）。
   - 実行中 execution がある場合の協調停止（daemon 側ポーリングで中断検知）を実装。
3. **実行制御の追加**
   - execution 単位の `retry`（新規 execution 生成または状態再投入）
   - `reject` に加え `skip` / `fail-fast` の運用アクションを追加。

### 3-3. 中期改善（統合）
1. **通常 agent 実行を Run Center に取り込む**
   - chat/task/orchestration 実行開始時に `agent_runs` へ run を作成。
   - tool call / long-running / approval を `run_executions` として統一記録。
2. **Web と Native の Run Center 統合**
   - Web でも Run Center を正式画面化。
   - 旧 Job Center は段階的に互換表示→廃止。
3. **イベント駆動更新**
   - 5秒ポーリング中心から WS/SSE へ移行し即時反映。

### 3-4. 長期改善（運用性）
- Run の SLA 指標（経過時間、停滞検知、失敗率）
- 監査トレイル（誰が承認/停止したか）
- マルチデバイス環境での再割当（reroute）

---

## 4. 変更スコープ（実装観点）

### 4-1. Backend
- `core/backend/api/native.py`
  - run cancel / execution retry 系 endpoint 追加
  - 通常 agent 実行から run へイベント連携する入口追加
- `core/backend/domains/native/run_service.py`
  - キャンセル時の一括状態遷移
  - retry / reroute など運用アクション追加
- `core/backend/shared/database.py`
  - 必要に応じて `run_executions` に制御用カラム追加（retry_of, canceled_by, cancel_reason など）

### 4-2. Native Daemon / Bridge
- `core/native/daemon/src/job_runner.rs`
  - run canceled 検知で協調停止
  - retry/reroute に対応した pull/claim ロジック拡張
- `core/native/bridge/api.ts`
  - cancel/retry/reroute API クライアント追加

### 4-3. UI（Native Desktop）
- `core/native/desktop/src-ui/components/RunCenterView.tsx`
  - i18n 対応
  - Stop/Retry/Reroute 操作UI追加
  - 読み取り専用ビューから運用操作ビューへ拡張

### 4-4. UI（Web）
- `core/frontend/app/jobs/page.tsx`（旧）
  - 段階的に縮退
- 新規 Run Center 画面（または既存画面置換）
  - `/api/runs` を正系 API として統一

---

## 5. 優先度付き実行プラン（提案）
1. **P0**: RunCenterView の英語統一 + locale設定化 + Stop Run 追加
2. **P1**: Backend/Daemon の協調停止・retry 実装
3. **P2**: 通常 agent 実行の run_executions 連携（観測統一）
4. **P3**: Web Job Center 廃止、Run Center 一本化

---

## 6. 要約
- 現在の Run Center は設計としては run/execution/approval の統合モデルを持つが、実態として **Native 実行専用の運用UI** に留まっている。
- 問題の本質は「対象範囲の狭さ（通常 agent 非連携）」「UI言語不統一」「運用操作不足（停止等なし）」。
- 改善は、**英語/i18n整備 + 停止/再試行操作 + 通常agent実行の run モデル統合** を段階実施するのが最短で効果が高い。

---

## 7. 追加確認: 「Run」は agent run か、daemon 固有 run か

### 7-1. 結論
- **命名上は agent run だが、現行運用上はほぼ daemon 実行キューの親コンテナとして使われている**。
- つまり懸念どおり、現在の Run Center の run は「通常 agent 実行（chat/orchestration）の run 記録」とは分離されている。

### 7-2. 仕様根拠
1. `/api/runs` は Native API ルータ (`core/backend/api/native.py`) に実装されており、`create_run` は任意 `project_id/agent_id/session_id` を受けるだけで、orchestration 実行開始と自動連動しない。
2. daemon 側は `/api/runs/pull` で `RunExecution(status=pending)` を取得し、`claim`→`PATCH status` で進行管理している。Run 自体は「execution 群の親」として扱われる。
3. 通常 agent 側の停止系は `DELETE /api/agents/tasks/{task_id}` から `orchestration_runs` を `cancel_run` する別経路で実装されており、`agent_runs` テーブルとは別系統。

### 7-3. 実務上の解釈
- 現在の `agent_runs` は、実質的に「Native daemon に処理させる execution を束ねる Run」。
- 「ユーザーが chat で起動した agent の実行履歴を統一的に見る」用途には、現状そのままでは使えない。
- 本来意図（agent run 管理）へ戻すには、chat/task/orchestration 実行イベントを `agent_runs/run_executions` に写像する統合作業が必要。
