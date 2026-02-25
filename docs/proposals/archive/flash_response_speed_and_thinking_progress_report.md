# Flashモデル応答遅延・Thinking Process可視化 改善レポート

## 1. 目的・狙いと概要

### 目的
- Flash系モデル（例: `gemini-2.5-flash`）選択時でも、ユーザー体感として「1分以上待たされる」状態を解消する。
- 返答が完了するまでのブラックボックス時間を減らし、処理中の進捗（thinking/tool実行状況）を段階的に見える化する。

### 狙い
1. **response高速化**
   - 「モデル生成時間」だけでなく、前後の待ち（キュー、ポーリング周期、履歴再取得、プロンプト準備）を含めてレイテンシを最小化する。
2. **thinking processの経過表示**
   - 最終回答を待つだけでなく、処理途中の状態をUIに継続反映し、待機体験を改善する。

### 概要
現状実装は「HTTP POSTで非同期タスク投入 → 1秒ポーリングで完了検知 → 完了後に履歴APIでまとめて取得」の構成で、**途中経過が見えず、完了時のみ反映**される。さらにバックエンド側も、ステータス粒度が `queued/processing/completed` 中心のため、thinking/tool進行の可視化が難しい。

---

## 2. 現状の関連部分の実装

### 2.1 フロントエンドの送信〜反映フロー
- Projectチャットは `stream=false` で `/api/agents/project/{project_id}/chat` へ送信し、返却 `task_id` をURLに反映してポーリング開始している。
- ポーリング先は `/api/agents/tasks/{task_id}` で、完了時にのみ `/api/agents/project/{project_id}/history` を再取得して画面更新している。
- 処理中表示は `Queued... / Processing... / Thinking...` のテキスト中心で、サブステップは表示されない。

### 2.2 バックエンドの非同期実行フロー
- `chat_with_project` はユーザー入力を Queue に積み、即時に `task_id` を返す。
- Worker は Redisキューから取り出して `processing` に更新し、`_run_orchestration2` 実行後に `completed` へ更新する。
- Queue status の保存項目は主に `status/result/task_type/project_id` で、進捗率や中間ステップを持たない。

### 2.3 LLM実行（Gemini）
- `GeminiEngine` は `generate_content` をターンごとに呼び出し、tool call があれば実行して次ターンへ進むループ。
- レスポンスは最終的に `EngineRunResult` として返される設計で、UI向けの逐次ストリーム送出は行っていない。

### 2.4 Thinking/Tool履歴の保存
- Worker は run履歴の新規メッセージから `ChatSubMessage` と `ToolUsage` を保存しており、DB上は途中情報を保持可能。
- ただしフロント側は完了後履歴取得が前提で、実行中の段階的反映がされない。

---

## 3. 現状の課題

1. **体感待ち時間の増大（非ストリーミング + 完了後一括反映）**
   - 生成途中で情報が出ないため、実時間以上に遅く感じる。

2. **進捗の粗さ（ステータス3段階中心）**
   - `queued/processing/completed` では「どこで詰まっているか」が分からない。

3. **ポーリング主導の限界**
   - 1秒間隔ポーリングは簡便だが、即時性とサーバー効率のバランスが悪い。

4. **前処理コストの不可視化**
   - プロンプト部品読込・履歴変換・ツール実行などの時間内訳が観測しにくく、ボトルネック特定が難しい。

5. **Hub系フローとの整合不明瞭さ**
   - フロントには `/api/agents/hub/chat` を呼ぶ実装がある一方、同等のバックエンド経路が見えづらく、運用経路の混在リスクがある。

---



## 3.1 ポーリング vs WebSocket（補足回答）

結論として、**この用途では「ポーリングを使い続ける」のが最善とは限りません**。

- **ポーリングの長所**
  - 実装が簡単で既存構成（非同期タスク + status API）に乗せやすい。
  - 企業プロキシやLB配下でも比較的扱いやすい。
- **ポーリングの短所**
  - 取得間隔ぶん遅延が必ず乗る（例: 1秒間隔なら平均0.5秒の遅れ）。
  - クライアント数が増えると「無駄なリクエスト」が増える。
  - thinkingのような細かい進捗表示には不向き。

- **WebSocketの長所**
  - 双方向通信が可能で、低遅延のイベント反映に強い。
- **WebSocketの短所（本件文脈）**
  - 接続管理・再接続・認証更新・スケール設計（sticky/session共有）が重くなりやすい。
  - 今回の要件は「主にサーバー→クライアント片方向通知」であり、WebSocketの双方向性が過剰になりやすい。

- **SSE（Server-Sent Events）の位置づけ**
  - HTTPベースで片方向pushに特化し、今回の「thinking/progress配信」に適合。
  - 実装・運用コストはWebSocketより低く、ポーリングより体感が良い。

したがって推奨は、**第一選択をSSE、フォールバックをポーリング**とするハイブリッド構成。
WebSocketは将来「同時編集・双方向制御」などの要件が明確になった段階で導入を再検討する。

## 4. 改善方法と実装

以下は **短期（効果優先）→中期（構造改善）** の順で提案。

> 方針: リアルタイム表示はWebSocketではなく **SSE中心** で設計し、切断時のみポーリングにフォールバックする。

### 4.1 response高速化

#### A. 短期: 体感レイテンシ改善（実装容易）
- **SSE導入（最終回答前のトークン/段階イベント送出）**
  - API: `/api/agents/project/{id}/chat/stream` を新設し、`queued`, `running`, `tool_call`, `tool_result`, `partial_text`, `done` を逐次送出。
  - UI: EventSourceで受信し、placeholder assistant message を逐次更新。
- **ステータス詳細化**
  - Queue statusに `phase`, `updated_at`, `step`, `tool_name` を追加して、既存ポーリングUIでも詳細表示可能にする。
- **ポーリング間隔の段階制御**
  - 開始直後は短め（500ms）、長時間化したら1.5〜2秒へ緩和し、体感と負荷を両立。

#### B. 中期: 実時間短縮（バックエンド最適化）
- **プロンプト部品のキャッシュ**
  - `identity/formatting` など静的ファイルはプロセス内キャッシュ（mtime監視）で再読込削減。
- **履歴サマリ戦略**
  - 長大履歴を毎回全投入せず、直近Nターン + 要約でトークン量削減。
- **ツール呼び出し上限/タイムアウト最適化**
  - tool長時間実行時に中間イベントを出しつつ、必要に応じてタイムアウトと再試行ポリシーを明確化。
- **計測追加**
  - `enqueue→dequeue`, `engine_run`, `tool_exec`, `db_save`, `history_fetch` をメトリクス化し、p50/p95で追跡。

### 4.2 thinking processの経過表示

#### A. データモデル/イベント設計
- `TaskProgressEvent`（例）
  - `task_id`, `ts`, `phase`, `message`, `tool`(任意), `partial_text`(任意), `meta` を定義。
- 保存先は Redis Stream または Pub/Sub。

#### B. Worker側実装
- 主要ポイントで `progress_event` を発行
  - run開始
  - 各tool call開始/完了
  - 部分テキスト生成（対応可能な範囲）
  - run完了/失敗
- 既存 `ChatSubMessage` 保存は継続し、完了後の確定履歴として利用。

#### C. API/UI実装
- **SSE first**: `/progress/stream?task_id=...` でリアルタイム表示。
- **fallback**: 既存 `/tasks/{task_id}` に `last_event` / `recent_events` を追加してポーリングでも段階表示。
- UIでは以下を表示
  - phase badge（Queue / Prompt build / LLM / Tool / Finalize）
  - 最新thinking行
  - tool実行ログ（開始・終了・所要時間）

---

## 5. 実装手順

### Phase 0: 計測導入（先に実施）
1. Workerに区間タイムログ（enqueue待ち〜完了）を追加。
2. APIレスポンスへ `server_timing` 互換情報を暫定追加。
3. ボトルネックを実測（最低1日分）。

### Phase 1: 進捗可視化（小改修）
1. Queue status拡張（`phase`, `step`, `updated_at`）。
2. Workerでフェーズ更新を細分化。
3. Frontendでstatus textを詳細表示（例: `Running tool: read_file...`）。

### Phase 2: SSE導入（本命）
1. バックエンドにSSEエンドポイント追加。
2. Worker/Engineからprogress event配信。
3. FrontendでEventSource購読、メッセージ逐次反映。
4. ネットワーク断時はポーリングにフォールバック。

### Phase 3: 実時間最適化
1. prompt componentキャッシュ化。
2. 長履歴の要約投入戦略を追加。
3. ツールタイムアウト・再試行ポリシーの調整。
4. p95応答時間をKPI管理。

### Phase 4: 互換整理
1. hub系/ project系の経路差分を棚卸し。
2. 実運用で使う経路に統一し、不要経路を段階的に整理。

---

## 6. 変更スコープ

### Backend
- `core/backend/api/agents.py`
  - ステータスAPI拡張、SSEエンドポイント追加。
- `core/backend/infrastructure/queue/manager.py`
  - status payload拡張、進捗イベント管理。
- `core/backend/app/worker.py`
  - フェーズ別進捗更新、tool実行イベント発行、計測ログ。
- `core/backend/domains/orchestration2/engine_runtime/gemini_engine.py`
  - 部分出力/ツール進捗イベント連携（可能範囲）。
- `core/backend/domains/orchestration2/prompting/prompt_context_loader.py`
  - 静的プロンプト読込キャッシュ化（必要時）。

### Frontend
- `core/frontend/app/projects/[projectId]/page.tsx`
  - EventSource購読、進捗タイムライン表示、ポーリングfallback。
- `core/frontend/components/MessageWithAttachments.tsx`
  - thinking/tool progressの段階表示強化。
- （必要に応じて）`core/frontend/hooks/useChat.ts`
  - hub系フローの整合化。

### Docs/運用
- `docs/`配下に運用設計（イベント仕様、障害時fallback、KPI）を追加。
- 監視項目（p50/p95, queue wait, tool latency）定義。

---

## 補足（推奨優先順位）
1. **まずはPhase 0/1**（計測 + 詳細ステータス）で「どこが遅いか」を見える化。
2. 次に **Phase 2（SSE）** で待機体験を大きく改善。
3. 最後に **Phase 3** で実時間を削る。

この順に進めると、実装効果を定量化しながら安全に改善できます。
