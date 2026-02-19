# antigravity向け 引き継ぎレポート（出力肥大化不整合）

- 作成日: 2026-02-18
- 目的: 今回の不整合調査結果を、antigravityチームがそのまま実装着手できる形で引き継ぐ。
- 対象: planner 周辺の長文出力（最終回答肥大化 / thinking process 肥大化）

---

## 1. 背景と依頼範囲

ユーザー観測では、`thinking step数=4` にもかかわらず以下が発生。

1. 最終回答が数千行に肥大化するパターン
2. 最終回答ではなく **thinking process 側** が数千行化するパターン（追伸ログ）

本レポートは、既存調査の確定事項と追加ログの示唆を統合し、antigravity向けに「何を直すか」を明文化したもの。

---

## 2. 既存調査での確定事項（コード根拠あり）

### 2.1 planner_capabilities の注入経路不整合
- `load_prompt_components()` で `planner_capabilities` を組み立てる設計だが、過去状態で早期 `return` により到達不能となる経路があった。
- その結果、planner が構造化 capability snapshot を使えず、フォールバックに流れやすい状態だった。

### 2.2 planner の raw skill本文フォールバック
- planner 側が `planner_capabilities` 不在時に `skills_text`（skill本文）をそのまま注入する設計があり、
  手順テンプレート・列挙文を誘発しうる。
- ログ上の `Action / Reasoning / Tool Call / Wait` 反復、`Use the ... tool` 大量列挙と整合。

---

## 3. 新規ログ（追伸）の示唆

### 観測要約
- 入力: `Hello world with c`
- 観測: 最終回答は通常に近いが、**Thinking Process (4 turns)** の内部が極端に長文化。
- パターン: 
  - 「If the user's request is ...」の定型文が大量反復
  - 同一文の反復（例: `If the user's request is a request for a hello world with c, provide it.`）
  - 末尾で最終回答は正常（CのHello World提示）

### 含意
- 「最終回答チャネル漏れ」だけでなく、**thinkingチャネルの反復制御不全** も独立に存在する可能性が高い。
- つまり、原因は1つではなく、少なくとも以下2系統:
  1. planner prompt汚染による最終出力肥大化
  2. thinking/reasoning生成側の反復停止条件不備

---

## 4. 原因仮説（antigravityで優先検証）

### H1. planner入力の情報粒度不整合
- 構造化 snapshot を渡すべき箇所で、長文の生本文（skill本文）が混入。
- 期待される「能力一覧」ではなく「手順テンプレート」を学習対象として受け取り、出力へ転写。

### H2. thinking出力の重複抑止欠如
- `thinking_step_limit=4` は「ステップ数」制御であり、
  各ステップのトークン/行数・自己類似度は別管理。
- 1ステップ内で自己展開（条件分岐テンプレートの再帰的列挙）が発生すると、4ステップでも長大化。

### H3. 推論ログの可視化レイヤでのフィルタ不足
- reasoning可視化時に、同型文の圧縮や上限打ち切りがない。
- 結果として、内部ループがユーザーから“無制限に見える”。

---

## 5. antigravityへの実装指示（必須）

### P0: planner入力の正規化を強制
1. plannerには `planner_capabilities`（構造化済み）だけを渡す。
2. `skills_text` の生本文を planner prompt に直接注入しない。
3. fallbackする場合も「skill名 + 1行説明 + tool名のみ」にサマリ化。

### P0: thinking/reasoningのハード上限
1. ステップごとに `max_reasoning_chars` または `max_reasoning_tokens` を導入。
2. 総量にも `max_total_reasoning_chars` を導入。
3. 超過時は「(reasoning truncated)」へ自動置換。

### P1: 反復検知（重複抑止）
1. 直近N行の重複率（例: 80%超）で生成停止。
2. 同一文の連続回数（例: 3回超）で圧縮表示。
3. `If the user's request is ...` のようなテンプレート反復を正規表現で検出し短縮。

### P1: 可視化レイヤの安全弁
1. thinking表示をデフォルトで折りたたむ。
2. 展開時もページネーション/先頭+末尾のみ表示。
3. 生ログダウンロードとUI表示を分離（UIは要約優先）。

### P2: 観測性
1. メトリクス追加:
   - `planner_prompt_chars`
   - `reasoning_chars`
   - `reasoning_repetition_score`
   - `final_answer_chars`
2. 異常閾値超過時にサンプル保存（再現解析用）。

---

## 6. antigravity向け検証シナリオ

### シナリオA: greeting最小入力
- 入力: `hello`
- 期待:
  - plannerは1行〜数行で終了
  - thinkingは短文のみ
  - `Use the ... tool` 連番出力が出ない

### シナリオB: plan再構成依頼
- 入力: 「以下の情報も含めてプランを再構成してください」
- 期待:
  - `Action/Reasoning/Tool Call/Wait` ブロック反復が出ない
  - 出力は指定フォーマット内で有限

### シナリオC: `Hello world with c`
- 期待:
  - 最終回答はCコード提示
  - thinkingは4ステップ内かつ各ステップ短文
  - 同一条件文の大量反復がゼロ

---

## 7. 受け入れ条件（Definition of Done）

- [ ] plannerに生skill本文が入らないことをテストで保証。
- [ ] thinking表示に行数/文字数上限が実装済み。
- [ ] 反復検知で同型文ループを停止できる。
- [ ] 上記3シナリオで再発しない（少なくとも連続20回実行で0件）。
- [ ] 異常時にメトリクス/サンプルログが取得可能。

---

## 8. 備考

- 今回の現象は「step数制御の破綻」ではなく、
  **(a) planner入力品質問題 + (b) reasoning反復抑止不足** の複合問題として扱うのが妥当。
- antigravity側では、prompt内容の最適化よりも先に
  **上限・重複抑止・可視化安全弁** を実装する方が効果が高い。
