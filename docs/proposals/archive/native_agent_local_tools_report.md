# Native Agent ローカル操作ツール 設計レポート

## 1. 目的
本レポートは、次フェーズで予定している「agentによるローカル操作実行」に向けて、
- 現在のagentツール実装状況
- 追加すべき基本ツール提案
- 変更スコープ
を整理する。

---

## 2. 現在のagentツール実装状況

## 2.1 Orchestration2 側（クラウド実行ツール）
- ToolRegistry による `ToolDef + implementation` 登録基盤は存在。
- 既存のツール群は files/search/ai/browser/system/notes/workspace/shell 等が実装済みで、
  クラウド側エージェントの実行基盤は整っている。
- `RunSafeShellTool` のようなサーバー側shellツールはあるが、Native端末操作専用のツール契約は未分離。

## 2.2 Integration 側
- `integrations/*/agent_tools.py` で Google Calendar / Outlook / LBS / LINE / Knowledge Core 向けツールが存在。
- これらは主に外部サービス連携であり、端末のマウス/キーボード/ウィンドウ操作を担うものではない。

## 2.3 Native 実行側（daemon）
- daemon の `local_tools` として以下を実装済み:
  - `run_shell`, `read_file`, `write_file`, `list_dir`, `move_file`, `delete_file`, `open_app`
- backend `dispatch` も上記ツールを前提に plan を生成。
- 現状は「ファイル + コマンド + アプリ起動」中心で、GUI操作（マウス/座標クリック/ウィンドウ探索）や環境情報取得ツールは未実装。

## 2.4 ギャップ要約
1. Native操作ツールが最小セットに留まる（GUI操作不足）。
2. 端末状態取得（OS/画面/アクティブウィンドウ/入力デバイス可用性）の標準ツールが不足。
3. agentが使うツール定義（クラウド側）とdaemon実装（ローカル側）の契約が疎結合で、拡張時にズレやすい。

---

## 3. agentがnativeを操作するためのツール提案一覧

## 3.1 基本カテゴリ
1. **環境情報取得系（必須）**
2. **ウィンドウ/アプリ制御系**
3. **マウス/キーボード操作系**
4. **画面理解系（観測）**
5. **ローカル実行系（既存拡張）**
6. **安全制御/承認系**

## 3.2 提案ツール（MVP優先順）

### A. 環境情報取得
1. `get_native_environment`
   - 取得: OS, version, hostname, user, shell, timezone, monitors, permissions
2. `get_active_window`
   - 取得: app name, window title, bounds, pid
3. `list_running_apps`
   - 取得: 実行中アプリ一覧（必要最小限メタデータ）

### B. ウィンドウ/アプリ制御
4. `launch_app`
   - 既存 `open_app` の強化版（起動確認/タイムアウト付き）
5. `focus_window`
   - title/app/pid 指定でフォーカス
6. `close_window`
   - 指定ウィンドウを閉じる（高リスク時は承認）

### C. マウス/キーボード
7. `mouse_move`
8. `mouse_click`
9. `mouse_drag`
10. `keyboard_type`
11. `keyboard_hotkey`

※ マウス/キーボード系は誤操作リスクが高いため、`dry_run` と `requires_focus_match` を推奨。

### D. 画面理解
12. `capture_screen`
13. `capture_window`
14. `find_on_screen`（OCR/画像テンプレート）

### E. 既存ローカル実行の補強
15. `run_shell_safe`
   - allowlist/path制約/timeout必須
16. `read_file_safe`
17. `write_file_safe`

### F. 承認・安全
18. `request_native_approval`
19. `get_approval_status`
20. `abort_native_action`

---

## 4. ツール実行の共通設計ルール（提案）

## 4.1 共通パラメータ
- `target_device_id`（必須）
- `dry_run`（デフォルト true 推奨）
- `timeout_sec`
- `idempotency_key`
- `risk_level`（自動算出 + ポリシー上書き可）

## 4.2 共通レスポンス
- `ok`, `error_code`, `message`, `artifacts`, `started_at`, `finished_at`, `device_snapshot`

## 4.3 安全制御
- high/critical は自動 `needs_approval`
- フォーカス対象が一致しない場合は実行拒否
- マウス/キーボード操作はセーフエリア制約（画面外/保護領域ガード）

---

## 5. 変更スコープ（Run Center 統合後）

> ※ Jobs/Approvals → Run Center 統合が完了済み。以下は現在のアーキテクチャに基づく。

## 5.1 Backend
- `integrations/native_tools/agent_tools.py`
  - `RunNativeJobTool` の tool schema 更新（全ツール一覧・引数スキーマ・リスクレベル）✅ 完了
- `core/backend/domains/native/run_service.py`
  - RunService で実行履歴メタデータを管理（既存で十分）
- ~~`core/backend/api/native.py` の `_DISPATCH_SYSTEM_PROMPT`~~
  - Run Center では agent が `run_native_job` を直接呼ぶため不要

## 5.2 Native daemon
- `core/native/daemon/src/local_tools.rs`
  - 新規ツール実装（env/window/process/screen） ✅ Phase 1 完了
- `core/native/daemon/src/job_runner.rs`
  - Run Center 対応済み（`run_executions` ベース） ✅ 完了
- `core/native/daemon/src/activity.rs`
  - `get_active_window` 用情報の標準化（PID/exe_name） ✅ 完了
- `core/native/daemon/Cargo.toml`
  - sysinfo/screenshots/image/base64/hostname/iana-time-zone 追加 ✅ 完了

## 5.3 Bridge / Shared
- `core/native/bridge/api.ts`
  - Run Center API クライアント（既存で十分）
- `core/native/shared/types.ts`
  - RunExecution / RunApproval / AgentRun 型で既にカバー

## 5.4 Desktop UI
- `core/native/desktop/src-ui/components/RunCenterView.tsx`
  - 実行タイムラインへの tool artifact 表示（将来強化）

---

## 6. 導入優先度

### Phase 1（最小） ✅ 実装完了
- `get_native_environment`, `get_active_window`, `list_running_apps`, `launch_app`, `capture_screen`
- 関連変更: `local_tools.rs`, `activity.rs`, `Cargo.toml`, `agent_tools.py`

### Phase 2（操作）
- `focus_window`, `mouse_click`, `keyboard_type`, `keyboard_hotkey`

### Phase 3（高度化）
- `find_on_screen`, `mouse_drag`, `abort_native_action`, 詳細監査

---

## 7. まとめ
- Phase 1 の「環境取得 + 画面キャプチャ + プロセス情報 + 起動確認付きアプリ起動」は実装完了。
- Agent は `run_native_job` tool 経由で `local.<tool>` として daemon にツールを実行させる。
- 次フェーズは **GUI操作（マウス/キーボード）** を追加し、agentが画面操作できる基盤を作る段階。
- Run Center 統合により、run/execution/approval の3層管理で監査性も確保されている。

