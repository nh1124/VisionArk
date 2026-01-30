# Vision Ark メモ機能 (Notes) 実装提案レポート (改訂版)

## 1. 詳細な仕様

### 1.1 UI/UX 仕様

#### サイドメニュー (Global Navigation)
- **アイコン追加**: サイドメニューに「Notes」アイコン（Lucideの `StickyNote`）を追加。全プロジェクトのメモを横断的に管理。

#### プロジェクト内統合
- **独立した機能としての統合**: 既存の Artifact/Reference タブ内ではなく、プロジェクト画面のヘッダーまたはサイドナビゲーションに**専用の「Notes」ボタン/アイコン**を配置。
- **クイックメモ**: プロジェクト作業中にワンクリックでメモ作成・参照ができるオーバーレイまたは専用パネルを提供。
- **自動紐付け**: プロジェクト画面から作成したメモは、そのプロジェクトIDと自動的に関連付けられる。

#### メモ一覧・管理
- **フィルタリング**: プロジェクト別、日付別、タイプ別（テキスト/音声）でフィルタリング可能。
- **検索**: 全文検索機能。
- **カード型デザイン**: メモのタイトル、作成日、プロジェクト名、本文の抜粋を表示。音声メモの場合は波形プレビューや再生ボタンを表示。

#### 音声メモ作成 UI
- **録音コントロール**: 最新のブラウザAPIを使用した録音インターフェース。
- **視覚フィードバック**: 録音中の音量レベルメーター。

---

### 1.2 実装面仕様

#### データモデル (Backend)
- **`Note` クラス (新規)**: `UploadedFile` の拡張は行わず、独立したエンティティとして実装。
    - `id` (UUID): メモの一意識別子
    - `user_id` (UUID): 所有者のユーザーID
    - `project_id` (UUID, Nullable): 関連プロジェクト。
    - `title` (String): メモのタイトル
    - `content` (Text): テキスト本文（Markdown対応）
    - `audio_file_id` (UUID, Nullable): 録音データ（`uploaded_files` テーブルへの外部キー）
    - `created_at`, `updated_at`: タイムスタンプ
- **ファイル管理**: 音声データ自体は既存の `UploadedFile` 仕組みを利用して保存。

#### 最新の Gemini Audio API 連携
- **ネイティブ音声理解**: `google-genai` SDK を使用し、Gemini 1.5 Pro/Flash のマルチモーダル機能を直接利用。
- **実装方法**:
    - 音声ファイルを `client.files.upload` でアップロード。
    - エージェントがメモを参照する際、音声データがある場合は Gemini に直接渡して音声内容に基づいた回答・処理を行わせる。
    - 音声の文字起こしをバックグラウンドで生成し、検索インデックスに登録。

---

## 2. 実現方法

### Backend (Python/FastAPI)
1.  **データベース**: `models/database.py` に `Note` クラスを新規実装。
2.  **API**: `/api/notes` ルーターを新設し、CRUD 操作を実装。音声アップロードは `file_service.py` を経由。
3.  **エージェントツール**: `tools/library/notes.py` を作成。

### Frontend (Next.js/React)
1.  **ページ**: `/app/notes/page.tsx` (Global) およびプロジェクト内専用ビューの作成。
2.  **音声録音**: `MediaRecorder` API を使用したカスタムフックの実装。

---

## 3. 変更スコープ

| ファイルパス | 変更内容 |
| :--- | :--- |
| `core/backend/models/database.py` | `Note` クラスの新規追加。 |
| `core/backend/api/notes.py` | **(新規)** メモ管理用 API の実装。 |
| `core/backend/services/note_service.py` | **(新規)** メモと音声処理のビジネスロジック。 |
| `core/backend/tools/library/notes.py` | **(新規)** エージェント用メモ操作ツール。 |
| `core/frontend/components/Sidebar.tsx` | グローバルナビに「Notes」追加。 |
| `core/frontend/app/projects/[projectId]/page.tsx` | プロジェクト専用の Notes 起動用アイコン追加。 |
| `core/frontend/app/notes/page.tsx` | **(新規)** 全メモ管理ページ。 |

---

## 5. ステップバイステップの実装プラン

1.  **Phase 1: 基盤整備**
    - データベースマイグレーション（モデル作成）。
    - 物理ディレクトリ `notes/` の作成とパーミッション設定。
2.  **Phase 2: テキストメモ機能**
    - 基本的な CRUD API とフロントエンド UI の作成。
    - プロジェクトとの紐付けロジックの実装。
3.  **Phase 3: 音声メモ機能**
    - フロントエンドでの録音コンポーネント開発。
    - 音声ファイルのアップロードと再生機能。
4.  **Phase 4: エージェント連携**
    - ノートツールの実装と、エージェントのシステムプロンプトへの統合。
    - 音声メモの Gemini File API 連携テスト。
