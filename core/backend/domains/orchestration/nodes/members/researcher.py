from typing import Any, Dict, Optional
from domains.orchestration.nodes.members.generic_member_node import GenericMemberNode

class ResearcherNode(GenericMemberNode):
    """
    The Investigator.
    Focus: External knowledge and Search.
    """
    role_name = "researcher"
    display_name = "Researcher"
    description = "External information gathering and deep investigation."
    default_tools = [
        "google_search",
        "deep_research",
        "research_url",
        "search_places",
        "save_artifact",
        "read_reference",
        "list_files",
        "import_github_repo",
        "search_knowledge",
        "ingest_knowledge",
        "update_node_description"
    ]
    
    def __init__(self, context: Dict[str, Any], node: Any, status_callback: Optional[Any] = None):
        super().__init__(context, node, status_callback)

    async def on_exit(self, result: Any):
        pass
