# LLMモデル管理方式の見直しレポート

## 1. 現状の実装内容

### 1-1. モデル選択の全体フロー
- フロントエンドは選択モデルを `X-Preferred-Model` ヘッダーでバックエンドに渡し、バックエンド側で `provider:model` を解釈して実行エンジンを決定する方式です。
- `parse_model_spec()` は `openai:gpt-4.1-mini` のような明示形式に加え、`gpt-` / `claude-` / `gemini-` などプレフィックス推定にも対応しています。

### 1-2. 現状のモデル定義の所在
- 利用可能モデル一覧（表示名・ID・provider紐付け）は、現時点では **Webフロントの静的配列** `MODEL_OPTIONS` にハードコードされています。
- `getProviderForModel()` も同ファイル内の固定ルール（配列一致 + prefix fallback）で判定しています。

### 1-3. バックエンドの責務（現状）
- バックエンドは「どの provider を使うか」「設定済みAPIキーがあるか」を判断して実行します。
- `model_router.py` は provider 解決と API key の取得を担っていますが、モデル一覧の配信は行っていません。
- `/api/settings/status` は provider単位（gemini/openai/anthropic）の設定有無を返しますが、モデルカタログは返しません。

### 1-4. 現状の課題
1. **モデル更新時にフロント修正が必要**
   - モデル追加・改名のたびにフロントのデプロイが必要です。
2. **クライアント間でモデル一覧のズレが起こりやすい**
   - WebとNativeで個別実装になると、更新タイミング差で不整合が発生します。
3. **サーバーが受け付けるモデルとUI表示モデルの整合保証が弱い**
   - バックエンドは基本的に provider と key 存在で判定し、モデルIDそのものの「許可リスト検証」は薄い構造です。

---

## 2. モデル管理方法の改善案

方針として、提案どおり **「バックエンドをモデルカタログのSingle Source of Truthにする」** 方式が妥当です。

### 2-1. 推奨アーキテクチャ

#### A. モデルカタログをバックエンドで一元管理
- 例: `core/backend/infrastructure/llm/model_catalog.py` を新設し、以下を定義。
  - provider（`gemini/openai/anthropic/...`）
  - model id（実送信用）
  - display name（UI表示）
  - capability metadata（任意: reasoning, vision, max_tokens, deprecation等）
  - status（active / preview / deprecated）
  - priority（UIソート用）

#### B. モデルカタログ取得APIを提供
- 例: `GET /api/llm/models`
- レスポンス案:
  - `providers`: provider一覧（表示名・設定可否）
  - `models`: providerごとのモデル一覧
  - `default_model`
  - `version`（キャッシュ制御用）

#### C. クライアントはAPI結果で描画
- Web/Nativeともに同一APIを参照。
- ローカル静的配列は廃止し、API取得失敗時の最低限fallbackのみ保持。

#### D. サーバー側で受理モデルを検証
- チャット実行時、受信した `X-Preferred-Model` がカタログに存在するか検証。
- 不正・廃止モデルなら `default_model` や provider既定モデルへフォールバックし、ログに記録。

### 2-2. 運用観点での追加提案
- **段階リリース**: `enabled_for` フィールドで Web/Native/Beta ユーザー単位に公開制御。
- **非推奨管理**: deprecatedモデルはUI非推奨表示しつつ既存セッションのみ許容。
- **観測性**: モデル選択頻度、失敗率、フォールバック率をメトリクス化。

### 2-3. 期待効果
- モデル更新時の作業を「バックエンド変更 + 1回デプロイ」に集約。
- Web/Nativeの表示不整合を解消。
- サーバー主導で安全にモデル廃止・差し替えが可能。

---

## 3. 変更スコープ

## 3-1. バックエンド（必須）
1. **モデルカタログ定義の追加**
   - 新規モジュール追加（例: `model_catalog.py`）。
2. **モデル一覧APIの追加**
   - 例: `api/llm.py` 新設 + router登録。
3. **モデル妥当性チェックの追加**
   - `agents.py` / `worker.py` のモデル解決直前でカタログ照合。
4. **既存ルーターとの責務分離**
   - `model_router.py`: provider解析中心
   - `model_catalog.py`: 利用可能モデル定義中心

## 3-2. Webフロント（必須）
1. `MODEL_OPTIONS` の静的定義依存を削減。
2. 初回ロード時に `/api/llm/models` を取得してモデルセレクタへ反映。
3. API失敗時のみ限定fallback（既定モデル1つ程度）を表示。

## 3-3. Nativeフロント（必須）
1. Webと同一の `/api/llm/models` を参照。
2. 表示・選択・永続化（ローカル保存）をAPIレスポンスベースへ統一。

## 3-4. 既存データ・互換性（重要）
1. `provider:model` 文字列形式は維持（後方互換）。
2. 旧IDが来た場合のマッピングテーブルを用意（必要時）。
3. `default_model` が廃止された場合の自動置換ロジックを実装。

## 3-5. 実装順（推奨）
1. バックエンドにカタログ + API追加（既存挙動は維持）。
2. WebをAPI参照へ切替（fallback付き）。
3. NativeをAPI参照へ切替。
4. 安定後に静的モデル定義を削除。

---

## 結論
- ご提案の「バックエンド管理 + API配信」は、モデル更新頻度が高い運用に対して非常に適した設計です。
- 特に **Web/Native両クライアントを同時運用する前提** では、モデル定義の一元化が保守性・整合性・運用安全性の面で有効です。
- 実装時は、`provider:model` 互換を維持しつつ、サーバー側のモデル妥当性検証と段階公開制御を合わせて導入するのが最も効果的です。
