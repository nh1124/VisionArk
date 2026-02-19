# engine_setup → orchestration2 再編レポート

## 背景

現在 `core/backend/domains/orchestration2/engine_setup.py` は、
- orchestration2 の「コアエンジン初期化」
- VisionArk 固有の「プロダクト設定（役割・グラフ・ツール束ね）」
- 実行時の「DB/ファイル読込によるプロンプト組み立て」

を 1 ファイルで担っており、責務が混在しています。今後の管理性・拡張性のため、`orchestration2` 配下に機能別フォルダへ分割する余地が大きいです。

---

## 1) 現状 engine_setup で定義されているもの

### A. スキル関連
- `_NoOpSkill`（ツールフィルタリング用途のダミー実装）
- `SKILL_DEFS`（固定スキル定義）
  - `investigation`
  - `document_creation`
  - `file_management`
  - `operation`
- `ALL_SKILL_NAMES`

### B. グラフ関連
- `PROJECT_GRAPH_YAML`
  - `project_assistant` グラフ
  - `plan -> execute -> verify -> respond` の 4 ステップ構成
  - 各ステップに role / skills / limits / 遷移条件を直書き

### C. ツール解決・登録関連
- `_get_all_tools()`
  - `tools.library.*` から各 Tool クラスを import
  - クラス一覧を `tool_classes` に集約
  - インスタンス化して `(ToolDef, impl)` のリストを返却

### D. プロンプトメタデータ事前読込
- `_load_prompt_components()`
  - 静的 prompt component (`identity`, `formatting`)
  - DB の project agent profile
  - PLAN.md
  - Skill 本文
  - User settings
  - これらを dict にまとめて返却

### E. エンジン組み立て（メインファクトリ）
- `create_engine_for_project()`
  - `SQLAlchemyStore` + `AgentEngine` 作成
  - コアツール登録
  - integration tools 動的登録（重複名スキップ）
  - integration tool を `operation` skill に反映
  - `GeminiEngine` 登録 / model 登録
  - skill / role / graph / agent 登録
  - prompt data を `engine._prompt_data` に格納

---

## 2) 移行可能なもの（orchestration2 配下へのフォルダ分割候補）

以下は「比較的安全に切り出せる順」で整理しています。

### 優先度 High

1. **グラフ定義（`PROJECT_GRAPH_YAML`）**
   - 文字列直書きから分離しやすい
   - 例: `domains/orchestration2/config/graphs/project_assistant.yaml`
   - 読込責務を graph loader に寄せる

2. **固定スキル定義（`SKILL_DEFS`, `ALL_SKILL_NAMES`）**
   - 例: `domains/orchestration2/config/skills/default_skills.py` または YAML
   - `engine_setup` からは参照のみへ

3. **ツールカタログ（`_get_all_tools` の tool_classes 群）**
   - 例: `domains/orchestration2/tools/catalog/default_catalog.py`
   - 「どの tool を標準搭載するか」を 1 箇所管理

### 優先度 Medium

4. **prompt preload（`_load_prompt_components`）**
   - DB/FS アクセスの集約層として独立可能
   - 例: `domains/orchestration2/prompting/prompt_context_loader.py`

5. **integration tools 反映ロジック**
   - tool 読込、重複回避、skill 反映、prompt text 生成を分離
   - 例: `domains/orchestration2/integrations/tool_reflection.py`

### 優先度 Low（段階導入）

6. **`_NoOpSkill`**
   - `engine/skills/noop.py` などへ移動
   - ただし将来、Skill 実体方式が固まるまで暫定維持でも可

7. **`create_engine_for_project` の分割**
   - 最終的に composer パターンへ
   - 例: `orchestration2/bootstrap/project_engine_builder.py`

---

## 3) 改善案

### 改善案A: 「設定」と「処理」の分離

- **設定（宣言的）**
  - graph, skills, default tool catalog
- **処理（命令的）**
  - DB読込、integration解決、engine組み立て

これにより、仕様変更（グラフ・スキル調整）時に Python ロジック改修を最小化できます。

### 改善案B: EngineBuilder/Composer 導入

`create_engine_for_project` を以下の手順オブジェクトに分解:
1. `register_core_tools()`
2. `register_integration_tools()`
3. `register_models_and_runtime()`
4. `register_skills_roles_graphs()`
5. `register_agent()`
6. `load_prompt_context()`

→ デバッグ点が明確になり、テストしやすくなります。

### 改善案C: 依存方向の整理

- `engine_setup` が `tools.library.*` を大量 import する構造を、
  「catalog module が提供する定義」に寄せる
- import の密結合を減らし、ツール追加時の変更点を局所化

### 改善案D: 明示的な PromptData 受け渡し

`engine._prompt_data` の私有属性直接格納は暗黙依存になりやすいため、
- 例: `engine.set_prompt_data(prompt_data)` のような public API
- または `run(..., metadata=...)` へ統一

### 改善案E: 例外処理の可観測性向上

現状は warning ログ中心のため、
- どの preload 項目が欠落したか
- fallback が発生したか

を構造化ログ（key-value）で出せるようにすると運用しやすいです。

---

## 4) 変更スコープ

## 4-1. 最小スコープ（低リスク）

- 新規追加
  - `domains/orchestration2/config/graphs/project_assistant.yaml`
  - `domains/orchestration2/config/skills/default_skills.py`
  - `domains/orchestration2/tools/catalog/default_catalog.py`
- 既存変更
  - `engine_setup.py`（上記を import するだけに薄くする）

**期待効果**
- 単一ファイル肥大の解消
- グラフ/スキル/ツール構成変更の差分が明確化

## 4-2. 中間スコープ（推奨）

- 最小スコープ +
- `prompt_context_loader.py` 新設
- integration reflection ロジック分離
- 単体テスト追加（catalog, graph load, prompt loader）

**期待効果**
- 変更耐性・テスト容易性の改善
- 障害箇所特定の高速化

## 4-3. 拡張スコープ（将来）

- builder/composer 導入
- engine 公開 API 拡充（prompt data セット）
- 設定ファイルの schema validation

**期待効果**
- 中長期的な保守性向上
- チーム開発での衝突軽減

---

## 推奨移行ステップ（実施順）

1. `PROJECT_GRAPH_YAML` を YAML ファイルへ移す
2. `SKILL_DEFS` を config module へ移す
3. `_get_all_tools` の tool_classes を catalog 化
4. `_load_prompt_components` を loader 化
5. integration reflection 分離
6. 最後に `create_engine_for_project` を builder 化

この順番なら、実行系 API 互換を維持しながら段階移行できます。
