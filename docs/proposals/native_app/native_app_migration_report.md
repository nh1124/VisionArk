# Native App 要件定義レポート（ローカル常駐アシスタント構想）

## 0. 前提と狙い

本レポートは、以下の役割分担を前提に Native App の仕様を固めるための要件整理である。

- **Server / Web App**: チャット、AIオーケストレーション、プロジェクト状態管理の本体
- **Native App（ローカル端末）**: 端末常駐の操作実行レイヤー（状態把握・ローカル操作・実行代行）

この構成により、Web経由の指示をローカル環境で安全に実行し、エージェントの実行力を拡張する。

---

## 1. Native App の役割

### 1.1 役割A: ローカル常駐アシスタント
- ユーザーの端末利用状況（アクティブアプリ、作業時間帯、入力傾向など）を収集・推定し、
  - Task の自動更新候補
  - Note への追記候補
  - リマインド提案
  を行う。
- 「ユーザーの状態把握」は **提案中心** とし、破壊的操作は明示承認を必須にする。

### 1.2 役割B: ローカル実行エージェント
- ローカルファイル操作（整理・命名・移動・検索・要約）を担う。
- ローカルアプリ操作（ブラウザ/IDE/ドキュメント編集など）を自動化し、Web上のAI指示を実環境へ橋渡しする。
- 「Web App → Native App → ローカル環境操作」の統一フローを提供する。

### 1.3 役割C: 開発実行基盤
- ローカルでの開発実行（ビルド、テスト、ログ収集）を支援する。
- エージェントからの依頼をジョブとして受け、実行結果をWeb Appに返す。

---

## 2. 詳細機能要件

### 2.1 状態把握・常駐アシスタント機能

#### 必須機能
1. **Activity Capture**: アクティブウィンドウ/アプリ、利用時間、アイドル時間の収集。
2. **Context Inference**: 収集データから「作業中/移動中/休憩中」などの状態推定。
3. **Task/Note Assist**: 状態推定に基づく Task 更新候補提示、作業ログから Note 追記案生成。
4. **Notification & Nudge**: 期限超過・長時間停滞・集中切れを通知。

#### 非機能要件
- バッテリー影響を最小化（低頻度ポーリング + イベント駆動優先）。
- 収集データはローカル暗号化し、送信データ最小化。

### 2.2 ローカルファイル操作機能

#### 必須機能
1. **File Indexing**: 指定フォルダ監視とメタデータ管理。
2. **Semantic Organizer**: AI分類（資料、議事録、コード等）と整理候補提示。
3. **Batch Operations**: リネーム、移動、重複検出、アーカイブの一括実行。
4. **Safe Execution**: 削除/上書きは Dry-run → 承認 → 実行。

#### 非機能要件
- Undo/Redo（操作履歴）を提供。
- 失敗時ロールバック方針を明示。

### 2.3 ローカルアプリ操作機能

#### 必須機能
1. **Action Runner**: アプリ起動、URLオープン、ショートカット送信、テキスト入力補助。
2. **Macro/Workflow**: 複数アクションのテンプレート化と再実行。
3. **Web-to-Local Bridge**: Web App から受けた指示をローカル実行し、結果返却。
4. **Policy Gate**: 操作対象アプリ・コマンドの許可リスト運用。

#### 非機能要件
- 実行ログ（誰の指示で何を実行したか）の監査性を担保。

### 2.4 開発支援機能

#### 必須機能
1. **Dev Task Executor**: build/test/lint/run をローカル実行。
2. **Artifact Collector**: ログ・テスト結果・出力物を収集してWebへ連携。
3. **Environment Profiles**: プロジェクト別実行環境（Node/Python/ENV）切替。

#### 非機能要件
- 危険コマンドは実行前確認または管理者ポリシー必須。

---

## 3. 実装方法（推奨アーキテクチャ）

### 3.1 全体構成
- **Cloud Side（既存）**
  - Web App（Next.js）
  - Backend API（FastAPI）
  - Agent Orchestration
- **Local Side（新規）**
  - Native App UI（設定/通知/承認）
  - Local Daemon（常駐プロセス）
  - OS Connector（ファイル・アプリ・通知API）
  - Local Store（SQLite + 暗号化）

推奨通信:
- Web App ⇄ Backend: 既存REST
- Native App ⇄ Backend: REST + WebSocket（イベント受信）
- Native UI ⇄ Local Daemon: localhost IPC

### 3.2 実装方式候補
- **案A: Tauri + Rust（デスクトップ先行）**
  - 長所: 軽量、OS連携しやすい、セキュリティ境界を作りやすい。
  - 短所: モバイル展開に追加設計が必要。
- **案B: Electron + Node.js**
  - 長所: Web技術資産を活かしやすく実装速度が高い。
  - 短所: メモリ消費が大きくなりやすい。
- **案C: React Native（モバイル先行）**
  - 長所: iOS/Android展開がしやすい。
  - 短所: PCローカル操作基盤としては別途戦略が必要。

> 現在の要件（ローカルファイル/アプリ操作、開発実行）を優先するなら、
> **Phase 1 は Tauri or Electron のデスクトップ常駐** を推奨。

### 3.3 コンポーネント設計（最小）
1. **Assistant Core**: 状態推定、提案生成、通知生成。
2. **Execution Engine**: ファイル操作・アプリ操作・開発コマンド実行。
3. **Permission Manager**: 権限同意、許可リスト、承認フロー。
4. **Sync Client**: Backend同期、ジョブ受信、結果送信。
5. **Audit Logger**: 実行履歴、エラー、監査証跡。

### 3.4 セキュリティ実装方針
- ローカル秘密情報はOSセキュアストレージで保存。
- 送受信はTLS + 短命トークン。
- 実行コマンドは allowlist + 引数バリデーション。
- 削除/上書き等は二段階承認。
- 監査ログは改ざん検知ハッシュを付与。

---

## 4. 既存 Web UI / 機能を前提にした統合要件

### 4.1 既存Webを継続利用する機能（Must）
Native導入後も、以下の既存Web機能は主系として継続利用する。

1. **Project Chat（非同期実行 + ポーリング）**
   - `POST /api/agents/project/{id}/chat` で実行依頼し、`task_id` を受け取り、
     `GET /api/agents/tasks/{task_id}` で状態監視する既存方式を維持。
2. **Thinking Process / Activity 可視化**
   - `sub_messages` を活用した思考過程表示を維持。
3. **Tasks（統合タスクUI）**
   - 既存の Task 一覧/編集/作成/インポート導線を保持。
4. **Dashboard（LBS）**
   - `/api/lbs/dashboard` 等で取得する負荷可視化は引き続きWeb中心。
5. **Notes**
   - Global Notes と Project Notes の既存導線をそのまま利用。

### 4.2 Native が追加提供する機能境界
- Webで完結する「計画・対話・可視化」を壊さず、Nativeは **実行力拡張** に集中する。
- 具体的には以下をNative責務とする。
  - ユーザー状態のローカル把握
  - ファイル/アプリのローカル実行
  - Web経由指示のローカル実行代行
  - 開発ジョブのローカル実行

### 4.3 UI連携要件（Web ⇄ Native）
1. **Chat連携**
   - Webチャットのツール実行結果として「Native Job」を扱えること。
2. **Approval連携**
   - 破壊的ローカル操作は、WebまたはNativeの承認UIで必ず可視化・承認。
3. **ステータス連携**
   - Nativeジョブ状態（queued/running/succeeded/failed）をWebのActivityに統合表示。
4. **Note/Task反映**
   - Nativeが生成した提案は最終的に既存Task/Notes API経由で反映し、データ正本を一元化。

### 4.4 既存画面との対応マトリクス（最小）
- **Projects Chat画面**: 指示起点（自然言語）
- **Activity Sidebar**: Native含む実行履歴の可視化
- **Tasks画面**: Native提案の承認結果を編集・確定
- **Notes画面 / Project Notes**: 自動追記候補の確認・編集
- **Dashboard画面**: Native由来の更新がLBSに反映された結果を確認

---

## 5. 段階導入プラン（既存Web前提）

### Phase 0: 要件確定
- 役割分担、権限境界、禁止操作を定義。
- 「Webが正本、Nativeが実行レイヤー」の原則を仕様化。

### Phase 1: MVP（常駐 + 状態把握 + Task/Note補助）
- Activity Capture
- Task/Note提案
- 通知
- 既存Task/Notes APIとの連携

### Phase 2: ローカルファイル実行
- インデックス
- 整理候補
- 承認付き一括操作
- Activity反映

### Phase 3: ローカルアプリ操作 + Web-to-Local Bridge
- Action Runner
- Macro
- サーバーからのジョブ実行
- Webチャットからの起動

### Phase 4: 開発支援機能
- build/test/lint 実行
- 実行ログ連携
- 失敗時の再実行・通知

---

## 6. 仕様決定のための未決事項
1. 監視対象データの粒度（プライバシー境界）
2. どこまで自動実行を許可するか（承認ポリシー）
3. 対応OS優先度（Windows/macOS/Linux）
4. 失敗時の責務分界（Native失敗 vs Backend失敗）
5. 監査要件（個人利用レベル / 企業利用レベル）

---

## 7. 結論

Native App は「Webの代替UI」ではなく、**既存Web（チャット・タスク・ノート・ダッシュボード）を活かしたローカル実行能力の拡張層**として設計するのが最適である。

特に本構想では、
- 状態把握による Task/Note 補助
- ローカルファイル/アプリ操作の実行代行
- Webからローカル環境を遠隔的に操作するブリッジ
- ローカル開発実行支援

の4本柱を、既存Web導線と整合した形で段階実装する。


---

## 8. 実装ディレクトリ配置提案（重要）

現行構成（`core/backend` と `core/frontend`）に整合させるなら、Native実装は **`core/native` を新設** するのが最も自然である。

### 8.1 推奨理由
- `core` 配下に「実行主体（backend/frontend/native）」を並べられ、責務分離が明確。
- 既存の Web 前提構成を壊さず、段階導入しやすい。
- CI/CD・依存管理・環境変数を Native 専用に分離できる。

### 8.2 推奨ディレクトリ案（最小）
```text
VisionArk/
├── core/
│   ├── backend/
│   ├── frontend/
│   └── native/
│       ├── desktop/            # Native UI（Tauri/Electron）
│       ├── daemon/             # 常駐プロセス（状態把握・ローカル実行）
│       ├── bridge/             # Web/Backend 連携クライアント（REST/WebSocket）
│       ├── integrations/       # OS別実装（win/mac/linux）
│       ├── shared/             # 共通型・ジョブ定義・ポリシー
│       └── scripts/            # 開発/ビルド/パッケージ補助
├── assets/
├── docs/
└── infra/
```

### 8.3 置かないほうがよい場所
- `core/frontend` 直下: Web依存が強くなり、Nativeの責務分離が崩れる。
- `core/backend` 直下: ローカル実行コンポーネントとサーバー実装が混在する。
- ルート直下 `native/`（初期段階）: 既存 `core` 構造との対称性が崩れ、運用ルールが分散しやすい。

### 8.4 初期実装の切り出し順
1. `core/native/shared`（ジョブ定義・型・ポリシー）
2. `core/native/bridge`（Backend接続）
3. `core/native/daemon`（常駐実行）
4. `core/native/desktop`（UI）

これにより、まず「Web→Nativeジョブ実行」の最短経路を作り、その後にUIやOS連携を拡張できる。
