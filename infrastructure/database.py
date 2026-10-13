# itzmy/infrastructure/database.py

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession, create_async_engine, AsyncEngine

from conf.config import settings

# 声明 类型注解  描述变量 要用什么类型
engine: AsyncEngine | None = None
async_session: async_sessionmaker[AsyncSession] | None = None
# 初始化
def init_db_engine() -> None:
    global engine, async_session

    # 1. 创建异步引擎
    # pool_pre_ping=True
    # 核心作用：自动重连。它能防止程序因为拿到了“过期”或“断开”的连接而报错。
    # 代价：每次使用连接前会多一次极微小的网络交互（发个 ping），但在现代网络环境下，这个开销几乎可以忽略不计。
    # 建议：在生产环境中，强烈建议开启这个选项，它能大大提高程序的稳定性，让你少处理很多莫名其妙的数据库断连错误。
    engine = create_async_engine(settings.database_url, echo=True,
                                 pool_pre_ping=True)  # echo 把 SQLAlchemy 发给数据库的每一条 SQL 都打印到控制台，让你亲眼看见“ORM 到底执行了什么”。它就是个调试开关，对功能零影响。

    # async_sessionmaker  批量生产数据库连接
    # 2. 创建异步session工厂 （为什么需要工厂，如果没有每请求一个 session、好几个配置项）
    # 由于 每创建 一个连接对象 都要做很多配置
    # session工厂  所有的配置工厂都做好了
    async_session = async_sessionmaker(engine, expire_on_commit=False)


# 关闭资源
async def close_db_engine():
    if engine is not None: # 关闭连接
        await engine.dispose()


if __name__ == '__main__':
    init_db_engine()


    async def test():
        async with async_session() as session:
            # text() 就是一个“转换器”：
            # 它把一个普通的 Python 字符串转换成 SQLAlchemy 能识别的“可执行 SQL 对象”。
            # 注意：使用 text() 时，建议尽量使用占位符（如 :user_id）来传参，
            # 不要直接把变量拼接到字符串里，这样可以防止 SQL 注入攻击。
            result = await session.execute(text("SELECT * FROM dialogue_states WHERE sender_id = :sender_id"),
                                           {"sender_id": 1})

            # data = result.fetchall()
            data = result.fetchone()
            print(data)
            print(type(data))

        await close_db_engine()


    asyncio.run(test())

    """ 工厂设计模式: 工厂模式把对象的创建过程收拢到一处，调用方只需请求，无需关心具体类和构造细节
简单工厂 —— 楼下面包店。 你想吃蛋糕，走到面包店说“来个奶油蛋糕”，店员从柜台拿给你。你不知道也不需要知道配方、烘焙时间、奶油怎么打——“怎么做”被锁进了面包店。而且：全城人买的蛋糕规格统一（质量稳定）；哪天店里改良配方（改配置），所有顾客无感地吃上了新版本（单点修改）；新客人只要会说“来个奶油蛋糕”（一行调用）。async_sessionmaker 就是这家店：你说“来个 session”，它把 engine、expire_on_commit 这些“配方”全包了。
	   单例模式:  单例模式保证一个类在整个程序中只存在一个实例，并提供一个全局访问点。
	   设计模式是前人反复踩坑后总结出来的、针对特定问题的经典解决方案模板。
    """