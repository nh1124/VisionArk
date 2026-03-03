# 事前調査: orchestration2 core tool library の機能重複・機能不全監査

作成日: 2026-03-03  
対象:
- `core/backend/domains/orchestration2/tools/library/*.py`（指定15ファイル相当）

---

## 1. 調査サマリ

本監査では、以下の2軸で確認しました。

1. **機能重複**（同じ目的を異なる tool が実現しており、agent の選択を曖昧化）
2. **機能しないツール**（現行コード上、呼び出し時に失敗する可能性が高いもの）

結論として、重大度が高い問題は次の3点です。

- `markdown.py` / `canvas.py` / `ai.py` が **存在しない `files.py` のクラス（`ReadReferenceTool`, `SaveArtifactTool`）に依存** している。  
- 指定対象に含まれる `document.py` は、現行の library には **ファイル自体が存在しない**。  
- 機能重複は「完全重複」よりも「責務境界の重なり」が多く、特に `write_file`・`update_md_section`・`create_note`・`create_workspace_item` 間で選択が曖昧。

---

## 2. 機能しないツール（高優先度）

## 2.1 `ReadMDSectionTool` / `UpdatePlanProgressTool` / `UpdateMDSectionTool`（markdown.py）

`markdown.py` は `files.py` から `ReadReferenceTool` / `SaveArtifactTool` を import して使用していますが、`files.py` に該当クラス定義がありません。  
そのため実行時 import エラーで失敗する可能性が高い状態です。

- 参照側:
  - `ReadReferenceTool` import/use: `markdown.py` L35-39, L135-139, L192-196
  - `SaveArtifactTool` import/use: `markdown.py` L109-116, L135-148, L239-244
- 定義不在側:
  - `files.py` は `WriteFileTool` などは定義するが、上記2クラスは未定義

## 2.2 `UpdateCanvasTool`（canvas.py）

`update_canvas` も `SaveArtifactTool` に依存して artifact 保存を行う設計ですが、同様に `files.py` に `SaveArtifactTool` が存在しないため、`file_path` 指定時に失敗リスクがあります。

- 参照側: `canvas.py` L37-44
- 定義不在側: `files.py`

## 2.3 `MermaidVisualizerTool`（ai.py）

`generate_mermaid_visualizer` は `SaveArtifactTool` を呼ぶ実装ですが、同じく定義不在依存です。

- 参照側: `ai.py` L500-508
- 定義不在側: `files.py`

## 2.4 `document.py`（指定対象）

今回指定された `core/backend/domains/orchestration2/tools/library/document.py` は現行ディレクトリに存在しません。  
設計上廃止済みか、参照更新漏れの可能性があります。

---

## 3. 機能重複（責務重なり）

## 3.1 文章/ドキュメント更新系の重複

- `write_file`: artifacts 配下へファイルを書き込む汎用書き込み。  
- `update_md_section`: Markdown セクション単位更新。  
- `create_note`: NoteService 経由でノート作成。  
- `create_workspace_item`: WorkspaceService 経由で共有アイテム作成。

いずれも「テキストコンテンツを保存する」操作であり、保存先とスキーマが異なるだけで、エージェントの観点では「どれを使うべきか」が曖昧になりやすいです。

## 3.2 計画更新系の重複

- `init_plan` / `update_plan_progress` / `get_current_status`（PLAN.md 専用）
- `update_md_section`（任意 markdown 汎用）

PLAN 専用 tool と汎用 markdown 編集 tool が並立しているため、どちらを正規経路とするかが曖昧です。

## 3.3 可視化アウトプット経路の重複

- `generate_mermaid_visualizer`: Mermaid を md として保存
- `update_canvas`: 画面キャンバス更新 + 任意で保存
- `write_file`: 直接 md 保存

「図/文書の最終成果物化」経路が複線化しており、成果物保存ポリシーを統一しにくい構造です。

## 3.4 委任対象定義の不整合（準重複問題）

`delegate_task` の説明は利用可能エージェントを researcher/writer の2種としている一方、seed 側では `reviewer` も定義されています。  
この差分により、機能自体はあるのに agent が使わない（または使いにくい）状態が起こりえます。

---

## 4. 改善提案

## 4.1 まずは機能不全を解消（P0）

1. `ReadReferenceTool` / `SaveArtifactTool` の扱いを統一
   - 選択肢A: `files.py` に互換ラッパーとして再導入
   - 選択肢B: `markdown.py` / `canvas.py` / `ai.py` を `read_file_chunk` / `write_file` ベースへ全面置換
2. `document.py` の扱いを明確化
   - 廃止済みなら docs/設定から参照を削除
   - 必要なら新規再導入

## 4.2 次に重複責務を整理（P1）

1. **保存先で tool を明確分離**
   - artifacts への成果物保存: `write_file` 系
   - Knowledge note: `create_note`
   - Shared context: `create_workspace_item`
2. `update_md_section` の適用範囲を限定
   - PLAN.md は専用 tool のみ、または逆に汎用 tool へ一本化
3. `delegate_task` の説明を seed 実態に同期
   - `reviewer` を説明へ反映

## 4.3 監査ルール化（P2）

- `default_catalog.py` に登録される core tool について、CI で以下を検査
  - invoke 内 import 先が存在すること
  - 内部呼び出し tool 名が実在すること
  - ツール説明の利用可能サブエージェントが seed 実態と一致すること

---

## 5. 参考: 実施した確認コマンド

- `rg` による tool 定義/参照調査
- `ls core/backend/domains/orchestration2/tools/library` による対象ファイル存在確認
- 簡易 Python スクリプトで `ReadReferenceTool` / `SaveArtifactTool` の「使用有無」と `files.py` 内「定義有無」を照合

