
import asyncio
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).parent))

from tools.agent_tools import (
    query_md_elements,
    upsert_md_table,
    generate_mermaid_visualizer,
    compare_md_sections,
    save_artifact
)

async def test_tools():
    user_id = "test_user"
    node_type = "SPOKE"
    spoke_name = "test_spoke"
    
    # Setup test file
    test_file = "test_artifact.md"
    content = """# Section 1
| ID | Name | Status |
|---|---|---|
| 1 | Task A | Done |
| 2 | Task B | Todo |

# Section 2
- Item 1
- Item 2
- [ ] Task 1
- [x] Task 2
"""
    print("--- Testing save_artifact ---")
    await save_artifact(test_file, content, overwrite=True, user_id=user_id, node_type=node_type, spoke_name=spoke_name)

    print("\n--- Testing query_md_elements (table) ---")
    res = await query_md_elements(test_file, "table", user_id=user_id, node_type=node_type, spoke_name=spoke_name)
    print(res.message)

    print("\n--- Testing query_md_elements (checkbox) ---")
    res = await query_md_elements(test_file, "checkbox", user_id=user_id, node_type=node_type, spoke_name=spoke_name)
    print(res.message)

    print("\n--- Testing upsert_md_table (update row) ---")
    res = await upsert_md_table(test_file, "Section 1", "ID", {"ID": "2", "Status": "Done"}, user_id=user_id, node_type=node_type, spoke_name=spoke_name)
    print(res.message)

    print("\n--- Testing upsert_md_table (new row) ---")
    res = await upsert_md_table(test_file, "Section 1", "ID", {"ID": "3", "Name": "Task C", "Status": "Todo"}, user_id=user_id, node_type=node_type, spoke_name=spoke_name)
    print(res.message)

    print("\n--- Testing generate_mermaid_visualizer ---")
    data = {"Project A": ["Task 1", "Task 2"], "Project B": ["Task 3"]}
    res = await generate_mermaid_visualizer(data, "mindmap", "My Projects", user_id=user_id, node_type=node_type, spoke_name=spoke_name)
    print(res.message)

    print("\n--- Testing compare_md_sections ---")
    source = {"file_path": test_file, "section_title": "Section 1"}
    target = {"file_path": test_file, "section_title": "Section 1"} # Compare with itself for now
    res = await compare_md_sections(source, target, user_id=user_id, node_type=node_type, spoke_name=spoke_name)
    print(res.message)

if __name__ == "__main__":
    asyncio.run(test_tools())
