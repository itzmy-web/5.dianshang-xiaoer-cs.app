# itzmy/models/metric.py
"""对话性能指标：每轮回复耗时（llmops 可观测）"""

from datetime import datetime

from models.base import Base
from sqlalchemy import DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column


class ChatMetricRecord(Base):
    __tablename__ = "chat_metrics"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sender_id: Mapped[str] = mapped_column(nullable=False)          # 用户标识
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)  # 本轮回复耗时（毫秒）
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
