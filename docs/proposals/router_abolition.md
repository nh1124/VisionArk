# Proposal: Router Abolition

## 1. 概要 (Overview)

**目的**: オーケストレーション責務の単純化。
現在は正規表現フック/購読情報に基づく「Router」による非同期ディスパッチ機構が存在するが、実行経路が増えて追跡が困難になっている。
これを廃止し、実行経路を「ユーザー入力 → 対象プロジェクト実行」を中心に収束させる。

## 2. 現状の課題 (Current Issues)

- **Routerの複雑性**: `Router` (`api/router.py`) はsingleton的に `_hooks` を保持し、メッセージ本文に基づくregexフックを行っている。
- **同期処理の負担**: Worker起動時および日次タスク(`SYNC_ROUTER_HOOKS`)でRouter初期化・再同期が必要。
- **分散したロジック**: ツール側の `subscribe_to_intent` などが `ProjectAgent.meta_payload` を更新し、Router再初期化をトリガーするなど、処理が分散している。

## 3. 提案内容 (Proposed Changes)

### 推奨改修

1.  **Routerの廃止**:
    -   `api/router.py` を廃止。
2.  **定期タスクの削除**:
    -   Worker起動時のRouter初期化フローを削除。
    -   日次 `SYNC_ROUTER_HOOKS` スケジューリングおよびハンドラ(`aes_system_handlers.py`)を削除。
3.  **関連ツールの削除**:
    -   Routing系ツール (`subscribe`, `unsubscribe`, `list`, `multicast`) を削除。

### 影響

-   `ProjectAgent.meta_payload.trigger_patterns` / `semantic_interests` などのフィールドは運用価値が下がるため、将来的なクリーンアップ対象となる。

## 4. 変更スコープ (Scope of Changes)

-   `core/backend/api/router.py` (廃止)
-   `core/backend/app/worker.py` (初期化 + 日次タスク登録削除)
-   `core/backend/domains/automation/aes_system_handlers.py` (`SYNC_ROUTER_HOOKS` 削除)
-   `core/backend/domains/orchestration2/tools/library/routing.py` (削除)
-   `core/backend/domains/orchestration2/engine_setup.py` (routingツール登録削除)

## 5. 改修難易度 (Difficulty & Priority)

-   **難易度**: 中
-   **優先度**: 低 (最後に実施推奨)

依存点は複数ファイルに散在しているが、基本的には「機能を削る」作業である。
ただし日次タスク(`SYNC_ROUTER_HOOKS`)の削除に伴う後始末や、エラーログ回避のための互換性維持に注意が必要。
