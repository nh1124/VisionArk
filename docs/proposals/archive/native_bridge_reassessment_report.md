# Native / Bridge 実装状態 再調査レポート

## 1. 調査の前提
- 対象: `core/native`（`desktop` / `daemon` / `bridge`）と、その連携先である `core/backend/api/native.py` / `domains/native/job_service.py`。
- 目的: main反映後の現状を、実装事実ベースで再確認し、次の改修優先度を明確化する。

---

## 2. 現在の実装サマリ（結論）

### 2.1 Native全体
- **MVPとしての動作導線は成立**している。
  - `desktop` で操作・表示。
  - `daemon` がジョブを取得してローカル実行。
  - backend API に結果反映。
- 一方で、**運用耐性（セキュリティ・責務統一・監査）**は未完成。

### 2.2 Bridge
- `bridge` 自体は REST / WebSocket の共通層として存在するが、
  **Native全体の唯一の通信レイヤーとしては未統一**。
- `desktop/src-ui/lib/api.ts` に独自API実装が残り、`bridge/api.ts` と責務が重複している。

---

## 3. 実装状態詳細（Native）

## 3.1 desktop（UI/操作）
### 実装済み
- Tauriアプリとして起動し、トレイ常駐・メニュー操作・メインウィンドウの表示切替を実装。
- グローバルショートカット `Super+Alt+N` で Quick Note ウィンドウを生成。
- 通知表示、keyring経由のトークン保存/取得/削除コマンドを提供。
- React UI側で dashboard/jobs/approvals/notes/tasks/projects/agents/settings など主要ビューを切替表示。

### 観測された課題
- APIクライアントが `desktop/src-ui/lib/api.ts` 側に大きく存在し、bridgeと重複。
- API接続先が `http://localhost:8000` 固定運用寄りで、環境切替設計が弱い。
- 認証関連のデバッグログ出力が多く、本番運用時のログ管理が必要。

## 3.2 daemon（実行エンジン）
### 実装済み
- `main.rs` で `bridge_client` / `activity` / `job_runner` の3タスクを同時起動。
- `job_runner` は `source=native&status=queued` をポーリングし、ジョブごとに dispatch plan を取得して step 実行。
- 高リスク（high/critical）stepで `needs_approval` に遷移し、承認待機後に再開。
- `local_tools` で `run_shell/read_file/write_file/list_dir/move_file/delete_file/open_app` を実装。
- step結果を `job.result.step_results` に追記し、全step終了で `succeeded` 化。

### 観測された課題
- 安全実行の制御（allowlist, path制限, dry-run, rollback）が未実装。
- `activity` は現状最小実装（Windowsでアクティブタイトル取得、他OSは `None`）で、提案機能への接続不足。
- 承認待機ロジックは状態値依存で、承認イベント中心の厳密モデルには未到達。

## 3.3 backend連携（Nativeジョブ）
### 実装済み
- `/api/jobs` の作成・一覧・取得・更新・dispatch・approve/reject を提供。
- `/api/jobs/{id}/dispatch` はLLMで plan JSON を生成し、job.resultに保存。

### 観測された課題
- `JobService.update_job_status/approve_job/reject_job` は `job_id` 条件のみで取得しており、
  サービス層単体では user境界を強制していない（API層依存）。

---

## 4. 実装状態詳細（Bridge）

## 4.1 bridge/api.ts
### 実装済み
- jobs / integrations / rules の HTTP client を提供。
- Bearer token 付与、共通 request 関数、型付き戻り値（shared types）を実装。

### 課題
- `BASE_URL` が固定文字列（`http://localhost:8000`）。
- desktop側の独自API層と並立し、共通化の効果が限定的。

## 4.2 bridge/ws.ts
### 実装済み
- WebSocket接続、メッセージtypeごとのハンドラ配信、切断時の再接続を実装。

### 課題
- 接続ライフサイクル制御（多重接続防止、明示的状態管理）が簡易。
- イベント契約（event schema）の正式化が未整備。

## 4.3 daemon側 bridge_client との関係
- `daemon` 側には Rust 実装の `bridge_client.rs` があり、WS接続して受信ログを出す構成。
- ただし現在は「接続・受信表示」中心で、push駆動のジョブ制御への統合は限定的。

---

## 5. ギャップ整理（理想 vs 現状）

1. **通信一元化ギャップ**
   - 理想: bridgeがNative共通通信層。
   - 現状: desktop独自API + bridge API が並立。

2. **安全実行ギャップ**
   - 理想: 実行ポリシー/承認/監査が厳密。
   - 現状: 実行ツールは動くが安全ガードは最小。

3. **イベント駆動ギャップ**
   - 理想: WSイベントで即時反映・即時実行トリガー。
   - 現状: poll中心、WSは補助的。

4. **認可強制ギャップ**
   - 理想: サービス層でも user境界を強制。
   - 現状: 一部更新系ロジックがAPI層依存。

---

## 6. 次の実装優先度（再提案）

### P0（先に着手）
1. `JobService` 更新系に user_id 条件を必須化。
2. `daemon/local_tools` に実行ポリシー（allowlist/path制約）導入。
3. `BASE_URL`/token戦略を bridge中心に統一し、desktopの重複APIを段階縮小。

### P1（次段）
1. bridgeのWSイベント契約を明文化し、desktop/daemon双方で共通利用。
2. 承認フローを状態値判定から approvalレコード中心に強化。
3. 監査ログ標準化（who/when/what/result）。

### P2（拡張）
1. Activity Capture の実利用（Task/Note提案連携）。
2. ユースケース別エンジン（メール/開発支援/買い物）の安全拡張。

---

## 7. 変更スコープ（実装時の最小単位）
- `core/native/bridge/*`
- `core/native/desktop/src-ui/lib/api.ts`
- `core/native/daemon/src/local_tools.rs`
- `core/native/daemon/src/job_runner.rs`
- `core/backend/domains/native/job_service.py`
- （必要に応じて）`core/backend/api/native.py` / DBスキーマ

---

## 8. まとめ
- 現状は「**動くNative MVP**」としては成立している。
- ただし bridgeの価値（共通通信層）を十分に活かせておらず、native全体で通信・認可・安全実行が分散している。
- 次フェーズは機能追加より先に、**bridge中心の通信統一 + daemon安全化 + backend認可強化**を優先するのが妥当。
