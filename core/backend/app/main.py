"""
FastAPI main application
AI TaskManagement OS Backend
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from shared.logger import setup_logging
setup_logging()

from shared.database import init_database
from api import agents, commands, rag, context, files, auth, settings as settings_api, export, notes
from api import decomposer, suggestions, scheduler, approvals, automation, notifications
from api import monitoring
from api import workspace as workspace_api
from api.native import native_router, runs_router
from api.definitions import router as definitions_router
from api.llm import router as llm_router
from api.long_running_jobs import router as long_running_jobs_router
from va_sdk.discovery import include_integration_routers

from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup"""
    print("Initializing AI TaskManagement OS...")
    print(f"   Environment: {settings.atmos_env}")
    print(f"   Bind: {settings.host}:{settings.backend_port}")
    
    if settings.atmos_env == "prod" and settings.atmos_api_key_pepper == "dev_pepper_change_in_prod":
        print("WARNING: ATMOS_API_KEY_PEPPER not changed from default in production!")
    
    init_database()  # Schema creation + migrations
    print("Database initialized")

    # Sync Agent Skills - DEPRECATED
    # from domains.automation.skills import init_skills
    # await init_skills()
    
    yield
    print("Shutting down...")


# Create FastAPI app
app = FastAPI(
    title="Vision Ark API",
    description="Orchestrator-Member architecture task management with LBS + RAG + Context Management",
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
        "http://localhost:8001",
        "tauri://localhost",
        "http://tauri.localhost",
        "http://localhost:1420"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)  # Auth first (no auth required for register)

# Dynamic Integration Discovery
include_integration_routers(app)

app.include_router(agents.router)
app.include_router(commands.router)
app.include_router(rag.router)
app.include_router(context.router)
app.include_router(files.files_router)  # Unified file management endpoints
app.include_router(settings_api.router)
app.include_router(decomposer.router)
app.include_router(suggestions.router)
app.include_router(export.router)
app.include_router(scheduler.router)
app.include_router(approvals.router)
app.include_router(automation.router)
app.include_router(monitoring.router)
app.include_router(notes.router)
app.include_router(notifications.router)
app.include_router(workspace_api.workspace_router)
app.include_router(native_router)
app.include_router(runs_router)
app.include_router(definitions_router)
app.include_router(llm_router)
app.include_router(long_running_jobs_router)


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
    # If workers > 1, reload MUST be False
    reload = settings.backend_workers == 1
    uvicorn.run(
        "main:app", 
        host=settings.host, 
        port=settings.backend_port, 
        reload=reload,
        workers=settings.backend_workers
    )
