# サブエージェント機能 本格実装レポート

## 1. 現状のエージェント実装

### 1-1. 実行基盤（orchestration2）
- 実行の中心は `AgentEngine` で、Tool / Skill / Role / Graph / Agent レジストリと、`Orchestrator` を束ねています。
- Run は `Orchestrator.run()` → `_run_loop()` でグラフをステップ実行し、`StepExecutor` が `role` / `skill` / `approval` / `delegation` / `responder` を処理します。
- 永続化は `Store` 抽象を介して行われ、現環境では `SQLAlchemyStore` が Run/Event/Approval/Delegation を DB 永続化します。

### 1-2. サブエージェントに関連する既存要素
- **Delegation のドメインモデルは実装済み**
  - `DelegationRequest` / `DelegationResult` / `DelegationResultStatus` があり、親 Run と子 Run の関連を保持できます。
- **DelegationManager は実装済み**
  - `delegate()` で親 Run を `WAITING_DELEGATION` にし、イベント `DELEGATE_TASK` を発火。
  - `complete_delegation()` で結果保存し、`DELEGATION_DONE` / `DELEGATION_FAILED` を発火。
- **AgentEngine 側に委譲 API は存在**
  - `delegate_task(parent_run_id, child_agent_name, task)` は子 Agent を名前解決し、子 Run を実行して結果を保存するところまで持っています。
- **グラフ仕様として delegation step は定義済み**
  - `GraphStep.type` に `delegation` が含まれます。

### 1-3. 現状の制約（本格運用を阻む点）
- デフォルトグラフ（`direct_assistant`, `project_assistant`）に delegation step が入っていないため、通常経路では委譲に遷移しません。
- Tool カタログに「委譲専用ツール（例: `delegate_task`）」が見当たらず、Role 推論中に自然にサブエージェント起動する導線が未整備です。
- `StepExecutor._execute_delegation_step()` は「結果イベントの有無確認」が主で、子 Run 起動オーケストレーションの責務が薄い実装です。
- `project_engine_builder` は 1 つのプロジェクト用 Agent を `direct_assistant` 固定で登録しており、複数 Agent を使い分ける設計がまだ限定的です。

---

## 2. 現状からの流用可能箇所

### 2-1. そのまま活用できるコンポーネント
1. **Delegation の状態管理**
   - `DelegationManager` + `RunStatus.WAITING_DELEGATION` + Event 発火はそのまま再利用可能。
2. **親子 Run の永続化構造**
   - `Store` API と `SQLAlchemyStore` の delegation 保存・取得を利用可能。
3. **子エージェント実行能力**
   - `AgentEngine.delegate_task()` は子 Agent 実行～結果確定の最小機能を既に保有。
4. **グラフによる制御枠組み**
   - `GraphStep(type=delegation)` と遷移条件 (`event.type`) で制御可能。

### 2-2. 部分流用（拡張前提）
1. **StepExecutor の delegation step**
   - 「待機点」としては使えるが、実運用では「どの Agent に何を投げるか」「並列数」「リトライ」「タイムアウト」をここか上位層で拡張する必要あり。
2. **Agent 登録フロー**
   - 既存の `create_engine_for_project()` は単一 Agent 前提が強いため、サブエージェント定義のロード機構を追加して流用。
3. **Role/Prompt 構成**
   - 既存 Prompt コンポーネントに「委譲判断基準」「委譲時の出力フォーマット」を追加すれば流用できる。

---

## 3. 実装方法の提案

### 3-1. 推奨アーキテクチャ（段階導入）
- **Phase A: Tool ベース委譲（最短で価値を出す）**
  1. `delegate_task` ツールを追加（引数: `child_agent`, `task`, `timeout_sec`, `context_scope`）。
  2. ツール実行時に `AgentEngine.delegate_task()` を呼び出す。
  3. 結果を親 Run の tool result / history に正規化して返す。
- **Phase B: Graph ネイティブ委譲（制御性向上）**
  1. `delegation` step を含む graph を追加。
  2. 役割ステップから delegation ステップへ遷移する条件を明示。
  3. `StepExecutor._execute_delegation_step()` を強化し、pending 管理・再開・失敗分岐を厳密化。
- **Phase C: 複数サブエージェント運用（本格運用）**
  1. Agent カタログ（役割別: researcher/writer/reviewer 等）を project 単位でロード。
  2. 並列委譲（`max_parallel_delegations`）と QoS（timeout/retry/backoff）を導入。
  3. 観測性（trace_id, parent/child run 可視化）と運用ガードレールを実装。

### 3-2. 実装上の重要ポイント
- **コンテキスト受け渡しの最小化**
  - 全履歴丸ごと渡しではなく、「要約 + 必要ファイル参照 + 制約」を child に渡す。
- **結果合成ルールを固定**
  - child 結果を親側で `completed/failed/timeout` に正規化し、最終応答に統一フォーマットで埋め込む。
- **失敗時戦略**
  - child fail/timeout 時に「再委譲」「自己継続」「ユーザー確認」のどれに進むかを graph 遷移で定義。
- **セキュリティ/権限**
  - 親 Agent が持つ tool 権限を child にどう継承/制限するかを明文化（原則は縮小権限）。

---

## 4. 変更スコープ

### 4-1. 必須変更（MVP）
1. **Tool レイヤ**
   - 委譲ツールの追加（`tools/library` + tool catalog 反映）。
2. **Engine 連携**
   - tool 実行から `AgentEngine.delegate_task()` 呼び出し導線を追加。
3. **Prompt/Role**
   - 委譲判断基準と出力規約を prompt に追加。
4. **Graph（任意だが推奨）**
   - delegation step を持つグラフを新設（既存 direct_assistant とは別 graph で安全導入）。

### 4-2. 本格導入で必要な追加変更
1. **project_engine_builder**
   - 単一 Agent 固定を外し、利用可能 Agent 群（親 + サブ）を登録。
2. **DB/設定**
   - プロジェクトごとに「利用可能サブエージェント」「優先度」「デフォルト timeout」を管理。
3. **API / UI**
   - 実行ログに親子 Run を表示（どの Agent が何を担当したか）。
4. **監視**
   - delegation 成功率、平均 child latency、timeout 率をメトリクス化。

### 4-3. 影響範囲（主対象ディレクトリ）
- `core/backend/domains/orchestration2/engine/**`
- `core/backend/domains/orchestration2/tools/**`
- `core/backend/domains/orchestration2/config/**`
- `core/backend/domains/orchestration2/bootstrap/**`
- （必要に応じて）`assets/prompts/**`, `core/backend/api/**`, `core/frontend/**`

---

## 5. 導入ロードマップ

### Milestone 0: 設計確定（1週間）
- 委譲ポリシー（いつ委譲するか、どの Agent に投げるか）を定義。
- child へ渡す context schema と、child から返す result schema を固定。
- 失敗時の遷移ルール（retry/fallback/confirm）を合意。

### Milestone 1: MVP（2週間）
- `delegate_task` ツール実装。
- `AgentEngine.delegate_task()` 連携。
- Prompt に委譲ルール追加。
- 最低限の E2E（親→子→親応答）テスト追加。

### Milestone 2: 制御強化（2週間）
- delegation step を使う graph を実装。
- timeout/retry/backoff、並列上限、キャンセル連動を追加。
- 失敗時の分岐品質を改善。

### Milestone 3: 本番運用準備（2〜3週間）
- 観測性（トレース、ダッシュボード、失敗分析）実装。
- 権限制御・監査ログ・レート制限を導入。
- feature flag で段階リリース（社内→一部ユーザー→全体）。

### Milestone 4: 継続改善
- 成果指標レビュー（成功率、応答品質、トークン効率）。
- Agent ルーティング最適化（ルールベース→学習ベース）。
- 複合タスク向けに多段委譲テンプレートを追加。

---

## 6. まとめ
- 現コードベースには、**Delegation の土台（モデル・状態遷移・保存・実行 API）**が既に存在します。
- 一方で、**通常フローに組み込む導線（委譲ツール、グラフ設計、複数 Agent 登録、観測性）**が不足しているため、現状は「部分実装」段階です。
- したがって、まずは **Tool ベースMVP** で実利を出し、その後 **Graph ネイティブ化 + 複数 Agent 運用**へ段階移行する進め方を推奨します。

---

## 7. Toolベース制御 vs Graphベース制御（比較整理）

「どちらをベースにするか」は、**短期価値を優先するか / 長期運用の制御性を優先するか**で判断するのが実務的です。

### 7-1. Toolベース制御（`delegate_task` ツール主導）

#### メリット
- **立ち上がりが速い**
  - 既存の Role → Tool 実行の流れに乗せられるため、MVPまでの実装コストが最も低い。
- **局所導入がしやすい**
  - 特定の Role / Skill だけに委譲を許可するなど、段階導入しやすい。
- **LLMの判断力を活かしやすい**
  - 「この作業は別Agentに投げるべき」という動的判断を自然に表現できる。
- **既存資産の流用率が高い**
  - `AgentEngine.delegate_task()` と現在の tool dispatch を繋ぐだけで最初の価値提供が可能。

#### デメリット
- **挙動が暗黙化しやすい**
  - 委譲判断がプロンプト依存になり、再現性や説明可能性が下がりやすい。
- **ガバナンス実装が後付けになりがち**
  - 並列数制御、リトライ戦略、失敗時分岐をツール側ロジックへ積み増すと複雑化する。
- **運用時の可視性が弱くなりやすい**
  - 「なぜ委譲したか」「なぜ再試行したか」を統一的に追跡しにくい。
- **品質の揺らぎ**
  - 同じ入力でもモデル判断で委譲有無が変わる可能性があり、SLA設計が難しい。

### 7-2. Graphベース制御（`delegation` step 主導）

#### メリット
- **フローが明示的で再現性が高い**
  - 委譲のタイミング・分岐・失敗時の遷移をグラフとして固定できる。
- **運用ガバナンスに強い**
  - timeout/retry/fallback/approval を step 遷移として定義でき、監査にも向く。
- **可観測性を作りやすい**
  - step/event単位でKPI（成功率、失敗率、遅延）を取りやすい。
- **チーム開発で保守しやすい**
  - 「仕様=グラフ」になり、レビュー観点が明確になる。

#### デメリット
- **初期設計コストが高い**
  - 分岐設計、状態遷移設計、例外系の網羅が必要で、MVP速度は落ちる。
- **柔軟性の不足が出る場合がある**
  - 非定型タスクでは、固定グラフが過剰制約になる可能性がある。
- **グラフ肥大化リスク**
  - ユースケースごとに分岐を増やすと、メンテコストが上がる。
- **導入初期の学習コスト**
  - 開発者が graph/compiler/step運用を理解する必要がある。

### 7-3. 判断の目安（どちらをベースにすべきか）

- **Toolベースをベースにすべきケース**
  - まずは早く実ユーザー価値を出したい。
  - 委譲対象が少数で、失敗時の影響が限定的。
  - 要件変動が大きく、仕様固定がまだ早い。

- **Graphベースをベースにすべきケース**
  - 委譲がプロダクトの中核機能で、安定運用が最優先。
  - SLA/監査/説明責任が必要。
  - 複数サブエージェントの並列・再試行・フォールバックを厳密管理したい。

### 7-4. 推奨方針（現状コードベース前提）

- 実務的には **「短期はToolベース、基盤はGraphへ寄せる」ハイブリッド** を推奨。
  1. **Step 1（短期）**: Toolベースで委譲を有効化し、ユースケースと失敗パターンを収集。
  2. **Step 2（中期）**: 収集したパターンを Graph の `delegation` step に昇格。
  3. **Step 3（長期）**: 重要経路はGraph固定、探索的経路のみTool判断を残す。

この進め方だと、**MVP速度** と **運用安定性** のトレードオフを最小化できます。


---

## 8. ご提案いただいた使い分けへの所見（結論: 非推奨ではなく、実務的に妥当）

ご提案の
1) 通常チャットは **tool/skill base（direct graph上）**
2) システム処理や意図的分散調査は **graph base（専用graph）**
という分離は、**現状の実装成熟度を踏まえると妥当**です。  
結論として、**非推奨ではありません**。むしろ段階導入として現実的です。

### 8-1. 良い点
- **通常チャットの速度・柔軟性を維持できる**
  - direct graph を維持しつつ、必要時のみ委譲するため、日常UXを崩しにくい。
- **高統制が必要な処理だけ graph に閉じ込められる**
  - 定型バッチ、監査対象処理、計画分解の厳密運用などを専用graphに隔離できる。
- **移行コストを抑えられる**
  - 既存経路を壊さず、重い要件だけ graph 化できるためリスクが低い。

### 8-2. 注意点（ここを外すと破綻しやすい）
- **ルーティング規約の明文化が必須**
  - 「どの条件で tool判断に任せるか / graphに強制遷移させるか」を仕様化する。
- **権限境界の固定**
  - tool base 側では child に渡す権限を縮小し、危険操作は graph base 側に限定する。
- **観測性の統一**
  - tool base と graph base でログ形式が分かれると運用不能になるため、
    `parent_run_id`, `child_run_id`, `delegation_reason`, `policy_path(tool|graph)` は共通記録する。
- **フェイル時の戻り先を固定**
  - timeout/failed 時の挙動（再試行、親で継続、ユーザー確認）を方式ごとに統一しておく。

### 8-3. 推奨運用ルール（最小セット）
- **デフォルト**: direct graph + tool/skill base（あなたの方針どおり）。
- **graph強制対象**:
  - 監査・再現性が必要な処理
  - 複数サブエージェント並列実行が前提の処理
  - 失敗時の厳密分岐（retry/fallback/approval）が必要な処理
- **段階的移行**:
  - tool base で成功/失敗パターンを収集 → 安定ユースケースから graph 化。

### 8-4. 最終意見
- あなたの案は「探索的・会話的タスクは柔軟に、重要タスクは統制的に」という分離で、
  **プロダクト実装として非常に筋が良い**です。
- ただし、長期的には「なんでも tool base」に流れないよう、
  **graph強制対象の基準**だけは先に決めておくことを強く推奨します。
