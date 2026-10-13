# itzmy/task/handler.py

from domain.messages import BotMessage
from domain.state import DialogueState
from knowledge.intents import KnowledgeIntent
from knowledge.providers import KnowledgeChunk
from knowledge.registry import KnowledgeProviderRegistry
from knowledge.responder import KnowledgeResponder
from task.command.models import Command
from task.flow.flows import FlowsList
from task.command.processor import CommandProcessor
from task.action.runner import ActionRunner
from task.flow.executor import FlowExecutor
from chitchat.responder import ChitChatResponder


# 知识处理器
class KnowledgeHandler:

    def __init__(
            self,
            knowledge_intents: dict[str, KnowledgeIntent],
            provider_registry: KnowledgeProviderRegistry,
            knowledge_responder: KnowledgeResponder):

        self.knowledge_intents = knowledge_intents # 知识意图
        self.provider_registry = provider_registry # 知识提供者注册表
        self.knowledge_responder = knowledge_responder # 知识回复器

    async def handle(self, intents: list[str], state: DialogueState) -> list[BotMessage]:

        # 1. 根据意图寻找知识来源（知识提供者id列表）
        provider_ids: list[str] = self._get_provider_ids_by_intents(intents)

        # 2. 从每个 provider 检索知识片段
        chunks: list[KnowledgeChunk] = [] # 知识片段列表
        for provider_id in provider_ids: # 遍历每个知识提供者id
            provider = self.provider_registry.get(provider_id) # 获取知识提供者
            current_chunks = await provider.retrieve(state) # 从知识提供者检索知识片段
            chunks.extend(current_chunks)# 合并知识片段

        # 3. 用知识生成回复
        return await self.knowledge_responder.respond(
            user_message=state.pending_turn.user_message,# 用户消息
            recent_turns=state.current_session().turns,# 最近轮次
            chunks=chunks # 知识片段列表
        )

    def _get_provider_ids_by_intents(self, intents: list[str]) -> list[str]:
        provider_ids: list[str] = [] # 初始化
        for intent in intents:
            provider_ids.extend(self.knowledge_intents[intent].provider_ids)
        return list(set(provider_ids))

    async def _kb_chunks(self, state: DialogueState) -> list[KnowledgeChunk]:
        """知识库文档块检索（RAG 简化版）：取用户消息关键词，LIKE 匹配 KB 块 top2"""
        text = (state.pending_turn.user_message.text or "").strip()
        if len(text) < 2:
            return []
        # 提取 2 字以上的中文/英文词片段做 LIKE
        import re as _re
        kws = [w for w in _re.findall(r"[\u4e00-\u9fa5A-Za-z]{2,}", text) if len(w) >= 2][:6]
        if not kws:
            return []
        try:
            from sqlalchemy import or_, select as _select
            from infrastructure import database as _db
            from models.kb import KBChunkRecord
            conds = [KBChunkRecord.content.like(f"%{w}%") for w in kws]
            async with _db.async_session() as session:
                rows = (await session.execute(
                    _select(KBChunkRecord).where(or_(*conds)).limit(2)
                )).scalars().all()
            return [KnowledgeChunk(content=f"文档《{r.doc_name}》：{r.content}") for r in rows]
        except Exception:
            return []

    async def stream(self, intents: list[str], state: DialogueState) -> list:
        """流式版本：检索知识片段后逐 token 产出（yield ('text'|'object', 内容)）"""
        provider_ids: list[str] = self._get_provider_ids_by_intents(intents)
        chunks: list[KnowledgeChunk] = []
        for provider_id in provider_ids:
            provider = self.provider_registry.get(provider_id)
            chunks.extend(await provider.retrieve(state))
        chunks.extend(await self._kb_chunks(state))  # 注入知识库文档块
        async for kind, payload in self.knowledge_responder.respond_stream(
                user_message=state.pending_turn.user_message,
                recent_turns=state.current_session().turns,
                chunks=chunks):
            yield kind, payload


# 聊天处理器
class ChitChatHandler:
    def __init__(self, responder: ChitChatResponder):
        self.responder = responder

    async def handle(self, state: DialogueState) -> list[BotMessage]:
        pending_turn = state.pending_turn
        user_message = pending_turn.user_message
        recent_turns = state.current_session().turns

        return await self.responder.respond(
            user_message=user_message,
            recent_turns=recent_turns,
        )

    async def stream(self, state: DialogueState):
        """流式版本：逐 token 产出闲聊回复"""
        pending_turn = state.pending_turn
        async for kind, payload in self.responder.respond_stream(
                user_message=pending_turn.user_message,
                recent_turns=state.current_session().turns):
            yield kind, payload


# 任务处理器
class TaskHandler:

    def __init__(
            self,
            flows: FlowsList,
            command_processor: CommandProcessor,
            flow_executor: FlowExecutor,
            action_runner: ActionRunner
    ):
        self.command_processor = command_processor
        self.flows = flows
        self.flow_executor = flow_executor
        self.action_runner = action_runner

    async def handle(self, commands: list[Command], state: DialogueState) -> list[BotMessage]:
        # 阶段1:把命令应用到 state
        # 调用命令处理器
        self.command_processor.run(commands, state, self.flows)

        # 阶段2:推进流程,生成回复(下一节)
        messages: list[BotMessage] = await self.flow_executor.run_task(
            state, self.flows, self.action_runner
        )
        return messages

        return [BotMessage(text="任务已经处理")]
