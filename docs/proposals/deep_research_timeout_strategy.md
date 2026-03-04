# Deep Research timeout対策レポート（Long-running Tool基盤 前提）

## 1. 現状の実装

`deep_research` は `core/backend/domains/orchestration2/tools/library/search.py` の `DeepResearchTool` に実装されています。

- Gemini deep (`speed=deep`) は Interactions API を `background=True` で開始後、同一リクエスト内でポーリングを継続します。
- ポーリング設定は固定値です。
  - `_GEMINI_POLL_INTERVAL_SEC = 10`
  - `_GEMINI_POLL_TIMEOUT_SEC = 1800`（30分）
- 30分以内に `completed` にならない場合、`fail(...)` でタイムアウト失敗を返します。
- `interaction_id` の永続化、ジョブ状態テーブル、後追いで結果を取得するAPIは現時点で存在しません。

## 2. 今回の課題

現状は「同期リクエスト中に完了できること」を前提にしているため、以下の課題が発生します。

1. **長時間ジョブでtimeoutが頻発**
   - 1800秒超過で必ず失敗し、再試行ループを誘発しやすい。
2. **完了可能な処理を取りこぼす**
   - 外部では処理が進行中でも、アプリ側は失敗として扱ってしまう。
3. **運用上の可観測性不足**
   - `interaction_id` を軸に状態追跡する仕組みがなく、失敗原因分析が難しい。
4. **再利用不能な実装**
   - deep_research 専用の場当たり対応だと、将来の長時間ツールへ横展開しづらい。

## 3. 方針（Phase1 + Phase2 + Long-running Tool基盤）

本レポートでは、deep_research個別対応ではなく、**長時間ツール全般を扱える共通基盤**を設計します。

### Phase1（即効）
- `deep_research` に `timeout_sec` を追加し、同期待機時間を可変化
- サーバ側バリデーションで範囲制限（例: `60 <= timeout_sec <= 3600`）

### Phase2（本命）
- timeout超過時に失敗せず、ジョブを永続化してバックグラウンド継続
- 進行状況・結果を `job_id` 経由で取得可能にする

### Long-running Tool基盤（将来含む）
- deep_research だけでなく、将来的な重いツールも同じAPI/状態管理で実行
- Tool実装は「ジョブ投入」と「ステータス参照」を呼ぶだけに単純化

---

## 4. 詳細な実装方法（DB基盤〜Tool向け基盤API）

## 4.1 アーキテクチャ概要

```text
Tool (deep_research / others)
  └─ LongRunningJobService.create_job(...)
      ├─ DB: long_running_jobs (queued)
      ├─ Queue: enqueue(job_id)
      └─ return job_id

Worker (JobExecutor)
  └─ dequeue(job_id)
      ├─ DB status: queued -> running
      ├─ Provider adapter (Gemini/OpenAI/...)
      ├─ progress/result/error 更新
      └─ DB status: completed/failed/expired/cancelled

Tool / API
  └─ LongRunningJobService.get_status(job_id)
      └─ status/result_path/error/progress を返却
```

---

## 4.2 DB設計

### 4.2.1 `long_running_jobs`（主テーブル）

推奨カラム:
- `id` (UUID, PK)
- `user_id` (必須), `project_id` (任意), `session_id` (任意)
- `tool_name`（例: `deep_research`）
- `job_kind`（例: `research.deep`）
- `provider`（`gemini|openai|anthropic|...`）
- `model`
- `input_payload` (JSONB)
- `status`（`queued|running|completed|failed|expired|cancelled`）
- `progress` (JSONB)（任意。`percent`, `stage`, `last_message`）
- `result_payload` (JSONB)
- `result_path` (TEXT, 必須)
- `error_code`, `error_message`
- `external_ref`（Geminiなら `interaction_id`）
- `sync_timeout_sec`
- `created_at`, `started_at`, `updated_at`, `completed_at`, `expires_at`

インデックス:
- `(user_id, created_at DESC)`
- `(status, updated_at)`
- `(tool_name, status)`
- `(external_ref)`

### 4.2.2 `long_running_job_events`（イベント履歴）

推奨カラム:
- `id` (UUID, PK)
- `job_id` (FK)
- `event_type`（`created|queued|running|progress|completed|failed|cancelled|expired`）
- `event_payload` (JSONB)
- `created_at`

用途:
- 監査ログ
- デバッグ
- UIのタイムライン表示

### 4.2.3 `long_running_job_locks`（任意）

分散ロック用途。複数ワーカー時の二重処理防止。
- `job_id` (PK)
- `owner_id`（worker識別子）
- `locked_at`, `expires_at`

---

## 4.3 Tool向け基盤API設計（内部サービス）

`domains/long_running/` を新設し、以下インターフェースを提供します。

### 4.3.1 `LongRunningJobService`

- `create_job(ctx, tool_name, job_kind, payload, options) -> JobCreateResult`
  - DBに `queued` 登録
  - Queueへ `job_id` 投入
- `get_job(job_id, user_id) -> JobRecord`
- `get_status(job_id, user_id) -> JobStatusResult`
- `list_jobs(user_id, tool_name?, status?, limit?, cursor?)`
- `cancel_job(job_id, user_id) -> CancelResult`
- `append_event(job_id, event_type, payload)`
- `update_progress(job_id, progress)`
- `complete_job(job_id, result_payload, result_path?)`
- `fail_job(job_id, error_code, error_message)`

### 4.3.2 `LongRunningJobExecutor`（ワーカー側）

- `register_handler(job_kind, handler)`
- `execute(job_id)`
  - `queued -> running`
  - handler実行
  - terminal stateへ更新

### 4.3.3 `JobHandler` プロトコル

```python
class JobHandler(Protocol):
    async def run(self, job: JobRecord, svc: LongRunningJobService) -> None: ...
```

deep_research は provider 固有名ではなく、まず `DeepResearchJobHandler`（共通）として実装し、内部で provider adapter に委譲します。

---

## 4.4 deep_research の具体実装

## 4.4.1 Tool I/F

`deep_research` に追加:
- `timeout_sec`（任意）
- `async_on_timeout`（任意, default=true）
- `result_path`（任意）

戻り値:
- 同期完了: 従来どおり結果本文
- timeout時:
  - `status=running`
  - `job_id`
  - `result_path`（将来保存先）
  - `message="Research continues in background"`

## 4.4.2 実行手順

1. Toolが `LongRunningJobService.create_job(...)` を呼び job作成
2. 同期枠で `timeout_sec` まで短時間ポーリング（任意）
3. 完了すれば即返却
4. 超過したら `running` 返却（失敗にしない）
5. ワーカーが `job_kind=research.deep` を処理
   - Gemini `interactions.create(... background=True)`
   - `external_ref=interaction_id` を保存
   - `interactions.get` で追跡
   - completed時に `result_path` へ保存
6. `deep_research_status(job_id)` で後追い取得

### 4.4.3 ハンドラー命名・構成（汎用対応）

今回の対応は Gemini 専用ではなく、provider 非依存で設計します。

推奨命名:
- `DeepResearchJobHandler`（job_kind=`research.deep` の共通ハンドラー）
- `DeepResearchProviderAdapter`（抽象）
  - `GeminiDeepResearchAdapter`
  - `OpenAIDeepResearchAdapter`
  - `AnthropicResearchAdapter`

責務分離:
- Handler: ジョブ状態遷移、result_path 書き込み、再試行制御
- Adapter: provider API 呼び出し、external_ref 管理、レスポンス正規化

この構成により、`job_kind` は固定 (`research.deep`) のまま provider 追加が可能です。

---

## 4.5 Tool/API公開設計

### 4.5.1 Tool API（LLMが使う）

- `deep_research(...)`
- `deep_research_status(job_id)`
- `deep_research_cancel(job_id)`（任意）

### 4.5.2 Backend REST API（UI/外部連携向け）

- `POST /api/long-running-jobs`
- `GET /api/long-running-jobs/{job_id}`
- `GET /api/long-running-jobs?tool_name=&status=`
- `POST /api/long-running-jobs/{job_id}/cancel`
- `GET /api/long-running-jobs/{job_id}/events`

レスポンス例（status）:
```json
{
  "job_id": "uuid",
  "tool_name": "deep_research",
  "status": "running",
  "progress": {"stage": "polling", "elapsed_sec": 1420},
  "result_path": "artifacts/research/job-uuid.md",
  "error_message": null,
  "updated_at": "2026-03-03T12:00:00Z"
}
```

---

## 4.6 Queue / Worker統合方式（AESキューは原則分離）

ご懸念の通り、AESキューは本来「定期実行（cron / system scheduled task）」用途です。
long-running tool の状態追跡ループは性質が異なるため、**論理・運用の両面で分離**を推奨します。

### 推奨方針
- **方式A（推奨）: 専用キュー + 専用エグゼキュータ**
  - 例: `long_running_jobs` キュー
  - Worker内で `LongRunningJobExecutor` を別ループとして起動
  - AES Dispatcher とは責務を混在させない
- **方式B（暫定）: 同一QueueManagerを使うが task_type を厳密分離**
  - 例: `TaskType.LONG_RUNNING_JOB`
  - ただし監視メトリクス・同時実行制御・SLOは AES と別管理

### 分離する理由
1. **責務分離**
   - AES: 「時刻到来で起動するタスク」
   - Long-running tool: 「状態遷移を追跡し完了回収するタスク」
2. **運用分離**
   - リトライ戦略、タイムアウト、並列数、監視指標が異なる
3. **障害分離**
   - deep_research滞留がAES定期処理に波及しない
4. **拡張性**
   - 将来、画像生成・大規模変換などの長時間toolを同基盤に追加しやすい

### 実装メモ
- Queue payload は最小化: `{ "job_id": "...", "job_kind": "..." }`
- 進捗・状態は必ず DB を正として更新
- ワーカー起動時に `LongRunningJobExecutor.run_forever()` を独立起動
- 同時実行数は `max_long_running_concurrency` で別枠設定

---

## 4.7 状態遷移定義

```text
queued -> running -> completed
                 └-> failed
                 └-> expired
queued/running -> cancelled
```

遷移ルール:
- `cancelled` はユーザー要求または管理操作
- `expired` は最大実行時間超過
- terminal state (`completed|failed|expired|cancelled`) は不変

---

## 4.8 失敗・再試行戦略

- `retry_count`, `max_retries` をジョブに保持
- ネットワーク瞬断は指数バックオフ再試行
- Provider側の非再試行エラー（認証不正等）は即 `failed`

---

## 4.9 セキュリティ/権限

- `job_id` 参照は必ず `user_id` 所有チェック
- `input_payload` の機微情報は最小化
- `result_path` はユーザーごとのnamespace配下に限定

---

## 4.10 観測性

ログキー:
- `job_id`, `tool_name`, `job_kind`, `provider`, `model`, `status`, `elapsed_sec`, `external_ref`, `result_path`

メトリクス:
- 完了率
- 平均/95p 実行時間
- timeout発生率
- 失敗理由別件数

---

## 5. 変更スコープ

### A. DB/マイグレーション
- `long_running_jobs` 追加
- `long_running_job_events` 追加
- 必要なら `long_running_job_locks` 追加

### B. ドメイン基盤（新規）
- `domains/long_running/services/job_service.py`
- `domains/long_running/executor/job_executor.py`
- `domains/long_running/handlers/deep_research_handler.py`（`DeepResearchJobHandler`）
- `domains/long_running/adapters/`（provider別 adapter）

### C. deep_research改修
- `core/backend/domains/orchestration2/tools/library/search.py`
  - `timeout_sec`, `async_on_timeout` 対応
  - timeout時に `job_id/result_path` を返却
- `deep_research_status` ツール追加

### D. Worker/Queue統合
- `long_running_jobs` 専用キュー（または task_type 分離）を追加
- worker起動フローへ `LongRunningJobExecutor` を独立ループで追加
- queue payload は `job_id` 中心の薄いエンベロープに統一

### E. API層
- `api/long_running_jobs.py`（新規）
- 認可・フィルタ・ページネーション

### F. テスト
- Unit: 状態遷移/バリデーション/権限
- Integration: create→running→completed, timeout→running返却→statusで回収
- Failure: providerエラー, cancel, expired

---

## 6. 導入ロードマップ

1. **M1**: DB + JobService + `deep_research_status` のread-only雛形
2. **M2**: deep_researchをjob化（timeout時 `running` 返却）
3. **M3**: 専用Queue + LongRunningJobExecutor + `DeepResearchJobHandler` で完了回収/結果保存
4. **M4**: provider adapter拡張（Gemini以外）と他long-running tool移行

---

## 7. 最終提案

- **採用すべき設計**: 「DB永続化 + queue/worker + tool向け共通Job API」
- **理由**: deep_researchのtimeout課題を解きつつ、将来の長時間ツールにも再利用できるため。
- **補足**: timeout時に `result_path` を返す要件はこの設計で自然に満たせます。


## 8. 設計スコープの判断（tool専用 vs orchestration2全体）

ご懸念の通り、既に AES（定期実行）や Run（実行追跡）がある中で、
`tool専用 long_running_jobs` を新設するかは重要なアーキテクチャ判断です。

### 8.1 判断軸

以下を満たすなら、**orchestration2全体の共通基盤として設計**するのが望ましいです。

1. 2つ以上の長時間ツール導入が見えている（deep_research以外も対象）
2. status/cancel/retry/result_path の契約を全ツールで統一したい
3. 監視（SLO, メトリクス）をツール横断で管理したい
4. キュー/ワーカーの運用を一本化したい

逆に、当面 deep_research のみで以下条件なら、**段階的にtool専用から開始**が現実的です。

- 早期リリース優先で実装コストを最小化したい
- 他long-running toolの要件が未確定
- 既存運用チームが新基盤の追加をすぐには捌けない

### 8.2 推奨アプローチ（現実解）

**「スキーマは汎用、導入はdeep_research先行」**を推奨します。

- テーブル名・API名は汎用 (`long_running_jobs`) にする
- まずは `tool_name=deep_research` のみ運用開始
- 他ツールは `job_kind` 追加で横展開

これにより、
- 初期は小さく始められ、
- 将来にわたって再設計コストを抑えられます。

### 8.3 既存基盤との棲み分け（最終案）

ご提示いただいた整理と、私の想定は一致しています。

- **AES**: Cron/System の定期実行タスク処理
- **Run**: Agentの実行単位。Run内のAgent処理状態管理と、実行イベント/履歴の集約
- **LongRunningJobs**: Agent配下で発火される「長期実行かつ単一job(tool)」の状態追跡と完了回収

補足:
- LongRunningJobs は Run に従属することが多いため、`run_execution_id` 参照を optional で持てる設計にして、
  実行エンジンは分離しつつトレースは連携可能にするのが実務上扱いやすいです。

この3層に分けることで、責務・SLO・障害影響範囲を明確化できます。

### 8.4 移行・統合余地

将来的に RunExecution と統合したい場合も、以下の形で段階統合可能です。

- `run_execution_id` を `long_running_jobs` に optional で保持
- UIは Run Center から long-running status を参照可能にする
- 実行エンジンは分離したまま、表示/検索だけ統合する

この方針なら、今の判断を将来の統合可能性と両立できます。

