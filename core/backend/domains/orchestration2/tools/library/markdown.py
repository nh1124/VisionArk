"""Markdown tools: read/update sections, plan management."""

from __future__ import annotations

from domains.orchestration2.engine.models.execution import ExecutionContext, ToolResult
from domains.orchestration2.engine.models.message import ToolCallRef
from domains.orchestration2.engine.models.tool import ToolDef
from domains.orchestration2.tools.base import fail, make_result

CURRENT_PLAN_FILE = "PLAN.md"


class ReadMDSectionTool:
    definition = ToolDef(
        name="read_md_section",
        description=(
            "Extract a specific section from a markdown file by heading. "
            "HOW TO USE: read_md_section(file_path=\"manual.md\", section_title=\"Installation\")"
        ),
        parameters={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the markdown file"},
                "section_title": {"type": "string", "description": "Heading title to extract"},
            },
            "required": ["file_path", "section_title"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        file_path = call.arguments.get("file_path", "")
        section_title = call.arguments.get("section_title", "")

        # Read file via ReadReferenceTool
        from domains.orchestration2.tools.library.files import ReadReferenceTool

        read_call = ToolCallRef(tool_name="read_reference", call_id=call.call_id, arguments={"file_path": file_path})
        reader = ReadReferenceTool()
        res = await reader.invoke(read_call, ctx)
        if res.error:
            return res

        lines = res.output.splitlines()
        found = []
        capture = False
        title_lower = section_title.lower()

        for line in lines:
            if title_lower in line.lower() and line.startswith("#"):
                capture = True
                found.append(line)
            elif capture and line.startswith("#"):
                break
            elif capture:
                found.append(line)

        if not found:
            return fail(call, f"Section '{section_title}' not found in {file_path}")

        return make_result(call, "\n".join(found))


class InitPlanTool:
    definition = ToolDef(
        name="init_plan",
        description=(
            "Initialize the project's PLAN.md. ATTENTION: This will OVERWRITE any existing PLAN.md. "
            "HOW TO USE: init_plan(goal=\"Build a spaceship\", strategy=\"Modular assembly\")"
        ),
        parameters={
            "type": "object",
            "properties": {
                "goal": {"type": "string", "description": "Main goal of the plan"},
                "strategy": {"type": "string", "description": "Strategy to achieve the goal"},
            },
            "required": ["goal", "strategy"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        goal = call.arguments.get("goal", "")
        strategy = call.arguments.get("strategy", "")

        try:
            from shared.paths import get_plan_template_path

            template_path = get_plan_template_path()
            content = ""

            if template_path.exists():
                template = template_path.read_text(encoding="utf-8")
                content = template.replace("[メインゴールの記述]", goal).replace("[戦略・アプローチの記述]", strategy)

            if not content:
                from datetime import datetime

                content = (
                    f"# Goal\n{goal}\n\n# Strategy\n{strategy}\n\n"
                    f"# Current Status\nInitializing...\n\n# Log\n- Plan created at {datetime.now()}"
                )
        except Exception:
            from datetime import datetime

            content = (
                f"# Goal\n{goal}\n\n# Strategy\n{strategy}\n\n"
                f"# Current Status\nInitializing...\n\n# Log\n- Plan created at {datetime.now()}"
            )

        from domains.orchestration2.tools.library.files import SaveArtifactTool

        save_call = ToolCallRef(
            tool_name="save_artifact",
            call_id=call.call_id,
            arguments={"file_path": CURRENT_PLAN_FILE, "content": content, "overwrite": True},
        )
        return await SaveArtifactTool().invoke(save_call, ctx)


class UpdatePlanProgressTool:
    definition = ToolDef(
        name="update_plan_progress",
        description="Add a progress update entry to the Log section of PLAN.md.",
        parameters={
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Summary of progress made"},
            },
            "required": ["summary"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        summary = call.arguments.get("summary", "")

        from domains.orchestration2.tools.library.files import ReadReferenceTool, SaveArtifactTool

        read_call = ToolCallRef(tool_name="read_reference", call_id=call.call_id, arguments={"file_path": CURRENT_PLAN_FILE})
        res = await ReadReferenceTool().invoke(read_call, ctx)
        if res.error:
            return fail(call, "PLAN.md not found. Use init_plan first.")

        new_content = res.output + f"\n- {summary}"
        save_call = ToolCallRef(
            tool_name="save_artifact",
            call_id=call.call_id,
            arguments={"file_path": CURRENT_PLAN_FILE, "content": new_content, "overwrite": True},
        )
        return await SaveArtifactTool().invoke(save_call, ctx)


class GetCurrentStatusTool:
    definition = ToolDef(
        name="get_current_status",
        description="Retrieve the Current Status section from PLAN.md.",
        parameters={"type": "object", "properties": {}, "required": []},
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        section_call = ToolCallRef(
            tool_name="read_md_section",
            call_id=call.call_id,
            arguments={"file_path": CURRENT_PLAN_FILE, "section_title": "Current Status"},
        )
        return await ReadMDSectionTool().invoke(section_call, ctx)


class UpdateMDSectionTool:
    definition = ToolDef(
        name="update_md_section",
        description=(
            "Update or append content to a specific section in a markdown file. "
            "HOW TO USE: update_md_section(file_path=\"PLAN.md\", section_title=\"Status\", content=\"Done.\", mode=\"overwrite\")"
        ),
        parameters={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the markdown file"},
                "section_title": {"type": "string", "description": "Heading title to update"},
                "content": {"type": "string", "description": "New content for the section"},
                "mode": {"type": "string", "description": "overwrite (default) or append"},
            },
            "required": ["file_path", "section_title", "content"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        file_path = call.arguments.get("file_path", "")
        section_title = call.arguments.get("section_title", "")
        content = call.arguments.get("content", "")
        mode = call.arguments.get("mode", "overwrite")

        from domains.orchestration2.tools.library.files import ReadReferenceTool, SaveArtifactTool

        read_call = ToolCallRef(tool_name="read_reference", call_id=call.call_id, arguments={"file_path": file_path})
        res = await ReadReferenceTool().invoke(read_call, ctx)
        full_content = res.output if not res.error else ""

        lines = full_content.splitlines() if full_content else []
        new_lines = []
        section_found = False
        in_section = False
        title_lower = section_title.lower()

        i = 0
        while i < len(lines):
            line = lines[i]
            if line.startswith("#") and title_lower in line.lower():
                section_found = True
                in_section = True
                new_lines.append(line)

                if mode == "overwrite":
                    i += 1
                    while i < len(lines) and not lines[i].startswith("#"):
                        i += 1
                    new_lines.append(content)
                    in_section = False
                    continue
            elif in_section and line.startswith("#"):
                if mode == "append":
                    new_lines.append(content)
                in_section = False
                new_lines.append(line)
            else:
                if not in_section or mode == "append":
                    new_lines.append(line)
            i += 1

        if in_section and mode == "append":
            new_lines.append(content)

        if not section_found:
            if new_lines and new_lines[-1].strip():
                new_lines.append("")
            new_lines.append(f"# {section_title}")
            new_lines.append(content)

        final = "\n".join(new_lines)
        save_call = ToolCallRef(
            tool_name="save_artifact",
            call_id=call.call_id,
            arguments={"file_path": file_path, "content": final, "overwrite": True},
        )
        return await SaveArtifactTool().invoke(save_call, ctx)
