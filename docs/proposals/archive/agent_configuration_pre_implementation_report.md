# Agent設定機能 導入前レポート

## 1. 現在のエージェント設計

### 1.1 実行時の実体
- チャット実行時は `create_engine_for_project()` で **毎リクエスト AgentEngine を構築**し、1つの `AgentDef` を登録して実行している。
- 現在登録される `AgentDef` は `graph_name="direct_assistant"` 固定で、`skills` は `ALL_SKILL_NAMES`（デフォルトスキル全量）を付与している。
- 実運用では「プロジェクトごとに複数エージェントをランタイム登録して選択する」設計にはまだなっていない。

### 1.2 永続化モデル（DB）
- `ProjectAgent` テーブルに、エージェントの基本情報（`display_name`, `description`, `system_prompt`, `tools`, `status` など）が保存される。
- `agent_type` に `PROJECT` / `MEMBER` などを持ち、将来的な階層（`parent_agent_id`）も保持できる。
- `Skill` / `ProjectSkill` テーブルが存在し、エージェントとスキルの多対多の表現は可能。

### 1.3 現在のUI/設定面
- プロジェクト設定画面は現状 `system_prompt` の編集が中心で、エージェント名・説明・スキル割り当てを個別管理する画面は未整備。
- 既存APIには `GET /project/{project_id}/agents` があり、プロジェクト紐づきエージェント一覧は取得可能。
- ただし「プロジェクト内で有効なエージェント群」「デフォルトエージェント」の設定面は現状未実装。

### 1.4 既存設計上の示唆
- グラフは `direct_assistant` と `project_assistant` が定義済みだが、現在のビルダーは `direct_assistant` を固定使用。
- `MEMBER` エージェント管理ツール（作成/更新/削除）は存在し、将来の delegation 対応の土台はある。
- ただし、チャット起動時に「どの agent を使うか」をUI設定と連動して解決する経路は未整備。

---

## 2. 今回仕様（要件）整理

### 2.1 サイドメニューに Agent ページを追加
Agentページで以下を作成・更新可能にする。
1. agent名
2. agent説明（desc）
3. スキル割り当て

補足:
- graph は内部設定値として保持可能にしつつ、**当面はデフォルト graph（現行 direct graph）を固定割当**する。

### 2.2 プロジェクト設定への追加
プロジェクト設定でエージェント有効化方針を管理する。
1. チャットでデフォルト使用されるエージェント
2. プロジェクト内で有効なエージェント集合
   - デフォルト以外は将来サブエージェント（delegation対象）として呼び出されうる

### 2.3 非機能/将来要件との接続
- 今回は delegation 本体実装の前段として、**呼び出し可能なエージェント集合を明示管理**できる形にする。
- ランタイム選択（default agentの解決）と将来の動的委譲（active agents）を矛盾なく接続する必要がある。

---

## 3. 変更スコープ

## 3.1 バックエンド（API / ドメイン）
- Agent管理API（CRUD）
  - project配下エージェントの一覧・作成・更新・無効化
  - 更新対象: `display_name`, `description`, skill割当（`ProjectSkill`）
- Project設定API拡張
  - `default_agent_id`（単一）
  - `enabled_agent_ids`（複数）
- 実行時解決ロジック
  - チャット開始時に `default_agent_id` を解決し、そのAgentDefを組み立て
  - graphは当面 `direct_assistant` を強制
- バリデーション
  - default_agent は enabled_agent_ids に含まれること
  - project外 agent 指定の拒否
  - status=active のみ有効選択可能

### 3.2 データモデル
- 追加候補（推奨）
  - `projects` への `default_agent_id`
  - `project_agent_states`（または `project_settings` 的JSON）で enabled 管理
- 既存活用
  - skill割当は `ProjectSkill` を活用
- マイグレーション
  - 既存プロジェクト向け初期値移行（main PROJECT agentをdefaultにし、active agentをenabledへ）

### 3.3 フロントエンド
- サイドメニューに `/agents`（または project context の `/projects/[id]/agents`）導線追加
- Agent管理ページ
  - 一覧、作成、編集（name/desc/skills）
- プロジェクト設定ページ
  - default agent選択UI
  - enabled agents複数選択UI
- UX要件
  - default未設定時の警告
  - 無効化時にdefault整合性を崩す操作を防止

### 3.4 スコープ外（明示）
- delegation実行フロー本体（子run起動、ルーティング戦略最適化）
- graph切替UI（今回は固定）
- 高度なスキル推薦/自動割当

---

## 4. 導入ロードマップ

### Phase 0: 設計確定（短期）
- API契約・DB変更方針・UI導線を確定
- 命名統一
  - `default_agent_id`
  - `enabled_agent_ids`
  - `agent skills`（`ProjectSkill`）

### Phase 1: データ層とAPI整備
- DB migration作成
- Agent CRUD API + skill割当API
- Project agent設定API（default/enabled）
- 既存データ移行バッチ（初期default付与）

### Phase 2: UI実装
- サイドメニュー Agent導線追加
- Agentページ（一覧・作成・編集）
- Project Settings への default/enabled 設定フォーム追加

### Phase 3: 実行時統合
- チャット起動で project設定を読んで default_agent を解決
- enabledでないagentは実行候補から除外
- graph固定 (`direct_assistant`) を内部で適用

### Phase 4: 安定化
- 回帰テスト
  - 既存プロンプト編集との共存
  - default/enabled整合性
  - 既存プロジェクトでの後方互換
- 運用メトリクス
  - default agent切替率
  - enabled agent数分布

### Phase 5: 次段（将来）
- delegation実装
  - enabled agents をサブエージェント候補として利用
- graph選択の一般化
- エージェント能力可視化（skills/tools）

---

## 5. 実装前の意思決定ポイント（先に決めるべきこと）

1. Agentページのスコープ
   - 全体設定 `/agents` か、project配下 `/projects/[id]/agents` か
2. enabled管理の保存形式
   - 正規化テーブル vs JSONカラム
3. default agent の不整合時挙動
   - 自動復旧（先頭activeへ）か、エラーで保存拒否か
4. skill割当粒度
   - `Skill`単位のみか、将来 `Tool`単位UIまで見据えるか
5. 既存 `PROJECT` / `MEMBER` の扱い
   - UIで両方編集可にするか、まずは `PROJECT` 相当のみ許可するか

---

## 6. 推奨方針（初回実装）
- 最小実装としては以下が安全。
  - graphは固定 `direct_assistant`
  - default/enabled を project設定として明示管理
  - Agent編集項目は `name/desc/skills` に限定
  - delegationは未実装のまま、enabledを将来利用前提で保持
- これにより、将来の delegation 実装時にデータ互換を保ちつつ機能拡張が可能。
