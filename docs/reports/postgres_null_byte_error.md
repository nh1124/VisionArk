# エラー調査レポート: PostgreSQLへのNULLバイト挿入エラー

## 1. エラー概要
**事象**: `atmos-worker` がタスク実行中に `sqlalchemy.dialects.postgresql.asyncpg.Error: <class 'asyncpg.exceptions.CharacterNotInRepertoireError'>: invalid byte sequence for encoding "UTF8": 0x00` というエラーでクラッシュしました。
**発生箇所**: `ChatSubMessage` テーブルへの `INSERT` 処理中。
**トリガー**: `read_reference` ツールが PDF ファイル (`refs/14e5ac24-f272-4361-a8a0-ee9f0303b70f.pdf`) を読み込み、その内容を `tool_result` として返したタイミングで発生しました。

## 2. 原因詳細
PostgreSQL の `TEXT` 型カラムは、内部表現として C言語形式の文字列（ヌル終端文字列）を使用する制約上、文字列の途中に `0x00` (NULLバイト) を含めることができません。
一方、Python の `str` 型や UTF-8 エンコーディング自体は `0x00` を許容します。

今回のケースでは以下の流れでエラーが発生しました：
1. `read_reference` ツールが PDF ファイルを読み込む際、`encoding="utf-8", errors="ignore"` で無理やりテキスト化しました。
2. PDF ファイル等のバイナリには `0x00` が含まれることが多く、これが Python の文字列変数 (`sub.content`) に混入しました。
3. `worker.py` がこの文字列をサニタイズせずに `ChatSubMessage` テーブルへ `INSERT` しようとし、`asyncpg` ドライバが PostgreSQL の仕様に反するデータを検出して例外をスローしました。

## 3. 改善案と修正方針

### 短期的な修正 (推奨)
データベース保存直前に、文字列に含まれる NULLバイトを空文字に置換するサニタイズ処理を追加します。

**変更スコープ**:
- **対象ファイル**: `core/backend/app/worker.py` (1ファイルのみ)
- **影響範囲**: `ChatSubMessage` および `ToolUsage` テーブルへの INSERT/UPDATE 処理。
- **リスク**: 低。既存の機能に影響を与えず、単にエラーを回避する守りの修正です。

**修正コード案**:
```python
def sanitize_text(text: str) -> str:
    """PostgreSQLが許容しないNULLバイトを削除する"""
    if not isinstance(text, str):
        return text
    return text.replace("\x00", "")

# ... (中略) ...

# 修正前
db_session.add(ChatSubMessage(..., content=sub.content, ...))

# 修正後
db_session.add(ChatSubMessage(..., content=sanitize_text(sub.content), ...))

# ToolUsageのresultも同様に修正が必要
tu.result = sanitize_text(sub.content)
```

### 長期的な検討事項
- **バイナリファイルの扱い**: PDF などのバイナリファイルを `read_reference` で読み込む際、テキストとして扱うのではなく、「[PDF File]」のようなプレースホルダーのみを返すか、Base64エンコードする仕様への変更を推奨します。これにより、トークン数の節約と文字化け防止にもつながります。

**変更スコープ**:
- **対象ファイル**: `core/backend/domains/orchestration2/tools/library/files.py` (ツール定義)
- **影響範囲**: `read_reference` ツールを使用するすべてのアージェント/機能。
- **リスク**: 中。ツールの挙動が変わるため、エージェントがファイル内容を期待している場合に混乱する可能性があります（例: PDFの中身を読み取って回答する場合など）。機能要件の見直しが必要です。
