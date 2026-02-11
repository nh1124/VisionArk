"""Graph specification models parsed from YAML."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .common import ApprovalPolicy


class StepPolicy(BaseModel):
    approval: ApprovalPolicy = ApprovalPolicy.AUTO


class StepLimits(BaseModel):
    max_turns: int | None = None
    max_tool_calls: int | None = None
    max_parallel_delegations: int | None = None


class StepTransition(BaseModel):
    when: str
    next: str


class GraphStep(BaseModel):
    id: str
    type: str  # role | skill | approval | delegation | responder
    role: str | None = None
    skill: str | None = None
    policy: StepPolicy = Field(default_factory=StepPolicy)
    limits: StepLimits = Field(default_factory=StepLimits)
    on: list[StepTransition] = Field(default_factory=list)
    terminal: bool = False


class GraphSpec(BaseModel):
    version: int = 1
    graph_name: str
    start: str
    steps: list[GraphStep] = Field(default_factory=list)
