# 事前調査レポート: integration/tool/skill 再設計に向けた現状整理

作成日: 2026-03-03  
対象: 以下の実施前に必要な事前調査

- integrations の一部を標準 tool へ移行（例: PDF 生成）
- tool のリファクタリング（旧実装の廃止/改善）
- skill 分割の見直し
- skill instructions の見直し

---

## 1. 現状の integration / skill の初期 seed 状態

## 1.1 ユーザー作成時に seed されるもの

初期 seed は `seed_user_definitions()` から `refresh_core_sync()` が呼ばれ、**core の tool/skill のみ**が `tool_registry` / `skill_registry` へ upsert されます。  
integration 由来はここでは seed されません。

- Core tools: `default_catalog.get_core_tools()` 由来
- Core skills: `config/skills/default_skills.py` の `SKILL_DEFS`（6つ）
  - `investigation`
  - `document_creation`
  - `file_management`
  - `operation`
  - `workspace_management`
  - `delegation`

## 1.2 integration の取り込みタイミング

integration は主に 2 経路で取り込まれています。

1. **Definition Refresh 経路**（DBへ永続化）
   - `POST /api/definitions/refresh/integrations`
   - `load_integration_tools()` / `load_integration_skills()` を通して DB に upsert
   - integration skill がある場合は `skill_registry` に保存

2. **Engine 起動時経路**（実行エンジンへの登録）
   - `register_and_reflect_integrations()` が integration/custom/mcp tools を engine に直接登録
   - prompt に integration tool 一覧テキストを注入

つまり現状は、**初期 seed = core 中心 / integration = refresh・実行時反映中心**という二層構成です。

## 1.3 現在の integration skill seed 状況

`get_skill_defs()` を実装している integration は実質 `ms_tools` のみで、`ms_office` skill が定義されています。  
他 integration（calendar/line/outlook/lbs/knowledge_core/native）は、tool はあるが skill 定義を持たない状態です。

## 1.4 初期状態における課題

- 「tool はあるが skill がない」integration が多く、agent の能力境界が曖昧
- 初期 seed 時点では integration skill が入らないため、運用開始直後の一貫性が弱い
- `operation` への寄せ集め運用に依存しやすい

---

## 2. integration -> 標準 tool / skill 移行の提案

## 2.1 移行判断の基準

以下に該当するものは integration ではなく標準 tool 化を推奨。

- 外部サービス認証が不要で、ローカル処理として完結する
- 多くのプロジェクトで常時利用される汎用処理
- エージェント基礎能力として常時提示したほうが計画精度が上がる

## 2.2 優先移行候補

### A. `render_pdf`（ms_tools -> core）

- 現状は MS integration 側だが、用途は「成果物レンダリング」という汎用処理
- 「Office 連携」より「ドキュメント出力」に属するため、core の document 系 tool へ移す方が自然
- 期待効果: スキル割当が明確化し、Office 非利用案件でも使える

### B. `word_tool` / `excel_tool` / `ppt_tool` の分離再設計

- 一気に core 移行するより、まずは API 面を分解（例: `create_docx`, `update_sheet`, `build_slide_deck`）
- 認証不要のローカル処理は core、Graph 依存操作は integration に残す
- 期待効果: 1 tool の責務過多を解消し、tool 選択精度を向上

### C. `ms_auth_manager` は integration 残置

- 外部認証依存のため integration が適切
- 上記 A/B と切り分けることで、「汎用ドキュメント操作」と「外部連携認証」を分離可能

## 2.3 移行後の skill 付け先（方向性）

- PDF/文書生成系: `document_output`（新設案）
- Office 編集系（ローカル）: `office_editing`（新設案）
- 認証/接続管理: `external_ops`（新設案）

---

## 3. tool リファクタリングが必要なもの（優先候補）

## 3.1 仕様・登録経路の不整合

1. **integration loader のフォールバック挙動**  
   `get_tools()` 未実装時にクラススキャンへフォールバックし、activation check をバイパスしうる。  
   → `get_tools()` を必須化し、フォールバックを段階的廃止するべき。

2. **`ms_tools.get_skill_defs()` のコメントと実態の乖離**  
   コメントでは「将来 no-op」前提だが、実際は loader 側で skill 読み込み済み。  
   → 説明/コメントを現行アーキに合わせる必要あり。

3. **skill refresh 時の `instructions` 保存不足**  
   SkillDef は `instructions` を持つが、core/integration refresh upsert が未保存。  
   → seed/refresh で `instructions` を永続化しないと新仕様の価値が出ない。

4. **definitions API の skill レスポンス不足**  
   `GET /api/definitions/skills` が `instructions` を返さない。  
   → 運用・監査・UI編集のため返却対象へ追加が必要。

## 3.2 integration 実装の未反映/取りこぼし

5. **LBS tool の公開漏れ**  
   `agent_tools.py` には `get_current_condition` など複数 tool があるが、`integrations/lbs/__init__.py` の `get_tools()` 返却一覧に未含有。  
   → 実装済みなのに agent から見えない tool が存在。

6. **always-on integration の再分類**  
   `ms_tools` / `native_tools` は activation check なしの常時提供。  
   → 本当に integration として扱うべきか（core化 or feature-flag化）を再判断すべき。

## 3.3 命名・責務の整理候補

7. **LBS 系の命名統一**  
   `update_task_details`, `delete_task_by_id`, `complete_lbs_task` 等、語彙と抽象度が混在。  
   → CRUD/Action 命名規則の統一が必要。

8. **巨大多機能 tool の分割**  
   `word_tool` / `excel_tool` / `ppt_tool` は機能粒度が粗く、LLM の tool 選択根拠が曖昧化しやすい。  
   → サブ操作ごとの tool 分割を推奨。

---

## 4. 新しい skill 群の提案（再分割案）

現行 6 skill は大枠として有効ですが、integration 拡大後の運用には粗いため、以下の再編を提案します。

## 4.1 提案スキルセット（vNext）

1. **research**
   - 検索/調査/情報収集
   - 既存 `investigation` を改称または再定義

2. **authoring**
   - 文書作成・編集・要約
   - 既存 `document_creation` を拡張

3. **document_output**
   - PDF 生成、図表化、最終出力
   - `render_pdf` など成果物化処理を集約

4. **repository_ops**
   - ファイル CRUD、リポジトリ取り込み、パッチ適用
   - 既存 `file_management` を明確化

5. **workspace_context**
   - workspace item 運用（共有知識の登録/更新）
   - 既存 `workspace_management` を改称

6. **project_admin**
   - メンバー管理、ルール更新、プロジェクト設定
   - 既存 `operation` の管理系を分離

7. **runtime_ops**
   - shell/browser/native 実行などのオペレーション
   - 高リスク操作を project_admin から切り分け

8. **external_comms**
   - LINE / Outlook / Calendar など外部コミュニケーション
   - integration tools を用途別に収容

9. **planning_tracking**
   - plan 初期化・進捗更新・status 取得
   - markdown/planning 系ツールを独立

10. **delegation**
    - サブエージェント委任
    - 既存継続

## 4.2 設計意図

- 「何をする skill か」をより明示し、tool 選択の誤爆を下げる
- high-risk 実行系（runtime_ops）を分離し、instruction で強い制御をかける
- integration tool を「接続元」ではなく「業務用途」で束ねる

---

## 5. skill instruction 見直し方針（事前提案）

## 5.1 instruction 記述テンプレート

各 skill の `instructions` は最低限、以下 4 要素を固定フォーマットで持つ。

1. **When to use**（使用条件）
2. **Do first**（開始時の必須確認）
3. **Do not**（禁止事項）
4. **Output contract**（返答形式・品質要件）

## 5.2 優先適用対象

- `runtime_ops`: 安全制約（破壊操作・外部接続）
- `document_output`: 成果物品質（体裁・検証）
- `external_comms`: 送信前検証（宛先/機密情報）

## 5.3 先行実装の最小スコープ

- Core 6 skill + `ms_office` に instruction を先行導入
- refresh / API / prompt の 3 経路で `instructions` を欠落なく通す
- その後 vNext skill へ段階移行

---

## 6. 実施順序（提案）

1. **調査確定**: 本レポート内容を基準に移行対象を確定
2. **土台修正**: instructions 永続化・API可視化・loader安全化
3. **tool再編**: `render_pdf` などの core 移管 + 多機能tool分割
4. **skill再編**: vNext skill 定義投入 + 既存agent割当更新
5. **instruction強化**: スキル別ガイドラインを本番適用

この順序で進めると、仕様ギャップ解消（P0）→ 構造改善（P1）→ 運用品質向上（P2）を安全に進められます。
