from ..engine.models.skill import SkillDef
from ..engine.models.message import Message
from ..engine.models.execution import ExecutionContext, SkillResult

class NoOpSkill:
    """Minimal BaseSkill-compatible impl for tool-filtering-only skills."""

    def __init__(self, skill_def: SkillDef) -> None:
        self.definition = skill_def

    async def run(self, input_message: Message, ctx: ExecutionContext) -> SkillResult:
        raise NotImplementedError("This skill is used for tool filtering only")
