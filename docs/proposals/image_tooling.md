# nanobanana pro2対応に向けた事前調査レポート

## 0. 目的と前提

本レポートは、以下3点を事前整理するための調査結果です。

1. 現在の画像系 tool 実装の把握
2. 新しい画像生成 tool 仕様案（nanobanana pro2 / マルチプロバイダ対応）
3. 変更スコープ（どのレイヤーに何を入れるか）

想定方針は「Gemini系設定時は nanobanana を使用し、それ以外は各プロバイダの画像生成機能にフォールバック」です。

---

## 1. 現在の画像系 tool 実装

### 1.1 画像生成 tool の実体

- 画像生成は `GenerateImageTool`（`generate_image`）として実装されている。
- 現状は `google.genai` クライアントを直呼びし、モデルは固定で `gemini-3-pro-image-preview` を使う。
- 入力は `prompt` と任意 `filename` のみで、参照画像（image-to-image）入力は仕様上も実装上も未対応。
- 生成結果は `response.parts` から `inline_data` を拾ってバイナリ保存する実装。

### 1.2 APIキー/クライアント取得

- tool 基盤 `get_user_api_key` / `get_gemini_client` は Gemini 専用実装。
- そのため `generate_image` は現状 Gemini 専用 tool になっている。

### 1.3 tool 登録と利用可能スキル

- `GenerateImageTool` はコアカタログに含まれており全体的に登録される。
- `document_creation` skill でも `generate_image` が許可されている。

### 1.4 「モデル画像ファイルを渡す」現状

- 現在、Gemini 実行時にのみ `read_file_chunk` が Files API へアップロードし、`provider_parts` へ `Part.from_uri` を入れられる。
- これにより **GeminiEngine では** 次ターン入力へネイティブ part を注入可能。
- 一方、OpenAI/Anthropic の engine 実装は tool 結果を文字列として渡すのみで、`provider_parts` 取り込みはない。

#### 現状のボトルネック

1. `generate_image` が Gemini 固定（モデル固定＋SDK固定）
2. 画像参照入力（複数画像、重み、マスク等）の引数設計がない
3. 対話的な改稿（前回画像を継続参照）を表現する状態管理がない
4. OpenAI/Anthropic 側には「バイナリ参照を次ターンへ渡す」仕組みが未整備

---

## 2. 新しい画像生成 tool 仕様案

## 2.1 設計方針

- **単一公開 tool 名を維持**: 互換性のため公開名は当面 `generate_image` を維持。
- **内部を provider ルーティング化**: `ctx.engine_kind` と設定モデルから、実行バックエンドを選ぶ。
- **画像参照入力を first-class 化**: `reference_images` を正式パラメータ化。
- **対話処理を first-class 化**: `conversation_id` / `seed_artifact` で継続編集を可能に。
- **成果物は常に artifacts 保存**: UI/後続 tool 連携を単純化。

## 2.2 提案ツールI/F（v2）

```json
{
  "type": "object",
  "properties": {
    "prompt": {"type": "string"},
    "negative_prompt": {"type": "string"},
    "reference_images": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "path": {"type": "string", "description": "project相対パス"},
          "role": {"type": "string", "enum": ["style", "subject", "composition", "mask"]},
          "weight": {"type": "number", "minimum": 0, "maximum": 2}
        },
        "required": ["path"]
      }
    },
    "size": {"type": "string", "enum": ["1024x1024", "1024x1536", "1536x1024"]},
    "quality": {"type": "string", "enum": ["standard", "high"]},
    "n": {"type": "integer", "minimum": 1, "maximum": 4},
    "filename_prefix": {"type": "string"},
    "conversation_id": {"type": "string"},
    "edit_instruction": {"type": "string"},
    "provider_hint": {"type": "string", "enum": ["auto", "gemini", "openai", "anthropic"]}
  },
  "required": ["prompt"]
}
```

### 2.3 動作仕様

1. **Provider決定**
   - 既定は `auto`。
   - `provider_hint` 指定があれば優先。
   - なければ `ctx.engine_kind` → モデル spec で決定。

2. **Gemini系（nanobanana）**
   - Gemini 設定時は nanobanana pro2 を優先利用。
   - `reference_images` は Gemini Files API URI または inline bytes に正規化して送信。

3. **非Gemini系**
   - OpenAI/Anthropic などは各プロバイダ画像APIを使用。
   - 参照画像対応可否を provider capability で判定し、未対応項目はエラーまたは degraded 実行。

4. **対話処理**
   - `conversation_id` 指定時は、直近生成のメタ（prompt, seed, 出力path, provider）を参照して編集。
   - `edit_instruction` があれば previous image への編集指示として優先。

5. **出力**
   - `artifacts/images/...` に保存。
   - ToolResult は JSON で返却（保存パス、provider、model、seed、conversation_id、warnings）。

### 2.4 戻り値仕様（例）

```json
{
  "success": true,
  "provider": "gemini",
  "model": "nanobanana-pro2",
  "conversation_id": "imgconv_20260301_abc123",
  "outputs": [
    {
      "path": "artifacts/images/nbp2_city_v1.png",
      "width": 1536,
      "height": 1024,
      "mime_type": "image/png"
    }
  ],
  "warnings": []
}
```

---

## 3. 変更スコープ

## 3.1 必須（MVP）

1. **tool実装更新**
   - `core/backend/domains/orchestration2/tools/library/ai.py`
   - `GenerateImageTool` を provider ルーティング構造へ改修。

2. **tool共通基盤拡張**
   - `core/backend/domains/orchestration2/tools/base.py`
   - Gemini専用APIキー取得から、provider指定APIキー取得関数を追加（または `model_router` 利用）。

3. **画像参照の解決レイヤー追加**
   - `reference_images[].path` を project 内ファイルに解決するヘルパー追加。
   - MIME判定・サイズ制限・存在確認を共通化。

4. **戻り値標準化**
   - 既存の「文字列メッセージ」中心から JSON envelope へ統一。

## 3.2 推奨（安定運用）

5. **Provider capability 定義**
   - 例: `supports_image_edit`, `supports_multi_image_ref`, `max_images`。
   - providerごとの差分を if 文で散らさないためのマップ化。

6. **会話状態ストア（軽量）**
   - 画像生成履歴（conversation_id 単位）を artifacts か DB に保持。
   - 最初は artifacts 側 JSON でも可（移行しやすさ重視）。

## 3.3 影響範囲（要確認）

- skill定義（`document_creation`）は tool 名維持なら変更最小。
- Prompt側の tool usage 例文更新（新パラメータ説明）が必要。
- フロントエンドは tool API 直呼びでなければ影響小だが、生成画像プレビュー導線は改善余地あり。

---

## 4. 段階的導入プラン

1. **Phase 1**: `generate_image` v2 引数だけ先に導入（内部は Gemini 優先）
2. **Phase 2**: OpenAI/Anthropic 画像APIアダプタ実装
3. **Phase 3**: conversation_id による編集継続

---

## 5. 結論

- 現在の実装は「Gemini固定の単発生成」には十分だが、
  - 参照画像入力
  - 対話的編集
  - マルチプロバイダ画像生成
  には未対応。
- まずは `generate_image` の公開I/Fを拡張し、内部を provider ルーティング化するのが最小リスク。
- nanobanana pro2 対応はこの構造変更の上に載せると、将来の provider 追加・切替にも耐えやすい。
