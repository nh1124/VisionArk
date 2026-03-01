"""Native device & job agent tools for VisionArk.

Provides tools for agents to interact with the user's native devices
(desktops, servers, mobiles) via the job routing system.

Usage
-----
Call get_tools(user_id, db) to obtain tool instances ready for use
in the orchestration engine.
"""
from .agent_tools import ListNativeDevicesTool, RunNativeJobTool


async def get_tools(user_id: str, db):
    """Return native device/job tools — always available (no activation check required)."""
    return [
        ListNativeDevicesTool(),
        RunNativeJobTool(),
    ]


__all__ = [
    "ListNativeDevicesTool",
    "RunNativeJobTool",
    "get_tools",
]
