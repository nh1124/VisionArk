"""AgentEngine facade — the public API for orchestration2."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .errors import AgentNotFoundError, RegistryKeyError
from .interfaces.llm_provider import LLMProvider
from .interfaces.role import BaseRole
from .interfaces.skill import BaseSkill
from .interfaces.store import Store
from .interfaces.tool import BaseTool
from .models.agent import AgentDef
from .models.approval import ApprovalDecision, ApprovalRequest
from .models.common import RunStatus
from .models.delegation import DelegationRequest, DelegationResult, DelegationResultStatus
from .models.execution import RunResponse
from .models.graph_spec import GraphSpec
from .models.message import Message
from .models.run import RunRecord
from .models.skill import SkillDef
from .models.tool import ToolDef
from .orchestration.approval_manager import ApprovalManager
from .orchestration.delegation_manager import DelegationManager
from .orchestration.graph_compiler import parse_graph_yaml
from .orchestration.orchestrator import Orchestrator
from .orchestration.step_executor import StepExecutor
from .registry.agent_registry import AgentRegistry
from .registry.graph_registry import GraphRegistry
from .registry.model_registry import ModelConfig, ModelRegistry
from .registry.role_registry import RoleRegistry
from .registry.skill_registry import SkillRegistry
from .registry.tool_registry import ToolRegistry
from .store.in_memory_store import InMemoryStore

from typing import TYPE_CHECKING as _TC
if _TC:
    from .interfaces.llm_engine import LLMEngine

logger = logging.getLogger(__name__)


class AgentEngine:
    """Orchestration2 engine — owns registries, store, and orchestrator.

    Instantiable (not a singleton) to enable testing and multiple instances.
    """

    def __init__(self, store: Store | None = None, engine_runtime: LLMEngine | None = None) -> None:
        # Store
        self._store: Store = store or InMemoryStore()
        # Engine runtime (optional — enables multi-turn delegation)
        self._engine_runtime = engine_runtime

        # Registries
        self.tools = ToolRegistry()
        self.skills = SkillRegistry()
        self.roles = RoleRegistry()
        self.models = ModelRegistry()
        self.graphs = GraphRegistry()
        self.agents = AgentRegistry()

        # Managers
        self._approval_mgr = ApprovalManager(self._store)
        self._delegation_mgr = DelegationManager(self._store)

        # Step executor
        self._step_executor = StepExecutor(
            store=self._store,
            tool_registry=self.tools,
            skill_registry=self.skills,
            role_registry=self.roles,
            model_registry=self.models,
            approval_manager=self._approval_mgr,
            delegation_manager=self._delegation_mgr,
            engine_runtime=self._engine_runtime,
        )

    def register_engine(self, engine: LLMEngine) -> None:
        """Register an LLMEngine and propagate it to the step executor."""
        self._engine_runtime = engine
        self._step_executor._engine = engine

        # Orchestrator
        self._orchestrator = Orchestrator(self._store, self._step_executor)

        # Async run tracking
        self._async_tasks: dict[str, asyncio.Task[RunResponse]] = {}

    # ── Registry: Tools ──────────────────────────────────────────────

    def register_tool(self, tool_def: ToolDef, tool_impl: BaseTool) -> None:
        self.tools.register(tool_def, tool_impl)

    def list_tools(self) -> list[ToolDef]:
        return self.tools.list()

    def get_tool(self, name: str) -> ToolDef:
        return self.tools.get_def(name)

    def update_tool(self, tool_def: ToolDef, tool_impl: BaseTool) -> None:
        self.tools.update(tool_def, tool_impl)

    def delete_tool(self, name: str) -> None:
        self.tools.delete(name)

    # ── Registry: Skills ─────────────────────────────────────────────

    def register_skill(
        self, skill_def: SkillDef, skill_impl: BaseSkill
    ) -> None:
        self.skills.register(skill_def, skill_impl)

    def list_skills(self) -> list[SkillDef]:
        return self.skills.list()

    def get_skill(self, name: str) -> SkillDef:
        return self.skills.get_def(name)

    def update_skill(
        self, skill_def: SkillDef, skill_impl: BaseSkill
    ) -> None:
        self.skills.update(skill_def, skill_impl)

    def delete_skill(self, name: str) -> None:
        self.skills.delete(name)

    # ── Registry: Roles ──────────────────────────────────────────────

    def register_role(self, role_impl: BaseRole) -> None:
        self.roles.register(role_impl)

    def list_roles(self) -> list[str]:
        return self.roles.list()

    def get_role(self, name: str) -> BaseRole:
        return self.roles.get(name)

    def update_role(self, role_impl: BaseRole) -> None:
        self.roles.update(role_impl)

    def delete_role(self, name: str) -> None:
        self.roles.delete(name)

    # ── Registry: Models ─────────────────────────────────────────────

    def register_model(
        self,
        name: str,
        provider_name: str,
        *,
        api_key: str | None = None,
        model_id: str | None = None,
        provider_impl: LLMProvider | None = None,
        **extra: Any,
    ) -> None:
        config_extra = dict(extra)
        if provider_impl is not None:
            config_extra["provider_impl"] = provider_impl
        config = ModelConfig(
            provider_name=provider_name,
            model_id=model_id,
            api_key=api_key,
            extra=config_extra,
        )
        self.models.register(name, config)

    def list_models(self) -> list[str]:
        return self.models.list()

    def get_model(self, name: str) -> ModelConfig:
        return self.models.get(name)

    def update_model(
        self,
        name: str,
        provider_name: str,
        *,
        api_key: str | None = None,
        model_id: str | None = None,
        provider_impl: LLMProvider | None = None,
        **extra: Any,
    ) -> None:
        config_extra = dict(extra)
        if provider_impl is not None:
            config_extra["provider_impl"] = provider_impl
        config = ModelConfig(
            provider_name=provider_name,
            model_id=model_id,
            api_key=api_key,
            extra=config_extra,
        )
        self.models.update(name, config)

    def delete_model(self, name: str) -> None:
        self.models.delete(name)

    # ── Registry: Graphs ─────────────────────────────────────────────

    def register_graph(self, graph_yaml: str) -> str:
        """Parse and register a graph from YAML. Returns graph_name."""
        spec = parse_graph_yaml(graph_yaml)
        self.graphs.register(spec)
        return spec.graph_name

    def register_graph_spec(self, spec: GraphSpec) -> str:
        """Register a pre-compiled GraphSpec. Returns graph_name."""
        self.graphs.register(spec)
        return spec.graph_name

    def list_graphs(self) -> list[str]:
        return self.graphs.list()

    def get_graph(self, name: str) -> GraphSpec:
        return self.graphs.get(name)

    def update_graph(self, graph_yaml: str) -> str:
        spec = parse_graph_yaml(graph_yaml)
        self.graphs.update(spec)
        return spec.graph_name

    def delete_graph(self, name: str) -> None:
        self.graphs.delete(name)

    # ── Registry: Agents ─────────────────────────────────────────────

    def register_agent(self, agent_def: AgentDef) -> str:
        """Register an agent definition. Returns agent_id (UUID)."""
        return self.agents.register(agent_def)

    def list_agents(self) -> list[tuple[str, AgentDef]]:
        return self.agents.list()

    def get_agent(self, agent_id: str) -> AgentDef:
        return self.agents.get(agent_id)

    def get_agent_by_name(self, name: str) -> tuple[str, AgentDef]:
        return self.agents.get_by_name(name)

    def update_agent(self, agent_id: str, agent_def: AgentDef) -> None:
        self.agents.update(agent_id, agent_def)

    def delete_agent(self, agent_id: str) -> None:
        self.agents.delete(agent_id)

    # ── Run Execution ────────────────────────────────────────────────

    async def execute_run(
        self,
        message: Message,
        *,
        agent_id: str | None = None,
        agent_def: AgentDef | None = None,
        history: list[Message] | None = None,
        async_mode: bool = False,
        metadata: dict | None = None,
    ) -> RunResponse:
        """Execute an agent run.

        Provide either ``agent_id`` (for registered agents) or ``agent_def``
        (for ad-hoc / test runs).

        ``metadata`` is an opaque dict passed through to ``ExecutionContext``
        so that host-app code (tools, roles) can access app-specific data
        like ``project_id``, ``db_session``, etc.
        """
        # Resolve agent definition
        resolved_def = self._resolve_agent_def(agent_id, agent_def)

        # Resolve graph
        graph = self.graphs.get(resolved_def.graph_name)

        if async_mode:
            return await self._execute_async(
                resolved_def, graph, message, history, metadata
            )

        return await self._orchestrator.run(
            agent_def=resolved_def,
            graph=graph,
            message=message,
            history=history,
            metadata=metadata,
        )

    async def execute_run_by_name(
        self,
        name: str,
        message: Message,
        *,
        history: list[Message] | None = None,
        async_mode: bool = False,
        metadata: dict | None = None,
    ) -> RunResponse:
        """Execute a run by agent name (convenience method)."""
        agent_id, _ = self.agents.get_by_name(name)
        return await self.execute_run(
            message=message,
            agent_id=agent_id,
            history=history,
            async_mode=async_mode,
            metadata=metadata,
        )

    async def _execute_async(
        self,
        agent_def: AgentDef,
        graph: GraphSpec,
        message: Message,
        history: list[Message] | None,
        metadata: dict | None = None,
    ) -> RunResponse:
        """Start an async run and return immediately with the run_id."""
        # Create a placeholder run record
        run = RunRecord(
            status=RunStatus.QUEUED,
            agent_name=agent_def.name,
            graph_name=graph.graph_name,
            input_message=message,
            history=list(history) if history else [],
            metadata=metadata or {},
        )
        await self._store.save_run(run)

        # Launch task
        task = asyncio.create_task(
            self._orchestrator.run(
                agent_def=agent_def,
                graph=graph,
                message=message,
                history=history,
                metadata=metadata,
            )
        )
        self._async_tasks[run.run_id] = task

        return RunResponse(
            run_id=run.run_id,
            completed=False,
        )

    # ── Run Status / Polling ─────────────────────────────────────────

    async def get_run_status(self, run_id: str) -> RunRecord | None:
        return await self._store.get_run(run_id)

    async def wait_response(self, run_id: str) -> RunResponse:
        """Wait for an async run to complete and return the response."""
        task = self._async_tasks.get(run_id)
        if task is not None:
            return await task

        # Run may have already completed — check store
        run = await self._store.get_run(run_id)
        if run is None:
            from .errors import RunNotFoundError

            raise RunNotFoundError(run_id)

        return RunResponse(
            run_id=run.run_id,
            completed=run.status == RunStatus.COMPLETED,
            message=run.output_message,
        )

    # ── Approval ─────────────────────────────────────────────────────

    async def resume_run(self, run_id: str) -> RunResponse:
        """Resume a suspended run by resolving agent_def + graph and calling orchestrator.resume()."""
        run = await self._store.get_run(run_id)
        if run is None:
            from .errors import RunNotFoundError
            raise RunNotFoundError(run_id)

        agent_def = self._resolve_agent_def_from_run(run)
        graph = self.graphs.get(run.graph_name)
        return await self._orchestrator.resume(run_id, agent_def, graph)

    async def approval_request(
        self,
        run_id: str,
        decisions: list[ApprovalDecision],
    ) -> RunResponse:
        """Resolve pending approvals and resume the run."""
        events = await self._approval_mgr.resolve(run_id, decisions)

        # Check if run can be resumed
        run = await self._store.get_run(run_id)
        if run is None:
            from .errors import RunNotFoundError
            raise RunNotFoundError(run_id)

        if run.status == RunStatus.RUNNING:
            return await self.resume_run(run_id)

        return RunResponse(
            run_id=run.run_id,
            completed=run.status == RunStatus.COMPLETED,
            message=run.output_message,
        )

    # ── Delegation ───────────────────────────────────────────────────

    async def delegate_task(
        self,
        parent_run_id: str,
        child_agent_name: str,
        task: str,
        *,
        timeout_sec: int | None = None,
    ) -> DelegationResult:
        """Delegate a task to a child agent and wait for the result."""
        # Resolve child agent
        child_agent_id, child_def = self.agents.get_by_name(child_agent_name)
        child_graph = self.graphs.get(child_def.graph_name)

        # Get parent run for context
        parent_run = await self._store.get_run(parent_run_id)
        step_id = parent_run.current_step_id if parent_run else ""

        # Create delegation request
        delegation_req = await self._delegation_mgr.delegate(
            parent_run_id=parent_run_id,
            child_agent_name=child_agent_name,
            task=task,
            step_id=step_id or "",
            timeout_sec=timeout_sec,
        )

        # Execute child run
        from .models.common import MessageRole

        child_message = Message(role=MessageRole.USER, content=task)
        try:
            child_response = await self._orchestrator.run(
                agent_def=child_def,
                graph=child_graph,
                message=child_message,
            )

            status = (
                DelegationResultStatus.COMPLETED
                if child_response.completed
                else DelegationResultStatus.FAILED
            )
            result = await self._delegation_mgr.complete_delegation(
                delegation_id=delegation_req.id,
                child_run_id=child_response.run_id,
                status=status,
                output_message=child_response.message,
            )
        except Exception as exc:
            result = await self._delegation_mgr.complete_delegation(
                delegation_id=delegation_req.id,
                child_run_id="",
                status=DelegationResultStatus.FAILED,
                error=str(exc),
            )

        return result

    # ── Helpers ───────────────────────────────────────────────────────

    def _resolve_agent_def(
        self,
        agent_id: str | None,
        agent_def: AgentDef | None,
    ) -> AgentDef:
        if agent_def is not None:
            return agent_def
        if agent_id is not None:
            return self.agents.get(agent_id)
        raise ValueError("Either agent_id or agent_def must be provided")

    def _resolve_agent_def_from_run(self, run: RunRecord) -> AgentDef:
        """Resolve AgentDef from a RunRecord by looking up by name."""
        try:
            _, agent_def = self.agents.get_by_name(run.agent_name)
            return agent_def
        except RegistryKeyError:
            raise AgentNotFoundError(
                f"Agent '{run.agent_name}' not found for run '{run.run_id}'"
            )
