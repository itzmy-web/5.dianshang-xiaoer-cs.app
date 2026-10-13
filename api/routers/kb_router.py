# itzmy/api/routers/kb_router.py
"""知识库文档上传（RAG 简化版）：txt/md 上传 → 切块入库 → 检索时注入
上传采用 base64 JSON（避免 multipart 依赖，云端沙箱零额外安装）"""
import base64
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, delete

from infrastructure import database
from models.kb import KBChunkRecord

router = APIRouter()

_CHUNK_SIZE = 420  # 每块目标字符数（按段落聚合，超长再切）


class KBUploadRequest(BaseModel):
    filename: str
    content_b64: str   # 文件内容 base64


def _split_text(text: str) -> list[str]:
    """按空行分段 → 相邻段聚合到 _CHUNK_SIZE，超长段硬切"""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text.replace("\r\n", "\n")) if p.strip()]
    if not paras:
        paras = [text.strip()] if text.strip() else []
    chunks: list[str] = []
    buf = ""
    for p in paras:
        if len(p) > _CHUNK_SIZE * 2:  # 超长段落硬切
            if buf:
                chunks.append(buf); buf = ""
            for i in range(0, len(p), _CHUNK_SIZE):
                chunks.append(p[i:i + _CHUNK_SIZE])
            continue
        if len(buf) + len(p) + 1 <= _CHUNK_SIZE:
            buf = (buf + "\n" + p).strip()
        else:
            if buf:
                chunks.append(buf)
            buf = p
    if buf:
        chunks.append(buf)
    return chunks


def _verify_admin_token(x_admin_token: str = ""):
    from conf.config import settings
    if x_admin_token != settings.admin_password:
        raise HTTPException(status_code=401, detail="管理员校验失败")


@router.post("/api/kb/upload")
async def kb_upload(req: KBUploadRequest, x_admin_token: str = ""):
    _verify_admin_token(x_admin_token)
    name = req.filename or "未命名文档"
    if not name.lower().endswith((".txt", ".md", ".markdown")):
        raise HTTPException(status_code=400, detail="仅支持 .txt / .md 文档")
    try:
        text = base64.b64decode(req.content_b64).decode("utf-8")
    except Exception:
        raise HTTPException(status_code=400, detail="文件内容解码失败，请重新选择文件")
    if len(text.strip()) < 10:
        raise HTTPException(status_code=400, detail="文档内容太短")

    chunks = _split_text(text)[:200]  # 上限 200 块，防误传超大文件
    async with database.async_session() as session:
        for i, c in enumerate(chunks):
            session.add(KBChunkRecord(doc_name=name, seq=i, content=c))
        await session.commit()
    return {"ok": True, "doc": name, "chunks": len(chunks)}


@router.get("/api/kb/list")
async def kb_list(x_admin_token: str = ""):
    _verify_admin_token(x_admin_token)
    async with database.async_session() as session:
        rows = (await session.execute(
            select(KBChunkRecord).order_by(KBChunkRecord.doc_name, KBChunkRecord.seq)
        )).scalars().all()
    docs: dict[str, dict] = {}
    for r in rows:
        d = docs.setdefault(r.doc_name, {"doc": r.doc_name, "chunks": 0, "chars": 0})
        d["chunks"] += 1
        d["chars"] += len(r.content)
    return {"docs": list(docs.values()), "total": len(rows)}


@router.delete("/api/kb/{doc_name}")
async def kb_delete(doc_name: str, x_admin_token: str = ""):
    _verify_admin_token(x_admin_token)
    async with database.async_session() as session:
        await session.execute(delete(KBChunkRecord).where(KBChunkRecord.doc_name == doc_name))
        await session.commit()
    return {"ok": True}
