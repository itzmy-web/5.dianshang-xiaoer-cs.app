# itzmy/api/routers/faq_router.py
"""FAQ 知识库后台管理（增删改查）：知识轨检索动态读取，改完即时生效
写操作需要管理员令牌（X-Admin-Token 头），防止任何人篡改知识库"""

import base64

from datetime import datetime

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from conf.config import settings
from infrastructure import database
from models.faq import FaqRecord

router = APIRouter()


class AdminLoginReq(BaseModel):
    password: str


@router.post("/api/admin/login")
async def admin_login(req: AdminLoginReq):
    if not settings.admin_password or req.password != settings.admin_password:
        raise HTTPException(status_code=401, detail="管理员密码错误")
    return {"ok": True, "token": settings.admin_password}


@router.get("/api/admin/demo")
async def admin_demo():
    """演示模式：直接返回演示密码，前端自动填入（同 /api/auth/send-code 的演示套路）。
    注意：正式环境应下线此接口并更换 .env 里的 ADMIN_PASSWORD。"""
    if not settings.admin_password:
        raise HTTPException(status_code=404, detail="未配置管理员密码")
    return {"ok": True, "demo_password": settings.admin_password}


def verify_admin(x_admin_token: str = Header(default="")):
    """管理写操作统一鉴权"""
    if not settings.admin_password or x_admin_token != settings.admin_password:
        raise HTTPException(status_code=401, detail="需要管理员身份，请先登录管理后台")


class FaqUpsert(BaseModel):
    title: str
    keywords: list[str]
    answer: str
    enabled: bool = True


@router.get("/api/faq")
async def faq_list():
    async with database.async_session() as session:
        rows = (await session.execute(
            select(FaqRecord).order_by(FaqRecord.id)
        )).scalars().all()
    return {"items": [
        {
            "id": r.id,
            "title": r.title,
            "keywords": [k.strip() for k in r.keywords.split(",") if k.strip()],
            "answer": r.answer,
            "enabled": bool(r.enabled),
            "updated_at": str(r.updated_at),
        } for r in rows
    ]}


@router.post("/api/faq")
async def faq_create(req: FaqUpsert, x_admin_token: str = Header(default="")):
    verify_admin(x_admin_token)
    if not req.title.strip() or not req.answer.strip():
        raise HTTPException(status_code=400, detail="标题和答案不能为空")
    async with database.async_session() as session:
        row = FaqRecord(
            title=req.title.strip()[:100],
            keywords=",".join(k.strip() for k in req.keywords if k.strip()),
            answer=req.answer.strip(),
            enabled=req.enabled,
        )
        session.add(row)
        await session.commit()
        new_id = row.id
    return {"ok": True, "message": "FAQ 已新增", "id": new_id}


@router.put("/api/faq/{faq_id}")
async def faq_update(faq_id: int, req: FaqUpsert, x_admin_token: str = Header(default="")):
    verify_admin(x_admin_token)
    async with database.async_session() as session:
        row = (await session.execute(
            select(FaqRecord).where(FaqRecord.id == faq_id)
        )).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="FAQ 不存在")
        row.title = req.title.strip()[:100]
        row.keywords = ",".join(k.strip() for k in req.keywords if k.strip())
        row.answer = req.answer.strip()
        row.enabled = req.enabled
        row.updated_at = datetime.utcnow()
        await session.commit()
    return {"ok": True, "message": "FAQ 已更新"}


@router.delete("/api/faq/{faq_id}")
async def faq_delete(faq_id: int, x_admin_token: str = Header(default="")):
    verify_admin(x_admin_token)
    async with database.async_session() as session:
        row = (await session.execute(
            select(FaqRecord).where(FaqRecord.id == faq_id)
        )).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="FAQ 不存在")
        await session.delete(row)
        await session.commit()
    return {"ok": True, "message": "FAQ 已删除"}


# ---------------- 批量导入导出（CSV，逗号分隔：title,keywords,answer,enabled） ----------------

import csv as _csv
import io as _io


@router.get("/api/faq/export")
async def faq_export(x_admin_token: str = Header(default="")):
    verify_admin(x_admin_token)
    async with database.async_session() as session:
        rows = (await session.execute(
            select(FaqRecord).order_by(FaqRecord.id)
        )).scalars().all()
    buf = _io.StringIO()
    w = _csv.writer(buf)
    w.writerow(["title", "keywords", "answer", "enabled"])
    for r in rows:
        w.writerow([r.title, r.keywords, r.answer.replace("\n", "\\n"), 1 if r.enabled else 0])
    from fastapi.responses import Response
    return Response(
        content="\ufeff" + buf.getvalue(),  # BOM 让 Excel 正确识别 UTF-8
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=faq_export.csv"},
    )


class FaqImportRequest(BaseModel):
    filename: str = "import.csv"
    content_b64: str


@router.post("/api/faq/import")
async def faq_import(req: FaqImportRequest, x_admin_token: str = Header(default="")):
    verify_admin(x_admin_token)
    try:
        raw = base64.b64decode(req.content_b64)
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("gbk", errors="ignore")
    except Exception:
        raise HTTPException(status_code=400, detail="文件内容解码失败")
    reader = _csv.reader(_io.StringIO(text))
    added, skipped = 0, 0
    async with database.async_session() as session:
        for i, row in enumerate(reader):
            if not row or (i == 0 and row[0].strip() == "title"):
                continue  # 跳过表头
            if len(row) < 3 or not row[0].strip() or not row[2].strip():
                skipped += 1
                continue
            session.add(FaqRecord(
                title=row[0].strip(),
                keywords=row[1].strip(),
                answer=row[2].strip().replace("\\n", "\n"),
                enabled=(len(row) < 4 or str(row[3]).strip() in ("1", "true", "True")),
                updated_at=datetime.utcnow(),
            ))
            added += 1
        await session.commit()
    return {"ok": True, "added": added, "skipped": skipped}
