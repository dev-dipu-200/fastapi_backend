from sqlalchemy.sql import select
from src.models.user_model import User
from datetime import datetime, timedelta
from src.configure.database import get_db
from fastapi import HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.configure.settings import get_settings
from src.configure.redis import get_redis_client
from src.common.helper import generate_token, decode_token, generate_unique_id
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# OAuth2 scheme for token validation
oauth2_scheme = HTTPBearer()

async def get_current_user(
    token: HTTPAuthorizationCredentials = Depends(oauth2_scheme),
):
    try:
        payload = await decode_token(token.credentials)
        return payload
    except Exception as e:
        raise HTTPException(
            status_code=403, detail=f"Invalid authentication credentials: {str(e)}"
        )

async def create_user(payload=None, db: AsyncSession = Depends(get_db)):
    user_data = payload.dict()
    del user_data["confirm_password"]
    user_data["user_id"] = await generate_unique_id("user", 10)
    user = User(**user_data)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {"message": "User created successfully"}

async def login_user(payload=None, db: AsyncSession = Depends(get_db)):
    settings = get_settings()
    query = select(User).where(User.email == payload.email)
    result = await db.execute(query)
    user_data = result.scalars().first()
    
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")
    
    expiry_time = int(settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload_data = {
        "email": user_data.email,
        "role": user_data.role,
        "is_active": user_data.is_active,
        "exp": datetime.utcnow() + timedelta(minutes=expiry_time)
    }
    generated_token = await generate_token(payload_data)
    del payload_data["exp"]
    
    return {
        "user": payload_data,
        "token": generated_token,
        "message": "User logged in successfully",
    }

async def logout_user(
    payload: dict = None,
    db: AsyncSession = Depends(get_db),
    token: HTTPAuthorizationCredentials = Depends(oauth2_scheme)
):
    settings = get_settings()
    redis_client = await get_redis_client()
    expiry_time = int(settings.ACCESS_TOKEN_EXPIRE_MINUTES) * 60  # Convert to seconds
    await redis_client.setex(
        f"blacklist:token:{token.credentials}",
        expiry_time,
        "invalidated"
    )
    return {"message": "User logged out successfully"}