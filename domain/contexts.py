from typing import Literal, Annotated

from pydantic import BaseModel, Field, TypeAdapter


# 任务上下文模型  用来描述任务
class TaskContext(BaseModel):
    """
    业务任务上下文   任务
    """
    flow_id: str  # 业务任务的流程ID
    step_id: str | None = None  # 业务任务下的步骤ID
    slots: dict = {}  # 业务任务执行过程中收集到的槽位数据


#  系统上下文模型 用来 描述系统通知
class SystemContext(BaseModel):
    """
    系统流程上下文
    定义具体流程的通用属性
    """
    flow_id: str  # 系统流程的流程ID
    step_id: str | None = None  # 系统流程当前执行的步骤ID


class StartedSystemContext(SystemContext):
    """
    流程开始
    """
    started_flow_id: str = ""  # 新开始的业务任务ID
    started_flow_name: str = ""  # 新开始的业务任务名字
    flow_id: Literal["system_task_started"] = "system_task_started"


class InterruptedSystemContext(SystemContext):
    """
    流程中断
    """
    interrupted_flow_id: str = ""  # 被中断的旧业务任务ID   refund_request
    interrupted_flow_name: str = ""  # 被中断的旧业务任务名字 退款申请
    started_flow_id: str = ""  # 新开始的业务任务ID
    started_flow_name: str = ""  # 新开始的业务任务名字
    flow_id: Literal["system_task_interrupted"] = "system_task_interrupted"


# 当任务 被取消的时候 用它
class CanceledSystemContext(SystemContext):
    """
    流程取消
    """
    canceled_flow_id: str = ""  # 被取消的业务任务ID
    canceled_flow_name: str = ""  # 被取消的业务任务名字
    flow_id: Literal["system_task_canceled"] = "system_task_canceled"


class ResumedSystemContext(SystemContext):
    """
    流程恢复
    """
    resumed_flow_id: str = ""  # 被恢复的业务任务ID
    resumed_flow_name: str = ""  # 被恢复的业务任务名字
    flow_id: Literal["system_task_resumed"] = "system_task_resumed"


class CollectedSystemContext(SystemContext):
    """
    系统流程收集槽位信息
    """
    slot_name: str = ""  # 收集的槽位名
    response: dict = {}  # 例如：{"text":"请告诉我你的订单号"}
    flow_id: Literal["system_collect_information"] = "system_collect_information"


# 定义系统流程的联合类型 捆在一起
SystemContextUnion = Annotated[
    StartedSystemContext |
    InterruptedSystemContext |
    CanceledSystemContext |
    ResumedSystemContext |
    CollectedSystemContext,
    Field(discriminator="flow_id")
]
system_context_adapter = TypeAdapter(SystemContextUnion)



if __name__ == '__main__':
    # 定义StartedSystemContext的字典数据
    data = {
        "flow_id": "system_task_started",
        "step_id": "start",
        "started_flow_id": "order_status_query",
        "started_flow_name": "订单状态查询"
    }



    # 使用适配器的 validate_python()：替代 model_validate()
    obj = system_context_adapter.validate_python(data)

    print(type(obj))
    print(obj)
