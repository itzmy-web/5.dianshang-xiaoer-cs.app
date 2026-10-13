# itzmy/task/action/builtin/action_response.py

from typing import Any

from jinja2 import Template
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate

from domain.messages import BotMessage
from domain.state import DialogueState
from infrastructure.llm import llm
from prompts.history_builder import HistoryBuilder
from task.action.base import Action, ActionResult


class ActionResponse(Action):
    name = "action_response"

    async def run(self, state: DialogueState, action_kwargs: dict[str, Any]) -> ActionResult:
        """
        响应内容
        :param state:
        :param action_kwargs:
        :return:
        """

        mode = action_kwargs.get("mode", "static")
        if mode == "static":  # 1️⃣ 纯模板.不碰LLM
            text = action_kwargs['text']
            rendered_text = self._render_text(text, state)  # 组装提示词
            return ActionResult(messages=[BotMessage(text=rendered_text)])

        elif mode == "rephrase":  # 模板打底稿 + LLM润色
            text = action_kwargs['text']
            rendered_text = self._render_text(text, state)  # 组装提示词
            prompt_text = action_kwargs['prompt']
            message = await self._call_llm(prompt_text, state, rendered_text)
            return ActionResult(messages=[BotMessage(text=message)])

        else:  # generate   # 完全由LLM 生成
            prompt_text = action_kwargs['prompt']
            message = await self._call_llm(prompt_text, state)
            return ActionResult(messages=[BotMessage(text=message)])

    def _render_text(self, text: str, state: DialogueState) -> str:
        # 把模板里的 {{  }} 替换成真实值。
        template = Template(text)
        result = template.render(
            slots=state.active_task.slots if state.active_task else {},
            context=state.active_system_task or state.active_task,
        )
        return result

    async def _call_llm(self, prompt_text: str, state: DialogueState, rendered_text: str = "") -> str:
        """
        rephrase 和 generate 都走这个方法，区别在传不传 rendered_text
        :param prompt_text:
        :param state:
        :param rendered_text:
        :return:
        """
        prompt = PromptTemplate.from_template(prompt_text)
        chain = prompt | llm | StrOutputParser()

        bot_message = await chain.ainvoke({
            "history": HistoryBuilder.build(state.current_session().turns),
            "user_message": HistoryBuilder._render_user_message(state.pending_turn.user_message),
            "current_response": rendered_text,
        })
        return bot_message


if __name__ == '__main__':
    import asyncio

    from domain.state import DialogueState, Turn, Session
    from domain.contexts import TaskContext
    from domain.messages import UserMessage, MessageType


    def build_state() -> DialogueState:
        """构造一个查订单场景的对话状态（槽位已填好）"""
        return DialogueState(
            sender_id="user_001",
            active_task=TaskContext(
                flow_id="order_status_query",
                step_id="show_order_status",
                slots={"order_number": "A001", "order_status": "已发货"},
            ),
            sessions=[Session(
                session_id="s1",
                started_at=0.0,
                last_activity_at=0.0,
            )],
            current_session_id="s1",
            pending_turn=Turn(
                turn_id="t1",
                user_message=UserMessage(
                    sender_id="user_001",
                    message_id="m1",
                    type=MessageType.TEXT,
                    text="帮我查一下订单 A001",
                ),
                bot_messages=[],
            ),
        )


    async def test_static():
        """① static：纯模板，不调 LLM"""
        action = ActionResponse()
        r = await action.run(build_state(), {
            "mode": "static",
            "text": "订单{{ slots.order_number }}当前状态是：{{ slots.order_status }}",
        })
        print("static   ->", r.messages[0].text)


    async def test_rephrase():
        """② rephrase：模板打底稿 + LLM 润色"""
        action = ActionResponse()
        r = await action.run(build_state(), {
            "mode": "rephrase",
            "text": "订单{{ slots.order_number }}当前状态是：{{ slots.order_status }}",
            "prompt": (
                "你是中文电商客服，语气自然友好。\n"
                "基于建议回复改写得更自然，保持原意，不要扩写。\n"
                "建议回复：{current_response}"
            ),
        })
        print("rephrase ->", r.messages[0].text)


    async def test_generate():
        """③ generate：不读 text，LLM 从零生成"""
        action = ActionResponse()
        r = await action.run(build_state(), {
            "mode": "generate",
            "prompt": "你是中文电商客服，请友好地回复用户：{user_message}",
        })
        print("generate ->", r.messages[0].text)


    async def main():
        # await test_static()    # 不需要时注释掉
        # await test_rephrase()  # 不需要时注释掉
        await test_generate()  # 不需要时注释掉


    asyncio.run(main())
