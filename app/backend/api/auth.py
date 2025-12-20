"""
Authentication API endpoints for self-service key registration
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
import uuid

from models.database import APIKey
from services.auth import get_db
from utils.security import generate_api_key, hash_api_key

router = APIRouter(prefix="/api/auth", tags=["Auth"])


class RegisterRequest(BaseModel):
    name: str
    client_id: str


class RegisterResponse(BaseModel):
    api_key: str  # Only shown once!
    key_id: str
    client_id: str
    message: str


@router.post("/register", response_model=RegisterResponse)
async def register(
    req: RegisterRequest,
    db: Session = Depends(get_db)
):
    """
    Register a new user and generate an API key.
    
    Note: The API key is only shown once at registration.
    Store it securely!
    """
    # Generate a user ID for the new user
    user_id = str(uuid.uuid4())
    
    # Generate secure API key
    raw_key = generate_api_key()
    key_hash = hash_api_key(raw_key)
    
    # Create database record
    api_key = APIKey(
        id=str(uuid.uuid4()),
        key_hash=key_hash,
        user_id=user_id,
        client_id=req.client_id,
        name=req.name,
        scopes=["*"],  # Full access for registered users
        is_active=True
    )
    
    try:
        db.add(api_key)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create account: {str(e)}")
    
    return RegisterResponse(
        api_key=raw_key,
        key_id=api_key.id,
        client_id=req.client_id,
        message="Account created successfully! Save your API key - it won't be shown again."
    )
