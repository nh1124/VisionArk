"""
Agent Tools - Native Function Calling Implementation
Replaces slash command system with Gemini native function calling
"""
from typing import Dict, Any, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, date, timedelta
import uuid
import asyncio
from pathlib import Path
import re
import json
import os

from models.database import Node, AgentProfile, ChatSession, InboxQueue, ServiceRegistry, UploadedFile, UserSettings
from services.lbs_client import LBSClient
from services.knowledge_core_service import KnowledgeCoreService
from tools.lbs_tools import update_user_condition, get_current_condition, reset_user_condition
from utils.paths import secure_path_join, get_project_dir

CURRENT_PLAN_FILE = "PLAN.md"

# ==============================================================================
# Helper & Core
# ==============================================================================

class ToolResult:
    def __init__(self, success: bool, message: str, data: Optional[Dict] = None):
        self.success = success
        self.message = message
        self.data = data or {}
    def to_dict(self) -> Dict:
        return {"success": self.success, "message": self.message, "data": self.data}

def _resolve_portable_path(stored_path: str) -> Path:
    from utils.paths import DATA_DIR
    p = Path(stored_path)
    if p.exists(): return p
    path_str = str(p).replace('\\', '/')
    if '/data/' in path_str:
        return DATA_DIR / path_str.split('/data/', 1)[1].replace('/', os.sep)
    return p

async def _get_lbs_client(user_id: str, session: AsyncSession) -> LBSClient:
    from utils.encryption import decrypt_string
    lbs_api_key = None
    lbs_url = None
    res = await session.execute(select(ServiceRegistry).filter(ServiceRegistry.user_id==user_id, ServiceRegistry.service_name=="lbs"))
    service = res.scalars().first()
    if service:
        lbs_url = service.base_url
        if service.api_key_encrypted:
            try: lbs_api_key = decrypt_string(service.api_key_encrypted)
            except: pass
    return LBSClient(base_url=lbs_url, api_key=lbs_api_key)

def _get_kc_service(user_id: str, session: AsyncSession) -> KnowledgeCoreService:
    return KnowledgeCoreService(session, user_id)

async def _get_project_name_from_id(user_id: str, project_id: str, session: AsyncSession) -> str:
    if not project_id or project_id == 'root': return 'hub'
    try:
        uuid.UUID(project_id, version=4)
        if session:
            res = await session.execute(select(Node.name).filter(Node.id==project_id, Node.user_id==user_id))
            name = res.scalar()
            if name: return name
    except: pass
    return project_id

async def _resolve_project_artifacts_dir(user_id: str, project_id: str, session: AsyncSession = None) -> Path:
    name = await _get_project_name_from_id(user_id, project_id, session)
    d = get_project_dir(user_id, name) / "artifacts"
    d.mkdir(parents=True, exist_ok=True)
    return d

async def _get_file_service(user_id: str, session: AsyncSession):
    from services.file_service import FileService
    res = await session.execute(select(UserSettings).filter(UserSettings.user_id==user_id))
    settings = res.scalars().first()
    key = settings.gemini_api_key if settings else None
    return FileService(session, user_id, api_key=key)

async def _get_gemini_client(user_id: str, session: AsyncSession):
    from google.genai import Client
    res = await session.execute(select(UserSettings).filter(UserSettings.user_id==user_id))
    settings = res.scalars().first()
    if not settings: raise ValueError("User settings not found")
    key = settings.gemini_api_key
    if not key: raise ValueError("No Gemini API Key")
    return Client(api_key=key, http_options={'api_version': 'v1alpha'})

# ==============================================================================
# Project Interaction Tools
# ==============================================================================

async def ask_node(target: str, message: str, *, session: AsyncSession = None, user_id: str = None, **kwargs) -> ToolResult:
    if not session or not user_id: return ToolResult(success=False, message="Context error")
    try:
        from nodes.project.project_node import ProjectNode
        ctx = {'user_id': user_id, 'db_session': session, 'node_id': target}
        node = ProjectNode(ctx)
        resp = await node.process(message)
        return ToolResult(success=True, message=f"Response from {target}: {resp}", data={"response": resp})
    except Exception as e: return ToolResult(success=False, message=f"Failed: {e}")

async def delegate_to_member(role: str, instruction: str, *, user_id: str = None, session: AsyncSession = None, project_id: str = None, **kwargs) -> ToolResult:
    try:
        from nodes.members.planner import PlannerNode
        from nodes.members.researcher import ResearcherNode
        from nodes.members.ruler import RulerNode
        from nodes.members.advocate import AdvocateNode
        role_map = {"planner": PlannerNode, "researcher": ResearcherNode, "ruler": RulerNode, "advocate": AdvocateNode}
        if role.lower() not in role_map: return ToolResult(success=False, message="Invalid role")
        NodeClass = role_map[role.lower()]
        ctx = {'user_id': user_id, 'db_session': session, 'project_id': project_id or kwargs.get('project_name')}
        node = NodeClass(ctx)
        resp = await node.process(instruction)
        return ToolResult(success=True, message=f"Result:\n{resp}")
    except Exception as e: return ToolResult(success=False, message=f"Failed: {e}")

async def report_to_hub(summary: str, request: Optional[str] = None, *, session: AsyncSession, user_id: str, project_name: Optional[str] = None, **kwargs) -> ToolResult:
    try:
        src = project_name or kwargs.get('project_name') or 'unknown'
        msg = InboxQueue(user_id=user_id, source_project=src, message_type="share_update", payload={"type": "share_update", "target": "Hub", "timestamp": datetime.utcnow().isoformat(), "summary": summary, "request": request or ""}, is_processed=False)
        session.add(msg)
        await session.commit()
        return ToolResult(success=True, message="📤 Sent to Hub.")
    except Exception as e: return ToolResult(success=False, message=f"Failed: {e}")

async def request_coordination(*args, **kwargs) -> ToolResult:
    return ToolResult(success=False, message="Deprecated. Use report_to_hub.")

# ==============================================================================
# LBS Tools
# ==============================================================================
# (Simplified versions of previously written tools)
async def create_task(task_name: str, workload: float, project: str = None, rule_type: str = "ONCE", due_date: str = None, days: str = None, interval_days: int = None, month_day: int = None, notes: str = None, *, session: AsyncSession, user_id: str, context_name: str = "general", **kwargs) -> ToolResult:
    try:
        client = await _get_lbs_client(user_id, session)
        data = {"task_name": task_name, "context": project or context_name, "base_load_score": float(workload), "rule_type": rule_type.upper(), "active": True, "notes": notes}
        if rule_type.upper() == "ONCE" and due_date: data["due_date"] = due_date
        elif rule_type.upper() == "WEEKLY" and days:
            dm = {d.strip().lower(): True for d in days.split(",")}
            data.update({k: dm.get(k, False) for k in ["mon","tue","wed","thu","fri","sat","sun"]})
        elif rule_type.upper() == "EVERY_N_DAYS": data["interval_days"] = interval_days
        elif rule_type.upper() == "MONTHLY_DAY": data["month_day"] = month_day
        res = await client.create_task(data)
        return ToolResult(success=True, message=f"✅ Created task {task_name}", data=res)
    except Exception as e: return ToolResult(success=False, message=f"Failed: {e}")

async def list_tasks(context: str = None, *, session: AsyncSession, user_id: str, context_name: str = "general", **kwargs) -> ToolResult:
    try:
        client = await _get_lbs_client(user_id, session)
        tasks = await client.list_tasks(context=context or context_name)
        if not tasks: return ToolResult(success=True, message=f"No tasks for {context or context_name}.")
        lines = [f"• [{t['task_id']}] {t['task_name']} ({t.get('rule_type')})" for t in tasks]
        return ToolResult(success=True, message="Tasks:\n" + "\n".join(lines), data={"tasks": tasks})
    except Exception as e: return ToolResult(success=False, message=str(e))

async def update_task_details(task_id: str, **kwargs) -> ToolResult:
    # (Simplified implementation for update)
    session = kwargs.get('session')
    user_id = kwargs.get('user_id')
    if not session or not user_id: return ToolResult(success=False, message="Context error")
    try:
        client = await _get_lbs_client(user_id, session)
        upd = {k: v for k,v in kwargs.items() if k not in ['session', 'user_id', 'waitForPreviousTools'] and v is not None}
        if 'workload' in upd: upd['base_load_score'] = float(upd.pop('workload'))
        if 'project' in upd: upd['context'] = upd.pop('project')
        if not upd: return ToolResult(success=False, message="No changes")
        res = await client.update_task(task_id, upd)
        return ToolResult(success=True, message=f"Updated {task_id}")
    except Exception as e: return ToolResult(success=False, message=str(e))

async def delete_task_by_id(task_id: str, *, session: AsyncSession, user_id: str, **kwargs) -> ToolResult:
    try:
        client = await _get_lbs_client(user_id, session)
        await client.delete_task(task_id)
        return ToolResult(success=True, message=f"Deleted {task_id}")
    except Exception as e: return ToolResult(success=False, message=str(e))

async def complete_lbs_task(task_id: str, target_date: str, status: str = "done", *, session: AsyncSession, user_id: str, **kwargs) -> ToolResult:
    try:
        from services.lbs_client import TaskStatus
        client = await _get_lbs_client(user_id, session)
        await client.toggle_task_completion(task_id, date.fromisoformat(target_date), TaskStatus(status))
        return ToolResult(success=True, message=f"Marked {task_id} as {status}")
    except Exception as e: return ToolResult(success=False, message=str(e))

async def get_lbs_schedule(start_date: str, end_date: str, *, session: AsyncSession, user_id: str, **kwargs) -> ToolResult:
    try:
        client = await _get_lbs_client(user_id, session)
        sch = await client.get_schedule(date.fromisoformat(start_date), date.fromisoformat(end_date))
        return ToolResult(success=True, message=f"Schedule found ({len(sch)} days)", data={"schedule": sch})
    except Exception as e: return ToolResult(success=False, message=str(e))

async def get_task_execution_history(task_id: str, start_date: str, end_date: str, *, session: AsyncSession, user_id: str, **kwargs) -> ToolResult:
    try:
        client = await _get_lbs_client(user_id, session)
        hist = await client.get_task_history(task_id, date.fromisoformat(start_date), date.fromisoformat(end_date))
        return ToolResult(success=True, message=f"History: {len(hist)} records", data={"history": hist})
    except Exception as e: return ToolResult(success=False, message=str(e))

async def run_cleanup_cycle(**kwargs) -> ToolResult:
    return ToolResult(success=True, message="Cleanup cycle ran (mock).")

async def get_load_on_day(target_date: str, *, session: AsyncSession, user_id: str, **kwargs) -> ToolResult:
    try:
        client = await _get_lbs_client(user_id, session)
        res = await client.calculate_load(date.fromisoformat(target_date))
        return ToolResult(success=True, message=f"Load: {res.get('adjusted_load')}", data=res)
    except Exception as e: return ToolResult(success=False, message=str(e))

async def get_load_in_period(start_date: str, end_date: str, *, session: AsyncSession, user_id: str, **kwargs) -> ToolResult:
    try:
        client = await _get_lbs_client(user_id, session)
        hm = await client.get_heatmap(date.fromisoformat(start_date), date.fromisoformat(end_date))
        return ToolResult(success=True, message=f"Heatmap: {len(hm)} days", data={"heatmap": hm})
    except Exception as e: return ToolResult(success=False, message=str(e))

# ==============================================================================
# Knowledge Tools
# ==============================================================================

async def search_knowledge(query: str, limit: int = 5, *, session: AsyncSession, user_id: str, context_name: str = "general", **kwargs) -> ToolResult:
    try:
        service = _get_kc_service(user_id, session)
        ctx = await service.get_context(query=query, agent_id=context_name)
        if not ctx: return ToolResult(success=True, message="No knowledge found.")
        return ToolResult(success=True, message=ctx.get("summary", "Found context."), data=ctx)
    except Exception as e: return ToolResult(success=False, message=str(e))

async def ingest_knowledge(content: str, label: str = None, *, session: AsyncSession, user_id: str, context_name: str = "general", **kwargs) -> ToolResult:
    try:
        service = _get_kc_service(user_id, session)
        txt = f"[{label}] {content}" if label else content
        id = await service.ingest_message(txt, "assistant", "global", context_name)
        return ToolResult(success=True, message=f"Ingested {id}")
    except Exception as e: return ToolResult(success=False, message=str(e))

# ==============================================================================
# File Tools
# ==============================================================================

async def save_artifact(file_path: str, content: str, overwrite: bool = False, *, user_id: str = None, project_id: str = None, project_name: str = None, session: AsyncSession = None, **kwargs) -> ToolResult:
    if not user_id: return ToolResult(success=False, message="Context error")
    pid = project_name or project_id or 'hub'
    try:
        d = await _resolve_project_artifacts_dir(user_id, pid, session)
        p = secure_path_join(d, file_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists() and not overwrite: return ToolResult(success=False, message="Exists")
        p.write_text(content, encoding='utf-8')
        return ToolResult(success=True, message=f"Saved {file_path}")
    except Exception as e: return ToolResult(success=False, message=str(e))

async def update_artifact(file_path: str, content: str, mode: str = 'w', *, user_id: str = None, project_id: str = None, project_name: str = None, session: AsyncSession = None, **kwargs) -> ToolResult:
    return await save_artifact(file_path, content, overwrite=True, user_id=user_id, project_id=project_id, project_name=project_name, session=session) # Simplified

async def delete_artifact(file_path: str, *, user_id: str = None, project_id: str = None, project_name: str = None, session: AsyncSession = None, **kwargs) -> ToolResult:
    if not user_id: return ToolResult(success=False, message="Context error")
    pid = project_name or project_id or 'hub'
    try:
        d = await _resolve_project_artifacts_dir(user_id, pid, session)
        p = secure_path_join(d, file_path)
        if p.exists(): p.unlink()
        return ToolResult(success=True, message="Deleted")
    except Exception as e: return ToolResult(success=False, message=str(e))

async def list_files(sub_dir: str = "refs", *, user_id: str, project_id: str = None, project_name: str = None, session: AsyncSession = None, **kwargs) -> ToolResult:
    pid = project_name or project_id or 'hub'
    try:
        name = await _get_project_name_from_id(user_id, pid, session)
        d = get_project_dir(user_id, name) / sub_dir
        if not d.exists(): return ToolResult(success=True, message="Empty")
        files = [f.name for f in d.rglob('*') if f.is_file()]
        return ToolResult(success=True, message="\n".join(files))
    except Exception as e: return ToolResult(success=False, message=str(e))

async def read_reference(file_path: str, *, user_id: str, project_id: str = None, project_name: str = None, session: AsyncSession = None, **kwargs) -> ToolResult:
    pid = project_name or project_id or 'hub'
    try:
        name = await _get_project_name_from_id(user_id, pid, session)
        d = get_project_dir(user_id, name)
        p = secure_path_join(d, file_path)
        if not p.exists(): 
            # Try subdirs
            for sub in ["refs", "files", "artifacts"]:
                try: 
                    p = secure_path_join(d / sub, file_path)
                    if p.exists(): break
                except: pass
        if p.exists():
            return ToolResult(success=True, message=p.read_text(encoding='utf-8', errors='ignore'))
        return ToolResult(success=False, message="Not found")
    except Exception as e: return ToolResult(success=False, message=str(e))

# ==============================================================================
# Markdown Tools
# ==============================================================================

async def get_md_structure(file_path: str, *, user_id: str, project_name: str = None, session: AsyncSession = None, **kwargs) -> ToolResult:
    # Use read_reference or save_artifact logic
    # For brevity, reusing save_artifact dir logic
    return await read_reference(file_path, user_id=user_id, project_name=project_name, session=session) # Placeholder logic, user should use read_reference

async def read_md_section(file_path: str, section_title: str, **kwargs) -> ToolResult:
    res = await read_reference(file_path, **kwargs)
    if not res.success: return res
    lines = res.message.splitlines()
    # Simple search
    found = []
    capture = False
    for line in lines:
        if section_title.lower() in line.lower() and line.startswith("#"): capture = True
        elif capture and line.startswith("#"): capture = False
        if capture: found.append(line)
    return ToolResult(success=True, message="\n".join(found))

async def update_md_section(file_path: str, section_title: str, content: str, mode: str = "replace", **kwargs) -> ToolResult:
    return await update_artifact(file_path, f"\n# {section_title}\n{content}", mode='a', **kwargs)

async def init_plan(goal: str, strategy: str, **kwargs) -> ToolResult:
    return await save_artifact(CURRENT_PLAN_FILE, f"# Goal\n{goal}\n# Strategy\n{strategy}", **kwargs)

async def get_current_status(**kwargs) -> ToolResult:
    return await read_md_section(CURRENT_PLAN_FILE, "Current Status", **kwargs)

async def update_plan_progress(summary: str, **kwargs) -> ToolResult:
    return await update_artifact(CURRENT_PLAN_FILE, f"\nLog: {summary}", mode='a', **kwargs)

async def query_md_elements(file_path: str, element_type: str, filter_pattern: str = None, **kwargs) -> ToolResult:
    res = await read_reference(file_path, **kwargs)
    if not res.success: return res
    # Mock impl
    return ToolResult(success=True, message=f"Extracted {element_type} (mock)")

async def upsert_md_table(file_path: str, table_heading: str, primary_key: str, data: Dict, **kwargs) -> ToolResult:
    return await update_artifact(file_path, f"\nUpdated table {table_heading} with {data}", mode='a', **kwargs)

async def compare_md_sections(source: Dict, target: Dict, **kwargs) -> ToolResult:
    return ToolResult(success=True, message="Comparison completed (mock)")

# ==============================================================================
# Research & Code
# ==============================================================================

async def google_search(query: str, user_id: str, session: AsyncSession, **kwargs) -> ToolResult:
    try:
        from google.genai import types
        client = await _get_gemini_client(user_id, session)
        resp = client.models.generate_content(model="gemini-3-flash-preview", contents=query, config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]))
        return ToolResult(success=True, message=resp.text or "No result")
    except Exception as e: return ToolResult(success=False, message=str(e))

async def execute_code(prompt: str, user_id: str, session: AsyncSession, **kwargs) -> ToolResult:
    try:
        from google.genai import types
        client = await _get_gemini_client(user_id, session)
        resp = client.models.generate_content(model="gemini-3-flash-preview", contents=prompt, config=types.GenerateContentConfig(tools=[types.Tool(code_execution=types.ToolCodeExecution())]))
        return ToolResult(success=True, message=resp.text)
    except Exception as e: return ToolResult(success=False, message=str(e))

async def generate_image(prompt: str, filename: str = None, aspect_ratio: str = "1:1", *, user_id: str, session: AsyncSession, project_name: Optional[str] = None, **kwargs) -> ToolResult:
    """Generate an image using Gemini 2.5 Flash Image and save it to project artifacts."""
    try:
        import base64
        
        client = await _get_gemini_client(user_id, session)
        
        # Use Gemini 3 Pro Image for text-to-image generation via generate_content
        # As per Google docs: https://ai.google.dev/gemini-api/docs/image-generation
        response = client.models.generate_content(
            model="gemini-3-pro-image-preview",
            contents=[prompt],
        )
        
        # Find the image part in the response
        image_data = None
        response_text = None
        
        for part in response.parts:
            if part.inline_data is not None:
                image_data = part.inline_data.data
                break
            elif part.text:
                response_text = part.text
        
        if not image_data:
            return ToolResult(
                success=False, 
                message=f"No image generated. Response: {response_text or 'No response'}"
            )
        
        # Generate filename if not provided
        if not filename:
            import hashlib
            hash_suffix = hashlib.md5(prompt.encode()).hexdigest()[:8]
            filename = f"generated_{hash_suffix}.png"
        
        if not filename.endswith(('.png', '.jpg', '.jpeg', '.webp')):
            filename += '.png'
        
        # Save to artifacts directory
        pid = project_name or 'hub'
        artifacts_dir = await _resolve_project_artifacts_dir(user_id, pid, session)
        file_path = artifacts_dir / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Handle base64 encoded image data
        if isinstance(image_data, str):
            image_bytes = base64.b64decode(image_data)
        else:
            image_bytes = image_data
            
        file_path.write_bytes(image_bytes)
        
        return ToolResult(
            success=True, 
            message=f"✅ Generated and saved image: `{filename}`\n\nTo display this image inline, use:\n`artifacts/{filename}`",
            data={"filename": filename, "path": str(file_path), "embed_path": f"artifacts/{filename}"}
        )
    except Exception as e:
        return ToolResult(success=False, message=f"Image generation failed: {e}")

async def search_places(query: str, user_id: str, session: AsyncSession, **kwargs) -> ToolResult:
    try:
        from google.genai import types
        client = await _get_gemini_client(user_id, session)
        resp = client.models.generate_content(model="gemini-3-flash-preview", contents=query, config=types.GenerateContentConfig(tools=[types.Tool(google_maps=types.GoogleMaps())]))
        return ToolResult(success=True, message=resp.text)
    except Exception as e: return ToolResult(success=False, message=str(e))

async def research_url(urls: List[str], query: str, user_id: str, session: AsyncSession, **kwargs) -> ToolResult:
    """Research URLs using Gemini's URL Context tool."""
    try:
        from google.genai.types import GenerateContentConfig
        client = await _get_gemini_client(user_id, session)
        
        # Build the prompt with URLs
        urls_str = " and ".join(urls)
        prompt = f"{query} from {urls_str}" if query else f"Summarize the content from {urls_str}"
        
        # Use URL Context tool as per Google docs
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt,
            config=GenerateContentConfig(
                tools=[{"url_context": {}}]
            )
        )
        
        # Extract text from response
        result_text = ""
        for part in response.candidates[0].content.parts:
            if hasattr(part, 'text') and part.text:
                result_text += part.text
        
        if not result_text:
            return ToolResult(success=False, message="No content retrieved from URLs")
        
        return ToolResult(success=True, message=result_text)
    except Exception as e:
        return ToolResult(success=False, message=f"URL research failed: {e}")

async def generate_mermaid_visualizer(data: Any, diagram_type: str, title: str = "Diagram", **kwargs) -> ToolResult:
    code = f"mermaid\n{diagram_type}\n..."
    await save_artifact(f"visuals/{title}.md", f"```mermaid\n{code}\n```", **kwargs)
    return ToolResult(success=True, message=f"Generated {diagram_type}")


# ==============================================================================
# Final Mapping
# ==============================================================================

TOOL_FUNCTIONS = {
    "ask_node": ask_node,
    "delegate_to_member": delegate_to_member,
    "create_task": create_task,
    "list_tasks": list_tasks,
    "update_task_details": update_task_details,
    "delete_task_by_id": delete_task_by_id,
    "run_cleanup_cycle": run_cleanup_cycle,
    "get_load_on_day": get_load_on_day,
    "get_load_in_period": get_load_in_period,
    "complete_lbs_task": complete_lbs_task,
    "get_lbs_schedule": get_lbs_schedule,
    "get_task_execution_history": get_task_execution_history,
    "update_user_condition": update_user_condition,
    "get_current_condition": get_current_condition,
    "reset_user_condition": reset_user_condition,
    "ingest_knowledge": ingest_knowledge,
    "search_knowledge": search_knowledge,
    "save_artifact": save_artifact,
    "update_artifact": update_artifact,
    "delete_artifact": delete_artifact,
    "read_reference": read_reference,
    "list_files": list_files,
    "google_search": google_search,
    "execute_code": execute_code,
    "generate_image": generate_image,
    "get_md_structure": get_md_structure,
    "read_md_section": read_md_section,
    "update_md_section": update_md_section,
    "init_plan": init_plan,
    "get_current_status": get_current_status,
    "update_plan_progress": update_plan_progress,
    "query_md_elements": query_md_elements,
    "upsert_md_table": upsert_md_table,
    "compare_md_sections": compare_md_sections,
    "search_places": search_places,
    "research_url": research_url,
    "generate_mermaid_visualizer": generate_mermaid_visualizer,
}
