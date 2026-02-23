# ファイル操作ツール改良 事前調査レポート

## 1. 現在のファイル操作方法（as-is）

### 1-1. エージェント向けツール層（orchestration2）
現在の標準カタログでは、ファイル操作に関する主要ツールとして以下が登録されています。

- `save_artifact`: `artifacts/` 配下への書き込み（上書きは `overwrite` 指定時のみ）。
- `read_reference`: プロジェクト配下ファイルの読取（`file_path/path/filename` を解決）。
- `list_files`: ディレクトリ一覧（`directory` または `path`）。
- `delete_artifact`: `artifacts/` 配下ファイル削除。
- `import_github_repo`: GitHub リポジトリを `refs/sources/github/` へ clone。
- 別系統として `workspace` 系ツール群（`list/read/create/update/move/delete`）があり、構造化コンテンツ管理を提供。

特徴:
- 返却形式は多くが「人間可読テキスト」中心で、厳密な構造化レスポンス（JSON オブジェクト）ではない。
- `read_reference` は 50,000 文字で切り詰めるため、大容量/長文ファイルの精密編集には不向き。
- Gemini 実行時は `read_reference` が File API アップロード経由の provider part を返せる。

### 1-2. 永続化・同期層（FileService）
`FileService` は以下を担います。

- 保存: `save_file` で実ファイル保存 + `UploadedFile` レコード作成。
- 削除: `delete_file`/`delete_path`。
- 圧縮DL: `zip_directory`。
- 同期: `sync_project_directory` で `refs/artifacts/files` を走査し DB と整合。

特徴:
- DB レジストリ（UUID）と物理ファイルのハイブリッド管理。
- 同期時に `IGNORED_DIRS` を除外しつつ再帰走査。
- ファイル名・パス変更に対しては「再同期で追従」する設計。

### 1-3. API 層
`/api/files` ルータでアップロード/一覧/内容取得/ダウンロード/削除を提供。

- UUID ベース操作（`/content/{file_id}`, `/download/{file_id}`, `DELETE /{file_id}`）
- 互換経路として path ベース取得 (`/project/{project_id}/{directory}/{file_path:path}`)
- フロントエンドは Next.js の proxy route 経由で backend に中継

## 2. 改善点（課題）

### 2-1. 「細かく操作」観点での機能ギャップ

1. **部分編集API不足**
   - 現状は「全文 read → 全文 write」が基本。
   - 行単位/範囲単位/差分適用（patch）操作がない。

2. **ファイル操作プリミティブ不足**
   - `rename/move/copy/mkdir/touch/stat/glob/find` が弱い（または workspace 側に偏在）。
   - artifacts と refs/files/workspace の操作UXが分断。

3. **構造化レスポンス不足**
   - `list_files` がテキスト行返却で、LLM が機械的に再利用しづらい。
   - エージェント間連携時にパース不安定が起きやすい。

4. **大容量ファイル取り扱いの粗さ**
   - `read_reference` は一律 truncate。
   - ページング/offset/line range 取得がない。

### 2-2. 信頼性・運用面の課題

1. **例外握り潰し**
   - 一部で `except Exception: pass` があり、失敗原因が観測しづらい。

2. **競合制御不足**
   - 並列エージェント実行時の同一ファイル更新に対し、ETag/バージョンチェックがない。

3. **API定義の不整合リスク**
   - `/api/files/download/{file_id}` が重複定義されており、将来の保守で混乱要因。

4. **権限制御の粒度不足**
   - ツール単位の粗い許可はあるが、「どのディレクトリ/パターンまで許可するか」の細粒度ポリシーが弱い。

## 3. 改善案（to-be）

### 3-1. 最小実装（Phase 1: 早期効果）

- 新規ツール追加:
  - `read_file_chunk(path, start_line, end_line | offset, length)`
  - `apply_text_patch(path, patches[], expected_hash)`
  - `move_file(src, dst, overwrite=false)`
  - `copy_file(src, dst, overwrite=false)`
  - `make_directory(path, parents=true)`
  - `get_file_stat(path)`
- 返却を**構造化JSON**化（少なくとも `success`, `path`, `bytes`, `hash`, `diagnostics`）。
- 失敗時は必ず原因コードを返す（`NOT_FOUND`, `HASH_MISMATCH`, `PERMISSION_DENIED`, など）。

### 3-2. 中期実装（Phase 2: 安全性向上）

- 楽観ロック導入:
  - `expected_hash`（または `expected_mtime`）必須化オプションを追加。
- トランザクション境界の明確化:
  - 物理更新 + DB 更新 + sync の一貫性を整理。
- 監査ログ:
  - 誰がどのツールでどのファイルを更新したかを記録。

### 3-3. 長期実装（Phase 3: エージェント最適化）

- ツリー/検索系:
  - `find_files(glob, max_depth, include_ignored=false)`
- 差分系:
  - `diff_files`, `preview_patch`, `revert_last_change`。
- モデル適応:
  - Gemini/Claude ごとに最適な返却フォーマット（tokens最適化）を出し分け。


### 3-4. 既存ツールを一気に削除する前提での方針（ハルシネーション対策）

本計画では、**新規ツール導入タイミングで既存ツールを一括削除**する前提とします。

採用理由:
- 似た責務の旧新ツールを併存させないことで、ツール選択の分岐を最小化できる。
- 実装エージェントに「使えるツール集合」を明確に固定でき、誤選択を抑えやすい。
- 互換アダプタや二重運用の保守コストを削減できる。

一括削除を成立させる実装条件（必須）:
1. **同時リリース**: 新ツール実装・カタログ差し替え・プロンプト更新・テストを同一PRで完了する。
2. **強制Fail Fast**: 未定義ツール名/未定義引数は即 `INVALID_TOOL` / `INVALID_ARGUMENT` を返す。
3. **ツール公開面の統一**: role/skill/allowlist から旧ツール名を完全除去する。
4. **リカバリ導線**: エラー本文に「現在の正しいツール名」を必ず返す。

ハルシネーション抑止の実装ポイント:
- ツール説明を「短く・一意」にする（重複責務の記述を避ける）。
- 旧ツール名で呼ばれた場合はサジェスト付きエラーを返す（例: `Use read_file_chunk instead of read_reference`）。
- Tool chooser には新ツールのみを登録し、選択空間を物理的に縮小する。

## 5. 変更スコープ（実装影響範囲）

### 5-1. 必須変更

- `core/backend/domains/orchestration2/tools/library/files.py`
  - 新規ツール追加 / 既存ツールのJSON応答化 / バリデーション強化
- `core/backend/domains/orchestration2/config/tools/default_catalog.py`
  - ツール登録追加
- `core/backend/domains/workspace/file_service.py`
  - patch適用・hash計算・move/copy/statなどの共通処理追加
- `core/backend/api/files.py`
  - 必要なら新API（chunk read / patch apply）を追加

### 5-2. 推奨変更

- `docs/core/file_management.md`
  - 新しい操作モデル（chunk/patch/lock）の反映
- ツール仕様ドキュメント（新規）
  - argument schema、エラーコード、サンプルI/Oを明示

### 5-3. テストスコープ

- ツール単体テスト
  - 正常系（read/write/patch/move）
  - 異常系（競合/権限/巨大ファイル/不正パス）
- API統合テスト
  - UUID/path 混在ケース
  - 同時更新レース

## 6. 実装エージェント（Gemini 3.1 Pro / Claude Opus 4.6）向け追加情報

### 6-1. 先に固定すべき設計判断

1. **canonical path 仕様**
   - 常に `project root` からの相対パスで統一するか。
2. **patch形式**
   - line-based（簡単）か unified diff（汎用）か。
3. **競合戦略**
   - hash mismatch時は fail-fast のみか、自動再読込リトライを許すか。
4. **response schema**
   - 全ツール共通 envelope を採用するか。

### 6-2. 受け入れ基準（例）

- 「100KB の Markdown を 1セクションだけ更新」時、再生成トークンを 70%以上削減。
- 競合更新で silent overwrite が起きない。
- 不正パス（`../` など）を全操作で遮断。
- すべての新ツールで機械可読 JSON が返る。

### 6-3. 移行戦略

- 既存 `save_artifact/read_reference/list_files` は新ツール導入と同時に削除（互換レイヤなし）。
- 旧ツールを参照する prompt / skill / allowlist / テストを同一リリースで一斉更新。
- 監視指標（tool success率、平均入出力tokens、retry率）を先に定義してから本番投入。

---
この調査は「実装前の合意形成」を目的に、現行コードの責務分解と拡張余地を整理したものです。最初の1スプリントでは **Phase 1（chunk read + patch + move/copy + JSON応答化）** を推奨します。
