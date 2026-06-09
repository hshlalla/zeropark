import os
import json
import redis
from typing import Optional, Any

class RedisCache:
    """Singleton Redis Cache Manager."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisCache, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", 6379))
        
        try:
            self.client = redis.Redis(
                host=redis_host, 
                port=redis_port, 
                db=0, 
                decode_responses=True
            )
            # Test connection silently
            self.client.ping()
        except Exception as e:
            # Fallback to dummy client if redis is not available yet
            print(f"Redis connection failed: {e}. Caching disabled.")
            self.client = None

    def get(self, key: str) -> Optional[Any]:
        if not self.client:
            return None
        val = self.client.get(key)
        if val:
            try:
                return json.loads(val)
            except json.JSONDecodeError:
                return val
        return None

    def set(self, key: str, value: Any, ttl_seconds: int = 86400):
        """Set a value with default TTL of 24 hours."""
        if not self.client:
            return
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        self.client.setex(key, ttl_seconds, value)

    def delete(self, key: str):
        if self.client:
            self.client.delete(key)

redis_cache = RedisCache()
