# AESリファクタリング調査レポート

作成日: 2026-02-17

## 1. aes処理内容

現状のAES（Automated Execution System）は、概ね以下の4段で動作しています。

1. **タスク登録（API/サービス）**
   - `/api/automation/schedule` から `scheduled_tasks` に `PENDING` で保存。  
   - `AESDispatcher.schedule_task()` でも同様に `ScheduledTask` を生成可能。

2. **ディスパッチ（ポーリング）**
   - `AESDispatcher.run_forever()` が10秒間隔で `dispatch_pending_tasks()` を呼び出し。  
   - `scheduled_at <= now` かつ `PENDING` のタスクを取得し、`PROCESSING` に更新して Redis Queue に投入。

3. **ワーカー実行**
   - `Worker._process_task()` が `TaskType.AES_SYSTEM_TASK` を受けると `_handle_aes_task()` を実行。  
   - DBから該当 `ScheduledTask` を取得し、`AESSystemHandlers.execute(task_type, context)` へ委譲。

4. **ハンドラ実行・後処理**
   - `aes_system_handlers.py` 内のレジストリ登録済みハンドラ（例: `HARD_DELETE`, `SYSTEM_TIMER`, `PROJECT_SNAPSHOT` など）を実行。  
   - 完了後、`ScheduledTask` を `COMPLETED` に更新。`recurring_rule` がある場合は次回分を再作成。

---

## 2. 不適になっているaes内容（リファクタ観点）

以下は、現状コード上で「設計の揺れ」または「リファクタ途中の痕跡」と見えるポイントです。

### A. スケジューリング経路が二重化している
- API (`/api/automation/schedule`) 側で `ScheduledTask` を直接生成しており、`AESDispatcher.schedule_task()` を使っていません。  
- そのため、時刻正規化・バリデーション方針・ログの実装が複線化し、将来差分が生まれやすい状態です。

### B. AESハンドラ登録モデルが「クラス/関数」の混在前提になっている
- `AESSystemHandlers.execute()` で「クラス型（`BaseAESHandler`継承）」「関数型（callable）」の両方を許可。  
- 柔軟性はありますが、責務境界が曖昧になり、型安全性・テスト容易性が低下しやすいです（特に integration 側に広がると顕在化）。

### C. LINE連携のコメント群が実装現状と乖離
- `integrations/line/handlers.py` 冒頭コメントに「Not yet implemented...」「plan referred...」等の経緯メモが残存。  
- 現状の責務（task/reply registryハンドラとして機能）に対して説明が古く、保守者が誤解しやすいです。

### D. Dispatcherの分散実行安全性が弱い
- `dispatch_pending_tasks()` は `PENDING` 一括取得後に `PROCESSING` へ更新していますが、行ロックや `SKIP LOCKED` などの排他戦略が明示されていません。  
- コメントでも「単一dispatcher前提」寄りの注記があり、将来水平スケール時の二重配信リスクが残ります。

### E. 使われていないimport/古い導線が残っている
- `aes_dispatcher.py` に未使用import（`json`, `update`, `AsyncSession`）が残存。  
- `api/automation.py` でも `AESDispatcher` import が未使用。  
- 小さな点ですが、リファクタ済みコードとしてはノイズです。

---

## 3. 変更提案

### 提案1: スケジュール作成を単一経路へ統一
- `api/automation.py` の `POST /schedule` と `PUT /tasks/{task_id}` の保存処理を、`AESDispatcher.schedule_task()`（または新設 `SchedulerService`）へ寄せる。
- 「時刻正規化」「payload初期化」「初期ステータス付与」を共通化し、重複ロジックを削減。

### 提案2: AESハンドラ契約を1種類に揃える
- 原則を「クラスベース（`BaseAESHandler`継承）」に統一（または逆に関数型に統一）。
- `aes_registry` 側で型チェックを強化し、登録時に契約違反を落とす。
- 既存integrationハンドラは薄いAdapterで包んで段階移行。

### 提案3: LINEハンドラのヘッダコメントを現行仕様へ更新
- 「過去の検討メモ」を削除し、
  - task registry の役割
  - reply registry の役割
  - workerとの接続点
  を簡潔に記述する。

### 提案4: ディスパッチの排他制御を導入
- DBがPostgreSQLなら `SELECT ... FOR UPDATE SKIP LOCKED` パターンへ変更。
- 併せて「1回のディスパッチ上限件数（batch size）」を導入し、負荷平準化。
- `PROCESSING` で停滞したタスクの再回収（timeout-based requeue）も設計に追加。

### 提案5: 不要import/不要依存を整理
- `aes_dispatcher.py`, `api/automation.py` などの未使用importを削除。
- CIに `ruff`/`flake8` の未使用importチェックを組み込む（未導入なら段階導入）。

---

## 4. 変更スコープ

### 最小スコープ（短期・安全）
- `integrations/line/handlers.py` の説明コメント更新。
- `core/backend/domains/automation/aes_dispatcher.py` の未使用import削除。
- `core/backend/api/automation.py` の未使用import削除。

### 中スコープ（推奨）
- `core/backend/api/automation.py` と `core/backend/domains/automation/aes_dispatcher.py` の責務整理（スケジュール作成共通化）。
- `core/backend/domains/automation/aes_system_handlers.py` のハンドラ契約統一に向けたAdapter導入。
- 影響確認: `core/backend/app/worker.py`、`integrations/*/handlers.py`。

### 大スコープ（将来）
- Dispatcher排他制御の刷新（DBロック戦略・再試行戦略・監視メトリクス導入）。
- 運用面の整備: stuck task監視、再実行ポリシー、可観測性（ログ構造化/メトリクス）。

---

## 補足（実施順の推奨）
1. **短期クリーニング**（コメント・未使用import）
2. **スケジュール作成経路の一本化**
3. **ハンドラ契約の統一**
4. **排他制御・運用設計の強化**

この順に進めると、機能影響を最小化しつつ段階的に整流化できます。
