# Skills 再設計レポート（orchestration2正本化方針）

**更新日**: 2026-02-19  
**目的**: 旧来 skill 方式を破棄し、`orchestration2` を唯一の正本として統一する。Claude がこの文書をそのまま実装タスクへ落とし込めるレベルで、削除対象・実装順序・変更スコープを明確化する。

---

## 0. 結論（先に要点）

- **旧来 skill 方式は全面破棄**する（filesystem `SKILL.md` 前提、既存 skills API 前提、DB Skill 前提の注入経路を停止）。
- **正本は orchestration2 の `SkillDef` / `SkillRegistry` / 実行時 tool filtering** のみ。
- **DB保存は将来対応（保留）**。今はメモリ上/コード定義を正とし、将来の UI 切替に向けてフォーマットだけ先に `orchestration2` に寄せる。
- **Integration 側も修正**し、skill 由来設定ではなく、orchestration2 の capability 登録に統一する。

---

## 1. skill の概要（新方針）

### 1.1 正本
`orchestration2` の下記要素を skill の唯一仕様とする。

- `SkillDef(name, description, tools, request_approval)`
- `SkillRegistry`
- `StepExecutor` による step 単位の tool 制限

### 1.2 廃止対象（考え方）
以下は「skill の正本」から外す。

- DB `skills` テーブルを前提とした prompt 注入フロー
- `/api/skills` による CRUD 運用
- filesystem `SKILL.md` の運用前提

> 注: DB保存そのものを将来禁止する意図ではない。**現時点では保留**し、将来再導入時は orchestration2 互換フォーマットへ統一する。

---

## 2. 役割（新方針）

skill は「手順知識の文章管理」ではなく、以下に限定する。

1. **能力境界の宣言**（どの tool 群を使えるか）
2. **実行時ガードレール**（step で許可される tool の制約）
3. **計画時可視化**（planner に capability snapshot を渡す）

文章的ノウハウ（旧 `content`）は、skill 本体ではなく別の prompt component で扱う。

---

## 3. 機能としての反映のされ方（To-Be）

### 3.1 エンジン起動
1. `config/skills/default_skills.py` など orchestration2 定義のみ読み込む。  
2. integration が提供する tool を engine へ登録。  
3. 必要に応じて integration 由来の tool を適切な `SkillDef.tools` へマージ。  
4. `SkillRegistry` 登録後、agent に skill 名を割り当てる。

### 3.2 実行
- `StepExecutor` が step の active skills を解決し、許可 tool を確定。
- skill 未指定 step は agent デフォルト skills から解決。

### 3.3 UI（将来）
- UI は orchestration2 互換フォーマット（`SkillDef` 相当）を編集対象にする。
- runtime で切替可能な仕組みは将来導入（DB保存再開時）。

---

## 4. 現在の使用状況（As-Is）

現状コードは「正本化方針」とズレが残っている。

1. `project_engine_builder.py` で DB skill 読み込み経路が残存。
2. `prompt_context_loader.py` で DB skill `content` を `skills_text` として注入。
3. `/api/skills` が CRUD・project紐付けを提供。
4. frontend の Skills ページが `/api/skills` 運用前提。
5. integration 配下に `SKILL.md` が残存。

---

## 5. 問題点（今回の指摘を反映）

1. **正本の多重化**
   - orchestration2 と DB/API と filesystem の3系統が併存し、仕様判断がぶれる。
2. **旧遺産が現行仕様を汚染**
   - `/api/skills`・`skills_text` 注入が「旧方式の再生産」になっている。
3. **integration 境界が曖昧**
   - integration 側が skill 概念を持つと、正本統一が崩れる。
4. **将来拡張の足場不足**
   - 「将来DBに戻す」際のフォーマット条件が未固定のため、再度分岐するリスクがある。

---

## 6. 改善案（実装前提で具体化）

### A. 旧方式の破棄（最優先）

**目的**: 旧 skill 資産を実行経路から除去し、正本を orchestration2 に一本化する。

- backend
  - `/api/skills` router の除去（`app/main.py` から include も削除）
  - `project_engine_builder.py` の DB skill 読み込み分岐を削除
  - `prompt_context_loader.py` の DB skill `skills_text` 注入を停止
- frontend
  - `app/skills/page.tsx` を削除または「廃止案内ページ」へ一時置換
- docs
  - skills 運用導線を orchestration2 正本に改訂

### B. orchestration2 フォーマット先行整備（将来DB再導入の布石）

**目的**: DBは未使用でも、将来の保存・UI切替に向けた型定義を固定する。

- `SkillDef` と1:1で対応するシリアライズ形式（JSON/YAML）を定義
- 必須/任意項目、バリデーション、互換方針（version）を明記
- 変換器（deserialize/normalize）を先に実装し、現時点ではコード定義読込にだけ適用

### C. UI動的切替の設計先行（実装は段階的）

**目的**: 将来「UIから skill 切替」を実現するための責務分離。

- UI が扱う DTO を `SkillDef` 準拠に変更
- backend は「保存先」を抽象化（今は in-memory provider、将来 DB provider）
- feature flag で段階導入可能にする

### D. Integration 側の修正

**目的**: integration が skill 正本を持たず、tool/capability 提供に責務限定する。

- `integrations/*/SKILL.md` を廃止（もしくは docs へ退避し runtime 非参照を保証）
- integration loader は tool 登録のみ担当
- skill への紐付けは orchestration2 側（builder/config）で一元管理

### E. 観測性（最小）

**目的**: 正本化後の運用確認を可能にする。

- 実行ログに `active_skills`, `resolved_tools`, `step_id` を出力
- まずは backend ログで可視化し、UI分析は後続

---

## 7. 改善案の変更スコープ（Claude 実装用）

## Phase 1: 破棄と統一（今回すぐ実施可能）

### Backend
- `core/backend/app/main.py`
  - `skills` router import / include 削除
- `core/backend/api/skills.py`
  - ファイル削除（または未使用化）
- `core/backend/domains/orchestration2/bootstrap/project_engine_builder.py`
  - `fetch_project_skills` と DB skill register 処理削除
- `core/backend/domains/orchestration2/prompting/prompt_context_loader.py`
  - `skills` 引数依存と `skills_text` 注入削除（orchestration2 の capability情報のみ維持）

### Frontend
- `core/frontend/app/skills/page.tsx`
- `core/frontend/app/skills/components/SkillEditor.tsx`
  - 削除 or 廃止表示

### Integrations
- `integrations/line/SKILL.md`
  - runtime 資産としては廃止

### Docs
- `docs/core/skills_system.md`
  - DB skills 前提記述を削除し、orchestration2 正本に全面改訂
- `docs/decisions/ADR-skills-deprecation.md`
  - 今回の追加破棄範囲を追記

## Phase 2: 将来拡張の土台（DB保留のまま）

- `orchestration2` 用 skill schema（version付き）策定
- provider 抽象（memory provider 実装）
- UI DTO 再設計

## Phase 3: DB再導入 + UI動的切替

- DB provider 実装
- migration + feature flag rollout
- 切替UIを有効化

---

## 8. 推奨実装順（Claude向けタスク分解）

1. **旧方式停止PR**
   - API/Frontend/Integration の旧skill経路を止める
2. **orchestration2 最小化PR**
   - builder / loader から DB skill 依存除去
3. **ドキュメント同期PR**
   - skills_system + ADR を新方針へ更新
4. **schema準備PR**
   - 将来DB再導入用フォーマット定義（未接続）

---

## 9. 受け入れ条件（Definition of Done）

- skill 実行経路で DB `skills` / `/api/skills` / filesystem `SKILL.md` を参照しない。
- skill は orchestration2 の `SkillDef` 系だけで解決される。
- integration は tool 提供のみ行い、skill 正本を持たない。
- ドキュメントが実装状態と一致している。

---

## 10. リスクと回避

- **リスク**: frontend の Skills 導線削除で利用者混乱  
  **回避**: 一時的に「廃止・移行中」ページを表示。

- **リスク**: DB skill 前提テストの失敗  
  **回避**: 旧テストは削除ではなく「legacy」分類で整理し、orchestration2 テストへ差し替える。

- **リスク**: integration の暗黙依存漏れ  
  **回避**: `integrations/*/SKILL.md` 検索CI（存在時 fail）を追加。
