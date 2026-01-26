from fastapi import APIRouter, Request, HTTPException
from typing import Dict, Any

router = APIRouter(prefix="/api/webhooks", tags=["Webhooks"])

@router.get("")
async def webhook_root():
    """Status endpoint for webhooks"""
    return {"status": "listening", "info": "VisionArk Webhook Gateway"}

# Note: Individual integrations should register sub-routers or specific endpoints here
from .line import line_router

router.include_router(line_router, prefix="/line")
