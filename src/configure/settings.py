import os
from functools import lru_cache

try:
    from dotenv import load_dotenv
    # Try to load .env file, but don't fail if it doesn't exist
    load_dotenv()
except ImportError:
    # python-dotenv is not installed, skip loading
    pass

# ============================================
# HARDCODED DEFAULT VALUES (Fallback Configuration)
# ============================================
# These values are used when environment variables are not set
# For production, override these with proper environment variables

DEFAULT_CONFIG = {
    # Security Settings
    "SECRET_KEY": "Sv/w?/T@^CN8RR$08^I7Tss6'j78it-CHANGE-THIS-IN-PRODUCTION",
    "ALGORITHM": "HS256",
    "ACCESS_TOKEN_EXPIRE_MINUTES": "30",

    # Database Settings
    "POSTGRES_SQL_URL": "postgresql://dipu:dipu@localhost:5432/fastapi_db",
    "MONGODB_URL": "mongodb://localhost:27017",
    "MONGODB_DB_NAME": "chat_db",

    # Redis Settings
    "REDIS_URL": "redis://localhost:6379",

    # Celery Settings
    "CELERY_BROKER_URL": "amqp://guest:guest@localhost:5672//",
    "CELERY_RESULT_BACKEND": "rpc://",

    # API Keys (placeholder - should be overridden in production)
    "OPENAI_API_KEY": "",
    "HF_API_KEY": "",

    # OAuth Credentials
    "GOOGLE_CLIENT_SECRET_PATH": "credentials/credentials.json",
    "OUTLOOK_CLIENT_ID": "",
    "OUTLOOK_TENANT_ID": "",
    "OUTLOOK_CLIENT_SECRET": "",
    "GROQ_API_KEY": "",

    # Environment
    "ENVIRONMENT": "development",
}

@lru_cache(maxsize=1)
def get_settings():
    return Settings()

class Settings:
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    POSTGRES_SQL_URL: str
    MONGODB_URL: str
    MONGODB_DB_NAME: str
    REDIS_URL: str
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str
    OPENAI_API_KEY: str
    HF_API_KEY: str
    GOOGLE_CLIENT_SECRET_PATH: str
    OUTLOOK_CLIENT_ID: str
    OUTLOOK_TENANT_ID: str
    OUTLOOK_CLIENT_SECRET: str
    ENVIRONMENT: str
    GROQ_API_KEY: str

    def __init__(self):
        # Load all settings with hardcoded fallbacks
        self.SECRET_KEY = self._get_env("SECRET_KEY", DEFAULT_CONFIG["SECRET_KEY"])
        self.ALGORITHM = self._get_env("ALGORITHM", DEFAULT_CONFIG["ALGORITHM"])

        access_token_expire = self._get_env(
            "ACCESS_TOKEN_EXPIRE_MINUTES",
            DEFAULT_CONFIG["ACCESS_TOKEN_EXPIRE_MINUTES"]
        )
        try:
            self.ACCESS_TOKEN_EXPIRE_MINUTES = int(access_token_expire)
        except ValueError:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be an integer")

        # Database URLs
        postgres_url = self._get_env("POSTGRES_SQL_URL", DEFAULT_CONFIG["POSTGRES_SQL_URL"])
        # Ensure asyncpg is used for async operations
        self.POSTGRES_SQL_URL = postgres_url.replace("postgresql://", "postgresql+asyncpg://")

        self.MONGODB_URL = self._get_env("MONGODB_URL", DEFAULT_CONFIG["MONGODB_URL"])
        self.MONGODB_DB_NAME = self._get_env("MONGODB_DB_NAME", DEFAULT_CONFIG["MONGODB_DB_NAME"])

        # Redis
        self.REDIS_URL = self._get_env("REDIS_URL", DEFAULT_CONFIG["REDIS_URL"])

        # Celery
        self.CELERY_BROKER_URL = self._get_env("CELERY_BROKER_URL", DEFAULT_CONFIG["CELERY_BROKER_URL"])
        self.CELERY_RESULT_BACKEND = self._get_env("CELERY_RESULT_BACKEND", DEFAULT_CONFIG["CELERY_RESULT_BACKEND"])

        # API Keys
        self.OPENAI_API_KEY = self._get_env("OPENAI_API_KEY", DEFAULT_CONFIG["OPENAI_API_KEY"])
        self.HF_API_KEY = self._get_env("HF_API_KEY", DEFAULT_CONFIG["HF_API_KEY"])
        self.GROQ_API_KEY = self._get_env("GROQ_API_KEY", DEFAULT_CONFIG["GROQ_API_KEY"])

        # OAuth Credentials
        self.GOOGLE_CLIENT_SECRET_PATH = self._get_env(
            "GOOGLE_CLIENT_SECRET_PATH",
            DEFAULT_CONFIG["GOOGLE_CLIENT_SECRET_PATH"]
        )
        self.OUTLOOK_CLIENT_ID = self._get_env("OUTLOOK_CLIENT_ID", DEFAULT_CONFIG["OUTLOOK_CLIENT_ID"])
        self.OUTLOOK_TENANT_ID = self._get_env("OUTLOOK_TENANT_ID", DEFAULT_CONFIG["OUTLOOK_TENANT_ID"])
        self.OUTLOOK_CLIENT_SECRET = self._get_env("OUTLOOK_CLIENT_SECRET", DEFAULT_CONFIG["OUTLOOK_CLIENT_SECRET"])

        # Environment
        self.ENVIRONMENT = self._get_env("ENVIRONMENT", DEFAULT_CONFIG["ENVIRONMENT"])

    def _get_env(self, key: str, default: str) -> str:
        """Get environment variable with fallback to default value."""
        value = os.getenv(key)
        if value is None or value == "":
            return default
        return value

settings = get_settings()