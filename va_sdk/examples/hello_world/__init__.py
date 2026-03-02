"""Hello World module — entry point for the example module.

Demonstrates:
  - Relative imports from sibling files (.tools, .skills)
  - Exposing get_tools() and get_skill_defs() for VisionArk registration
"""

from .tools import EchoTool, ReverseTextTool
from .skills import SKILL_DEFS


def get_tools(user_id: str, db):
    return [EchoTool(), ReverseTextTool()]


def get_skill_defs():
    return SKILL_DEFS
