# itzmy/models/feedback.py
"""消息评价（👍/👎）持久化模型"""

from datetime import datetime

from models.base import Base
from sqlalchemy import DateTime, TEXT
from sqlalchemy.orm import Mapped, mapped_column


class FeedbackRecord(Base):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sender_id: Mapped[str] = mapped_column(nullable=False)          # 用户标识
    question: Mapped[str] = mapped_column(TEXT, nullable=False)     # 用户当时的问题
    answer: Mapped[str] = mapped_column(TEXT, nullable=False)       # 机器人的回答
    rating: Mapped[str] = mapped_column(nullable=False)             # up / down
    comment: Mapped[str] = mapped_column(TEXT, nullable=True)       # 可选补充说明
    # 复核状态：0=待复核 1=已处理 2=知识缺失（坏例复核队列用）
    reviewed: Mapped[int] = mapped_column(default=0)
    # 满意度星级 1-5（告别评价用，可空）
    stars: Mapped[int | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
