1. はじめに (Introduction)
1.1 システム名称と目的 (System Name and Purpose)

システム名称
AI TaskManagement OS

背景 (Background)
開発者（ユーザー）は、自身の掲げる「LifeVision」の実現に向け、研究・開発・自己研鑽など性質の異なる複数のプロジェクトを並列して遂行している。
これら複数の文脈（コンテキスト）を脳内だけでスイッチングし、各々の進捗状態（State）を保持し続けることは、認知資源に対し甚大な負荷（Gravity）として作用し、本来発揮すべき知的生産性を阻害する要因となっている。

目的 (Purpose)
本システムは、プロジェクト管理における「記憶」「状態維持」「コンテキスト切り替え」のコストを外部化・自動化することで、ユーザーの認知負荷を無効化することを目的とする。
単なるToDoリストではなく、「思考の外部OS（Exocortex）」 として機能し、ユーザーが常に「今、ここでの実行」に100%のリソースを割ける状態を担保する。
また、学業修了後も拡張を続け、将来的に仕事や事業、個人的な探究活動を横断的かつ統合的に管理するための基盤システムとしての役割を担う。

1.2 開発哲学 (Development Philosophy)
本システムは、以下の3つの哲学に基づいて設計・実装される。
1. Explicit Control (明示的制御)
AIは黒魔術的な自動判断を行わない。情報の共有、タスクの完了、フェーズの移行は、常にユーザーまたはSpoke（実行エージェント）からの**明示的なコマンド（Push型プロトコル）**によってのみトリガーされる。「勝手にやる」便利さよりも、「意図通りに動く」信頼性を優先する。

2. Decentralized Execution (自律分散実行)
中央集権的な巨大な脳（Single Huge Context）を作らない。各プロジェクト（Spoke）は、それぞれ独立したファイルシステム、参照資料、Personaを持つ「閉じた宇宙」として動作する。Hub（中央）はメタ情報のみを管理し、細部の文脈には干渉しない。

3. State over Memory (記憶より状態)
「AIの記憶（Context Window）」を過信しない。重要な決定事項、LBS（負荷スコア）、タスクステータスは、揮発性のチャットログではなく、永続的な**構造化データ（SQL/Filesystem）**として管理する。AIはその状態を読み書きするインターフェース（IO）に過ぎない。

1.3 想定ユーザーとユースケース (Target User & Use Cases)
想定ユーザー
	• 属性: コンピュータサイエンスおよび光工学をバックグラウンドに持つエンジニア/研究者（2025年9月 大学院修了想定）。
	• 特性: 複数の専門領域を横断し、並列処理能力が高いが、管理コストの増大に課題を持つ。GUIよりもCLIやScriptingによる制御・カスタマイズを好む。
主要ユースケース (Key Use Cases)
	1. Research & Development (R&D):
		○ 専門分野（光工学・情報科学）における論文調査、技術検証、実装、執筆活動の進捗管理。
		○ Spokeにて関連論文（PDF）をRAG参照しながらの思考実験とログ保存。
	2. Project & Business Management:
		○ 将来的な事業や業務プロジェクトにおけるWBS（Work Breakdown Structure）管理とLBSによる負荷分散。
		○ Hubによる複数プロジェクト間のリソース競合の解決と優先順位付け。
	3. Life Strategy & Culture:
		○ 茶道などの文化的活動や趣味、生活事務（Life Admin）のスケジュール管理。
		○ LifeVisionに基づく長期的なスキル習得（リスキリング）計画の策定と実行。
		
		

2. システムアーキテクチャ (System Architecture)
2.1 全体構成図 (Hub-Spoke Model)
本システムは、ユーザーの認知負荷を最小化するため、情報の「参照（Reference）」「統括（Orchestration）」「実行（Execution）」を明確に分離した3層構造を採用する。トポロジーとしては、中央のHubが全ての状態管理を担い、Spokeが放射状に展開する「スター型ネットワーク」を形成する。これにより、各プロジェクト間の依存関係をHubで一元管理し、Spoke間の複雑な通信（メッシュ型通信）によるコンテキスト汚染を回避する。
graph TD
    %% レイヤー定義: 静的な参照情報
    subgraph Layer_Global [Layer 1: Global Reference (Read-only)]
        direction TB
        Vision[LifeVision / NTTvision]
        Rules[Global Rules / Prompts]
        Assets[Shared Assets]
    end
%% レイヤー定義: 動的な状態管理と判断
    subgraph Layer_Hub [Layer 2: The HUB (Orchestration)]
        direction TB
        HubAgent[🤖 HUB Agent (PM Role)]
        HubDB[(LBS Master DB)]
        Inbox[📥 Inbox Buffer (Async Queue)]
        Log_Hub[Hub Interaction Logs]
    end
%% レイヤー定義: 個別の実行環境
    subgraph Layer_Spoke [Layer 3: The SPOKE (Execution)]
        direction TB
        SpokeA[💎 Spoke: Research (R&D)]
        SpokeB[💎 Spoke: ProjectManagement]
        SpokeC[💎 Spoke: Finance / Life]
        LocalRefs[Local References (PDFs/Code)]
    end
%% 外部サービス連携
    subgraph External [External Services]
        MSToDo[Microsoft ToDo (Task Sync)]
        Calendar[Outlook / Google Calendar]
    end
%% データフローの定義
    %% 1. 参照フロー (Read-only)
    Vision -.->|Reference| HubAgent
    Vision -.->|Reference| SpokeA
    Vision -.->|Reference| SpokeB
    Vision -.->|Reference| SpokeC
    Rules -.->|System Prompt| HubAgent
    Rules -.->|System Prompt| SpokeA
%% 2. 状態管理フロー (State Management)
    HubAgent <-->|CRUD Operations| HubDB
    HubDB <-->|Bi-directional Sync| MSToDo
    HubDB <-->|Schedule Blocking| Calendar
%% 3. Pushプロトコル (Information Flow)
    SpokeA -- Push (Meta Info) --> Inbox
    SpokeB -- Push (Meta Info) --> Inbox
    SpokeC -- Push (Meta Info) --> Inbox
%% 4. 指示とローカル参照
    Inbox -- Fetch (/check_inbox) --> HubAgent
    HubAgent -- Instruction / Resource Allocation --> SpokeA
    LocalRefs -.-> SpokeA
2.2 レイヤー定義 (Layer Definitions)
各レイヤーは「責任の単一性（Single Responsibility Principle）」に基づき設計されており、上位レイヤーは下位レイヤーの詳細に関知せず、下位レイヤーは上位レイヤーの決定に従う。
Layer 1: Global Reference (Global Assets)
	• 役割: システム全体の「憲法」および「羅針盤」。AIが判断に迷った際の最終的な拠り所となる「静的な真実（Ground Truth）」を提供する。
	• 構成要素:
		○ LifeVision.pdf, NTTvision.pdf: ユーザーの長期的目標や価値観を定義したドキュメント。
		○ Global_System_Prompt.md: 全エージェントに共通する振る舞い（トーン＆マナー、禁止事項、出力形式）の定義ファイル。
		○ Shared_Glossary.json: プロジェクト横断で使用される専門用語や略語の定義集。
	• 特性: 完全な読み取り専用 (Read-only)。
		○ HubおよびすべてのSpokeは、起動時（コンテキスト生成時）にこのレイヤーをシステムプロンプトの一部として読み込む。
		○ AI自身がこのレイヤーを変更することは許可されない。変更にはユーザーによる明示的なファイル更新（Gitコミットやファイル上書き）が必要であり、これによりAIによる「目標の勝手な書き換え」や「ルールの自己都合解釈」を防ぐ。
Layer 2: The HUB (Orchestration Layer)
	• 役割: リソース（時間・認知・労力）の最適配分と、プロジェクト間の競合調停を行う「管制塔」。
	• 責任:
		○ LBS (Load Balancing System) 管理: 全タスクの負荷スコア（Load Score）を監視・集計する。特定の日に負荷が集中した場合、優先順位の低いタスクを別日へ移動させるなどの調整案を提示し、システム全体のオーバーフローを防ぐ。
		○ Inbox処理 (Information Traffic Control): Spokeから非同期に送信されてくる報告（Inbox Buffer）を処理する。ノイズを除去し、重要な更新のみをコンテキストに取り込み、LBSデータベースへ反映させる。
		○ Spoke管理 (Lifecycle Management): 新規プロジェクト発生時のSpoke生成（ディレクトリ作成、初期設定）や、プロジェクト完了時のSpokeアーカイブ（ログ保存、コンテキスト破棄）を行う。
	• 非干渉の原則 (Non-Interference):
		○ Hubは、Spoke内部で行われている「具体的な作業内容」（例：Pythonコードのデバッグ、論文のパラグラフ推敲、個別のメール文面作成）には一切干渉しない。
		○ Hubが扱うのは「メタ情報」（進捗率、障害の有無、完了予定日、次のマイルストーン）のみであり、これによりHubのコンテキスト消費を最小限に抑え、長期記憶の維持を可能にする。
Layer 3: The SPOKE (Execution Layer)
	• 役割: 具体的タスクの実行と記録を行う「現場」。
	• 構成要素:
		○ Custom Persona: プロジェクトの性質に応じた特化型プロンプト。
			§ 例（Research）: 「論理的整合性を最重視し、批判的思考を持つ研究パートナー」
			§ 例（Life Admin）: 「事務手続きを効率的に処理する、簡潔な秘書」
		○ Local Refs: そのプロジェクト固有の参考文献。Hubには共有されない膨大なPDF（論文）、データセット、コードベースなどが含まれる。RAG（Retrieval-Augmented Generation）の検索対象となる。
		○ Artifacts: 生成された成果物（ドラフト、コード、図表）。
	• 特性: 独立性 (Isolation)。
		○ 各Spokeはコンテナのように独立しており、他のSpokeの存在や内部状態を直接知ることはできない。
		○ 必要な連携（例：Researchの成果をFinance予算に反映する）は、必ずHubを経由（Spoke A → Hub → Spoke B）して行われる。これにより、情報の混線とハルシネーションの伝播を防ぐ。
2.3 データの流れと制御フロー (Data Flow & Control Logic)
A. Push Protocol (Spoke to Hub)
AIによるブラックボックス的な自動共有や、全ログの無差別な転送を排除し、信頼性の高い「情報の蒸留」と「伝達」を実現するプロトコル。
	1. Trigger (発火):
		○ Explicit: ユーザーがSpoke内でコマンド（例: /share, /complete, /report）を実行する。
		○ Implicit: Spokeエージェントが「タスクの完了」「重大な障害の発生」「フェーズの移行」を検知し、ユーザーに「Hubへ報告しますか？」と提案し承認を得る、あるいは事前に許可された範囲で自動生成する。
	2. Generation (構造化生成):
		○ Spokeエージェントは、チャット画面上で人間が読むための自然言語テキスト（要約や挨拶）とは別に、システムが解釈可能なメタ情報ブロック (<meta-action>) を生成・出力する。
		○ このブロックには、更新すべきデータ種別、重要度、具体的な値が含まれる。
<!-- Example: Research Spokeからの報告 -->
<meta-action type="share_update">
  <target>Hub</target>
  <timestamp>2025-11-27T10:00:00</timestamp>
  <summary>論文Xの査読完了。追加実験（実験ID: Exp-04）が必要と判明。</summary>
  <!-- LBSデータベースへの直接的な更新指示 -->
  <lbs_update>
    <task id="T-101" status="review_needed" load_score="4.5" />
    <task id="T-new" action="create" name="追加実験 Exp-04" due_date="2025-12-05" load_score="3.0" />
  </lbs_update>
  <!-- Hubへの相談事項 -->
  <request>追加実験のため、来週の修論執筆タスクのリソース調整を希望。</request>
</meta-action>
	3. Hook (捕捉と転送):
		○ フロントエンドアプリケーションは、チャットストリームから正規表現等でこのXMLブロックを検出し、UI上では「共有カード」として整形表示（または非表示）する。
		○ 抽出されたデータは、即座に Inbox Buffer (JSONファイルやRedisキューなど) へ転送・保存される。
B. Inbox Buffer Pattern (Asynchronous Processing)
Hubのコンテキスト汚染（Context Pollution）を防ぎ、ユーザーが任意のタイミングで管理業務を行えるようにするための非同期処理パターン。
	1. Pooling (蓄積):
		○ Spokeから送信された情報は、Hubのチャット履歴に直接書き込まれるのではなく、一時的な Inbox_Data.json にキューとしてスタックされる。
		○ これにより、Spoke側で頻繁な更新があっても、Hub側のチャットが通知で埋め尽くされることを防ぐ。
	2. Fetching (取得と確認):
		○ ユーザーがHubで /check_inbox コマンドを実行、または「Inbox確認」ボタンを押下したタイミングでのみ、システムは蓄積されたデータをフェッチする。
		○ Pre-processing: システムはデータをHubエージェントに渡す前に、重複の排除やフォーマットの正規化を行うことができる。また、UI上でユーザーが「この報告は無視する」「これは重要」と選別してから取り込むことも可能とする（Human-in-the-loop）。
	3. Processing (統合と判断):
		○ Hubエージェントは取り込まれた情報をコンテキストに展開し、LBSデータベース（SQL）へのUPDATE文を発行したり、全体のスケジュールへの影響を評価する。
		○ 「追加実験が必要」という報告に対し、Hubは「では来週のLife Adminタスクを削減してリソースを確保する」といった戦略的判断（Trade-off Decision）を行い、ユーザーに提案する。
C. External Sync (LBS to Outside)
AIの揮発的なメモリではなく、永続化されたLBSデータベース（State）を「正（Master）」とし、外部ツールへ同期を行うことで、実生活との整合性を保つ。
	1. State Change (状態更新):
		○ Hubエージェントの指示、またはSpokeからのPush情報に基づき、バックエンドのLBSデータベース（PostgreSQL/SQLite）のレコードが更新される。
	2. Sync Agent (同期プロセス):
		○ チャットボットとは独立して動作するバックグラウンドプロセス（Sync Agent）が、DBの変更ログ（WAL）や更新フラグを定期的に監視する。
	3. API Call (外部反映):
		○ Microsoft ToDo: タスクの新規作成、完了ステータスの同期、期日の変更をMicrosoft Graph API経由で行う。双方向同期をサポートし、スマホのToDoアプリでの完了操作もLBSへフィードバックされる。
		○ Calendar: 作業負荷の高いタスクについては、Google Calendar APIを通じて「Focus Time」として予定ブロックを確保し、物理的な時間のダブルブッキングを防ぐ。


3. データ・ディレクトリ構造 (Data & Directory Structure)
3.1 ルートディレクトリ構成 (Root Directory Structure)
本システムは、情報の「参照スコープ（Scope）」と「データの永続性（Persistence）」に基づき、ディレクトリ構造を物理的に厳格に分離する設計を採用する。 これにより、AIエージェントが不必要な情報にアクセスして混乱する（Context Pollution）のを防ぎつつ、システムの堅牢性を担保する。また、Gitによるバージョン管理とローカルバックアップを容易にするため、生成されるデータと静的な設定ファイルを明確に区分する。
AI TaskManagement OS/
├── global_assets/          # [Layer 1] 全エージェント共有・読み取り専用領域
│   │   # システム全体の憲法にあたるドキュメント群。
│   │   # これらは原則としてGit管理下などで静的に保持され、AIによる自動書き換えは禁止される。
│   │   # 変更が必要な場合は、ユーザーが明示的にファイルを更新し、システム再起動を行う。
│   ├── LifeVision.pdf      # 長期戦略ドキュメント（人生の北極星、価値観の定義）
│   ├── NTTvision.pdf       # 中期戦略ドキュメント（3-5年スパンの具体的ロードマップ）
│   ├── system_prompt_global.md # 全エージェントに適用される共通プロンプト（口調、禁止事項、出力形式の統一）
│   └── glossary.json       # プロジェクト横断的な共通用語集・略語定義（専門用語の揺らぎ防止）
│
├── hub_data/               # [Layer 2] Hub管理領域（Orchestration State）
│   │   # システムの状態（State）を保持する心臓部。
│   │   # ここにあるデータが失われると、タスクの進捗状況や負荷バランスが不明になるため、
│   │   # 定期的なバックアップが必須となる領域である。
│   ├── lbs_master.db       # [Core DB] SQLite/PostgreSQL
│   │   # タスク定義、LBS計算結果、例外設定を含むリレーショナルデータベース実体。
│   │   # アプリケーションはこのファイルをSingle Source of Truthとして扱う。
│   ├── inbox/              # [Buffer] Spokeからの受信データプール
│   │   # SpokeからHubへの非同期通信を実現するためのバッファ領域。
│   │   ├── pending.jsonl   # 未処理のメタ情報キュー（追記型ログ）。Hubが読み込むまでここに蓄積される。
│   │   └── archive/        # 処理済みデータのログ（監査・デバッグ用）。過去の通信内容をトレース可能にする。
│   └── logs/               # Hubチャットの履歴ログ（コンテキストローテーション用）
│
├── spokes/                 # [Layer 3] プロジェクト別実行領域（Execution Environment）
│   │   # 各プロジェクトが互いに干渉しないよう、独立したサンドボックスとして機能する。
│   │   # ディレクトリ名がそのまま `context` タグとして機能する。
│   ├── research_photonics/ # 例: 光工学研究プロジェクト
│   │   ├── system_prompt.md# このSpoke専用のPersona定義（研究者としての振る舞い設定）
│   │   ├── refs/           # 参照資料ディレクトリ
│   │   │   # 論文PDFや実験データなど。ここにあるファイルのみがVector Store化され、RAGの対象となる。
│   │   │   # 他のプロジェクト（例: 家計管理）からは参照不可とすることで、ハルシネーションを防ぐ。
│   │   ├── artifacts/      # 生成物ディレクトリ
│   │   │   # AIが生成したドラフト、コード、図表などはここに保存される。
│   │   │   # ユーザーによる成果物の取り出し（Export）もここから行う。
│   │   └── chat.log        # このSpoke内での会話履歴
│   │
│   ├── life_admin/         # 例: 生活事務・雑務処理
│   │   └── ...
│   └── ...
│
├── app/                    # アプリケーションコード (Frontend/Backend Logic)
│   # UIコンポーネント、DBマイグレーションスクリプト、APIハンドラを含む。
│   # Python (FastAPI/Streamlit) または TypeScript (Next.js) コードが配置される。
└── .env                    # 環境変数
    # API Keys (OpenAI/Gemini), DB Connection Strings, Secret Keys等を管理。
    # セキュリティリスクを避けるため、Git管理対象外とする。
3.2 データベース設計 (Database Design)
LBS (Load Balancing System) の状態を永続化し、複雑なスケジュールルールを高速に検索・表示するためのリレーショナルデータベース設計。 書き込み（Command）と読み取り（Query）の責任を分離する設計思想（CQRSに近いアプローチ）を取り入れ、複雑な繰り返し計算を事前に行う構造とする。これにより、ダッシュボード表示時のレイテンシを最小化し、ストレスのない操作性を実現する。
Entity Relationship Diagram (ERD)
erDiagram
    SYSTEM_CONFIG {
        string key PK "ALPHA, BETA, CAP, SWITCH_COST"
        string value "数値またはJSON設定値"
        string description "設定の意味と影響範囲"
        datetime updated_at
    }
TASKS ||--o{ TASK_EXCEPTIONS : has
    TASKS ||--o{ LBS_DAILY_CACHE : expands_to
TASKS {
        string task_id PK "T-UUID (システムの主キー)"
        string task_name "タスク名称"
        string context "Spoke Name (プロジェクトタグ)"
        float base_load_score "0.0 - 10.0 (基本負荷)"
        boolean active "有効/無効フラグ"
        
        %% ルール定義
        string rule_type "ONCE / WEEKLY / EVERY_N / MONTHLY..."
        date due_date "単発タスクの締切日"
        
        %% 繰り返し設定詳細
        boolean mon "月曜実施フラグ"
        boolean tue "火曜実施フラグ"
        boolean wed "..."
        boolean thu "..."
        boolean fri "..."
        boolean sat "..."
        boolean sun "..."
        
        int interval_days "N日おきのN"
        date anchor_date "繰り返しの起点日"
        int month_day "毎月d日"
        int nth_in_month "第n週 (1-5, -1=最終)"
        int weekday_mon1 "曜日指定 (1=Mon...7=Sun)"
        
        date start_date "適用開始日"
        date end_date "適用終了日"
        string notes "備考・依存関係"
        string external_sync_id "Microsoft ToDo ID"
        datetime created_at
        datetime updated_at
    }
TASK_EXCEPTIONS {
        int id PK
        string task_id FK "対象タスク"
        date target_date "例外適用日"
        string exception_type "SKIP / OVERRIDE_LOAD / FORCE_DO"
        float override_load_value "変更後の負荷値"
        string notes "例外理由（祝日、体調不良など）"
        datetime created_at
    }
LBS_DAILY_CACHE {
        int id PK
        date target_date "カレンダーの日付"
        string task_id FK
        float calculated_load "例外・係数反映後の最終負荷スコア"
        string rule_type_snapshot "展開時点での適用ルール"
        string status "planned / completed / skipped"
        boolean is_overflow "CAP超過フラグ"
        datetime generated_at
    }
INBOX_QUEUE {
        int id PK
        string source_spoke "送信元Spoke"
        string message_type "share / complete / alert"
        json payload "構造化されたメタ情報 (<meta-action>)"
        boolean is_processed "処理済みフラグ"
        datetime received_at
        datetime processed_at
        string error_log "処理失敗時のエラーメッセージ"
    }
Table Definitions & Logic Details
1. tasks (Master Rules Table)
タスクおよび複雑な繰り返しルールの「定義（Definition）」を管理するマスタテーブル。 LBSエンジンの入力ソースとなる。タスクの削除は論理削除（active=FALSE）を推奨し、過去のログとの整合性を保つ。
	• rule_type 詳細仕様:
		○ ONCE: 単発タスク。due_dateのみを参照する。完了後は自動的にアーカイブ対象となる。
		○ WEEKLY: 毎週指定曜日。mon...sunフラグがTRUEの曜日に展開される。講義や定例会議などに使用。
		○ EVERY_N_DAYS: N日おき。anchor_date から interval_days 加算ごとに展開。リハビリや特定のメンテナンス作業などに使用。
		○ MONTHLY_DAY: 毎月指定日（例：毎月25日）。month_dayを使用。支払日などに適する。
		○ MONTHLY_NTH_WEEKDAY: 毎月第n曜日（例：第3月曜日）。nth_in_month と weekday_mon1 を組み合わせて計算。祝日による変動の影響を受けやすいタスクに使用。
	• load_score (Base Load):
		○ そのタスクを遂行するために必要な標準的な認知負荷・時間的コスト（0.0〜10.0）。
		○ 0.5刻みなどで設定し、Spoke側での実行ログに基づき、Hubが補正提案を行うこともある（例: 「このタスクは毎回時間がかかっているため、スコアを3.0から4.0へ引き上げるべきです」）。
2. task_exceptions (Exception Rules)
定例タスク（Routine）に対する「特異点」を管理するテーブル。 「毎週月曜の会議」が「祝日で休み」になる場合などに、ルール自体を変更（タスク定義の削除・再作成）することなく、このテーブルにレコードを追加することで特定日のみ挙動を変えることができる。これにより、ルールの汚染を防ぐ。
	• exception_type:
		○ SKIP: その日のタスク展開をキャンセルする。負荷は0になる。休暇や祝日対応に使用。
		○ OVERRIDE_LOAD: その日だけ負荷値を変更する（例：期末の会議だけ議題が多く3.0→5.0へ増量）。
		○ FORCE_DO: 定例日ではないが、臨時に実施する場合に追加（臨時会議など）。
3. lbs_daily_cache (Expanded Calendar / Materialized View)
tasks のルールと task_exceptions を基に展開された、実際の日次タスクリスト（Read Model）。 アプリのダッシュボード表示やヒートマップ描画は、計算コストの高い tasks ルールを毎回解析するのではなく、このキャッシュテーブルを参照して高速に行う。
	• 展開ロジック:
		○ バックグラウンドジョブ（Daily Batch）が、向こう3ヶ月〜1年分の日付に対してタスクを展開し、レコードを生成・更新する。
		○ ルール変更時（tasksテーブルの更新時）は、影響を受ける期間のキャッシュのみを再計算して更新する。
		○ calculated_load = (tasks.load_score or exception.override) * system_config.ALPHA (もし期限切迫なら)
	• 役割:
		○ これが「LBS（Load Balancing System）」の実体であり、このテーブルのSUM(load)が CAP を超えないよう管理することがHubの主目的となる。
		○ 過去のデータは「実績」として残り、将来のデータは「予測」として機能する。
4. system_config (Global Constants & Tuner)
LBS全体の挙動や負荷計算式（Algorithm）を制御する係数設定。 ユーザーの体調やフェーズ（繁忙期・閑散期）に合わせて調整可能にすることで、システムに「柔軟性」を持たせる。
	• ALPHA (Urgency Multiplier): 締め切り直前の負荷増加係数。
		○ 例: 1.2 → 締め切り前日は負荷が1.2倍として計算され、他のタスクを入れる余地を減らす（焦燥感の数値化）。
		○ これにより、締め切り直前に予定を詰め込みすぎる「計画の誤謬」を防ぐ。
	• BETA (Interruption Penalty): 件数ペナルティの指数。
		○ 多くのタスクを抱えること自体が引き起こすストレスを非線形にモデル化する。
	• CAP (Daily Capacity): 1日あたりの許容最大負荷スコア。
		○ 例: 8.0。これを超えるとヒートマップが赤くなり、Hubがリスケジュールを強く推奨する。
		○ 体調不良時はこの値を一時的に下げる（例: 5.0）ことで、システム全体を「省エネモード」に移行できる。
	• SWITCH_COST (Context Switch Overhead): コンテキストスイッチによる負荷加算値。
		○ 1日に異なる context (Spoke) のタスクが混在する場合、種類数に応じて負荷スコアに加算されるペナルティ値（例: +0.5 / type）。
		○ 「マルチタスクは効率が悪い」という原則をシステム的に強制する仕組み。
3.3 LBS ロジック仕様 (LBS Logic Specification)
提供された機能要件に基づき、データベース更新およびアプリケーション表示時の計算アルゴリズムを定義する。このロジックは、単なる数値計算ではなく、人間の「認知コスト」をシミュレートすることを目的としている。
F1/F2: 登録・例外ロジック (Registration & Exception Handling)
	• Master Registration:
		○ ユーザーまたはAIは、TASKS テーブルにタスクを登録する際、必ず rule_type を指定する。
		○ 定期タスクの場合、開始日 (start_date) と終了日 (end_date) を設定することで、学期ごとの時間割やプロジェクト期間に合わせた運用が可能。
	• Exception Handling:
		○ TASK_EXCEPTIONS への登録は、LBS_DAILY_CACHE 生成時に最優先で評価される。
		○ 同一日に SKIP と OVERRIDE が競合した場合、SKIP が優先される（「やらない」ことが決定しているなら負荷量は無関係なため）。
F3: 展開ロジック (Expansion Algorithm)
日次バッチまたはリアルタイム計算にて、TASKS × Calendar Date を展開し、LBS_DAILY_CACHE を生成するプロセス詳細。
	1. 期間判定 (Period Validation):
		○ 対象日 Target Date が、タスクの有効期間内 (start_date <= Target Date <= end_date) であるか判定する。
		○ active = TRUE であることも必須条件とする。
	2. ルール適合判定 (Rule Matching):
		○ ONCE: Target Date == due_date
		○ WEEKLY: Target Date の曜日カラム (mon...sun) がTRUEであるか。
		○ EVERY_N_DAYS: (Target Date - anchor_date) の日数が interval_days で割り切れるか（余りが0か）。
		○ MONTHLY_DAY: Target Date の日が month_day と一致するか。存在しない日付（例: 2月30日）の場合はスキップ、または月末補正を行うオプションを実装する。
		○ MONTHLY_NTH_WEEKDAY: カレンダー計算ライブラリを用い、その月の第 nth_in_month 回目の weekday_mon1 曜日を算出して一致判定を行う。
	3. 例外適用 (Exception Override):
		○ TASK_EXCEPTIONS テーブルを検索し、当該タスク・当該日付のレコードが存在するか確認する。
		○ 存在する場合、その exception_type に応じてキャッシュ生成を制御する（レコードを作成しない、または負荷値を上書きして作成する）。
F4: 負荷補正ロジック (Load Adjustment Calculation)
日ごとの総負荷（Adjusted Total Load）算出において、タスク数増大によるパニックと、コンテキストスイッチによる集中力低下を数式化する。
	• 数式: 
$$Adjusted = Base + ALPHA \times N^{BETA} + SWITCH\_COST \times \max(U-1, 0)$$
	• 変数定義と設計意図:
		○ $Base$: 純粋な作業負荷の合計。各タスクの load_score (例外反映後) を単純加算したもの。
		○ $N$ (Count): 当日のタスク件数。件数が多いだけで、心理的な圧迫感（Cognitive Overhead）が生じることを $N^{BETA}$ で表現する。
		○ $U$ (Unique Contexts): 当日のユニークな context (Spoke) の数。
		○ $ALPHA$ (Coefficient): 基礎係数 (例: 0.1)。タスク数ペナルティの影響度を調整する。
		○ $BETA$ (Exponent): 指数係数 (例: 1.2)。タスク数が増えるにつれてペナルティが加速度的に増加するように設定する。これにより「小さなタスクを大量に詰め込む」行為を抑制する。
		○ $SWITCH\_COST$: 切り替えコスト (例: 0.5)。
			§ $U=1$ （1つのプロジェクトに集中）の場合、$\max(0, 0) = 0$ となりペナルティなし。
			§ $U=3$ （研究、授業、事務を並行）の場合、$\max(2, 0) \times 0.5 = 1.0$ の負荷が加算される。
		○ $CAP$: 1日の限界許容量。$Adjusted$ がこれを超えると、システムは新規タスクの追加を拒否、または既存タスクの延期を強く推奨する。
F5/F6/F7: 可視化要件 (Visualization & Dashboard)
View Filters
	• 期間: Day (詳細リスト) / Week (バーチャート) / Month (カレンダーヒートマップ)
	• 軸:
		○ Context Stacking: コンテキストごとに色分けして積み上げ表示し、どのプロジェクトがリソースを圧迫しているか可視化する。
		○ Rule Type: 定型業務（Routine）と突発業務（Once）の比率を表示する。
Warning Indicators (条件付き書式)
計算された $Adjusted$ 値に基づき、UI上で直感的な警告色を表示し、ユーザーに行動変容を促す。
	• 🟢 SAFE (Level 1): load < 6.0
		○ 余裕がある状態。先行着手や休息（Slack Time）に充てることを推奨。
	• 🟡 WARNING (Level 2): 6.0 <= load < 8.0
		○ 適正負荷の上限付近。新規タスクの追加には慎重な判断が必要。
	• 🔴 DANGER (Level 3): 8.0 <= load <= 10.0 (または CAP到達)
		○ 過負荷状態。残業や睡眠時間の削減が必要になるレベル。タスクの SKIP や延期を検討すべき。
	• 🟣 CRITICAL (Level 4): load > 10.0 (CAP超過)
		○ 破綻状態。物理的に遂行不可能である可能性が高い。強制的なリスケジュールが必要。
Dashboard KPIs
	• 週平均負荷: 週間の $Adjusted$ 平均値。「特定の日に無理をしていないか」だけでなく「慢性的に負荷が高いか」を監視する。
	• 過負荷連続日数: $Adjusted > 8.0$ が連続している日数。これが3日を超えた場合、「Burnout Risk Alert」を発報する。
	• 回復日率: 週のうち $Adjusted < 4.0$ (回復日) が確保されている割合。週に1日以上（約14%）確保することを推奨目標とする。
3.4 ファイル権限と参照スコープ (Access Control & Scope)
システム的な「権限（Permission）」だけでなく、AIエージェントにとっての「可視範囲（Visibility）」と「責任境界（Responsibility Boundary）」を定義する。これはセキュリティだけでなく、AIの性能維持（Attentionの最適化）のために不可欠である。
Layer / Agent	global_assets/	hub_data/	spokes/{Own}/	spokes/{Other}/
Hub Agent	Read (System Prompt)	Read / Write (DB & Inbox)	Manage (Create/Archive)	Manage (Create/Archive)
Spoke Agent	Read (System Prompt)	Push Only (Write to Inbox)	Read / Write (Refs & Artifacts)	No Access (Invisible)
User (App)	Read / Write	Read / Write	Read / Write	Read / Write
制御ポリシーの詳細
	1. Isolation (独立性の担保 - Sandbox Model)
		○ ポリシー: Spokeエージェントは、ファイルシステムレベルで他のSpokeディレクトリにアクセスできないようにアプリケーション側で制限（ChrootまたはPath制限）する。
		○ 目的:
			§ ハルシネーション防止: あるプロジェクトの文脈（例：光工学研究の専門用語）が、別のプロジェクト（例：家計管理）に混入し、AIが文脈を取り違えるのを物理的に防ぐ。
			§ 情報セキュリティ: 将来的に外部の共同研究者とSpokeの一部を共有する場合でも、他のSpoke（個人的な日記や金融情報）へのアクセスを遮断できる。
	2. Unidirectional Flow (一方通行の書き込み - Push Protocol)
		○ ポリシー: SpokeからHubへのデータ移動は、必ず inbox ディレクトリまたは inbox_queue テーブルを介した書き込み（Push）のみとする。Spokeが直接 lbs_master.db を読み書きすることは禁止する。
		○ 目的:
			§ データの整合性: データベースのスキーマや状態管理ロジックを知っているのはHubのみとし、Spokeによる不正な更新を防ぐ。
			§ 割り込み防止: Hubが集中して処理を行っている最中に、Spokeからのデータ更新によってコンテキストが乱されるのを防ぐ。Hubは自分のタイミングでInboxを処理できる。
	3. Human Override (ユーザー特権)
		○ ポリシー: ユーザー（あなた）は全てのファイルおよびデータベースに対してRoot権限を持つ。
		○ 目的:
			§ 最終決定権の保持: AIはあくまで支援ツールであり、最終的なスケジュールの決定権はユーザーにある。AIの生成した誤ったデータやログを直接修正・削除することが許可される。
			§ 緊急対応: システム障害時やAIのAPIダウン時でも、SQLを直接叩いて状態を確認・変更できるバックドアを確保する。


4. 機能要件：オーケストレーション (Core Logic: Orchestration)
本システムは、中央集権的な巨大な脳（Single Context）ではなく、独立したエージェント間の疎結合な連携によって動作する。この連携を支えるのが「Push型プロトコル」と「Inboxバッファ」である。
4.1 Push型情報共有プロトコル (<meta-action> 仕様)
SpokeエージェントからHubへの通信は、自然言語の会話に埋め込まれた構造化データブロック <meta-action> によって行われる。アプリケーションはチャットストリームを監視し、このブロックをフックして処理する。
4.1.1 プロトコル設計思想
	• Explicit Push (明示的送信): エージェントは「何でも共有」するのではなく、報告すべきマイルストーン（完了、課題発生、フェーズ移行）でのみこのタグを生成する。
	• Hidden Metadata: このXMLブロックは、チャットUI上では「共有カード」としてレンダリングされるか、または非表示となり、人間の可読性を妨げない。
4.1.2 XMLスキーマ定義
<meta-action type="ACTION_TYPE">
    <!-- 必須: 送信先 -->
    <target>Hub</target>
    
    <!-- 必須: 発生日時 (ISO 8601) -->
    <timestamp>2025-11-27T14:30:00Z</timestamp>
    
    <!-- 必須: 人間用の要約 (Hubでの表示用) -->
    <summary>短潔な要約テキスト</summary>
    
    <!-- 任意: LBSデータベースへのCRUD指示 -->
    <lbs_update>
        <!-- タスクステータスの更新 -->
        <task id="T-UUID" status="done" />
        <!-- 新規タスクの発生 -->
        <task action="create" name="Task Name" due_date="YYYY-MM-DD" load_score="3.0" />
    </lbs_update>
    
    <!-- 任意: Hubへの定性的な相談・リクエスト -->
    <request>
        来週のリソース配分についての相談内容...
    </request>
    
    <!-- 任意: 生成物へのリンク -->
    <artifacts>
        <file path="spokes/research/artifacts/draft_v1.md" />
    </artifacts>
</meta-action>
4.1.3 Action Types
	• share_update: 定期的な進捗報告。
	• task_complete: タスク完了通知。LBSのステータスを更新する。
	• issue_alert: 障害発生や遅延見込みの報告。警告色で表示される。
	• request_review: 成果物のレビュー依頼。Artifactへのパスを含む。
4.2 Inboxバッファ機構 (非同期処理フロー)
Hubのコンテキスト（Attention）を守るため、Pushされた情報は即座にHubに注入されず、「Inbox」というバッファ領域を経由する。
4.2.1 処理フロー (State Transition)
stateDiagram-v2
    [*] --> Generated: Spokeが<meta-action>生成
    Generated --> Queued: Appが検知しJSONLに保存
    
    state "Inbox Buffer" as Buffer {
        Queued --> Pending: 未処理リストに表示
    }
    
    Pending --> Fetched: Userが/check_inbox実行
    Fetched --> Processed: Hubエージェントが内容を解釈
    Processed --> Archived: ログ保存・Queueから削除
    
    Processed --> LBS_Updated: DB更新
	1. Queueing (蓄積):
		○ 検知された <meta-action> はパースされ、hub_data/inbox/pending.jsonl に追記される。
		○ Hubチャット画面のサイドバー等に「未読件数: 3」のようなインジケータが表示される。
	2. Fetching (取り込み):
		○ ユーザーが任意のタイミングで「Inbox確認」アクションを行う。
		○ システムは pending.jsonl の内容をまとめてHubのプロンプトに注入する。
		○ Prompt例: 「以下の報告がSpokeから届いています。内容を確認し、LBSを更新または戦略的助言を行ってください。[DATA...]」
	3. Archiving (完了):
		○ Hubが処理を完了したら、データは hub_data/inbox/archive/YYYY-MM.jsonl に移動され、Inboxは空になる。
4.3 カスタムスタイル (System Prompt) 管理
各エージェント（Hub/Spoke）の人格と役割定義は、静的なMarkdownファイルとして管理し、UIから編集可能にする。
4.3.1 ファイル構造
	• Global: global_assets/system_prompt_global.md
		○ 全エージェント共通の基底プロンプト（「あなたはAntigravity OSの一部である...」等）。
	• Local: spokes/{context_id}/system_prompt.md
		○ そのSpoke固有の差分プロンプト。
4.3.2 プロンプト合成ロジック (Injection Strategy)
エージェント起動時（コンテキスト生成時）、システムは以下の順序でプロンプトを結合してLLMに送信する。
	1. Global Prompt: システム全体のルール、出力フォーマット制限。
	2. Layer 1 Assets: LifeVision.pdf, NTTvision.pdf のテキスト内容（または要約）。
	3. Local Prompt: 「あなたは光工学の研究者である。論理的かつ批判的に...」といったPersona定義。
	4. Current Context: 直近のチャットログ、またはLBSの現状スナップショット。
4.3.3 管理機能
	• UI Editor: アプリ設定画面で各Spokeの system_prompt.md を直接編集できるエディタを提供する。
	• Version Control: プロンプトの変更履歴はGitで管理され、いつでも「前の人格」に戻せるようにする。

5. 機能要件：コンテキスト管理 (Context Management)
LLMのコンテキストウィンドウは有限であり、長期プロジェクトでは必ず「あふれ」が発生する。本システムは、ログのローテーションと要約（Compression）、および外部参照（RAG）を組み合わせることで、擬似的に無限の記憶を実現する。
5.1 ログローテーションと自動要約 (/archive)
コンテキストがトークン上限に近づいた際、またはプロジェクトのフェーズが完了した際に、記憶を「圧縮」してコンテキストをリフレッシュする機能。
5.1.1 処理フロー
	1. Trigger (発火):
		○ Auto: トークン使用率が規定値（例: 80%）を超えた場合。
		○ Manual: ユーザーがコマンド /archive を実行した場合（「フェーズ1完了」のタイミング等）。
	2. Summarization (要約生成):
		○ システムは現在のチャット履歴全体を読み込み、以下の構造を持つ「コンテキスト要約 (archived_summary.md)」を生成する。
			§ Decisions: 決定事項リスト。
			§ Pending Issues: 未解決の課題。
			§ Key Facts: 重要な事実関係（「A案はBの理由で却下された」等）。
	3. Rotation (ローテーション実行):
		○ 現在のチャットログ (chat.log) を logs/chat_YYYYMMDD_HHMM.log にリネームして退避する。
		○ チャットウィンドウをクリアする。
	4. Injection (再注入):
		○ 新たなチャットセッションの冒頭に、生成した archived_summary.md をシステムプロンプトの一部として注入する。
		○ これにより、AIは詳細な会話履歴は忘れても、「これまでの経緯と現在の状態」を保持したまま再スタートできる。
5.2 参照情報のRAG化 (Refsフォルダの扱い)
spokes/{context}/refs/ ディレクトリに配置された資料（論文PDF、仕様書、議事録）を、AIが能動的に参照できる知識ベースとして構築する。
5.2.1 ベクトル化プロセス
	• Watcher: アプリケーションは refs/ フォルダを監視する。
	• Embedding: 新規ファイル追加や更新を検知すると、テキストをチャンク分割し、OpenAI/GeminiのEmbedding APIを用いてベクトル化する。
	• Storage: ベクトルデータは各Spoke専用のローカルVector Store（ChromaDB, FAISS等）に保存される。他Spokeとは隔離される。
5.2.2 検索・参照ロジック
	• On-Demand Retrieval: ユーザーが「昨日の論文の実験条件について教えて」と問うた際、AIはそのクエリに関連するチャンクをVector Storeから検索し、回答生成に利用する。
	• Citation: 回答には必ず引用元ファイル名とページ数を明記させる（「Source: paper_A.pdf, p.12」）。これにより、ハルシネーションを確認可能にする。
5.3 生成物の管理 (Artifactsフォルダ)
チャット内での「使い捨ての回答」と、成果物としての「永続ファイル」を明確に区別する。
5.3.1 Artifactsの定義
	• spokes/{context}/artifacts/ に保存されるファイル群。
	• 例: 論文ドラフト (draft.md)、Pythonスクリプト (analysis.py)、要件定義書 (requirements.md)。
5.3.2 操作インターフェース
	• Create/Update: AIは <meta-action> タグを用いて、特定のファイル名と内容を指定し、Artifactsフォルダへの書き込みを行う。
<meta-action type="update_artifact">
    <path>artifacts/experiment_log.md</path>
    <content>...</content>
</meta-action>
	• User Access: ユーザーはこのフォルダをVS CodeやExplorerで直接開き、編集・閲覧できる。
	• Read-back: AIはArtifactsフォルダ内のファイルを常に最新の状態として認識・参照できる（RAGとは異なり、生テキストとして読み込む場合もある）。
5.3.3 バージョン管理推奨
	• artifacts/ フォルダはGit管理下置くことを強く推奨する。AIによる破壊的な変更があった場合でも、Gitの履歴から復元可能にするためである。システム側で自動コミットを行うオプションも検討する。


6. 機能要件：外部連携 (External Integration)
本システムは、独自のLBSデータベース（Master）を持ちつつ、ユーザーが日常的に使用するMicrosoft ToDoやOutlook Calendarを「表示・操作端末（Client）」として利用する。データの整合性を保つため、厳格な同期ロジックと方向性を定義する。 両サービスとも Microsoft Graph API を介して制御するため、認証基盤を統一できる利点がある。
6.1 LBS (SQL) との同期ロジック
6.1.1 基本原則 (Master-Slave Architecture)
	• Master: lbs_master.db (Local SQL)。すべてのタスクの定義、負荷スコア、ステータスの正本。
	• Client: Microsoft ToDo, Outlook Calendar。これらはあくまで「ビューワー」および「簡易入力IF」として扱う。
	• Conflict Resolution: 競合が発生した場合（例：ローカルでタスク名を変更し、同時にスマホで完了にした）、原則としてローカル（LBS）の状態を優先するが、完了フラグ（is_completed）に関しては外部入力を優先して取り込む。
6.1.2 同期フロー (Sync Cycle)
同期エージェント（Sync Agent）は、以下のサイクルで動作する。
sequenceDiagram
    participant Spoke as Spoke/User
    participant DB as LBS Master DB
    participant Agent as Sync Agent
    participant Ext as MS ToDo / Outlook
%% Push Flow
    Note over Spoke, Ext: 1. Outbound Sync (LBS -> External)
    Spoke->>DB: タスク作成 / 更新
    Agent->>DB: 変更検知 (Polling/Trigger)
    Agent->>Ext: Create / Update Task/Event (Graph API)
    Ext-->>Agent: Return External ID
    Agent->>DB: Save External ID
%% Pull Flow
    Note over Spoke, Ext: 2. Inbound Sync (External -> LBS)
    Ext->>Ext: スマホでタスク完了
    Agent->>Ext: Delta Query (差分取得)
    Ext-->>Agent: Completed Task List
    Agent->>DB: Update Status = DONE
    DB->>Spoke: (Optional) Notify Hub
6.2 Microsoft ToDo (Graph API) 双方向同期
Microsoft Graph APIを使用し、生活事務や雑務（Life Admin）のシームレスな管理を実現する。
6.2.1 データマッピング
LBS (tasks Table)	MS ToDo Property	備考
task_id (UUID)	openExtension	カスタムデータとして拡張プロパティに埋め込む
external_sync_id	id	ToDo側のIDをローカルに保存
task_name	title	
notes	body/content	
due_date	dueDateTime	
active = FALSE	status = completed	
context	listId (Folder)	プロジェクトごとにリストを分けるか、タグで管理
6.2.2 実装詳細
	1. Outbound (App -> ToDo):
		○ Create: LBSでタスクが作成されると、対応するToDoリスト（例: "Antigravity"）にタスクを追加し、返却されたIDを保存する。
		○ Update: タスク名や期限が変更された場合、PATCHリクエストで反映する。負荷スコア（LBS固有値）は本文（Body）の末尾に [LBS: 3.0] のように記載するか、無視する。
	2. Inbound (ToDo -> App):
		○ Completion: スマホでチェック完了すると、次回のSyncでLBS側のタスクも completed に更新される。
		○ Inbox Capture: ToDoの「Tasks（既定のリスト）」に追加されたタスクは、「未分類の新規タスク」としてLBSのInboxに取り込み、Hubに割り振りを依頼する。これにより、移動中に思いついたタスクをスマホから放り込める。
	3. Deletion Handling:
		○ ToDo側でタスクが削除された場合、LBS側では物理削除せず、active=FALSE (アーカイブ) にする。
		○ LBS側で削除された場合、ToDo側も削除（または完了扱い）にする。
6.3 Outlook Calendar 連携 (Time Blocking)
LBSの負荷スコアが高いタスクや、時間が固定されたタスク（講義、MTG）をカレンダー上のブロックとして確保する。これらも Microsoft Graph API (/me/events) を使用する。
	• Rule: load_score >= 5.0 または rule_type が時間固定のタスクのみ同期する。全てのTo-Doでカレンダーを埋め尽くさないため。
	• Time Allocation: LBS上の estimated_hours（もしあれば）に基づき、カレンダーの空きスロット（Free/Busy情報）を取得して自動配置案を作成する（「この論文読みは火曜の10:00-12:00でいかがですか？」とHubが提案）。



7. UI/UX設計 (User Interface)
本システムは、対話型AIの柔軟性（Chat）と、プロジェクト管理ツールの堅牢性（GUI）を融合させた、エンジニアのための 「Chat-Centric IDE (Integrated Development Environment)」 としてデザインされる。 VS CodeやIntelliJ IDEAが「コードを書くための統合環境」であるならば、Antigravity OSは「人生とプロジェクトを実装するための統合環境」である。ユーザーはコンテキストスイッチを最小限に抑えつつ、マウスとキーボードを行き来しながら高速に意思決定を行うことができる。
7.1 画面レイアウト (Navigation & Workspace)
画面全体は「常駐するナビゲーション」と「可変のワークスペース」に明確に分離される。これにより、ユーザーは「今どこにいるか」を見失うことなく、複数のタスク（Hubでの戦略策定と、Spokeでの論文執筆など）を並列して進めることが可能となる。
7.1.1 レイアウト構成図
+---+-----------------------------------------------------------------------+
| N | [Workspace Tab: 📊 LBS Dashboard x] [Tab: 💎 Research x] [ + ]       |
| a |                                                                       |
| v |  +---------------------------+  +----------------------------------+  |
|   |  | [Weekly Tasks Tree]       |  | [KPI Cards]                      |  |
| B |  | > 11/25 (Mon) Total: 8.5  |  | Today Score: 4.8 (Good)          |  |
| a |  |   v Finance               |  | Weekly Score: 7.2 (Warning)      |  |
| r |  |     - NISA残枠... : 2.5   |  | Recov. Rate: 14%                 |  |
|   |  |   v ProjectMgmt           |  |                                  |  |
|   |  |     - PMBOK読解... : 2.0  |  | [Load Trend Graph]               |  |
|   |  +---------------------------+  |  /^\   /\      [Context Pie]     |  |
|   |  | [Quick Action]            |  | /   \ /  \___    (( @ ))         |  |
|   |  | + Add Task...             |  |                                  |  |
|   |  +---------------------------+  +----------------------------------+  |
|   |                                                                       |
+---+-----------------------------------------------------------------------+
| S | [Status Bar] DB: Connected | Sync: 1 min ago | Inbox: 3 unread (Alert)|
+---+-----------------------------------------------------------------------+

7.1.2 サイドバー構成 (Navigation Menu)
常時表示される左端のメニューバー（幅50px-200px可変）。アイコンベースで直感的にモードを切り替える。
	1. 🏠 Home / Hub Chat:
		○ 統合司令塔（Hub）とのメインチャット画面。システム全体のログや、AIとの雑談・壁打ちもここで行う。
		○ アイコンバッジには「Hubからの緊急提案数」を表示。
	2. 📊 LBS Dashboard:
		○ LBS専用のアナリティクスビュー。Excelで管理していたような複雑な数値を可視化する。
		○ ホバー時に現在の Today Score をツールチップで表示し、クリックせずに概況を把握可能にする。
	3. 📥 Inbox (Notification Center):
		○ Spokeからの報告、外部（Microsoft ToDo）からの同期タスクが集まる場所。
		○ 未読件数を赤バッジで表示し、処理が必要なタスクの滞留を防ぐ。
	4. 💎 Projects (Spokes Explorer):
		○ 展開可能なツリー形式でプロジェクト一覧を表示。
		○ Research / Finance / Life Admin などの各Spokeへワンクリックで遷移。
		○ 各プロジェクトの稼働状況（Active/Archived）をアイコンの色で表現。
	5. ⚙️ Settings:
		○ APIキー設定、DB接続設定に加え、System Promptエディタへのショートカット。
7.1.3 ワークスペース (Tabbed Interface)
	• Multi-Tab: ブラウザやIDEのように、チャット画面やダッシュボードを「タブ」として複数開くことができる。
	• Split View: タブをドラッグして画面を左右（または上下）に分割可能。「左側で論文を読みながら（Spokeチャット）、右側でスケジュールを確認する（LBS Dashboard）」といった並行作業を支援する。
7.2 LBS Dashboard (Dedicated View)
ユーザーが共有したExcelダッシュボードの構成をWebアプリケーションとして再構築し、静的な「表」から動的な「コントロールパネル」へと進化させる。 単にデータを見るだけでなく、その場でドラッグ＆ドロップして未来を修正できることが重要である。
7.2.1 表示要素 (Visualization Widgets)
	• KPI Cards (Top Row): 瞬時の状況判断を促すシグナル。
		○ Today Score: 当日の負荷合計値。閾値（6.0, 8.0）を超えると背景色が緑→黄→赤→紫と変化し、危機感を視覚的に伝える。
		○ Today Eval: 負荷スコアに基づいた定性評価（Safe, Good, Warning, Danger, Overload）。
		○ Weekly Score: 週平均負荷。慢性的な過労を検知する。
		○ Over Days: 今週のキャパシティ（CAP）超過日数。これが「2日以上」ある場合、リスケジュールを推奨するアラートアイコンを表示。
	• Weekly Tasks Tree (Left Panel): 時間軸でのタスク構造。
		○ 日付 > コンテキスト > タスク の3階層ツリー表示。
		○ Load Visualization: 各タスクの右端に負荷スコアを表示し、その日の合計値がヘッダーに自動集計される。
		○ Context Color: プロジェクトごとに定義された色（例: Research=青, Finance=緑）でタスク名の左端を装飾し、視認性を高める。
	• Analytics Charts (Right Panel): 長期的トレンドの把握。
		○ Load Trend: 向こう1週間〜1ヶ月の負荷予測折れ線グラフ。山と谷を可視化し、「来週の木曜日は空いている」といった計画立案を助ける。
		○ Context Ratio: 直近1週間または選択期間におけるコンテキスト別負荷割合のドーナツグラフ。「今は研究にリソースを全振りできているか？」を確認する。
		○ Eval Trend: 日々の評価（Good/Danger等）をGitHub Contributions風のヒートマップで表示。生活リズムの乱れをパターンとして認識させる。
	• Daily Ranking:
		○ Day Top 5: その日の高負荷タスクランキング。ボトルネックとなっているタスクを一目で特定する。
7.2.2 操作機能 (Direct Manipulation)
	• Drag & Drop Rescheduling:
		○ ツリー内のタスクを掴んで別の日付へドロップすることで、即座に due_date や例外設定を変更する。
		○ ドロップした瞬間に再計算が走り、移動先の日付の合計スコアが更新される（Excelでは難しいリアルタイム性）。
	• Direct Edit (Inline):
		○ タスク名やスコアをダブルクリックしてその場で編集モードに入る。
		○ コンテキストメニュー（右クリック）から「明日に延期」「スコア+1」「詳細を編集」などのクイックアクションを実行可能。
7.3 Inbox UI (Notification Center)
コマンド操作ではなく、LINEやメールクライアントのような「リスト＆詳細」形式のUIを採用する。これは単なる通知確認ではなく、Hubへの情報の流入を制御する「関所（Gatekeeper）」として機能する。
7.3.1 画面構成
	• Message List (Left Column):
		○ Spokeからの報告（<meta-action>）や、Microsoft ToDoから同期された新規タスクが時系列で並ぶ。
		○ 各アイテムには「送信元アイコン（Spokeの種類）」、「要約テキスト（Subject）」、「受信日時」が表示される。
		○ 未読アイテムは太字またはハイライト表示され、処理漏れを防ぐ。
	• Detail View (Right Column): 選択したメッセージの全容と操作パネル。
		○ Header: 送信元エージェント名とタイムスタンプ。
		○ Body: 報告の全文（Markdownレンダリング対応）。「論文Xを読みました。その結果、Yという課題が見つかりました...」といったコンテキストを含む。
		○ Proposed Actions (Diff View): AIが提案するLBSへの変更内容を差分表示する。
			§ [UPDATE] Task T-101: Status DOING -> DONE
			§ [CREATE] Task T-New: "追加実験" (Due: 12/05, Load: 3.0)
7.3.2 アクションフロー (Triage Logic)
ユーザーは詳細ビュー下部のアクションボタン群（Floating Action Bar）で処理を決定する。
	1. ✅ Accept (承認・反映):
		○ 提案内容（LBS更新、新規タスク作成）をデータベースにコミットする。
		○ 処理後、アイテムは「Archive」タブへ移動し、Hubのチャットログに「〇〇を承認しました」とシステムメッセージが追記される。
	2. ✏️ Edit & Accept (修正承認):
		○ 提案内容を編集モードで開く。「タスク追加は認めるが、期日は12/5ではなく余裕を持って12/10にする」「負荷スコアは3.0じゃなくて5.0だ」といった人間の判断を加えてから反映する。
	3. ❌ Reject (却下):
		○ LBSへの反映を行わず、アイテムを削除（または却下済みフォルダへ移動）する。
		○ オプションで「却下理由」を入力し、送信元のSpokeへフィードバックを返すことができる（例: 「今は予算がないため却下」）。
	4. 💤 Snooze (保留):
		○ 「後で確認する」としてInboxに残す、または指定時間後に再通知する。
7.4 コマンドパレット (Auxiliary Control)
GUI操作を補完し、Power User（あなた）がホームポジションから手を離さずに操作完結できるよう、IDEライクなコマンドパレットを提供する。
7.4.1 操作仕様
	• Trigger: Cmd+K (Mac) / Ctrl+K (Win) または / キー。
	• Fuzzy Search: コマンド名の一部を入力するだけで候補が絞り込まれる（例: "dash" → > Go to Dashboard）。
7.4.2 主要コマンド一覧
コマンド	対象	機能詳細	引数例
> Go to Dashboard	UI	LBSダッシュボードタブを開く、またはアクティブにする	-
> Go to Hub	UI	Hubチャットへ移動	-
> Quick Add Task	LBS	画面遷移せずにタスクをLBSへ登録するダイアログを開く	> Quick Add
> Switch Project	UI	指定したSpokeのチャットへ瞬時に切り替える	> Switch Research
> Sync External	System	Microsoft ToDo / Calendar との同期を強制実行	-
> Archive Context	System	現在のチャットコンテキストを要約・圧縮してログローテーションを実行	-


8. 技術スタックと開発フェーズ (Tech Stack & Roadmap)
本システム Antigravity OS は、個人のタスク管理ツールを超えた「拡張された脳（Exocortex）」を目指すものである。 これを実現するためには、高度な行列演算を伴うLBS計算ロジック（Backend）、IDEのように複雑で応答性の高いUI（Frontend）、そして長期間の状態を保持しながら非同期に動作するAIエージェント群を、一つの堅牢なシステムとして統合する必要がある。 本章では、単なる流行ではなく、「開発効率（DX）」、「型安全性（Robustness）」、「拡張性（Scalability）」 の観点から厳選されたモダンスタックと、その実装計画を詳述する。
8.1 推奨技術構成 (Recommended Tech Stack)
A. Frontend: "The IDE Shell"
ユーザーが一日中滞在し、思考と作業を行うためのSPA（Single Page Application）。遅延のない操作感と、情報密度の高いダッシュボード描画能力が求められる。
	• Framework: Next.js 14+ (App Router)
		○ 選定理由:
			§ Server Components: LBSダッシュボードの初期描画に必要な重いデータフェッチをサーバー側で完結させ、クライアントへのJS転送量を削減することで、FCP (First Contentful Paint) を高速化する。
			§ Server Actions: APIのエンドポイントを明示的に書かずとも、フォーム送信やボタン操作から直接バックエンドロジック（DB更新など）を呼び出せるため、"Glue Code"（接着剤コード）を大幅に削減できる。
			§ Deployment: Vercel等のプラットフォームを利用することで、CI/CDパイプラインの構築コストをゼロにし、開発に集中できる環境を即座に用意できる。
	• Language: TypeScript
		○ 選定理由:
			§ Type Safety: LBSのデータ構造（Task, LBS_Cache）は多層的で複雑である。Backend（Python/Pydantic）と型定義を同期（OpenAPI Generator等を利用）させることで、APIレスポンスの型不整合によるランタイムエラーを根絶する。
			§ Developer Experience: エディタ上での強力な補完機能により、開発速度とリファクタリングの安全性を担保する。
	• UI Library: Tailwind CSS + shadcn/ui
		○ 選定理由:
			§ Consistency: shadcn/ui (Radix UIベース) を採用することで、アクセシビリティ（キーボード操作対応）が確保された高品質なコンポーネント（ダイアログ、コマンドパレット、トースト通知）を即座に利用できる。
			§ Dark Mode: エンジニアの長時間作業に必須のダークモード対応が容易であり、IDEライクな没入感のあるデザインシステムを構築しやすい。
			§ AI Compatibility: "v0.dev" や "Claude Artifacts" などの生成AIツールが標準的に出力する形式であり、AIにUIコードを書かせる際の精度が極めて高い。
	• State Management: Zustand or Jotai
		○ 選定理由:
			§ Simplicity: Reduxのようなボイラープレート（記述量）の多さを避け、最小限のコードでグローバルステート（チャットログ、未読バッジ数、LBSの現在値）を管理できる。
			§ Granular Updates: 必要なコンポーネントだけを再レンダリングさせる最適化が容易であり、高頻度で更新されるLBSヒートマップやチャットストリームのパフォーマンス低下を防ぐ。
B. Backend: "The Logic Core"
複雑なLBSアルゴリズムの実行と、自律的なAIエージェントのオーケストレーションを担うAPIサーバー。
	• Framework: FastAPI (Python)
		○ 選定理由:
			§ AsyncIO Native: 複数のAIモデル（OpenAPI, Gemini）へのAPIリクエストや、DBへのクエリを非同期（Non-blocking）で並列処理できるため、ユーザーを待たせないレスポンスを実現できる。
			§ Pydantic Integration: リクエスト/レスポンスのバリデーションを自動化し、データの整合性を入り口で保証する。
			§ Auto Documentation: Swagger UIが自動生成されるため、Frontend開発時のAPI仕様書作成の手間を省略できる。
	• AI Orchestration: LangGraph
		○ 選定理由:
			§ Stateful Agents: 従来のLangChain（DAG: 有向非巡回グラフ）では難しかった、**「循環（Loop）」や「条件分岐（Branching）」**を含むエージェントフロー（例: SpokeがHubに報告→Hubが却下→Spokeが再考→再報告）を、ステートマシンとして明確に定義できる。
			§ Persistence: エージェントの「思考の途中経過」をDBに保存し、サーバー再起動後も会話を継続できる機能（Checkpointing）が標準で備わっている。
	• LBS Engine: NumPy / Pandas
		○ 選定理由:
			§ Vectorized Operations: LBS_DAILY_CACHE の数ヶ月分の日付データ展開や、全タスクに対する負荷係数計算（$Base + \alpha \times N^\beta$）を、Pythonのループ処理ではなくベクトル演算として一括処理することで、計算時間をミリ秒オーダーに短縮する。
			§ Data Analysis: 将来的に蓄積されたログデータを分析し、自分の「生産性バイオリズム」を解析する際にも、そのままデータサイエンスの資産を活用できる。
C. Database & Infrastructure
	• Core DB: Supabase (PostgreSQL)
		○ 選定理由:
			§ All-in-One: リレーショナルデータベース（LBS管理）、ベクトルデータベース（pgvectorによるRAG）、認証基盤（Auth）、リアルタイム配信（Realtime）を単一のプラットフォームで完結できる。
			§ Row Level Security (RLS): 将来的にシステムを公開したり、友人と共有する場合でも、DBレベルで厳格なアクセス制御を設定できる。
			§ Local Development: supabase start コマンド一つでローカルに完全なバックエンド環境を再現できるため、インターネットなしでも開発が可能。
	• Vector Store: Supabase (pgvector)
		○ 選定理由:
			§ Hybrid Search: キーワード検索（SQL）と意味検索（Vector）を組み合わせたハイブリッド検索が容易であり、タスク名による検索と、文脈による資料検索を同じDBで行える運用メリットが大きい。

