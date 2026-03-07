# ローカル codex / antigravity / Claude CLI 操作の integration 分割設計レポート

## 0. 背景

前提として、VisionArk には以下の仕組みが既にある。

- integration は `integrations/*` 配下を動的に検出し、`get_tools(user_id, db)` を通じてツールを読み込む。  
- integration は `va_sdk.BaseTool` を実装し、adapter 経由で orchestration2 の `ToolDef` として利用される。  
- ローカル実行自体は `run_native_job`（`local.run_shell` など）で Native daemon へ委譲できる。  

これにより「CLI 実行」は実現できるが、1つの汎用 integration にまとめると、
**サービス有効化・認証情報・運用ポリシーが混在し、エージェント実装/運用が複雑化**する。

---

## 1. 結論（今回の方針）

ご指摘のとおり、**integration は CLI/agent 単位で分離する構成が適切**。

- `integrations/codex`
- `integrations/antigravity`
- `integrations/claude`（または `claudes` 命名方針に準拠）

この分離により、各 integration ごとに以下を独立管理できる。

1. 有効化（on/off）
2. 必要認証情報（API key / token / endpoint / org など）
3. ツール公開範囲（どの tool を agent に見せるか）
4. ヘルスチェック/監査/障害切り分け

---

## 2. 現状の仕組みとの整合（実装根拠）

## 2-1. 有効化の単位
- 既存 integration でも `__init__.py` の `get_tools(user_id, db)` 内で `ServiceRegistry` を参照し、`service_name` + `is_active` で有効化判定している。  
- したがって `service_name = codex / antigravity / claude` を個別に持てば、切替は自然に分離できる。  

## 2-2. 認証情報の保存
- `ServiceRegistry` には `api_key_encrypted` / `access_token_encrypted` / `refresh_token_encrypted` / `config(JSON)` があり、サービスごとの資格情報・設定を保持できる。  
- 既存 API (`/api/settings/services`) でもサービス登録・更新が可能で、このモデルを流用できる。  

## 2-3. manifest 駆動 UI
- 既存 integration は `manifest.json` を持っており、`id`, `authType`, `setup_instructions`, `config_fields` で接続 UI/手順を定義している。  
- したがって codex / antigravity / claude も **個別 manifest** で接続フローを分離できる。  

---

## 3. 推奨アーキテクチャ（分離版）

## 3-1. ディレクトリ構成

```text
integrations/
  codex/
    __init__.py
    agent_tools.py
    manifest.json
    client.py          # 任意: 認証/実行APIラッパ
    api.py             # 任意: 接続テスト/補助API
  antigravity/
    __init__.py
    agent_tools.py
    manifest.json
    client.py
  claude/
    __init__.py
    agent_tools.py
    manifest.json
    client.py
```

## 3-2. service_name 命名
- `codex`, `antigravity`, `claude` を `ServiceRegistry.service_name` に採用。
- `get_tools()` は自 integration 名だけを見る。

## 3-3. ツール公開方針
- codex integration は codex 関連ツールのみ公開（例: `codex_check_runtime`, `codex_run`）
- antigravity integration は antigravity 関連のみ
- claude integration は claude 関連のみ

> 重要: ツール名を分けることで、agent が誤って別CLIを呼ぶ事故を減らせる。

---

## 4. 認証・設定管理（DB + manifest）

## 4-1. DB（ServiceRegistry）に持つ情報
各 service ごとに最低限以下を保存：

- `service_name`: `codex` / `antigravity` / `claude`
- `is_active`: 有効化フラグ
- `api_key_encrypted`: API key 型資格情報
- `access_token_encrypted` / `refresh_token_encrypted`: OAuth/Token 更新が必要な場合
- `base_url`: CLI連携先や補助APIがある場合
- `config`: JSON 拡張
  - `default_device_id`
  - `default_timeout_sec`
  - `allowed_workdirs`
  - `profile`（safe / standard / power など）

## 4-2. manifest.json で持つ情報
各 integration に個別 manifest を置き、UI には以下を出す。

- `id`: service_name と一致
- `authType`: `api_key` / `oauth` / `shared` など
- `config_fields`: 必須入力（endpoint, org, project, default profile）
- `setup_instructions`: 導入手順（CLI インストール / 認証 / 接続確認）

これにより、**「どのagent(=どのCLI)に何が必要か」が UI 上で明確化**される。

---

## 5. ツール設計（各 integration 共通パターン）

## 5-1. 最低限のツール
各 integration で同型の2ツールを推奨。

1. `*_check_runtime`
   - バイナリ存在、version、実行可能ディレクトリ、device 到達性を確認
2. `*_run`
   - 実行本体。内部で `run_native_job(job_type="local.run_shell")` に変換

例：
- codex: `codex_check_runtime`, `codex_run`
- antigravity: `antigravity_check_runtime`, `antigravity_run`
- claude: `claude_check_runtime`, `claude_run`

## 5-2. 共通レスポンス規約
- `ok: bool`
- `category: success|missing_binary|invalid_args|permission_denied|timeout|approval_required|internal_error`
- `summary: str`
- `run_id` / `execution_id`
- `raw`（必要時のみ）

## 5-3. リスク制御
- 破壊的コマンドは integration 側で deny または `risk_level=high` 固定
- high/critical は既存 Run Center 承認フローに接続

---

## 6. 実装ステップ（手元エージェント向け）

### Step 1: integration 雛形を3つ作成
- `integrations/codex`
- `integrations/antigravity`
- `integrations/claude`

### Step 2: manifest を個別作成
- `id` を service_name と一致
- authType / config_fields / setup をCLIごとに記述

### Step 3: DB登録導線を整備
- `/api/settings/services` を使って各 service を個別登録
- 認証情報は `ServiceRegistry` の encrypted カラムへ保存

### Step 4: get_tools の有効化ゲート実装
- `ServiceRegistry(service_name=<self>, is_active=True)` の時だけ tool を返す

### Step 5: check/runtime & run ツール実装
- 先に `*_check_runtime`
- 次に `*_run`（`run_native_job` 経由）

### Step 6: 検証
- サービス別 on/off が正しく分離されること
- 認証未設定時のエラー分類が分離されること
- 承認が必要なケースで待機→承認→再開されること

---

## 7. 変更スコープ

## 7-1. 必須
- `integrations/codex/*`
- `integrations/antigravity/*`
- `integrations/claude/*`

## 7-2. 状況次第
- settings UI/API の文言追加（サービス追加時）
- health check 方針（CLIローカル実行と外部APIの差分整理）

## 7-3. 今回非スコープ
- Native daemon の全面再設計
- Run Center モデル変更

---

## 8. リスクと回避策

1. **integration 乱立による運用負荷**
   - 回避: テンプレート共通化（`client.py`/レスポンス規約を統一）
2. **manifest と DB項目の不整合**
   - 回避: `id == service_name` を厳格運用
3. **コマンド実行の安全性**
   - 回避: allowlist + 高リスク自動承認要求 + workdir 制限

---

## 9. 最終提案

- 要望実現の最短かつ安全な道は、**integration を codex / antigravity / claude で分割**すること。  
- 認証・有効化は `ServiceRegistry`、接続UXは各 `manifest.json` で管理する。  
- 実行本体は既存 `run_native_job` を再利用し、integration 層で型・検証・分類を加える。  

この方式なら、agentごとの設定要件（有効化・認証情報）を独立管理でき、
実装担当が段階的に導入しやすい。
