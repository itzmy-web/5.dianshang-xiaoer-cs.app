# itzmy/models/trace.py
"""LLM 调用追踪：每次大模型调用的轨道/耗时/是否成功（mini-Langfuse，自建可观测）"""

from datetime import datetime

from models.base import Base
from sqlalchemy import Boolean, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column


class LlmTraceRecord(Base):
    __tablename__ = "llm_traces"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    track: Mapped[str] = mapped_column(nullable=False)                # 调用轨道：plan/knowledge/chitchat/...
    model: Mapped[str] = mapped_column(nullable=False)                # 模型名
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)  # 耗时
    prompt_chars: Mapped[int] = mapped_column(Integer, nullable=False)  # 提示词长度（字符）
    ok: Mapped[bool] = mapped_column(Boolean, default=True)           # 是否成功
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
