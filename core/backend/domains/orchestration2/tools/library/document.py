"""Document output tools: render_pdf."""

from __future__ import annotations

import json
import logging
import re

from domains.orchestration2.engine.models.execution import ExecutionContext, ToolResult
from domains.orchestration2.engine.models.message import ToolCallRef
from domains.orchestration2.engine.models.tool import ToolDef
from domains.orchestration2.tools.base import fail, make_result, resolve_artifacts_dir

logger = logging.getLogger(__name__)


_DEFAULT_CSS = """
body {
  font-family: 'Segoe UI', 'Hiragino Sans', 'Meiryo', sans-serif;
  font-size: 11pt; line-height: 1.7; color: #1a1a1a;
}
h1 { font-size: 20pt; border-bottom: 2px solid #333; padding-bottom: 4px; }
h2 { font-size: 15pt; border-bottom: 1px solid #aaa; padding-bottom: 2px; }
h3 { font-size: 13pt; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; }
th, td { border: 1px solid #ccc; padding: 6px 10px; }
th { background: #f0f0f0; font-weight: bold; }
pre, code { font-family: 'Consolas', monospace; background: #f5f5f5; padding: 2px 4px; }
pre { padding: 10px; }
blockquote { border-left: 3px solid #aaa; margin: 0; padding-left: 12px; color: #555; }
"""

_PLAYWRIGHT_FORMATS = {"A4", "Letter", "Legal", "Tabloid", "A3", "A5"}


def _safe_name(name: str, fallback: str = "output") -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip() or fallback


def _to_html(source_type: str, content: str, options: dict, warnings: list) -> str:
    if source_type == "markdown":
        body = _md_to_html(content, warnings)
    elif source_type == "html":
        body = content
    elif source_type == "json_template":
        body = _json_to_html(content, warnings)
    else:
        escaped = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        body = f"<pre>{escaped}</pre>"

    if options.get("toc"):
        body = _build_toc(body) + body

    extra_css = options.get("extra_css", "")
    locale = options.get("locale", "")
    lang = f' lang="{locale}"' if locale else ""
    return (
        f'<!DOCTYPE html><html{lang}><head><meta charset="UTF-8">'
        f"<style>{_DEFAULT_CSS}{extra_css}</style></head><body>{body}</body></html>"
    )


def _md_to_html(content: str, warnings: list) -> str:
    try:
        import markdown as md_lib
        return md_lib.markdown(content, extensions=["tables", "fenced_code", "toc", "nl2br"])
    except ImportError:
        warnings.append("markdown library missing; rendering as plain text.")
        return f"<pre>{content}</pre>"
    except Exception as exc:
        warnings.append(f"Markdown warning: {exc}")
        return f"<pre>{content}</pre>"


def _json_to_html(content: str, warnings: list) -> str:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        warnings.append(f"Invalid JSON: {exc}")
        return f"<pre>{content}</pre>"
    parts: list[str] = []
    if t := data.get("title"):
        parts.append(f"<h1>{t}</h1>")
    if s := data.get("subtitle"):
        parts.append(f"<p><em>{s}</em></p>")
    for section in data.get("sections", []):
        if h := section.get("heading"):
            parts.append(f"<h2>{h}</h2>")
        if b := section.get("body"):
            parts.append(f"<p>{b}</p>")
        if items := section.get("items", []):
            parts.append("<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>")
        headers = section.get("table_headers", [])
        rows = section.get("table_rows", [])
        if headers or rows:
            parts.append("<table>")
            if headers:
                parts.append("<thead><tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr></thead>")
            if rows:
                parts.append("<tbody>" + "".join(
                    "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows
                ) + "</tbody>")
            parts.append("</table>")
    return "\n".join(parts) or "<p>(empty)</p>"


def _build_toc(html_body: str) -> str:
    headings = re.findall(r"<h([1-3])[^>]*?>(.*?)</h\1>", html_body, re.I | re.S)
    if not headings:
        return ""
    items = [
        f"<li>{'&nbsp;' * (int(lvl) - 1) * 4}{re.sub(r'<[^>]+>', '', txt).strip()}</li>"
        for lvl, txt in headings
    ]
    return f"<h2>Table of Contents</h2><ul>{''.join(items)}</ul><hr>"


def _validate(content: str, warnings: list) -> dict:
    return {
        "missing_assets": re.findall(r'!\[.*?\]\(((?!https?://).+?)\)', content),
        "unresolved_links": re.findall(r'\[.*?\]\(((?!https?://).+?)\)', content),
        "warnings_count": len(warnings),
    }


async def _render(html: str, options: dict) -> bytes:
    from playwright.async_api import async_playwright
    page_size = options.get("page_size", "A4")
    if page_size not in _PLAYWRIGHT_FORMATS:
        page_size = "A4"
    m = options.get("margins", {})
    header_text = options.get("header", "")
    footer_text = options.get("footer", "")
    page_numbers = options.get("page_numbers", False)
    _s = "font-family:'Segoe UI',sans-serif;font-size:9px;color:#555;width:100%;padding:0 20mm;box-sizing:border-box;"
    display_hf = bool(header_text or footer_text or page_numbers)
    header_tmpl = f'<div style="{_s}text-align:center;">{header_text}</div>' if header_text else ("<span></span>" if display_hf else "")
    pn = '<span class="pageNumber"></span> / <span class="totalPages"></span>' if page_numbers else ""
    footer_body = "  ·  ".join(filter(None, [footer_text, pn]))
    footer_tmpl = f'<div style="{_s}text-align:center;">{footer_body}</div>' if footer_body else ("<span></span>" if display_hf else "")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=["--no-sandbox"])
        try:
            page = await browser.new_page()
            await page.set_content(html, wait_until="networkidle")
            pdf_bytes = await page.pdf(
                format=page_size,
                margin={
                    "top": f"{m.get('top', 20)}mm",
                    "bottom": f"{m.get('bottom', 20)}mm",
                    "left": f"{m.get('left', 20)}mm",
                    "right": f"{m.get('right', 20)}mm",
                },
                display_header_footer=display_hf,
                header_template=header_tmpl,
                footer_template=footer_tmpl,
                print_background=True,
            )
        finally:
            await browser.close()
    return pdf_bytes


class RenderPdfTool:
    definition = ToolDef(
        name="render_pdf",
        description=(
            "Render content (Markdown, HTML, plain text, or JSON template) to a "
            "production-quality PDF file. Uses Playwright for rendering — supports "
            "full Unicode including Japanese. Saves to artifacts/pdfs/."
        ),
        parameters={
            "type": "object",
            "properties": {
                "source_type": {
                    "type": "string",
                    "description": "Content format: markdown | html | text | json_template",
                },
                "source_content": {
                    "type": "string",
                    "description": "Content to render as PDF",
                },
                "output_filename": {
                    "type": "string",
                    "description": "Output file name without .pdf extension",
                    "default": "output",
                },
                "options": {
                    "type": "object",
                    "description": (
                        "Rendering options: page_size (A4/Letter/A3/A5), "
                        "margins ({top,bottom,left,right} in mm), "
                        "header (str), footer (str), page_numbers (bool), "
                        "toc (bool), extra_css (str)"
                    ),
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "Validate without writing file",
                    "default": False,
                },
            },
            "required": ["source_type", "source_content"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        source_type: str = call.arguments.get("source_type", "text")
        source_content: str = call.arguments.get("source_content", "")
        output_filename: str = _safe_name(call.arguments.get("output_filename", "output"))
        options: dict = call.arguments.get("options") or {}
        dry_run: bool = call.arguments.get("dry_run", False)

        warnings: list[str] = []

        try:
            html = _to_html(source_type, source_content, options, warnings)
        except Exception as exc:
            return fail(call, f"Content conversion failed: {exc}")

        if dry_run:
            result_data = {
                "success": True,
                "dry_run": True,
                "warnings": warnings,
                "message": "Dry run OK — use dry_run=false to write the PDF.",
                "validation_report": _validate(source_content, warnings),
            }
            return make_result(call, json.dumps(result_data))

        try:
            pdf_bytes = await _render(html, options)
        except ImportError:
            return fail(
                call,
                "Playwright/Chromium not available. "
                "Run: pip install playwright && playwright install chromium",
            )
        except Exception as exc:
            logger.exception("render_pdf rendering failed")
            return fail(call, f"PDF rendering failed: {exc}")

        try:
            art = await resolve_artifacts_dir(ctx)
            pdf_dir = art / "pdfs"
            pdf_dir.mkdir(parents=True, exist_ok=True)
            out_path = pdf_dir / f"{output_filename}.pdf"
            out_path.write_bytes(pdf_bytes)
        except Exception as exc:
            return fail(call, f"Failed to save PDF: {exc}")

        page_count = pdf_bytes.count(b"/Type /Page\n") or pdf_bytes.count(b"/Type/Page")
        if page_count == 0:
            page_count = max(1, len(pdf_bytes) // 50_000)

        result_data = {
            "success": True,
            "file_path": f"artifacts/pdfs/{output_filename}.pdf",
            "format": "pdf",
            "size_bytes": len(pdf_bytes),
            "page_count": page_count,
            "warnings": warnings,
            "validation_report": _validate(source_content, warnings),
        }
        return make_result(call, json.dumps(result_data))
