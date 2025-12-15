from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from .base import BaseModel

# SQLite Models
class SortUrls(BaseModel):
    __tablename__ = "ulrs"
    long_url = Column(String, nullable=False, unique=True)
    short_url = Column(String, nullable=False, unique=True)

