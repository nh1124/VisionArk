# Agent Skills System

Skills は「能力境界の宣言」と「実行時ガードレール」を提供します。
正本は `orchestration2` の `SkillDef` / `SkillRegistry` のみです。

---

## 1. 正本: orchestration2

### SkillDef（仕様の唯一の型）

```python
class SkillDef(BaseModel):
    name: str
    description: str | None = None
    tools: list[str] = []          # このスキルが使用できるツール名
    request_approval: bool = False
```

### SkillRegistry

- `core/backend/domains/orchestration2/engine/registry/skill_registry.py`
- `name → (SkillDef, impl)` マッピングを管理
- `StepExecutor` が step 単位で使用可能ツールを解決するために参照する

---

## 2. エンジン起動フロー

1. `config/skills/default_skills.py` の `SKILL_DEFS` を読み込む
2. Integration が提供するツールをエンジンへ登録
3. 必要に応じて integration ツールを適切な `SkillDef.tools` へマージ
4. `SkillRegistry` 登録後、agent に skill 名を割り当てる

実装: `core/backend/domains/orchestration2/bootstrap/project_engine_builder.py`

---

## 3. 静的スキルの追加方法

`config/skills/default_skills.py` に `SkillDef` エントリを追加します:

```python
SkillDef(
    name="my_skill",
    description="このスキルの概要",
    tools=["tool_a", "tool_b"],
)
```

---

## 4. 廃止済みコンポーネント

> [!WARNING]
> 以下のコンポーネントは廃止・除去されています。
> 詳細は [ADR: Skills Deprecation](../decisions/ADR-skills-deprecation.md) を参照してください。

| コンポーネント | 状態 | 代替 |
|---|---|---|
| `automation/skill_service.py` | **除去済み** | `orchestration2` の `SkillDef` |
| `automation/skills/registry.py` | **除去済み** | UI/API によるスキル管理（現在も廃止） |
| DB `skills` テーブル + `/api/skills` | **廃止済み** | `config/skills/default_skills.py` |
| `integrations/*/SKILL.md` の runtime 参照 | **廃止済み** | `orchestration2/config/skills/` で一元管理 |
| Frontend Skills ページ | **廃止済み** | 廃止案内ページを表示 |

---

## 5. 将来の拡張（DB再導入）

DB保存は現在保留中です。将来再導入する場合は:

- `SkillDef` と 1:1 で対応するシリアライズ形式（JSON/YAML）を使用する
- `version` フィールドを含む互換方針を策定する
- backend では「保存先」を抽象化（in-memory provider / DB provider）する

詳細は `docs/proposals/Skill_refactoring.md` の Phase 2〜3 を参照してください。
