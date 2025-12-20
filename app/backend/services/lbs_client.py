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
    def __init__(self, base_url: str = None, api_key: str = None, user_id: str = "dev_user"):
        self.base_url = base_url or os.getenv("LBS_SERVICE_URL", "http://localhost:8300/api/v1")
        self.api_key = api_key or os.getenv("LBS_API_KEY")
        self.user_id = user_id
        
    def _get_headers(self):
        headers = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        # For development/legacy reason, we passed X-User-ID in our design
        headers["X-User-ID"] = self.user_id
        return headers

    def get_dashboard(self, start_date: Optional[date] = None) -> Dict:
        params = {}
        if start_date:
            params["start_date"] = start_date.isoformat()
        
        with httpx.Client(base_url=self.base_url) as client:
            resp = client.get("/lbs/dashboard", params=params, headers=self._get_headers())
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
            resp = client.post("/lbs/tasks", json=task_data, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

    def update_task(self, task_id: str, task_data: Dict) -> Dict:
        with httpx.Client(base_url=self.base_url) as client:
            resp = client.put(f"/lbs/tasks/{task_id}", json=task_data, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

    def delete_task(self, task_id: str) -> Dict:
        with httpx.Client(base_url=self.base_url) as client:
            resp = client.delete(f"/lbs/tasks/{task_id}", headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

    def get_tasks(self, context: Optional[str] = None) -> List[Dict]:
        params = {}
        if context:
            params["context"] = context
        with httpx.Client(base_url=self.base_url) as client:
            resp = client.get("/lbs/tasks", params=params, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

    def calculate_load(self, target_date: date) -> Dict:
        with httpx.Client(base_url=self.base_url) as client:
            resp = client.get(f"/lbs/calculate/{target_date.isoformat()}", headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

    def create_exception(self, exception_data: Dict) -> Dict:
        with httpx.Client(base_url=self.base_url) as client:
            resp = client.post("/lbs/exceptions", json=exception_data, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()
