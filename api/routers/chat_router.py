import asyncio
import json
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from api.routers.dependencies import get_dialogue_service
from api.schemas import ChatRequest, ChatResponse, ChatBotMessage, ChatObject, HistoryMessage, HistoryResponse
from domain.messages import ProcessResult, UserMessage, MessageType, FocusedObject
from service.dialogue_service import DialogueService
from infrastructure import database
from models.metric import ChatMetricRecord

router = APIRouter()


async def _record_metric(sender_id: str, latency_ms: int) -> None:
    """落库回复耗时（可观测：看板展示平均响应时长）"""
    try:
        async with database.async_session() as session:
            session.add(ChatMetricRecord(sender_id=sender_id, latency_ms=latency_ms))
            await session.commit()
    except Exception:
        pass  # 指标失败不影响主链路


# 定义路由接口

@router.post("/api/chat")
async def chat_endpoint(
        chat_request: ChatRequest,
        dialogue_service: DialogueService = Depends(get_dialogue_service)
) -> ChatResponse:
    # 1. 处理输入接口模型  将前端传过来的数据 实例化成 对象  将数据 存进对象里  user_message.message_id
    user_message = _build_user_message(chat_request)
    # 2. 业务处理  HTTP --->chat_router.py ----> service ---> engine 调用链路
    t0 = time.time()
    process_result: ProcessResult = await dialogue_service.process_message(user_message)
    elapsed_ms = int((time.time() - t0) * 1000)
    await _record_metric(chat_request.sender_id, elapsed_ms)
    # 3. 处理输出接口模型
    return _build_chat_response(process_result, elapsed_ms)


def _build_user_message(chat_request: ChatRequest) -> UserMessage:
    """
    将请求数据模型转换为领域数据模型 供业务使用
    :param chat_request:
    :return:
    """
    # 鲁棒性兜底: text 和 object 都为空时, 直接拒绝, 不进入业务链路
    # (否则会被判成 OBJECT 消息但 object=None, 在 HistoryBuilder 渲染时崩溃)
    if not chat_request.text and chat_request.object is None:
        raise HTTPException(
            status_code=400,
            detail="text 和 object 至少要传一个",
        )

    return UserMessage(
        sender_id=chat_request.sender_id,
        message_id=chat_request.message_id if chat_request.message_id else str(uuid.uuid4()),
        type=MessageType.TEXT if chat_request.text else MessageType.OBJECT,
        text=chat_request.text,
        object=FocusedObject(
            id=chat_request.object.id,
            type=chat_request.object.type,
            title=chat_request.object.title,
            attributes=chat_request.object.attributes,
        ) if chat_request.object else None
    )


def _build_chat_response(process_result: ProcessResult, elapsed_ms: int | None = None) -> ChatResponse:
    return ChatResponse(
        sender_id=process_result.sender_id,
        message_id=process_result.message_id,
        elapsed_ms=elapsed_ms,
        messages=[
            ChatBotMessage(
                text=bot_msg.text,
                object=ChatObject(
                    type=bot_msg.object.type,
                    id=bot_msg.object.id,
                    title=bot_msg.object.title,
                    attributes=bot_msg.object.attributes
                ) if bot_msg.object else None
            )
            for bot_msg in process_result.messages
        ]
    )


# @router.get('/api/chat/history')
# async def history(sender_id: str) -> HistoryResponse:
#     return HistoryResponse(
#         sender_id=sender_id,
#         messages=[
#             HistoryMessage(role='user', text='你好'),
#             HistoryMessage(role='bot', text='我不好'),
#         ],
#     )

@router.get("/api/chat/history")
async def history(sender_id: str, service: DialogueService = Depends(get_dialogue_service)) -> HistoryResponse:
    chat_message_response: list[HistoryMessage] = await service.load_chat_history(sender_id)
    return HistoryResponse(sender_id=sender_id, messages=chat_message_response)


@router.post("/api/chat/new-session")
async def new_session(chat_request: ChatRequest, service: DialogueService = Depends(get_dialogue_service)):
    """「➕ 新话题」：关闭当前会话，避免多任务串味（历史保留）"""
    return await service.new_session(chat_request.sender_id)


@router.get("/api/chat/progress")
async def progress(sender_id: str, service: DialogueService = Depends(get_dialogue_service)):
    """任务流程进度（前端步骤条）"""
    return await service.load_progress(sender_id)


# ---------------- SSE 流式回复（打字机效果） ----------------
# 事件协议：
#   {type:"start", count}                    回复开始，共 count 条消息
#   {type:"msg_start", index}                第 index 条文本消息开始
#   {type:"delta", index, delta}             第 index 条的增量文本
#   {type:"msg_end", index}                  第 index 条文本结束
#   {type:"object", index, object}           第 index 条的对象（卡片）
#   {type:"done", message_id}                全部结束
#   {type:"error", detail}                   出错
@router.post("/api/chat/stream")
async def chat_stream(
        chat_request: ChatRequest,
        dialogue_service: DialogueService = Depends(get_dialogue_service),
):
    async def event_gen():
        try:
            user_message = _build_user_message(chat_request)
        except HTTPException as e:
            yield f"data: {json.dumps({'type': 'error', 'detail': e.detail}, ensure_ascii=False)}\n\n"
            return
        yield f"data: {json.dumps({'type': 'start'}, ensure_ascii=False)}\n\n"
        t0 = time.time()
        idx = 0
        try:
            yield f"data: {json.dumps({'type': 'start', 'count': 1}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'msg_start', 'index': 0}, ensure_ascii=False)}\n\n"
            async for kind, payload in dialogue_service.stream_message(user_message):
                if kind == 'object':
                    # 对象（卡片）以 object 事件整块推送
                    yield f"data: {json.dumps({'type': 'object', 'index': idx, 'object': payload.model_dump()}, ensure_ascii=False)}\n\n"
                else:
                    # 真·流式：LLM token 直接透传（不再伪 3 字符切片）
                    yield f"data: {json.dumps({'type': 'delta', 'index': idx, 'delta': payload}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'msg_end', 'index': idx}, ensure_ascii=False)}\n\n"
            elapsed_ms = int((time.time() - t0) * 1000)
            await _record_metric(chat_request.sender_id, elapsed_ms)
            yield f"data: {json.dumps({'type': 'done', 'elapsed_ms': elapsed_ms}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'msg_end', 'index': idx}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'error', 'detail': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------- 会话列表 / 会话消息 / 用户端轮询 ----------------

@router.get("/api/chat/sessions")
async def sessions(sender_id: str, service: DialogueService = Depends(get_dialogue_service)):
    return {"sessions": await service.list_sessions(sender_id)}


@router.get("/api/chat/session-messages")
async def session_messages(sender_id: str, session_id: str,
                           service: DialogueService = Depends(get_dialogue_service)):
    return {"sender_id": sender_id, "session_id": session_id,
            "messages": await service.load_session_messages(sender_id, session_id)}


@router.get("/api/chat/poll")
async def poll(sender_id: str, after: int = 0,
               service: DialogueService = Depends(get_dialogue_service)):
    """用户端轮询增量消息（人工接管回复靠它实时到达）"""
    return await service.poll_messages(sender_id, after)
