Agent Tooling Extension Report

Goal
- Deliver final outputs as PDF files (not Markdown).
- Enable the agent to operate Microsoft products (Word, Excel, PowerPoint).

1) Current Agent Tool Implementation Approach

1.1 Runtime model
- The agent uses tool calls with structured inputs/outputs.
- Current execution patterns include:
  - shell execution tools (command and session based)
  - MCP resource listing/reading tools
  - browser automation tools
  - pull request creation integration

1.2 Current strengths
- End-to-end automation is already possible: run commands, create artifacts, and commit changes.
- Tool responsibilities are separated, improving reliability and observability.
- Local artifact generation is straightforward.

1.3 Current gaps relative to requested features
- No standardized first-class PDF rendering tool contract.
- No dedicated Word/Excel/PowerPoint operation tools with stable APIs.
- Authentication and audit controls for Microsoft operations are not unified as a platform capability.

2) Additional Tools Required to Realize the Specification

2.1 Proposed tool set
A. render_pdf
- Purpose: convert structured content into stable, production-quality PDF.

B. word_tool
- Purpose: create/edit documents, apply templates/styles, support review workflow.

C. excel_tool
- Purpose: read/write ranges, formulas, pivots/charts, validations, summaries.

D. ppt_tool
- Purpose: generate/update slide decks from outlines, data, and templates.

E. ms_auth_manager
- Purpose: shared authentication, authorization, token lifecycle, and audit context.

2.2 Why split tools by product
- Word, Excel, and PowerPoint have different operation models and error modes.
- Smaller contracts are easier to test, secure, and roll out incrementally.
- Scope-based permission control is cleaner per tool.

3) Tool Specifications

3.1 render_pdf specification
Input
- source_type: markdown | html | text | json_template
- source_content: report content
- template_id: optional layout template
- options:
  - page_size, margins, header_footer
  - page_numbers, toc, locale, font_pack

Output
- pdf_path
- page_count
- warnings[]
- validation_report

Quality requirements
- Detect missing images/assets and unresolved links.
- Deterministic pagination for same input/template.
- dry-run mode for preview before final write.

3.2 word_tool specification
Core APIs
- create_from_template(template_id, data)
- patch_document(doc_id, operations[])
- apply_styles(doc_id, style_map)
- add_comments(doc_id, comments[])
- export(doc_id, format=docx|pdf)

Operational requirements
- Structured change history (who/when/what).
- Section-level patching for large documents.

3.3 excel_tool specification
Core APIs
- read_range(workbook_id, sheet, range)
- update_range(workbook_id, sheet, range, values)
- apply_formula(workbook_id, sheet, range, formula)
- create_pivot(workbook_id, config)
- create_chart(workbook_id, config)
- validate(workbook_id, rules)

Operational requirements
- Validation before write (type/null/range rules).
- Partial failure reporting with recovery hints.

3.4 ppt_tool specification
Core APIs
- create_from_template(template_id, outline)
- upsert_slide(deck_id, slide_spec)
- bind_chart(deck_id, excel_source)
- export(deck_id, format=pptx|pdf)

Operational requirements
- Enforce brand rules (font/color/layout).
- Per-slide generation logs and previews.

3.5 ms_auth_manager specification
Core APIs
- get_token(provider, scopes[])
- refresh_token(session_id)
- validate_scope(required_scopes[])
- attach_audit_context(operation_id, actor, resource)

Security requirements
- Least-privilege by default.
- Read and write scopes clearly separated.
- Data masking/redaction policy hooks.

4) Change Scope

4.1 Code scope
- Add five new tool registrations.
- Define stable input/output schemas.
- Add provider layer:
  - graph_provider (Microsoft Graph API)
  - office_script_provider (Office Scripts)
  - openxml_provider (offline document processing)
- Add common audit module with operation metadata and change digests.

4.2 Infrastructure scope
- Secret management for app credentials.
- Token refresh jobs.
- Centralized audit log sink (SIEM or audit DB).

4.3 Operations scope
- Permission request and approval flow.
- dry-run approval before production writes.
- Incident escalation for failed write operations.

4.4 Non-functional scope
- Observability: success rate, latency, failure taxonomy.
- Reliability: retries, backoff, idempotency keys.
- Maintainability: per-tool contract tests.

5) Recommended Rollout Plan

Phase 1 (2-4 weeks)
- Implement render_pdf + ms_auth_manager + excel_tool basic operations.
- Start with reporting workflows requiring PDF deliverables.

Phase 2 (4-8 weeks)
- Add word_tool and ppt_tool template-based generation.
- Enable controlled write operations in production.

Phase 3 (continuous)
- Integrate approval workflows and governance dashboards.
- Improve policy-driven controls and SLA tracking.

Final Recommendation
- Start with render_pdf and ms_auth_manager as shared foundations.
- Prioritize excel_tool for immediate business impact.
- Expand to word_tool and ppt_tool with strict auditability and scoped permissions.
