"""
FastAPI main application
AI TaskManagement OS Backend
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from models.database import init_database
from api import lbs, inbox, agents, commands, rag, context, files


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup"""
    print("🚀 Initializing AI TaskManagement OS...")
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
    allow_origins=["http://localhost:3000", "http://localhost:3001"],  # Next.js dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(lbs.router)
app.include_router(inbox.router)
app.include_router(agents.router)
app.include_router(commands.router)
app.include_router(rag.router)
app.include_router(context.router)
app.include_router(files.router)


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
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
