# itzmy/api/routers/feedback_router.py
"""消息评价（👍/👎）+ 运营统计 + 坏例复核队列"""

from collections import Counter

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import case, func, select

from api.routers.faq_router import verify_admin
from infrastructure import database
from models.feedback import FeedbackRecord
from models.metric import ChatMetricRecord
from models.trace import LlmTraceRecord

router = APIRouter()


class FeedbackRequest(BaseModel):
    sender_id: str
    question: str = ""
    answer: str = ""
    rating: str          # up / down
    comment: str | None = None
    stars: int | None = None       # 满意度星级 1-5（告别评价用）


@router.post("/api/feedback")
async def submit_feedback(req: FeedbackRequest):
    if req.rating not in ("up", "down"):
        raise HTTPException(status_code=400, detail="rating 只能是 up 或 down")

    async with database.async_session() as session:
        session.add(FeedbackRecord(
            sender_id=req.sender_id,
            question=req.question[:500],
            answer=req.answer[:2000],
            rating=req.rating,
            comment=(req.comment or "")[:500],
            stars=max(1, min(5, req.stars)) if req.stars else None,
        ))
        await session.commit()

    return {"ok": True, "message": "感谢反馈！我们会继续改进～"}


# ---------------- 满意度统计（星级 NPS 简化版） ----------------

@router.get("/api/stats/stars")
async def stats_stars():
    from sqlalchemy import func, case
    async with database.async_session() as session:
        row = (await session.execute(
            select(
                func.count(FeedbackRecord.stars),
                func.avg(FeedbackRecord.stars),
                func.sum(case((FeedbackRecord.stars >= 4, 1), else_=0)),
                func.sum(case((FeedbackRecord.stars <= 2, 1), else_=0)),
            ).where(FeedbackRecord.stars.isnot(None))
        )).one()
        dist = (await session.execute(
            select(FeedbackRecord.stars, func.count(FeedbackRecord.id))
            .where(FeedbackRecord.stars.isnot(None))
            .group_by(FeedbackRecord.stars)
        )).all()
    total = int(row[0] or 0)
    avg = float(row[1]) if row[1] else None
    promoters = int(row[2] or 0)
    detractors = int(row[3] or 0)
    nps = round((promoters - detractors) / total * 100) if total else None
    return {
        "total": total,
        "avg_stars": round(avg, 2) if avg else None,
        "nps": nps,
        "distribution": {int(s): int(c) for s, c in dist},
    }


@router.get("/api/stats")
async def stats():
    """运营统计：对话量、评价、点踩率、热门问题"""
    async with database.async_session() as session:
        total = (await session.execute(select(func.count(FeedbackRecord.id)))).scalar() or 0
        up = (await session.execute(
            select(func.count(FeedbackRecord.id)).where(FeedbackRecord.rating == "up")
        )).scalar() or 0
        down = (await session.execute(
            select(func.count(FeedbackRecord.id)).where(FeedbackRecord.rating == "down")
        )).scalar() or 0
        recent_rows = (await session.execute(
            select(FeedbackRecord).order_by(FeedbackRecord.id.desc()).limit(20)
        )).scalars().all()
        # 词云数据：按问题原文聚合 top30
        wc_rows = (await session.execute(
            select(FeedbackRecord.question, func.count(FeedbackRecord.id).label("c"))
            .where(FeedbackRecord.question != "")
            .group_by(FeedbackRecord.question)
            .order_by(func.count(FeedbackRecord.id).desc())
            .limit(30)
        )).all()
        # 按天趋势（最近 14 天）：评价量 + 点踩量
        trend_rows = (await session.execute(
            select(
                func.date(FeedbackRecord.created_at).label("d"),
                func.count(FeedbackRecord.id).label("n"),
                func.sum(case((FeedbackRecord.rating == "down", 1), else_=0)).label("dn"),
            ).group_by("d").order_by("d").limit(14)
        )).all()
    # 按天平均响应时长（独立指标表，联到同一天）
    async with database.async_session() as session:
        lat_rows = (await session.execute(
            select(
                func.date(ChatMetricRecord.created_at).label("d"),
                func.avg(ChatMetricRecord.latency_ms).label("avg_ms"),
                func.count(ChatMetricRecord.id).label("n"),
            ).group_by("d").order_by("d").limit(14)
        )).all()
        overall_avg = (await session.execute(
            select(func.avg(ChatMetricRecord.latency_ms))
        )).scalar()
        # LLM 调用追踪统计（mini-Langfuse）
        llm_total = (await session.execute(select(func.count(LlmTraceRecord.id)))).scalar() or 0
        llm_fail = (await session.execute(
            select(func.count(LlmTraceRecord.id)).where(LlmTraceRecord.ok == False)  # noqa: E712
        )).scalar() or 0
        llm_avg = (await session.execute(
            select(func.avg(LlmTraceRecord.latency_ms))
        )).scalar()
        llm_recent_rows = (await session.execute(
            select(LlmTraceRecord).order_by(LlmTraceRecord.id.desc()).limit(15)
        )).scalars().all()
        # 按轨道聚合平均耗时
        track_rows = (await session.execute(
            select(LlmTraceRecord.track, func.avg(LlmTraceRecord.latency_ms).label("avg_ms"),
                   func.count(LlmTraceRecord.id).label("n"))
            .group_by(LlmTraceRecord.track)
        )).all()
    lat_by_day = {str(r.d): (float(r.avg_ms), int(r.n)) for r in lat_rows}
    daily = []
    seen = []
    for r in trend_rows:
        d = str(r.d)
        seen.append(d)
        avg = lat_by_day.pop(d, (None, 0))
        daily.append({"date": d, "count": int(r.n), "down": int(r.dn or 0),
                      "avg_latency_ms": round(avg[0]) if avg[0] else None})
    for d, (avg, n) in lat_by_day.items():  # 只有耗时没有评价的天也带上
        if d not in seen:
            daily.append({"date": d, "count": 0, "down": 0,
                          "avg_latency_ms": round(avg) if avg else None})
    daily.sort(key=lambda x: x["date"])
    daily = daily[-14:]

    # 热门问题：按问题原文去重计数
    q_counter = Counter((r.question or "").strip() for r in recent_rows if r.question)
    hot = [{"question": q, "count": c} for q, c in q_counter.most_common(8)]

    rated = up + down
    return {
        "total_feedback": total,
        "up": up,
        "down": down,
        "down_rate": round(down / rated, 3) if rated else 0.0,
        "hot_questions": hot,
        "wordcloud": [{"name": (q or "").strip()[:30], "value": int(c)} for q, c in wc_rows if (q or "").strip()],
        "avg_latency_ms": round(overall_avg) if overall_avg else None,
        "llm_stats": {
            "total_calls": llm_total,
            "fail_calls": llm_fail,
            "avg_latency_ms": round(llm_avg) if llm_avg else None,
            "by_track": [{"track": r.track, "avg_latency_ms": round(float(r.avg_ms)), "count": int(r.n)}
                         for r in track_rows],
            "recent": [
                {"track": t.track, "model": t.model, "latency_ms": t.latency_ms,
                 "prompt_chars": t.prompt_chars, "ok": bool(t.ok), "created_at": str(t.created_at)}
                for t in llm_recent_rows
            ],
        },
        "daily": daily,
        "recent": [
            {
                "sender_id": r.sender_id,
                "question": r.question,
                "rating": r.rating,
                "created_at": str(r.created_at),
            } for r in recent_rows
        ],
    }


# ---------------- 坏例复核队列（点踩的回复 → 人工复核） ----------------
class ReviewRequest(BaseModel):
    id: int
    status: int          # 1=已处理 2=知识缺失


@router.get("/api/review")
async def review_list():
    """待复核/已复核的坏例列表（点踩消息）"""
    async with database.async_session() as session:
        rows = (await session.execute(
            select(FeedbackRecord)
            .where(FeedbackRecord.rating == "down")
            .order_by(FeedbackRecord.reviewed, FeedbackRecord.id.desc())
            .limit(50)
        )).scalars().all()
    return {"items": [
        {
            "id": r.id,
            "sender_id": r.sender_id,
            "question": r.question,
            "answer": r.answer,
            "comment": r.comment or "",
            "reviewed": r.reviewed,
            "created_at": str(r.created_at),
        } for r in rows
    ]}


@router.post("/api/review")
async def review_update(req: ReviewRequest, x_admin_token: str = Header(default="")):
    verify_admin(x_admin_token)
    if req.status not in (0, 1, 2):
        raise HTTPException(status_code=400, detail="status 只能是 0待复核 / 1已处理 / 2知识缺失")
    async with database.async_session() as session:
        row = (await session.execute(
            select(FeedbackRecord).where(FeedbackRecord.id == req.id)
        )).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="记录不存在")
        row.reviewed = req.status
        await session.commit()
    return {"ok": True}


# ---------------- 转人工实时提醒 + 人工接管回复（管理端） ----------------

@router.get("/api/admin/transfer-alerts")
async def transfer_alerts(x_admin_token: str = Header(default="")):
    """管理端轮询：未处理的转人工事件列表"""
    verify_admin(x_admin_token)
    from models.kb import TransferEventRecord
    async with database.async_session() as session:
        rows = (await session.execute(
            select(TransferEventRecord)
            .where(TransferEventRecord.handled == 0)
            .order_by(TransferEventRecord.id.desc()).limit(20)
        )).scalars().all()
    return {"alerts": [{"id": r.id, "sender_id": r.sender_id,
                        "created_at": r.created_at.isoformat()} for r in rows]}


class AgentReplyRequest(BaseModel):
    sender_id: str
    text: str


@router.post("/api/admin/transfer-reply")
async def transfer_reply(req: AgentReplyRequest, x_admin_token: str = Header(default="")):
    """人工客服接管回复：以客服身份写进用户会话历史"""
    verify_admin(x_admin_token)
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="回复内容不能为空")
    from api.routers.dependencies import get_dialogue_state_repository, get_engine
    repo = await get_dialogue_state_repository.__anext__()  # async generator 取值
    engine = await get_engine()
    from service.dialogue_service import DialogueService
    service = DialogueService(dialogue_state_repository=repo, dialogue_engine=engine)
    result = await service.agent_reply(req.sender_id, req.text.strip()[:800])
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("detail", "无进行中的会话"))
    return {"ok": True, "message": "回复已送达用户会话"}
