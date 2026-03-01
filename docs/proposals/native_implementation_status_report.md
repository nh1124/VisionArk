# Native実装の進行状況調査レポート

## 1. 現在のNative実装状況

### 1.1 全体像（構成面）
- `core/native` は提案どおり `desktop / daemon / bridge / shared / scripts` に分割され、最低限の基盤構造は成立している。
- `desktop` では Tauri ベースのネイティブUI、トレイ常駐、グローバルショートカット、Quick Note ウィンドウが実装済み。
- `daemon` ではジョブポーリング、Plan & Execute 実行ループ、ローカルツール実行、承認待機の基本フローが実装済み。
- `backend` 側には `/api/jobs`（作成・一覧・更新・dispatch・approve/reject）と `/api/native`（integrations/rules）が追加済みで、Native連携のAPI骨格は存在。

### 1.2 実装済みの主要機能

#### Desktop（Tauri UI）
- メインUI（Dashboard/Jobs/Approvals/Notes/Tasks/Projects/Agents/Settings）を含む統合画面が実装され、ログイン判定→画面遷移まで動作する構造。
- システムトレイ常駐・メインウィンドウ表示切替・クイックノート起動（`Super+Alt+N`）を実装。
- 通知プラグインとセキュアトークン保存（keyring）をコマンドとして公開。

#### Daemon
- `source=native&status=queued` のジョブを定期ポーリングして取得。
- 各ジョブについて `dispatch` でプランを取得し、step単位で `run_shell/read_file/write_file/list_dir/move_file/delete_file/open_app` を実行。
- `high/critical` ステップで `needs_approval` に遷移し、承認後に再開する流れを実装。

#### Backend
- Nativeジョブの作成・一覧・取得・状態更新APIを実装。
- LLMを使ったジョブプラン生成（`/api/jobs/{id}/dispatch`）を実装。
- Integrations / Rules のCRUD（一覧・作成）を実装。
- DBには `jobs / job_approvals / integration_connections / automation_rules` が定義済み。

---

## 2. proposalsの狙いとの比較

### 2.1 総評
- **進捗評価:** 「基盤は成立、狙いの中核機能は一部実現、実運用に必要な安全性・統合度は未達」。
- 設計上の3本柱（Native UI / Local Daemon / Cloud連携）のうち、**最初の接続可能な縦スライス**はできている。
- ただし、提案で重視される **安全な実行統制・監査・状態把握・ユースケース統合（メール/買い物等）** はまだ未完成。

### 2.2 狙い別の比較

| proposals上の狙い | 現在の実装状況 | 判定 |
|---|---|---|
| Web同等のNative UI提供 | 主要画面群は存在するが、Webとの差分検証・完全パリティ保証は未確認 | 部分達成 |
| ローカル実行Daemon統合 | ジョブ取得〜実行〜結果反映の最短フローは実装済み | 概ね達成 |
| Web→Nativeブリッジのリアルタイム化 | WebSocket接続はあるがメッセージ処理はログ出力中心 | 部分達成 |
| 承認ガード/高リスク制御 | リスク判定と `needs_approval` はあるが粒度・ポリシー制御が粗い | 部分達成 |
| 状態把握（Activity Capture） | Windowsタイトル取得のデバッグループのみで提案機能未接続 | 未達 |
| セキュア運用（秘密情報・監査） | keyring保存はあるがコマンド許可制、監査整備は不足 | 部分達成 |
| ユースケース拡張（メール/買い物） | API器はあるが実ユースケースの実行エンジン未実装 | 未達 |

---

## 3. 未実装機能・バグ/リスク指摘

### 3.1 未実装・機能不足
1. **Activity Captureが未接続**
   - 現状はアクティブウィンドウを取得してログ出力するのみで、Task/Note補助やBackend同期に未連携。
2. **WebSocketブリッジが受信処理未実装**
   - 接続してメッセージをログに出すだけで、ジョブキックや通知更新に使っていない。
3. **Approvalモデルが簡易実装**
   - `job_approvals` テーブルはあるが、ジョブ実行フローで十分に活用していない。
4. **実行ポリシー制御が不足**
   - ツール実行に allowlist/path制限/dry-run/rollback がないため、提案要件（Safe Execution）に未達。
5. **環境設定の外部化不足**
   - APIの接続先が複数箇所で `http://localhost:8000` 固定に近く、配布/本番運用に不向き。
6. **ユースケース実装不足**
   - メール自動化、買い物自動化、開発実行の成果物収集等が未完成。

### 3.2 バグ・不具合リスク
1. **認可境界の弱さ（重大）**
   - `JobService.update_job_status/approve_job/reject_job` が `user_id` で絞らず `job_id` だけで更新しており、API層で呼び出しを誤ると他ユーザーJob更新の余地が残る。
2. **承認待機ロジックの判定が曖昧**
   - 承認待機中に `queued` または `running` を「承認済み」と見なして再開するため、状態遷移競合時に誤再開の可能性がある。
3. **機密情報ログ出力の懸念**
   - keyring処理や認証周辺にデバッグログが多く、運用ログで情報露出リスクがある。
4. **bridge APIのトークン管理未統合**
   - `core/native/bridge/api.ts` は手動 `setToken` 前提で、desktop側の認証保存と統一されていない。

---

## 4. 改善案

### 4.1 直近で優先すべき改善（P0）
- **認可強化:** `JobService` の更新系APIを必ず `user_id` 条件付きにする。
- **実行ガード導入:** `run_shell` とファイル操作に allowlist・作業ディレクトリ制限・危険引数バリデーションを導入。
- **承認の厳密化:** `job_approvals` を実フローに組み込み、承認ID/期限/決定者で状態遷移を確定させる。
- **接続先設定統一:** API base URL を環境変数 or 設定画面経由へ統一し、ハードコードを撤廃。

### 4.2 次段で実装すべき改善（P1）
- **WebSocketイベント実装:** `job_created`, `job_updated`, `approval_requested` などのイベントを定義し、push駆動へ移行。
- **Activity連携:** 収集→ローカル暗号化保存→要約送信→Task/Note提案までの最短パイプラインを実装。
- **監査ログ整備:** `who/when/what/result` の監査レコードを標準化し、Web UIで検索可能にする。

### 4.3 中期改善（P2）
- **ユースケース実装の縦展開:** メール自動化 → 開発支援 → 買い物の順で安全制御付き実装。
- **運用品質:** リトライ戦略、レート制御、障害時のロールバック、テレメトリ導入。

---

## 5. 変更スコープ（提案）

### 5.1 変更対象ディレクトリ
- `core/backend/api/native.py`
- `core/backend/domains/native/job_service.py`
- `core/backend/shared/database.py`（必要に応じて approval 監査項目拡張）
- `core/native/daemon/src/*`
- `core/native/desktop/src/*`
- `core/native/desktop/src-ui/lib/api.ts`
- `core/native/bridge/*`
- `core/native/shared/*`

### 5.2 影響範囲
- **Backend API互換性:** ジョブ状態遷移/承認APIの契約変更が入り得る。
- **Desktop/Daemon連携:** 実行制御の厳密化に伴い、UI側の承認操作とdaemonの再開条件に変更が必要。
- **データ互換性:** 監査ログ・承認履歴のスキーマ変更時にmigrationが必要。

---

## 6. 導入ロードマップ

### Phase A（1〜2週）: 安全性の土台
- Job更新系の認可修正（user_id制約）。
- 実行ツールのポリシーガード（allowlist/path制限）。
- 承認フローを `job_approvals` 中心に再実装。

### Phase B（2〜3週）: リアルタイム連携と可観測性
- WebSocketイベント契約の定義と実装。
- daemon の push 受信トリガー化（polling依存の低減）。
- 監査ログフォーマット統一とUI可視化。

### Phase C（2〜4週）: ユースケース機能化
- コーディング自動化（build/test/lint + artifact収集）を先行実装。
- Activity Capture→Task/Note提案の最小機能を実装。

### Phase D（3〜6週）: 高リスクユースケース拡張
- メール自動化（下書き生成、承認送信）。
- 買い物フロー（候補提示、二段階承認、決済保護）。

### Exit Criteria（導入完了判定）
- 高リスク操作が必ず承認・監査経路を通る。
- Web/Native双方からジョブ状態が一貫表示される。
- 代表ユースケース（開発実行・メール）がE2Eで安定稼働する。
