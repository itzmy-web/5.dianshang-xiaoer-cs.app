# itzmy/test/sqlalchemy/mymodel.py
from typing import Optional

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String

"""
ORM 的核心思想是“一个类对应一张表、一个对象对应一行数据”，但 SQLAlchemy 得先知道哪些类是表模型。DeclarativeBase 就是干这个的：任何类继承它之后，类定义过程会被拦截——__tablename__、Mapped[...] 这些声明会被收集起来，翻译成数据库层面的表结构描述（列名、类型、主键、可否为空），这套描述叫元数据（metadata）
"""
# ORM  Python类  对应的 数据库里面的表
#  类  很特殊   得是  继承
from models.base import Base

class User(Base):
    __tablename__ = "user_account" # 表名
    # 它给 SQLAlchemy 两个关键信息——这个属性对应什么数据库类型，以及给 IDE/类型检查器一个“这是表字段”的类型标注。
    # mapped_column:字段绑定（将类属性映射到数据库）
    # Mapped[int] 管“是什么”，mapped_column(...) 管“怎么建”（主键、外键、默认值、索引、列长度）
    id: Mapped[int] = mapped_column(primary_key=True)
    # String(30)：name字段在数据库表的列中类型是varchar 长度是30
    name: Mapped[str] = mapped_column(String(30))

    #  Optional：该字段在数据库表中的值是可以允许为null
    # "Optional"（可选的）这个命名容易让人误解成“这个字段可有可无、可以不写”，其实它说的是“这个值可以缺席”——值不存在时用 None 表示。 Optional[str]  =  str | None
    fullname: Mapped[Optional[str]]

    def __repr__(self) -> str:
        # 辅助  打印时候 按照拼接 字符串内容打印  给程序员看
        # __str__
        return f"User(id={self.id!r}, name={self.name!r}, fullname={self.fullname!r})"


class Address(Base):
    __tablename__ = "address"

    id: Mapped[int] = mapped_column(primary_key=True)
    email_address: Mapped[str]

    def __repr__(self) -> str:
        return f"Address(id={self.id!r}, email_address={self.email_address!r})"
