"""
Scheduler Agent - LLM-Powered Task Preprocessor

Uses Gemini to intelligently optimize the task queue before
deterministic scheduling (add travel time, fix estimates, reorder).
"""

import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from google.genai import Client, types
from config import settings

logger = logging.getLogger(__name__)


# ============================================================================
# Prompt Template
# ============================================================================

SCHEDULER_AGENT_PROMPT = """You are an intelligent schedule optimizer. Your job is to preprocess a task list before it gets time-slotted.

## Current Context
- Current Time: {current_time}
- Fatigue Level: {fatigue_level}/5 (0=Fresh, 5=Exhausted)
- Day: {day_of_week}

## Input Tasks
```json
{tasks_json}
```

## Your Job
Analyze the tasks and return an optimized queue. Consider:

1. **Travel Time**: If consecutive tasks are in different locations, insert travel buffer tasks.
2. **Time Estimates**: If a task has unrealistic duration based on its load, adjust it.
3. **Fatigue Awareness**: If fatigue is high (3+), prioritize light tasks first.
4. **Context Switching**: Group tasks by similar context when possible.
5. **ANCHORS (LOCKED TASKS)**: Any task with `"is_locked": true` or `"_source_locked": true` MUST NOT be moved.
   - You can schedule items AROUND anchors, but anchors must stay at their `start_time`.
   - If an anchor is at 10:00, you cannot put another task at 10:00.

## Output Format
Return ONLY valid JSON (no markdown, no explanation):
```json
{{
  "optimized_queue": [
    {{
      "task_id": "...",
      "task_name": "...",
      "load": 2.0,
      "estimated_minutes": 60,
      "start_time": "09:00",
      "end_time": "10:00",
      "is_locked": true,  <-- Return locked status
      "notes": "Original task"
    }},
    {{
      "task_id": "travel_1",
      "task_name": "Travel to office",
      "context": "Travel",
      "is_travel_buffer": true,
      "estimated_minutes": 30
    }}
  ]
}}
```

IMPORTANT:
- Keep all original task_ids intact.
- RESPECT "is_locked": true. Do not change start_time of locked tasks.
- Only ADD travel buffers (with task_id like "travel_1").
- Return ONLY the JSON object.
"""


# ============================================================================
# SchedulerAgent Class
# ============================================================================

class SchedulerAgent:
    """
    Intelligent preprocessor that uses LLM to optimize the task queue
    before deterministic time-slotting.
    """
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.0-flash"):
        """
        Initialize the scheduler agent.
        
        Args:
            api_key: Google AI API key (uses env GOOGLE_API_KEY if not provided)
            model: Model to use for optimization
        """
        import os
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY")
        self.model = model
        self._client: Optional[Client] = None
    
    def _get_client(self) -> Optional[Client]:
        """Lazy-load the Gemini client."""
        if self._client is None and self.api_key:
            try:
                self._client = Client(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini client: {e}")
                return None
        return self._client
    
    async def enrich_schedule(
        self,
        current_time: datetime,
        fatigue_level: int,
        tasks: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Use LLM to optimize the task queue.
        
        Args:
            current_time: Current datetime
            fatigue_level: 0-5 fatigue level
            tasks: List of task dicts from LBS
            
        Returns:
            Optimized task list (or original if LLM fails)
        """
        if not tasks:
            return tasks
        
        client = self._get_client()
        if not client:
            print("🔴 AGENT: No Gemini client, returning original tasks")
            return tasks
        
        print(f"🟢 AGENT: Starting with {len(tasks)} tasks, fatigue={fatigue_level}")
        for i, t in enumerate(tasks[:3]):
            print(f"   Input[{i}]: {t.get('task_name', 'N/A')[:30]} | load={t.get('load', 'N/A')}")
        
        try:
            # Build the prompt
            prompt = SCHEDULER_AGENT_PROMPT.format(
                current_time=current_time.strftime("%Y-%m-%d %H:%M"),
                fatigue_level=fatigue_level,
                day_of_week=current_time.strftime("%A"),
                tasks_json=json.dumps(tasks, indent=2, default=str)
            )
            
            print(f"🟡 AGENT: Calling Gemini ({self.model})...")
            
            # Call Gemini
            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=4096,
                )
            )
            
            # Extract text from response
            response_text = response.text.strip()
            
            print(f"🟡 AGENT: Got response ({len(response_text)} chars)")
            print(f"   Response preview: {response_text[:300]}...")
            
            # Parse JSON response
            optimized = self._parse_response(response_text, tasks)
            
            if optimized:
                print(f"🟢 AGENT: SUCCESS - {len(tasks)} -> {len(optimized)} items")
                
                # Log what changed
                travel_buffers = [t for t in optimized if t.get("is_travel_buffer")]
                if travel_buffers:
                    print(f"   ✅ Added {len(travel_buffers)} travel buffer(s)")
                    for tb in travel_buffers:
                        print(f"      - {tb.get('task_name')}: {tb.get('estimated_minutes', 'N/A')} min")
                else:
                    print("   ⚠️ No travel buffers added by LLM")
                
                # Log reordering
                original_order = [t.get("task_name", "")[:20] for t in tasks]
                new_order = [t.get("task_name", "")[:20] for t in optimized if not t.get("is_travel_buffer")]
                if original_order != new_order:
                    print("   ✅ Tasks reordered")
                
                return optimized
            else:
                print("🔴 AGENT: LLM returned invalid response, using original")
                return tasks
                
        except Exception as e:
            print(f"🔴 AGENT ERROR: {e}")
            return tasks  # Fallback to original
    
    def _parse_response(
        self, 
        response_text: str, 
        original_tasks: List[Dict]
    ) -> Optional[List[Dict]]:
        """
        Safely parse LLM response JSON.
        
        Returns:
            Parsed optimized_queue or None if parsing fails
        """
        try:
            # Try to find JSON in the response
            text = response_text
            
            # Handle markdown code blocks
            if "```json" in text:
                start = text.find("```json") + 7
                end = text.find("```", start)
                text = text[start:end].strip()
            elif "```" in text:
                start = text.find("```") + 3
                end = text.find("```", start)
                text = text[start:end].strip()
            
            # Parse JSON
            data = json.loads(text)
            
            # Extract optimized_queue
            if isinstance(data, dict) and "optimized_queue" in data:
                queue = data["optimized_queue"]
                if isinstance(queue, list) and len(queue) > 0:
                    # Log reasoning if present
                    if "reasoning" in data:
                        logger.info(f"LLM reasoning: {data['reasoning'][:200]}")
                    return queue
            
            # If response is just a list, use it directly
            if isinstance(data, list) and len(data) > 0:
                return data
                
            return None
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response as JSON: {e}")
            return None
        except Exception as e:
            logger.warning(f"Error parsing LLM response: {e}")
            return None


# ============================================================================
# Convenience Function
# ============================================================================

async def enrich_tasks_with_agent(
    tasks: List[Dict[str, Any]],
    current_time: datetime,
    fatigue_level: int = 0,
    api_key: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Convenience function to enrich tasks using the scheduler agent.
    
    Args:
        tasks: Original task list
        current_time: Current datetime
        fatigue_level: 0-5 fatigue level
        api_key: Gemini API key
        
    Returns:
        Enriched task list (or original if agent fails)
    """
    agent = SchedulerAgent(api_key=api_key)
    return await agent.enrich_schedule(current_time, fatigue_level, tasks)

