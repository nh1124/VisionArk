# Native App ユースケース別 機能設計レポート

## 1. 対象ユースケース
1. メール自動化（Outlook）
2. コーディング自動化
3. 買い物自動化

---

## 2. 機能要件（ユースケース別）

## 2.1 メール自動化（Outlook）

### 2.1.1 シナリオ
1. Outlook にメール到着
2. 重要メールのみ要約通知
3. 返信必要なら下書き自動生成
4. メールからタスク抽出して登録

### 2.1.2 必須機能
- 受信フック（Webhook or polling）
- 重要度分類（rules + LLM）
- 返信要否判定
- Outlook Draft作成
- Task抽出・`/api/lbs/tasks` 登録

### 2.1.3 既存との接続
- 通知はWeb/Native双方に表示
- タスクは既存Tasks画面で編集
- 要約/処理履歴はActivityに統合

### 2.1.4 変更点
- Backendに `email_jobs`, `email_rules` の管理API追加
- Integration credential の暗号化保管追加

---

## 2.2 コーディング自動化

### 2.2.1 シナリオ
1. ユーザーが開発依頼
2. Native Agent がローカル環境で実装・コンパイル・検証
3. 完了通知 + 成果物提示

### 2.2.2 必須機能
- Repo checkout / branch運用
- コード編集実行
- build/test/lint 実行
- 結果要約（成功/失敗/次アクション）
- Artifact添付（ログ/バイナリ/差分）

### 2.2.3 既存との接続
- チャット起点を維持
- 結果は既存メッセージ/Artifact表示を利用
- タスク連動（長期ジョブはTask化）

### 2.2.4 変更点
- Native execution profile（言語別ランナー）追加
- Backend job result schema 拡張（build metadata）

---

## 2.3 買い物自動化

### 2.3.1 シナリオ
1. 買い物依頼
2. エージェントが商品探索
3. カート投入・購入確認まで進行
4. 最終確認後購入、または事前承認なら自動購入

### 2.3.2 必須機能
- 商品検索（複数サイト）
- 候補ランキング（価格/配送/評価）
- カート投入自動化
- 決済前承認（必須デフォルト）
- 事前承認ルール（上限金額/店舗/カテゴリ）

### 2.3.3 既存との接続
- 承認はWeb Approval Centerで実施
- 購買履歴はNotes/Taskに記録可能
- Activityで監査可能

### 2.3.4 変更点
- 高リスク操作カテゴリ（payment_submit）定義
- 2段階承認 + 再認証トークン導入

---

## 3. 横断データモデル（追加案）

### 3.1 NativeJob
- `id`, `type(email/coding/shopping)`, `status`, `requested_by`, `approved_by`, `risk_level`, `payload`, `result`, `started_at`, `finished_at`

### 3.2 ApprovalRequest
- `id`, `job_id`, `action_type`, `policy_mode`, `expires_at`, `decision`

### 3.3 IntegrationConnection
- `provider`, `account_ref`, `scopes`, `secret_ref`, `health_status`

### 3.4 AutomationRule
- `trigger`, `condition`, `action`, `approval_policy`, `limit`

---

## 4. API拡張（最小）

- `POST /api/native/jobs`
- `GET /api/native/jobs/{id}`
- `POST /api/native/jobs/{id}/approve`
- `POST /api/native/jobs/{id}/reject`
- `GET /api/native/jobs?status=`
- `POST /api/integrations/outlook/connect`
- `POST /api/integrations/outlook/rules`

---

## 5. セキュリティ要件

- 資格情報はOS Vault + Backend側暗号化参照
- 高リスク操作（送信・決済・削除）は承認必須
- 購入自動実行は「事前承認 + 金額上限 + 対象限定」が揃ったときのみ
- 監査ログは不可逆ハッシュ連鎖で保全

---

## 6. KPI

- メール: 通知遅延、下書き作成成功率、タスク抽出精度
- コーディング: ビルド成功率、修正反復回数、完了時間
- 買い物: 候補提示精度、承認待ち時間、誤購入ゼロ

