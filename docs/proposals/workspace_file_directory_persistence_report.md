# Workspaceでファイル／ディレクトリ保存を可能にするための検討レポート

## 1. 現在のworkspaceの使用状況

### 1.1 データモデル
現行の shared workspace は `workspace_items` を中心に構成され、1レコードが1つの「テキスト主体の知識アイテム」を表します。
主な属性は `path`, `title`, `content`, `tags`, `scope`, `version` で、**バイナリファイル本体やディレクトリエントリを表現する型はありません**。

- `WorkspaceItem.content` は `Text` 型（インライン本文）
- バージョン履歴は `workspace_item_versions` に `content` スナップショットとして保存
- プロジェクト関連付けは `workspace_bindings` で管理

### 1.2 API利用
`/api/workspace` は現在、以下のユースケースに最適化されています。

- アイテムCRUD（`/items`）
- 改訂履歴（`/items/{item_id}/versions`）
- プロジェクトバインディング（`/projects/{project_id}/bindings`）
- プロジェクト文脈解決（`/projects/{project_id}/resolve`）

入力スキーマも `content: Optional[str]` を中心としており、アップロード・ダウンロード・ディレクトリ作成などのファイル操作APIは未提供です。

### 1.3 実行時コンテキストへの組み込み
オーケストレーション層では `WorkspaceService.resolve_context()` で取得したアイテム群を
`## Shared Workspace Context` としてプロンプトに連結しています。
ここでも `title/path/tags/content` 前提のため、ファイル本体参照（URI, MIME, サイズ等）の注入設計は未実装です。

### 1.4 既存の近接機能
一方で、プロジェクト配下のファイル管理 (`uploaded_files`) には UUID 管理・ディレクトリ種別・物理保存の仕組みが存在します。
このため「workspaceでも同等の保存機能を提供する」際は、既存の `FileService`/UUIDレジストリの再利用余地があります。

---

## 2. ファイル／ディレクトリ保存を可能にする場合の仕様策定

### 2.1 目標
- shared workspace 内で、**テキストアイテムとファイル／フォルダを同一階層で扱える**こと
- 既存 `workspace_items` の後方互換維持
- 権限・監査・バージョンの一貫性確保

### 2.2 論理モデル（提案）
`workspace_items` を汎用ノード化し、種類を明示します。

- `item_type`: `note | file | directory`
- `path`: workspace内論理パス（例: `company/policies/security.pdf`）
- `content`: `note` のみ利用
- `storage_path`, `mime_type`, `size_bytes`, `checksum`: `file` のみ利用
- `is_deleted`, `version`: 既存踏襲

補助テーブル（必要に応じて）：
- `workspace_item_versions` 拡張
  - `note`: テキスト差分／スナップショット
  - `file`: メタデータ + 世代参照（実体はオブジェクトストレージ／ローカル）

### 2.3 操作仕様（API）
最低限、以下のAPIを定義します。

1. ノード作成
   - `POST /api/workspace/items`（`item_type=directory|note`）
2. ファイルアップロード
   - `POST /api/workspace/files`（multipart）
3. 一覧取得
   - `GET /api/workspace/tree?path=...`（階層表示）
4. コンテンツ取得
   - `GET /api/workspace/items/{id}`（noteメタ）
   - `GET /api/workspace/files/{id}/content`（download/stream）
5. 更新
   - `PATCH /api/workspace/items/{id}`（rename/move/title/tags）
   - `PUT /api/workspace/files/{id}`（差し替え）
6. 削除
   - `DELETE /api/workspace/items/{id}`（directoryは再帰）

### 2.4 バリデーション／セキュリティ
- パス正規化（`..`, 絶対パス, hidden path を拒否）
- 所有者境界（`owner_id`）と既存ACL準拠
- MIME/サイズ上限（例: 25MB, 許可拡張子）
- ディレクトリ削除時のトランザクション整合（DB/物理ストレージ）

### 2.5 コンテキスト解決仕様
`resolve_context` は既存互換を維持しつつ、以下に拡張します。

- `note`: 従来通り本文を連結
- `file`: プロンプトには要約メタ（名前, MIME, サイズ, 取得ID）を連結
- 必要時のみファイル内容を遅延取得（トークン過剰消費を防止）

---

## 3. 変更スコープ

### 3.1 バックエンド（必須）
- `shared.database`
  - `workspace_items` スキーマ拡張（`item_type` ほか）
  - マイグレーション追加
- `domains.workspace.workspace_service`
  - file/directory CRUD, move/rename, recursive delete
  - content/version 取り扱い分岐
- `api/workspace.py`
  - upload/download/tree系エンドポイント追加
- `domains/orchestration2/prompting/prompt_context_loader.py`
  - fileノードのコンテキスト注入ロジック追加

### 3.2 ストレージ層（必須）
- 既存 `FileService` の再利用 or `WorkspaceFileService` 新設
- 保存先規約（例: `/data/users/{user_id}/workspace/`）
- チェックサムと重複排除戦略（任意）

### 3.3 クライアント／ツール（推奨）
- orchestration tool の拡張
  - `create_workspace_directory`
  - `upload_workspace_file`
  - `read_workspace_file`
  - `move_workspace_item`
- UI（存在する場合）
  - tree表示
  - ドラッグ&ドロップアップロード

### 3.4 非機能
- 監査ログ（誰が何を保存/更新/削除したか）
- 性能目標（tree一覧P95, upload処理時間）
- 障害時リカバリ（孤児ファイルのクリーンアップジョブ）

---

## 4. 導入ロードマップ

### Phase 0: 設計確定（1週間）
- API/DB仕様凍結
- 互換性方針（既存workspace itemの移行方式）決定
- 上限値（サイズ, MIME, 同時アップロード）決定

### Phase 1: データ層拡張（1週間）
- `workspace_items` に `item_type` 等を追加
- マイグレーション実装（既存データは `note` 扱い）
- 単体テスト整備

### Phase 2: サービス/API実装（1〜2週間）
- directory作成・tree取得・再帰削除
- file upload/download/replace
- 権限チェック・パス検証

### Phase 3: オーケストレーション統合（1週間）
- workspace file/directory用ツール追加
- `resolve_context` の file-aware 化
- プロンプト肥大化抑制（遅延読込）

### Phase 4: UI/運用整備（1週間）
- tree UI と操作導線整備
- 運用指標のダッシュボード化
- 障害手順書（復旧、クリーンアップ）作成

### Phase 5: 段階リリース（継続）
- Feature Flagで限定公開
- 既存ユーザーから順次展開
- 利用ログを基に上限値・UXをチューニング

---

## 補足: 採用戦略
最初から「workspace専用の新規巨大機構」を作るより、既存の project file 管理で実績のある UUID管理・保存手法を流用し、
workspaceドメインに合わせた最小拡張で立ち上げる方が、開発コストと運用リスクの両面で合理的です。
