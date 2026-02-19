# Planner のツール可視性不足に関する改善案レポート

## 背景と課題

現状では planner が「実際に後段（project role）で使える tool / skill の全体像」を十分に認識しないまま計画を生成することがあり、結果として:

- planner が立てた手順を project role が実行段階で修正する
- 計画と実行の整合性が下がる
- 無駄な再計画・やり直しが増える

という問題が発生し得ます。

この課題は、単に prompt の文面改善だけでなく、
- 可視化情報の供給
- planning 制約
- 実行時検証
- 役割分担の明確化

を組み合わせて扱うのが効果的です。

---

## 1) 解決アプローチの全体像

対策は大きく 5 系統に分けられます。

1. **Planner に見せる情報を増やす**（tool/skill capability snapshot）
2. **Planner が使える skill を拡張する**（必要最小限）
3. **Planner prompt を構造化する**（可用能力を前提に計画させる）
4. **Plan-Validate ステップを追加する**（実行前の機械検証）
5. **Graph/Role の責務を再設計する**（計画と実行の契約を明文化）

---

## 2) 具体策（メリット・デメリット）

## A. Capability Snapshot 注入（最優先）

### 概要
planner 実行前に、現在セッションで実際に有効な能力をメタデータとして渡します。

例:
- 有効 skill 一覧
- skill→tool マッピング
- 各 tool の簡易説明（1行）
- integration tool の有効/無効状態

### メリット
- planner の「見えていない問題」を直接解消できる
- prompt 依存を減らし、事実ベースで計画可能
- 既存 role 実装への侵襲が比較的小さい

### デメリット
- メタデータ生成の責務追加（builder/loader 側）
- 表示情報が冗長だとトークンコスト増

### 実装イメージ
- `create_engine_for_project()` で dynamic skills / registered tools を集計
- `ctx.metadata["planner_capabilities"]` 等へ格納
- planner prompt で「この capability だけを使って計画せよ」と制約

---

## B. Planner への skill 付与拡張（慎重に）

### 概要
`planner` step の skills を増やし、調査だけでなく「計画に必要な確認ツール」を使えるようにする。

### メリット
- planner がより現実的な手順を作りやすい
- 例外ケース（外部連携が有効か等）を自分で確認できる

### デメリット
- planner が過剰に実行寄りになり、責務が肥大化
- tool call コスト増、計画前処理が重くなる
- security/policy 観点で planner に不要権限が載る恐れ

### 推奨
- 付与は「計画精度向上に必須の最小限」に限定
- まずは read-only 系（一覧/状態確認）から

---

## C. Planner Prompt の構造化（必須）

### 概要
プロンプトに以下を明示し、計画出力フォーマットも制約します。

- 利用可能 skill/tool の範囲
- 各ステップに必要能力を明記させる
- 不足能力がある場合は代替案を併記させる

### 出力フォーマット例
- Step
- Goal
- Required skill(s)
- Required tool(s)
- Fallback
- Exit condition

### メリット
- 人間レビュー・自動検証の両方がしやすい
- 後段 role での解釈ぶれが減る

### デメリット
- 既存 prompt と出力パーサの調整が必要

---

## D. Plan Validator ステップ追加（効果大）

### 概要
`plan -> validate_plan -> execute` へ graph を拡張し、
計画中に宣言された required tool/skill が実際に利用可能か機械検証します。

### チェック例
- required skill が agent に付与されているか
- required tool が skill の許可範囲に入っているか
- integration tool がセッション上で有効か

### メリット
- 「実行時に初めて破綻」が減る
- planner の品質ばらつきを吸収できる

### デメリット
- graph と validator 実装追加が必要
- strict にしすぎると柔軟性が落ちる

### 推奨
- 初期は warning ベース（自動修正提案）
- 安定後に fail-fast へ段階強化

---

## E. Planner と Project の契約（Plan Contract）

### 概要
計画を自由文だけでなく、契約オブジェクトとして扱います。

例（契約項目）:
- objectives
- ordered_steps
- required_capabilities
- risk_assumptions
- replanning_policy

Project role はこの契約を受け取り、
- 契約内で実行
- 契約逸脱時は理由を記録して再計画要求

### メリット
- 「なんとなく修正」ではなく、逸脱理由が追跡可能
- 監査性・説明可能性が上がる

### デメリット
- モデル/スキーマ/ログの整備コストがある

---

## 3) 推奨アーキテクチャ（段階導入）

### Phase 1（短期・低リスク）

1. Capability Snapshot 注入（A）
2. Planner Prompt 構造化（C）

**効果**
- planner の見落としを即時に低減
- 実装変更は比較的小さく、導入しやすい

### Phase 2（中期・推奨）

3. Plan Validator 追加（D）
4. planner skill 付与の最小拡張（B）

**効果**
- 計画と実行の不整合をシステム的に抑止
- 必要箇所だけ planner を強化

### Phase 3（長期・高度化）

5. Plan Contract 化（E）
6. 逸脱メトリクス収集（再計画率、逸脱理由分類）

**効果**
- 継続改善サイクルを回せる
- 品質を運用指標で管理できる

---

## 4) 具体的な改善オプション（比較表）

| 手法 | 効果 | 実装コスト | リスク | 推奨度 |
|---|---:|---:|---:|---:|
| Capability Snapshot | 高 | 低〜中 | 低 | ★★★★★ |
| Prompt 構造化 | 中〜高 | 低 | 低 | ★★★★★ |
| Planner skill 拡張 | 中 | 低〜中 | 中 | ★★★☆☆ |
| Plan Validator | 高 | 中 | 低〜中 | ★★★★☆ |
| Plan Contract | 高 | 中〜高 | 中 | ★★★★☆ |

---

## 5) 実務上の意思決定ガイド

次の順で判断すると進めやすいです。

1. まず「planner は何を見えていないか」を可視化（capability dump）
2. その不足が prompt で解決できるか検証
3. 解決しない不足のみ skill を追加
4. それでも揺れる場合は validator を導入
5. 長期運用で監査性が必要になったら contract 化

---

## 6) 結論

単独施策ではなく、

- **A. Capability Snapshot**
- **C. Prompt 構造化**
- （次点で）**D. Plan Validator**

の 3 点セットが、コストと効果のバランスが最も良いです。

`skill 付与を増やす` は有効ですが、先に可視化・検証レイヤを入れてから最小限で行うのが安全です。
