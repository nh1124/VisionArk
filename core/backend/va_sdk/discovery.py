import pkgutil
import importlib
import json
import os
from fastapi import FastAPI, APIRouter
from typing import List, Optional, Dict, Any

# Global catalog store (in-memory cache)
INTEGRATION_CATALOG: List[Dict[str, Any]] = []

def discover_integration_models():
    """
    Search for models.py in each integration folder and import them.
    This registers the models with SQLAlchemy's Base.metadata.
    Should be called BEFORE init_database().
    """
    import integrations
    integrations_path = integrations.__path__[0]
    
    for name in os.listdir(integrations_path):
        dir_path = os.path.join(integrations_path, name)
        if not os.path.isdir(dir_path) or name.startswith("__"):
            continue
            
        models_path = os.path.join(dir_path, "models.py")
        if os.path.exists(models_path):
            try:
                importlib.import_module(f"integrations.{name}.models")
                print(f"[Discovery]   🗄️ Registered database models for '{name}'")
            except Exception as e:
                print(f"[Discovery]   ❌ Failed to load models for {name}: {e}")

def include_integration_routers(app: FastAPI):
    """
    Automatically discover and include FastAPI routers and manifests 
    from the integrations directory.
    """
    import integrations
    global INTEGRATION_CATALOG
    INTEGRATION_CATALOG = [] # Reset on startup
    
    print("[Discovery] Starting dynamic integration discovery...")
    
    # Get the base path of the integrations package
    integrations_path = integrations.__path__[0]
    
    # We want to iterate over the direct subdirectories (each represents an integration)
    for name in os.listdir(integrations_path):
        dir_path = os.path.join(integrations_path, name)
        if not os.path.isdir(dir_path) or name.startswith("__"):
            continue
            
        print(f"[Discovery] Inspecting integration: {name}")
        
        # 1. Load Manifest if exists
        manifest_path = os.path.join(dir_path, "manifest.json")
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                    INTEGRATION_CATALOG.append(manifest)
                    print(f"[Discovery]   📄 Loaded manifest for '{name}'")
            except Exception as e:
                print(f"[Discovery]   ❌ Failed to load manifest for {name}: {e}")
        
        # 2. Discover API/Router
        try:
            api_module_name = f"integrations.{name}.api"
            # Try to import api.py if it exists
            if os.path.exists(os.path.join(dir_path, "api.py")):
                module = importlib.import_module(api_module_name)
                router = getattr(module, "router", None)
                
                if isinstance(router, APIRouter):
                    prefix = getattr(module, "ROUTER_PREFIX", f"/{name}")
                    tags = getattr(module, "ROUTER_TAGS", [name.title()])
                    full_prefix = f"/api{prefix}" if not prefix.startswith("/api") else prefix
                    
                    app.include_router(router, prefix=full_prefix, tags=tags)
                    print(f"[Discovery]   ✅ Registered router at {full_prefix}")
        except Exception as e:
            # Not all integrations have an API
            pass

    print(f"[Discovery] Dynamic discovery complete. Total integrations in catalog: {len(INTEGRATION_CATALOG)}")

def get_integration_catalog() -> List[Dict[str, Any]]:
    """Return the list of discovered integration manifests."""
    return INTEGRATION_CATALOG
