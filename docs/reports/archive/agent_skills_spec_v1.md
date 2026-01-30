# Agent Skills Detailed Specification

## 1. スキル獲得エンジニアリング (Skill Acquisition)

### 1-1. 静的スキル (Static Skills)
*   **定義**: 開発者またはユーザーが明示的に作成・配置するスキル。
*   **配置**: `core/backend/skills/[skill_name]/SKILL.md` に基づく。
*   **登録方法**: システム起動時、または「スキル同期」ボタン押下時にファイルシステムをスキャンし、DB（`skills` テーブル）に同期する。

### 1-2. 動的スキル (Dynamic Skills)
*   **自動抽出 (Skill Mining)**:
    *   `QueueManager` を経由するタスクのうち、成功（`status='completed'`）かつユーザー評価が高い（または頻出する）手順を抽出。
    *   `Knowledge Core` に蓄積された時系列行動データを LLM で要約し、`SKILL.md` 形式の候補を出力。
*   **学習サイクル**:
    1.  **Observing**: `ChatMessage` / `ScheduledTask` の履歴を分析。
    2.  **Drafting**: AIが新しいスキル候補を作成し `is_draft=True` でDB登録。
    3.  **Refining**: ユーザーがUI上で「スキルとして保存」を承認・編集。

---

## 2. 管理UI (Management UI)

### 2-1. UI上の配置
*   **サイドメニュー**: 「Integrations」の下、または「Project Management」と同列に「**Skills**」メニューを追加。
*   **プロジェクト内設定**: 各プロジェクトの `Settings > Agent Skills` ページで、そのプロジェクトで使用可能なスキルを有効/無効化。

### 2-2. 主要機能
*   **Skill Explorer**:
    *   インストール済みスキルのカタログ表示（Name, Description, Author）。
    *   スキル毎のON/OFF切り替え。
*   **Skill Editor**:
    *   `SKILL.md` の内容をWeb上で編集（YAMLメタデータ、手順プロンプト）。
    *   使用ツールの紐付け。
*   **Learning Hub**:
    *   AIが自動生成した「スキル候補（Drafts）」のリスト表示。
    *   「承認（保存）」、「却下」、「修正」の操作。

---

## 3. 使用方法 (Usage Strategy)

### 3-1. 非明示的使用 (Implicit / Automatic)
*   エージェント（Node）にアサインされたスキルは、常にシステムプロンプトの一部として注入される。
*   **仕組み**: `NodeFactory` がエージェント生成時に、関連するスキルの `SKILL.md` の本文（Instruction）を結合する。

### 3-2. 明示的使用 (Explicit / Tool-like)
*   ユーザーがチャットで「〜スキルを使って〇〇して」と明示的に指示した場合。
*   特定のスキルに関連するツール群を優先的に活用して実行する。

---

## 4. 技術的実装 (Technical Implementation)

### 4-1. ディレクトリ構成
```bash
core/backend/
├── skills/                     # スキル基盤
│   ├── base.py                 # Skillモデル定義
│   ├── registry.py             # ファイル監視 & 動的ロード
│   └── [skill_id]/             # 個別スキル
│       └── SKILL.md            # 本体
└── va_sdk/
    └── skill_loader.py         # Nodeへのプロンプト注入ロジック
```

### 4-2. SKILL.md Format
```markdown
---
id: competitor-analysis-v1
name: 競合分析
description: 指定されたWebサイトのUI/UXと機能を分析します
version: 1.0.0
tools: ["search_web", "read_url_content"]
trigger_patterns: ["競合", "ベンチマーク", "他社比較"]
---
# 手順
1. 指定URLにアクセスし、主要なヒーローセクションをキャプチャ...
2. ...
```

### 4-3. システム変更点 (DB & Logic)

#### DBモデル拡張 (`models/database.py`)
```python
class Skill(Base):
    __tablename__ = "skills"
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True) # Global or User-owned
    name = Column(String(100))
    description = Column(String(500))
    content = Column(Text)              # SKILL.md の本文
    metadata_payload = Column(JSON)     # YAMLフロントマター
    is_active = Column(Boolean, default=True)
    is_draft = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class NodeSkill(Base):
    """NodeとSkillの多対多リレーション"""
    __tablename__ = "node_skills"
    node_id = Column(String(36), ForeignKey("nodes.id"), primary_key=True)
    skill_id = Column(String(36), ForeignKey("skills.id"), primary_key=True)
```

#### ロジック変更
1.  **`NodeFactory.get_node`**:
    *   DBから `node_skills` を取得し、対象スキルの `content` を取得。
    *   `system_prompt` の末尾に `### Attached Skills\n{skill_contents}` として注入。
2.  **`Worker`**:
    *   タスク完了後に `SkillMiningService` を非同期で呼び出し、分析を実行。
