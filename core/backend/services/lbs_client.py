import httpx
import os
from datetime import date
from typing import List, Optional, Dict, Union
from pydantic import BaseModel
import enum

class TaskStatus(str, enum.Enum):
    """Possible statuses for an LBS task execution."""
    TODO = "todo"
    DONE = "done"
    SKIPPED = "skipped"
    IN_PROGRESS = "in_progress"

class LBSClient:
    """
    Client for interacting with the LBS Microservice.
    Delegates all load balancing logic to the standalone service.
    """
    def __init__(self, base_url: str = None, api_key: str = None, token: str = None):
        from config import settings
        
        # 1. Determine default URL from settings or env
        env_url = os.getenv("LBS_SERVICE_URL")
        # Use provided base_url, then env_url (if not empty), then settings default, then fallback
        hardcoded_fallback = "http://localhost:8100/api/lbs"
        final_url = base_url or env_url or settings.lbs_service_url or hardcoded_fallback
        
        # In Docker, localhost refers to the container. Use host.docker.internal for the host LBS.
        if "localhost" in final_url and os.path.exists("/.dockerenv"):
            final_url = final_url.replace("localhost", "host.docker.internal")
            
        self.base_url = final_url
        if self.base_url and not self.base_url.startswith("http"):
            self.base_url = f"http://{self.base_url}"
        
        # Ensure base_url ends with a slash for proper relative path joining
        if self.base_url and not self.base_url.endswith("/"):
            self.base_url += "/"
            
        self.api_key = api_key
        self.token = token
        
    def _get_headers(self):
        from config import settings
        headers = {
            "X-SERVICE-KEY": settings.atmos_service_key
        }
        
        if self.api_key:
            headers["X-API-KEY"] = self.api_key
        
        # Prefer JWT token propagation
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        
        return headers

    def get_dashboard(self, start_date: Optional[date] = None) -> Dict:
        params = {}
        if start_date:
            params["start_date"] = start_date.isoformat()
        
        with httpx.Client(base_url=self.base_url) as client:
            resp = client.get("dashboard", params=params, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

    def create_task(self, task_data: Dict) -> Dict:
        with httpx.Client(base_url=self.base_url) as client:
            resp = client.post("tasks", json=task_data, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

    def get_task(self, task_id: str, target_date: Optional[Union[date, str]] = None) -> Optional[Dict]:
        with httpx.Client(base_url=self.base_url) as client:
            resp = client.get(f"tasks/{task_id}", headers=self._get_headers())
            resp.raise_for_status()
            task = resp.json()

            if target_date:
                t_date_str = target_date.isoformat() if isinstance(target_date, date) else target_date
                # Fetch schedule for that day to get status
                sched_resp = client.get("schedule", params={"start_date": t_date_str, "end_date": t_date_str}, headers=self._get_headers())
                if sched_resp.ok:
                    schedule = sched_resp.json()
                    for day_data in schedule:
                        if day_data["date"] == t_date_str:
                            for t in day_data["tasks"]:
                                if t["task_id"] == task_id:
                                    task["status"] = t["status"]
                                    break
            return task

    def update_task(self, task_id: str, task_data: Dict) -> Dict:
        with httpx.Client(base_url=self.base_url) as client:
            resp = client.put(f"tasks/{task_id}", json=task_data, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

    def delete_task(self, task_id: str) -> Dict:
        with httpx.Client(base_url=self.base_url) as client:
            resp = client.delete(f"tasks/{task_id}", headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

    def get_tasks(self, context: Optional[str] = None, active: Optional[bool] = None, target_date: Optional[Union[date, str]] = None) -> List[Dict]:
        params = {}
        if context:
            params["context"] = context
        if active is not None:
            params["active"] = str(active).lower()
            
        with httpx.Client(base_url=self.base_url) as client:
            resp = client.get("tasks", params=params, headers=self._get_headers())
            resp.raise_for_status()
            tasks = resp.json()

            if target_date:
                t_date_str = target_date.isoformat() if isinstance(target_date, date) else target_date
                # Fetch schedule to get execution status for this date
                sched_params = {"start_date": t_date_str, "end_date": t_date_str}
                sched_resp = client.get("schedule", params=sched_params, headers=self._get_headers())
                if sched_resp.ok:
                    schedule = sched_resp.json()
                    status_map = {}
                    for day_data in schedule:
                        if day_data["date"] == t_date_str:
                            for t in day_data["tasks"]:
                                status_map[t["task_id"]] = t["status"]
                    
                    for task in tasks:
                        task["status"] = status_map.get(task["task_id"], "todo")
            
            return tasks

    def calculate_load(self, target_date: date) -> Dict:
        with httpx.Client(base_url=self.base_url) as client:
            resp = client.get(f"calculate/{target_date.isoformat()}", headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

    def create_exception(self, exception_data: Dict) -> Dict:
        with httpx.Client(base_url=self.base_url) as client:
            resp = client.post("exceptions", json=exception_data, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

    def get_heatmap(self, start: date, end: date) -> List[Dict]:
        params = {"start": start.isoformat(), "end": end.isoformat()}
        with httpx.Client(base_url=self.base_url) as client:
            resp = client.get("heatmap", params=params, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

    def get_trends(self, weeks: int = 12, start_date: Optional[date] = None) -> Dict:
        params = {"weeks": weeks}
        if start_date:
            params["start_date"] = start_date.isoformat()
        with httpx.Client(base_url=self.base_url) as client:
            resp = client.get("trends", params=params, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

    def get_context_distribution(self, start: date, end: date) -> Dict:
        params = {"start": start.isoformat(), "end": end.isoformat()}
        with httpx.Client(base_url=self.base_url) as client:
            resp = client.get("context-distribution", params=params, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

    def bulk_delete_tasks(self, task_ids: List[str]) -> Dict:
        with httpx.Client(base_url=self.base_url) as client:
            resp = client.post("tasks/bulk-delete", json={"task_ids": task_ids}, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

    def bulk_update_active(self, task_ids: List[str], active: bool) -> Dict:
        with httpx.Client(base_url=self.base_url) as client:
            resp = client.post("tasks/bulk-update-active", json={"task_ids": task_ids, "active": active}, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

    def upload_tasks_csv(self, file_content: bytes, filename: str) -> Dict:
        """Upload CSV file for server-side task creation"""
        with httpx.Client(base_url=self.base_url) as client:
            # We need to explicitly set timeout for large file uploads
            files = {"file": (filename, file_content, "text/csv")}
            resp = client.post("tasks/upload-csv", files=files, headers=self._get_headers(), timeout=30.0)
            resp.raise_for_status()
            return resp.json()

    def get_schedule(self, start_date: Union[date, str], end_date: Union[date, str]) -> List[Dict]:
        """Get daily schedule from LBS service."""
        params = {
            "start_date": start_date.isoformat() if isinstance(start_date, date) else start_date,
            "end_date": end_date.isoformat() if isinstance(end_date, date) else end_date
        }
        with httpx.Client(base_url=self.base_url) as client:
            resp = client.get("schedule", params=params, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

    def force_expand(self, start_date: date, end_date: date) -> Dict:
        """Force trigger task expansion for a range."""
        params = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat()
        }
        with httpx.Client(base_url=self.base_url) as client:
            resp = client.post("expand", params=params, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

    def toggle_task_completion(self, task_id: str, target_date: Union[date, str], status: Union[bool, TaskStatus] = TaskStatus.DONE) -> Dict:
        """
        Record a specific task execution status for a particular date.
        """
        date_str = target_date.isoformat() if isinstance(target_date, date) else target_date
        
        # Convert boolean to Enum for backward compatibility or ease of use
        if isinstance(status, bool):
            status_val = TaskStatus.DONE if status else TaskStatus.TODO
        else:
            status_val = status
            
        with httpx.Client(base_url=self.base_url) as client:
            resp = client.post(f"tasks/{task_id}/complete", json={
                "target_date": date_str, 
                "status": status_val.value if isinstance(status_val, TaskStatus) else status_val
            }, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

    def get_task_history(self, task_id: str, start_date: Union[date, str], end_date: Union[date, str]) -> List[Dict]:
        """Fetch execution logs for a specific task."""
        params = {
            "start_date": start_date.isoformat() if isinstance(start_date, date) else start_date,
            "end_date": end_date.isoformat() if isinstance(end_date, date) else end_date
        }
        with httpx.Client(base_url=self.base_url) as client:
            resp = client.get(f"tasks/{task_id}/history", params=params, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()
