# External Calendar Integration (Google / Outlook)

## 1. 概要 (Overview)
VisionArk (LBS) と外部カレンダーサービス（Google Calendar / Microsoft Outlook）を双方向同期させる機能。
「他人との予定（外部）」と「個人の作業タスク（内部）」を一元管理し、認知負荷（LBS）に基づいた現実的なスケジューリングを実現する。

## 2. コア・コンセプト (Core Concepts)

### A. 二層構造 (Two-Layer Architecture)
*   **External Layer (Social/Hard Constraints)**
    *   **対象**: 会議、移動、来客、プライベートな用事。
    *   **扱い**: **Read-Only (Master)**。VisionArkはこれらを「動かせない岩（Fixed Blocks）」として扱い、その隙間にタスクを配置する。
*   **Internal Layer (Personal/Flexible Work)**
    *   **対象**: 執筆、コーディング、調査などのソロワーク。
    *   **扱い**: **Read/Write (Manageable)**。VisionArkが負荷状況に応じて自由に配置・移動・ロックを行う。

### B. ロック機構 (Locking Mechanism)
外部カレンダーには「変更不可」の標準機能がないため、以下の方法でロック状態を管理する。
*   **System Side**: APIの `Extended Properties` (隠しメタデータ) に `lbs_locked: true` を保持。
*   **User Side**: タイトル先頭に `[🔒]` を付与、またはイベント色を「赤」に変更して視覚的に警告。

## 3. ユースケース (Use Cases)

### Case 1: 会議過多アラート (Overload Prevention)
*   **Scenario**: Googleカレンダーに会議が4件入っており、隙間時間が合計2時間しかない。
*   **Action**:
    1.  VisionArkはカレンダーの会議を「認知負荷: 高」のブロックとして認識。
    2.  残りの可用時間と疲労度を計算。
    3.  「本日は高負荷タスク（設計書作成）を行う余裕がありません」と警告し、自動的に翌日へリスケジュール案を提示。

### Case 2: ディープワークの防衛 (Focus Defense)
*   **Scenario**: 締め切り前の集中作業時間を確保したい。
*   **Action**:
    1.  VisionArk上でタスクをロック（LBS Lock）。
    2.  Googleカレンダーに「🔒 集中作業 (Do Not Disturb)」として同期。
    3.  他人がカレンダーを見た際「予定あり」となり、会議の割り込みを防ぐ。

### Case 3: 外出先での即時確認 (Mobile Access)
*   **Scenario**: 移動中にふと「次のタスクなんだっけ？」と思う。
*   **Action**:
    1.  スマホのGoogleカレンダーウィジェットを見るだけで、VisionArkが配置した「次の作業」を確認可能。
    2.  VisionArkを開く必要がない。

## 4. 機能仕様 (Functional Specifications)

### 4.1. 同期ロジック (Sync Logic)

| 方向 | トリガー | 処理内容 | 競合解決 |
| :--- | :--- | :--- | :--- |
| **Import**<br>(Cal → VA) | 定期ポーリング<br>(5分毎) | ・外部予定を「タスク(active=False)」としてDBに取り込み。<br>・LBS負荷計算の「既定負荷」として加算。 | **Calendar優先**。<br>外部で予定が変更されたら、VisionArk側も追従して移動。 |
| **Export**<br>(VA → Cal) | スケジュール計算完了時 | ・LBSで確定したタスクをカレンダーへ書き出し。<br>・メタデータ(LBS_ID)を付与。 | **VisionArk優先**。<br>VisionArkで再計算されたら、カレンダー上の配置も上書き移動。 |

### 4.2. メタデータ仕様 (Metadata)

Google/Outlookのイベントプロパティに以下を埋め込む。

```json
{
  "extendedProperties": {
    "private": {
      "visionark_id": "task-uuid-12345",
      "visionark_type": "task",  // task | block
      "visionark_locked": "true",
      "visionark_load": "3.5"
    }
  }
}
```

### 4.3. 負荷推定 (Load Estimation) - Import時

外部カレンダーのイベントを取り込む際、キーワードマッチで負荷を簡易推定する。

| キーワード例 | 推定負荷 (Load) | カテゴリ |
| :--- | :--- | :--- |
| 1on1, 面談, 報告会 | 3.0 (中) | Communication |
| 移動, ランチ, 休憩 | 0.5 (低) | Break / Buffer |
| 経営会議, トラブル対応 | 5.0 (高) | High Stress |
| (その他デフォルト) | 1.0/時間 | General |

## 5. UI/UX 要件

*   **OAuth認証画面**:
    *   Google/Microsoft アカウントでのログインと権限委譲（Scope: `calendar.events`）。
*   **同期設定**:
    *   対象カレンダーの選択（「仕事用」のみ同期、「プライベート」は除外など）。
    *   書き出し時のプレフィックス設定（例: `[VA] ...`）。
*   **強制同期ボタン**:
    *   即座に同期を実行する手動トリガー。

