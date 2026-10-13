# itzmy/test/sqlalchemy/test_sync_usage.py

from mymodel import Base, User
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


def main():
    # 1. 创建引擎
    # sqlite: 轻量级数据库,数据直接存储到文件中
    # ///mydb: 在当前目录下创建数据库文件mydb
    # ////mydb: 在磁盘根目录下创建数据库文件mydb
    # echo=True: 执行的各种DDL...语句都可以在控制台
    engine = create_engine("sqlite:///mydb", echo=True)
    # 2. 创建表
    Base.metadata.create_all(engine)
    # with：获取session，并自动关闭资源
    with Session(engine) as session:
        # # 3. 插入记录
        # a = User(
        #     name="Mr 张",
        #     fullname="张三"
        # )
        #
        # b = User(
        #     name="sandy",
        #     fullname="Sandy Cheeks"
        # )
        #
        # c = User(
        #     name="patrick",
        #     fullname="Patrick Star"
        # )
        # # 截止34行 我们只是创建出来对象
        # # 向数据库中添加三条记录
        # session.add_all([a, b, c])
        #
        # # 手动提交：将数据刷到磁盘
        # session.commit()

        # # 4. 查询 ORM
        # select(User).where(User.name.in_(["Mr 张", "sandy"]))  是sql 查询数据库
        # stmt = select(User).where(User.name.in_(["Mr 张", "sandy"]))
        # for user in session.scalars(stmt):
        #     print(user)
        #
        # stmt = select(User).where(User.name == 'Mr 张')
        # print(session.scalars(stmt).one())
        # SQL注入问题
        # from sqlalchemy import text
        # rows = session.execute(text("SELECT * FROM user_account WHERE name IN ('Mr 张', 'sandy') or 1 = 1"))
        # for row in rows:
        #     print(row)  # (1, 'Mr 张', '张三') ← 每行是元组
        # sql注入
        from sqlalchemy import text
        rows = session.execute(
            text("SELECT * FROM user_account WHERE name = :who"),
            {"who": "Mr 张"}
        )  # 原理在于参数绑定走的是预编译路径 SQLAlchemy会重新组装SQL 防止注入

        # text(select * from user_account where pwd = '123456' or 1 = 1)
        #
        for row in rows:
            print(row)  # (1, 'Mr 张', '张三') ← 每行是元组
        """
        # 方式一 不推荐
        from sqlalchemy import text
        rows = session.execute(text("SELECT * FROM user_account WHERE name IN ('Mr 张', 'sandy')"))
        for row in rows:
            print(row)  # (1, 'Mr 张', '张三') ← 每行是元组

        # 方式二 推荐  防止SQL注入
        from sqlalchemy import text
        rows = session.execute(
            text("SELECT * FROM user_account WHERE name = :who"),
            {"who": "Mr 张"}
		) # 原理在于参数绑定走的是预编译路径 SQLAlchemy会重新组装SQL 防止注入

		# SQL注入简单解读
		比如 sql = f"SELECT * FROM user_account WHERE name = '{用户输入}'"
		攻击者在输入框里填的不是用户名，而是一段精心构造的字符串：' OR '1'='1。f-string 拼出来的 SQL 变成了：SELECT * FROM user_account WHERE name = '' OR '1'='1'

		text(sql) 看结构：name = ''（空，不匹配）OR '1'='1'（恒真）——整个 WHERE 条件永真，返回全部 3 行。这就是经典的“万能密码”攻击：本该“输入对的用户名才能过”的验证逻辑，被一个 OR 摧毁了，攻击者直接以任意身份登录。
        """


if __name__ == '__main__':
    main()
