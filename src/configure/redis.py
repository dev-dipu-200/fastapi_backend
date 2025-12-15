import redis.asyncio as redis
from src.configure.settings import settings
from urllib.parse import urlparse

REDIS_CHANNEL = "user_updates"
redis_client = None


async def init_redis():
    global redis_client
    if redis_client is None:
        # Parse Redis URL to extract host, port, and password
        redis_url = settings.REDIS_URL
        parsed = urlparse(redis_url)

        # Extract host and port
        host = parsed.hostname or "localhost"
        port = parsed.port or 6379
        password = parsed.password

        # Initialize Redis client
        redis_client = redis.Redis(
            host=host,
            port=port,
            password=password,
            decode_responses=True
        )


async def get_redis_client() -> redis.Redis:
    if redis_client is None:
        await init_redis()
    return redis_client
