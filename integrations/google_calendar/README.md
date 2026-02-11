# Google Calendar Integration

VisionArk (LBS) と Google Calendar を双方向同期させるためのインテグレーションです。外部の予定を「動かせない予定（Hard Constraints）」として LBS のスケジュール計算に組み込みます。

## Shared App Model
このインテグレーションは**Shared App モデル**を採用しています。
システム管理者が Google Cloud Console で1つのアプリを登録し、全ユーザー（マルチクライアント）がそのアプリを介して自身のカレンダーを認証します。

## セットアップ (Setup)

### 1. Google Cloud Console の設定
1. [Google Cloud Console](https://console.cloud.google.com/) でプロジェクトを作成します。
2. **Google Calendar API** を有効にします。
3. **OAuth 同意画面** を構成します。
4. **認証情報** から「OAuth 2.0 クライアント ID」を作成します。
   - アプリケーションの種類: Web アプリケーション
   - 承認済みのリダイレクト URI: `http://localhost:8000/api/google-calendar/callback`

### 2. 環境変数の設定
`.env` ファイルに以下の変数を追加してください。

```env
GOOGLE_CLIENT_ID=your_client_id_here
GOOGLE_CLIENT_SECRET=your_client_secret_here
GOOGLE_REDIRECT_URI=http://localhost:8000/api/google-calendar/callback
```

## 機能 (Features)

- **OAuth2 認証**: ユーザーが設定画面の認証ボタンを押すと、アクセストークンとリフレッシュトークンが `service_registry` に暗号化されて保存されます。
- **カレンダー同期 (Import)**: Google Calendar の予定を LBS の `active=False` (固定) タスクとして取り込みます。
- **タスク書き出し (Export)**: VisionArk で確定したスケジュールを `[VA]` プレフィックス付きでカレンダーに同期します。
- **エージェント・ツール**: AIエージェントが `list_calendar_events` や `create_calendar_event` を使用して直接カレンダーを操作できます。

## 開発者ノート (Developer Notes)

- API実装: `core/backend/integrations/google_calendar/api.py`
- 同期ロジック: `core/backend/integrations/google_calendar/handlers.py`
- クライアント: `core/backend/integrations/google_calendar/client.py`
