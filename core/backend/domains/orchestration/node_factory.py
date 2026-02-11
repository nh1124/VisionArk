from typing import Any, Dict, Optional, Type
from shared.database import Node

class NodeFactory:
    """Centralized factory to instantiate nodes based on type and role."""

    @staticmethod
    def get_node(node_record: Node, context: Dict[str, Any], status_callback: Optional[Any] = None) -> Any:
        """
        Instantiates a node based on its type.
        
        Args:
            node_record: The database record for the node.
            context: The execution context (db_session, user_id, etc.)
            status_callback: Optional callback for UI updates.
        """
        node_type = node_record.node_type
        
        if node_type == "SYSTEM":
            from domains.orchestration.system_node_registry import SystemNodeRegistry
            NodeClass = SystemNodeRegistry.get_node_class(node_record.role_name)
            return NodeClass(context, node_record)
            
        elif node_type == "PROJECT":
            from domains.orchestration.nodes.project.project_node import ProjectNode
            return ProjectNode(context, status_callback=status_callback)
            
        elif node_type == "MEMBER":
            # Specialized member check
            if node_record.role_name == "advocate":
                from domains.orchestration.nodes.members.advocate import AdvocateNode
                return AdvocateNode(context, node_record, status_callback=status_callback)
            elif node_record.role_name == "planner":
                from domains.orchestration.nodes.members.planner import PlannerNode
                return PlannerNode(context, node_record, status_callback=status_callback)
            elif node_record.role_name == "ruler":
                from domains.orchestration.nodes.members.ruler import RulerNode
                return RulerNode(context, node_record, status_callback=status_callback)
            
            # Fallback to generic member
            from domains.orchestration.nodes.members.generic_member_node import GenericMemberNode
            return GenericMemberNode(context, node_record)
            
        else:
            raise ValueError(f"Unsupported node type: {node_type}")
