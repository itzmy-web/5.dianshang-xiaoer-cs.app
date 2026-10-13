# itzmy/task/action/custom/lookup_order_status.py
from typing import Any

from domain.state import DialogueState
from task.action.base import Action, ActionResult
from task.action.custom.shared import fetch_order, _build_order_summary


class LookupOrderStatusAction(Action):
    name = "action_lookup_order_status"
    # 拿状态里面的 订单号 查（请求后端） 订单状态
    async def run(self, state: DialogueState, action_kwargs: dict[str, Any]) -> ActionResult:
        order_number = state.active_task.slots.get("order_number") # 从状态中把订单号提取出来A1001

        # 调后端节后
        payload = await fetch_order(order_number) # 请求后端以后数据
        # payload 查完以后

        if payload is None:
            return ActionResult(slot_updates={
                "order_status": "查询失败",
                "order_summary": "暂时无法查到该订单信息，请稍后再试。",
            })

        return ActionResult(slot_updates={
            "order_status": payload.get("status_desc") or payload.get("status") or "未知",
            "order_summary": _build_order_summary(payload),
        })
