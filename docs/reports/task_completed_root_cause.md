# 「Task completed.」フォールバックが返る原因分析レポート（orchestration2）

## 結論（先に要点）
`Task completed.` は orchestration2 側の正常完了メッセージではなく、`Worker._run_orchestration2()` の**空文字フォールバック**です。  
つまり「最終 `run_response.message.content` が空（または `None`）」になった時点で、実行が失敗・未収束・空応答でも同じ文言に上書きされます。

---

## 1. フォールバックが発火する直接条件
`Worker._run_orchestration2()` では、`run_response.message` が無い/空文字の場合に強制的に `Task completed.` を返します。

- `run_response.message.content` を `response_text` に入れる
- `response_text.strip()` が空なら `"Task completed."` に置換

このため、実体としては「失敗」「空応答」「ツール呼び出しのみで最終文が未生成」のいずれでも UI は同じ表示になります。

---

## 2. 空レスポンスが発生する主な経路

### 経路A: role step が `done` を出せず、ツールイベントのみでループする
現在のデフォルト graph は `main(role)` で `event.type == 'done'` のときだけ `respond` へ遷移し、それ以外は `main` に戻ります。  
一方で role step は LLM が `tool_calls` を返した場合、`TOOL_CALL/TOOL_RESULT` イベントを積むだけで `DONE` イベントを出しません。

結果:
- `done` 条件に一致せず `main` へ戻り続ける
- ターン上限/ツール上限で失敗して run 終了
- ただし `run.output_message` が未設定のまま終了し得る
- Worker 側フォールバックで `Task completed.` 表示

### 経路B: LLM 応答が function call 中心で本文テキストが空
Gemini プロバイダはレスポンスから text part を連結して `content` にします。function call だけだと `content` は空文字になります。  
この状態で最終的な自然言語応答が生成されないと、`run.output_message.content` が空のままになりやすく、Worker フォールバックが発火します。

### 経路C: run が FAILED でも Worker がエラー面を表示しない
Orchestrator は上限超過などで `run.status=FAILED` / `run.error` を保存しますが、Worker は `run.error` を表示せず、`message.content` の空判定のみで `Task completed.` に置換します。  
そのため、実際は失敗していても UI 上は「完了」に見えます。

### 経路D: responder step 側でも空文字を救済し切れない
`_execute_responder_step()` は `run.output_message.content` が空なら `last_assistant[-1].content` を使いますが、最後の assistant content 自体が空文字のケースでは、最終 `run.output_message` も空文字になり得ます。

---

## 3. 今回の症状との整合（添付画面: Thinking Process 6 turns + Task completed.）
表示上「6 turns」進んでいるのに最終文が `Task completed.` なのは、次の流れと整合します。

1. main(role) で複数ターン推論（tool call を含む）
2. どこかで最終自然言語を確定できず、`run.output_message` が空/未設定
3. Worker が空文字フォールバックを適用
4. UI に `Task completed.` が表示

特に graph を更新して「推論設計」を変えた場合、`done` 遷移条件と role の `DONE` 発火条件が噛み合っていないと、この症状が再現しやすいです。

---

## 4. コード上の原因ポイント

1. **フォールバック本体（表示の上書き）**
   - `core/backend/app/worker.py`
   - `response_text` が空なら `"Task completed."` を代入

2. **done 遷移依存の graph**
   - `core/backend/domains/orchestration2/engine_setup.py`
   - `main` は `event.type == 'done'` でのみ `respond` へ

3. **tool_calls 分岐で DONE 非発火**
   - `core/backend/domains/orchestration2/engine/orchestration/step_executor.py`
   - `if llm_response.tool_calls:` では `TOOL_CALL/TOOL_RESULT` のみ

4. **role が completion を宣言しない設計**
   - `core/backend/domains/orchestration2/roles/project_role.py`
   - `post_process(...).done=False` 固定

5. **function-call中心応答で content 空になり得る**
   - `core/backend/infrastructure/llm/orchestration2_provider.py`
   - text part 連結のみを `content` として採用

6. **FAILED の詳細がユーザー面に出ない**
   - `core/backend/domains/orchestration2/engine/orchestration/orchestrator.py`（`run.error` 保存）
   - `core/backend/app/worker.py`（`run.error` 未反映、空文字だけフォールバック）

---

## 5. 優先度付き改善案

### P0（まずやる）
1. Worker の空文字フォールバックを「成功時のみ」に限定する。  
   - 例: `run_response.completed == False` かつ空文字なら `Task failed: ...` を返す
2. 失敗時は `run.error` をユーザー面/ログに露出させる。

### P1（再発防止）
3. `tool_calls` 分岐後に「追加で LLM 再呼び出しして最終回答を生成」する終端パスを明示する。
4. もしくは graph 側に `tool_result` 受領後の要約 step（必ず自然言語を返す step）を置く。

### P2（設計整合）
5. `ProjectRole.post_process()` の `done` 判定ポリシーを導入（終端宣言可能にする）。
6. responder step で空文字なら固定文ではなく `run.error` / 直近イベントを反映する。

---

## 6. 切り分け手順（運用）
1. `orchestration_runs` の `status/error/current_step_id` を確認
2. 同 `run_id` の `orchestration_events` を時系列確認（`DONE` が出ているか、`TOOL_RESULT` ループか）
3. `chat_sub_messages` で最終 turn の `tool_call/tool_result` と assistant text の有無を確認
4. 上記で assistant最終文が空なら、Worker フォールバック発火が確定

以上より、本件は「role/graph 更新そのもの」だけでなく、**空応答を成功文言へ上書きする返却層（Worker）の仕様**が症状を強く見えにくくしているのが本質です。
