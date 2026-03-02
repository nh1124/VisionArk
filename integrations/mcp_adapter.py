"""MCP tool adapter for VisionArk orchestration2 engine.

Wraps a single MCP server tool as an orchestration2-compatible callable.
The MCP connection is established on each call (no persistent connection).
"""
from __future__ import annotations

import logging
from typing import Any

from domains.orchestration2.engine.models.execution import ExecutionContext, ToolResult
from domains.orchestration2.engine.models.message import ToolCallRef
from domains.orchestration2.engine.models.tool import ToolDef
from domains.orchestration2.tools.base import make_result, fail as orch_fail

logger = logging.getLogger(__name__)


class MCPToolAdapter:
    """Wraps a single MCP server tool as an orchestration2 tool callable."""

    def __init__(
        self,
        server_name: str,
        tool_name: str,
        description: str,
        url: str,
        headers: dict,
        input_schema: dict,
    ) -> None:
        self._server_name = server_name
        self._url = url
        self._headers = headers
        self.definition = ToolDef(
            name=tool_name,
            description=description or f"MCP tool from {server_name}",
            parameters=input_schema or {"type": "object", "properties": {}, "required": []},
        )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        """Execute the MCP tool by connecting to the server and calling the tool."""
        try:
            from mcp.client.sse import sse_client
            from mcp import ClientSession

            tool_args = call.arguments or {}

            async with sse_client(url=self._url, headers=self._headers) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        name=self.definition.name,
                        arguments=tool_args,
                    )

            text_parts = [
                c.text for c in result.content if hasattr(c, "text") and c.text
            ]
            output = "\n".join(text_parts) if text_parts else "(no output)"
            return make_result(call, output)

        except Exception as exc:
            logger.warning(
                "MCP tool '%s' on server '%s' failed: %s",
                self.definition.name, self._server_name, exc,
            )
            return orch_fail(call, f"MCP call failed: {exc}")
