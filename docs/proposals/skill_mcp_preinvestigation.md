# Open Claw / Antigravity 向け Skill・MCP 事前調査レポート

## 0. このレポートの前提
- 本レポートは、現行 VisionArk リポジトリの実装（tool/skill registry, upload module, integration refresh）を一次情報として整理しています。
- Open Claw / Antigravity 側は、一般的な OSS Agent エコシステムで使われる「Skill（手順パッケージ）」と「MCP（Model Context Protocol）」の公開的な設計思想をベースに比較しています。
- そのため、最終的な実装時には **対象プロジェクトの実際の manifest / API 仕様差分**を再確認する前提です。

---

## 1. VisionArk が現在サポートしている skill / tool の概要

### 1-1. Tool の実体
VisionArk では tool は Python 実装（`BaseTool` 継承）として提供され、`default_catalog.py` でコア tool を列挙して読み込む構造です。
主なカテゴリはファイル操作・検索・生成・ブラウザ操作・運用管理・委譲などです。

### 1-2. Skill の実体
Skill は `SkillDef(name, description, tools)` の静的定義として持ち、`default_skills.py` 上で「investigation / document_creation / operation ...」のように、
**tool の集合を束ねるメタ定義**として扱われています。

### 1-3. 動的拡張（ユーザーアップロード）
`/api/definitions/modules` でユーザー定義モジュールを登録でき、`__init__.py` から以下を公開する方式です。
- `get_tools(user_id, db)`
- `get_skill_defs()`

これにより VisionArk は既に「tool と skill の追加拡張」が可能です。さらに `/api/definitions/refresh` 系 API で core/integration 再同期ができます。

### 1-4. 現行方式の特徴（要点）
- **強み**: Python ベースで厳密に制御しやすく、既存 DB registry と統合済み。
- **弱み**: Open Claw 系で多い `SKILL.md` 主体の配布物をそのまま読めない。
- **弱み**: MCP クライアント/サーバとしての標準接続面は（現状）明示実装が見当たらず、外部 MCP 資源との相互運用は追加実装が必要。

---

## 2. Open Claw / Antigravity 文脈で語られる Skill・MCP の概要

### 2-1. Skill（一般的な意味）
Open Claw / Antigravity などで言われる Skill は、概ね次の要素を含む「再利用可能な実行知識パッケージ」です。
- 目的（何を達成するか）
- 実行手順（どう進めるか）
- 利用可能ツールや前提条件
- 失敗時のフォールバック

つまり Tool が「関数」なら Skill は「手順書付きプレイブック」です。

### 2-2. MCP（Model Context Protocol）
MCP は、LLM と外部システム（ファイル、DB、SaaS、社内 API）を標準インターフェースで接続するためのプロトコルです。
実務上は以下の狙いで使われます。
- ツール接続の共通化（実装差分の吸収）
- リソースアクセスの標準化
- エージェントごとの独自プラグイン実装を減らす

### 2-3. Open Claw / Antigravity で重要になりやすい点
- Skill は Markdown/Manifest で配布しやすいこと
- MCP 接続先を増やしてもエージェント本体の改修を最小化できること
- Skill と Tool（MCP 提供機能）の紐付けが宣言的に管理できること

---

## 3. VisionArk で Skill / MCP をサポートするための方法

### 3-1. もっとも安全な導入順（推奨）
1. **Skill Import 層を追加**（`SKILL.md`/manifest → `SkillDef` 変換）
2. **MCP Adapter 層を追加**（MCP サーバ機能を VisionArk tool として公開）
3. **Registry に origin 情報を追加拡張**（`origin_type = core|integration|upload|mcp|skill_pack`）
4. **UI/運用フロー整備**（有効化、権限、監査ログ）

### 3-2. 実装イメージ

#### A) Skill 互換レイヤー
- `domains/orchestration2/skills/importers/` を作成
- 例: `import_skill_pack(files) -> list[SkillDef]`
- YAML frontmatter / JSON manifest から以下を抽出
  - `name`, `description`, `tools`, `instructions`
- `instructions` は prompt context loader へ注入可能な形式に保持

#### B) MCP 互換レイヤー
- `integrations/mcp/` を新設し、MCP 接続設定を定義
- MCP の tool/resource を VisionArk の `ToolDef` へ変換
- 呼び出し時は Adapter が MCP クライアントとして中継

#### C) 定義管理 API の拡張
既存 `/api/definitions/*` を活かしつつ、以下を追加。
- `POST /api/definitions/mcp/servers`（接続先登録）
- `POST /api/definitions/mcp/refresh`（MCP 機能再同期）
- `POST /api/definitions/skill-packs`（SKILL.md パック登録）

#### D) セキュリティ
- 接続先 allowlist
- OAuth/API key の secret vault 保存
- tool 単位の `is_active` + 権限スコープ
- 実行ログ（誰が/何を/どこへ）

### 3-3. 互換方針（重要）
既存の `BaseTool` 実装を捨てず、
- ネイティブ tool = 高性能・高信頼の主力
- MCP tool = 接続拡張の標準経路
- Skill pack = 運用知識の配布形式
として **3層共存**させると移行コストが低いです。

---

## 4. 提案ロードマップ（最小実装）

### Phase 1: Skill Pack 受け口
- `SKILL.md` / manifest parser 実装
- `SkillDef` への変換と DB 登録
- 既存 `/api/definitions/modules` と同じ UX で有効化

### Phase 2: MCP PoC
- 1 つの MCP server を対象に tool/resource bridge を実装
- 2〜3 個のユースケースで性能・失敗時挙動を評価

### Phase 3: 標準化
- `origin_type=mcp` を正式化
- 監査ログ・権限制御・タイムアウト/リトライ統一
- Skill と MCP 提供機能の依存関係可視化

### Phase 4: Open Claw / Antigravity 互換検証
- 実際の skill パッケージを取り込み検証
- フォーマット差分の吸収（importer plugin 化）
- ドキュメントに「互換表」を整備

---

## 5. 結論
- VisionArk はすでに **tool/skill registry とユーザー拡張 API**を持っており、土台は十分あります。
- 追加すべき本質は、
  1) `SKILL.md` 系配布物の importer、
  2) MCP adapter、
  3) 権限・監査を含む運用設計、
  の3点です。
- この順で導入すれば、既存資産を壊さず Open Claw / Antigravity 系エコシステムへの相互運用性を段階的に高められます。
