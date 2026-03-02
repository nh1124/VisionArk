# Tool / Skill Refactoring Investigation Report (2026-03-02, rev2)

## 1) 現在の skill / tool の実装方法

### 1-1. orchestration2 側（実行時）
- `project_engine_builder.create_engine_for_project()` で、毎リクエスト `AgentEngine` を組み立てる。
- Tool は `default_catalog.get_core_tools()` から静的クラス列挙で登録される。
- Skill は `config/skills/default_skills.py` の `SKILL_DEFS` を `NoOpSkill` として登録する。
- Integration tool は `register_and_reflect_integrations()` で追加登録され、同時に `operation` skill へ動的に tool 名を追記する（実行中の `dynamic_skills` のみ変更）。

### 1-2. integration 側（発見・読み込み）
- `integrations/loader.load_integration_tools()` が `integrations/*` 配下をディレクトリ走査し、`__init__.py` の `get_tools(user_id, db)` を優先して呼び出す。
- `BaseTool` インスタンスを `IntegrationToolAdapter` で orchestration2 互換の `ToolDef + ToolImpl` に変換して返す。
- 現状の integration ローダーは tool を返すのみで、skill 定義の供給経路は持たない（skill 反映は orchestration2 側 `tool_reflection.py` に集約）。

### 1-3. DB / seed 側
- `skill_registry` テーブルが存在し、`shared/seed.py` はユーザー作成時に `SKILL_DEFS` を DB へ upsert する。
- ただし実行経路（engine への skill 登録）は DB ではなく `SKILL_DEFS` を直接参照している。
- つまり **DB は「保持」しているが、ランタイム正本は static config** という二重状態になっている。

### 1-4. 設計判断の履歴
- `docs/decisions/ADR-skills-deprecation.md` により、過去の `SKILL.md -> DB` 同期や `/api/skills` CRUD は廃止され、Phase 1 時点で orchestration2 の static skill を正本化した履歴がある。
- 現在は「DB skill / filesystem skill は実行経路から除去済み」という前提で運用されている。

---

## 2) 新たな仕様（要求事項ベース）

ユーザー要件（要約）:
1. skill / tool 登録は DB 主体
2. seed / integration 定義は起動時・特定タイミング refresh で読み込み、DB 登録
3. orchestration2 だけでなく integration からも tool / skill を読み込む
4. integration と orchestration2 の実装差を比較し、優れた方式に統一

### 2-1. 目標アーキテクチャ（提案）
- **Source-of-Truth を DB に一本化**。
- static 定義（`default_skills.py`, `default_catalog.py`）と integration 提供定義（`get_tools` + 新規 `get_skills`）は、
  - 起動時 bootstrap
  - 手動 refresh API
  - 定期 refresh（任意）
  のいずれかで DB に反映する。
- 実行時 `project_engine_builder` は DB から tool/skill をロードして engine に登録する。

### 2-2. 具体仕様（最小）
- Tool Registry DB（新規または既存拡張）
  - 主キー: `user_id + tool_name`
  - カラム例: `description`, `params_schema`, `origin_type(core|integration|upload)`, `origin_id`, `is_active`, `version_hash`, `updated_at`
- Skill Registry DB（既存 `skill_registry` を拡張）
  - `tools` を単純配列で保持しつつ、将来的には中間テーブル化を推奨
  - `origin_type`, `origin_id`, `is_builtin`, `version_hash`, `status` を導入
- Refresh 仕様
  - core seed: static 定義を DB に upsert
  - integration refresh: `integrations/*` から tool/skill を収集して DB に upsert
  - 差分更新: `version_hash` 比較で不要更新を抑制
  - 無効化方針: 消えた定義は hard delete ではなく `is_active=False` 推奨
- Runtime 仕様
  - Engine 起動時は DB の `is_active=True` のみ採用
  - 競合時優先順位: `core > integration > upload`（暫定）または namespace 必須化で衝突禁止

### 2-3. 「優れた方への統一」観点
- orchestration2 側の長所
  - `ToolDef` / `SkillDef` の型が明確
  - engine registry API が明瞭
- integration 側の長所
  - ディレクトリ発見 + `get_tools(user_id, db)` の有効化ゲート
  - runtime 追加導入の拡張性
- 統一指針
  - 統一 I/F: `get_tools()` に加えて `get_skills()` を integration 側標準契約にする
  - core 側も同じ Provider 契約（`CoreProvider.get_tools/get_skills`）で扱い、refresh パイプラインを1本化

### 2-4. 将来要件（自己開発・即時登録）を見越した拡張ポイント
想定フロー（ユーザー/システムが tool/skill を開発 → 専用 API で upload → 検証失敗なら reject → 成功時即 active）に対応するため、現段階の refactor に次を含める。

- **定義ソース種別の標準化**
  - `origin_type` を `core | integration | upload` の3系統で統一。
  - upload 由来も refresh と同じ upsert パスに通し、「登録ロジックの二重実装」を避ける。
- **検証済みのみ公開する状態遷移**
  - `draft -> validating -> active | invalid` を tool/skill 共通で導入。
  - engine は `active` のみ読み込む（upload直後に active 化する要求に整合）。
- **配置先の抽象化**
  - 「ユーザーディレクトリ下に置かれる」要件を満たすため、DBには `artifact_path` と `artifact_hash` を保存。
  - ランタイムは path 直接参照ではなく、検証済み artifact レジストリ経由でロードする。
- **ロール/スキル紐付け再設計の余地確保**
  - skill-tool 紐付けと agent-skill 紐付けを DB 正規化し、upload 直後の自動割当ポリシー（例: default `operation` 付与）を後付け可能にする。

---

## 3) 変更スコープ

### 3-1. 必須変更（高）
1. **DB スキーマ**
   - tool registry テーブル追加
   - skill registry 拡張（origin/version/status/active）
2. **Refresh サービス新設**
   - `domains/orchestration2/bootstrap` 近傍に `definition_refresh_service.py` を追加
   - core/integration の収集 -> 正規化 -> upsert を実装
3. **integration 契約更新**
   - `integrations/*/__init__.py` に `get_skills`（任意実装可）を導入
   - `integrations/loader.py` を tool+skill 両対応に拡張
4. **engine bootstrap 切替**
   - `project_engine_builder.py` の static 直接登録を DB ロード中心に変更
   - `tool_reflection.py` の「operationへ append」処理を廃止し、DB 上の skill-tool 紐付けで解決

### 3-2. 影響範囲（中）
- `shared/seed.py`: ユーザー作成時 seed の責務見直し（初期投入 + refresh 呼び出しへ）
- `api/auth.py`: サインアップ時の seed 呼び出し変更
- 運用 API: `POST /admin/definitions/refresh`（または user スコープ）追加
- 監査ログ/可観測性: refresh 件数・衝突・失敗 integration の記録

### 3-3. 非機能・移行（中〜高）
- 既存ユーザー移行
  - 既存 `skill_registry` のデータ活用方針（上書き/保持）を明確化
- 可用性
  - refresh 失敗時は前回 DB スナップショットを継続利用
- 性能
  - 起動時 full refresh を避ける場合、初回のみ full + 以後差分

### 3-4. 将来の upload 機能に備えた追加スコープ（今回の refactor で先に仕込む）
- `tool_registry` / `skill_registry` に `status`, `validation_error`, `artifact_path`, `artifact_hash`, `activated_at` を追加可能な設計にする。
- refresh パイプラインを「source plugin 化」して、後続で upload source を追加しやすくする。
- `active` 判定を共通関数化し、engine load / UI 表示 / API 応答で判定の不一致を防ぐ。

### 3-5. 段階導入プラン（推奨）
- Phase A: DB schema + refresh service 追加（runtime は現状維持）
- Phase B: integration skill 契約導入、DB 登録開始
- Phase C: `project_engine_builder` を DB 正本へ切替（feature flag）
- Phase D: static 直接登録コード削除、ADR 更新
- Phase E: upload API/validator 追加、active 即時反映を導入

---

## 4) リスクと対策（要点）
- リスク: core/integration/upload 間の同名衝突
  - 対策: namespace 規約（`core.*`, `integration.<pkg>.*`, `user.<id>.*`）または優先順位固定
- リスク: refresh/validation 時の不整合で実行不能
  - 対策: トランザクション + staging テーブル + atomic swap
- リスク: integration / upload ごとの実装品質差
  - 対策: `get_skills` / upload manifest 契約テスト（必須フィールド、参照 tool 存在チェック）
- リスク: upload したコードの安全性
  - 対策: 検証環境分離、許可 import 制限、実行 time/memory 制限、署名/ハッシュ検証

---

## 5) 結論
- 現状は「実行正本=static」「DB=補助」の二重構造。
- 要求仕様を満たすには、**定義収集（core+integration）と実行ロードを DB 中心へ再配線**する必要がある。
- さらに将来の「自己開発 -> upload -> 検証 -> 即時利用」を想定すると、今回段階で source 種別・状態遷移・artifact 管理の土台まで先行設計するのが最も安全。
