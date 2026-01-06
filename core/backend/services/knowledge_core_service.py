
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from models.database import ServiceRegistry
from utils.encryption import decrypt_string
from .knowledge_core.client import KnowledgeCoreClient
from .knowledge_core.models import IngestResponse, ContextResponse

class KnowledgeCoreService:
    """
    Wrapper service for KnowledgeCore integration in VisionArk.
    Handles service discovery from ServiceRegistry and provides simplified API.
    """

    def __init__(self, db: AsyncSession, user_id: str):
        self.db = db
        self.user_id = user_id
        self.client: Optional[KnowledgeCoreClient] = None

    async def _initialize_client(self):
        """Fetch KnowledgeCore config and initialize client"""
        try:
            from sqlalchemy import select
            result = await self.db.execute(
                select(ServiceRegistry).filter(
                    ServiceRegistry.user_id == self.user_id,
                    ServiceRegistry.service_name == "knowledge_core",
                    ServiceRegistry.is_active == True
                )
            )
            service = result.scalars().first()

            if service:
                api_key = None
                if service.api_key_encrypted:
                    try:
                        api_key = decrypt_string(service.api_key_encrypted)
                    except Exception as e:
                        print(f"[KnowledgeCoreService] Failed to decrypt API key: {e}")
                
                self.client = KnowledgeCoreClient(base_url=service.base_url)
                if api_key:
                    self.client.set_api_key(api_key)
                print(f"[KnowledgeCoreService] Initialized for user {self.user_id} at {service.base_url}")
            else:
                print(f"[KnowledgeCoreService] No active 'knowledge_core' service found for user {self.user_id}")
        except Exception as e:
            print(f"[KnowledgeCoreService] Initialization error: {e}")

    async def ingest_message(self, text: str, role: str, scope: str = "global", agent_id: Optional[str] = None) -> Optional[str]:
        """Ingest a chat message into KnowledgeCore"""
        if not self.client:
            await self._initialize_client()
            if not self.client: return None

        try:
            source = f"visionark_{role}"
            response = await self.client.ingest_text(
                text=text,
                source=source,
                scope=scope,
                agent_id=agent_id
            )
            return response.ingest_id
        except Exception as e:
            print(f"[KnowledgeCoreService] Ingestion error: {e}")
            return None

    async def get_context(self, query: str, app_context: Optional[dict] = None, agent_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieve context from KnowledgeCore for a given query"""
        if not self.client:
            await self._initialize_client()
            if not self.client: return None

        try:
            response = await self.client.get_context(
                query=query,
                include_global=True,
                app_context=app_context
            )
            return response.context
        except Exception as e:
            print(f"[KnowledgeCoreService] Context retrieval error: {e}")
            return None
