from typing import Any, Dict
from datetime import datetime
from nodes.base_node import BaseNode
from services.scheduler_service import calculate_schedule_v3, OperationRecord

class SchedulerNode(BaseNode):
    """
    The Timekeeper.
    Wraps the SchedulerService to handle scheduling requests.
    """
    
    async def pre_process(self):
        pass

    async def process(self, message: str) -> Dict[str, Any]:
        """
        Process explicit scheduling requests.
        """
        print(f"[SchedulerNode] Processing request: {message}")
        
        # 1. Parse Intent & Extract Parameters (Mocking extraction for now)
        # In a real scenario, we might use an LLM here to extract tasks/constraints from the message.
        # For V3 demo, we assume the Router determined this is a schedule request.
        
        # 2. Fetch current state (Tasks)
        # TODO: Fetch real tasks from DB. Mocking for now.
        mock_tasks = [
            {"id": "t1", "title": "Review Code", "load": 2.0, "status": "todo"},
            {"id": "t2", "title": "Write Docs", "load": 1.5, "status": "todo"}
        ]
        
        # 3. Call Scheduler Service
        try:
            # We use the V3 pipeline
            result: OperationRecord = await calculate_schedule_v3(
                tasks=mock_tasks,
                exceptions=[], # Fetch from LBS
                fatigue=0,     # Fetch from User State
                now=datetime.now(),
                api_key=None   # Pass if we want Agent optimization
            )
            return result.to_dict()
            
        except Exception as e:
            print(f"[SchedulerNode] Error: {e}")
            return {"error": str(e)}

    async def propose_task(self, draft_task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Propose a slot for a drafted task.
        """
        print(f"[SchedulerNode] Proposing slot for: {draft_task}")
        
        # 1. Fetch Request params
        duration = float(draft_task.get("load", 1.0)) # Treat load as duration hours for simplicity in V3
        target_date = datetime.now() # Default to today/next avail
        
        # 2. Get Current Schedule State
        # In real V3, we'd fetch actual tasks from DB via 'list_tasks' or service
        # For now we use calculate_schedule_v3 with empty/mock to see "busy" slots logic if we had tasks.
        # But to find a gap, we need to know what's busy. 
        # Only mocking the *tasks input*, but running the *real logic*.
        try:
             # Fetch mock existing tasks (simulating DB)
             existing_tasks = [
                 {"id": "existing_1", "title": "Morning Sync", "start_time": "09:00", "end_time": "10:00", "is_locked": True},
                 {"id": "existing_2", "title": "Lunch", "start_time": "12:00", "end_time": "13:00", "is_locked": True}
             ]
             
             schedule_record: OperationRecord = await calculate_schedule_v3(
                 tasks=existing_tasks,
                 exceptions=[],
                 fatigue=0,
                 now=target_date
             )
             
             # 3. Find Gap (Heuristic)
             # Simple logic: Scan 09:00 to 18:00 for a gap > duration
             business_start = 9
             business_end = 18
             
             # Convert schedule to occupied ranges (in decimal hours)
             occupied = []
             for item in schedule_record.schedule:
                 if item.start and item.end:
                     s_dec = item.start.hour + item.start.minute/60.0
                     e_dec = item.end.hour + item.end.minute/60.0
                     occupied.append((s_dec, e_dec))
             occupied.sort()
             
             proposed_start = None
             
             # Check distinct gaps
             current_cursor = business_start
             for s, e in occupied:
                 if s - current_cursor >= duration:
                     proposed_start = current_cursor
                     break
                 current_cursor = max(current_cursor, e)
                 
             if proposed_start is None and (business_end - current_cursor >= duration):
                 proposed_start = current_cursor
                 
             if proposed_start is None:
                 # Push to tomorrow (Mock logic)
                 return {
                     "status": "deferred",
                     "reason": "No slots available today",
                     "task": draft_task
                 }
                 
             # Format Output
             import math
             start_h = int(proposed_start)
             start_m = int((proposed_start - start_h) * 60)
             end_decimal = proposed_start + duration
             end_h = int(end_decimal)
             end_m = int((end_decimal - end_h) * 60)
             
             slot_str = f"{start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d}"
             
             result = {
                "status": "proposed",
                "slot": {
                    "start": f"{start_h:02d}:{start_m:02d}",
                    "end": f"{end_h:02d}:{end_m:02d}",
                    "date": target_date.strftime("%Y-%m-%d")
                },
                "task": draft_task
             }
             return result

        except Exception as e:
            print(f"[SchedulerNode] Error proposing task: {e}")
            return {"status": "error", "message": str(e)}

    async def post_process(self, result: Any):
        pass
    
    async def run_maintenance(self):
        """
        Async periodic check.
        """
        print("[SchedulerNode] Running maintenance checks...")
        # Check for overload, overdue tasks, etc.
