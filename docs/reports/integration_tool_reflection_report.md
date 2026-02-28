# Integration実装とTool反映フロー（現行実装レポート）

このドキュメントは、**現時点のVisionArk実装**における以下を、エージェント実装時の参照用に整理したものです。

- integration の登録・起動時反映
- orchestration2 への tool 取り込み
- skill / prompt への tool 反映（tool reflection）
- 新規integration / 新規toolを追加するときの実装手順

---

## 1. 全体像（どこで何が起きるか）

### 1-1. API / Manifest 側（FastAPI起動時）

`core/backend/app/main.py` で `include_integration_routers(app)` が呼ばれ、`integrations/*` 配下をスキャンして以下を動的登録します。

- `manifest.json` の読み込み（Integration Hub用カタログ）
- `api.py` 内の `router` を `/api/...` へマウント

実装本体は `va_sdk/discovery.py` にあり、`INTEGRATION_CATALOG` にmanifestを保持します。

### 1-2. Worker 側（バックグラウンド実行起動時）

`core/backend/app/worker.py` は起動時に `integrations` パッケージをロードし、`pkgutil.walk_packages` で各 integration module を import します。
目的は、integration の `handlers.py` が import 時に `task_registry` / `reply_registry` 等へハンドラを登録できるようにするためです。

### 1-3. AI実行時（projectごとの engine 構築時）

`create_engine_for_project(...)`（`project_engine_builder.py`）で:

1. コアtoolを登録
2. `register_and_reflect_integrations(...)` を呼び、ユーザー有効化済みintegrationのtoolを取得・登録
3. 反映済みtoolを skill（`operation`）へ動的追加
4. 追加tool説明文を prompt data（`integration_tools_text`）へ注入

この処理により、**ユーザーごとに有効なintegration toolだけ**が、その実行時のエージェントに見える構成になります。

---

## 2. integration tool の取得方法（有効化判定）

### 2-1. integrationごとの `get_tools(user_id, db)`

各 integration の `__init__.py` は `get_tools(user_id, db)` を公開し、`ServiceRegistry` を参照して `is_active == True` のときのみtoolインスタンスを返します。

- `integrations/google_calendar/__init__.py`
- `integrations/line/__init__.py`
- `integrations/outlook/__init__.py`
- `integrations/lbs/__init__.py`
- `integrations/knowledge_core/__init__.py`

### 2-2. 全integrationの収集

`integrations/loader.py` の `load_integration_tools(user_id, db)` が `integrations/*` を巡回し、各 `integrations.<name>` を import して `get_tools` を呼びます。

- `get_tools` があればそれを優先（推奨経路）
- 無ければ `BaseTool` 継承classの直接スキャンへフォールバック（ただし有効化ガードを迂回するため非推奨）

---

## 3. orchestration2 への接続（Adapter）

integration 側toolは `va_sdk.BaseTool` 準拠、orchestration2 側は独自の `ToolDef + invoke` 契約です。
この差分を `integrations/adapter.py` の `IntegrationToolAdapter` が吸収しています。

主な役割:

1. `args_schema`（Pydantic）から JSON Schema を生成し `ToolDef.parameters` に変換
2. 実行時に `ExecutionContext.metadata` から `IntegrationContext`（user_id, db, project/session等）を構築
3. `sdk_tool.run(ctx=..., **args)` を呼び、`SDK ToolResult` を orchestration2 `ToolResult` へ変換

---

## 4. tool reflection の実装（skill / prompt 反映）

`core/backend/domains/orchestration2/integrations/tool_reflection.py` の
`register_and_reflect_integrations(...)` が中核です。

処理順:

1. `load_integration_tools(...)` でtool群を取得
2. engine内の既存tool名と衝突チェック
   - 衝突時はスキップ（コアtool優先）
3. 衝突しないtoolを `engine.register_tool(...)`
4. `dynamic_skills` の `operation` skill に tool name を `extend`
5. `integration_tools_text`（`- tool_name: description` の列挙）を返す

`project_engine_builder.py` 側では、この `integration_tools_text` を `prompt_data` に入れており、プロンプト構成時に integration tool の説明をLMへ渡せる設計です。

---

## 5. 新規integration実装時の最小チェックリスト

`integrations/<new_service>/` を作り、最低限以下を実装します。

1. `__init__.py`
   - `get_tools(user_id, db)` を実装（`ServiceRegistry.is_active` ガード必須）
   - `handlers.py` を使う場合は `from . import handlers` を入れて登録を保証
2. `agent_tools.py`
   - `va_sdk.BaseTool` 継承toolを定義
   - `name` 重複を避ける（コアtool名と衝突すると反映スキップ）
3. `api.py`（必要なら）
   - `router` を公開（起動時自動マウント対象）
4. `manifest.json`（必要なら）
   - Integration Hub表示情報
5. `models.py`（必要なら）
   - 起動時 discovery で import される

---

## 6. 新規toolを「エージェントに反映」する要点

### 必須条件

- toolは `get_tools(...)` の返り値に含める
- 対象ユーザーの `ServiceRegistry(service_name, is_active=True)` が存在する
- tool名が既存コアtoolと重複しない

### 反映先

- engine registry（実行可能tool）
- `operation` skill（利用可能toolの選択範囲）
- prompt text（tool説明）

つまり、現行設計では「登録するだけ」でなく、**user activation + reflection** が揃って初めて実運用で使える状態になります。

---

## 7. 運用上の注意（現行コードベース）

- `integrations/__init__.py` は既知integrationを `try/except ImportError` で個別importしています。新規追加時はここへの追記も検討すると、worker起動時の明示ロード経路が安定します。
- `load_integration_tools` には `get_tools` 未定義時フォールバックがありますが、有効化ガードを外すリスクがあるため、**全integrationで `get_tools` 実装を必須運用**にするのが安全です。
- reflection先は現在 `operation` skill 固定です。将来、integrationの種類別に skill を分けたい場合は `register_and_reflect_integrations` で振り分けロジックを追加するのが拡張ポイントです。

---

## 8. エージェント実装者向けの実践ガイド（短縮版）

- integration由来の外部操作を増やすときは、まず `integrations/<service>/agent_tools.py` に実装し、`get_tools` へ返す。
- エージェントがそのtoolを使わない場合は、
  1) service有効化状態、
  2) tool名衝突、
  3) reflectionで `operation` skill へ追加されたか
  の順で確認する。
- バックグラウンド処理連携（同期ジョブ・返信チャンネル）が必要なら、`handlers.py` で registry decorator を使い、import経路を保証する。

以上が、現行の integration 実装方法と tool 反映方法の実装ベース整理です。
