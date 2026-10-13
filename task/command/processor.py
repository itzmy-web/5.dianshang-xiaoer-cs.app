# itzmy/task/command/processor.py
from domain.contexts import TaskContext, InterruptedSystemContext, StartedSystemContext, ResumedSystemContext, \
    CanceledSystemContext
from domain.state import DialogueState
from task.command.models import Command, StartFlowCommand, SetSlotsCommand, CancelFlowCommand, ResumeFlowCommand
from task.flow.flows import FlowsList


class CommandProcessor:

    def run(
            self,
            commands: list[Command],
            state: DialogueState,
            flows: FlowsList,
    ) -> None:
        """
        把命令应用到 state
        :param commands:
        :param state:
        :param flows:
        :return:
        """
        for command in commands:
            self._apply(command, state, flows)

    def _apply(
            self,
            command: Command,
            state: DialogueState,
            flows: FlowsList,
    ) -> None:
        """
        处理命令
        :param command:
        :param state:
        :param flows:
        :return:
        """
        if isinstance(command, StartFlowCommand):  # 开始流程
            self._handle_start_flow(command, state, flows)
        elif isinstance(command, SetSlotsCommand):  # 收集槽
            self._handle_set_slots(command, state)
        elif isinstance(command, CancelFlowCommand):  # 取消流程
            self._handle_cancel_flow(state, flows)
        elif isinstance(command, ResumeFlowCommand):  # 恢复流程
            self._handle_resume_flow(command, state, flows)

    def _handle_resume_flow(self, command: ResumeFlowCommand, state: DialogueState, flows: FlowsList):
        # ===== 第一步:确定要恢复哪个流程 =====
        if command.flow is not None:
            # 指名恢复:用户明确说了恢复哪个  refun_request 字符串 命令
            target_flow = flows.get_flow_by_id(command.flow)
            if target_flow is None:
                raise ValueError(f"未知流程 '{command.flow}'.")
            target_flow_id = target_flow.id
            target_flow_name = target_flow.name
        else:
            # 不指名恢复:用户只说"继续刚才的" → 取暂停栈栈顶(最近挂起的)
            if not state.paused_tasks:# 如果没有后台任务
                return
            top_paused = state.paused_tasks[-1]
            target_flow_id = top_paused.flow_id
            target_flow_name = self._readable_flow_name(target_flow_id, flows)

        # ===== 第二步:按"当前有没有活跃任务"恢复 =====
        active_task = state.active_task
        if active_task is not None:  # 你现在是要 退款  正在进行的是 查物流  后台挂起 查订单
            if active_task.flow_id == target_flow_id:  # 你现在准备要执行的任务target_flow_id 和我
                return  # 已经在办它,不重复
            interrupted_flow_id = active_task.flow_id  # interrupted_flow_id= 查物流
            interrupted_flow_name = self._readable_flow_name(active_task.flow_id, flows)
            state.interrupted_active_task()
            # 当前活跃的任务 None 后台  查订单  查物流  target_flow_id 要退款  False
            if not state.resumed_active_task(target_flow_id):  # 判断 申请 不在后台当中
                # 恢复成 查物流
                state.resumed_active_task()  # 恢复失败,回退
                print(state.active_task)
                return  #
            self._activate_interrupted_system_flow(  # ③打断当前+恢复目标
                state, flows, interrupted_flow_id, interrupted_flow_name,
                target_flow_id, target_flow_name)
        else:
            if not state.resumed_active_task(command.flow):  # ④没任务,直接恢复
                return
            resumed = state.active_task
            self._activate_resumed_system_flow(
                state, flows, resumed.flow_id, self._readable_flow_name(resumed.flow_id, flows))

    def _handle_cancel_flow(self, state: DialogueState, flows: FlowsList):
        # 获取当前正在执行的 flow
        active_task = state.active_task
        target_flow = flows.get_flow_by_id(active_task.flow_id)
        # 取消当前 task
        state.cancel_active_task()
        # 启动 system_task_canceled 过场
        state.start_active_system_task(
            CanceledSystemContext(
                flow_id="system_task_canceled",
                step_id=flows.get_flow_by_id("system_task_canceled").start_step().id,
                canceled_flow_id=target_flow.id,
                canceled_flow_name=target_flow.name,
            )
        )

    def _handle_set_slots(self, command: SetSlotsCommand, state: DialogueState):
        if state.active_task:  # 当前有没有活跃任务 在某个流程中
            state.set_slots(command.slots)  # 命令：set_slots  填订单

    def _handle_start_flow(self, command: StartFlowCommand, state: DialogueState, flows: FlowsList) -> None:
        """
        开启业务任务
        :param command:
        :param state:
        :param flows:
        :return:
        """

        # 清除当前系统流程
        state.end_active_system_task()

        # 业务流程
        # 防御:不允许直接启动 system_ 开头的内部流程
        if command.flow.startswith("system_"):  # 无权执行 系统工作流
            raise ValueError(f"不能直接启动系统流程：'{command.flow}'")

        # 校验:流程必须存在
        # flows.get_flow_by_id 通过你的流程名称 None
        target_flow = flows.get_flow_by_id(command.flow)
        if target_flow is None:
            raise ValueError(f"未知流程：'{command.flow}'.")

        # 校验:流程必须有起点
        start_step = target_flow.start_step()  # 找你开始节点

        if start_step is None:
            raise ValueError(f"流程 '{command.flow}' 没有开始步骤")

        # order_status_query 从状态取 看有没有正在活跃的任务   state.active_task=NONE
        # order_status_query 正在进行 查订单
        active_task = state.active_task

        # ===== 情况一:当前有活跃任务 =====
        if active_task is not None:

            # 同一个流程：不重复启动
            if active_task.flow_id == command.flow:
                # 执行同一个任务 订单查询
                return

            # 不是同一个流程：把当前任务放进暂停栈
            interrupted_flow_id = active_task.flow_id  # 拿出当前正在进行的任务ID
            interrupted_flow_name = self._readable_flow_name(active_task.flow_id, flows)  # 拿名字
            state.interrupted_active_task()  # 放到后台

            # 试着从暂停栈恢复要开的流程
            resumed = state.resumed_active_task(command.flow)  # 后台有没有曾经 被挂起的 查物流工作流
            if not resumed:
                # 要开的流程不在暂停栈 → 新建
                state.start_active_task(TaskContext(flow_id=command.flow, step_id=start_step.id))
                started_flow_id = command.flow  # 任务ID
                started_flow_name = self._readable_flow_name(command.flow, flows)  # 任务名字
            else:
                # 要开的流程在暂停栈 → 已被 resumed_active_task 恢复
                started_flow_id = command.flow  # 恢复的任务ID
                started_flow_name = self._readable_flow_name(command.flow, flows)  # 恢复的任务名称

            # 激活"打断"过场
            self._activate_interrupted_system_flow(
                state, flows, interrupted_flow_id, interrupted_flow_name,
                started_flow_id, started_flow_name)

            return

        # ===== 情况二:当前没有活跃任务 =====
        # 试着恢复同名任务
        resumed = state.resumed_active_task(command.flow)
        if resumed:
            # 要开的流程在暂停栈 → 恢复
            self._activate_resumed_system_flow(state, flows, command.flow,
                                               self._readable_flow_name(command.flow, flows))
            return

        # 要开的流程从没做过 → 新建
        state.start_active_task(TaskContext(flow_id=command.flow, step_id=start_step.id))
        self._activate_started_system_flow(
            state, flows, command.flow, self._readable_flow_name(command.flow, flows),
        )

    @staticmethod
    def _readable_flow_name(flow_id: str, flows: FlowsList) -> str:
        # 根据任务ID 取出任务名称  order_status_query 订单查询
        # l.....    物流查询
        flow = flows.get_flow_by_id(flow_id)
        return flow.name if flow else flow_id

    @staticmethod
    def _activate_started_system_flow(state: DialogueState, flows: FlowsList, started_flow_id: str,
                                      started_flow_name: str):  # 激活系统过场
        flow = flows.get_flow_by_id("system_task_started")
        state.start_active_system_task(StartedSystemContext(
            flow_id="system_task_started",
            step_id=flow.start_step().id,
            started_flow_id=started_flow_id,
            started_flow_name=started_flow_name,
        ))

    @staticmethod
    def _activate_interrupted_system_flow(
            state: DialogueState, flows: FlowsList, interrupted_flow_id: str, interrupted_flow_name: str,
            started_flow_id: str, started_flow_name: str):
        # 插播系统过场
        flow = flows.get_flow_by_id("system_task_interrupted")
        state.start_active_system_task(InterruptedSystemContext(
            flow_id=flow.id,
            step_id=flow.start_step().id,
            interrupted_flow_id=interrupted_flow_id,
            interrupted_flow_name=interrupted_flow_name,
            started_flow_id=started_flow_id,
            started_flow_name=started_flow_name
        ))

    @staticmethod
    def _activate_resumed_system_flow(
            state: DialogueState, flows: FlowsList,
            resumed_flow_id: str, resumed_flow_name: str):

        flow = flows.get_flow_by_id("system_task_resumed")
        state.start_active_system_task(ResumedSystemContext(
            flow_id=flow.id,
            step_id=flow.start_step().id,
            resumed_flow_id=resumed_flow_id,
            resumed_flow_name=resumed_flow_name
        ))


if __name__ == '__main__':
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

    from task.flow.loader import FlowLoader
    from domain.state import DialogueState
    from domain.contexts import TaskContext
    from task.command.models import ResumeFlowCommand

    base = Path(__file__).resolve().parents[2]
    flows = FlowLoader().load_many([
        base / "flow_config" / "user_flows.yml",
        base / "flow_config" / "system_flows.yml",
    ])
    processor = CommandProcessor()

    # ================= 通用小工具 =================
    results = []


    def check(name, cond):
        results.append(cond)
        print(("  ✅ " if cond else "  ❌ ") + name)


    def new_state(active=None, paused=()):
        """手工摆好前置状态: new_state(active='物流', paused=['订单'])"""
        s = DialogueState(sender_id="u_test")
        if active:
            s.active_task = TaskContext(flow_id=active)
        s.paused_tasks = [TaskContext(flow_id=f) for f in paused]
        return s


    def resume(s, flow=None):
        """模拟用户说'继续刚才的(退款)', 并打印状态"""
        print(f"\n▶ resume(flow={flow})")
        processor.run([ResumeFlowCommand(command="resume_flow", flow=flow)], s, flows)
        task, sysf = s.active_task, s.active_system_task
        print(f"    active={task.flow_id if task else None}"
              f"  paused={[t.flow_id for t in s.paused_tasks]}"
              f"  过场={sysf.flow_id if sysf else None}")


    # ================= 第7章: 挂起恢复 4 种情况 =================

    def test_7_1_same_as_active():
        """[①] 要恢复的就是当前正办的 → 不重复, 无过场
        场景: 正查物流, 说"继续物流" —— 什么都不该变"""
        # 之前的操作 已经操过了 我也存了状态
        s = new_state(active="logistics_tracking", paused=["order_status_query"])

        resume(s, "logistics_tracking")
        check("[7-①] active 仍是物流", s.active_task.flow_id == "logistics_tracking")
        check("[7-①] 暂停栈不变", [t.flow_id for t in s.paused_tasks] == ["order_status_query"])
        check("[7-①] 无过场", s.active_system_task is None)


    def test_7_2_not_in_paused():
        """[②] 要恢复的不在暂停栈 → 回退, 静默无过场
        场景: 正查物流, 说"继续退款"(退款从没挂起过) —— 像没发生一样"""
        s = new_state(active="logistics_tracking", paused=["order_status_query"])
        resume(s, "refund_request")
        check("[7-②] 物流回退为 active", s.active_task.flow_id == "logistics_tracking")
        check("[7-②] 暂停栈只剩订单", [t.flow_id for t in s.paused_tasks] == ["order_status_query"])
        check("[7-②] 无过场", s.active_system_task is None)


    def test_7_3_interrupt_then_resume():
        """[③] 办 A 时回到挂起的 B → 打断 A + 恢复 B + Interrupted 过场
        场景: 正查物流, 说"继续刚才的退款" """
        s = new_state(active="logistics_tracking", paused=["refund_request"])
        resume(s, "refund_request")
        check("[7-③] active=退款", s.active_task.flow_id == "refund_request")
        check("[7-③] 物流反进暂停栈", [t.flow_id for t in s.paused_tasks] == ["logistics_tracking"])
        check("[7-③] Interrupted 过场", s.active_system_task.flow_id == "system_task_interrupted")


    def test_7_4_no_active():
        """[④] 没事做 → 直接恢复, 不指名取栈顶 + Resumed 过场
        场景: 订单、物流先后挂起, 说"继续刚才的" → 恢复最近的物流"""
        s = new_state(paused=["order_status_query", "logistics_tracking"])
        resume(s, None)  # flow=None: 用户只说"继续刚才的"
        check("[7-④] 恢复栈顶=物流", s.active_task.flow_id == "logistics_tracking")
        check("[7-④] 暂停栈剩订单", [t.flow_id for t in s.paused_tasks] == ["order_status_query"])
        check("[7-④] Resumed 过场", s.active_system_task.flow_id == "system_task_resumed")


        # ============ 测试调度: 测哪个用例, 注释掉其他行 ============
        # test_7_1_same_as_active()
        # test_7_2_not_in_paused()
        # test_7_3_interrupt_then_resume()


    test_7_4_no_active()

    print(f"\n结果: {sum(results)}/{len(results)} 通过")
