
# ==============================================================================
# Tool Definitions (JSON Schemas)
# ==============================================================================

# Common tools available to most agents
_COMMON_TOOLS = [
    {
        "name": "ask_node",
        "description": "Send a message/question to another Project or the Hub. Use this to coordinate or request info.",
        "parameters": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "The name of the target project (e.g., 'hub', 'research-alpha')"},
                "message": {"type": "string", "description": "The content of the message"}
            },
            "required": ["target", "message"]
        }
    },
    {
        "name": "save_artifact",
        "description": "Save content to a file in the project's artifacts directory.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Relative path (e.g., 'plans/v1.md')"},
                "content": {"type": "string", "description": "File content"},
                "overwrite": {"type": "boolean", "description": "Overwrite if exists"}
            },
            "required": ["file_path", "content"]
        }
    },
    {
        "name": "read_reference",
        "description": "Read a file from the project's storage (refs, files, artifacts).",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Relative path to file"}
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "list_files",
        "description": "List files in a subdirectory.",
        "parameters": {
            "type": "object",
            "properties": {
                "sub_dir": {"type": "string", "description": "Subdirectory name (default 'refs')"}
            }
        }
    },
    {
         "name": "search_knowledge",
         "description": "Search the knowledge base (Rag/memories).",
         "parameters": {
             "type": "object",
             "properties": {
                 "query": {"type": "string", "description": "Search query"},
                 "limit": {"type": "integer", "description": "Max results"}
             },
             "required": ["query"]
         }
    },
     {
         "name": "ingest_knowledge",
         "description": "Save a piece of knowledge/memory to the Knowledge Core.",
         "parameters": {
             "type": "object",
             "properties": {
                 "content": {"type": "string", "description": "The fact/info to save"},
                 "label": {"type": "string", "description": "Optional label/topic"}
             },
             "required": ["content"]
         }
    }
]

# Project (General) Agent Tools
PROJECT_TOOL_DEFINITIONS = [
    *_COMMON_TOOLS,
    {
        "name": "delegate_to_member",
        "description": "Delegate a task to a specialized member agent (Planner, Researcher, Ruler, Advocate).",
        "parameters": {
            "type": "object",
            "properties": {
                "role": {"type": "string", "enum": ["planner", "researcher", "ruler", "advocate"]},
                "instruction": {"type": "string", "description": "Task instructions"}
            },
            "required": ["role", "instruction"]
        }
    },
    {
        "name": "report_to_hub",
        "description": "Send a summary update or request to the Hub (Root Project).",
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Progress summary"},
                "request": {"type": "string", "description": "Optional request/blocker"}
            },
            "required": ["summary"]
        }
    },
    {
        "name": "create_task",
        "description": "Create a task in the LBS system.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_name": {"type": "string"},
                "workload": {"type": "number", "description": "Estimated load (1-10)"},
                "rule_type": {"type": "string", "enum": ["ONCE", "WEEKLY", "EVERY_N_DAYS", "MONTHLY_DAY"]},
                "due_date": {"type": "string", "description": "YYYY-MM-DD for ONCE"},
                "days": {"type": "string", "description": "Comma-sep days for WEEKLY (mon,tue...)"},
                "notes": {"type": "string"}
            },
            "required": ["task_name", "workload"]
        }
    },
    {
        "name": "list_tasks",
        "description": "List active tasks.",
        "parameters": {
            "type": "object",
            "properties": {
                "context": {"type": "string", "description": "Filter by context/project"}
            }
        }
    },
    {
        "name": "update_task_details",
        "description": "Update a task.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "workload": {"type": "number"},
                "notes": {"type": "string"}
            },
            "required": ["task_id"]
        }
    },
     {
        "name": "complete_lbs_task",
        "description": "Mark a task as complete.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "target_date": {"type": "string", "description": "YYYY-MM-DD"},
                "status": {"type": "string", "default": "done"}
            },
            "required": ["task_id", "target_date"]
        }
    },
    {
        "name": "generate_image",
        "description": "Generate an image path from a prompt.",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "filename": {"type": "string"}
            },
            "required": ["prompt"]
        }
    },
     {
        "name": "google_search",
        "description": "Search Google for information.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"}
            },
            "required": ["query"]
        }
    }
]

# Planner Agent Tools
PLANNER_TOOL_DEFINITIONS = [
    *_COMMON_TOOLS,
    {
        "name": "init_plan",
        "description": "Initialize a new plan.",
        "parameters": {
            "type": "object",
            "properties": {
                 "goal": {"type": "string"},
                 "strategy": {"type": "string"}
            },
             "required": ["goal", "strategy"]
        }
    },
     {
        "name": "update_plan_progress",
        "description": "Log progress to the plan.",
        "parameters": {
            "type": "object",
            "properties": {
                 "summary": {"type": "string"}
            },
             "required": ["summary"]
        }
    },
     {
        "name": "get_current_status",
        "description": "Get current plan status.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "generate_mermaid_visualizer",
        "description": "Generate a Mermaid diagram.",
        "parameters": {
            "type": "object",
            "properties": {
                "data": {"type": "string", "description": "Data to visualize"},
                "diagram_type": {"type": "string", "enum": ["gantt", "flowchart", "sequence", "class"]},
                "title": {"type": "string"}
            },
            "required": ["data", "diagram_type"]
        }
    }
]

# Researcher Agent Tools
RESEARCHER_TOOL_DEFINITIONS = [
    *_COMMON_TOOLS,
    {
        "name": "google_search",
        "description": "Search Google.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"]
        }
    },
    {
        "name": "research_url",
        "description": "Deeply research specific URLs.",
        "parameters": {
             "type": "object",
             "properties": {
                 "urls": {"type": "array", "items": {"type": "string"}},
                 "query": {"type": "string"}
             },
             "required": ["urls", "query"]
        }
    },
    {
        "name": "search_places",
        "description": "Search Google Maps/Places.",
        "parameters": {
             "type": "object",
             "properties": {"query": {"type": "string"}},
             "required": ["query"]
        }
    }
]

# Ruler Agent Tools (LBS/Schedule focused)
RULER_TOOL_DEFINITIONS = [
    *_COMMON_TOOLS,
    {
        "name": "create_task",
        "description": "Create LBS task.",
        "parameters": PROJECT_TOOL_DEFINITIONS[2]["parameters"] # Reuse
    },
    {
         "name": "get_lbs_schedule",
         "description": "Get schedule for a period.",
         "parameters": {
             "type": "object",
             "properties": {
                 "start_date": {"type": "string"},
                 "end_date": {"type": "string"}
             },
             "required": ["start_date", "end_date"]
         }
    },
     {
         "name": "get_load_on_day",
         "description": "Calculate load score for a day.",
         "parameters": {
             "type": "object",
             "properties": {"target_date": {"type": "string"}},
             "required": ["target_date"]
         }
    },
    {
        "name": "run_cleanup_cycle",
        "description": "Run LBS cleanup.",
        "parameters": {"type": "object", "properties": {}}
    }
]

# Advocate Agent Tools (User/Condition focused)
ADVOCATE_TOOL_DEFINITIONS = [
    *_COMMON_TOOLS,
    {
        "name": "get_current_condition",
        "description": "Get user's current condition.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "update_user_condition",
        "description": "Update user condition metrics.",
        "parameters": {
            "type": "object",
            "properties": {
                "physical": {"type": "integer"},
                "mental": {"type": "integer"},
                "notes": {"type": "string"}
            }
        }
    }
]
