# Native構成要素（bridge / daemon / desktop）役割調査レポート

## 1. 目的
本レポートは、VisionArk Native実装における `bridge` / `daemon` / `desktop` の役割分担を明確化し、今後の改修時に「どこを変更すべきか」を判断しやすくすることを目的とする。

---

## 2. 各コンポーネントの役割

## 2.1 desktop（`core/native/desktop`）
### 主な責務
- ユーザーが直接触る **ネイティブUI層**。
- 画面表示（Dashboard / Jobs / Approvals / Notes / Tasks / Projects / Agents / Settings）と、ログイン・操作導線を提供。
- Tauri機能（トレイ常駐、通知、グローバルショートカット、Quick Noteウィンドウ）を管理。
- OSセキュアストレージ（keyring）を通したトークン保存APIを提供。

### 実装上の位置づけ
- `src/lib.rs` がアプリ本体（tray, shortcut, window lifecycle）を制御。
- `src/commands.rs` が Tauri command（通知・トークン保管等）を提供。
- `src-ui/` がUI実装本体で、`lib/api.ts` 経由で backend API を叩く。

### この層でやるべきこと / やらないこと
- やるべき: UI表示、承認操作、設定入力、ユーザー起点の操作。
- やらないこと: ジョブ実行ループや高頻度ポーリングなどの常駐ワーカー本体。

---

## 2.2 daemon（`core/native/daemon`）
### 主な責務
- 端末側で常駐する **実行エンジン層**。
- Backend から Nativeジョブを取得して、Plan & Execute で step 実行。
- ローカル操作ツール（shell, file, app起動）を呼び出して結果を返却。
- 高リスク step では `needs_approval` 状態へ遷移し、承認待機後に再開。

### 実装上の位置づけ
- `main.rs` で 3つのループ（bridge_client / activity / job_runner）を起動。
- `job_runner.rs` がジョブポーリング、dispatch、step実行、結果反映を担当。
- `local_tools.rs` が実行可能ツールのディスパッチとOS実行を担当。
- `activity.rs` がアクティブウィンドウ取得（現状は最小実装）。

### この層でやるべきこと / やらないこと
- やるべき: 実行制御、再試行、状態遷移、結果収集。
- やらないこと: リッチUI、画面遷移ロジック、ユーザー向け表示整形。

---

## 2.3 bridge（`core/native/bridge`）
### 主な責務
- Native系から Backend を利用するための **接続抽象化層（通信SDK）**。
- REST API 呼び出し（jobs / integrations / rules）と WebSocket購読の共通化。
- shared型（`core/native/shared`）を利用し、コンポーネント間の契約を揃える。

### 実装上の位置づけ
- `api.ts`: jobs/integrations/rules のHTTPクライアント。
- `ws.ts`: WebSocket接続、再接続、イベント購読。
- `index.ts`: bridgeの公開エントリ。

### この層でやるべきこと / やらないこと
- やるべき: 通信処理、認証ヘッダ付与、イベント配信の標準化。
- やらないこと: UI状態管理、ローカルコマンド実行、業務判断ロジック。

---

## 3. 3層の連携フロー（現状）
1. ユーザーが `desktop` UI で操作する。
2. UIは backend API を呼び、Nativeジョブを作成・閲覧する。
3. `daemon` が queued job をポーリングして取得する。
4. `daemon` が dispatch plan を取得し、`local_tools` で順次実行。
5. 実行結果を backend の job.result / status に反映。
6. `desktop` 側の Jobs/Approvals画面が状態を表示し、必要時に承認する。

補足: `bridge` はこの流れで共通通信部品として使う想定だが、現状は `desktop` と `daemon` が直接HTTPを持つ箇所もあり、統一は途上。

---

## 4. 現状の課題（責務分離の観点）
1. **通信実装の二重化**
   - `desktop/src-ui/lib/api.ts` と `native/bridge/api.ts` が並立し、トークン管理やBASE_URL戦略が分裂。
2. **bridgeの活用不足**
   - bridgeが「共通SDK」として十分に採用されておらず、実質的に補助モジュール化している。
3. **daemonの安全境界不足**
   - 実行ツールのallowlist/path制限/dry-runなどが未整備で、実行層の責務（安全実行）に対して弱い。
4. **desktopの責務肥大リスク**
   - 認証・API呼び出し・表示・一部業務判断が混在しやすく、将来的な保守性低下の懸念。

---

## 5. 改修方針（役割を活かす設計）

### 5.1 desktop
- UI/UXと入力処理に集中させる。
- API呼び出しは可能な限り bridge 経由に寄せる。
- 承認・通知の表示に特化し、実行判断は backend/daemonへ委譲する。

### 5.2 daemon
- 実行ポリシーと監査の中心に据える。
- 「実行前検証 → 承認判定 → 実行 → 監査記録」のパイプラインを標準化する。
- polling中心から pushトリガー併用へ移行する。

### 5.3 bridge
- Nativeの公式通信層として一本化する。
- BASE_URL / token / retry / timeout / event schema を共通管理する。
- desktop/daemon双方が再利用できる最小SDKとして責務を固定化する。

---

## 6. 結論
- `desktop` は「体験と操作」、`daemon` は「ローカル実行」、`bridge` は「通信契約」の責務で整理できる。
- 現在は最低限の3層が存在するが、**通信の一本化（bridge中心化）と daemon の安全実行強化** が次の実装フェーズの重要課題。
- 今後の実装では、機能追加より先に責務境界を明確化すると、Native全体の拡張速度と品質を両立しやすい。

---

## 7. bridgeを置くかどうかの判断材料（メリット/デメリット/推奨）

### 7.1 bridgeを置くメリット
1. **通信契約の一元化**
   - `BASE_URL`、認証ヘッダ、リトライ、タイムアウト、エラーハンドリングを1箇所に集約できる。
2. **変更耐性の向上**
   - API仕様変更時に、`desktop` と `daemon` の両方を直接修正する必要が減る。
3. **型安全と一貫性の確保**
   - `core/native/shared` の型と組み合わせることで、ジョブ/承認/イベントのデータ不整合を減らせる。
4. **運用品質の標準化**
   - ログ、メトリクス、サーキットブレーカー等の横断機能を共通実装しやすい。

### 7.2 bridgeを置くデメリット
1. **レイヤー増加による学習コスト**
   - 開発者が `desktop -> bridge -> backend` の流れを理解する必要があり、初期の認知負荷が上がる。
2. **過剰抽象化のリスク**
   - 小規模段階で抽象化しすぎると、かえってデバッグ性と実装速度が落ちる可能性がある。
3. **責務の曖昧化リスク**
   - bridgeに業務ロジックを入れ始めると、`daemon`/`backend` との境界が崩れて保守性が下がる。

### 7.3 bridgeを置かない場合のメリット/デメリット
#### メリット
- 実装が単純で、初期開発は速い。
- 依存関係が減るため、最小PoCでは扱いやすい。

#### デメリット
- 認証/通信ロジックが重複しやすく、将来の仕様変更コストが増える。
- `desktop` と `daemon` で挙動差（リトライ条件やエラー処理）が出やすい。
- セキュリティ設定（ヘッダ・トークン・証明書検証）の統一漏れが起きやすい。

### 7.4 推奨
- **結論としては「薄いbridgeは残す」ことを推奨**。
- ただし「巨大な抽象層」は避け、以下の最小責務に限定する。
  - 認証付きHTTP/WebSocket接続
  - 共通リトライ/タイムアウト
  - 型付きDTOの変換
  - 共通エラー形式への正規化
- 逆に、以下は bridge に入れない。
  - 画面状態管理（desktop責務）
  - 実行判断・承認判定（daemon/backend責務）
  - ユースケース固有の業務ロジック

### 7.5 「無くてもいい」判断になる条件
- Nativeが長期的に単一クライアント（desktopのみ）で、daemonがbackend直結しない。
- API変更頻度が低く、認証/通信要件が単純。
- 横断要件（監査、再送制御、共通メトリクス）が小さい。

上記条件を満たす短期PoCなら bridge 省略は合理的だが、
現状の VisionArk Native は `desktop` と `daemon` が並立しており通信要件も増加傾向のため、
**最小bridgeを維持して統一を進める方が中期的なコストを下げやすい**。
