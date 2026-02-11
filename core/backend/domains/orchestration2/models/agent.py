"""Agent definition models."""

from pydantic import BaseModel, Field


class AgentLimits(BaseModel):
    max_turns: int = 12
    max_parallel_delegations: int = 2


class AgentDef(BaseModel):
    name: str
    description: str | None = None
    graph_name: str
    default_model: str
    skills: list[str] = Field(default_factory=list)
    role_bindings: dict[str, str] = Field(default_factory=dict)
    limits: AgentLimits = Field(default_factory=AgentLimits)


class AgentIdRef(BaseModel):
    agent_id: str
