"""
FastAPI main application
AI TaskManagement OS Backend
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from models.database import init_database
from api import lbs, inbox, agents, commands, rag, context, files, auth, settings as settings_api

from config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup"""
    print("🚀 Initializing AI TaskManagement OS...")
    print(f"   Environment: {settings.atmos_env}")
    print(f"   API Key Required: {settings.atmos_require_api_key}")
    print(f"   Legacy Key Enabled: {settings.atmos_enable_legacy_env_key}")
    print(f"   Bind: {settings.host}:{settings.backend_port}")
    
    if settings.atmos_env == "prod" and settings.atmos_api_key_pepper == "dev_pepper_change_in_prod":
        print("⚠️  WARNING: ATMOS_API_KEY_PEPPER not changed from default in production!")
    
    init_database()  # Use automatic path detection
    print("✅ Database initialized")
    yield
    print("👋 Shutting down...")


# Create FastAPI app
app = FastAPI(
    title="AI TaskManagement OS API",
    description="Hub-Spoke architecture task management with LBS + RAG + Context Management",
    version="0.2.0 (Phase 2)",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"http://localhost:{settings.frontend_port}",
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:8001"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)  # Auth first (no auth required for register)
app.include_router(lbs.router)
app.include_router(inbox.router)
app.include_router(agents.router)
app.include_router(commands.router)
app.include_router(rag.router)
app.include_router(context.router)
app.include_router(files.router)
app.include_router(settings_api.router)


@app.get("/")
def root():
    """Root endpoint"""
    return {
        "message": "AI TaskManagement OS API",
        "version": "0.1.0 (MVP)",
        "docs": "/docs"
    }


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.host, port=settings.backend_port, reload=True)
