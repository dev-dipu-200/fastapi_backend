from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Text
from .base import BaseModel

class User(BaseModel):
    __tablename__ = "users"
    password = Column(String)
    user_id = Column(String, unique=True, nullable=False)
    email = Column(String, nullable=False)
    role = Column(String, nullable=False)
    organization__org_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    token_json = Column(Text, nullable=True)  # NEW: Stores Gmail OAuth token as JSON

class Email(BaseModel):
    __tablename__ = 'emails'

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(String, unique=True, nullable=False)
    subject = Column(String, nullable=True)
    sender = Column(String, nullable=True)
    body = Column(Text, nullable=True)
    user_id = Column(String, ForeignKey('users.user_id'), nullable=False)  # NEW: Associate with User
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)  # NEW: Timestamp