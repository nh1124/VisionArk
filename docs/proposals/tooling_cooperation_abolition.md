# Proposal: Tooling Cooperation Abolition

## 1. 概要 (Overview)

**目的**: オーケストレーション責務の単純化と誤解の解消。
`ask_agent` や `broadcast` などのツールは「他エージェントに投げる」設計だが、現状の実装（`create_engine_for_project`）では `target_agent_id` が無視され、常に単一のProject Agentが実行される。
この概念と実装の乖離を解消するため、これらツールを廃止または機能転換する。

## 2. 現状の課題 (Current Issues)

-   **実装の乖離**: `AskAgentTool` 等は `target_agent_id` をQueueに積むが、Worker側はProject単位で都度Agent定義を生成しており、指定されたAgent IDへの切り替えが行われない。
-   **誤解を招くコンテキスト**: PromptにTeam Roster（他Member/Project情報）が注入されているため、LLMは「呼び出せる」と認識してしまうが、実際には同一Project Agent内で処理されるか、期待通りに動かない。

## 3. 提案内容 (Proposed Changes)

### 推奨改修

1.  **ツールの廃止/無効化**:
    -   `ask_agent`
    -   `broadcast_system_message`
    -   `list_agents` (呼び出し先一覧としての用途廃止)
    -   `multicast_message` (Router廃止と連動)
2.  **Promptの修正**:
    -   `_load_prompt_components()` における Team Roster の注入を停止、または「参照情報のみ」である旨を明記して縮退させる。
3.  **仕様の明文化**:
    -   「1 run = 1 project agent」という現在の動作仕様を正とし、マルチエージェント動作は将来の `orchestration2` の delegation 機構に委ねる（今回はスコープ外）。

## 4. 変更スコープ (Scope of Changes)

-   `core/backend/domains/orchestration2/tools/library/system.py`
-   `core/backend/domains/orchestration2/engine_setup.py` (systemツール登録修正)
-   `core/backend/domains/orchestration2/engine_setup.py` (team roster 生成ロジック修正)

## 5. 改修難易度 (Difficulty & Priority)

-   **難易度**: 低〜中
-   **優先度**: 中 (2番目に実施推奨)

主にツール定義の削除とPrompt修正で対応可能。
既存Promptが期待している挙動と実動作の差を埋めることで、LLMの混乱（ハルシネーション等）を減らす効果も期待できる。
