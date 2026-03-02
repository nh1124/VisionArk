# Native デバイス選択・接続管理 設計レポート

## 1. 背景
現状の Native 実装は `user_id` 単位のジョブ管理が中心で、複数端末（PC / smartphone など）を同時に扱う際の
「どの端末が接続中で、どの端末にジョブを実行させるか」を厳密に扱う仕様が不足している。

本レポートでは、以下の運用要件を満たす設計を定義する。
- ユーザーが UI からデバイスを有効化する。
- エージェントは list からデバイス識別子を取得し、tool 実行時に対象デバイスを指定して使う。

---

## 2. 設計方針（決定）

### 2.1 役割分担
- **Backend**: デバイス登録・接続状態・有効化状態・能力情報の正本管理、ジョブルーティング。
- **Native（desktop/daemon/mobile）**: 自端末の自己申告（register/heartbeat）、自端末IDでのジョブ取得と実行。
- **Agent**: `list_native_devices` ツールで候補を取得し、`target_device_id` を指定して実行依頼。

### 2.2 運用ルール
1. ジョブ実行対象は原則 `target_device_id` 必須（省略時は backend が自動選定ポリシーを適用）。
2. 「有効化」されていないデバイスは実行対象にできない。
3. オフライン端末は選択できるが、実行は `queued_waiting_device` で待機させる。

---

## 3. データモデル

## 3.1 `native_devices`（新規）
| カラム | 型 | 説明 |
|---|---|---|
| id | UUID | デバイス識別子（`device_id`） |
| user_id | UUID | 所有ユーザー |
| display_name | string | UI表示名 |
| device_kind | enum(`desktop`,`mobile`,`server`,`other`) | 端末種別 |
| platform | enum(`windows`,`macos`,`linux`,`ios`,`android`,`other`) | OS種別 |
| client_version | string | Nativeクライアント版 |
| capabilities | JSON | 例: `run_shell`, `file_rw`, `open_app` |
| is_enabled | bool | ユーザーがUIで有効化したか |
| status | enum(`online`,`offline`,`stale`) | 接続状態 |
| last_seen_at | datetime | 最終heartbeat |
| created_at / updated_at | datetime | 監査用 |

### 3.2 `jobs`（既存拡張）
追加カラム:
- `target_device_id` (nullable, FK `native_devices.id`)
- `routing_mode` (`manual` | `auto`)
- `device_snapshot` (JSON; 実行時の端末情報を保持)

### 3.3 `device_sessions`（任意・推奨）
WebSocket/long-poll の接続単位管理。再接続診断・多重接続追跡に使用。

---

## 4. API設計

## 4.1 Device管理API
- `POST /api/native/devices/register`
  - Native起動時に自己登録（同一 fingerprint は upsert）
- `POST /api/native/devices/{device_id}/heartbeat`
  - `status=online`, `last_seen_at` 更新
- `GET /api/native/devices`
  - ユーザー所有デバイス一覧（agent/tool/UI共通）
- `PATCH /api/native/devices/{device_id}`
  - `display_name`, `is_enabled` 変更（UIから有効化/無効化）

## 4.2 Job API拡張
- `POST /api/jobs`
  - 追加入力: `target_device_id` / `routing_mode`
- `GET /api/jobs/pull?device_id=...&status=queued&limit=...`
  - daemon/mobile が「自分宛ジョブのみ」取得
- `POST /api/jobs/{job_id}/claim`
  - 取得競合時の二重実行防止（`claimed_by_device_id` 記録）

## 4.3 認可ルール
- `target_device_id` が他ユーザー所有なら 403。
- `is_enabled=false` のデバイスは実行対象指定不可（400）。
- backend更新系は `user_id + device_id + job_id` の複合条件で検証。

---

## 5. Agent Tool 契約（重要）

## 5.1 追加ツール
1. `list_native_devices()`
   - 返却: `[{device_id, display_name, device_kind, platform, is_enabled, status, capabilities, last_seen_at}]`
2. `run_native_job(...)`
   - 入力必須: `target_device_id`
   - 入力例: `{ "type": "local.dev", "target_device_id": "...", "payload": {...} }`

## 5.2 実行フロー
1. エージェントが `list_native_devices` を呼び出す。
2. 条件（enabled / online / capability一致）で候補選定。
3. `target_device_id` を明示して `run_native_job` 実行。
4. backend は対象デバイスへルーティングし、該当daemonのみが pull/claim して実行。

---

## 6. UI要件（ユーザー操作）

## 6.1 Settings > Devices 画面（新規）
- デバイス一覧（名前、OS、最終接続、状態、能力）
- 有効化トグル（`is_enabled`）
- 既定実行デバイス（optional）

## 6.2 Job作成時の選択
- 手動実行時に「対象デバイス」を選択可能。
- 未選択時は `routing_mode=auto`（ポリシーに従う）。

---

## 7. ルーティング仕様

## 7.1 manual
- `target_device_id` 必須。
- そのデバイスのみが pull/claim 可能。

## 7.2 auto
優先順位:
1. enabled=true
2. online
3. capability一致
4. 直近成功実績（optional）
5. fallback: `queued_waiting_device`

---

## 8. 障害・競合対策
- heartbeat未更新で `stale` 判定（例: 60秒）。
- claimタイムアウトで再キュー。
- 同一jobに対する二重claim防止（DB一意制約またはCAS更新）。
- deviceオフライン時は `waiting_device` を返し、UI/通知で再選択可能にする。

---

## 9. セキュリティ・監査
- すべての device API は user境界を強制。
- ジョブ実行ログに `target_device_id` / `claimed_by_device_id` / `executed_at` を記録。
- 高リスク操作は既存 approval と併用し、承認ログに device情報を残す。

---

## 10. 導入ロードマップ

### Phase 1（最小成立）
- `native_devices` + register/heartbeat/list/enable API
- Jobに `target_device_id` 追加
- daemon pullを `device_id` 指定型へ変更

### Phase 2（安定化）
- claim機構
- `routing_mode=auto` 実装
- UI Devices画面

### Phase 3（高度化）
- capabilityベース自動ルーティング
- device_session管理
- 詳細監査ダッシュボード

---

## 11. まとめ
- ご指定の要件
  - **「ユーザーがUIからデバイスを有効化」**
  - **「エージェントがlistで識別子取得し、tool実行時に指定」**
  は、上記設計で直接実現可能。
- まずは `device registry + target_device_id + pull/claim` の3点を先行導入することで、
  サーバー1台/Native複数端末の運用に必要な制御面を短期で成立できる。
