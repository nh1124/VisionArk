# integration動的反映（skills/roles/実行経路）提案レポート

作成日: 2026-02-17

## 0. 依頼背景
- 現状は「integration tool の登録」までは行っているが、実行時に LLM から呼ばれない懸念がある。
- 本レポートでは、orchestration2 の skill/role/tool選択フローを分解し、**integrationを動的に反映して実際に呼ばれる状態**にする設計を提案する。

---

## 1. 現状整理（なぜ“登録しても呼ばれない”のか）

### 1-1. integration tool 登録は行われている
- `engine_setup.create_engine_for_project()` で core tools 登録後、`load_native_integration_tools()` を呼んで integration tools を registry へ登録している。

### 1-2. しかし、LLMへ渡す tool 一覧は skill で絞り込まれる
- role step 実行時、`StepExecutor._gather_tool_definitions()` が `step.skills`（なければ `agent_def.skills`）に基づいて公開 tool を決定。
- ここで参照される skill 定義（`SkillDef.tools`）に載っていない tool は、**登録済みでも LLM に渡らない**。

### 1-3. 現在の SKILL_DEFS は静的で integration tool 名を含まない
- `engine_setup.py` の `SKILL_DEFS` は `investigation / document_creation / file_management / operation` の固定配列。
- それぞれの `tools` リストに integration の tool 名（例: `send_line_message` など）が入っていない。
- 結果、graph 上の `plan/execute/verify` step で integration tool が露出しない。

### 1-4. role prompt 側でも integration の可視化が弱い
- PlannerRole / ProjectRole は `skills_text` / `active_skills_text` を参照してプロンプトを組む。
- ただしこのテキストは主にDB由来 skill 説明で、runtime登録された integration tool の説明が同期されない可能性が高い。

> 結論: 「tool registry への登録」と「stepでLLMに公開されること」は別問題。  
> 真の接続回復には、**skill解決 + role prompt 反映**まで動的化が必要。

---

## 2. orchestration2 の実行フロー観点での論点

1. `engine_setup` で tool/skill/role/graph を登録
2. role step 実行時に `step.skills` から `tool_defs` を算出
3. engine runtime（Gemini）へ `tool_defs` を渡す
4. LLM が function call を返した場合のみ tool invoke

このため integration tool を実際に呼ばせるには、最低でも以下が必要:
- A) skill 定義に integration tool を組み込む
- B) role prompt に integration tool の存在を説明する
- C) （必要なら）graph 側の step.skills 設定も補強する

---

## 3. 提案アーキテクチャ（推奨）

## 提案A: Dynamic Skill Composition（推奨・段階導入向け）

### A-1. 追加コンポーネント
`engine_setup` から呼ぶ `IntegrationReflectionService`（仮称）を追加し、以下を返す:
- `integration_tool_defs`: 登録対象 tool 定義
- `integration_skill_map`: integration tool をどの skill group に入れるか
- `integration_prompt_blocks`: role に渡す説明文（tool name + description + 使用条件）

### A-2. skill への反映方法
既存 `SKILL_DEFS` をベースに、runごとに以下を実行:
1. static `SKILL_DEFS` を shallow copy
2. reflection service の `integration_skill_map` を merge
3. merge後 SkillDef を `engine.register_skill()`

マージルール（推奨）:
- default は `operation` へ追加
- 明示分類がある場合は優先（例: manifest category が productivity なら `operation`、knowledge なら `investigation`）
- 重複 tool 名は de-dup

### A-3. role への反映方法
`ctx.metadata` に以下を注入:
- `integration_tools_text`: integration tool 一覧（name/description/注意点）
- `integration_services_state`: active integration 名

role 側は以下を追記:
- PlannerRole: 「利用可能な外部連携ツール」節
- ProjectRole: 「Active Integrations & Tools」節
- VerifierRole: 必要なら read-only で確認可能な integration tool を明示

### A-4. 期待効果
- 既存 graph（plan/execute/verify/respond）を壊さず、tool 露出だけ動的に拡張できる。
- userごとに active integration が異なるケースにも対応可能。

---

## 提案B: Integration Step を graph に追加（中長期）

- `execute` と別に `integrate` ステップを作り、integration専用 skill 群を使用。
- 例: `skills: [integration_ops]` を持つ role step を追加。
- ただし graph 管理・遷移の複雑化があるため、まず提案Aで十分。

---

## 4. 実装詳細（提案A）

### 4-1. 反映ポイント（engine_setup）
1. core tools 登録
2. integration tools ロード
3. **dynamic skill composition**（ここが新規）
4. role 登録
5. graph 登録

※ 重要: skill登録時点で integration tool 名が SkillDef.tools に含まれていること。

### 4-2. skill map 生成の入力
- integration module 名（`line`, `google_calendar` など）
- tool 名 / description
- optional metadata（manifest category, tool属性）

### 4-3. 既定ポリシー
- 明示属性なしの場合は `operation` に割当
- read-heavy tool（search/list系）は `investigation` へ優先配置
- create/update系は `operation` または `document_creation`

### 4-4. エラー時方針
- 1 integration の反映失敗は warning + 継続
- skill merge 失敗時は static SKILL_DEFS のみで続行（フェイルソフト）

---

## 5. 受け入れ基準（実行されることの確認）

1. `engine.list_tools()` に integration tool が存在
2. `_gather_tool_definitions(step.skills)` の結果に integration tool が含まれる
3. Gemini に渡る `tool_defs` に integration tool が含まれる
4. 対話で function call が発生し、integration tool invoke まで到達
5. role prompt に integration tool 情報が表示される（ログ/デバッグ出力で確認可）

---

## 6. 最小検証シナリオ

### シナリオ1: LINE tool
- 前提: `line` service active
- 入力: 「LINEで自分に“明日の朝確認”を送って」
- 期待: `send_line_message` が tool_defs に入り、function call される

### シナリオ2: inactive service
- 前提: `google_calendar` inactive
- 期待: その tool は dynamic skills に入らない、または tool_defs へ露出しない

### シナリオ3: prompt可視化
- 期待: Planner/Project prompt に integration tools 節が含まれる

---

## 7. 実装優先順位

1. Dynamic skill composition（最優先）
2. role prompt への integration 表示注入
3. 反映ログ（何がどの skill に入ったか）
4. 必要なら graph 拡張（中長期）

---

## 8. まとめ
- 現状の課題は「登録不足」ではなく「公開経路（skill/role）未連携」。
- 接続回復の本丸は、**integration tool を dynamic skill に編入し、role prompt に可視化すること**。
- まずは提案A（Dynamic Skill Composition）で、既存設計を崩さず実行可能性を回復するのが最適。
