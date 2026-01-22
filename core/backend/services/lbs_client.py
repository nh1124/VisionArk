import httpx
import os
import enum
from datetime import date, datetime
from typing import List, Optional, Dict, Any, Union

class TaskStatus(str, enum.Enum):
    """Possible statuses for an LBS task execution."""
    TODO = "todo"
    DONE = "done"
    SKIPPED = "skipped"

class LBSClient:
    """
    Asynchronous client for interacting with the LBS Microservice.
    Aligned with the latest LBS Python SDK.
    """
    def __init__(
        self, 
        base_url: Optional[str] = None, 
        api_key: Optional[str] = None, 
        token: Optional[str] = None,
        external_jwt: Optional[str] = None,
        timeout: float = 300.0
    ):
        from config import settings
        
        # Determine default URL
        env_url = os.getenv("LBS_SERVICE_URL")
        hardcoded_fallback = "http://localhost:8100/api/lbs"
        final_url = base_url or env_url or settings.lbs_service_url or hardcoded_fallback
        
        # Docker networking adjustment
        if "localhost" in final_url and os.path.exists("/.dockerenv"):
            final_url = final_url.replace("localhost", "host.docker.internal")
            
        self.base_url = final_url.rstrip("/")
        if not self.base_url.startswith("http"):
            self.base_url = f"http://{self.base_url}"
            
        self.api_key = api_key or os.getenv("LBS_API_KEY")
        self.token = token
        self.external_jwt = external_jwt
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        if self.api_key:
            headers["X-API-KEY"] = self.api_key
        elif self.token:
            headers["Authorization"] = f"Bearer {self.token}"
            
        if self.external_jwt:
            headers["X-EXTERNAL-JWT"] = self.external_jwt
            
        return headers

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        headers = self._get_headers()
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))

        if self._client:
            resp = await self._client.request(method, path.lstrip("/"), headers=headers, **kwargs)
        else:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
                resp = await client.request(method, path.lstrip("/"), headers=headers, **kwargs)

        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            try:
                error_data = resp.json()
                detail = error_data.get("detail", str(e))
                raise Exception(f"{resp.status_code} Error: {detail}") from e
            except Exception:
                raise e

        if resp.status_code == 204:
            return None
        return resp.json()

    # --- Authentication ---

    async def login(self, username_or_email: str, password: str) -> str:
        """Login and obtain a JWT."""
        payload = {"username_or_email": username_or_email, "password": password}
        data = await self._request("POST", "auth/login", json=payload)
        self.token = data.get("access_token")
        return self.token

    async def verify_identity(self) -> Dict:
        """Verify current identity status."""
        return await self._request("GET", "auth/me")

    async def confirm_link_external(self) -> Dict:
        """Link an external identity to the local account."""
        return await self._request("POST", "auth/link/confirm")

    async def provision_api_key(self, rotate: bool = False, scopes: List[str] = ["read"]) -> Dict:
        """Provision an API key."""
        payload = {"rotate": rotate, "scopes": scopes}
        return await self._request("POST", "auth/api-keys/provision", json=payload)

    # --- User Management ---

    async def create_user(self, email: str, name: Optional[str] = None, password: Optional[str] = None) -> Dict:
        """Create a new local user account."""
        payload = {"email": email, "name": name, "password": password}
        return await self._request("POST", "users/", json=payload)

    async def get_user_me(self) -> Dict:
        """Get profile details."""
        return await self._request("GET", "users/me")

    # --- Task Operations ---

    async def list_tasks(self, context: Optional[str] = None, active: Optional[bool] = None, target_date: Optional[Union[date, str]] = None) -> List[Dict]:
        """
        List task definitions.
        If target_date is provided, merges daily status from schedule.
        """
        params = {}
        if context: params["context"] = context
        if active is not None: params["active"] = str(active).lower()
        
        all_tasks = await self._request("GET", "tasks", params=params)

        if target_date:
            t_date_str = target_date.isoformat() if isinstance(target_date, date) else target_date
            try:
                # Fetch schedule for that specific day to get statuses and overrides
                schedule = await self.get_schedule(t_date_str, t_date_str)
                task_overlay = {}
                scheduled_task_ids = set()
                
                if schedule and isinstance(schedule, list):
                    for day_data in schedule:
                        if day_data.get("date") == t_date_str:
                            for t in day_data.get("tasks", []):
                                tid = t.get("task_id")
                                if tid:
                                    scheduled_task_ids.add(tid)
                                    task_overlay[tid] = {
                                        "status": t.get("status", "todo"),
                                        "load": t.get("load"),
                                        "start_time": t.get("start_time"),
                                        "end_time": t.get("end_time"),
                                        "is_locked": t.get("is_locked", False),
                                        "has_exception": t.get("has_exception", False),
                                        "exception_type": t.get("exception_type")
                                    }
                
                filtered_tasks = []
                for task in all_tasks:
                    tid = task.get("task_id")
                    if tid in scheduled_task_ids:
                        overlay = task_overlay.get(tid, {})
                        task.update(overlay)
                        filtered_tasks.append(task)
                return filtered_tasks
            except Exception as e:
                import logging
                logging.warning(f"Failed to fetch schedule for {t_date_str}: {e}")
                return []
        
        return all_tasks

    async def get_task(self, task_id: str, target_date: Optional[Union[date, str]] = None) -> Dict:
        """Get task details, optionally with status for a specific date."""
        params = {}
        if target_date:
            params["target_date"] = target_date.isoformat() if isinstance(target_date, date) else target_date
        
        task = await self._request("GET", f"tasks/{task_id}", params=params)
        
        # Compatibility: if target_date was provided but status not in response, try to fetch it
        if target_date and "status" not in task:
            t_date_str = target_date.isoformat() if isinstance(target_date, date) else target_date
            try:
                schedule = await self.get_schedule(t_date_str, t_date_str)
                for day_data in schedule:
                    if day_data.get("date") == t_date_str:
                        for t in day_data.get("tasks", []):
                            if t.get("task_id") == task_id:
                                task["status"] = t.get("status", "todo")
                                break
            except: pass
            
        return task

    async def create_task(self, task_data: Dict) -> Dict:
        """Create a new task."""
        return await self._request("POST", "tasks", json=task_data)

    async def update_task(self, task_id: str, task_data: Dict, force_override: bool = False) -> Dict:
        """Update a task."""
        params = {"force_override": str(force_override).lower()}
        return await self._request("PUT", f"tasks/{task_id}", json=task_data, params=params)

    async def delete_task(self, task_id: str, force_override: bool = False) -> Dict:
        """Delete a task."""
        params = {"force_override": str(force_override).lower()}
        return await self._request("DELETE", f"tasks/{task_id}", params=params)

    async def bulk_delete_tasks(self, task_ids: List[str], force_override: bool = False) -> Dict:
        """Delete multiple tasks."""
        params = {"force_override": str(force_override).lower()}
        return await self._request("POST", "tasks/bulk-delete", json={"task_ids": task_ids}, params=params)

    async def bulk_update_active(self, task_ids: List[str], active: bool, force_override: bool = False) -> Dict:
        """Update active status for multiple tasks."""
        params = {"force_override": str(force_override).lower()}
        return await self._request("POST", "tasks/bulk-update-active", json={"task_ids": task_ids, "active": active}, params=params)

    async def toggle_task_completion(self, task_id: str, target_date: Union[date, str], status: Union[bool, TaskStatus] = TaskStatus.DONE) -> Dict:
        """Toggle task completion for a date."""
        date_str = target_date.isoformat() if isinstance(target_date, date) else target_date
        if isinstance(status, bool):
            status_val = TaskStatus.DONE if status else TaskStatus.TODO
        else:
            status_val = status
            
        return await self._request("POST", f"tasks/{task_id}/complete", json={
            "target_date": date_str, 
            "status": status_val.value if isinstance(status_val, TaskStatus) else status_val
        })

    async def get_task_history(self, task_id: str, start_date: Union[date, str], end_date: Union[date, str]) -> List[Dict]:
        """Get historical records for a task."""
        params = {
            "start_date": start_date.isoformat() if isinstance(start_date, date) else start_date,
            "end_date": end_date.isoformat() if isinstance(end_date, date) else end_date
        }
        return await self._request("GET", f"tasks/{task_id}/history", params=params)

    async def upload_tasks_csv(self, file_content: bytes, filename: str) -> Dict:
        """Upload CSV file for server-side task creation"""
        files = {"file": (filename, file_content, "text/csv")}
        # httpx handles boundary and content-type automatically for files when headers doesn't have it
        headers = self._get_headers()
        if "Content-Type" in headers:
            del headers["Content-Type"]
            
        if self._client:
            resp = await self._client.post("tasks/upload-csv", headers=headers, files=files)
        else:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
                resp = await client.post("tasks/upload-csv", headers=headers, files=files)
        resp.raise_for_status()
        return resp.json()

    # --- Load Analysis ---

    async def get_dashboard(self, start_date: Optional[Union[date, str]] = None) -> Dict:
        """Get summary dashboard."""
        params = {}
        if start_date:
            params["start_date"] = start_date.isoformat() if isinstance(start_date, date) else start_date
        return await self._request("GET", "dashboard", params=params)

    async def get_heatmap(self, start: Union[date, str], end: Union[date, str], statuses: Optional[List[Union[str, TaskStatus]]] = None) -> List[Dict]:
        """Get daily load distribution."""
        params = {
            "start": start.isoformat() if isinstance(start, date) else start,
            "end": end.isoformat() if isinstance(end, date) else end,
        }
        if statuses:
            params["status"] = [s.value if isinstance(s, TaskStatus) else s for s in statuses]
        return await self._request("GET", "heatmap", params=params)

    async def get_trends(self, weeks: int = 12, start_date: Optional[Union[date, str]] = None, statuses: Optional[List[Union[str, TaskStatus]]] = None) -> Dict:
        """Get prediction trends."""
        params = {"weeks": weeks}
        if statuses:
            params["status"] = [s.value if isinstance(s, TaskStatus) else s for s in statuses]
        if start_date:
            params["start_date"] = start_date.isoformat() if isinstance(start_date, date) else start_date
        return await self._request("GET", "trends", params=params)

    async def get_context_distribution(self, start: Union[date, str], end: Union[date, str], statuses: Optional[List[Union[str, TaskStatus]]] = None) -> Dict:
        """Get context load distribution."""
        params = {
            "start": start.isoformat() if isinstance(start, date) else start,
            "end": end.isoformat() if isinstance(end, date) else end,
        }
        if statuses:
            params["status"] = [s.value if isinstance(s, TaskStatus) else s for s in statuses]
        return await self._request("GET", "context-distribution", params=params)

    async def calculate_load(self, target_date: Union[date, str], statuses: Optional[List[Union[str, TaskStatus]]] = None) -> Dict:
        """Calculate raw load for a date."""
        target = target_date.isoformat() if isinstance(target_date, date) else target_date
        params = {}
        if statuses:
            params["status"] = [s.value if isinstance(s, TaskStatus) else s for s in statuses]
        return await self._request("GET", f"calculate/{target}", params=params)

    async def get_schedule(self, start_date: Union[date, str], end_date: Union[date, str]) -> List[Dict]:
        """Get daily schedule."""
        params = {
            "start_date": start_date.isoformat() if isinstance(start_date, date) else start_date,
            "end_date": end_date.isoformat() if isinstance(end_date, date) else end_date
        }
        return await self._request("GET", "schedule", params=params)

    async def force_expand(self, start_date: Union[date, str], end_date: Union[date, str]) -> Dict:
        """Force trigger task expansion."""
        params = {
            "start_date": start_date.isoformat() if isinstance(start_date, date) else start_date,
            "end_date": end_date.isoformat() if isinstance(end_date, date) else end_date
        }
        return await self._request("POST", "expand", params=params)

    async def get_resolved_task(self, task_id: str, target_date: Union[date, str]) -> Dict:
        """Get task details with exception overrides for a specific date."""
        params = {
            "target_date": target_date.isoformat() if isinstance(target_date, date) else target_date
        }
        return await self._request("GET", f"tasks/{task_id}/resolved", params=params)

    async def create_exception(self, exception_data: Dict, force_override: bool = False) -> Dict:
        """Register a task exception."""
        params = {"force_override": str(force_override).lower()}
        return await self._request("POST", "exceptions", json=exception_data, params=params)

    async def update_exception(self, exception_id: int, exception_data: Dict, force_override: bool = False) -> Dict:
        """Update a task exception."""
        params = {"force_override": str(force_override).lower()}
        return await self._request("PUT", f"exceptions/{exception_id}", json=exception_data, params=params)

    async def delete_exception(self, exception_id: int, force_override: bool = False) -> Dict:
        """Delete a task exception."""
        params = {"force_override": str(force_override).lower()}
        return await self._request("DELETE", f"exceptions/{exception_id}", params=params)

    async def get_exceptions(self, start_date: Union[date, str], end_date: Union[date, str]) -> List[Dict]:
        """Get exceptions for a date range."""
        params = {
            "start_date": start_date.isoformat() if isinstance(start_date, date) else start_date,
            "end_date": end_date.isoformat() if isinstance(end_date, date) else end_date
        }
        return await self._request("GET", "exceptions", params=params)

    async def update_condition(self, target_date: Union[date, str], cognitive_fatigue: int, note: Optional[str] = None) -> Dict:
        """Update daily condition."""
        date_str = target_date.isoformat() if isinstance(target_date, date) else target_date
        payload = {
            "date": date_str,
            "cognitive_fatigue": cognitive_fatigue,
            "note": note
        }
        return await self._request("POST", "conditions", json=payload)

    async def get_condition(self, target_date: Union[date, str]) -> Dict:
        """Get condition for a date."""
        date_str = target_date.isoformat() if isinstance(target_date, date) else target_date
        return await self._request("GET", f"conditions/{date_str}")

    async def delete_condition(self, target_date: Union[date, str]) -> Dict:
        """Delete condition for a date."""
        date_str = target_date.isoformat() if isinstance(target_date, date) else target_date
        return await self._request("DELETE", f"conditions/{date_str}")

    async def health_check(self) -> Dict:
        """System health check."""
        return await self._request("GET", "health")
