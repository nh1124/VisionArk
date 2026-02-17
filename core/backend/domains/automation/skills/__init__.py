from .registry import skill_registry

async def init_skills():
    """Initialize skills from file system."""
    await skill_registry.sync_skills()

