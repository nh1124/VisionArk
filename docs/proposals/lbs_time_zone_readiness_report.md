# VisionArk: LBS Timezone対応 事前調査レポート

## 1. 背景
LBS側で以下2点のTimezone仕様が追加された。

- リクエストヘッダ `X-Timezone`（未指定時 `UTC`）
- タスク作成・更新時の `timezone` フィールド（IANA TZ）

本レポートは、**VisionArkの現状**を整理し、LBS仕様更新に合わせた**対応必要箇所**と**変更スコープ**を明確化する。

---

## 2. 現在のTimezone対応（As-Is）

### 2.1 ユーザー設定としてのTimezone保持は実装済み
- フロント設定画面で `timezone`（IANA）を選択可能。
- バックエンド `/api/settings/general` で `general_settings.timezone` を保存可能。
- デフォルト値は `UTC`。

> ただし、この設定値はLBS API呼び出し時ヘッダへは連携されていない。

### 2.2 LBSクライアント層で `X-Timezone` ヘッダ未対応
- `integrations/lbs/client.py` のヘッダ生成では `Content-Type` / `Accept` / `X-API-KEY` / `Authorization` などのみ付与。
- `X-Timezone` をセットする引数（例: `x_timezone`）が `LBSClient.__init__` に存在しない。

### 2.3 LBSタスク作成・更新で `timezone` ペイロード未対応
- VisionArkのTask DTO（`TaskCreate`, `TaskUpdate`）に `timezone` フィールドがない。
- フロントのタスク作成UIでも `timezone` を送信していない。
- エージェントツール（`create_task`）でも `timezone` を組み立てていない。

### 2.4 日付境界依存のAPIは多数利用中
`schedule/dashboard/heatmap/tasks/{id}/resolved` など、LBS新仕様で `X-Timezone` 影響が大きいエンドポイントをVisionArkは日常的に利用している。

---

## 3. 対応が必要な箇所（To-Be）

## 3.1 必須対応A: `X-Timezone` の全LBSリクエスト適用

### 対応方針
- `LBSClient` に `x_timezone` 引数を追加。
- `_get_headers()` で `X-Timezone` を常時付与。
- 値の優先順位を明確化：
  1. 明示指定（引数）
  2. ユーザー設定 `general_settings.timezone`
  3. 未取得時 `UTC`

### 主な対象
- `integrations/lbs/client.py`
- `integrations/lbs/api.py` の `get_lbs_client` 依存注入（ユーザー設定読込）
- `integrations/lbs/agent_tools.py` の `get_lbs_client` 呼び出し（必要なら引数拡張）

## 3.2 必須対応B: タスクPayloadの `timezone` 対応

### 対応方針
- Task作成/更新スキーマに `timezone` を追加。
- UI作成・編集から `timezone` を送れるようにする（最小構成として「ユーザー設定TZを自動設定」でも可）。
- エージェントツールで作成/更新する際も `timezone` を補完（明示指定 > user_settings > UTC）。

### 主な対象
- `integrations/lbs/api.py`（`TaskCreate`, `TaskUpdate`）
- `core/frontend/app/components/TaskCreateModal.tsx`
- `core/frontend/app/components/TaskEditPanel.tsx`
- `integrations/lbs/agent_tools.py`

## 3.3 必須対応C: IANAフォーマットの正規化/バリデーション

### 対応方針
- 受け入れるTZはIANA形式（例 `Asia/Tokyo`）に統一。
- 保存時/送信前に不正値を弾くか `UTC` フォールバック。

### 主な対象
- `core/backend/api/settings.py`（一般設定更新時の軽量バリデーション）
- `integrations/lbs/client.py`（最終送信前の防御）

## 3.4 推奨対応D: 観測性（デバッグ容易化）
- LBS連携ログに `timezone` を出す（機微情報を含まない範囲）。
- 不正TZや欠落時のwarningログを追加。

---

## 4. 変更スコープ

## 4.1 実装スコープ（コード）

### Backend Integration（主スコープ）
- `integrations/lbs/client.py`:
  - `x_timezone` 対応
  - `X-Timezone` ヘッダ付与
- `integrations/lbs/api.py`:
  - ユーザー設定timezoneの注入
  - Task create/update schemaへ `timezone` 追加
- `integrations/lbs/agent_tools.py`:
  - create/update時payload timezone補完

### Frontend（副スコープ）
- `core/frontend/lib/api.ts`:
  - （選択肢）フロント→VA APIに `X-Timezone` を付与するか検討
  - ※最終的にVAバックエンドからLBSへ付与できるなら必須ではない
- `core/frontend/app/components/TaskCreateModal.tsx`
- `core/frontend/app/components/TaskEditPanel.tsx`
  - Task payloadへ `timezone` を含める対応

### Settings / Data Layer（副スコープ）
- `core/backend/api/settings.py`:
  - timezone入力のバリデーション強化（IANA）
- DBスキーマ変更は原則不要（`general_settings` JSON格納済み）

## 4.2 影響範囲（仕様/UX）
- 日付境界のズレ（例: UTC日跨ぎ）に関するユーザー体験が改善。
- 既存データで `timezone` 未設定タスクはLBS側で `UTC` 扱いのため、表示時差の再確認が必要。
- API利用側（Agent/Automation）で同一日付指定でも結果がTZ依存になるため、テスト期待値更新が必要。

## 4.3 テストスコープ
- ユニット
  - `LBSClient` ヘッダ生成で `X-Timezone` を検証
  - Task payloadに `timezone` が入ることを検証
- 結合
  - `GET /api/lbs/schedule` がTZごとに日付境界反映されること
  - `POST/PUT /api/lbs/tasks` で `timezone` 透過されること
- E2E（任意）
  - 設定画面TZ変更 → ダッシュボード/スケジュールの見え方が変わること

---

## 5. 優先度つき実施案

1. **Phase 1（必須・高）**: Backend integrationで `X-Timezone` 自動付与 + Task `timezone` 透過。
2. **Phase 2（高）**: Agent toolsのpayload補完と回帰テスト追加。
3. **Phase 3（中）**: Frontend作成/編集UIで timezone明示（必要なら表示文言も整備）。
4. **Phase 4（中）**: バリデーション/ログ/監視の強化。

---

## 6. リスクと注意点
- TZ文字列がIANAでない場合、LBS側で400やUTCフォールバックの可能性。
- 既存タスク（timezone未保持）の表示に差異が出るため、移行ポリシー（既存=UTC固定 or ユーザーTZ補完）を事前決定すること。
- フロント側でTZを送っても、最終的にLBSへ渡すのはバックエンド経由のため、責務境界を明確化すること。

---

## 7. 参照した主要実装ポイント（VisionArk内）
- ユーザー設定のtimezone保持: `core/backend/api/settings.py`, `core/frontend/app/settings/page.tsx`
- LBSクライアントヘッダ生成: `integrations/lbs/client.py`
- LBSプロキシTask schema: `integrations/lbs/api.py`
- エージェント経由Task作成: `integrations/lbs/agent_tools.py`
- フロントAPI呼び出し共通処理: `core/frontend/lib/api.ts`

