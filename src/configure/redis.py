import redis.asyncio as redis

REDIS_CHANNEL = "user_updates"
redis_client = None


async def init_redis():
    global redis_client
    if redis_client is None:
        redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True)


async def get_redis_client() -> redis.Redis:
    if redis_client is None:
        await init_redis()
    return redis_client
