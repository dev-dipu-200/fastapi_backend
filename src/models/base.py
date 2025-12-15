from datetime import datetime
from sqlalchemy import Column, Integer, DateTime
from src.configure.database import Base, engine


class BaseModel(Base):
    __abstract__ = True

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow())
    updated_at = Column(DateTime, nullable=True, onupdate=datetime.utcnow())
    deleted_at = Column(DateTime, nullable=True)
