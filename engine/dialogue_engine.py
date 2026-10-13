# itzmy/engine/dialogue_engine.py

import time

from domain.state import DialogueState
from domain.messages import UserMessage, ProcessResult, BotMessage, MessageType
from knowledge.intents import KNOWLEDGE_INTENTS
from plan.models import ClarifyReason
from task.command.models import Command, SetSlotsCommand
from task.flow.flows import FlowsList
from task.flow.steps import CollectFlowStep
from plan.turn_planner import TurnPlanner
from plan.turn_validator import TurnPlanValidator
from task.handler import TaskHandler, ChitChatHandler, KnowledgeHandler
from clarify.responder import ClarifyResponder


class DialogueEngine:

    def __init__(
            self,
            turn_planner: TurnPlanner,
            task_handler: TaskHandler,
            knowledge_handler: KnowledgeHandler,
            chitchat_handler: ChitChatHandler,
            clarify_responder: ClarifyResponder,
            turn_plan_validator: TurnPlanValidator
    ) -> None:
        pass
        self.turn_planner = turn_planner
        self.task_handler = task_handler
        self.knowledge_handler = knowledge_handler
        self.chitchat_handler = chitchat_handler
        self.clarify_responder = clarify_responder
        self.turn_plan_validator = turn_plan_validator

    def _prepare_session(self, dialogue_state: DialogueState) -> None:
        """
        准备会话
        :param dialogue_state:
        :return:
        """
        # 1. 获取当前会话
        session = dialogue_state.current_session()
        # 2. 如果当前会话不存在，则创建一个会话
        if session is None:
            dialogue_state.start_session()
            return
        # 3. 判断会话是否超时
        now = time.time()
        if now - session.last_activity_at > 60 * 60:  # 1小时
            # 关闭会话
            dialogue_state.close_current_session()
            # 重置运行时状态
            dialogue_state.reset_runtime_state_for_new_session()
            # 创建会话
            dialogue_state.start_session()
        else:  #
            # 更新会话（会话续期）  会话 创建 活跃时间 关闭时间
            session.last_activity_at = now

    def _begin_turn(self, dialogue_state: DialogueState, user_message: UserMessage) -> None:
        """
        开始一个turn
        :param dialogue_state:
        :param user_message:
        :return:
        """
        dialogue_state.begin_turn(user_message)

    async def _handle_text_message(self, dialogue_state: DialogueState) -> list[BotMessage]:

        # 1. 调 LLM 生成本轮计划（确定任务轨道） 让LLM 决定 走哪条路
        turn_plan = await self.turn_planner.predict(dialogue_state, self.task_handler.flows)

        # 2. 防幻觉校验(本节不实现,后面讲)
        # 2. 防幻觉校验：LLM 可能编造流程名/意图，或一次多意图
        validation = self.turn_plan_validator.validate(
            state=dialogue_state,
            turn_plan=turn_plan,
            flow_list=self.task_handler.flows,  # 注意：你 validator 的形参名叫 flow_list
            intents=KNOWLEDGE_INTENTS,
        )
        if not validation.valid:
            return await self.clarify_responder.respond(
                state=dialogue_state, reason=validation.reason,
            )

        # 3. 按轨道分发
        if turn_plan.task is not None:
            return await self.task_handler.handle(
                commands=turn_plan.task.commands,
                state=dialogue_state,
            )
        elif turn_plan.knowledge is not None:
            # 3.2 信息检索
            return await self.knowledge_handler.handle(intents=turn_plan.knowledge.intents, state=dialogue_state)
        else:
            # 闲聊轨道
            return await self.chitchat_handler.handle(state=dialogue_state)

    @staticmethod
    def _flow_has_unfilled_collect_slot(
            state: DialogueState,
            flows: FlowsList,
            slot_name: str,
    ) -> bool:
        # 判断 什么 可以返回  不可以返回  指令
        """检查当前流程是否定义了名为 slot_name 的收集槽且尚未填充。"""
        active_task = state.active_task  # 如果当前没有活跃的流程  不会填槽 （）
        # 校验  当前没有正在进行的流程
        if active_task is None:  # ① 没有活跃流程
            return False

        # 当前有活跃的流程  refund_request退款流程  tuikuan_request
        flow = flows.get_flow_by_id(active_task.flow_id)
        if flow is None:  # ② 流程 id 查不到(防御)
            return False

        # 订单号  我已经  提取过了 不再提取
        if active_task.slots.get(slot_name):  # ③ 这个槽已经填了
            return False

        for step in flow.steps:  # ④ 流程里有没有收集这个槽的步骤
            if isinstance(step, CollectFlowStep) and step.slot_name == slot_name:
                return True

        return False

    def _resolve_object_commands(
            self,
            message: UserMessage,
            state: DialogueState,
            flows: FlowsList,
    ) -> list[Command]:
        # 当前聚焦的对象
        message_object = message.object
        if message_object is None:  # 鲁棒性校验
            return []

        # order product
        object_type = message_object.type.strip().lower()

        if object_type == "order":  # 订单
            if self._flow_has_unfilled_collect_slot(state, flows, "order_number"):
                """
                {
                    'commands': 'set_slot',
                     slots= {'order_number': '01001'}
                }
                """  # true
                return [SetSlotsCommand(
                    command="set_slots",
                    slots={"order_number": message_object.id},
                )]
            return []

        if object_type == "product":  # 商品
            if self._flow_has_unfilled_collect_slot(state, flows, "product_id"):
                # true
                """
                  {
                    'commands': 'set_slot',
                     slots= {'product_id': '01001'}
                }
                
                """
                return [SetSlotsCommand(
                    command="set_slots",
                    slots={"product_id": message_object.id},
                )]
            return []

        return []

    async def _handle_object_message(
            self,
            message: UserMessage,
            state: DialogueState,
    ) -> list[BotMessage]:
        # 将对象解析成command(SetSlotsCommand)
        commands = self._resolve_object_commands(
            message=message,
            state=state,
            flows=self.task_handler.flows,
        )

        if commands:
            # 场景 A:对象能填当前槽 → 转成命令,推进流程
            return await self.task_handler.handle(commands=commands, state=state)

        # 没有匹配到 slot。如果用户正在一个流程中,不打断,让流程继续。
        if state.active_task is not None:
            # 场景 C:在流程里但槽不匹配 → 不打断,空命令让流程继续
            return await self.task_handler.handle(commands=[], state=state)

        # 场景 B:没有流程 → 澄清

        return await self.clarify_responder.respond(
            state=state,
            reason=ClarifyReason.OBJECT_REQUIRES_INTENT,
        )

    async def stream_text_message(self, dialogue_state: DialogueState, user_message: UserMessage):
        """文本消息流式处理生成器：yield ('text'|'object', payload)。
        与 process_message 同构（会话准备/turn/落库），仅回复产出改为逐 token。
        任务轨/澄清轨/对象消息仍整块产出（以 delta 一次推给前端）。"""
        self._prepare_session(dialogue_state)
        self._begin_turn(dialogue_state, user_message)

        parts: list[tuple[str, object]] = []   # 收集完整回复用于落库
        if user_message.type is not MessageType.TEXT:
            dialogue_state.set_focused_object(user_message.object)
            messages = await self._handle_object_message(message=user_message, state=dialogue_state)
            for m in messages:
                yield ('object' if m.object is not None else 'text'), (m if m.object is not None else m.text)
                parts.append(m)
            dialogue_state.pending_turn.bot_messages.extend(messages)
            dialogue_state.commit_turn()
            return

        # 1. LLM 路由（计划 + 校验）
        turn_plan = await self.turn_planner.predict(dialogue_state, self.task_handler.flows)
        validation = self.turn_plan_validator.validate(
            state=dialogue_state,
            turn_plan=turn_plan,
            flow_list=self.task_handler.flows,
            intents=KNOWLEDGE_INTENTS,
        )
        if not validation.valid:
            messages = await self.clarify_responder.respond(
                state=dialogue_state, reason=validation.reason,
            )
            for m in messages:
                yield 'text', m.text
                parts.append(m)
            dialogue_state.pending_turn.bot_messages.extend(messages)
            dialogue_state.commit_turn()
            return

        # 2. 按轨道流式分发
        if turn_plan.task is not None:
            messages = await self.task_handler.handle(commands=turn_plan.task.commands, state=dialogue_state)
            for m in messages:
                yield ('object' if m.object is not None else 'text'), (m if m.object is not None else m.text)
                parts.append(m)
        elif turn_plan.knowledge is not None:
            async for kind, payload in self.knowledge_handler.stream(
                    intents=turn_plan.knowledge.intents, state=dialogue_state):
                yield kind, payload
                parts.append(payload if kind == 'object' else ('text', payload))
        else:
            async for kind, payload in self.chitchat_handler.stream(state=dialogue_state):
                yield kind, payload
                parts.append(('text', payload))

        # 3. 落库：连续 text 片段合并为一条 BotMessage，object 保持独立
        bot_messages: list[BotMessage] = []
        text_buf: list[str] = []
        def _flush():
            if text_buf:
                bot_messages.append(BotMessage(text=''.join(text_buf)))
                text_buf.clear()
        for p in parts:
            if isinstance(p, BotMessage):
                _flush(); bot_messages.append(p)
            elif isinstance(p, tuple) and p[0] == 'object':
                _flush(); bot_messages.append(p[1])
            else:
                text_buf.append(p[1])
        _flush()
        dialogue_state.pending_turn.bot_messages.extend(bot_messages)
        dialogue_state.commit_turn()

    async def process_message(self, dialogue_state: DialogueState,
                              user_message: UserMessage) -> ProcessResult:        # TODO (用户的消息---->LLM路由(三条轨道的某一条) 执行某一条)
        # TODO  便利贴  TODOList  待办事项清单

        # 1. 准备会话
        self._prepare_session(dialogue_state)

        # 2. 开启本轮turn
        self._begin_turn(dialogue_state, user_message)

        # 3. 按消息类型分流
        if user_message.type is MessageType.TEXT:
            messages = await self._handle_text_message(dialogue_state)
        else:
            # 对象消息(本节不实现,后面讲)
            # 先将当前这一次 用户点击聚焦对象 存进状态  记录一下 当前聚焦的 是谁？
            dialogue_state.set_focused_object(user_message.object)

            # 调方法 要去处理 用户这一次 聚焦对象
            messages = await self._handle_object_message(message=user_message, state=dialogue_state)

        # 4. 把本轮回复写入turn
        dialogue_state.pending_turn.bot_messages.extend(messages)
        # 提交:turn 进入 session 历史
        dialogue_state.commit_turn()

        # 5. 组装返回结果
        return ProcessResult(
            sender_id=user_message.sender_id,
            message_id=user_message.message_id,
            messages=messages,
        )

        # return ProcessResult(
        #     sender_id=user_message.sender_id,
        #     message_id=user_message.message_id,
        #     messages=[
        #         BotMessage(text="我是智能小客服"),
        #         BotMessage(text="欢迎你来到这里...")
        #     ]
        #
        # )
