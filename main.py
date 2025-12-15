from fastapi import FastAPI, WebSocket
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from src.api.home.router import router as api_router
from src.api.auth.router import router as auth_router
from src.chat_works.ws import websocket_listener, websocket_chat_endpoint
from src.configure.database import init_mongo
from src.configure.redis import init_redis
from src.configure.celery import celery_app
from src.configure.logging_config import logger
import uvicorn

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting application...")
    await init_mongo()
    await init_redis()
    celery_app.conf.broker_connection_retry_on_startup = True
    logger.info("Application started successfully")
    yield
    logger.info("Shutting down application...")

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router, prefix="/api")
app.include_router(api_router, prefix="/api")

@app.websocket("/api/notifications/")
async def notifications_ws(websocket: WebSocket):
    await websocket_listener(websocket)

@app.websocket("/api/chat/")
async def chat_ws(websocket: WebSocket):
    await websocket_chat_endpoint(websocket)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)