from enum import Enum
from pydantic import BaseModel


class FocusedObject(BaseModel):
    """
    聚焦对象
    """
    id: str  # 对象的唯一标识（如order_id、product_id）
    type: str  # 对象类型（如 "order", "product"）
    title: str | None = None  # 对象的标题（如 “纯棉T恤”）
    attributes: dict = {}  # 其他额外信息


class MessageType(Enum):
    TEXT = "text"  # 文本类型
    OBJECT = "object"  # 对象类型


class UserMessage(BaseModel):
    """用户的消息模型"""
    sender_id: str  # 用户ID(必填字段)
    message_id: str  # 消息ID(必填字段)
    type: MessageType  # 消息类型（text 或 object）必填字段
    text: str | None = None  # 文本消息(用户说的话)
    object: FocusedObject | None = None  # 对象类型的消息(用户点击的对象)
    # 会话记忆：昵称提示（DialogueService 从用户画像注入，HistoryBuilder 渲染进提示词）
    profile_hint: str = ""


class BotMessage(BaseModel):
    text: str | None = None  # 机器人回复的话
    object: FocusedObject | None = None  # 机器人返回的对象



class ProcessResult(BaseModel):
    sender_id: str  # 用户ID
    message_id: str  # 消息ID(内部生成)
    messages: list[BotMessage]  # 回复消息（机器人回复的所有消息都给前端）



if __name__ == '__main__':
    fo = FocusedObject(id="1", type="2")  #

    # 把 Python 对象变成字典
    data = fo.model_dump(mode='json')
    # 把字典还原成 Python 对象
    obj = FocusedObject.model_validate(data)

    print(type(fo))  # FocusedObject对象
    print(type(data))  # dict字典
    print(type(obj))  # FocusedObject对象
