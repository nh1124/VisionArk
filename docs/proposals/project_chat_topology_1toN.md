# Project-Chat 関係の見直しレポート（1対1 → 1対多）

## 1. 現在のチャット構成（As-Is）

### 1.1 データモデル
- `projects` と `chat_sessions` は DB 上は **1対多** で設計されている（`Project.sessions` リレーション）。
- `chat_sessions` は `project_id` を必須保持し、`parent_session_id` によりセッション分岐（スレッド派生）にも対応可能な設計。
- `chat_messages` は `session_id` で `chat_sessions` に紐づく。

**解釈**: スキーマ自体は 1対多セッションを許容しているが、実運用ロジックで「最新アクティブ1件」を採用している。

### 1.2 API 層の実装挙動
- `POST /project/{project_id}/chat` は入力時点で `session_id` を受け取らず、`project_id` 単位でキュー投入する。
- `GET /project/{project_id}/history` は `project_id` で未アーカイブセッションを新しい順に取得し、**先頭1件のみ**をアクティブセッションとして履歴返却する。
- `GET /project/{project_id}/active-task` も `project_id` 単位で進行中タスクを返す。

### 1.3 Worker / Queue 層の実装挙動
- Worker は `context.session_id` が無い場合、`project_id` の最新未アーカイブ `ChatSession` を再利用し、無ければ新規作成する。
- QueueManager の active task は `active_task:{project_id}` で管理され、project単位1本の復元キーになっている。

### 1.4 フロントエンドの実装挙動
- プロジェクト画面は履歴取得時に `GET /project/{project_id}/history` のみを使い、セッション選択UIは持たない。
- 送信時は `POST /project/{project_id}/chat` へ投げるため、実質「プロジェクト = 会話1本（最新セッション）」として扱われる。

### 1.5 現状まとめ
- **論理仕様（実装運用）**: project ↔ chat は実質 1対1。
- **物理スキーマ（DB）**: project ↔ chat_session は 1対多。
- つまり「将来1対多へ拡張しやすい下地はあるが、API・Worker・UIが1対1運用に固定されている」状態。

---

## 2. 1対1 と 1対多 のメリット・デメリット

## 2.1 1対1（現行運用）

### メリット
- UX が単純（開けば常に同じ会話）。
- 実装/運用コストが低い（セッション選択、命名、権限、分析軸が少ない）。
- タスク復元・通知・履歴APIなどを `project_id` 単位で簡単に扱える。

### デメリット
- 会話が長大化し、文脈肥大・検索性低下・誤参照リスクが増える。
- テーマ別会話（設計/実装/障害対応/顧客QAなど）を分離できない。
- 並行作業時に履歴が混線し、監査性（誰が何の文脈で判断したか）が弱くなる。
- 将来の「会話単位共有」「会話単位エクスポート」「会話単位権限制御」が難しい。

## 2.2 1対多（project配下に複数chat/session）

### メリット
- 文脈を用途別に分離でき、精度・可観測性・保守性が上がる。
- 同一project内で複数の思考ラインを並行実行できる（検証系/運用系など）。
- 会話単位のアーカイブ、要約、共有、分析（成功率・トークン量）が可能になる。
- 中長期的に「Project = コンテナ」「Chat = 作業ストリーム」という自然な情報設計に移行できる。

### デメリット
- UX が複雑化（セッション一覧、命名、切替、既定セッション概念が必要）。
- API/Worker/Queue/通知/課金メトリクスでセッション識別子の伝搬が必要。
- active task 管理を project単位1本から session単位へ再設計する必要がある。
- 移行期に旧クライアント互換とデータ整合性の二重管理が発生する。

---

## 3. 1対多へ移行する場合の変更スコープ

## 3.1 Backend API
- 追加候補:
  - `GET /project/{project_id}/sessions`（一覧）
  - `POST /project/{project_id}/sessions`（新規作成）
  - `PATCH /sessions/{session_id}`（タイトル変更/アーカイブ）
  - `GET /sessions/{session_id}/history`（履歴取得）
  - `POST /sessions/{session_id}/chat`（会話送信）
- 互換維持:
  - 既存 `POST /project/{project_id}/chat` は「default session へルーティング」に変更。
  - 既存 `GET /project/{project_id}/history` は default session のみ返す互換APIとして段階的縮退。

## 3.2 Worker / Queue
- `context` に `session_id` を必須（または強推奨）化。
- active task キーを `active_task:{project_id}` から `active_task:{session_id}`（＋必要に応じ `active_tasks:{project_id}` 集約）へ変更。
- タスク中断/復元/WS通知を session軸に合わせる。

## 3.3 Database
- 既存スキーマは概ね利用可能（`chat_sessions` が既に存在）。
- 追加推奨:
  - `chat_sessions.user_id`（高速検証・権限判定簡素化）※任意
  - `chat_sessions.last_message_at`（一覧ソート最適化）
  - `chat_sessions.is_default`（互換API運用時の既定セッション識別）
- インデックス見直し:
  - `(project_id, is_archived, updated_at)`
  - 必要に応じ `(project_id, is_default)`

## 3.4 Frontend
- 左ペイン等に「チャット一覧（セッション一覧）」追加。
- セッション新規作成、タイトル編集、アーカイブ、切替。
- URL を `/projects/{projectId}?session_id=...` で表現。
- 送信・履歴・タスクポーリング・再接続を session_id ベースに切替。

## 3.5 運用/監視
- メトリクス軸を project中心から session中心へ拡張（成功率、遅延、トークン消費）。
- 監査ログやエクスポート機能を session単位で再定義。
- ドキュメント/ヘルプ文言を「プロジェクト内複数チャット」前提へ更新。

---

## 4. 推奨ロードマップ（段階移行）

## Phase 0: 設計固定（1〜2日）
- セッション識別子の責務（UI/API/Queue/Worker）を決定。
- 互換APIポリシー（いつまで `project/*/chat` を残すか）を決定。
- default session の定義を決定（初回作成時自動生成など）。

## Phase 1: Backend先行（3〜5日）
- Session CRUD APIを追加。
- 既存 chat/history API を内部的に default session 経由へ変更。
- Worker が `session_id` 優先で動作するよう統一。
- Queue の active task を session軸対応（互換でproject軸も一時併用）。

## Phase 2: Frontend移行（4〜7日）
- セッション一覧UIと切替動線を実装。
- 履歴取得・送信・ポーリングを session_id 化。
- URL deep link 対応（session_id 指定で復元）。

## Phase 3: データ移行と互換縮退（2〜3日）
- 全projectに default session を保証（不足分の補完）。
- 旧API利用箇所を段階停止（ログ計測しながら）。
- project軸active-taskからsession軸へ完全移行。

## Phase 4: 最適化（継続）
- セッション自動命名、要約、アーカイブポリシー。
- セッション単位 analytics / 課金可視化。
- スレッド分岐（`parent_session_id`）をUIに露出。

---

## 5. 意思決定の提案

- 結論として、**中長期的には 1対多への移行を推奨**。
- 理由は、DB設計が既に1対多前提を許容しており、主要課題はデータモデルよりも「API/Queue/UIの運用設計」にあるため。
- ただし一括切替ではなく、**default session を介した後方互換付き段階移行**が安全。
- 最初のマイルストーンは「session_id を全経路で扱える状態」に置くのが最小リスク。
