# itzmy/chitchat/responder.py

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from domain.messages import UserMessage, BotMessage
from domain.state import Turn
from prompts.history_builder import HistoryBuilder
from prompts.loader import load_prompt
from infrastructure.llm import llm


class ChitChatResponder:

    async def respond(self,
                      user_message: UserMessage,
                      recent_turns: list[Turn]):
        # 处理一下消息 文本
        user_message = HistoryBuilder._render_user_message(user_message)

        history = HistoryBuilder.build(recent_turns)

        prompt_text = load_prompt("chitchat_respond")
        prompt = PromptTemplate.from_template(prompt_text, template_format="jinja2")
        chain = prompt | llm | StrOutputParser()
        from infrastructure.trace import trace_llm
        from conf.config import settings
        response = await trace_llm(
            "chitchat", settings.llm_model, prompt_text,
            chain.ainvoke({
                "user_message": user_message,
                "history": history,
            }))
        return [BotMessage(text=response)]

    async def respond_stream(self, user_message: UserMessage, recent_turns: list[Turn]):
        """流式版本：逐 token 产出闲聊回复（真·流式）"""
        user_message = HistoryBuilder._render_user_message(user_message)
        history = HistoryBuilder.build(recent_turns)

        prompt_text = load_prompt("chitchat_respond")
        prompt = PromptTemplate.from_template(prompt_text, template_format="jinja2")
        chain = prompt | llm | StrOutputParser()

        async for delta in chain.astream({
            "user_message": user_message,
            "history": history,
        }):
            if delta:
                yield ('text', delta)
