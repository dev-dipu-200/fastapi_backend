from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from motor.motor_asyncio import AsyncIOMotorClient
from src.configure.settings import settings

# PostgreSQL Configuration
engine = create_async_engine(
    settings.POSTGRES_SQL_URL, 
    pool_size=5, 
    max_overflow=10, 
    pool_timeout=30, 
    echo=False
)
Base = declarative_base()
AsyncSessionLocal = async_sessionmaker(
    autocommit=False, 
    autoflush=False, 
    bind=engine, 
    class_=AsyncSession
)

async def get_db():
    async with AsyncSessionLocal() as db:
        yield db
    

# MongoDB Configuration
MONGO_URI = settings.MONGODB_URL
MONGO_DB_NAME = settings.MONGODB_DB_NAME
mongo_client = None

async def init_mongo():
    global mongo_client
    if mongo_client is None:
        mongo_client = AsyncIOMotorClient(MONGO_URI)

async def get_mongo_db():
    if mongo_client is None:
        await init_mongo()
    return mongo_client[MONGO_DB_NAME]