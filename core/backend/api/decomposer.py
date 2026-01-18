"""
Task Decomposition API
Uses Gemini to break down high-level tasks into structured subtasks
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session

from models.database import get_session, UserSettings
from llm.gemini_provider import GeminiProvider
from api.auth import get_current_user
from utils.encryption import decrypt_string
import json
import re

router = APIRouter(prefix="/api/decompose", tags=["decompose"])


class DecomposeRequest(BaseModel):
    task_description: str
    max_subtasks: int = 5
    context: Optional[str] = None  # Optional project context


class SuggestedTask(BaseModel):
    task_name: str
    workload: float  # 0-10
    project: str
    notes: Optional[str] = None
    rule_type: str = "ONCE"


class DecomposeResponse(BaseModel):
    original_task: str
    suggested_tasks: List[SuggestedTask]


def _get_gemini_api_key(user_id: str, session: Session) -> str:
    """Retrieve and decrypt Gemini API key for the user"""
    settings = session.query(UserSettings).filter_by(user_id=user_id).first()
    if not settings or not settings.gemini_api_key:
        raise HTTPException(status_code=400, detail="Gemini API key not configured")
    return decrypt_string(settings.gemini_api_key)


@router.post("", response_model=DecomposeResponse)
async def decompose_task(
    request: DecomposeRequest,
    current_user=Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    Use Gemini to decompose a high-level task into structured subtasks.
    Returns suggested task names, workloads, and project assignments.
    """
    user_id = current_user.user_id
    
    # Get API key
    api_key = _get_gemini_api_key(user_id, session)
    
    # Build the prompt for task decomposition
    prompt = f"""You are a task decomposition assistant. Given a high-level task description, break it down into actionable subtasks.

High-level task: {request.task_description}
{"Context/Project: " + request.context if request.context else ""}
Maximum subtasks: {request.max_subtasks}

For each subtask, provide:
1. task_name: A clear, actionable task name (max 50 chars)
2. workload: Estimated effort on a scale of 0-10 (0=trivial, 10=major effort)
3. project: Suggested project/context category (use the provided context if available, otherwise suggest appropriate ones like "personal", "work", "admin", etc.)
4. notes: Optional brief notes or tips

Return your response as a JSON array of objects with keys: task_name, workload, project, notes
Return ONLY the JSON array, no other text.

Example output:
[
  {{"task_name": "Research moving companies", "workload": 3, "project": "personal", "notes": "Get at least 3 quotes"}},
  {{"task_name": "Pack non-essential items", "workload": 5, "project": "personal", "notes": "Start with off-season clothes"}}
]
"""
    
    try:
        # Use Gemini to generate subtasks
        provider = GeminiProvider(api_key=api_key)
        response = await provider.complete(
            prompt=prompt,
            model="gemini-2.0-flash",
            temperature=0.7
        )
        
        # Parse the JSON response
        response_text = response.strip()
        
        # Try to extract JSON from the response if it's wrapped in markdown
        json_match = re.search(r'\[[\s\S]*\]', response_text)
        if json_match:
            response_text = json_match.group(0)
        
        subtasks_data = json.loads(response_text)
        
        # Validate and create SuggestedTask objects
        suggested_tasks = []
        for task_data in subtasks_data[:request.max_subtasks]:
            suggested_tasks.append(SuggestedTask(
                task_name=task_data.get("task_name", "Untitled Task")[:50],
                workload=min(10, max(0, float(task_data.get("workload", 5)))),
                project=task_data.get("project", task_data.get("spoke", request.context or "general")), # Fallback to spoke/context
                notes=task_data.get("notes"),
                rule_type="ONCE"
            ))
        
        return DecomposeResponse(
            original_task=request.task_description,
            suggested_tasks=suggested_tasks
        )
        
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to parse AI response: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Decomposition failed: {str(e)}"
        )
