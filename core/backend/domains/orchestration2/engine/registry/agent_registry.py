"""Agent registry: agent_id -> AgentDef with name uniqueness."""

from __future__ import annotations

from uuid import uuid4

from ..errors import AgentNotFoundError, DuplicateNameError, RegistryKeyError
from ..models.agent import AgentDef

_REGISTRY_NAME = "AgentRegistry"


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, AgentDef] = {}  # agent_id -> AgentDef
        self._name_index: dict[str, str] = {}  # name -> agent_id

    def register(self, agent_def: AgentDef) -> str:
        """Register an agent and return its agent_id (UUID)."""
        if agent_def.name in self._name_index:
            raise DuplicateNameError(_REGISTRY_NAME, agent_def.name)
        agent_id = str(uuid4())
        self._agents[agent_id] = agent_def
        self._name_index[agent_def.name] = agent_id
        return agent_id

    def get(self, agent_id: str) -> AgentDef:
        if agent_id not in self._agents:
            raise AgentNotFoundError(f"Agent with id '{agent_id}' not found")
        return self._agents[agent_id]

    def get_by_name(self, name: str) -> tuple[str, AgentDef]:
        """Return (agent_id, AgentDef) by name."""
        agent_id = self._name_index.get(name)
        if agent_id is None:
            raise RegistryKeyError(_REGISTRY_NAME, name)
        return agent_id, self._agents[agent_id]

    def list(self) -> list[tuple[str, AgentDef]]:
        """Return list of (agent_id, AgentDef)."""
        return list(self._agents.items())

    def update(self, agent_id: str, agent_def: AgentDef) -> None:
        if agent_id not in self._agents:
            raise AgentNotFoundError(f"Agent with id '{agent_id}' not found")
        old_def = self._agents[agent_id]
        # If name changed, update name index
        if old_def.name != agent_def.name:
            if agent_def.name in self._name_index:
                raise DuplicateNameError(_REGISTRY_NAME, agent_def.name)
            del self._name_index[old_def.name]
            self._name_index[agent_def.name] = agent_id
        self._agents[agent_id] = agent_def

    def delete(self, agent_id: str) -> None:
        if agent_id not in self._agents:
            raise AgentNotFoundError(f"Agent with id '{agent_id}' not found")
        agent_def = self._agents.pop(agent_id)
        self._name_index.pop(agent_def.name, None)

    def has(self, agent_id: str) -> bool:
        return agent_id in self._agents

    def has_name(self, name: str) -> bool:
        return name in self._name_index
