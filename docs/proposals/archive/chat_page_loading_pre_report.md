# ChatPage 全件読み込みに関する事前レポート

## 1. 現在のチャットページでのチャットの扱い方

対象: `core/frontend/app/projects/[projectId]/page.tsx` と `core/backend/api/agents.py`

### 1-1. フロントエンドの取得方式
- 画面初期化時に `fetchHistory()` が実行される。
- `activeSessionId` がある場合は `/api/agents/sessions/{session_id}/history`、ない場合は `/api/agents/project/{project_id}/history` を呼び出す。
- レスポンスの `history` 配列を **全件 map して `messages` state に入れ直す** 実装になっている。
- 承認リクエスト一覧 (`/api/approvals/project/{projectId}/list`) も並列で取得している。

### 1-2. タスク実行中の更新方式
- 実行中は WebSocket + 3秒間隔のポーリングが走る。
- タスク完了時に再度 history API を叩き、最終的に **履歴全体を再取得して再描画** する。
- つまり「差分追加」ではなく「全履歴の再同期」寄りの動作。

### 1-3. バックエンドの返却方式
- history API は `_get_history_for_session(session_id)` を経由し、`ChatMessage` を `created_at ASC` で取得。
- サブメッセージ・tool_calls まで含めて **セッション内メッセージをフルシリアライズ** して返す。
- 現状、ページング（`limit`/`offset`/`cursor`）や「最新N件のみ」指定はない。

---

## 2. 問題点

### 2-1. 初回表示遅延（TTI悪化）
- メッセージ件数が増えるほど API レスポンスと JSON parse が重くなる。
- さらにフロントで全件 map・state 置換・再レンダリングが走るため、初回表示が重くなる。

### 2-2. 更新時の再同期コストが高い
- タスク完了時に全履歴再取得のため、会話が長いほど毎回の更新コストが増大。
- 同じ過去メッセージを何度も送受信・再描画する。

### 2-3. DB/サーバー側の無駄な負荷
- 大規模セッションで sub_messages/tool_calls を毎回全展開するため、クエリ量・シリアライズ量が肥大化。
- 単一ユーザーの長時間利用でもエンドポイント負荷が線形増加する。

### 2-4. UX面の副作用
- 読み込み中の空白時間が長くなる。
- スクロール位置維持や体感レスポンスが不安定になりやすい。

---

## 3. 改善案

### 改善案A（最優先）: Cursorベースの履歴ページング

#### API
- `GET /history?limit=50&cursor=<message_id or timestamp>` を追加。
- 返却: `{ items, next_cursor, has_more }`。
- 初回は最新50件、上方向スクロールで過去を追加取得。

#### FE
- `messages` を「置換」ではなく「先頭 prepend / 末尾 append」で管理。
- `hasMore` が true の間のみ追加取得。
- 既存の初回 `fetchHistory()` は `fetchLatestPage()` に変更。

#### 効果
- 初回表示の payload を大幅圧縮。
- 長い会話でも表示速度を一定に近づける。

### 改善案B: 増分同期エンドポイント

#### API
- `GET /history/delta?after=<last_seen_message_id>` を追加。
- 既読以降の新規メッセージだけ返す。

#### FE
- タスク完了後は full refresh ではなく delta fetch。
- WSイベントと組み合わせて「確定時のみ差分補完」する。

#### 効果
- 毎ターンの再同期コスト削減。
- 通信量・再レンダリング負荷の抑制。

### 改善案C: メッセージ軽量化（summary-first）
- 履歴一覧では heavy fields（巨大 `tool_calls.result` など）を省略可能にする。
- 詳細表示が必要な時だけ `GET /messages/{id}` で展開。

### 改善案D: 仮想スクロール導入
- `react-virtuoso` 等で表示中DOM数を制限。
- 履歴件数が多くてもブラウザ描画コストを抑える。

### 改善案E: キャッシュ戦略
- セッション単位で SWR/React Query を導入し、stale-while-revalidate。
- 同一セッション再訪時の再取得量を削減。

---

## 4. 変更スコープとロードマップ

## 4-1. 変更スコープ

### Backend
- `core/backend/api/agents.py`
  - history API に `limit/cursor`（または `before_id/after_id`）を追加。
  - delta API 新設。
- 必要に応じて DB index 追加（`chat_messages(session_id, created_at, id)` など）。

### Frontend
- `core/frontend/app/projects/[projectId]/page.tsx`
  - 履歴取得ロジックをページング＋増分同期へ置換。
  - 無限スクロール（上方向）とスクロール位置維持。
- メッセージリストコンポーネントへ virtualized list の適用。

### QA/計測
- 指標: 初回履歴取得時間、payload size、LCP/TTI、タスク完了後反映時間。
- データセット: 100/1,000/5,000メッセージ相当で比較。

## 4-2. 推奨ロードマップ

### Phase 0（0.5〜1日）: 計測基盤
- 現状の API 応答時間・payload size・描画時間をロギング。

### Phase 1（2〜3日）: APIページング実装
- Backendに cursor pagination を追加。
- 既存APIとの互換維持（クエリなしは従来挙動）。

### Phase 2（2〜4日）: FE初回ロード改善
- 初回は最新N件のみ表示。
- 上スクロールで過去ページ取得。

### Phase 3（2〜3日）: 増分同期へ移行
- タスク完了後 full history fetch を廃止し delta fetch 化。

### Phase 4（2〜3日）: 仮想スクロール導入
- メッセージDOM肥大によるスクロール劣化を解消。

### Phase 5（1〜2日）: チューニング/回帰検証
- 指標比較、境界ケース（セッション切替・再送・承認フロー）確認。

---

## 5. 実装優先度（提案）
1. **A: ページング**（最も効果が高く、根本対策）
2. **B: 増分同期**（毎ターンの無駄削減）
3. **D: 仮想スクロール**（クライアント描画を安定化）
4. **C/E: 軽量化・キャッシュ**（仕上げ最適化）

以上を実施することで、長期運用プロジェクトでも「初回が重い」「更新のたびに重い」を段階的に解消可能。
