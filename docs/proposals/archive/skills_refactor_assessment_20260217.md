# Skillsリファクタリング評価レポート（2026-02-17, orchestration2基準版）

## 目的
`orchestration2` が想定する Skill 仕様を正規（SoT: Source of Truth）とし、旧来ロジックを**廃止前提**で整理したうえで、移行方針と変更スコープを明確化する。

---

## 前提（今回の確認基準）
- **正規仕様**: `core/backend/domains/orchestration2` の Skill モデル/レジストリ/実行制御。
- **旧来実装の扱い**: `domains/automation` 側のSkill関連処理は原則廃止対象。
- 方針は「共存」ではなく、**orchestration2仕様へ完全収束**とする。

---

## 1. skills関連処理内容（現状, 仕様レイヤ別）

### 1-1. orchestration2（正規）
- Skillは `SkillDef(name, description, tools, request_approval)` で定義される。
- `SkillRegistry` で `name -> (SkillDef, impl)` を厳格管理する。
- 実行時は step/agent に設定された skill 名から tool 可視性を決定し、未登録 skill/tool は warning 扱いで除外する。

### 1-2. engine_setup（正規層へのブリッジ）
- 静的 `SKILL_DEFS` を登録し、integration tool は `operation` skill に動的反映している。
- prompt用の `skills_text` / `skill_definitions` をDBから読み込む処理も併存している（要整理）。

### 1-3. automation（旧来・廃止対象）
- `domains/automation/skills/registry.py` が `SKILL.md` をDB同期。
- `SkillService` が intent/filter/conflict/tool_policy 統合を持つが、orchestration2 実行経路では未接続。
- `SkillMiningService` は draft skill をDB生成する。

### 1-4. API / Frontend
- `/api/skills` に CRUD・batch・project割当がある。
- フロント `projects/[projectId]/settings` は `node` エンドポイント前提コードが残っている。

---

## 2. 不適になっているskills処理内容（orchestration2基準）

### 2-1. 旧SkillService中心の構想
- `SkillService` は orchestration2の `SkillDef`/`SkillRegistry`/step skill 解決経路に入っていない。
- よって実行制御の中核として再採用する方針は不適。

### 2-2. skill仕様の二重化
- orchestration2は `SkillDef.tools` ベースで制御。
- 旧来側は `metadata_payload` の `intent/priority/conflicts/tool_policy` を前提。
- 仕様が二重化し、保守コストとバグリスクを増やしている。

### 2-3. 旧registryの探索不整合
- `domains/automation/skills/registry.py` の探索パスは現配置とズレがあり、取り込み漏れリスクがある。
- ただし本件は「修正して延命」ではなく、廃止計画の中で扱うべき。

### 2-4. Frontend/API契約の世代不整合
- settings画面が `/api/skills/node/{nodeId}` 前提だが、backendには同エンドポイントが無い。
- `node_type` 前提も `ProjectAgent(agent_type/role_name)` と不整合。

### 2-5. ドキュメントが旧仕様を含む
- `docs/core/skills_system.md` は `node_skills` 等の旧説明を含み、orchestration2の正規仕様と乖離。

---

## 3. 変更提案（旧来廃止 + orchestration2収束）

### 提案A（最優先）: Skillの正規仕様をorchestration2へ一本化
- 実行上の真実を `SkillDef` / `SkillRegistry` に固定する。
- 旧来メタデータ中心の解決ロジックは採用しない。

### 提案B: 旧SkillServiceは廃止
- `core/backend/domains/automation/skill_service.py` は廃止前提とする。
- 必要な機能がある場合は orchestration2 側へ再実装し、同ファイルへは機能追加しない。

### 提案C: APIとFrontendの契約をProjectAgent基準で統一
- settings画面の `node` 前提コードを撤去し、`/api/skills/project/{project_id}` を正規利用。
- 互換エンドポイントを追加する場合も期限付きで、最終的に削除。

### 提案D: DB Skillを使うならDBモデルをSkillDefに揃える
- DB skill を runtime入力として使う方針を採るなら、`SkillDef` と同等の構造にDB側を更新する。
- 具体的には、`tools` / `request_approval` / `description` など実行に必要な属性を正規化し、
  runtimeでは「DB -> SkillDef」変換ではなく、**SkillDef準拠データを直接扱う**構成へ寄せる。
- `metadata_payload` 依存の旧属性（intent/priority/conflicts/tool_policy）は廃止または別用途へ分離。

### 提案E: 廃止前提の回帰テスト追加
- 「旧来経路が実行経路に混入しない」ことを検証するテストを追加。
- 「DB skill（SkillDef準拠）でtool可視性が決まる」契約テストを追加。
- 「node系旧APIを呼ばない/残さない」契約テストを追加。

---

## 4. 変更スコープ（実施単位）

### Phase 1: 方針固定（必須）
1. `docs/core/skills_system.md`
   - 正規仕様を orchestration2 と明記
   - 旧仕様を「廃止予定」へ変更
2. ADRまたは短い設計メモ追加
   - 旧SkillService/旧registryを廃止対象として決定

### Phase 2: 契約整備（小〜中）
3. `core/frontend/app/projects/[projectId]/settings/page.tsx`
   - node API参照を削除し project skills APIへ統一
4. `core/backend/api/skills.py`
   - 必要な互換APIがある場合は期限明記のうえ暫定対応

### Phase 3: 実装収束（中）
5. `core/backend/domains/automation/skill_service.py`
   - 廃止（または削除に向けて no-op 化）
6. `core/backend/domains/automation/skills/registry.py`
   - 廃止（必要なら移行期間のみread-only化）
7. `core/backend/domains/orchestration2/engine_setup.py`
   - DB skill利用時はSkillDef準拠データを直接扱う経路へ一本化

### Phase 4: 品質固定（推奨）
8. backend/frontend回帰テスト
   - 旧来経路不使用の保証
   - SkillDef準拠DB skillの実行保証
   - API契約（node残骸の再流入防止）

---

## 結論（今回の確認結果）
- 「orchestration2が正規仕様で、それ以外は旧来ロジック」という認識は妥当。
- 今後は旧来処理を延命せず、**廃止前提**でorchestration2へ収束させるのが適切。
- 優先順位は **(1) 方針明文化 → (2) API/UI契約整合 → (3) 旧実装廃止**。

