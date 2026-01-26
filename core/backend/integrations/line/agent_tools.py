from typing import Any, Optional
from pydantic import BaseModel, Field
from tools.base import BaseTool
from .client import get_line_client
from sqlalchemy.ext.asyncio import AsyncSession

class SendLineMessageArgs(BaseModel):
    text: str = Field(..., description="The message text to send to LINE")
    to_user_id: Optional[str] = Field(None, description="Optional LINE user ID. If not provided, uses the default from settings.")

class SendLineMessageTool(BaseTool):
    name = "send_line_message"
    description = (
        "Send a text message to a user via LINE. "
        "Use this for notifications or direct replies to the user's mobile device."
    )
    args_schema = SendLineMessageArgs

    async def run(self, text: str, to_user_id: Optional[str] = None, **kwargs) -> Any:
        db_session: AsyncSession = kwargs.get("db_session") or getattr(self, "context", {}).get("db_session")
        user_id: str = kwargs.get("user_id") or getattr(self, "context", {}).get("user_id")
        
        if not db_session or not user_id:
            return {"success": False, "message": "Context error: Missing session or user_id"}
            
        try:
            client = await get_line_client(user_id, db_session)
            if not client:
                return {"success": False, "message": "LINE integration not configured or inactive for this user."}
            
            # If to_user_id is not provided, try to get it from the client's config if we had it
            # But usually, it should be passed from the AI context or the service registry's default
            if not to_user_id:
                # 1. Fallback to the saved default in ServiceRegistry config
                from models.database import ServiceRegistry
                from sqlalchemy import select
                result = await db_session.execute(select(ServiceRegistry).filter(
                    ServiceRegistry.user_id == user_id,
                    ServiceRegistry.service_name == "line"
                ))
                service = result.scalars().first()
                if service and service.config:
                    to_user_id = service.config.get("default_to_user_id")
                
                # 2. Fallback to the user's linked ExternalIdentity
                if not to_user_id:
                    from models.database import ExternalIdentity
                    id_res = await db_session.execute(select(ExternalIdentity).filter(
                        ExternalIdentity.user_id == user_id,
                        ExternalIdentity.issuer == "line"
                    ))
                    identity = id_res.scalars().first()
                    if identity:
                        to_user_id = identity.subject
                        print(f"[SendLineMessageTool] Found linked identity: {to_user_id}")

            if not to_user_id:
                return {"success": False, "message": "No destination LINE User ID found. Please link your account by messaging the bot first, or set 'default_to_user_id' in settings."}

            await client.push_message(to_user_id, text)
            return {"success": True, "message": f"Successfully sent LINE message to {to_user_id}"}
            
        except Exception as e:
            return {"success": False, "message": f"Failed to send LINE message: {str(e)}"}
