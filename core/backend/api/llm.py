"""LLM model catalog API."""
from fastapi import APIRouter, Depends
from domains.identity.auth import resolve_identity, Identity
from infrastructure.llm.model_catalog import catalog_to_dict

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.get("/models")
async def get_model_catalog(_: Identity = Depends(resolve_identity)):
    """利用可能なモデル一覧を返す。認証済みユーザーのみ。"""
    return catalog_to_dict()
