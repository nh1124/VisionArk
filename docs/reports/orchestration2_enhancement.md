# orchestration2 活用強化 事前調査レポート

作成日: 2026-02-13  
対象: `core/backend/domains/orchestration2` とその呼び出し層

---

## 1. 現在の orchestration2 実装と使い方の概要

### 1-1. 実装アーキテクチャ
- orchestration2 は **グラフ駆動 + レジストリ駆動** の実行エンジンとして設計され、`engine/` を再利用可能コア、`roles/` と `tools/` を VisionArk 固有実装として分離しています。
- 実行の主要経路は `Worker._run_orchestration2()` → `create_engine_for_project()` → `AgentEngine.execute_run()` → `Orchestrator.run()` です。
- ストアは `SQLAlchemyStore` を使用し、`orchestration_runs` / `orchestration_events` へ run/event を永続化します。

### 1-2. 実行グラフの現状
- 現在のプロジェクト用グラフは `main(role: project)` と `respond(responder, terminal)` の **2ステップ固定**です。
- `main` は `done` で `respond` に遷移し、それ以外は `main` に戻る単ループ構成です。
- `step_executor` の `responder` 実装は、実際には role 呼び出しをせず既存 `output_message` を返すため、`ResponderRole` の prompt は実行経路で活用されません。

### 1-3. ツール・スキル・モデルの使い方
- エンジン初期化時に files/search/ai/browser/governance/notes/system/members/writer/shell/markdown 系ツールを一括登録します。
- ただし AgentDef 側に `skills` を設定していないため、実行時は「スキル経由制約」ではなく **全登録ツール公開**になります。
- モデルは `GeminiLLMProvider` を `default` モデルとして登録し、project 実行時はこれを利用します。

---

## 2. 現状の使用状況

> ここでは「実装上どこで利用されているか」を整理（実運用の実行件数は別途 DB 集計が必要）。

### 2-1. 利用されている経路
- 通常のユーザメッセージ処理（`TaskType.USER_MESSAGE`）で、`project_id` がある場合は orchestration2 実行に統一されています。
- chat 保存時には `ChatSubMessage.run_id/step_id`、`ToolUsage.call_id` など orchestration2 追跡向けカラムへ記録します。
- `orchestration_runs` / `orchestration_events` テーブルがあり、RunRecord とイベントログの保持が可能です。

### 2-2. まだ部分利用・未接続な経路
- `create_project_from_prompt` や `decompose_task` は `GeminiLLMProvider` を直接呼び、orchestration2 の graph/role/skill には載っていません。
- `AgentEngine` は async 実行・resume・approval/delegation API を持ちますが、現行のプロジェクトグラフと呼び出し経路では実質ほぼ未活用です。

---

## 3. 現時点での使い方の問題点

1. **グラフが単純すぎて「オーケストレーション」の価値を使い切れていない**  
   - 2ステップの単一 role ループのため、推論フェーズ分離（Plan→Act→Verify）やタスク種別ごとの分岐ができていません。

2. **スキル制約が無効化された設計になっている**  
   - AgentDef に `skills` 未設定のため、`_gather_tool_definitions()` は全ツール公開にフォールバック。安全性と推論集中性の両面で不利です。

3. **プロンプト注入のキー不整合**  
   - `engine_setup` は `agent_profile` を metadata に積む一方、`ProjectRole` は `node_profile` を参照しており、DB のエージェント個別 prompt が反映されない可能性があります。

4. **継続実行（作業継続力）に弱い状態**  
   - `SQLAlchemyStore` の approval/delegation は in-memory 保持で、プロセス跨ぎやワーカー再起動に対して頑健ではありません。

5. **responder 設計の不整合**  
   - グラフ上 `role: responder` が書かれているが、`step_executor` の responder は role を呼ばず既存出力を返すだけで、設定が実質死に設定です。

6. **orchestration2 の適用境界が限定的**  
   - 周辺 API が provider 直呼びを残しており、共通の履歴・監査・制御ロジックに乗りません。

---

## 4. 改善提案（推論性能向上・作業継続力強化）

### 提案A: グラフを「Plan → Execute → Verify → Respond」へ分解
- 目的: 推論品質の向上（計画の明示化・自己検証の導入）。
- 内容:
  - `role(plan)` で短い作業計画を作る
  - `skill/role(execute)` でツール実行
  - `role(verify)` で要件充足チェック、不足時は execute へ戻す
  - 最後に `responder` で整形
- 効果: 回答の一貫性、抜け漏れ検知、不要ツール呼び出し抑制。

### 提案B: スキル登録 + AgentDef.skills でツール集合を制限
- 目的: 推論の集中と安全性向上。
- 内容:
  - 主要ユースケース（調査、文書作成、ファイル操作、運用）単位で SkillDef を定義。
  - graph step ごとに active skill を切り替え、必要なツールのみ公開。
- 効果: ツール乱用低減、トークン節約、失敗時の原因切り分け容易化。

### 提案C: metadata キー整合（`agent_profile` / `node_profile`）の修正
- 目的: カスタムプロンプトの確実な反映。
- 内容:
  - `ProjectRole` 側参照キーを `agent_profile` に合わせる（または両対応）。
- 効果: エージェント個性・運用ルールが実行に反映され、品質ばらつきを減らす。

### 提案D: Approval/Delegation 状態の永続化
- 目的: 作業継続力（中断復帰耐性）の強化。
- 内容:
  - pending approval / delegation を DB 管理へ移行。
  - `resume(run_id)` が再起動後でも再開可能なようにする。
- 効果: 長時間タスクやヒューマン承認フローに強い基盤。

### 提案E: orchestration2 適用範囲を周辺 API へ拡張
- 目的: 実装統一と観測性向上。
- 内容:
  - `create-from-prompt`、`decompose` も軽量 graph で実行。
  - 共通 run_id/event ログを残す。
- 効果: 品質改善施策を横展開しやすくなり、比較分析が可能。

### 提案F: 運用メトリクスの定義と可視化
- 目的: 「真価を引き出せているか」を定量判断。
- 指標例:
  - run 成功率 / 失敗種別
  - 1応答あたり tool call 数
  - verify での差し戻し率
  - 中断から再開成功率
- 効果: 改善の優先順位付けがデータドリブンになる。

---

## 5. 案ごとの変更スコープと優先度

| 提案 | 優先度 | 変更スコープ | 主要変更箇所 | 想定リスク |
|---|---|---|---|---|
| A. グラフ分解 (Plan/Execute/Verify) | P0 | 中 | `engine_setup.py` の graph、必要に応じ role 追加 | ループ設計を誤ると遅延増 |
| B. スキル制約導入 | P0 | 中〜大 | skill 実装追加、agent 登録時 `skills` 設定、運用設計 | 初期はツール不足で失敗しやすい |
| C. metadata キー整合 | P0 | 小 | `roles/project_role.py`（+必要なら `engine_setup.py`） | 低 |
| D. 承認/委譲の永続化 | P1 | 大 | `store/sqlalchemy_store.py`、DB スキーマ、resume 経路 | 移行・整合性の検証コスト |
| E. 周辺 API の orchestration2 化 | P1 | 中 | `api/agents.py`, `api/decomposer.py` ほか | 既存レスポンス仕様差分 |
| F. メトリクス可視化 | P1 | 中 | 集計クエリ/API/ダッシュボード | 計測定義の合意コスト |

---

## 6. 推奨実行順（短期ロードマップ）

1. **Week 1 (P0)**: C（キー整合）→ A（グラフ分解の最小版）→ B（最低限の skill 制約）
2. **Week 2 (P1)**: F（メトリクス導入）で効果測定開始
3. **Week 3-4 (P1)**: D（中断復帰）と E（周辺 API 展開）

この順序にすると、先に「品質改善の即効性（A/B/C）」を取り、次に「計測（F）」でボトルネックを確認しながら、最後に「継続力の土台（D）」と「適用面積拡大（E）」へ進めます。
