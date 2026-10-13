# itzmy/models/profile.py
"""用户画像：会话记忆（昵称等），跨会话持久化"""

from datetime import datetime

from models.base import Base
from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column


class UserProfileRecord(Base):
    __tablename__ = "user_profiles"
    sender_id: Mapped[str] = mapped_column(String(64), primary_key=True)   # 用户标识
    nickname: Mapped[str] = mapped_column(String(50), default="")          # 昵称（"叫我土豆" → 土豆）
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
