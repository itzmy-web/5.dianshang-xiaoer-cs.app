# itzmy/service/dialogue_service.py
import re

from api.schemas import HistoryMessage
from domain.messages import UserMessage, ProcessResult, BotMessage, MessageType
from domain.state import DialogueState
from prompts.history_builder import HistoryBuilder
from repository.dialogue_state_repository import DialogueStateRepository
from engine.dialogue_engine import DialogueEngine
from infrastructure import database
from models.profile import UserProfileRecord
from models.kb import TransferEventRecord

# 会话记忆：「叫我土豆 / 请叫我土豆 / 我的名字是土豆」→ 提取昵称
NICKNAME_RE = re.compile(r"(?:叫我|请叫我|称呼我[为]|我的名字[是叫])\s*([\u4e00-\u9fa5A-Za-z0-9_·]{1,12})")
# 转人工关键词（整句匹配，避免误伤普通问题）
TRANSFER_RE = re.compile(r"^(?:转|找|接)?(?:人工|真人)(?:客服)?[!！。~～?？]?$")
# 告别关键词（触发会话小结）
FAREWELL_RE = re.compile(r"^(?:没了|没有了|没事了|没有了谢谢|没了谢谢|谢谢|谢谢啦|好的谢谢|拜拜|再见|bye)(?:[!！。~～\s]*)$")
# 负面情绪关键词（情绪检测：连续命中 2 次 → 安抚 + 主动建议转人工）
NEGATIVE_WORDS = ("破店", "垃圾", "什么玩意", "气死", "投诉", "差评", "骗子", "坑人",
                  "无语", "神经", "废物", "滚", "客服呢", "没人管", "太差了", "什么服务")


def _is_negative(text: str) -> bool:
    return any(w in text for w in NEGATIVE_WORDS)


def _summarize_topics(state: DialogueState) -> list[str]:
    """扫描本会话历史，归纳聊过的话题（确定性规则，不调 LLM）"""
    topics = set()
    session = state.current_session()
    turns = session.turns if session else []
    for t in turns:
        txt = (t.user_message.text or "")
        if any(k in txt for k in ("物流", "到哪", "单号", "订单")):
            topics.add("📦 订单/物流查询")
        if "退款" in txt or "退货" in txt:
            topics.add("💸 退款/退货")
        if any(k in txt for k in ("推荐", "有没有", "想买", "商品")):
            topics.add("🛍️ 商品导购")
        if any(k in txt for k in ("发货", "运费", "发票", "会员", "优惠券", "政策")):
            topics.add("📚 政策咨询")
    return sorted(topics)


class DialogueService:
    """
    处理对话的业务类
    """

    def __init__(self, dialogue_state_repository: DialogueStateRepository,
                 dialogue_engine: DialogueEngine):
        self.dialogue_state_repository = dialogue_state_repository
        self.dialogue_engine = dialogue_engine

    async def process_message(self, user_message: UserMessage) -> ProcessResult:
        """
        核心处理逻辑(IO：很慢/计算:调用LLM以及执行引擎、比较慢)
        :param user_message:
        :return:
        """
        # 1. 通过 repository 根据 sender_id 加载对话状态(O 阶段)  先取数据
        dialogue_state: DialogueState = await self.dialogue_state_repository.load_state(user_message.sender_id)

        # 1.5 文本消息预处理：会话记忆 / 转人工拦截
        if user_message.type is MessageType.TEXT and user_message.text:
            text = user_message.text.strip()

            # ① 转人工：固定话术，不进三轨路由（照常记入历史）
            if TRANSFER_RE.match(text):
                try:
                    async with database.async_session() as s:
                        s.add(TransferEventRecord(sender_id=user_message.sender_id))
                        await s.commit()
                except Exception:
                    pass
                return await self._canned_turn(
                    dialogue_state, user_message,
                    [BotMessage(text="已为您转接人工客服，当前排队第 1 位，预计等待 30 秒 ⏳"),
                     BotMessage(text="（演示环境：人工坐席由 AI 小二继续顶班，有什么问题请直接说～）")],
                )

            # ② 告别小结：「没了/谢谢/拜拜」→ 自动总结本次对话，引导评价
            if FAREWELL_RE.match(text):
                session = dialogue_state.current_session()
                n_turns = len(session.turns) if session else 1
                topics = _summarize_topics(dialogue_state)
                lines = [f"客官慢走～ 本次对话小结：", f"• 共 {max(n_turns, 1)} 轮对话"]
                lines += [f"• 处理了：{tp}" for tp in topics] or ["• 闲聊陪伴 🎈"]
                lines.append("有其他问题随时来找我，欢迎给刚才的服务点个 👍/👎 哦！")
                return await self._canned_turn(
                    dialogue_state, user_message,
                    [BotMessage(text="\n".join(lines))],
                )

            # ③ 昵称记忆：「叫我XX」→ 存画像并固定确认，不惊动 LLM
            m = NICKNAME_RE.search(text)
            if m:
                nick = m.group(1)
                await self._save_nickname(user_message.sender_id, nick)
                return await self._canned_turn(
                    dialogue_state, user_message,
                    [BotMessage(text=f"好嘞，{nick}！我记住你了，以后就这么称呼你～ 消息历史会跟着账号走，下次回来我还认识你 😄")],
                )

            # ④ 已有昵称 → 注入提示词，让三条轨道的 LLM 都会自然称呼用户
            profile = await self._get_profile(user_message.sender_id)
            if profile and profile.nickname:
                user_message.profile_hint = f"（备注：该用户希望被称呼为「{profile.nickname}」，回复时可以自然地这样称呼）"

        # 2. 使用 engine 根据对话状态处理最新消息
        process_result: ProcessResult = await self.dialogue_engine.process_message(dialogue_state, user_message)

        # 2.5 情绪检测：负面消息连续 ≥2 条 → 追加安抚话术 + 主动建议转人工
        if user_message.type is MessageType.TEXT and user_message.text:
            if _is_negative(user_message.text):
                dialogue_state.negative_streak = getattr(dialogue_state, "negative_streak", 0) + 1
                if dialogue_state.negative_streak >= 2:
                    process_result.messages.append(BotMessage(
                        text="听到你这么说，小二真的很过意不去 🙏 你的反馈我已经如实记录并优先标注了。"
                             "如果还是解决不了，随时说「转人工」，我们的人工坐席马上接手！"))
            else:
                dialogue_state.negative_streak = 0

        # 3. 通过 repository 保存最新的对话状态(I 阶段)  存
        await self.dialogue_state_repository.save_state(dialogue_state)
        # 4. 返回本轮处理结果
        return process_result

    # ---------------- 内部工具 ----------------

    async def _canned_turn(self, dialogue_state: DialogueState,
                           user_message: UserMessage, messages: list[BotMessage]) -> ProcessResult:
        """不走引擎的固定回复：同样记入会话历史并落库，保证刷新后历史完整"""
        if dialogue_state.current_session() is None:
            dialogue_state.start_session()
        dialogue_state.begin_turn(user_message)
        if dialogue_state.pending_turn is not None:
            dialogue_state.pending_turn.bot_messages.extend(messages)
            dialogue_state.commit_turn()
        await self.dialogue_state_repository.save_state(dialogue_state)
        return ProcessResult(
            sender_id=user_message.sender_id,
            message_id=user_message.message_id,
            messages=messages,
        )

    async def _get_profile(self, sender_id: str) -> UserProfileRecord | None:
        async with database.async_session() as session:
            return (await session.execute(
                select_profile(sender_id)
            )).scalar_one_or_none()

    async def _save_nickname(self, sender_id: str, nickname: str) -> None:
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert
        async with database.async_session() as session:
            stmt = sqlite_insert(UserProfileRecord).values(
                sender_id=sender_id, nickname=nickname)
            stmt = stmt.on_conflict_do_update(
                index_elements=[UserProfileRecord.sender_id],
                set_={"nickname": nickname})
            await session.execute(stmt)
            await session.commit()

    # ---------------- 新会话 / 流程进度 / 流式 / 会话列表 / 转人工接管 ----------------

    async def stream_message(self, user_message: UserMessage):
        """流式处理生成器：yield ('text'|'object', payload)。
        预检命中（转人工/告别/昵称）时整块产出；否则走引擎 token 级流式。
        复用 process_message 的预检与后处理（情绪检测），保证行为一致。"""
        dialogue_state: DialogueState = await self.dialogue_state_repository.load_state(user_message.sender_id)

        parts: list[tuple[str, object]] = []
        if user_message.type is MessageType.TEXT and user_message.text:
            text = user_message.text.strip()

            if TRANSFER_RE.match(text):
                try:
                    async with database.async_session() as s:
                        s.add(TransferEventRecord(sender_id=user_message.sender_id))
                        await s.commit()
                except Exception:
                    pass
                msgs = [BotMessage(text="已为您转接人工客服，当前排队第 1 位，预计等待 30 秒 ⏳"),
                        BotMessage(text="（演示环境：人工坐席由 AI 小二继续顶班，有什么问题请直接说～）")]
                for m in msgs:
                    yield 'text', m.text; parts.append(m)
                await self._canned_turn(dialogue_state, user_message, msgs)
                return

            if FAREWELL_RE.match(text):
                session = dialogue_state.current_session()
                n_turns = len(session.turns) if session else 1
                topics = _summarize_topics(dialogue_state)
                lines = ["客官慢走～ 本次对话小结：", f"• 共 {max(n_turns, 1)} 轮对话"]
                lines += [f"• 处理了：{tp}" for tp in topics] or ["• 闲聊陪伴 🎈"]
                lines.append("有其他问题随时来找我，欢迎给刚才的服务点个 👍/👎 哦！")
                msg = BotMessage(text="\n".join(lines))
                yield 'text', msg.text; parts.append(msg)
                await self._canned_turn(dialogue_state, user_message, [msg])
                return

            m = NICKNAME_RE.search(text)
            if m:
                nick = m.group(1)
                await self._save_nickname(user_message.sender_id, nick)
                msg = BotMessage(text=f"好嘞，{nick}！我记住你了，以后就这么称呼你～ 消息历史会跟着账号走，下次回来我还认识你 😄")
                yield 'text', msg.text; parts.append(msg)
                await self._canned_turn(dialogue_state, user_message, [msg])
                return

            profile = await self._get_profile(user_message.sender_id)
            if profile and profile.nickname:
                user_message.profile_hint = f"（备注：该用户希望被称呼为「{profile.nickname}」，回复时可以自然地这样称呼）"

        # 引擎流式
        gen = (self.dialogue_engine.stream_text_message(dialogue_state, user_message)
               if user_message.type is MessageType.TEXT
               else self._stream_object(dialogue_state, user_message))
        async for kind, payload in gen:
            yield kind, payload
            parts.append((kind, payload))

        # 情绪检测后处理（与 process_message 行为一致）
        if user_message.type is MessageType.TEXT and user_message.text and _is_negative(user_message.text):
            dialogue_state.negative_streak = getattr(dialogue_state, "negative_streak", 0) + 1
            if dialogue_state.negative_streak >= 2:
                warn = "听到你这么说，小二真的很过意不去 🙏 你的反馈我已经如实记录并优先标注了。如果还是解决不了，随时说「转人工」，我们的人工坐席马上接手！"
                yield 'text', warn
        else:
            dialogue_state.negative_streak = 0
        await self.dialogue_state_repository.save_state(dialogue_state)

    async def _stream_object(self, dialogue_state: DialogueState, user_message: UserMessage):
        """对象消息走原同步路径，包装成生成器（保持流式协议统一）"""
        self.dialogue_engine._prepare_session(dialogue_state)
        self.dialogue_engine._begin_turn(dialogue_state, user_message)
        dialogue_state.set_focused_object(user_message.object)
        messages = await self.dialogue_engine._handle_object_message(message=user_message, state=dialogue_state)
        for m in messages:
            yield ('object' if m.object is not None else 'text'), (m if m.object is not None else m.text)
        dialogue_state.pending_turn.bot_messages.extend(messages)
        dialogue_state.commit_turn()

    async def list_sessions(self, sender_id: str) -> list[dict]:
        """历史会话列表（新→旧）"""
        state = await self.dialogue_state_repository.load_state(sender_id)
        out: list[dict] = []
        for s in reversed(state.sessions):
            first_user = next((t.user_message.text or '[图片/卡片消息]'
                               for t in s.turns if t.user_message.text), '[图片/卡片消息]')
            out.append({
                "session_id": s.session_id,
                "turns": len(s.turns),
                "started_at": getattr(s, "started_at", None),
                "summary": (first_user[:40] or '（空）'),
                "current": (s is state.current_session()),
            })
        return out

    async def load_session_messages(self, sender_id: str, session_id: str) -> list[HistoryMessage]:
        """渲染指定会话的消息（供前端切换查看）"""
        state = await self.dialogue_state_repository.load_state(sender_id)
        target = next((s for s in state.sessions if s.session_id == session_id), None)
        if target is None:
            return []
        msgs: list[HistoryMessage] = []
        for turn in target.turns:
            msgs.append(HistoryBuilder.render_user_message(session_id, turn.user_message))
            msgs.extend([HistoryBuilder.render_bot_messages(session_id, b) for b in turn.bot_messages])
        return msgs

    async def agent_reply(self, sender_id: str, text: str) -> dict:
        """人工客服接管回复：以客服身份追加到该用户当前会话最后一个 turn"""
        state = await self.dialogue_state_repository.load_state(sender_id)
        session = state.current_session()
        if session is None or not session.turns:
            return {"ok": False, "detail": "该用户当前没有进行中的会话"}
        last_turn = session.turns[-1]
        last_turn.bot_messages.append(BotMessage(text="👤 人工客服：" + text))
        await self.dialogue_state_repository.save_state(state)
        return {"ok": True}

    async def poll_messages(self, sender_id: str, after: int) -> dict:
        """用户端轮询：返回全部消息（前端按序号增量渲染）+ 未读人工回复"""
        msgs = await self.load_chat_history(sender_id)
        total = len(msgs)
        fresh = msgs[after:] if after < total else []
        return {"total": total, "messages": fresh}

    async def new_session(self, sender_id: str) -> dict:
        """「➕ 新话题」：关闭当前会话（历史保留），下条消息自动开新会话，避免多任务串味"""
        state = await self.dialogue_state_repository.load_state(sender_id)
        if state.current_session() is not None:
            state.close_current_session()
        state.reset_runtime_state_for_new_session()
        await self.dialogue_state_repository.save_state(state)
        return {"ok": True, "message": "已开启新话题"}

    async def load_progress(self, sender_id: str) -> dict:
        """任务流程进度（前端渲染步骤条）"""
        state = await self.dialogue_state_repository.load_state(sender_id)
        task = state.active_task
        if task is None:
            return {"active": False}
        slots = task.slots or {}
        flow_id = task.flow_id or ""
        flow_names = {
            "refund_request": "退款申请",
            "order_status_query": "订单查询",
            "logistics_tracking": "物流查询",
            "similar_product_recommendation": "商品推荐",
        }
        return {
            "active": True,
            "flow_id": flow_id,
            "flow_name": flow_names.get(flow_id, flow_id),
            "has_order_number": bool(slots.get("order_number")),
            "has_refund_reason": bool(slots.get("refund_reason")),
            "has_product_id": bool(slots.get("product_id")),
        }

    async def load_chat_history(self, sender_id: str) -> list[HistoryMessage]:

        # 根据 sender_id 从数据库加载完整 DialogueState
        state = await self.dialogue_state_repository.load_state(sender_id)

        # 遍历 state.sessions，把每个 turn 展开成消息列表
        chat_messages: list[HistoryMessage] = []
        for session in state.sessions:
            for turn in session.turns:
                # 从数据库中 取出所有状态(用户消息)  渲染指定模型（HistoryMessage ）
                chat_messages.append(HistoryBuilder.render_user_message(session.session_id, turn.user_message))
                chat_messages.extend([
                    HistoryBuilder.render_bot_messages(session.session_id, b_msg) for b_msg in turn.bot_messages
                ])

        # 返回给 router 组装的结果
        return chat_messages


def select_profile(sender_id: str):
    from sqlalchemy import select
    return select(UserProfileRecord).where(UserProfileRecord.sender_id == sender_id)
