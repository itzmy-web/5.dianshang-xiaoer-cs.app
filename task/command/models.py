# itzmy/task/command/models.py

from typing import Any

from pydantic import BaseModel

# 用父类方法 通过参数 去调用对应的字类对象
class Command(BaseModel):
    command: str  # LLM 指令

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Command":
        clz = COMMAND_NAME_TO_CLASS[data["command"]]
        return clz(**data)

    """简单工厂方法： 有一个工厂类或者方法，靠参数选择具体产品。创建逻辑集中在单一位置。比如：from_dict 就是唯一的工厂；也符合开闭原则（OCP）：新增命令时，只需要新增子类和修改映射字典，不需要改动 from_dict 方法内部的逻辑。"""

class StartFlowCommand(Command):
    flow: str
class SetSlotsCommand(Command):
    slots: dict[str, Any]
class CancelFlowCommand(Command):
    pass
class ResumeFlowCommand(Command):
    flow: str | None = None


COMMAND_NAME_TO_CLASS = {
    "start_flow": StartFlowCommand,
    "set_slots": SetSlotsCommand,
    "cancel_flow": CancelFlowCommand,
    "resume_flow": ResumeFlowCommand,
}

if __name__ == '__main__':
    command = {"command": "set_slots", "slots": {"order_number": "10001"}}
    print(Command.from_dict(command))
