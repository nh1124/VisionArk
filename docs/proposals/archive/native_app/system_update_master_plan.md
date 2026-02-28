# Native App 統合に向けたシステム設計更新レポート（マスタープラン）

## 1. 本レポートの目的

本レポートは、提示された3ユースケース（メール自動化 / コーディング実行 / 買い物実行）を、既存 VisionArk（Web中心アーキテクチャ）へ統合するための開発計画を定義する。

重要論点は以下の2点。
- 現行システムとのすり合わせ（既存を活かす部分 / 変更が必要な部分）
- UI設計（Web UIとNative UIの責務分担）

---

## 2. 開発に必要な情報項目（類推結果）

以下を「実装前に確定すべき項目」と定義する。

### 2.1 システム理念・責務分離
1. データ正本（SSOT）をどこに置くか
2. Native Appを「代替UI」ではなく「実行レイヤー」とする原則
3. 自動実行と承認実行の境界

### 2.2 機能要件
1. ユースケース別の機能分解
2. 既存機能（Chat/Tasks/Notes/Dashboard）との接続点
3. 失敗時の代替動作・再実行要件

### 2.3 非機能要件
1. セキュリティ（認証、秘密情報、決済操作の保護）
2. 監査性（誰の指示で何を実行したか）
3. 性能（通知遅延、ジョブ完了時間）
4. 可用性（ローカルAgent停止時の挙動）

### 2.4 アーキテクチャ設計
1. コンポーネント分割（Cloud/Local）
2. API/イベント設計
3. ジョブキュー・状態遷移モデル
4. 外部連携（Outlook、EC、ローカルIDE）

### 2.5 データモデル設計
1. Native Job
2. Approval Request
3. Integration Credential/Connection
4. Automation Rule

### 2.6 UI/UX設計
1. Web側の統合UI（チャット・承認・ジョブ監視）
2. Native側の常駐UI（状態/通知/承認）
3. ユースケース別の操作導線

### 2.7 運用・開発プロセス
1. ディレクトリ配置
2. 段階導入ロードマップ
3. テスト計画
4. ロールバック計画

---

## 3. 現行システムとのすり合わせ方針

## 3.1 そのまま活かす部分
- Webチャットを指示起点とする運用
- 非同期タスク実行 + ポーリングモデル
- Tasks/Notes/Dashboard の情報正本
- Activity/Thinking 表示による実行可視化

## 3.2 追加・変更が必要な部分
- **Backend**
  - Native実行ジョブを管理するAPI・状態管理を追加
  - 承認ポリシー（決済/送信/削除）を型として管理
  - 外部連携（Outlook/EC）の統合アダプタ追加
- **Frontend (Web)**
  - Job Center（実行状況一覧）
  - Approval Center（承認キュー）
  - Integration設定画面（資格情報・ポリシー）
- **Native**
  - Local Daemon（常駐）
  - 実行エンジン（OS操作・ブラウザ操作・IDE操作）
  - セキュア秘密情報管理

## 3.3 変更しない原則
- Tasks/Notesの最終保存先は既存Backend APIを維持
- UIの主操作導線はWebを中心に維持
- Nativeはローカル実行能力を提供する補助レイヤー

---

## 4. ユースケース統合概要（詳細は分割レポート参照）

### 4.1 メール自動化（Outlook）
- 受信イベント → 重要度判定 → 要約通知
- 返信要否判定 → 下書き作成（Outlook側）
- タスク抽出 → VisionArk Tasks登録

### 4.2 コーディング自動化
- 要件受領 → 実装計画 → ローカル環境で実装・ビルド・検証
- 成果報告 → Artifact/差分/実行結果を通知

### 4.3 買い物自動化
- 商品探索 → 候補提示 → カート投入
- 決済前承認（既定）または事前許可時のみ自動購入
- 決済操作は高リスクカテゴリとして二段階保護

---

## 5. 推奨ディレクトリ配置（確定案）

```text
VisionArk/
├── core/
│   ├── backend/
│   ├── frontend/
│   └── native/
│       ├── desktop/            # Native UI
│       ├── daemon/             # 常駐Agent
│       ├── bridge/             # Backend接続
│       ├── integrations/       # outlook/ec/ide/os別連携
│       ├── execution/          # ジョブ実行エンジン
│       ├── security/           # secret vault / policy gate
│       └── shared/             # 型・契約
```

---

## 6. 実装フェーズ

### Phase 0: 契約設計
- Job/Approval/Policy のAPI契約
- UIワイヤー定義

### Phase 1: Native基盤
- `core/native` 骨組み
- Daemon + Bridge + Job受信

### Phase 2: メールユースケース
- Outlook連携
- 要約通知/下書き/タスク抽出

### Phase 3: コーディングユースケース
- ローカル実行（build/test）
- 結果収集・通知

### Phase 4: 買い物ユースケース
- Web操作ワークフロー
- 決済承認ガード

### Phase 5: 運用最適化
- 監査ダッシュボード
- 自動化ルールUI

---

## 7. 分割レポート案内
- `native_app_usecase_functional_design.md`: ユースケース別機能要件/データ/API
- `native_app_ui_ux_design.md`: Web/Native UI 詳細設計

