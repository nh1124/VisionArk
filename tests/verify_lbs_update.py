import asyncio
import unittest
from unittest.mock import AsyncMock, patch, MagicMock
import sys
import os

# Add project root to sys.path
PROJECT_ROOT = os.path.join(os.getcwd(), "core", "backend")
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

class TestLBSClientUpdate(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Mock settings before importing LBSClient
        self.mock_settings = MagicMock()
        self.mock_settings.lbs_service_url = "http://mock-lbs:8100/api/lbs"
        self.mock_settings.atmos_service_key = "mock-service-key"
        self.mock_settings.atmos_env = "prod"
        self.mock_settings.atmos_default_user_id = "test-user"
        
        # Patch configuration before import
        with patch.dict('sys.modules', {'config': MagicMock(settings=self.mock_settings)}):
            from services.lbs_client import LBSClient, TaskStatus
            self.LBSClient = LBSClient
            self.TaskStatus = TaskStatus

        self.client = self.LBSClient(
            base_url="http://localhost:8100/api/lbs",
            api_key="test-api-key"
        )

    @patch('httpx.AsyncClient.request', new_callable=AsyncMock)
    async def test_list_tasks_renaming(self, mock_request):
        """Verify that list_tasks calls the correct endpoint."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"task_id": "T1"}]
        mock_resp.raise_for_status = MagicMock()
        mock_request.return_value = mock_resp
        
        await self.client.list_tasks(context="work")
        
        # Check call args
        args, kwargs = mock_request.call_args
        self.assertEqual(args[0], "GET")
        self.assertEqual(args[1], "tasks")
        self.assertEqual(kwargs['params']['context'], "work")
        
        # Verify headers (no X-SERVICE-KEY, has X-API-KEY)
        headers = kwargs['headers']
        self.assertEqual(headers["X-API-KEY"], "test-api-key")
        self.assertNotIn("X-SERVICE-KEY", headers)

    @patch('httpx.AsyncClient.request', new_callable=AsyncMock)
    async def test_toggle_task_completion(self, mock_request):
        """Verify toggle_task_completion calls the correct endpoint."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"success": True}
        mock_resp.raise_for_status = MagicMock()
        mock_request.return_value = mock_resp
        
        await self.client.toggle_task_completion("T1", "2026-01-11", self.TaskStatus.DONE)
        
        args, kwargs = mock_request.call_args
        self.assertEqual(args[0], "POST")
        self.assertEqual(args[1], "tasks/T1/complete")
        self.assertEqual(kwargs['json']['status'], "done")

    @patch('httpx.AsyncClient.request', new_callable=AsyncMock)
    async def test_get_heatmap_statuses(self, mock_request):
        """Verify get_heatmap passes statuses correctly."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_resp.raise_for_status = MagicMock()
        mock_request.return_value = mock_resp
        
        await self.client.get_heatmap("2026-01-01", "2026-01-07", statuses=[self.TaskStatus.DONE])
        
        args, kwargs = mock_request.call_args
        self.assertEqual(kwargs['params']['status'], ["done"])

async def main():
    unittest.main()

if __name__ == "__main__":
    asyncio.run(main())
