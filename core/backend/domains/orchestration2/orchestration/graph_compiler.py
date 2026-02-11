"""Parse YAML graph definitions, validate, and compile into GraphSpec."""

from __future__ import annotations

import logging
import re
from typing import Any

import yaml

from ..errors import GraphValidationError
from ..models.graph_spec import GraphSpec, GraphStep, StepTransition

logger = logging.getLogger(__name__)

# Valid step types
_VALID_STEP_TYPES = {"role", "skill", "approval", "delegation", "responder"}

# Pattern for when clauses: event.type == 'value' or default
_WHEN_EVENT_PATTERN = re.compile(
    r"^event\.(\w+)\s*==\s*['\"]([^'\"]+)['\"]$"
)
_WHEN_DEFAULT = "default"


def parse_graph_yaml(yaml_str: str) -> GraphSpec:
    """Parse a YAML string into a GraphSpec, validating along the way."""
    try:
        data = yaml.safe_load(yaml_str)
    except yaml.YAMLError as exc:
        raise GraphValidationError(f"Invalid YAML: {exc}") from exc

    if not isinstance(data, dict):
        raise GraphValidationError("Graph YAML must be a mapping")

    return _validate_and_compile(data)


def compile_graph(data: dict[str, Any]) -> GraphSpec:
    """Compile a dict (already parsed from YAML) into a validated GraphSpec."""
    return _validate_and_compile(data)


def _validate_and_compile(data: dict[str, Any]) -> GraphSpec:
    """Validate raw data and produce a GraphSpec."""
    # Basic required fields
    if "graph_name" not in data:
        raise GraphValidationError("Missing required field: graph_name")
    if "start" not in data:
        raise GraphValidationError("Missing required field: start")
    if "steps" not in data or not data["steps"]:
        raise GraphValidationError("Graph must have at least one step")

    # Parse steps
    steps: list[GraphStep] = []
    step_ids: set[str] = set()

    for raw_step in data["steps"]:
        if not isinstance(raw_step, dict):
            raise GraphValidationError(f"Each step must be a mapping, got: {type(raw_step)}")
        if "id" not in raw_step:
            raise GraphValidationError("Each step must have an 'id' field")
        if "type" not in raw_step:
            raise GraphValidationError(f"Step '{raw_step['id']}' must have a 'type' field")

        step_type = raw_step["type"]
        if step_type not in _VALID_STEP_TYPES:
            raise GraphValidationError(
                f"Step '{raw_step['id']}' has invalid type '{step_type}'. "
                f"Must be one of: {_VALID_STEP_TYPES}"
            )

        step_id = raw_step["id"]
        if step_id in step_ids:
            raise GraphValidationError(f"Duplicate step id: '{step_id}'")
        step_ids.add(step_id)

        step = GraphStep.model_validate(raw_step)
        steps.append(step)

    # Validate start points to existing step
    start = data["start"]
    if start not in step_ids:
        raise GraphValidationError(
            f"'start' references non-existent step: '{start}'"
        )

    # Validate all next references
    for step in steps:
        _validate_transitions(step, step_ids)

    # Validate at least one terminal step
    terminal_steps = [s for s in steps if s.terminal]
    if not terminal_steps:
        raise GraphValidationError(
            "Graph must have at least one terminal step"
        )

    # Warn on cycles without limits
    _warn_cycles_without_limits(steps, start)

    return GraphSpec(
        version=data.get("version", 1),
        graph_name=data["graph_name"],
        start=start,
        steps=steps,
    )


def _validate_transitions(step: GraphStep, step_ids: set[str]) -> None:
    """Validate transition 'when' clauses and 'next' references."""
    default_count = 0

    for transition in step.on:
        # Validate next points to existing step
        if transition.next not in step_ids:
            raise GraphValidationError(
                f"Step '{step.id}' transition references "
                f"non-existent step: '{transition.next}'"
            )

        # Validate when clause syntax
        when = transition.when.strip()
        if when == _WHEN_DEFAULT:
            default_count += 1
            if default_count > 1:
                raise GraphValidationError(
                    f"Step '{step.id}' has multiple 'default' transitions"
                )
        elif not _WHEN_EVENT_PATTERN.match(when):
            raise GraphValidationError(
                f"Step '{step.id}' has invalid 'when' expression: '{when}'. "
                f"Expected: event.<field> == '<value>' or 'default'"
            )


def _warn_cycles_without_limits(steps: list[GraphStep], start: str) -> None:
    """Warn if there are cycles in steps that have no limits set."""
    step_map = {s.id: s for s in steps}
    visited: set[str] = set()
    in_stack: set[str] = set()

    def dfs(step_id: str) -> None:
        if step_id in in_stack:
            step = step_map.get(step_id)
            if step and step.limits.max_turns is None and step.limits.max_tool_calls is None:
                logger.warning(
                    "Cycle detected at step '%s' with no limits set. "
                    "Consider adding max_turns or max_tool_calls.",
                    step_id,
                )
            return
        if step_id in visited:
            return
        visited.add(step_id)
        in_stack.add(step_id)

        step = step_map.get(step_id)
        if step:
            for transition in step.on:
                dfs(transition.next)

        in_stack.discard(step_id)

    dfs(start)


def evaluate_when(when: str, event: Any) -> bool:
    """Evaluate a 'when' clause against an OrchestrationEvent.

    Supports:
    - "default" -> always True
    - "event.<field> == '<value>'" -> field comparison
    """
    when = when.strip()
    if when == _WHEN_DEFAULT:
        return True

    match = _WHEN_EVENT_PATTERN.match(when)
    if not match:
        return False

    field_name = match.group(1)
    expected_value = match.group(2)

    actual_value = getattr(event, field_name, None)
    if actual_value is None:
        return False

    # Handle enum values
    actual_str = actual_value.value if hasattr(actual_value, "value") else str(actual_value)
    return actual_str == expected_value
