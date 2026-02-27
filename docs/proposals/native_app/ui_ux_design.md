# Native App 統合 UI/UX 設計レポート

## 1. UI設計原則

1. **Web中心**: 既存Webを主操作面として維持
2. **Native補助**: Nativeは通知・承認・ローカル実行の即応面
3. **同一タスクID追跡**: Web/Nativeで同じJobを追える
4. **高リスク操作の明確表示**: 決済・送信・削除は赤系バッジ

---

## 2. Web UI 追加設計

## 2.1 Job Center（新規ページ）
- 一覧: status, usecase, risk, requested_at
- 詳細: 実行ログ、成果物、失敗理由、再実行
- フィルタ: usecase（email/coding/shopping）

## 2.2 Approval Center（新規ページ）
- 承認待ち一覧
- 承認ダイアログに以下を表示
  - 何が実行されるか
  - 影響範囲（送信先、購入額など）
  - 期限

## 2.3 Integration Settings（拡張）
- Outlook連携状態
- EC連携状態
- 自動化ルール（ON/OFF、上限額、対象サイト）

## 2.4 既存画面への差し込み
- Project Chat: Native Job起動ボタン/進捗チップ
- Activity Sidebar: Native実行ログの統合表示
- Tasks: 抽出タスクの出典（email/native）表示
- Notes: 要約や購買ログの自動追記出典表示

---

## 3. Native UI 設計

## 3.1 Resident Panel（常駐ミニUI）
- 現在実行中ジョブ
- 直近通知
- 一時停止/再開

## 3.2 Approval Pop-up
- 高リスク操作時にOS通知 + ワンクリック遷移
- 詳細はWeb Approval Centerへ遷移可能

## 3.3 Local Execution Console
- コーディングジョブの build/test ログ確認
- エラー時にワンクリックで再実行

---

## 4. ユースケース別UIフロー

## 4.1 メール
1. Outlook受信
2. Native通知: 「重要メール要約 + 下書き作成済」
3. Webで下書き確認（必要なら編集）
4. 送信承認

## 4.2 コーディング
1. Webチャットで依頼
2. Job Centerで進捗確認
3. 完了通知 → 差分と検証結果確認
4. 必要なら再実行

## 4.3 買い物
1. Webチャットで依頼
2. 候補カード表示（価格/配送/評価）
3. カート投入後、購入承認ダイアログ
4. 承認後購入完了（または事前許可時は自動）

---

## 5. デザインコンポーネント（追加案）

- `RiskBadge`（low/medium/high/critical）
- `JobStatusChip`（queued/running/succeeded/failed/needs_approval）
- `ApprovalDialog`
- `ExecutionTimeline`
- `SourceAttributionTag`（email/native/manual）

---

## 6. アクセシビリティ / 運用

- 承認ダイアログはキーボードのみで操作可能
- 承認期限切れ前に再通知
- 重要通知はサウンド種別を設定可能

---

## 7. 実装優先順位

1. Web Job Center + Approval Center
2. Native通知 + 承認ポップアップ
3. Activity統合
4. ユースケース個別UI強化（メール→コーディング→買い物）

