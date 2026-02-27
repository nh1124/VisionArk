# コマンド仕様見直しレポート（改訂版 / 2026-02-25）

本レポートは**現行コード実装を基準**に、`/new` への移行とコマンド体系の再整理を中心にまとめる。

## 1. コマンドの実装方法（現状）

### 1.1 バックエンド実行フロー
1. `POST /api/commands/execute` で `text/scope/project_id` を受け取る。  
2. `parse_command(text)` で `Command(name, args, raw_input)` に変換。  
3. `_get_command_map()` で解決した `BaseCommand` 実装の `run()` を呼び出す。  
4. `CommandResult(success, message, data)` を API レスポンスへ変換。  

### 1.2 実装上のポイント
- 先頭 `/` でない入力はコマンドとして扱わない。  
- 引数は `shlex.split` 前提（引用符対応）。  
- 各コマンドは `BaseCommand` 継承で拡張可能。  

### 1.3 フロントエンド接続
- `projects/[projectId]/page.tsx` で `/` 始まり入力を API 実行。  
- `CommandAutocomplete.tsx` が `GET /api/commands/list` で補完候補を取得。  

---

## 2. 実装されているコマンド（現行）

### 2.1 正規名
- `/archive`
- `/move`
- `/create_project`
- `/delete_project`
- `/clone`
- `/send_message`
- `/resend`
- `/undo`
- `/timer`
- `/note`

### 2.2 エイリアス
- `/mv` → `/move`
- `/kill` → `/delete_project`

---

## 3. 主要提案: `/create_project` を `/new` に統一

### 3.1 方針
- ユーザー向け主コマンド名を `/new` に統一する。  
- 移行期間中は `/create_project` を後方互換 alias として維持する。  

### 3.2 実装仕様
- `command_parser.py` のマップに以下を定義：
  - `"new": CreateProjectCommand`
  - `"create_project": CreateProjectCommand`（互換）
- `CreateProjectCommand` の公開メタ情報を以下に更新：
  - `name = "new"`
  - `usage = "/new <name> [prompt]"`
- `/api/commands/list` では `/new` を主表示し、`/create_project` は alias として表示。  

### 3.3 互換運用
- 2〜4週間は `/create_project` 実行時に「`/new` 推奨」メッセージを返却。  
- 利用率観測後、alias 継続または廃止を判断。  

### 3.4 受け入れ条件（Acceptance Criteria）
- `/new my_project` で既存と同等にプロジェクト作成できる。  
- `/create_project my_project` も移行期間中は成功する。  
- 補完一覧で `new` が主表示される。  

---

## 4. 追加・削除提案（全体整理）

### 4.1 追加候補
1. `/help`（高優先）  
   - 既存のコマンド一覧生成ロジックを活用し、自己解決導線を強化。  
2. `/task`（中〜高優先）  
   - クイックタスク投入をコマンド化し、チャット起点の記録を短縮。  
3. `/report`（中優先）  
   - `send_message` の意味をユーザー向けに明確化する上位語彙。  
4. `/switch`（中優先）  
   - `/move` 同義語として導入し、操作語彙を分かりやすくする。  

### 4.2 削除・統合候補
1. `/kill` の廃止（高優先）  
   - 破壊的な語彙で誤操作リスクが高く、`/delete_project` に統一が望ましい。  
2. `/send_message` の外部公開見直し（中優先）  
   - ユーザー向けには `/report` に寄せ、内部用途に限定する案を検討。  
3. 長いコマンド名の整理（中優先）  
   - `create_project -> new` のように、日常操作は短縮名を優先。  

### 4.3 運用ルール案
- 追加時: 正式名 + 必要最小限 alias に限定。  
- 削除時: 非推奨期間（案内メッセージ）を経て廃止。  
- 互換期間: 最低2週間、推奨は1リリースサイクル。  

---

## 5. 変更スコープ

### 5.1 バックエンド
- `core/backend/domains/automation/command_parser.py`
  - `/new` 追加、`/create_project` を alias 化
- `core/backend/domains/automation/commands/library.py`
  - `CreateProjectCommand` の `name/usage` 更新
- `core/backend/api/commands.py`
  - list 表示で主コマンド名と alias 表示が意図どおりか確認

### 5.2 フロントエンド
- `core/frontend/app/components/CommandAutocomplete.tsx`
  - 補完表示で `/new` が主表示であることを確認
- `core/frontend/app/projects/[projectId]/page.tsx`
  - 実行後の案内文（必要なら非推奨メッセージ表示）確認

---

## 6. 導入ロードマップ

### Phase 1（即時）
- `/new` 追加（`/create_project` 互換維持）
- 補完表示を `/new` 中心に調整

### Phase 2（次スプリント）
- `/create_project` 非推奨表示
- `/kill` alias の安全性見直し（警告または廃止）

### Phase 3（運用）
- コマンド利用率を計測し、低利用 alias を整理
- `/help` 導入で推奨コマンド体系を明示

---

## 7. 結論
- 本改訂では、`/clear` 提案は取り下げ、`/new` への移行計画を主軸に再構成した。  
- 併せて、追加・削除候補と運用ルールを明文化し、実装判断の基準を揃えた。  
- まずは `/new` 移行を先行実施し、その後に周辺コマンド整理を段階的に進める。  
