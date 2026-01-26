import pkgutil
import importlib
from fastapi import FastAPI, APIRouter
from typing import List, Optional

def include_integration_routers(app: FastAPI):
    """
    Automatically discover and include FastAPI routers from the integrations directory.
    Scans for modules named 'api.py' within core/backend/integrations/[name]/.
    """
    import integrations
    
    print("[Discovery] Starting dynamic router discovery...")
    
    for loader, module_name, is_pkg in pkgutil.walk_packages(integrations.__path__, integrations.__name__ + "."):
        # We only care about .api submodules (e.g., integrations.line.api)
        if module_name.endswith(".api"):
            try:
                module = importlib.import_module(module_name)
                router = getattr(module, "router", None)
                
                if isinstance(router, APIRouter):
                    # Extract metadata from the module or fallback to defaults
                    # integrations.line.api -> line
                    integration_name = module_name.split('.')[-2]
                    
                    prefix = getattr(module, "ROUTER_PREFIX", f"/{integration_name}")
                    tags = getattr(module, "ROUTER_TAGS", [integration_name.title()])
                    
                    # Ensure prefix starts with /API if we want a global namespace, 
                    # but usually integrations are mounted under /api
                    full_prefix = f"/api{prefix}" if not prefix.startswith("/api") else prefix
                    
                    app.include_router(router, prefix=full_prefix, tags=tags)
                    print(f"[Discovery] ✅ Registered router for '{integration_name}' at {full_prefix}")
                else:
                    print(f"[Discovery] ⚠ Module {module_name} found but no 'router' (APIRouter) object exported.")
            except Exception as e:
                print(f"[Discovery] ❌ Failed to load {module_name}: {e}")

    print("[Discovery] Dynamic router discovery complete.")
