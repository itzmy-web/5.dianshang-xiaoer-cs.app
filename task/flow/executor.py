# itzmy/task/flow/executor.py
from domain.contexts import CollectedSystemContext
from domain.messages import BotMessage
from domain.state import DialogueState
from task.action.base import ActionResult
from task.flow.flows import FlowsList
from task.action.runner import ActionRunner, ActionCall
from task.flow.links import StaticLink, ConditionalLink, FallbackLink
from task.flow.steps import FlowStep, StartFlowStep, EndFlowStep, CollectFlowStep, ActionFlowStep


class FlowExecutor:
    """
    流程执行器：推进yaml中定义的业务任务流程以及系统任务流程
    """

    async def run_task(self, state: DialogueState, flows: FlowsList, action_runner: ActionRunner):

        messages: list[BotMessage] = []
        while True:  # 找要执行的流程步骤

            # 1. 取"下一个"要执行的单个动作:沿流程推进 step,遇 action step 返回其 ActionCall;
            #  若已无活跃任务可推进,则返回 action_listen 哨兵(该等用户输入了)
            action_call: ActionCall = self.advance_until_action(state, flows)

            # 2. 当action_name是action_listen的时候，结束流程，并返回消息，等待下一轮的用户输入
            if action_call.action_name == "action_listen":
                break
            else:

                # 3. 如果是其他类型的action，则执行action
                action_result: ActionResult = await action_runner.run(action_call, state)
                state.set_slots(action_result.slot_updates)
                messages.extend(action_result.messages)
                """
        slot_updates = {"order_status": "已发货"}   ← set_slots 写回 state
        messages  = [BotMessage("您的订单已发货，单号...")]  ← extend 收进 messages
                """

        # 4. 返回消息，等待下一轮的用户输入
        return messages

    def advance_until_action(self, state: DialogueState, flows: FlowsList) -> ActionCall:

        while True:

            # 1. 获取当前任务上下文对象：系统任务优先
            current_active_task = state.current_active_task()  # 申请退款

            # 2. 如果当前没有任务，手动返回action_listen，等待用户输入
            # 两种典型情况：
            # - 业务流程刚跑完 end 步骤，active_task 被清空，又没有系统过场
            # - 用户刚启动会话，根本还没开任何任务
            if current_active_task is None:  # 没有任务
                return ActionCall(action_name="action_listen")  # 有任务

            # 3. 获取当前流程对象
            flow = flows.get_flow_by_id(current_active_task.flow_id)

            # 4. 获取当前step
            step = flow.get_step_by_id(current_active_task.step_id)

            # 5. 运行当前step
            action_call = self._run_step(state, step, flows)  # action

            # 6. 如果step的类型是action,退出while true
            if action_call is not None:
                return action_call

    def _run_step(self, state: DialogueState, step: FlowStep, flows: FlowsList) -> ActionCall | None:
        # 判断你当前的步骤 是个什么类型 step
        if isinstance(step, StartFlowStep):
            return self._run_start_step(step, state)
        if isinstance(step, EndFlowStep):
            return self._run_end_step(state)
        if isinstance(step, CollectFlowStep):
            return self._run_collect_step(step, state, flows)
        if isinstance(step, ActionFlowStep):
            return self._run_action_step(step, state)

    def _run_collect_step(self, step: CollectFlowStep, state: DialogueState, flows: FlowsList):

        # 1. 尝试自动补槽
        self._try_to_fill_collect_slot_focused_object(state, step)


    # 如果为 none
        # 2. 判断槽位是否已经填过
        if state.active_task.slots.get(step.slot_name):

            # 填过则直接执行下一步
            self._advance_next_step(state, step)
            return None
        else:
            # 没填过则启动系统过场：补槽任务
            state.start_active_system_task(CollectedSystemContext(
                # flow_id="system_collect_information",
                step_id=flows.get_flow_by_id('system_collect_information').start_step().id,
                slot_name=step.slot_name,
                response=step.response.model_dump(mode="json")
            ))
            return None


    def _try_to_fill_collect_slot_focused_object(self, state: DialogueState, step: CollectFlowStep):

        if state.focused_object is None:# 没有聚焦对象的情况
            return None

        if step.slot_name == 'order_number' and state.focused_object.type == "order":
            state.set_slots({step.slot_name: state.focused_object.id})

        if step.slot_name == "product_id" and state.focused_object.type == "product":
            state.set_slots({step.slot_name: state.focused_object.id})

    def _run_action_step(self, step: ActionFlowStep, state: DialogueState) -> ActionCall:
        # 1. 推进下一步
        self._advance_next_step(state, step)
        # 2. 构造 ActionCall
        action_call = self._build_action_call(state, step)
        # 3. 退出内层让外层执行
        return action_call


    def _build_action_call(self, state, step) -> ActionCall:
        # 1. 获取action_name (action_listen/action_response/action_xxx)
        # 2. 获取action_kwargs (构建参数)
        action_name = step.action
        action_kwargs = step.args
        # action_kwargs有可能有:结构有可能是一个str、dict、或者空字典{}
        # str: "context.response"
        if isinstance(action_kwargs, str):
            action_kwargs = state.active_system_task.model_dump(mode="json")[action_kwargs.split(".")[1]]
        return ActionCall(action_name=action_name, action_kwargs=action_kwargs)


    def _run_end_step(self, state: DialogueState) -> None:
        if state.active_system_task:
            # 清空state中系统任务流程上下文
            state.end_active_system_task()
        else:
            # 清空state中业务任务流程上下文
            state.end_active_task()
        return None

    def _run_start_step(self, step: StartFlowStep, state: DialogueState) -> None:
        # 1. 推进下一步
        self._advance_next_step(state, step)
        # 2. 返回None
        return None

    def _advance_next_step(self, state, step):
        # 1. 寻找下一个step id
        next_step_id = self._select_next_step(step, state)
        # 2. 更新当前任务上下文的step_id(给当前执行任务流程的上下文用)不做这个动作，出不来
        state.current_active_task().step_id = next_step_id

    def _select_next_step(self, step: FlowStep, state: DialogueState) -> str:

        for link in step.next:
            if isinstance(link, StaticLink):
                return link.target  # 下一个步骤的id（next: ask_order_number）
            if isinstance(link, ConditionalLink):
                # 条件链接真
                if self._eval_condition(state, link.condition):
                    return link.target  # if then  后面内容
            if isinstance(link, FallbackLink):
                return link.target  # else 后面内容
        return "没有下一步"

    """
    - id: start
      type: start
      next:
        - if: "slots.get('product_id')"   # 有商品 → 走 respond
          then: respond
        - else: missing_product_context    # 没商品 → 走 else
    """

    def _eval_condition(self, state: DialogueState, condition: str) -> bool:
        data = {
            "slots": state.active_task.slots,
            # current_active_task：获取当前任务上下文对象：系统任务优先
            # model_dump：对象转字典
            "context": state.current_active_task().model_dump(mode="json")
        }
        return bool(eval(condition, {'__builtins__': None}, data))  # 安全写法{'__builtins__': None}  （安全护栏）
        # eval:把 condition 字符串当代码跑,只能访问 data 里的 slots/context 两个名字
        # bool:再问"跑出来的结果真不真"(非 None/False/0/空 → True)
        # 例:condition="slots.get('product_id')", data["slots"]={"product_id":"P10086"}
        #     → 跑出 "P10086"(非空)→ bool → True

        """
        {'__builtins__': None} = “把这个 eval 的所有内置能力关掉,它只能访问我们主动放进 data 的 slots 和 context 两个玩具,其它柜子全锁死” 。

        __builtins__ 是什么
它是 Python 的"内置函数仓库"——print、len、open、__import__、eval 这些不用 import 就能用的能力,全在里面。正常情况下,Python 会自动把这个仓库塞进命名空间,所以 eval 里的代码默认能调用任何内置函数。而手动写成 None,就是把这个仓库整个锁死。

        比如condition = "__import__('os').system('del important.txt')"
        """


if __name__ == "__main__":
    import asyncio

    fx = FlowExecutor()


    class _FakeRunner:  # 本 case 用不到,占位
        async def run(self, action_call, state):
            return ActionResult()


    # 场景:用户刚进会话,还没任何任务 → run_task 返回空消息
    # 调用链路: run_task ─► advance_until_action ─► 无任务 → action_listen ─► break → return []
    state = DialogueState(sender_id="u1")  # 没有任何任务

    messages = asyncio.run(fx.run_task(state, FlowsList(), _FakeRunner()))

    print("返回的消息:", messages)
    assert messages == [], "预期返回空消息列表"
    print("✅ 通过:消息为空")
