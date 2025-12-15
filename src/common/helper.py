import random
from datetime import datetime
from fastapi import HTTPException

base_url = "http://localhost:8000"

import jwt
from src.configure.settings import settings

# Store the number of clicks each short URL has received.


def generate_self_short_ulr(url: str) -> str:
    random_slug = "".join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=6))
    return f"{base_url}/short.ly/{random_slug}"


def generate_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


async def generate_token(user: dict):
    token = jwt.encode(user, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return token


async def decode_token(token: str):
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        if "exp" in payload and payload["exp"] < int(datetime.utcnow().timestamp()):
            return {"error": "Your session has expired. Please log in again."}
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401, detail="Your session has expired. Please log in again."
        )
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def generate_unique_id(prefix: str, length: int = 20) -> str:
    random_id = "".join(
        random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=length)
    )
    return f"{prefix}_{random_id}"
