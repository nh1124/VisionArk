# VisionArk Documentation Index

このディレクトリは、VisionArk システムの設計、仕様、および機能に関する情報を体系化したものです。将来のコーディングエージェントや開発者がシステムを迅速に把握できるように構成されています。

## 🏗️ [Core Architecture](./core/)
システムの中核となる設計思想や共通基盤に関するドキュメントです。
- [System Design](./core/system_design.md): 全体アーキテクチャ、哲学、要件定義。
- [File Management](./core/file_management.md): UUIDレジストリベースのファイル管理システム（最新）。
- [Skills System](./core/skills_system.md): エージェントスキルの定義と登録メカニズム。
- [External Integration](./core/external_integration.md): Microsoft Graph 等の外部サービス連携。
- [AES Worker Spec](./core/aes_worker_spec.md): バックグラウンドワーカーの仕様。
- [Node Prompt & Summarization](./core/node_prompt_summarization.md): プロンプト管理とコンテキスト要約のロジック。
- [Project Governance](./core/project_governance.md): プロジェクト固有のファイル命名規則、ディレクトリ構造、メタデータ管理。
- [External Integration](./core/external_integration.md): Microsoft Graph 等の外部サービス連携。

## 🔌 [Integration Guide](./integration_guide/)
外部システム連携（LINE, Calendar等）の開発者向け総合ガイド。
- [Integration Developer Guide](./integration_guide/README.md)

## ✨ [Features](./features/)
各特定の機能やノードに関する詳細仕様です。
- [Notes Feature](./features/notes_feature.md): ノート作成と管理機能。
- [Ask Node](./features/ask_node.md): 質問回答に特化したノード。
- [Calendar Integration](./features/external_calendar_integration.md): カレンダー同期機能の詳細。

## 🛡️ [Audits](./audits/)
システムの安全性や品質に関する監査結果です。
- [Ask Node Audit](./audits/ask_node_audit.md)

## � [Proposals](./proposals/)
将来の拡張やアーキテクチャの改善案に関するドキュメントです。
- [SDK Evolution Proposal](./proposals/sdk_evolution.md): SDKの型安全化と将来の拡張ロードマップ。

## �📁 [Archive](./reports/archive/)
過去の調査レポート、古いバージョンの仕様書など、歴史的コンテキストを保持するための場所です。
- [Skill Mining Investigation](./reports/archive/skill_mining_investigation.md)
- [Agent Skills Investigation](./reports/archive/agent_skills_investigation.md)
- [Legacy Tool Path Conventions](./reports/archive/tool_path_conventions.md)

---
*Last Updated: 2026-01-29*
