# VisionArk 共有ワークスペース設計レポート（改訂）

## 1. 現在の workspace の状態

### 1.1 物理構成（現行）
- 現行設計では `data/users/{user_id}/{project_id}` が最小単位で、実質的に「プロジェクト中心」の構造です。  
- プロジェクト固有の運用は `.visionark/project_rules.json` と `artifacts/PLAN.md` で管理され、Ruler の前提はプロジェクト単位です。  
- 一方で、ユーザーがプロジェクト横断で再利用したい情報（個人情報、会社情報、価値観、長期方針など）を格納する **共有workspaceの標準領域** は未定義です。

### 1.2 論理構成（現行）
- `IntegrationContext` は `user_id` と任意の `project_id` を持ちますが、共有workspaceの構造や参照対象集合を明示するフィールドはありません。  
- そのため、共通情報は「都度プロジェクトにコピー」「都度チャットで説明」になりやすく、再利用・更新追跡・アクセス制御が運用依存になります。

### 1.3 現状課題（共有観点）
1. **再利用の分散**: 共通情報が各 project に重複配置されやすい。  
2. **更新整合性の不足**: 1箇所更新が全体に反映されない。  
3. **境界管理の曖昧さ**: private/org/project の公開範囲を明示しづらい。  
4. **運用自由度の不足**: ユーザーごとに最適な整理軸を持ちにくい。

---

## 2. 新しい workspace の提案

### 2.1 設計方針
- **Workspace-first + User-defined organization**: 「共有workspaceを持つ」ことを標準化し、内部のフォルダ構造・分類軸はユーザーが自由に決める。  
- システムが強制するのは最小メタデータのみ（識別子、所有者、公開範囲、版）。内容カテゴリは固定しない。  
- 既存の project workspace を壊さず、後方互換で段階導入する。

### 2.2 提案する論理モデル（最小）

#### 共通オブジェクト
- `workspace_item`（共有workspace内の任意アイテム）
- `workspace_item_version`（改訂履歴）
- `workspace_binding`（project への参照バインド）
- `workspace_acl`（アクセス制御）

#### 必須メタ（最小）
- `item_id`, `owner_id`, `scope(private/org/project)`, `version`, `path`, `tags`, `updated_at`

> ポイント: `domain` を固定列挙しない。必要ならユーザー定義タグやラベルで整理。

### 2.3 提案ディレクトリ（ファイル運用を継続する場合）

```text
data/
└── users/
    └── {user_id}/
        ├── workspace/                # 共有workspace（内部構造はユーザー自由）
        │   ├── _index.json           # システム管理メタ（必須）
        │   ├── _acl.json             # システム管理ACL（必須）
        │   ├── profile/
        │   │   └── ...
        │   ├── company/
        │   │   └── ...
        │   ├── vision/
        │   │   └── ...
        │   └── any_user_defined_dirs/
        │       └── ...
        └── projects/
            └── {project_id}/
                ├── artifacts/
                ├── docs/
                └── .visionark/
```

> 例として `profile/company/vision` を示すが、これは固定仕様ではなく単なる初期テンプレート。

### 2.4 参照モデル（優先順位）
1. project に明示的に bind された workspace item
2. scope=`project` の workspace item
3. scope=`org` の workspace item
4. scope=`private` の workspace item
5. 現在のチャット文脈

上記をオーケストレーション層の共通resolverで統一し、特定の旧ノード機能に依存しない設計とする。

### 2.5 最小APIセット（例）
- `POST /api/workspace/items`（作成）
- `GET /api/workspace/items`（一覧・検索）
- `GET /api/workspace/items/{item_id}`（取得）
- `POST /api/workspace/items/{item_id}/versions`（改訂）
- `POST /api/workspace/projects/{project_id}/bindings`（project へバインド）

---

## 3. 変更スコープ

### 3.1 バックエンド
- `workspace` ドメイン追加（Item / Version / Binding / ACL）
- `workspace_service` 追加（CRUD, versioning, policy check）
- `IntegrationContext` 拡張（`workspace_scope`, `bound_items` など）
- 知識参照・文脈取得経路を workspace-aware 化（共通resolver経由）

### 3.2 データ・ストレージ
- 追加テーブル（またはメタ管理）
  - `workspace_items`
  - `workspace_item_versions`
  - `workspace_bindings`
  - `workspace_acl`
- 既存 path から `projects/` 配下への移行ジョブ

### 3.3 フロントエンド
- `Workspace Hub`（自由配置のファイル/ノート管理）
- `Project Bindings`（projectごとに参照許可を付与）
- チャットUIに「参照中workspace項目」バッジ表示

### 3.4 ガバナンス・運用
- `.visionark/project_rules.json` に `workspace_bindings` セクション追加
- 監査ログ（誰が何を参照/更新したか）
- 機密情報向けの redact/export ルール

---

## 4. 導入のためのロードマップ

### Phase 0: 設計確定（1週間）
- 最小メタデータ仕様とACL仕様の確定
- 旧構成との互換方針（resolver / migration）確定
- API/DBのADR作成

### Phase 1: 基盤実装（2週間）
- `workspace_items` 系テーブル + CRUD API
- 共通resolver実装（参照優先順位）
- `IntegrationContext` の後方互換拡張

### Phase 2: project連携（1〜2週間）
- Project Bindings API
- 主要参照フローを workspace-aware 化
- UIに参照バッジ表示

### Phase 3: データ移行（1週間）
- 既存 project 内の共通情報候補を抽出し workspace へ昇格
- path移行（`{user_id}/{project_id}` → `{user_id}/projects/{project_id}`）
- 互換レイヤーで段階切替

### Phase 4: 運用安定化（継続）
- 監査ログ/運用ガイド整備
- 定期レビュー運用（更新期限・鮮度管理）
- 利用メトリクス可視化（参照頻度、重複率、未参照項目）

---

## 5. この改訂方針で得られる効果
- **自由度**: 内部整理をユーザー主導で最適化できる。  
- **整合性**: project横断で単一ソースを参照可能。  
- **安全性**: scope/ACLで公開境界を統一管理。  
- **拡張性**: 将来の外部連携（Notion/Drive/CRM等）にも接続しやすい。

