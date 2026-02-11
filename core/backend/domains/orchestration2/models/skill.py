"""Skill definition model."""

from pydantic import BaseModel, Field


class SkillDef(BaseModel):
    name: str
    description: str | None = None
    tools: list[str] = Field(default_factory=list)
    request_approval: bool = False
