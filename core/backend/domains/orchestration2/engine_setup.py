"""Engine setup — bootstraps an AgentEngine per request.

This is VisionArk-specific glue code (NOT part of orchestration2 core).
It registers tools, skills, roles, models, graphs, and agents for a given
project context.

Refactored to delegate to:
- domains/orchestration2/bootstrap/project_engine_builder.py
"""

from __future__ import annotations

# Re-export creation function to maintain API compatibility
from .bootstrap.project_engine_builder import create_engine_for_project

# Re-export definitions (though better to import from config/skills/default_skills)
from .config.skills.default_skills import SKILL_DEFS, ALL_SKILL_NAMES
