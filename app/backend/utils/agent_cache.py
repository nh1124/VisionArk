"""
Agent cache with TTL/LRU eviction for multi-user support
"""
import time
from collections import OrderedDict
from threading import Lock
from typing import Dict, Any, Optional


class TTLLRUCache:
    """
    Thread-safe LRU cache with TTL (Time To Live) eviction.
    
    Used for caching per-user agent instances to avoid memory growth.
    
    Args:
        max_size: Maximum number of items in cache (default: 100)
        ttl_seconds: Time to live in seconds (default: 1 hour)
    """
    
    def __init__(self, max_size: int = 100, ttl_seconds: int = 3600):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._lock = Lock()
    
    def get(self, key: str) -> Optional[Any]:
        """Get item from cache, returns None if not found or expired."""
        with self._lock:
            if key not in self._cache:
                return None
            
            value, timestamp = self._cache[key]
            
            # Check if expired
            if time.time() - timestamp > self.ttl_seconds:
                del self._cache[key]
                return None
            
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            return value
    
    def set(self, key: str, value: Any) -> None:
        """Set item in cache with current timestamp."""
        with self._lock:
            # Remove if exists (to update timestamp)
            if key in self._cache:
                del self._cache[key]
            
            # Evict LRU items if at capacity
            while len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)
            
            self._cache[key] = (value, time.time())
    
    def remove(self, key: str) -> bool:
        """Remove item from cache. Returns True if removed."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def clear(self) -> None:
        """Clear all items from cache."""
        with self._lock:
            self._cache.clear()
    
    def size(self) -> int:
        """Return number of items in cache."""
        with self._lock:
            return len(self._cache)
    
    def cleanup_expired(self) -> int:
        """Remove all expired items. Returns count removed."""
        removed = 0
        current_time = time.time()
        
        with self._lock:
            expired_keys = [
                key for key, (_, timestamp) in self._cache.items()
                if current_time - timestamp > self.ttl_seconds
            ]
            for key in expired_keys:
                del self._cache[key]
                removed += 1
        
        return removed


# Global agent caches
# Hub agents: keyed by user_id
# Spoke agents: keyed by "{user_id}:{spoke_name}"
_hub_agent_cache = TTLLRUCache(max_size=100, ttl_seconds=3600)  # 1 hour TTL
_spoke_agent_cache = TTLLRUCache(max_size=500, ttl_seconds=1800)  # 30 min TTL


def get_hub_agent_cache() -> TTLLRUCache:
    """Get the hub agent cache instance."""
    return _hub_agent_cache


def get_spoke_agent_cache() -> TTLLRUCache:
    """Get the spoke agent cache instance."""
    return _spoke_agent_cache
