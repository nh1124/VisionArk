"""Hello World tools — example BaseTool implementations."""

from va_sdk import BaseTool, IntegrationContext, ToolResult


class EchoTool(BaseTool):
    """Returns the input message unchanged."""

    name = "hello_echo"
    description = "Echo back the input message. Useful for testing that custom tools are working."

    async def run(self, ctx: IntegrationContext, message: str = "Hello!", **kwargs) -> ToolResult:
        return ToolResult(
            content=f"Echo: {message}",
            is_success=True,
        )


class ReverseTextTool(BaseTool):
    """Returns the input text reversed character by character."""

    name = "hello_reverse"
    description = "Reverse a string character by character."

    async def run(self, ctx: IntegrationContext, text: str = "", **kwargs) -> ToolResult:
        if not text:
            return ToolResult(content="No text provided.", is_success=False)
        return ToolResult(
            content=text[::-1],
            is_success=True,
        )
