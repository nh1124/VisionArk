# アーキテクチャ変更 事前調査レポート

## 1. 変更の概要（目的）

今回の変更案は、以下の3点を通じて **オーケストレーション責務の単純化** と **UI可視性の復旧** を狙うものです。

1. **routerの仕組みを廃止**
   - 現在は正規表現フック/購読情報に基づく非同期ディスパッチ機構が存在しており、実行経路が増えて追跡が難しくなっています。
   - これを廃止し、実行経路を「ユーザー入力→対象プロジェクト実行」中心に収束させる意図。

2. **toolから従来の連携（他member/他project呼び出し）を廃止**
   - ask/multicast/broadcast等のツールは「他エージェントに投げる」設計ですが、現行のengine起動経路では target_agent_id が実行エージェント選択に使われていません。
   - つまり、概念上の連携機能と実装実態に乖離があり、誤解を生むため廃止（または機能転換）したい。

3. **backend思考プロセス・ツールコール履歴のfrontend表示を修正**
   - DB/API/Frontend側に「submessageを思考過程として表示する」枠組みはあるものの、保存の入り口で履歴が欠落し、結果的に表示されない。
   - 本来期待される「thinking process + tool usage」可視化を回復する。

---

## 2. 現在の関連コード上の仕組み

### 2.1 Router関連

- `Router` は `api/router.py` で singleton 的に `_hooks` を保持し、メッセージ本文にregex一致したフックを `QueueManager.enqueue()` へ転送します。
- フックの初期化元は `ProjectAgent.meta_payload.trigger_patterns` で、`initialize_default_hooks()` がDBから読み直します。
- Worker起動時にRouter初期化し、さらに日次で `SYNC_ROUTER_HOOKS` をスケジュールして再同期しています。
- ツール側では `subscribe_to_intent` / `unsubscribe_from_intent` が `ProjectAgent.meta_payload` を更新し、直後にRouter再初期化を呼びます。

### 2.2 他member/他project連携ツール関連

- `AskAgentTool` / `BroadcastSystemMessageTool` / `MulticastMessageTool` は、`target_agent_id` を含むcontextでQueueに投入します。
- ただし実行側（`create_engine_for_project`）は **project単位で単一agent定義を都度生成**しており、`target_agent_id` を参照してagentを切替える処理がありません。
- さらに `_load_prompt_components()` では Team Roster（System/Members/Peer Projects）をプロンプトへ注入しており、「呼び出し可能に見える」情報を与える一方、実行は同一project agentに収束しやすい構造です。

### 2.3 思考プロセス/ツールコール表示関連

- API `/api/agents/project/{project_id}/history` は `ChatMessage.sub_messages` と `ChatSubMessage.tool_calls` を取得して返します。
- Frontend `projects/[projectId]/page.tsx` は `m.sub_messages` を `MessageWithAttachments` に渡し、同コンポーネント側でThinking Steps/Tool結果表示ロジックを持っています。
- しかしWorker保存時、submessage保存が `run_response.message.submessages` 依存になっており、`run.history` 側で発生した途中のTOOL_CALL/TOOL_RESULTが保存されにくい構造です。
- さらに `ToolUsage` レコードを実際には保存していないため、APIが期待する `sub.tool_calls` が空になりやすいです。

---

## 3. 変更内容（提案）

## 変更① Router廃止

### 推奨改修

- `api/router.py` を廃止（またはdeprecated化して no-op 化）。
- Worker起動時のRouter初期化、日次 `SYNC_ROUTER_HOOKS` スケジューリングを削除。
- `aes_system_handlers.py` の `SYNC_ROUTER_HOOKS` ハンドラを削除（互換期間はログのみ出して即return）。
- routing系ツール（subscribe/unsubscribe/list/multicast）を削除または非公開化。

### 影響

- `ProjectAgent.meta_payload.trigger_patterns` / `semantic_interests` の運用価値が下がるため、将来クリーンアップ対象。

## 変更② 他member/他project呼び出し廃止

### 推奨改修

- ツール登録から以下を外す（または明確に無効化）:
  - `ask_agent`
  - `broadcast_system_message`
  - `list_agents`（少なくとも「呼び出し先一覧」用途を廃止）
  - `multicast_message`（router系と連動）
- `_load_prompt_components()` の Team Roster 注入をやめるか、「参照情報のみ」である旨を縮退。
- 仕様として「1 run = 1 project agent」を明文化。

### 代替案

- もし将来本当にマルチagentをやるなら、Queue経由ではなく orchestration2 の delegation 機構に寄せる（現状は未接続）。

## 変更③ 思考プロセス/ツール履歴表示の修正

### 推奨改修

- Worker保存処理を `run_response.message` 依存から、**run全履歴（最低でもこのターンで増えたassistant/toolメッセージ）** を保存する方式へ変更。
- `ChatSubMessage.kind/run_id/step_id/meta_payload` を欠落なく保存。
- `sub.tool_call` 情報から `ToolUsage` レコードも保存する（APIが参照する `sub.tool_calls` を埋める）。
- 必要なら履歴APIで `sub.kind` や `tool_call` 本体（name/args/call_id/provider_data）を返し、frontend表示情報を強化。

### 期待効果

- frontend既存実装（`sub_messages`描画）だけで thinking/toolが自然に復活する可能性が高い。

---

## 4. 変更スコープ

## 変更① Router廃止のスコープ

- `core/backend/api/router.py`
- `core/backend/app/worker.py`（初期化 + 日次タスク登録）
- `core/backend/domains/automation/aes_system_handlers.py`（`SYNC_ROUTER_HOOKS`）
- `core/backend/domains/orchestration2/tools/library/routing.py`
- `core/backend/domains/orchestration2/engine_setup.py`（routingツール登録）

## 変更② 他member/他project連携廃止のスコープ

- `core/backend/domains/orchestration2/tools/library/system.py`
- `core/backend/domains/orchestration2/engine_setup.py`（systemツール登録）
- `core/backend/domains/orchestration2/engine_setup.py`（team roster 生成）
- 必要に応じて: prompt文言/運用ドキュメント

## 変更③ 表示復旧のスコープ

- `core/backend/app/worker.py`（保存ロジックの主改修ポイント）
- `core/backend/api/agents.py`（historyレスポンス項目調整）
- `core/frontend/app/projects/[projectId]/page.tsx`（受け取り項目の整合確認）
- `core/frontend/components/MessageWithAttachments.tsx`（表示項目拡張が必要なら）
- `core/backend/shared/database.py`（既存スキーマ利用で足りるか要確認。基本は追加migration不要見込み）

---

## 5. 変更ごとの改修難易度

- **変更① Router廃止: 中**
  - 依存点は複数ファイルに散っているが、機能的には「削る」方向が中心。
  - ただし運用タスク（`SYNC_ROUTER_HOOKS`）の後始末と互換ログ設計は必要。

- **変更② 他member/他project連携廃止: 低〜中**
  - 主にツール公開面の縮退で対応可能。
  - 既存プロンプトの期待値（team roster記述）と実動作の差を同時に是正すれば事故が少ない。

- **変更③ 思考/ツール履歴表示修正: 中〜高（最優先）**
  - 原因が「保存経路の情報欠落」にあるため、Worker保存設計の見直しが必要。
  - DB保存形式とAPI返却形式、frontend描画の3層整合が必要で、最もテスト観点が多い。

---

## 実施順（推奨）

1. **変更③（表示復旧）**: まず観測性を戻す。
2. **変更②（連携ツール縮退）**: 誤解を生む機能公開を止める。
3. **変更①（Router廃止）**: 最後に不要基盤を撤去。

この順序だと、まずデバッグ可能性を回復し、その後に機能整理を安全に進められます。
