import httpx
import os
from datetime import date
from typing import List, Optional, Dict
from pydantic import BaseModel

class LBSClient:
    """
    Client for interacting with the LBS Microservice.
    Delegates all load balancing logic to the standalone service.
    """
    def __init__(self, base_url: str = None, api_key: str = None, token: str = None):
        default_url = os.getenv("LBS_SERVICE_URL", "http://localhost:8100/api/lbs")
        # In Docker, localhost refers to the container. Use host.docker.internal for the host LBS.
        if "localhost" in default_url and os.path.exists("/.dockerenv"):
            default_url = default_url.replace("localhost", "host.docker.internal")
            
        self.base_url = base_url or default_url
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
            headers["x-api-key"] = self.api_key
        
        # Prefer JWT token propagation
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        
        return headers

    def get_dashboard(self, start_date: Optional[date] = None) -> Dict:
        params = {}
        if start_date:
            params["start_date"] = start_date.isoformat()
        
        with httpx.Client(base_url=self.base_url) as client:
            # Note: Removal of leading / to join with base_url correctly if it has path
            resp = client.get("dashboard", params=params, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

    def create_task(self, task_data: Dict) -> Dict:
        with httpx.Client(base_url=self.base_url) as client:
            # The microservice expects /tasks not /lbs/tasks assuming the prefix in microservice
            # Wait, our microservice has prefix /api/lbs or /api/v1/lbs?
            # In LBS/src/main.py: app.include_router(routes.router, prefix=settings.API_V1_STR)
            # settings.API_V1_STR = "/api/v1"
            # routes.router prefix in routes.py is /lbs
            # So it's /api/v1/lbs/tasks
            resp = client.post("tasks", json=task_data, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

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

    def get_tasks(self, context: Optional[str] = None) -> List[Dict]:
        params = {}
        if context:
            params["context"] = context
        with httpx.Client(base_url=self.base_url) as client:
            resp = client.get("tasks", params=params, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

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
