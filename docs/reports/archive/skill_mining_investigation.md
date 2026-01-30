# Skill Mining Investigation & Improvement Report

## 1. 現状のスキルマイニング機能の調査結果

### 1.1 動的スキルマイニングの現状の手法
現在のスキルマイニングは、エージェントのインタラクションから「反復可能な手順（Procedural Intelligence）」を自動抽出し、新しい「スキル」としてドラフト保存する仕組みとなっています。

- **トリガー場所**: `core/backend/worker.py` のタスク処理ループの最後（`finally` ブロック）で実行されます。
- **実行条件**: タスクタイプが `USER_MESSAGE` または `NODE_EXECUTION` であり、かつメッセージ内にツール実行（`tool_calls`）が含まれている場合。
- **抽出ロジック (`skill_mining.py`)**:
    1. 最新のメッセージ10件をコンテキストとして取得。
    2. LLM (`gemini-3-flash-preview`) を使用して、その手順を `SKILL.md` 形式に変換。
    3. JSON形式で抽出されたメタデータ（name, description, id, content）を `is_draft=True` としてデータベースの `skills` テーブルに保存。
- **その他の手法**:
    - `AES (Automated Execution System)` によるバッチマイニング（過去20セッションをまとめて解析）も実装されていますが、現在は主に上記のリアルタイムトリガーがメインです。

### 1.2 低質なスキルの作成とキュー圧迫の原因
調査の結果、以下の3点が主な原因であることが判明しました。

1. **過剰なトリガー頻度 (Hyper-active Triggering)**:
   - メッセージ1通ごとに（ツール呼び出しがあれば）バックグラウンドで解析が走るため、同一セッション内で何度も同じスキルのドラフトが作成されます。
2. **重複排除（Deduplication）の欠如**:
   - `skill_mining.py` 内の `_check_duplicate_skill` がコメントアウトされており、既に同名のスキルや類似の手順が存在しても、新しいドラフトとして保存されます。
3. **キュー管理の不在とリソース競合**:
   - `worker.py` 内で `asyncio.create_task` を使って直接並列実行されています。これにより、メインのタスク処理と並行して大量のLLMリクエストとDB接続が発生し、システム全体のレスポンス低下やLLMのレート制限、キューのブロッキング（暗黙的なリソース競合）を引き起こしています。
4. **低質な抽出（Low-quality Extraction）**:
   - ツールを1回使っただけの単純な行動（例：1つのファイルを読んだだけ）でも「スキル」として抽出しようとするため、汎用性のない断片的なスキルが量産されています。

---

## 2. 改善案の提案

### 2.1 概要
スキルマイニングを「各メッセージごとの反応的処理」から「重要度の高いタイミングでの計画的処理」へと移行します。また、重複排除と複雑性評価を導入し、質の高いスキルのみをドラフト化します。

### 2.2 具体的手法

#### ① AES (Automated Execution System) への完全移行
- `worker.py` での直接実行を廃止し、スキルマイニングが必要な場合は `SYSTEM_SKILL_MINING` タスクを AES キューにエンキューするように変更します。
- これにより、スキルマイニングの実行優先度を下げたり、並列数を制限したりすることが可能になり、メインのメッセージ処理への影響を最小限に抑えられます。

#### ② 複雑性スコアリング（Complexity Heuristics）
- 単純な `has_tools` だけでなく、以下の条件を追加します。
    - ツール呼び出し回数が閾値以上（例：3回以上）。
    - 異なる種類のツールを組み合わせて使用している。
    - タスクのステータスが「完了（Completed）」したタイミングでのみ実行。

#### ③ セマンティック重複排除（Semantic Deduplication）
- 生成前に、既存のスキル（Active/Draft両方）の `name` や `trigger_patterns` と比較し、類似度が高い場合は生成をスキップします。
- LLMに「これは新しいスキルと呼べるか？」を判定させる安価なプリチェック（Check-then-Generate）を導入します。


### 2.3 変更スコープ

- **`core/backend/services/skill_mining.py`**:
    - 重複チェックロジックの実装。
    - 手順の複雑性を評価する関数の追加。
- **`core/backend/worker.py`**:
    - `asyncio.create_task` による直接呼び出しの削除。
    - 完了時に AES タスク（`SYSTEM_SKILL_MINING`）として登録するロジックへの差し替え。
- **`core/backend/services/aes_system_handlers.py`**:
    - `SkillMiningHandler` の強化（リトライ制御やバッチ処理の最適化）。
- **`core/backend/models/database.py`**:
    - (任意) スキルの値のハッシュ保存用カラムの追加（高速な重複チェックのため）。

---
**作成者**: Antigravity (AI Architect)
**日付**: 2026-01-29
