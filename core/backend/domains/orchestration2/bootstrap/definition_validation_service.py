"""Definition validation service.

Validates uploaded Python tool code before it is saved to disk or registered
in the DB.  All checks are synchronous and run before any file I/O.

Validation stages:
  1. Syntax check  — ast.parse() must succeed
  2. Contract check — module must define a top-level get_tools() function
  3. Security scan  — block dangerous imports and builtins

The security scan is not a full sandbox.  It is a best-effort guard against
obviously malicious patterns.  Code runs in-process, so it is not untrusted.
"""
from __future__ import annotations

import ast
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Blocked imports
# ---------------------------------------------------------------------------

# Module names (or top-level packages) that are unconditionally blocked.
_BLOCKED_MODULES: frozenset[str] = frozenset(
    {
        "subprocess",
        "pty",
        "multiprocessing",
        "ctypes",
        "cffi",
        "resource",
        "signal",
        "socket",        # direct socket use — integrations should use httpx/aiohttp
        "SocketServer",
        "socketserver",
    }
)

# Specific imports that are blocked even when the top-level package is allowed.
# Format: "module.attr"
_BLOCKED_FROM_IMPORTS: frozenset[str] = frozenset(
    {
        "os.system",
        "os.popen",
        "os.execv",
        "os.execve",
        "os.execvp",
        "os.execvpe",
        "os.fork",
        "os.forkpty",
        "os.spawn",
        "os.spawnl",
        "os.spawnle",
        "os.spawnlp",
        "os.spawnlpe",
        "os.spawnv",
        "os.spawnve",
        "os.spawnvp",
        "os.spawnvpe",
    }
)

# Built-in call names that are blocked (detected via Call(func=Name(id=...)) AST).
_BLOCKED_CALLS: frozenset[str] = frozenset({"exec", "eval", "compile", "__import__"})


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    ok: bool
    error: str | None = None

    @classmethod
    def success(cls) -> "ValidationResult":
        return cls(ok=True)

    @classmethod
    def fail(cls, reason: str) -> "ValidationResult":
        return cls(ok=False, error=reason)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def validate_module_files(
    files: dict[str, str], module_name: str = "<module>"
) -> ValidationResult:
    """Validate all files in a multi-file module upload.

    Rules:
      - __init__.py must be present (entry point)
      - All .py files: syntax check + security scan
      - __init__.py only: contract check (get_tools or get_skill_defs)
      - Filenames must be safe (no path traversal, alphanumeric/underscore/dot)
    """
    import re as _re
    _SAFE_FILENAME = _re.compile(r"^[a-zA-Z0-9_][a-zA-Z0-9_.]*\.py$")

    if "__init__.py" not in files:
        return ValidationResult.fail(
            "Module must contain __init__.py as the entry point"
        )

    for filename, content in files.items():
        if not filename.endswith(".py"):
            continue  # non-py files are not validated (future: allow .json/.yaml etc.)

        if not _SAFE_FILENAME.match(filename):
            return ValidationResult.fail(
                f"Unsafe filename: '{filename}'. "
                "Filenames must be alphanumeric/underscore/dot and end with .py"
            )

        # Syntax check
        try:
            tree = ast.parse(content, filename=filename)
        except SyntaxError as exc:
            return ValidationResult.fail(
                f"[{filename}] Syntax error at line {exc.lineno}: {exc.msg}"
            )

        # Security scan on every .py file
        sec = _check_security(tree)
        if not sec.ok:
            return ValidationResult.fail(f"[{filename}] {sec.error}")

        # Contract check only for __init__.py
        if filename == "__init__.py":
            contract = _check_contract(tree)
            if not contract.ok:
                return ValidationResult.fail(f"[__init__.py] {contract.error}")

    return ValidationResult.success()


def validate_tool_code(code: str, tool_name: str = "<upload>") -> ValidationResult:
    """Validate uploaded Python code for a tool module.

    Returns ValidationResult with ok=True on success, or ok=False and a
    human-readable error string describing the first failure encountered.
    """
    # --- Stage 1: Syntax ---
    try:
        tree = ast.parse(code, filename=tool_name)
    except SyntaxError as exc:
        return ValidationResult.fail(f"Syntax error at line {exc.lineno}: {exc.msg}")

    # --- Stage 2: Contract ---
    contract_result = _check_contract(tree)
    if not contract_result.ok:
        return contract_result

    # --- Stage 3: Security ---
    security_result = _check_security(tree)
    if not security_result.ok:
        return security_result

    return ValidationResult.success()


# ---------------------------------------------------------------------------
# Stage implementations
# ---------------------------------------------------------------------------


def _check_contract(tree: ast.Module) -> ValidationResult:
    """Verify that the module defines at least one of get_tools() or get_skill_defs().

    A module may define both (full integration-style package) or just one:
      - get_tools(user_id, db) -> list[BaseTool]   — tool-only module
      - get_skill_defs() -> list[SkillDef]          — skill-only module
      - both                                         — full integration package
    """
    has_get_tools = False
    has_get_skill_defs = False
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "get_tools":
                has_get_tools = True
            elif node.name == "get_skill_defs":
                has_get_skill_defs = True
    if not has_get_tools and not has_get_skill_defs:
        return ValidationResult.fail(
            "Module must define at least one of:\n"
            "  get_tools(user_id, db) -> list[BaseTool]\n"
            "  get_skill_defs() -> list[SkillDef]"
        )
    return ValidationResult.success()


def _check_security(tree: ast.Module) -> ValidationResult:
    """Scan AST for dangerous import and call patterns."""
    for node in ast.walk(tree):
        # Plain imports: import subprocess, import socket, ...
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in _BLOCKED_MODULES:
                    return ValidationResult.fail(
                        f"Blocked import: '{alias.name}' is not allowed in uploaded tools"
                    )

        # From imports: from os import system, from subprocess import ...
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            top = module.split(".")[0]
            if top in _BLOCKED_MODULES:
                return ValidationResult.fail(
                    f"Blocked import: 'from {module} import ...' is not allowed"
                )
            # Check specific "module.attr" combos
            for alias in node.names:
                qualified = f"{module}.{alias.name}"
                if qualified in _BLOCKED_FROM_IMPORTS:
                    return ValidationResult.fail(
                        f"Blocked import: '{qualified}' is not allowed in uploaded tools"
                    )
            # Block importing everything with the wildcard from blocked modules
            if any(alias.name == "*" for alias in node.names) and top in _BLOCKED_MODULES:
                return ValidationResult.fail(
                    f"Blocked import: 'from {module} import *' is not allowed"
                )

        # Direct calls to exec/eval/compile/__import__
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in _BLOCKED_CALLS:
                return ValidationResult.fail(
                    f"Blocked built-in call: '{node.func.id}()' is not allowed in uploaded tools"
                )

    return ValidationResult.success()
