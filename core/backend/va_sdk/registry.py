from typing import Callable, Dict, Any, List, Optional
import functools

class Registry:
    def __init__(self, name: str):
        self.name = name
        self._handlers: Dict[str, Callable] = {}
        
    def register(self, key: str):
        """Decorator to register a function as a handler for a specific key."""
        def decorator(func: Callable):
            print(f"[{self.name}] Registering handler for: {key}")
            self._handlers[key] = func
            
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                return await func(*args, **kwargs)
            return wrapper
        return decorator

    def get(self, key: str) -> Optional[Callable]:
        """Retrieve a handler by key."""
        return self._handlers.get(key)
        
    def get_all(self) -> Dict[str, Callable]:
        """Retrieve all handlers."""
        return self._handlers

# Global Registries
task_registry = Registry("TaskRegistry")
aes_registry = Registry("AESRegistry")
reply_registry = Registry("ReplyRegistry")
