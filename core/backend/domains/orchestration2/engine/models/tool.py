"""Tool definition model."""

from pydantic import BaseModel


class ToolDef(BaseModel):
    name: str
    description: str
    parameters: dict | None = None
    request_approval: bool = False
