# itzmy/knowledge/responder.py

import json
import re

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from infrastructure.llm import llm
from domain.messages import UserMessage, BotMessage, FocusedObject
from domain.state import Turn
from prompts.history_builder import HistoryBuilder
from prompts.loader import load_prompt
from knowledge.providers import KnowledgeChunk, ProductSearchProvider

# 当你要走 知识 这个轨道的时候  调用
class KnowledgeResponder:

    async def respond(
            self,
            user_message: UserMessage,
            recent_turns: list[Turn],
            chunks: list[KnowledgeChunk]
    ) -> list[BotMessage]:
        # 0. 导购模式：商品搜索结果直接渲染成商品卡片，无需 LLM（快且稳定）
        for chunk in chunks:
            if chunk.content.startswith(ProductSearchProvider.SEARCH_PREFIX):
                return self._product_cards(chunk.content[len(ProductSearchProvider.SEARCH_PREFIX):])

        # 准备提示词上下文
        user_message = HistoryBuilder._render_user_message(user_message) # 渲染用户消息
        history = HistoryBuilder.build(recent_turns) # 构建历史对话
        knowledge_content = "\n\n".join([chunk.content for chunk in chunks]) # 合并知识内容

        # 构造chain
        prompt_text = load_prompt("knowledge_respond") # 加载知识回复提示词
        prompt = PromptTemplate.from_template(
            prompt_text,
            template_format="jinja2"
        ) # 构造提示词模板
        chain = prompt | llm | StrOutputParser()# 构造chain

        # 运行chain（埋点：LLM 调用追踪）
        from infrastructure.trace import trace_llm
        from conf.config import settings
        response = await trace_llm(
            "knowledge", settings.llm_model, prompt_text,
            chain.ainvoke({
                "user_message": user_message,
                "history": history,
                "knowledge_content": knowledge_content,
            }))  # 运行chain

        # 来源标注：FAQ 命中的回复，尾部追加知识来源，体现 RAG 引用可追溯
        titles = [m.group(1) for c in chunks
                  if (m := re.match(r"FAQ 命中《(.+?)》：", c.content))]
        if titles:
            response += "\n\n📚 来源：FAQ《" + "》《".join(titles) + "》"

        return [BotMessage(text=response)] # 返回机器人回复消息

    async def respond_stream(
            self,
            user_message: UserMessage,
            recent_turns: list[Turn],
            chunks: list[KnowledgeChunk]
    ):
        """流式版本：逐 token 产出文本（真·流式，首字秒回）。
        约定：正常情况只产出一条文本消息；商品卡片等特例仍整块产出（yield ('object', BotMessage)）。"""
        # 0. 导购模式：商品卡片整块返回
        for chunk in chunks:
            if chunk.content.startswith(ProductSearchProvider.SEARCH_PREFIX):
                for msg in self._product_cards(chunk.content[len(ProductSearchProvider.SEARCH_PREFIX):]):
                    yield ('text', msg.text) if msg.text else ('object', msg)
                return

        user_message = HistoryBuilder._render_user_message(user_message)
        history = HistoryBuilder.build(recent_turns)
        knowledge_content = "\n\n".join([chunk.content for chunk in chunks])

        prompt_text = load_prompt("knowledge_respond")
        prompt = PromptTemplate.from_template(prompt_text, template_format="jinja2")
        chain = prompt | llm | StrOutputParser()

        from conf.config import settings
        parts: list[str] = []
        try:
            async for delta in chain.astream({
                "user_message": user_message,
                "history": history,
                "knowledge_content": knowledge_content,
            }):
                if delta:
                    parts.append(delta)
                    yield ('text', delta)
        except Exception as e:
            if not parts:
                raise  # 一个字都没出 → 交给上层兜底报错
            yield ('text', '\n（回复生成中断，请重试）')
            return

        # 来源标注（流结束后一次性追加）
        titles = [m.group(1) for c in chunks
                  if (m := re.match(r"FAQ 命中《(.+?)》：", c.content))]
        tail = ''
        if titles:
            tail = "\n\n📚 来源：FAQ《" + "》《".join(titles) + "》"
            yield ('text', tail)

    @staticmethod
    def _product_cards(json_str: str) -> list[BotMessage]:
        """把商品搜索结果渲染成 文案 + 商品卡片（点击可继续咨询）"""
        try:
            items = json.loads(json_str)
        except Exception:
            return [BotMessage(text="（商品数据解析失败，请稍后再试）")]
        if not items:
            return [BotMessage(text="暂时没找到相关商品 😢 可以换个说法试试，比如「有没有 T 恤」或「手机在卖吗」～")]
        msgs = [BotMessage(text=f"为你找到 {len(items)} 件相关商品 👇 点卡片可以直接继续咨询：")]
        for p in items[:4]:
            msgs.append(BotMessage(object=FocusedObject(
                id=p.get("product_id", ""),
                type="product",
                title=p.get("title", ""),
                attributes={"price": p.get("price"), "stock": p.get("stock"), "status": p.get("status")},
            )))
        return msgs
