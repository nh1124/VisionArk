# Outlook Calendar (Microsoft Graph) Integration

VisionArk (LBS) と Microsoft Outlook を双方向同期させるためのインテグレーションです。

## Shared App Model
このインテグレーションは**Shared App モデル**を採用しています。
システム管理者が Azure Portal で1つのエンタープライズアプリ（またはアプリ登録）を行い、全ユーザーがそのアプリ権限の下で自身の Outlook カレンダーを連携します。

## セットアップ (Setup)

### 1. Azure Portal / Entra ID の設定
1. [Azure Portal](https://portal.azure.com/) の「アプリの登録」で新規登録を行います。
2. **認証** セクションでリダイレクト URI を設定します。
   - リダイレクト URI: `http://localhost:8000/api/outlook/callback`
3. **証明書とシークレット** でクライアント シークレットを作成します。
4. **API のアクセス許可** で以下の権限を追加します。
   - `Calendars.ReadWrite`
   - `offline_access`

### 2. 環境変数の設定
`.env` ファイルに以下の変数を追加してください。

```env
OUTLOOK_CLIENT_ID=your_client_id_here
OUTLOOK_CLIENT_SECRET=your_client_secret_here
OUTLOOK_REDIRECT_URI=http://localhost:8000/api/outlook/callback
```

## 機能 (Features)

- **Microsoft Graph 連携**: 最新の Microsoft Graph API を使用してカレンダーを操作します。
- **インテリジェント同期**: 外部の予定を LBS のスケジュール負荷として認識し、 VA 内のタスク再計算に反映させます。
- **エージェント・ツール**: AIエージェントが `list_outlook_events` ツールを使用してカレンダーの確認や予定の作成・削除を自律的に行えます。

## 開発者ノート (Developer Notes)

- API実装: `core/backend/integrations/outlook/api.py`
- 同期ロジック: `core/backend/integrations/outlook/handlers.py`
- クライアント: `core/backend/integrations/outlook/client.py`
