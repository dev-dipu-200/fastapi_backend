import os
from dotenv import load_dotenv
from functools import lru_cache
from typing import Optional

load_dotenv()

@lru_cache(maxsize=1)
def get_settings():
    return Settings()

class Settings:
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    POSTGRES_SQL_URL: str
    MONGODB_URL: str

    def __init__(self):
        self.SECRET_KEY = self._get_required_env("SECRET_KEY")
        self.ALGORITHM = self._get_required_env("ALGORITHM")
        access_token_expire = os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
        try:
            self.ACCESS_TOKEN_EXPIRE_MINUTES = int(access_token_expire)
        except ValueError:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be an integer")
        self.POSTGRES_SQL_URL = os.getenv(
            "POSTGRES_SQL_URL", 
            "postgresql+asyncpg://dipu:dipu@localhost:5432/fastapi_db"
        ).replace("postgresql://", "postgresql+asyncpg://")
        self.MONGODB_URL = self._get_required_env(
            "MONGODB_URL", 
            default="mongodb://localhost:27017/chat_db"
        )

    def _get_required_env(self, key: str, default: Optional[str] = None) -> str:
        value = os.getenv(key, default)
        if value is None:
            raise ValueError(f"Missing required environment variable: {key}")
        return value

settings = get_settings()