# Cron Task 事前調査レポート（Project 1対多チャット対応）

作成日: 2026-02-25  
対象: `POST_MESSAGE` 系の cron/scheduled task と Project 複数セッション運用

---

## 1. 現在の cron タスク仕様

### 1-1. 実行基盤
- `ScheduledTask` テーブルを AES Dispatcher がポーリングし、`PENDING` かつ `scheduled_at <= now` のレコードをキュー投入する。  
- 取り込み時に `status=PROCESSING`、`last_run_at=now` へ更新し、Worker 側で実行される。  
- Worker は AES system task を `AESSystemHandlers` にルーティングし、完了後 `status=COMPLETED` に更新する。  
- `recurring_rule` がある場合は実行後に次回タスクを複製作成（`@hourly/@daily/@weekly` の簡易実装、未知は daily 扱い）。

### 1-2. `POST_MESSAGE` の現在挙動
- Cron 画面 (`/cron`) で `task_type=POST_MESSAGE` を作成/更新可能。UI 入力は **project・message・scheduled_at・recurring_rule** のみ。  
- 保存 payload は `{ message }` のみで、`session_id` は保持していない。  
- 実行時の `PostMessageHandler` は `project_id` と `message` を使って `TaskType.USER_MESSAGE` を enqueue する。ここでも `session_id` は context に含まれない。  
- Worker の Project 実行ロジックは `context.session_id` が無い場合、プロジェクト内の非アーカイブセッションを `created_at DESC` で 1 件選択し、なければ新規作成してそのセッションに書き込む。

### 1-3. 1対多チャット（複数セッション）との関係
- 通常チャット API はセッション指定チャット (`/sessions/{session_id}/chat`) と、project デフォルトセッション向けチャットの両方を提供。  
- `POST_MESSAGE` 系 cron のみ、セッションが明示指定されず「実行時の自動選択」に委ねられている。

---

## 2. 問題点

1. **セッション決定が非決定的（ユーザー期待とズレる）**  
   - cron 登録時点で「どの会話スレッドに投稿するか」が固定されない。  
   - 後から新規セッションが増えると、同じ cron でも投稿先が変わりうる。

2. **選択ロジックが UI の “現在アクティブ会話” と整合しない**  
   - Worker の fallback は `created_at DESC` ベース。  
   - 一方で一覧/UI の「使っている会話」は `last_message_at` や URL の `session_id` を軸に扱う場面があり、指標が分断している。

3. **運用上の監査性が低い**  
   - 後から「なぜこのセッションに投稿されたか」を DB レコードだけで説明しづらい（タスク自体に session 情報がない）。

4. **再発タスク（recurring）でズレが累積しうる**  
   - 次回タスク複製時も payload を引き継ぐだけのため、設計上 session 固定がなければ毎回 fallback 判定になる。

---

## 3. 改善案

### A案（推奨・最小リスク）: `POST_MESSAGE` に `session_id` を明示保存

- cron 作成/更新 payload に `session_id`（任意だが実質必須）を追加。  
- UI では Project 選択後にセッション一覧を取得し、投稿先セッションを選択可能にする。  
- `PostMessageHandler` は `session_id` を `TaskType.USER_MESSAGE` の context に透過渡し。  
- Worker は `session_id` があれば必ずそのセッションに投稿。無効時は失敗か明示的 fallback（設定可能）にする。

**メリット**: 既存アーキテクチャ変更が小さく、挙動の予測可能性が上がる。  
**デメリット**: 既存タスクとの後方互換対応が必要。

### B案: `session_mode` を導入（`default` / `latest` / `fixed`）

- payload を `{"message": ..., "session_mode": "fixed", "session_id": "..."}` 形式に拡張。  
- `fixed` は A案同等、`default` は is_default セッション、`latest` は last_message_at 優先。  
- 将来の要件（「常に既定チャットへ」「直近作業チャットへ」）に対応しやすい。

**メリット**: 運用要件に柔軟。  
**デメリット**: 実装点が増え、テストケースが増大。

### C案（暫定）: fallback ロジックのみ改善

- `session_id` 未指定時の選択を `is_default` 優先、次点 `last_message_at DESC` に変更。  
- 現行 UI/運用とズレを減らす。

**メリット**: 変更が最小。  
**デメリット**: 根本的な「投稿先がタスクに保存されない」問題は残る。

---

## 4. 変更スコープ

### バックエンド
- `api/automation.py`  
  - `ScheduleTaskRequest.payload` のバリデーション拡張（POST_MESSAGE の `session_id` 許可/検証）。
- `domains/automation/aes_system_handlers.py`  
  - `PostMessageHandler` が `session_id` を context へ渡す。
- `app/worker.py`  
  - `session_id` 未指定時 fallback ポリシー統一（`is_default` 優先など）。
- （任意）`shared/database.py` マイグレーション不要  
  - 既存 payload(JSON) 活用で対応可能。

### フロントエンド
- `app/cron/page.tsx`  
  - Project 選択に応じた session 選択 UI 追加。  
  - 保存 payload に `session_id` を含める。  
  - 既存タスク編集時の session 表示/復元。

### テスト/検証
- API 単体: POST_MESSAGE 作成時の `session_id` バリデーション。  
- E2E: cron 実行で指定 session にメッセージが保存されること。  
- 回帰: session 未指定の旧タスクが想定 fallback で動作すること。

---

## 5. ロードマップ（提案）

### Phase 0: 方針確定（0.5日）
- A/B/C案の採用決定。推奨は A案（必要なら後続で Bへ拡張）。

### Phase 1: 互換性を保った backend 先行（1日）
- `session_id` を受け取り、実行コンテキストに透過。  
- 未指定時 fallback を `is_default -> last_message_at -> created_at` へ改善。  
- ログに `resolved_session_id` を出力し監査性を担保。

### Phase 2: cron UI 拡張（1日）
- session ドロップダウン追加。  
- 既存タスク編集時の表示対応。  
- 未選択時の警告文（「投稿先が変動する可能性あり」）を表示。

### Phase 3: 既存タスク移行サポート（0.5日）
- 既存 `POST_MESSAGE` タスクを列挙し、推奨 session を提案する管理 UI か補助スクリプトを用意。

### Phase 4: 安定化（0.5日）
- 実運用ログで誤投稿がないか確認。  
- 必要に応じて B案（`session_mode`）へ拡張。

---

## 補足（実務判断）
- まずは **A案 + fallback 改善** が費用対効果が高い。  
- 「デフォルト運用」か「特定スレッド固定運用」かをチーム内で先に決めると UI/文言がぶれない。  
- recurring を多用する運用ほど、session の明示固定は優先度が高い。
