"""Hello World skills — example SkillDef definitions."""

from domains.orchestration2.engine.models.skill import SkillDef

SKILL_DEFS = [
    SkillDef(
        name="hello_world",
        description="Example skill grouping the hello_echo and hello_reverse tools.",
        tools=["hello_echo", "hello_reverse"],
    )
]
