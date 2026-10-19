# itzmy/api/app.py

"""
定义fastapi实例

"""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Cookie, FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from api.routers.chat_router import router
from api.routers.mock_commerce_router import router as mock_commerce_router
from api.routers.feedback_router import router as feedback_router
from api.routers.auth_router import router as auth_router
from api.routers.faq_router import router as faq_router
from api.routers.media_router import router as media_router
from api.routers.auth_router import is_valid_token
from conf.config import settings
from infrastructure import database
from infrastructure.database import init_db_engine, close_db_engine
from infrastructure.http_client import init_http_client, close_http_client


# 装饰器 是 Python特有的语法 在不改变函数内部 代码的情况下 额外 增加新的功能
# 汽车 什么都不懂  拿去店里  额外 车顶 装个机关枪  封闭开放 （不主张 你去修改代码 但是 愿意让函数 有更多的功能）
@asynccontextmanager
async def lifespan(app: FastAPI):

    # 1. 应用启动
    print("启动服务器...")
    init_db_engine()  # ← 执行这里，创建数据库连接池
    init_http_client()

    # 1.5 SQLite 自动建表（云端/本地开箱即用，无需手动执行 SQL）
    from models.base import Base
    import models.dialogue_state  # noqa: F401  确保模型已注册进 Base.metadata
    import models.feedback        # noqa: F401  评价表
    import models.user            # noqa: F401  用户表
    import models.faq             # noqa: F401  FAQ 知识库表
    import models.profile         # noqa: F401  用户画像表
    import models.metric          # noqa: F401  响应耗时指标表
    import models.trace           # noqa: F401  LLM 调用追踪表
    import models.kb              # noqa: F401  知识库文档块 + 转人工事件表
    # 注意：engine 是 init_db_engine() 里重新赋值的模块全局变量，
    # 必须用 database.engine 动态取，不能用 from-import 拿到的旧值（None）
    async with database.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("数据库表已就绪")

    # 1.6 旧库迁移：feedback 表补 reviewed 列（已存在则忽略）
    from sqlalchemy import text as sql_text
    try:
        async with database.engine.begin() as conn:
            await conn.execute(sql_text("ALTER TABLE feedback ADD COLUMN reviewed INTEGER DEFAULT 0"))
        print("feedback.reviewed 迁移完成")
    except Exception:
        pass  # 列已存在
    try:
        async with database.engine.begin() as conn:
            await conn.execute(sql_text("ALTER TABLE feedback ADD COLUMN stars INTEGER"))
        print("feedback.stars 迁移完成")
    except Exception:
        pass  # 列已存在

    # 1.7 FAQ 播种：首次启动把内置知识灌进数据库（之后后台可自由编辑）
    from sqlalchemy import func, select
    from models.faq import FaqRecord
    from knowledge.providers import FAQProvider
    async with database.async_session() as session:
        cnt = (await session.execute(select(func.count(FaqRecord.id)))).scalar() or 0
        if not cnt:
            for item in FAQProvider.FAQ_DEFAULT:
                session.add(FaqRecord(
                    title=item["title"],
                    keywords=",".join(item["keywords"]),
                    answer=item["answer"],
                ))
            await session.commit()
            print(f"FAQ 知识库已播种 {len(FAQProvider.FAQ_DEFAULT)} 条")

    # 2. 进入 yield
    yield  # ← FastAPI 开始接收请求


    # 3. 应用关闭（Ctrl+C 或部署平台停止）
    await close_db_engine()  # ← 执行这里，关闭连接池
    await close_http_client()
    print("服务器已关闭")

# 创建应用
app = FastAPI(description="商擎助理智能客服应用", lifespan=lifespan)


# ---------------- 数字人（魔珐星云）凭证下发 ----------------
# 密钥仅存放于服务端 .env / 环境变量，绝不出现在前端源码中
@app.get("/api/digital-human/credentials")
async def digital_human_credentials():
    if not (settings.digital_human_app_id and settings.digital_human_app_secret):
        return {"configured": False, "detail": "服务端未配置 DIGITAL_HUMAN_APP_ID / DIGITAL_HUMAN_APP_SECRET"}
    return {
        "configured": True,
        "app_id": settings.digital_human_app_id,
        "app_secret": settings.digital_human_app_secret,
        "gateway_server": settings.digital_human_gateway_server,
    }


# 健康检查
@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------------- 服务端登录门禁（强制：未登录访问主页一律 302 到登录页） ----------------
WEB_DIR = Path(__file__).resolve().parents[1] / "web"


@app.middleware("http")
async def no_store_for_html(request, call_next):
    """HTML 一律禁止缓存：保证前端更新立刻生效，浏览器不会拿着旧页面绕过新版门禁"""
    response = await call_next(request)
    if "text/html" in response.headers.get("content-type", ""):
        response.headers["Cache-Control"] = "no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response


@app.get("/", include_in_schema=False)
@app.get("/index.html", include_in_schema=False)
async def index_gate(cs_token: str | None = Cookie(default=None)):
    # 没有有效登录 cookie → 服务端直接重定向到登录页（不依赖任何前端 JS/缓存）
    if not is_valid_token(cs_token):
        return RedirectResponse("/login.html", status_code=302)
    return FileResponse(WEB_DIR / "index.html",
                        headers={"Cache-Control": "no-store, must-revalidate"})


# 路由分发
app.include_router(router)
app.include_router(mock_commerce_router)   # 内置商城演示数据（查订单/物流/商品/搜索）
app.include_router(feedback_router)        # 消息评价 + 运营统计 + 坏例复核
app.include_router(auth_router)            # 注册 / 登录 / 游客
app.include_router(faq_router)             # FAQ 知识库后台管理
app.include_router(media_router)           # 图片识别（Qwen-VL）
from api.routers.kb_router import router as kb_router
app.include_router(kb_router)              # 知识库文档上传（RAG 简化版）

# 托管聊天前端（web/index.html），放在路由之后避免遮蔽 /api
# 注意：/ 与 /index.html 由上面的门禁路由接管，StaticFiles 只兜底其他静态文件
if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
