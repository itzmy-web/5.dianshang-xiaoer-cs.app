# itzmy/models/kb.py
"""知识库文档块（RAG 简化版）+ 转人工事件模型"""

from datetime import datetime

from models.base import Base
from sqlalchemy import DateTime, TEXT
from sqlalchemy.orm import Mapped, mapped_column


class KBChunkRecord(Base):
    """管理员上传的文档切分块：检索时作为额外知识片段注入"""
    __tablename__ = "kb_chunks"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    doc_name: Mapped[str] = mapped_column(nullable=False)            # 来源文档名
    seq: Mapped[int] = mapped_column(default=0)                      # 块序号
    content: Mapped[str] = mapped_column(TEXT, nullable=False)       # 块文本
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TransferEventRecord(Base):
    """转人工事件：管理端实时提醒 + 接管回复"""
    __tablename__ = "transfer_events"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sender_id: Mapped[str] = mapped_column(nullable=False)
    handled: Mapped[int] = mapped_column(default=0)                  # 0=待处理 1=已接管
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
