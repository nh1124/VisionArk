# Native Jobs / Approvals 統合 & Job再設計レポート

## 1. 背景
現行Nativeの `Jobs` と `Approvals` は分離UIで管理されているが、実運用では
- 実行中の run 状況把握
- 承認待ち（高リスク操作）対応
が連続した1つのオペレーションとして扱われるため、同一UIで管理する方が自然である。

加えて、Nativeの本来目的は「ローカル操作の実行力拡張」であり、固定ジョブ型よりも
「agent が与えられたツールを使って状況適応的に実行する」モデルが適している。

---

## 2. Jobの現在の想定仕様（現状整理）

## 2.1 現在の中核概念
- `jobs` テーブルを中心に、`status`（queued/running/needs_approval/...）を遷移管理。
- Native daemon が `source=native&status=queued` をポーリングし、jobを取得。
- backend の `dispatch` が plan（steps）を生成し、daemon が step tool を逐次実行。
- high/critical step は `needs_approval` で停止し、承認後再開。

## 2.2 現在の前提
- Job中心のモデルであり、実行主体（agent run）との一体管理は弱い。
- Jobは「独立タスク単位」で表現され、run全体の文脈（会話/セッション/agent意図）との紐づきが限定的。
- ApprovalsはJob内状態としては存在するが、UIは Jobs と分断。

## 2.3 課題
1. **運用視点での断絶**
   - 実行監視（Jobs）と承認対応（Approvals）を行き来する必要があり認知負荷が高い。
2. **agent-runとの不整合**
   - 実際に見たいのは「いま agent が何をしているか（run状況）」だが、Job粒度では断片化しやすい。
3. **ローカル操作の柔軟性不足**
   - 固定ジョブ型に寄せるほど、ツール合成型の実行（状況適応）と設計が衝突しやすい。

---

## 3. 新しいJob仕様（提案）

## 3.1 概念再定義
- Jobを「独立した作業単位」から、**Agent Run に従属する実行イベント**へ再定義する。
- 主語を Job から Run に移し、UI/運用も `Run Center` を主軸とする。

### 新しい階層
1. **Run（主）**
   - 1回のエージェント実行セッション（ユーザー指示→完了まで）
2. **Execution Item（従）**
   - Run中で発生した実行イベント（旧Job相当）
3. **Approval Item（従）**
   - Execution Itemに紐づく承認要求

## 3.2 仕様案

### A. データモデル
- `agent_runs`（新規）
  - `id`, `user_id`, `project_id`, `agent_id`, `session_id`, `status`, `started_at`, `finished_at`, `summary`
- `run_executions`（旧jobsの再編）
  - `id`, `run_id`, `kind(local.file/local.dev/...)`, `status`, `risk_level`, `payload`, `result`, `target_device_id`
- `run_approvals`（旧job_approvalsの再編）
  - `id`, `execution_id`, `status`, `requested_at`, `decided_at`, `decided_by`, `reason`

### B. 状態遷移
- Run status: `queued -> running -> waiting_approval -> completed/failed/canceled`
- Execution status: `pending -> running -> waiting_approval -> succeeded/failed/rejected`

### C. API
- `GET /api/runs?status=...`
- `GET /api/runs/{run_id}`（executions + approvals を内包）
- `POST /api/runs/{run_id}/approve/{approval_id}`
- `POST /api/runs/{run_id}/reject/{approval_id}`

### D. Agent Tool 契約
- `list_agent_runs()`
- `list_run_executions(run_id)`
- `request_run_execution(run_id, tool, args, target_device_id?)`
- `approve_run_item(run_id, approval_id)`

---

## 4. Jobs / Approvals UI 統合提案

## 4.1 画面名
- **Run Center**（旧 Jobs / Approvals を統合）

## 4.2 最小UI構成
1. 左: Run一覧（active / waiting approval / completed）
2. 中央: 選択Runのタイムライン（実行イベント）
3. 右: 承認キュー（そのRunに紐づく項目 + 全体フィルタ）

## 4.3 操作導線
- Runを開くと、実行履歴と承認要求を同時表示。
- 承認操作後、同一画面で即ステータス反映（ページ遷移なし）。
- デバイス指定実行（将来）はExecution作成時に同UIで選択。

## 4.4 必要な追加情報（実装前に確定）
1. RunのID源泉（既存agent task_idを流用するか、新規発番か）
2. Run終了判定（最後のExecution完了時か、agent最終応答時か）
3. 承認単位（step単位 or execution単位）
4. 既存Jobs/Approvalsページの移行方針（段階統合 or 一括置換）

---

## 5. 新旧Job仕様の比較

| 観点 | 現在（Job中心） | 新仕様（Run中心） |
|---|---|---|
| 主体 | Job | Agent Run |
| 見える化 | Job一覧 + Approvals別画面 | Run単位の統合ビュー |
| 承認管理 | Job状態遷移の一部 | Run配下のApproval Item |
| 柔軟なツール合成 | 可能だが文脈分断 | Run文脈内で自然 |
| 運用認知負荷 | 高め（画面往復） | 低い（同一画面） |
| 既存互換 | 現行そのまま | 移行作業が必要 |

---

## 6. メリット / デメリット / 推奨

## 6.1 新仕様のメリット
1. **運用一貫性**: 実行監視と承認対応をRun単位で完結できる。
2. **本来目的との整合**: Nativeの「ローカル操作実行」をagent-run文脈で扱える。
3. **拡張性**: ツール追加・デバイス指定・監査追加をRun配下に統合しやすい。
4. **観測性**: 「いま何をしているか」をRunとして直接表示できる。

## 6.2 新仕様のデメリット
1. **移行コスト**: DB/API/UIの再編が必要。
2. **既存互換対応**: 旧jobs APIとの互換レイヤー設計が必要。
3. **初期複雑性**: run/execution/approval の3層管理を導入する必要がある。

## 6.3 推奨
- **推奨: あり（段階導入）**
- 理由:
  - ユーザー要望（Jobs/Approvals統合）に直接一致。
  - Nativeの本来狙い（agentによる柔軟なローカル操作）と設計整合が高い。
- ただし、運用停止リスクを下げるため **互換層付き段階移行** を推奨。

---

## 7. 変更スコープ

## 7.1 Backend
- `core/backend/shared/database.py`
  - `agent_runs`, `run_executions`, `run_approvals` 追加（または `jobs` 再編）
- `core/backend/api/native.py`
  - run系 endpoint 追加、旧jobs endpoint を互換化
- `core/backend/domains/native/job_service.py`
  - run中心 service へ再編

## 7.2 Native daemon / bridge
- `core/native/daemon/src/job_runner.rs`
  - pull対象を `run_executions` ベースへ変更
- `core/native/bridge/api.ts`
  - run API client 追加
- `core/native/shared/types.ts`
  - run/execution/approval の型追加

## 7.3 Native desktop UI
- `core/native/desktop/src-ui/components/JobsView.tsx`
- `core/native/desktop/src-ui/components/ApprovalsView.tsx`
- 新規 `RunCenterView.tsx`（統合画面）
- `App.tsx` ナビゲーション統合（Jobs/Approvalsを統合導線へ）

---

## 8. 導入手順（推奨）

### Phase 1: 互換層準備
- run系テーブル/API追加
- 旧jobs APIは内部的にrun_executionsへマッピング

### Phase 2: UI統合
- Run Center追加
- Jobs/Approvalsは内部リンク化（非推奨ラベル）

### Phase 3: daemon切替
- daemonの取得対象をrun_executionsへ切替
- 監査/承認をrun配下で統一

### Phase 4: 完全移行
- 旧jobs専用APIを段階廃止
- Run中心監視/通知へ一本化

---

## 9. まとめ
- Jobs/Approvalsの統合はUX上自然であり、運用効率も高い。
- JobをRun従属の実行イベントへ再定義することで、
  「agentが必要ツールを状況に応じて使う」Native本来の目的と整合する。
- 推奨は **Run中心モデルへの段階移行**。
