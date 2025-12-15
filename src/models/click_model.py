from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from .base import BaseModel


class Clicks(BaseModel):
    __tablename__ = "clicks"
    sort_url_id = Column(Integer, ForeignKey("ulrs.id"), nullable=False)
    click_count = Column(Integer, default=0)
    last_clicked_at = Column(DateTime, nullable=True)


