"""Tool definition model."""

from pydantic import BaseModel


class ToolDef(BaseModel):
    name: str
    description: str
    request_approval: bool = False
