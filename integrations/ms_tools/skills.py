"""Skill definitions for the MS Office integration.

These are NOT loaded by default_skills.py.
They are declared here so that, when tool_reflection is extended to support
per-integration skill registration, it can call get_skill_defs() on each
integration package and dynamically register these alongside core skills.

Usage (future tool_reflection extension):
    from integrations.ms_tools.skills import SKILL_DEFS
    # or via the standard interface:
    from integrations.ms_tools import get_skill_defs
    skill_defs = get_skill_defs()
"""
from domains.orchestration2.engine.models.skill import SkillDef

SKILL_DEFS: list[SkillDef] = [
    SkillDef(
        name="ms_office",
        description="Create and edit Microsoft Office files (Word, Excel, PowerPoint)",
        tools=[
            "word_tool",
            "excel_tool",
            "ppt_tool",
            "ms_auth_manager",
        ],
    ),
]
