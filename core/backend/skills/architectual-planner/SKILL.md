---
name: "Architectural Planner"
description: "プロジェクト全体の現状を分析し、中長期的な計画書（plan.md）を作成・維持管理するスキル"
id: "architectural-planner-v1"
tools: ["list_files", "read_artifact", "save_artifact", "search_knowledge"]
---

# Architectural Planner Procedure

プロジェクトを迷いなく進行させるため、以下の手順で「北極星」となる計画書を管理してください：

1. **実態調査**:
   - `list_files` と `read_artifact` で現在の実装状況や成果物を把握します。
   - 既存の `plan.md` や `README.md` を読み込み、現在のマイルストーンを確認します。

2. **ギャップ分析**:
   - ユーザーとの対話履歴や `search_knowledge` から、最終的に目指している「ゴール」を抽出します。
   - 現状とゴールの間にある未着手の課題や技術的負債を特定します。

3. **計画書の作成・更新**:
   - `save_artifact` を用いて、プロジェクトのルート（または適切な場所）に `plan.md` を作成または更新します。
   - `plan.md` には以下の構成を含めてください：
     - プロジェクトのビジョンと最終目標
     - 完了済みマイルストーン
     - 現在進行中のフェーズ
     - 今後の予定（TODOリスト）
     - 既知の制約やリスク

4. **コンテキストの同期**:
   - 他のエージェント・ノードが作業内容に迷った際、常に `plan.md` を参照するように指示を出します（`ask_node` 経由など）。

5. **継続的改善**:
   - 大きな進捗があった際や方向転換があった際は、直ちに計画書をリビジョンアップします。
