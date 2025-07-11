# app/utils/async_cache.py
import asyncio
import time
import functools
import hashlib
import pickle
import threading
from typing import Any, Callable, Dict, Optional, Tuple, TypeVar, Awaitable
from pathlib import Path

# Type variables for generic typing
F = TypeVar('F', bound=Callable[..., Awaitable[Any]])
T = TypeVar('T')

class AsyncCache:
    """Thread-safe async cache with expiration support"""
    
    def __init__(self):
        self._cache: Dict[str, Tuple[Any, float]] = {}  # key -> (value, expires_at)
        self._lock = asyncio.Lock()
        self._sync_lock = threading.Lock()  # For sync operations
    
    def _generate_key(self, func_name: str, args: tuple, kwargs: dict) -> str:
        """Generate a unique cache key from function name and arguments"""
        key_data = {
            'func': func_name,
            'args': args,
            'kwargs': sorted(kwargs.items()) if kwargs else {}
        }
        
        try:
            serialized = pickle.dumps(key_data, protocol=pickle.HIGHEST_PROTOCOL)
            return hashlib.md5(serialized).hexdigest()
        except (pickle.PicklingError, TypeError):
            key_str = f"{func_name}_{str(args)}_{str(sorted(kwargs.items()) if kwargs else '')}"
            return hashlib.md5(key_str.encode()).hexdigest()
    
    async def get(self, key: str) -> Optional[Any]:
        """Get cached value if valid"""
        async with self._lock:
            if key in self._cache:
                value, expires_at = self._cache[key]
                if time.time() < expires_at:
                    return value
                else:
                    # Remove expired entry
                    del self._cache[key]
            return None
    
    async def set(self, key: str, value: Any, ttl: int) -> None:
        """Cache value with TTL in seconds"""
        async with self._lock:
            expires_at = time.time() + ttl
            self._cache[key] = (value, expires_at)
    
    def clear_sync(self, pattern: Optional[str] = None) -> int:
        """Synchronous cache clear"""
        with self._sync_lock:
            if pattern is None:
                count = len(self._cache)
                self._cache.clear()
                return count
            else:
                keys_to_remove = [k for k in self._cache.keys() if pattern in k]
                for key in keys_to_remove:
                    del self._cache[key]
                return len(keys_to_remove)
    
    def info_sync(self) -> Dict[str, Any]:
        """Synchronous cache info"""
        with self._sync_lock:
            current_time = time.time()
            total_entries = len(self._cache)
            expired_entries = sum(
                1 for _, expires_at in self._cache.values()
                if current_time >= expires_at
            )
            return {
                'total_entries': total_entries,
                'active_entries': total_entries - expired_entries,
                'expired_entries': expired_entries
            }

# Global async cache instance
_async_cache = AsyncCache()

def async_cache(ttl: int = 3600) -> Callable[[F], F]:
    """
    Async cache decorator for async functions
    
    Args:
        ttl: Time to live in seconds (default 1 hour)
    
    Example:
        @async_cache(ttl=300)
        async def get_fedex_access_token() -> str:
            # Your async token fetching logic
            return await fetch_token()
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = _async_cache._generate_key(func.__name__, args, kwargs)
            
            # Try to get from cache
            cached_result = await _async_cache.get(cache_key)
            if cached_result is not None:
                print(f"Using cached result for {func.__name__}")
                return cached_result
            
            # Cache miss - call original async function
            print(f"Fetching new result for {func.__name__}")
            result = await func(*args, **kwargs)
            
            # Store in cache
            await _async_cache.set(cache_key, result, ttl)
            
            return result
        
        # Add cache management methods (sync versions for easier use)
        wrapper.clear_cache = lambda: _async_cache.clear_sync(func.__name__)
        wrapper.cache_info = _async_cache.info_sync
        
        return wrapper
    
    return decorator

# Example implementation for FedEx token
@async_cache(ttl=3600)  # Cache for 1 hour
async def get_fedex_access_token() -> str:
    """
    Async version of FedEx token fetching with caching
    """
    import aiohttp
    
    url = "https://apis.fedex.com/oauth/token"
    
    form_data = {
        'grant_type': 'client_credentials',
        'client_id': 'your_client_id',
        'client_secret': 'your_client_secret'
    }
    
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=form_data, headers=headers) as response:
            response.raise_for_status()
            token_data = await response.json()
            return token_data['access_token']

# Alternative: Mixed sync/async approach
class TokenManager:
    """Token manager that works with both sync and async contexts"""
    
    def __init__(self):
        self._token: Optional[str] = None
        self._expires_at: float = 0
        self._lock = threading.Lock()
        self._async_lock = asyncio.Lock()
    
    def _is_valid(self) -> bool:
        return self._token is not None and time.time() < self._expires_at
    
    async def get_token_async(self) -> str:
        """Get token in async context"""
        async with self._async_lock:
            if self._is_valid():
                print("Using cached token (async)")
                return self._token
            
            print("Fetching new token (async)")
            token = await self._fetch_token_async()
            self._token = token
            self._expires_at = time.time() + 3600  # 1 hour
            return token
    
    def get_token_sync(self) -> str:
        """Get token in sync context"""
        with self._lock:
            if self._is_valid():
                print("Using cached token (sync)")
                return self._token
            
            print("Fetching new token (sync)")
            token = self._fetch_token_sync()
            self._token = token
            self._expires_at = time.time() + 3600  # 1 hour
            return token
    
    async def _fetch_token_async(self) -> str:
        """Async token fetching"""
        import aiohttp
        
        url = "https://apis.fedex.com/oauth/token"
        form_data = {
            'grant_type': 'client_credentials',
            'client_id': 'your_client_id',
            'client_secret': 'your_client_secret'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=form_data) as response:
                response.raise_for_status()
                token_data = await response.json()
                return token_data['access_token']
    
    def _fetch_token_sync(self) -> str:
        """Sync token fetching"""
        import requests
        
        url = "https://apis.fedex.com/oauth/token"
        form_data = {
            'grant_type': 'client_credentials',
            'client_id': 'your_client_id',
            'client_secret': 'your_client_secret'
        }
        
        response = requests.post(url, data=form_data)
        response.raise_for_status()
        token_data = response.json()
        return token_data['access_token']
    
    def clear_cache(self):
        """Clear cached token"""
        with self._lock:
            self._token = None
            self._expires_at = 0

# Global token manager instance
token_manager = TokenManager()

# Convenience functions
async def get_fedex_token() -> str:
    """Get FedEx token (async)"""
    return await token_manager.get_token_async()

def get_fedex_token_sync() -> str:
    """Get FedEx token (sync)"""
    return token_manager.get_token_sync()

# Example usage
async def main():
    """Example usage of async cached token"""
    print("=== Async Token Caching Example ===\n")
    
    # Method 1: Using async cache decorator
    print("1. Using async cache decorator:")
    token1 = await get_fedex_access_token()
    print(f"Token 1: {token1[:20]}...")
    
    token2 = await get_fedex_access_token()  # Should use cache
    print(f"Token 2: {token2[:20]}...")
    print(f"Same token? {token1 == token2}")
    print()
    
    # Method 2: Using token manager
    print("2. Using token manager:")
    token3 = await get_fedex_token()
    print(f"Token 3: {token3[:20]}...")
    
    token4 = await get_fedex_token()  # Should use cache
    print(f"Token 4: {token4[:20]}...")
    print(f"Same token? {token3 == token4}")
    print()
    
    # Cache management
    print("3. Cache info:")
    print(f"Decorator cache: {get_fedex_access_token.cache_info()}")
    
    print("\n4. Clearing caches:")
    get_fedex_access_token.clear_cache()
    token_manager.clear_cache()
    print("Caches cleared!")

if __name__ == "__main__":
    # Run the async example
    asyncio.run(main())