# itzmy/models/user.py
"""用户账号模型：手机号 / 微信 / 支付宝 / 游客 统一账号表"""

from datetime import datetime

from models.base import Base
from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column


class UserRecord(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(16), nullable=False)          # phone / wx / ali / guest
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # 手机号或系统生成ID
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)      # 前端展示昵称
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
