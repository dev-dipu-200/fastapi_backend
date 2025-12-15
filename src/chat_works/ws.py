import json
import base64
import logging
import asyncio
from typing import Dict
from bson import ObjectId
from datetime import datetime
from pydantic import BaseModel
from sqlalchemy import or_, func
from sqlalchemy.sql import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import WebSocket, WebSocketDisconnect, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from urllib.parse import quote, parse_qs
from async_lru import alru_cache
from src.models.user_model import User
from src.common.helper import decode_token
from src.configure.database import get_mongo_db, get_db
from src.configure.redis import get_redis_client, REDIS_CHANNEL

# Configure logging with debug level
logger = logging.getLogger(__name__)

# OAuth2 scheme for token validation
oauth2_scheme = HTTPBearer()

# Pydantic model for user response
class UserResponse(BaseModel):
    id: str
    email: str
    role: str
    is_status: str
    last_seen: str | None
    unread_count: int
    room_id: str | None

# WebSocket manager using Redis pub/sub
class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, Dict[str, WebSocket]] = {}

    async def connect(self, websocket: WebSocket, email: str):
        await websocket.accept()
        if email not in self.active_connections:
            self.active_connections[email] = {}
        connection_id = str(id(websocket))
        self.active_connections[email][connection_id] = websocket

        redis_client = await get_redis_client()
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(f"{REDIS_CHANNEL}:{email}")
        asyncio.create_task(self.listen_to_pubsub(pubsub, email, connection_id))

    async def disconnect(self, websocket: WebSocket, email: str):
        connection_id = str(id(websocket))
        if email in self.active_connections and connection_id in self.active_connections[email]:
            del self.active_connections[email][connection_id]
            if not self.active_connections[email]:
                del self.active_connections[email]

    async def listen_to_pubsub(self, pubsub, email: str, connection_id: str):
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    if email in self.active_connections and connection_id in self.active_connections[email]:
                        websocket = self.active_connections[email][connection_id]
                        await websocket.send_text(message["data"])
        except Exception as e:
            logger.error(f"Pubsub error for {email}: {str(e)}")
        finally:
            await pubsub.unsubscribe(f"{REDIS_CHANNEL}:{email}")

    async def send_to_group(self, group: str, message: dict):
        redis_client = await get_redis_client()
        await redis_client.publish(f"{REDIS_CHANNEL}:{group}", json.dumps(message))

manager = WebSocketManager()

def get_safe_cache_key(prefix: str, email: str) -> str:
    safe_email = quote(email)
    return f"{prefix}_{safe_email}"

async def get_current_user_websocket(token: str):
    logger.debug(f"Received token: {token[:10] if token else None}...")
    if not token:
        logger.error("No token provided")
        raise HTTPException(status_code=403, detail="No token provided")
    try:
        token = token.strip().strip('"\'')
        logger.debug(f"Processed token: {token[:10]}...")
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        payload = await decode_token(credentials.credentials)
        logger.debug(f"Token validated, payload: {payload}")
        return payload
    except Exception as e:
        logger.error(f"Token validation failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=403, detail=f"Invalid authentication credentials: {str(e)}"
        )

async def websocket_chat_endpoint(websocket: WebSocket, token: str = None):
    query_string = websocket.scope.get('query_string', b'').decode()
    logger.debug(f"WebSocket connection attempt with scope: {websocket.scope}")
    logger.debug(f"Query string: {query_string}")

    if not token:
        logger.debug("Token parameter is None, attempting manual query string parsing")
        query_params = parse_qs(query_string)
        token_values = query_params.get('token', [])
        token = token_values[0] if token_values else None
        logger.debug(f"Manually parsed token: {token[:10] if token else None}...")

    if not token:
        logger.warning("No token provided in query parameter or parsed query string")
        raise HTTPException(status_code=403, detail="No token provided")

    try:
        user = await get_current_user_websocket(token)
    except HTTPException as e:
        logger.warning(f"Authentication failed: {e.detail}")
        raise e

    email = user.get('email')
    if not email:
        logger.warning("No email in token payload")
        raise HTTPException(status_code=403, detail="Invalid user data in token")

    if not user.get('is_active', True):
        logger.warning(f"User {email} is inactive")
        raise HTTPException(status_code=403, detail="User is inactive")

    logger.info(f"User {email} authenticated successfully")
    await manager.connect(websocket, email)

    redis_client = await get_redis_client()
    await redis_client.set(get_safe_cache_key("user_status", email), "online")
    await redis_client.set(get_safe_cache_key("user_last_seen", email), datetime.utcnow().isoformat())

    await websocket.send_json({
        "source": "connection",
        "data": {
            "message": "connected",
            "email": email,
            "timestamp": datetime.utcnow().isoformat(),
        },
    })

    await send_pending_messages(websocket, email)
    await receive_unread_message(websocket, email)

    try:
        while True:
            data = await websocket.receive_json()
            logger.debug(f"Received message from {email}: {data}")
            await handle_message(websocket, email, data)
    except WebSocketDisconnect:
        await manager.disconnect(websocket, email)
        await redis_client.set(get_safe_cache_key("user_status", email), "offline")
        await redis_client.set(
            get_safe_cache_key("user_last_seen", email),
            datetime.utcnow().isoformat(),
            ex=30 * 24 * 60 * 60,
        )
        await redis_client.publish(
            REDIS_CHANNEL,
            json.dumps({
                "source": "user.status",
                "data": {
                    "email": email,
                    "status": "offline",
                    "last_seen": datetime.utcnow().isoformat(),
                }
            })
        )
        logger.info(f"User {email} disconnected")
    except Exception as e:
        logger.error(f"WebSocket error for {email}: {str(e)}", exc_info=True)
        await send_error(websocket, "server_error", "Internal server error")
        await websocket.close()

async def handle_message(websocket: WebSocket, email: str, data: dict):
    try:
        source = data.get("source")
        if not source:
            raise ValueError("Missing message source")

        handler_name = f"receive_{source.replace('.', '_')}"
        handler = globals().get(handler_name)
        if not handler:
            raise ValueError(f"Unknown message source: {source}")

        logger.debug(f"Handling message source {source} for {email}")
        await handler(websocket, email, data)
    except ValueError as e:
        logger.warning(f"Invalid message from {email}: {str(e)}")
        await send_error(websocket, "invalid_request", str(e))
    except Exception as e:
        logger.error(f"Message handling error for {email}: {str(e)}", exc_info=True)
        await send_error(websocket, "server_error", "Internal server error")

async def send_error(websocket: WebSocket, error_type: str, message: str):
    await websocket.send_json({
        "source": "error",
        "error": {"type": error_type, "message": message}
    })

@alru_cache(maxsize=1)
async def get_messages_collection():
    db = await get_mongo_db()
    return db["messages"]

@alru_cache(maxsize=1)
async def get_rooms_collection():
    db = await get_mongo_db()
    return db["rooms"]

async def receive_message_send(websocket: WebSocket, email: str, data: dict):
    message_data = data.get("data", {})
    required_fields = ["room_id", "sender", "receiver", "message"]
    if not all(field in message_data for field in required_fields):
        await send_error(websocket, "validation_error", "Missing required fields")
        return

    if message_data["sender"] != email:
        await send_error(websocket, "permission_denied", "Cannot send messages as another user")
        return

    rooms_collection = await get_rooms_collection()
    room_id = message_data["room_id"]
    if not room_id:
        existing_room = await rooms_collection.find_one({
            "participants": {"$all": [message_data["sender"], message_data["receiver"]]}
        })
        if existing_room:
            room_id = str(existing_room["_id"])
        else:
            room_doc = {
                "participants": [message_data["sender"], message_data["receiver"]],
                "created_at": datetime.utcnow(),
                "last_message_at": datetime.utcnow()
            }
            result = await rooms_collection.insert_one(room_doc)
            room_id = str(result.inserted_id)
            logger.debug(f"Created new room with ID: {room_id} for {message_data['sender']} and {message_data['receiver']}")
        message_data["room_id"] = room_id

    messages_collection = await get_messages_collection()
    message_doc = {
        "room_id": room_id,
        "sender": message_data["sender"],
        "receiver": message_data["receiver"],
        "message": message_data["message"],
        "timestamp": datetime.utcnow(),
        "is_read": False,
        "delivered": False,
    }

    if message_data.get("file") and message_data.get("filename"):
        try:
            file_data = base64.b64decode(message_data["file"])
            message_doc["file"] = {
                "filename": message_data["filename"],
                "size": len(file_data),
                "data": file_data,
                "content_type": message_data.get("content_type", "application/octet-stream"),
            }
        except Exception as e:
            logger.error(f"File processing error: {str(e)}")
            await send_error(websocket, "file_error", "Invalid file data")
            return

    result = await messages_collection.insert_one(message_doc)
    message_id = str(result.inserted_id)

    payload = {
        "source": "message.send",
        "data": {
            "message_id": message_id,
            "room_id": room_id,
            "sender": message_data["sender"],
            "receiver": message_data["receiver"],
            "message": message_data["message"],
            "timestamp": message_doc["timestamp"].isoformat(),
            "delivered": False,
        },
    }

    if "file" in message_doc:
        payload["data"]["file"] = {
            "filename": message_doc["file"]["filename"],
            "size": message_doc["file"]["size"],
            "content_type": message_doc["file"]["content_type"],
        }

    await websocket.send_json(payload)
    await manager.send_to_group(message_data["receiver"], payload)

    await messages_collection.update_one(
        {"_id": ObjectId(message_id)},
        {"$set": {"delivered": True}}
    )

    await rooms_collection.update_one(
        {"_id": ObjectId(room_id)},
        {"$set": {"last_message_at": datetime.utcnow()}}
    )

async def receive_message_read(websocket: WebSocket, email: str, data: dict):
    message_id = data.get("data", {}).get("message_id")
    if not message_id:
        await send_error(websocket, "validation_error", "Missing message_id")
        return

    messages_collection = await get_messages_collection()
    result = await messages_collection.update_one(
        {"_id": ObjectId(message_id), "receiver": email},
        {"$set": {"is_read": True, "read_at": datetime.utcnow()}}
    )

    if result.modified_count == 0:
        await send_error(websocket, "not_found", "Message not found or already read")
        return

    await manager.send_to_group(email, {
        "source": "message.read",
        "data": {
            "message_id": message_id,
            "status": "read",
            "read_at": datetime.utcnow().isoformat(),
        },
    })

async def receive_message_edit(websocket: WebSocket, email: str, data: dict):
    message_data = data.get("data", {})
    required_fields = ["message_id", "new_message"]
    if not all(field in message_data for field in required_fields):
        await send_error(websocket, "validation_error", "Missing required fields")
        return

    messages_collection = await get_messages_collection()
    result = await messages_collection.update_one(
        {"_id": ObjectId(message_data["message_id"]), "sender": email},
        {
            "$set": {
                "message": message_data["new_message"],
                "edited": True,
                "edited_at": datetime.utcnow(),
            }
        }
    )

    if result.modified_count == 0:
        await send_error(websocket, "not_found", "Message not found or not authorized to edit")
        return

    updated_message = await messages_collection.find_one({"_id": ObjectId(message_data["message_id"])})
    payload = {
        "source": "message.edit",
        "data": {
            "message_id": message_data["message_id"],
            "room_id": updated_message["room_id"],
            "sender": updated_message["sender"],
            "receiver": updated_message["receiver"],
            "new_message": message_data["new_message"],
            "edited_at": updated_message.get("edited_at", datetime.utcnow()).isoformat(),
        },
    }

    await manager.send_to_group(updated_message["sender"], payload)
    await manager.send_to_group(updated_message["receiver"], payload)

async def receive_message_delete(websocket: WebSocket, email: str, data: dict):
    message_id = data.get("data", {}).get("message_id")
    if not message_id:
        await send_error(websocket, "validation_error", "Missing message_id")
        return

    messages_collection = await get_messages_collection()
    message = await messages_collection.find_one({"_id": ObjectId(message_id)})
    if not message:
        await send_error(websocket, "not_found", "Message not found")
        return

    if message["sender"] != email:
        await send_error(websocket, "permission_denied", "Not authorized to delete this message")
        return

    result = await messages_collection.delete_one({"_id": ObjectId(message_id)})
    if result.deleted_count == 0:
        await send_error(websocket, "server_error", "Failed to delete message")
        return

    payload = {
        "source": "message.delete",
        "data": {
            "message_id": message_id,
            "room_id": message["room_id"],
            "deleted_by": email,
            "deleted_at": datetime.utcnow().isoformat(),
        },
    }

    await manager.send_to_group(message["sender"], payload)
    await manager.send_to_group(message["receiver"], payload)

async def receive_message_type(websocket: WebSocket, email: str, data: dict):
    required_fields = ["room_id", "receiver"]
    if not all(field in data.get("data", {}) for field in required_fields):
        await send_error(websocket, "validation_error", "Missing required fields")
        return

    await manager.send_to_group(data["data"]["receiver"], {
        "source": "message.type",
        "data": {
            "room_id": data["data"]["room_id"],
            "sender": email,
            "is_typing": data["data"].get("is_typing", True),
        },
    })

async def receive_user_status(websocket: WebSocket, email: str, data: dict):
    target_email = data.get("data", {}).get("email")
    if not target_email:
        await send_error(websocket, "validation_error", "Missing email")
        return

    redis_client = await get_redis_client()
    status = await redis_client.get(get_safe_cache_key("user_status", target_email)) or "offline"
    last_seen = await redis_client.get(get_safe_cache_key("user_last_seen", target_email))

    await websocket.send_json({
        "source": "user.status",
        "data": {
            "email": target_email,
            "status": status,
            "last_seen": last_seen if last_seen else None,
        },
    })

async def receive_user_list(websocket: WebSocket, email: str, data: dict):
    try:
        is_pagination = data.get("is_pagination", True)
        page = int(data.get("page", 1))
        per_page = int(data.get("per_page", 10))
        search_query = data.get("search", "").strip()
        
        # Check cache
        cache_key = f"user_list:{email}:{page}:{per_page}:{search_query}"
        redis_client = await get_redis_client()
        cached_data = await redis_client.get(cache_key)
        if cached_data:
            await websocket.send_json(json.loads(cached_data))
            return

        # Parallelize data fetching
        async def fetch_users(session: AsyncSession):
            query = select(User.id, User.email, User.role, User.is_active).where(User.email != email)
            if search_query:
                query = query.where(User.email.ilike(f"%{search_query}%"))
            
            # Count total users
            count_query = select(func.count()).select_from(User).where(User.email != email)
            if search_query:
                count_query = select(func.count()).select_from(query.subquery())
            total_result = await session.execute(count_query)
            total_users = total_result.scalar_one()
            
            # Apply pagination
            if is_pagination:
                query = query.offset((page - 1) * per_page).limit(per_page)
            
            result = await session.execute(query)
            return total_users, result.all()

        async def fetch_unread_counts(emails):
            messages_collection = await get_messages_collection()
            unread_counts_cursor = messages_collection.aggregate([
                {"$match": {
                    "receiver": email,
                    "is_read": False,
                    "sender": {"$in": emails}
                }},
                {"$group": {
                    "_id": "$sender",
                    "unread_count": {"$sum": 1}
                }},
            ])
            return {doc["_id"]: doc["unread_count"] async for doc in unread_counts_cursor}

        async def fetch_rooms():
            rooms_collection = await get_rooms_collection()
            rooms_cursor = rooms_collection.find({
                "participants": email,
                "$expr": {"$eq": [{"$size": "$participants"}, 2]}
            }, {"participants": 1, "_id": 1})
            return {str(room["_id"]): room async for room in rooms_cursor}

        async def fetch_redis_data(status_keys, last_seen_keys):
            async with redis_client.pipeline() as pipe:
                for key in status_keys + last_seen_keys:
                    pipe.get(key)
                return await pipe.execute()

        # Fetch users first to get emails
        async for session in get_db():
            total_users, users_query = await fetch_users(session)
            break  # Only need one session
        emails = [user.email for user in users_query]

        # Execute other queries concurrently
        unread_dict, rooms, redis_results = await asyncio.gather(
            fetch_unread_counts(emails),
            fetch_rooms(),
            fetch_redis_data(
                [get_safe_cache_key("user_status", u) for u in emails],
                [get_safe_cache_key("user_last_seen", u) for u in emails]
            )
        )

        # Process rooms
        room_map = {}
        for room_id, room in rooms.items():
            participants = room["participants"]
            other_user = next((p for p in participants if p != email), None)
            if other_user in emails:
                room_map[other_user] = room_id

        # Process Redis results
        num_users = len(emails)
        status_values = redis_results[:num_users]
        last_seen_values = redis_results[num_users:]
        status_dict = {get_safe_cache_key("user_status", user.email): v or "offline" for user, v in zip(users_query, status_values)}
        last_seen_dict = {get_safe_cache_key("user_last_seen", user.email): v for user, v in zip(users_query, last_seen_values) if v}

        # Build user list
        user_list = [
            UserResponse(
                id=str(user.id),
                email=user.email,
                role=user.role,
                is_status=status_dict.get(get_safe_cache_key("user_status", user.email), "offline"),
                last_seen=last_seen_dict.get(get_safe_cache_key("user_last_seen", user.email)),
                unread_count=unread_dict.get(user.email, 0),
                room_id=room_map.get(user.email)
            ).dict()
            for user in users_query
        ]

        response = {"source": "user.list", "data": user_list}
        if is_pagination:
            response["pagination"] = {
                "page": page,
                "per_page": per_page,
                "total": total_users,
                "total_pages": (total_users + per_page - 1) // per_page
            }

        # Cache response
        await redis_client.setex(cache_key, 60, json.dumps(response))
        await websocket.send_json(response)

    except Exception as e:
        logger.error(f"User list error: {str(e)}", exc_info=True)
        await send_error(websocket, "server_error", f"Failed to fetch users: {str(e)}")

async def receive_message_list(websocket: WebSocket, email: str, data: dict):
    try:
        room_id = data.get("data", {}).get("room_id")
        if not room_id:
            logger.debug(f"No room_id provided for {email}, returning user list")
            await receive_user_list(websocket, email, data)
            return

        page = int(data.get("data", {}).get("page", 0))
        page_size = min(int(data.get("data", {}).get("page_size", 20)), 100)
        skip = page * page_size

        # Check cache for message list
        cache_key = f"message_list:{email}:{room_id}:{page}:{page_size}"
        redis_client = await get_redis_client()
        cached_data = await redis_client.get(cache_key)
        if cached_data:
            await websocket.send_json(json.loads(cached_data))
            return

        messages_collection = await get_messages_collection()
        query = {
            "room_id": room_id,
            "$or": [{"sender": email}, {"receiver": email}],
        }

        total_count = await messages_collection.count_documents(query)
        messages_cursor = messages_collection.find(query).sort("timestamp", -1).skip(skip).limit(page_size)
        messages = []
        async for msg in messages_cursor:
            msg_data = {
                "message_id": str(msg["_id"]),
                "room_id": msg["room_id"],
                "sender": msg["sender"],
                "receiver": msg["receiver"],
                "message": msg["message"],
                "timestamp": msg["timestamp"].isoformat(),
                "is_read": msg.get("is_read", False),
                "delivered": msg.get("delivered", False),
                "edited": msg.get("edited", False),
                "edited_at": msg.get("edited_at").isoformat() if msg.get("edited_at") else None,
            }
            if "file" in msg:
                msg_data["file"] = {
                    "filename": msg["file"]["filename"],
                    "size": msg["file"]["size"],
                    "content_type": msg["file"]["content_type"],
                }
            messages.append(msg_data)
        messages.reverse()

        response = {
            "source": "message.list",
            "data": {
                "messages": messages,
                "page": page,
                "page_size": page_size,
                "total": total_count,
                "has_more": (skip + page_size) < total_count,
            },
        }

        # Cache with short TTL since messages can change
        await redis_client.setex(cache_key, 30, json.dumps(response))
        await websocket.send_json(response)
    except Exception as e:
        logger.error(f"Message list error: {str(e)}", exc_info=True)
        await send_error(websocket, "server_error", "Failed to fetch messages")

async def receive_read_list(websocket: WebSocket, email: str, data: dict):
    payload = data.get("data", {})
    sender = payload.get("sender")
    if not sender:
        await send_error(websocket, "validation_error", "Missing sender")
        return

    messages_collection = await get_messages_collection()
    now = datetime.utcnow()
    result = await messages_collection.update_many(
        {"sender": sender, "receiver": email, "is_read": False},
        {"$set": {"is_read": True, "read_at": now}}
    )

    if result.modified_count == 0:
        await send_error(websocket, "not_found", "No unread messages found from this sender")
        return

    await manager.send_to_group(email, {
        "source": "read.list",
        "data": {
            "sender": sender,
            "status": "read",
            "read_count": result.modified_count,
            "read_at": now.isoformat()
        }
    })

async def receive_ping(websocket: WebSocket, email: str, data: dict):
    await websocket.send_json({"source": "pong"})

async def send_pending_messages(websocket: WebSocket, email: str):
    messages_collection = await get_messages_collection()
    pending_messages_cursor = messages_collection.find({"receiver": email, "delivered": False}).sort("timestamp", 1)
    pending_messages = [msg async for msg in pending_messages_cursor]

    # Send messages
    for msg in pending_messages:
        payload = {
            "source": "message.send",
            "data": {
                "message_id": str(msg["_id"]),
                "room_id": msg["room_id"],
                "sender": msg["sender"],
                "receiver": msg["receiver"],
                "message": msg["message"],
                "timestamp": msg["timestamp"].isoformat(),
                "delivered": True,
            },
        }
        if "file" in msg:
            payload["data"]["file"] = {
                "filename": msg["file"]["filename"],
                "size": msg["file"]["size"],
                "content_type": msg["file"]["content_type"],
            }
        await websocket.send_json(payload)

    # Batch update delivered status
    if pending_messages:
        message_ids = [msg["_id"] for msg in pending_messages]
        await messages_collection.update_many(
            {"_id": {"$in": message_ids}},
            {"$set": {"delivered": True}}
        )

async def receive_unread_message(websocket: WebSocket, email: str):
    try:
        messages_collection = await get_messages_collection()
        unread_aggregation = messages_collection.aggregate([
            {"$match": {"receiver": email, "is_read": False}},
            {"$group": {"_id": "$sender", "unread_count": {"$sum": 1}}},
        ])
        unread_summary = [
            {"sender": entry["_id"], "unread_count": entry["unread_count"]}
            async for entry in unread_aggregation
        ]
        await websocket.send_json({
            "source": "message.unread",
            "data": unread_summary
        })
    except Exception as e:
        logger.error(f"Unread message aggregation error: {str(e)}", exc_info=True)
        await send_error(websocket, "server_error", "Failed to fetch unread message counts")

async def websocket_listener(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            logger.debug(f"Notification received: {data}")
            await websocket.send_json({"status": "received", "data": data})
    except WebSocketDisconnect:
        logger.info("Notifications WebSocket disconnected")