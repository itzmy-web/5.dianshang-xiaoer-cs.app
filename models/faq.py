# itzmy/models/faq.py
"""FAQ 知识库条目：支持后台增删改查，知识轨检索时动态读取"""

from datetime import datetime

from models.base import Base
from sqlalchemy import DateTime, TEXT, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column


class FaqRecord(Base):
    __tablename__ = "faq_entries"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)      # 标题（来源标注用）
    keywords: Mapped[str] = mapped_column(TEXT, nullable=False)          # 命中关键词，逗号分隔
    answer: Mapped[str] = mapped_column(TEXT, nullable=False)            # 标准答案
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)         # 停用/启用
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
