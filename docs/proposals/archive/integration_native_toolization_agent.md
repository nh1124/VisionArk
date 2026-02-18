# integration native tool化 実装要件レポート（別エージェント向け）

作成日: 2026-02-17  
対象: integration を orchestration2 から利用可能にする実装担当エージェント

---

## 1. 目的

orchestration2 実行時に、`integrations/*/agent_tools.py` の機能を **native tool として呼び出し可能**にする。  
ただし、**実装コードの配置は `integrations/` 配下のまま維持**し、`domains/orchestration2/tools/library` への全面移植は行わない。

---

## 2. ゴール定義（Doneの条件）

以下をすべて満たしたら完了:

1. `create_engine_for_project()` 実行時に、core tool に加えて integration tool が tool registry に登録される。
2. integration tool は orchestration2 の `ToolDef + invoke(call, ctx)` 契約で実行される。
3. `ServiceRegistry.is_active` の状態に応じて tool の公開有無が切り替わる。
4. 同名toolが core 側と衝突する場合、挙動が明確（例: skip + warning log）である。
5. 実行時エラーは run 全体を即クラッシュさせず、`ToolResult.error` に変換される。
6. 最低限の検証（単体または統合）で「ロード」「実行」「エラーハンドリング」が確認できる。

---

## 3. 実装スコープ

### 3.1 変更してよい場所
- `integrations/`（adapter/loader の配置）
- `core/backend/domains/orchestration2/engine_setup.py`（登録導線）
- 必要最小限のテストファイル（既存テスト体系に合わせる）
- 必要最小限のドキュメント更新

### 3.2 変更してはいけない方針
- integration の実体実装（各 `client.py`, `api.py`, `agent_tools.py`）の大規模改変
- orchestration2 engine core の protocol 破壊的変更
- integration 実装を `domains/orchestration2/tools/library` へ移動

---

## 4. 機能要件

### 要件A: Integration Tool Adapter
- `va_sdk.BaseTool` を orchestration2 互換オブジェクトへ変換する adapter を用意する。
- adapter は以下を提供:
  - `definition: ToolDef`
  - `async invoke(call: ToolCallRef, ctx: ExecutionContext) -> ToolResult`
- `args_schema` が存在する場合は JSON Schema 化し `ToolDef.parameters` に反映。
- `args_schema` がない場合は空 object schema を使う。

### 要件B: Context マッピング
- orchestration2 の `ExecutionContext.metadata` から必要情報を取り出し、`IntegrationContext` を構築する。
- 必須マッピング:
  - `user_id`
  - `db_session`
  - `project_id`
  - `session_id`
  - `api_key`
  - `metadata`（透過）

### 要件C: Dynamic Loading
- `integrations/*` を走査し、`get_tools(user_id, db_session)` を持つ integration を対象にする。
- 各 integration から返る tool instance を adapter 化して登録候補にする。
- import 失敗や個別 integration 失敗は全体停止ではなく warning 扱いにする。

### 要件D: Engine登録
- `create_engine_for_project()` 内で:
  1. core tools 登録
  2. integration tools 登録
- tool名衝突時ルールを実装（推奨: integration 側 skip）。
- 登録件数をログ出力し、動作観測可能にする。

### 要件E: エラーハンドリング
- integration tool 実行例外は `ToolResult(error=...)` に変換する。
- integration が返す結果型が `va_sdk.ToolResult` でない場合も、最低限 `str()` で返せるようにする。

---

## 5. 非機能要件

1. **可観測性**: 起動/登録ログに、何件の integration tool が登録されたか出す。
2. **後方互換性**: 既存 core tools の挙動を壊さない。
3. **障害分離**: 1つの integration が壊れても他 integration の登録を継続する。
4. **最小侵襲**: 既存 integration 実装の構造は維持。

---

## 6. 推奨タスク分解（実装エージェント向け）

1. adapter/loader 実装（`integrations/` 配下）
2. `engine_setup.py` への組み込み
3. 重複名ポリシー実装
4. 例外処理・ログ整備
5. テスト追加（最低3系統）
   - 登録成功
   - 重複名スキップ
   - 実行時例外→`ToolResult.error`
6. ドキュメント最小更新

---

## 7. 受け入れ基準（Acceptance Criteria）

- [ ] `engine.list_tools()` に integration tool 名が現れる。  
- [ ] integration の active/inactive 切替で露出 tool が変わる。  
- [ ] tool 実行時に `IntegrationContext` が正しく埋まる。  
- [ ] 例外発生時に orchestration run が異常終了せず、tool result に error が残る。  
- [ ] 既存 core tool 呼び出しの回帰がない。  
- [ ] ログ上で登録件数・スキップ理由が追える。

---

## 8. テスト要件（最低限）

### テスト1: Loader
- ダミー integration を用意し、`get_tools()` から1件返す。
- loader が `ToolDef` を生成できることを確認。

### テスト2: Duplicate
- core 側と同名 tool を返す integration を用意。
- 登録がスキップされ、warning が記録されることを確認。

### テスト3: Invoke Error Path
- `run()` 内で例外を投げるダミーツールを実行。
- `ToolResult.error` が設定されることを確認。

### テスト4: Happy Path
- `va_sdk.ToolResult(content=..., is_success=True)` を返すケースで output が反映されることを確認。

---

## 9. 実装時の注意点

- schema生成時に Pydantic 例外が起きる可能性があるため、tool単位でフォールバックする。
- `db_session` 未注入時の挙動（fail-fast or error result）を明文化する。
- tool名は LLM が呼ぶ公開インターフェースなので、意図しない rename は禁止。
- 「登録できたが実行不可」状態を避けるため、最低1件の実行テストを必須化する。

---

## 10. PRに必ず含める説明

1. なぜ integration 配下維持で native化するのか
2. 既存 runtime との差分（呼び出し経路）
3. 衝突時ポリシー
4. 失敗時の挙動
5. テスト結果（コマンドと結果）

---

## 11. 今回の依頼に対する最終アウトプット定義

このレポートを実装エージェントへの仕様書として渡し、  
実装側は本仕様の「受け入れ基準」を満たすPRを作成すること。
