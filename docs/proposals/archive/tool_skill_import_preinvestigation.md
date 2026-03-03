# Pre-Investigation Report: Tool/Skill Import Implementation (2026-03-02)

## 0. 目的
本レポートは、次フェーズで実施予定の「tool/skill インポート機能（upload + validation + 即時利用）」実装に向け、
- 仕様整理
- 変更スコープ
- 実装順序
- リスクと対策
を事前に固めることを目的とする。

---

## 1. 想定ユースケース
1. ユーザーまたは VisionArk システムが tool / skill を開発する。
2. 専用 API からアップロードする（ファイルはユーザーディレクトリ配下に保存）。
3. アップロード時に検証（構文・依存・契約・安全ポリシー）。
4. 検証成功時のみ DB に登録し `active` 化する。
5. 登録直後からエージェントが実行可能（次回 engine 生成時に必ず反映。可能ならホットリロード）。

---

## 2. 仕様まとめ（提案）

### 2-1. API 仕様（MVP）
- `POST /api/definitions/import`
  - 入力: `type(tool|skill)`, `name`, `manifest`, `files[]`, `activate=true|false`
  - 出力: `definition_id`, `status(validating|active|invalid)`, `errors[]`
- `POST /api/definitions/{id}/validate`
  - 再検証（依存更新・ポリシー変更時用）
- `POST /api/definitions/{id}/activate`
  - `valid` な定義のみ active 化
- `POST /api/definitions/{id}/deactivate`
- `GET /api/definitions`
  - source, status, type, updated_at で絞り込み

### 2-2. データモデル仕様
- `tool_registry`（新規）
  - `id, user_id, name, description, params_schema, code_entry, artifact_path, artifact_hash`
  - `origin_type(core|integration|upload)`, `origin_id`, `status`, `is_active`
  - `validation_error`, `version_hash`, `created_at`, `updated_at`, `activated_at`
- `skill_registry`（既存拡張）
  - 既存列に加え `origin_type, origin_id, status, validation_error, artifact_*` を追加
- `skill_tool_bindings`（推奨）
  - skill と tool の多対多を正規化

### 2-3. 検証仕様
- 構文検証: Python AST parse など
- 契約検証: `ToolDef` / `SkillDef` 必須項目
- 参照整合: skill が参照する tool が存在し active 可能か
- セキュリティ検証:
  - 禁止 import（例: `subprocess`, `os.system` など）
  - ファイルアクセス制限
  - ネットワーク利用制限（ポリシー許可時のみ）
- 実行前 smoke test:
  - no-op 入力で初期化可能か
  - timeout 内で終了するか

### 2-4. アクティベーション仕様
- 基本フロー: `draft -> validating -> active | invalid`
- `active` 化条件:
  - 検証結果 `valid`
  - 重複名・衝突規約クリア
  - ロール/スキル紐付けポリシーを満たす
- 反映タイミング:
  - 最低限: 次回 `create_engine_for_project()` 時に DB からロード
  - 拡張: active 時に running engine へ差分反映（ホットリロード）

### 2-5. 名前衝突 / バージョン仕様
- 命名規約: `user.<user_id>.<name>` を推奨
- 衝突ルール（暫定）: `core > integration > upload`
- バージョニング:
  - `version_hash` で同一内容を判定
  - 変更時は新バージョン row か履歴テーブルに保存

---

## 3. 変更スコープ

### 3-1. Backend API
- 新規ルーター: `api/definitions.py`（import/validate/activate/list）
- 認可:
  - 自ユーザー定義のみ操作可
  - システム生成定義は専用スコープで操作

### 3-2. Domain / Service
- `definition_import_service.py`
  - artifact 保存
  - manifest 解釈
  - validation pipeline 実行
  - DB upsert
- `definition_validation_service.py`
  - syntax/contract/security/smoke を段階実行
- `definition_activation_service.py`
  - active 切替
  - engine 反映トリガー

### 3-3. Loader / Engine
- `integrations/loader.py` と同様の抽象化で `upload_loader` を追加
- `project_engine_builder.py` は source 非依存で DB active 定義をロード
- `tool_reflection.py` の runtime append 依存を除去

### 3-4. Storage
- ユーザーディレクトリ配下例:
  - `~/.visionark/users/{user_id}/definitions/{definition_id}/...`
- 保存時に `artifact_hash` 記録、DB と一致確認

### 3-5. Frontend / UX（任意だが推奨）
- Import UI
  - zip / 複数ファイル upload
  - validation 結果表示
  - activate 切替
- ログ/エラー表示
  - どの検証で失敗したかを明示

---

## 4. 実装フェーズ案
- Phase 1: DB schema + import API skeleton + artifact 保存
- Phase 2: validator（syntax/contract）+ invalid 制御
- Phase 3: activation + engine DB load 完全化
- Phase 4: security validator + sandbox smoke test
- Phase 5: UX改善 + ホットリロード（必要時）

---

## 5. リスクと対策
- リスク: 悪意あるコード投入
  - 対策: 検証サンドボックス分離、禁止API検査、実行制限
- リスク: 検証コスト増で API 遅延
  - 対策: 非同期ジョブ化 + status polling
- リスク: 即時利用要求と一貫性の衝突
  - 対策: active 切替を単一トランザクション化し、engine 読み込みは active のみ
- リスク: 既存定義との互換性崩壊
  - 対策: source/type/version の互換レイヤを用意

---

## 6. 実装前に確定すべき意思決定
1. upload 定義の実行言語を Python 限定にするか。
2. ホットリロードを初期スコープに含めるか（次回 engine 生成のみでよいか）。
3. 検証失敗時 artifact を保持するか削除するか。
4. upload tool の権限制御（どの skill/role に自動で見せるか）。
5. システム自己開発（VisionArk generated）とユーザー upload を同一 API に統合するか。

---

## 7. 結論
- upload ベースの tool/skill 拡張を安全に成立させる鍵は、
  1) DB 正本、
  2) 検証ステート管理、
  3) active のみ実行、
  4) artifact 管理
  の4点である。
- 先行する refactor（DB中心化）が完了していれば、import 機能は source plugin を追加する形で段階導入できる。
