# itzmy/plan/turn_validator.py

from typing import Dict

from domain.state import DialogueState
from knowledge.intents import KnowledgeIntent
from plan.models import TurnPlan, TurnPlanValidationResult, ClarifyReason
from task.command.models import SetSlotsCommand, StartFlowCommand, ResumeFlowCommand, CancelFlowCommand
from task.flow.flows import FlowsList


class TurnPlanValidator:# 校验器

    def _reject(self, reason: ClarifyReason) -> TurnPlanValidationResult:
        return TurnPlanValidationResult(
            valid=False,
            reason=reason
        )

    def _validate_task(
            self,
            turn_plan: TurnPlan,
            flows: FlowsList,
    ) -> TurnPlanValidationResult:

        task_plan = turn_plan.task

        """
        if  user_id:
            user_id = "vip":
                .....
            user_id = 'svip':
                .....
        """

        # 第一重:commands 不能为空
        if task_plan is None or not task_plan.commands:
            return self._reject(ClarifyReason.MISSING_TASK_COMMANDS)

        # 第二重:每个 command 都得是认识的类型
        allowed = (StartFlowCommand, ResumeFlowCommand, CancelFlowCommand, SetSlotsCommand)
        if not all(isinstance(cmd, allowed) for cmd in task_plan.commands):
            return self._reject(ClarifyReason.INVALID_TASK_COMMANDS)

        # 第三重:不能一次开多个流程 [开始流程，开始流程]  申请退款  查物流
        start_commands = [cmd for cmd in task_plan.commands if isinstance(cmd, StartFlowCommand)]
        if len(start_commands) > 1: # ClarifyReason.MULTIPLE_TASK_FLOWS 等价于 多任务流程
            return self._reject(ClarifyReason.MULTIPLE_TASK_FLOWS)

        # 第四重:要开的流程必须真实存在  tuikuan_flow
        if start_commands:
            flow = flows.get_flow_by_id(start_commands[0].flow) # 根据流程ID 找到那个流程
            if flow is None:# 如果找不到流程
                return self._reject(ClarifyReason.UNKNOWN_TASK_FLOW)

        # 校验成功
        return TurnPlanValidationResult(valid=True)
    # 入口
    def validate(
            self,
            state: DialogueState,
            turn_plan: TurnPlan,
            flow_list: FlowsList,
            intents: Dict[str, KnowledgeIntent]
    ) -> TurnPlanValidationResult:
        """
        校验 turn_plan
        :param turn_plan:
        :return:
        """
        # active_tracks LLM 返回的 轨道名称
        active_tracks = self._active_tracks(turn_plan)

        # 1. 是否没有命中轨道 null
        if not active_tracks:
            return self._reject(ClarifyReason.MISSING_TRACK)  # "missing_track" 缺失轨道

        # 2. 是否命中多条轨道
        if len(active_tracks) > 1:
            return self._reject(ClarifyReason.MULTIPLE_TRACKS)

        # 3. 获取唯一的轨道  active_tracks  task
        active_track = active_tracks[0]

        # 4. 判断轨道到底是哪一个
        if active_track == "task":
            # 4.1 业务任务轨道
            return self._validate_task(turn_plan, flow_list)  # task 校验

        if active_track == "knowledge":# 知识
            # 4.2 信息咨询任务轨道（后面2.7.2小节实现）
            return self._validate_knowledge(state, turn_plan, intents)

        # True：校验通过
        return TurnPlanValidationResult(valid=True)
    # demo   能够更细粒度  权限  校验

    def _validate_knowledge(
            self,
            state: DialogueState,
            turn_plan: TurnPlan,
            intents: Dict[str, KnowledgeIntent]
    ) -> TurnPlanValidationResult:

        # 第一重校验：意图不能缺
        knowledge_plan = turn_plan.knowledge
        if knowledge_plan is None or not knowledge_plan.intents: # 知识轨道（API 帮助手册 RAG） 意图
            return self._reject(ClarifyReason.MISSING_KNOWLEDGE_INTENT)# 校验失败

        focused_object = state.focused_object # 取出聚焦对象 订单
        for intent in knowledge_plan.intents:# ['refund_policy']
            # intent ---> 'refund_policy'
            # intents['refund_policy']
            intent_meta = intents[intent]
            # required_object ---> product
            required_object = intent_meta.requires_object

            # 你当前这个意图 是不是存在依赖
            if required_object is not None:  # 该意图需要某个对象才能回答（查订单、查商品、退款政策）

                if focused_object is None or focused_object.type != required_object:
                    return self._reject(ClarifyReason.MISSING_FOCUSED_OBJECT)

        return TurnPlanValidationResult(valid=True)


    @staticmethod
    def _active_tracks(turn_plan: TurnPlan) -> list[str]:
        active_tracks: list[str] = []
        if turn_plan.task is not None:
            active_tracks.append("task")  # 轨道的名字

        if turn_plan.knowledge is not None:
            active_tracks.append("knowledge")  # 轨道的名字

        if turn_plan.chitchat is not None:
            active_tracks.append("chitchat")  # 轨道的名字

        return active_tracks


if __name__ == '__main__':
    # ---- 仅测试用导入，不参与生产逻辑 ----
    from task.command.models import Command
    from task.flow.flows import Flow
    from domain.messages import FocusedObject
    from knowledge.intents import KNOWLEDGE_INTENTS
    from plan.models import TaskTurnPlan

    validator = TurnPlanValidator()

    # 状态1：无聚焦对象
    state = DialogueState(sender_id="user_001")
    # 状态2：已聚焦订单对象（用于 order_info 的正向用例）
    state_with_order = DialogueState(
        sender_id="user_001",
        focused_object=FocusedObject(id="ORDER_10001", type="order", title="订单10001"),
    )

    # 流程列表：必须包含 refund_request，否则合法的 start_flow 会被误判为 UNKNOWN_TASK_FLOW
    flow_list = FlowsList(flows=[
        Flow(id="refund_request", name="退款申请", description="处理用户退款申请"),
        Flow(id="onboarding", name="欢迎引导", description="开场欢迎"),
    ])
    intents = KNOWLEDGE_INTENTS

    def run_case(name: str, turn_plan: TurnPlan, st: DialogueState = state):
        result = validator.validate(st, turn_plan, flow_list, intents)
        print(f"[{name}] valid={result.valid}  reason={result.reason}")

    # 1. 三轨道全空 → MISSING_TRACK
    #run_case(" 1.无轨道          ", TurnPlan.from_dict({}))

    # 2. 同时命中 task + knowledge 两条轨道 → MULTIPLE_TRACKS
    # run_case(" 2.多轨道          ", TurnPlan.from_dict({
    #     "task": {"commands": [{"command": "start_flow", "flow": "refund_request"}]},
    #     "knowledge": {"intents": ["refund_policy"]},
    # }))
    #
    # 3. 仅 chitchat 轨道 → 直接放行
    # run_case(" 3.仅闲聊          ", TurnPlan.from_dict({"chitchat": {}}))

    # # 4. task 轨道但 commands 为空 → MISSING_TASK_COMMANDS
    #run_case(" 4.commands为空     ", TurnPlan.from_dict({"task": {"commands": []}}))

    # # 5. task 里出现不认识的 command 类型 → INVALID_TASK_COMMANDS
    # run_case(" 5.未知命令类型     ",
    #          TurnPlan(task=TaskTurnPlan(commands=[Command(command="weird_cmd")])))
    #
    # # 6. 一次开了两个流程 → MULTIPLE_TASK_FLOWS
    # run_case(" 6.同时开多个流程   ", TurnPlan(task=TaskTurnPlan(commands=[
    #     StartFlowCommand(command="start_flow", flow="refund_request"),
    #     StartFlowCommand(command="start_flow", flow="onboarding"),
    # ])))
    #
    # # 7. start_flow 指向不存在的流程 → UNKNOWN_TASK_FLOW
    # run_case(" 7.流程不存在       ", TurnPlan.from_dict({
    #     "task": {"commands": [{"command": "start_flow", "flow": "not_exist_flow"}]},
    # }))
    #
    # # 8. start_flow 指向真实存在的流程 → 校验通过
    # run_case(" 8.合法开流程       ", TurnPlan.from_dict({
    #     "task": {"commands": [{"command": "start_flow", "flow": "refund_request"}]},
    # }))
    #
    # # 9. task 只有 set_slots → 校验通过
    # run_case(" 9.仅设置槽位       ", TurnPlan.from_dict({
    #     "task": {"commands": [{"command": "set_slots", "slots": {"order_number": "ORDER_10001"}}]},
    # }))
    #
    # # 10. knowledge 轨道但 intents 为空 → MISSING_KNOWLEDGE_INTENT
    # run_case("10.intents为空      ", TurnPlan.from_dict({"knowledge": {"intents": []}}))
    #
    # # 11. order_info 要求聚焦订单，但 state 没有聚焦对象 → MISSING_FOCUSED_OBJECT
    # run_case("11.缺聚焦对象       ", TurnPlan.from_dict({
    #     "knowledge": {"intents": ["order_info"]},
    # }))
    #
    # 12a. order_info + 已聚焦订单对象 → 校验通过
    run_case("12a.有聚焦对象      ", TurnPlan.from_dict({
        "knowledge": {"intents": ["order_info"]},
    }), st=state_with_order)
    #
    # # 12b. refund_policy 本身不要求聚焦对象 → 校验通过
    # run_case("12b.无需聚焦对象    ", TurnPlan.from_dict({
    #     "knowledge": {"intents": ["refund_policy"]},
    # }))
