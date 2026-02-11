from typing import Any, Dict, List, Optional
from datetime import datetime
from domains.orchestration.nodes.base_node import BaseNode
from domains.automation.scheduler_service import calculate_schedule_v3, OperationRecord

class SchedulerNode(BaseNode):
    """
    The Timekeeper.
    Wraps the SchedulerService to handle scheduling requests.
    """
    
    async def _get_lbs_client(self) -> Any:
        """
        Initialize LBSClient using credentials from the database.
        """
        from shared.database import AsyncSessionLocal, ServiceRegistry
        from services.lbs_client import LBSClient
        from sqlalchemy import select
        
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ServiceRegistry).filter(
                    ServiceRegistry.user_id == self.user_id,
                    ServiceRegistry.service_name == "lbs"
                )
            )
            svc = result.scalars().first()
            if not svc:
                print(f"[SchedulerNode] No LBS service registry found for user {self.user_id}")
                return None
            
            return LBSClient(base_url=svc.base_url, api_key=svc.api_key)

    async def _get_lbs_context(self, client: Any, target_date: datetime) -> Dict[str, Any]:
        """
        Fetch tasks, exceptions, and fatigue from LBS.
        """
        date_str = target_date.strftime("%Y-%m-%d")
        try:
            # 1. Fetch Tasks (with status for the day)
            tasks = await client.list_tasks(target_date=date_str)
            
            # 2. Fetch Exceptions
            exceptions = await client.get_exceptions(start_date=date_str, end_date=date_str)
            
            # 3. Fetch Condition (Fatigue)
            fatigue = 0
            try:
                condition = await client.get_condition(target_date=date_str)
                fatigue = condition.get("cognitive_fatigue", 0)
            except:
                pass
                
            return {
                "tasks": tasks,
                "exceptions": exceptions,
                "fatigue": fatigue
            }
        except Exception as e:
            print(f"[SchedulerNode] Error fetching LBS context: {e}")
            return {"tasks": [], "exceptions": [], "fatigue": 0}

    async def on_enter(self):
        pass

    async def on_execute(self, message: str) -> Dict[str, Any]:
        """
        Process explicit scheduling requests.
        """
        print(f"[SchedulerNode] Processing request: {message}")
        
        # 1. Initialize Client
        client = await self._get_lbs_client()
        if not client:
            return {"error": "LBS service not configured."}
            
        async with client:
            # 2. Fetch Context
            now = datetime.now()
            lbs_ctx = await self._get_lbs_context(client, now)
            
            # 3. Call Scheduler Service (V3 Pipeline)
            try:
                result: OperationRecord = await calculate_schedule_v3(
                    tasks=lbs_ctx["tasks"],
                    exceptions=lbs_ctx["exceptions"],
                    fatigue=lbs_ctx["fatigue"],
                    now=now,
                    api_key=self.context.get("api_key")
                )
                return result.to_dict()
                
            except Exception as e:
                print(f"[SchedulerNode] Error during scheduling: {e}")
                return {"error": str(e)}

    async def propose_task(self, draft_task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Propose a slot for a drafted task.
        """
        print(f"[SchedulerNode] Proposing slot for: {draft_task}")
        
        duration = float(draft_task.get("load", 1.0))
        target_date = datetime.now()
        
        client = await self._get_lbs_client()
        if not client:
            return {"status": "error", "message": "LBS service not configured."}
            
        async with client:
            try:
                # Fetch Real Context
                lbs_ctx = await self._get_lbs_context(client, target_date)
                
                # Use real existing tasks/exceptions to build the schedule
                schedule_record: OperationRecord = await calculate_schedule_v3(
                    tasks=lbs_ctx["tasks"],
                    exceptions=lbs_ctx["exceptions"],
                    fatigue=lbs_ctx["fatigue"],
                    now=target_date
                )
                
                # Find Gap (Heuristic)
                business_start = 9
                business_end = 18
                
                occupied = []
                for item in schedule_record.schedule:
                    if item.start and item.end:
                        s_dec = item.start.hour + item.start.minute/60.0
                        e_dec = item.end.hour + item.end.minute/60.0
                        occupied.append((s_dec, e_dec))
                occupied.sort()
                
                proposed_start = None
                current_cursor = business_start
                for s, e in occupied:
                    if s - current_cursor >= duration:
                        proposed_start = current_cursor
                        break
                    current_cursor = max(current_cursor, e)
                    
                if proposed_start is None and (business_end - current_cursor >= duration):
                    proposed_start = current_cursor
                    
                if proposed_start is None:
                    return {
                        "status": "deferred",
                        "reason": "No slots available today",
                        "task": draft_task
                    }
                    
                start_h = int(proposed_start)
                start_m = int((proposed_start - start_h) * 60)
                end_decimal = proposed_start + duration
                end_h = int(end_decimal)
                end_m = int((end_decimal - end_h) * 60)
                
                return {
                    "status": "proposed",
                    "slot": {
                        "start": f"{start_h:02d}:{start_m:02d}",
                        "end": f"{end_h:02d}:{end_m:02d}",
                        "date": target_date.strftime("%Y-%m-%d")
                    },
                    "task": draft_task
                }

            except Exception as e:
                print(f"[SchedulerNode] Error proposing task: {e}")
                return {"status": "error", "message": str(e)}

    async def on_exit(self, result: Any):
        pass
    
    async def run_maintenance(self):
        """
        Async periodic check.
        """
        print("[SchedulerNode] Running maintenance checks...")
        # Future: proactive overload alerts via LBS analysis
