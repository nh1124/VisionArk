# LLMマルチプロバイダー対応 事前調査レポート（Gemini → OpenAI / Claude対応）

作成日: 2026-02-25  
対象リポジトリ: VisionArk

---

## 1. 現在のLLM使用方法（As-Is）

### 1-1. 全体像
- 現在の実装は **Gemini前提** で統一されている。
- Orchestrationの中核（`orchestration2`）は、
  - 単発補完向け `LLMProvider` 抽象（`complete`）
  - マルチターン実行向け `LLMEngine` 実装（`GeminiEngine`）
  の2層で動いているが、実体はGemini専用。

### 1-2. バックエンド構成
- `LLMProvider` プロトコルは抽象化されている（`complete(messages, system, tools, model)`）。
- ただし実装クラスは `GeminiLLMProvider` のみで、Google GenAI SDKに直接依存。
- オーケストレーション本体の実行エンジンも `GeminiEngine` 固定で組み立てられる。

### 1-3. 呼び出し箇所（主な経路）
1. **Project実行経路（メイン）**
   - `create_engine_for_project()` が `GeminiEngine` を生成し `engine.register_engine(...)`。
2. **補助API/ツール**
   - Project作成時のプロンプト生成（`/api/agents/project/create-from-prompt`）で `GeminiLLMProvider` を直接利用。
   - タスク分解API（`/api/decompose`）も `GeminiLLMProvider` 直呼び。
   - `recursive_writer` ツールも `GeminiLLMProvider` 直呼び。

### 1-4. 設定・認証・UIの現状
- `UserSettings.ai_config` はJSONで保持し、コメント上はOpenAIキー格納も想定しているが、
  実運用ロジックは **Geminiキーのみ有効**。
- `UserSettings` に復号アクセサは `gemini_api_key` のみ存在。
- `/api/settings/ai` も実際に更新するのは `gemini_api_key` のみ。
- `/api/settings/status` は `gemini` を必須要素として判定。
- フロントのモデル選択肢はGemini系列のみ（`MODEL_OPTIONS`）。
- サインアップ時もGemini API Key入力が必須。

### 1-5. 技術依存
- Python依存に `google-genai` はあるが、OpenAI/Anthropic SDK依存は未導入。

---

## 2. OpenAI / Claude 追加時の実装方法（To-Be案）

## 2-1. 方針
**推奨: Provider Adapter + Engine Factory パターン**

- 「モデル名」だけでなく「プロバイダー」を第一級概念として扱う。
- 以下を追加:
  1. `provider_id`（`gemini` / `openai` / `anthropic`）
  2. `model_id`（例: `gemini-2.5-flash`, `gpt-4.1-mini`, `claude-3-5-sonnet-latest`）
- 既存の `LLMProvider`/`LLMEngine` 抽象を活かし、Gemini実装と同レベルでOpenAI/Claude実装を並立させる。

## 2-2. 具体アーキテクチャ

### A. 設定ドメイン拡張
- `ai_config` を以下のように整理:
  - `gemini_api_key`
  - `openai_api_key`
  - `anthropic_api_key`
  - `default_provider`
  - `default_model`
- `UserSettings` に `openai_api_key` / `anthropic_api_key` の復号propertyを追加。
- `/api/settings/ai` で3キーを同等に更新・マスク可能に。

### B. Provider解決レイヤ
- 追加案: `infrastructure/llm/provider_registry.py`
  - `resolve_provider(provider_id, user_settings, preferred_model)` → 実体 `LLMProvider`
- 追加案: `infrastructure/llm/model_router.py`
  - `parse_model("openai:gpt-4.1-mini")` 形式や、
  - 互換のため `gemini-...` 単体指定も許容。

### C. 実行エンジン拡張
- 現状 `GeminiEngine` 固定のため、以下いずれか:
  1. `OpenAIEngine`, `AnthropicEngine` を追加し、`create_engine_for_project()`で分岐。
  2. もしくは `UniversalEngine` を新設し、内部でプロバイダー切替（初期実装は1の方が安全）。

### D. Tool Calling差分の吸収
- Gemini/OpenAI/AnthropicでTool呼び出しフォーマットが異なるため、
  共通内部表現（既存 `ToolCallRef` / `ToolResult`）への変換アダプタを各Engineに実装。
- 必要条件:
  - 引数JSON正規化
  - call_idの生成/保持
  - finish_reason（`tool_calls` / `stop`）統一

### E. API・UI拡張
- Header `X-Preferred-Model` は継続利用しつつ、`provider:model` 形式を受け入れる。
- フロント `MODEL_OPTIONS` を provider group化:
  - Gemini
  - OpenAI
  - Claude
- 設定画面に OpenAI/Anthropic のAPIキー欄を追加。
- `SystemStatus` は「Gemini必須」から「少なくとも1つのLLMプロバイダー必須」に変更。

### F. 段階的後方互換
- 既存ユーザーはGeminiのみ設定済みでも現行通り動作。
- `default_provider` 未設定時は、
  1) `gemini` を優先
  2) それも無ければ利用可能プロバイダーの先頭
  とする。

---

## 3. 変更スコープ（Impact）

## 3-1. 直接変更が必要な領域

### バックエンド
1. `shared/database.py`
   - `UserSettings` アクセサ追加（OpenAI/Anthropic）。
2. `api/settings.py`
   - AI設定の入出力/マスク対象拡張。
   - status判定ロジック変更。
3. `domains/orchestration2/bootstrap/project_engine_builder.py`
   - `GeminiEngine` 固定生成をFactory化。
4. `infrastructure/llm/`
   - OpenAI/Anthropic Provider/Engine 実装追加。
   - provider registry / model routing 追加。
5. Gemini直呼び箇所の置換
   - `api/agents.py`（create-from-prompt）
   - `api/decomposer.py`
   - `tools/library/writer.py`
   - `shared/service_helpers.py`（Gemini専用関数名と返却の見直し）
6. 依存パッケージ
   - `requirements.txt` に `openai`, `anthropic` を追加。

### フロントエンド
1. `lib/ModelContext.tsx`
   - モデル定義をマルチプロバイダー化。
2. `components/ChatInput.tsx` / `app/new/page.tsx`
   - 表示名ロジックをGemini固定文言から一般化。
3. `app/settings/page.tsx`
   - APIキー入力欄追加（OpenAI/Claude）。
4. `components/SystemStatus.tsx`
   - 必須条件表示を再定義。
5. `app/auth/signup/page.tsx`
   - Gemini必須入力の扱い再設計（任意化 or 最低1つ必須）。

## 3-2. 間接影響（要注意）
- プロンプト/ツール挙動の差で出力品質・安定性が変わる。
- レート制限/課金体系がプロバイダーごとに異なるため、将来的に使用量計測が必要。
- エラー体系（timeout, invalid_request, content_filter等）の統一ハンドリングが必要。

## 3-3. 非機能要件
- APIキー保存/マスク/復号の安全性を維持。
- 既存Geminiユーザーの無停止移行。
- 観測性（ログに provider/model を必ず記録）を強化。

---

## 4. 導入ロードマップ（実装エージェント向け）

## Phase 0: 仕様確定（0.5〜1日）
- Provider識別子、モデル命名規約、デフォルト選択ルールを確定。
- `X-Preferred-Model` の互換仕様確定（旧: modelのみ / 新: provider:model）。

**成果物**
- 設計メモ（データ構造、API仕様、フォールバック規則）

## Phase 1: 設定基盤の拡張（1日）
- `UserSettings` の復号property追加。
- `/api/settings/ai` の保存・マスク・取得を3プロバイダー対応。
- `/api/settings/status` を「いずれかのLLM設定でOK」に変更。

**受け入れ基準**
- 既存Gemini設定が壊れない。
- OpenAI/Anthropicキーの保存・再表示（masked）が可能。

## Phase 2: Provider Factory導入（1〜2日）
- `provider_registry` + `model_router` を追加。
- Gemini直呼び箇所（`create-from-prompt`, `decomposer`, `writer`）をFactory経由に置換。

**受け入れ基準**
- 呼び出し側が「Geminiクラス名」を知らなくても動く。
- `provider:model` 指定で適切なProviderが選ばれる。

## Phase 3: Orchestration Engineのマルチ化（2〜4日）
- `OpenAIEngine` / `AnthropicEngine` を追加（またはUniversalEngine）。
- `project_engine_builder` でユーザー設定 + headerからEngineを選択。

**受け入れ基準**
- 同一フローで Gemini/OpenAI/Claude が動作。
- ツール呼び出し往復（tool_call → tool_result → 再推論）が各Providerで通る。

## Phase 4: フロント対応（1〜2日）
- モデル一覧をProvider別表示。
- 設定画面のAPIキー入力追加。
- モデル表示文言を一般化。

**受け入れ基準**
- UIでProvider跨ぎモデルを選べる。
- バックエンドに期待通り header が送られる。

## Phase 5: QA / リリース（1〜2日）
- 回帰テスト（Gemini既存機能）。
- Provider別スモークテスト。
- ログ/メトリクス確認。

**受け入れ基準**
- 既存ユーザー影響なし。
- 障害時のフォールバック/エラーメッセージが明確。

---

## 5. 実装エージェント向けタスク分解（そのまま依頼可能）

1. `AIConfig` 拡張（openai/anthropic key + default provider/model）。
2. `provider_registry` と `model_router` の新規作成。
3. Gemini直呼びの4箇所を registry経由へ置換。
4. `project_engine_builder` の Engine Factory 化。
5. OpenAIEngine, AnthropicEngine の最小実装（text + tools）。
6. settings/status/signup/UI model selector の改修。
7. 回帰・統合テスト追加。
8. feature flag（例: `ENABLE_MULTI_PROVIDER_LLM=true`）で段階リリース。

---

## 6. 主要リスクと対策
- **リスク1: Tool calling仕様差**
  - 対策: Provider別アダプタ層で吸収し、内部型を固定。
- **リスク2: 既存Gemini品質劣化**
  - 対策: Gemini経路は初期段階でコード差分を最小化。
- **リスク3: 設定ミス時のUX低下**
  - 対策: status APIで不足設定を明示し、UIでガイド。
- **リスク4: 運用コスト増**
  - 対策: provider/model別の利用ログを追加し可視化。

---

## 7. 推奨結論
- VisionArkは既に抽象インターフェース（`LLMProvider`）を持っており、
  **構造的にはマルチプロバイダー化しやすい**。
- ただし実際の依存点はGeminiに広く埋め込まれているため、
  **「設定基盤 → Provider Factory → Engineマルチ化 → UI」** の順で
  段階導入するのが最も安全。
- 最初のマイルストーンは「Geminiを壊さずOpenAIの単発補完を通す」ことを推奨。
  その後にClaudeとマルチターン実行を拡張する。

