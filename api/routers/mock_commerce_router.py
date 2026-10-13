# itzmy/api/routers/mock_commerce_router.py
"""
内置商城演示数据（Mock 商城 API）
让「查订单 / 查物流 / 查商品」在无独立商城服务的环境下真实出数据。
路径与 knowledge/providers.py、task/action 的调用约定一致：
    GET /products/{product_id}
    GET /orders/{order_number}
    GET /orders/{order_number}/logistics
"""

import re

from fastapi import APIRouter, HTTPException

router = APIRouter()

PRODUCTS = {
    "SKU001": {
        "product_id": "SKU001", "title": "纯棉T恤（白色 L 码）",
        "price": 79.0, "stock": 326, "status": "在售",
        "tags": ["纯棉", "宽松版型", "七天无理由退货"],
    },
    "SKU002": {
        "product_id": "SKU002", "title": "iPhone 15 Pro 256G 原色钛金属",
        "price": 8999.0, "stock": 57, "status": "在售",
        "tags": ["手机", "苹果", "国行正品", "全国联保", "顺丰包邮"],
    },
    "SKU003": {
        "product_id": "SKU003", "title": "运动水杯 1L",
        "price": 45.0, "stock": 0, "status": "缺货中，预计 3 天后补货",
        "tags": ["食品级材质", "便携提绳"],
    },
}

ORDERS = {
    "DD2024001": {
        "order_number": "DD2024001", "status": "已发货",
        "amount": 8999.0, "product": "iPhone 15 Pro 256G 原色钛金属",
        "created_at": "2026-10-08 10:23", "user_id": "u1001",
    },
    "DD2024002": {
        "order_number": "DD2024002", "status": "待发货",
        "amount": 124.0, "product": "纯棉T恤 ×1 + 运动水杯 ×1",
        "created_at": "2026-10-09 21:47", "user_id": "u1001",
    },
    "DD2024003": {
        "order_number": "DD2024003", "status": "已签收",
        "amount": 79.0, "product": "纯棉T恤（白色 L 码）",
        "created_at": "2026-10-01 09:12", "user_id": "u1001",
    },
}

LOGISTICS = {
    "DD2024001": {
        "logistics_company": "顺丰速运", "tracking_number": "SF1234567890",
        "logistics_status": "运输中 · 已到达杭州转运中心",
        "status": "运输中 · 已到达杭州转运中心",
        "traces": [
            {"time": "10-09 18:32", "desc": "包裹已从深圳发出"},
            {"time": "10-10 06:15", "desc": "到达杭州转运中心"},
            {"time": "10-10 09:40", "desc": "杭州转运中心发出，准备派送"},
        ],
    },
    "DD2024002": {
        "logistics_company": "暂未分配", "tracking_number": "-",
        "logistics_status": "商家备货中，预计 24 小时内发出",
        "status": "商家备货中，预计 24 小时内发出",
        "traces": [],
    },
    "DD2024003": {
        "logistics_company": "中通快递", "tracking_number": "ZT7586412390",
        "logistics_status": "已签收 · 感谢你在商城购物",
        "status": "已签收 · 感谢你在商城购物",
        "traces": [
            {"time": "10-02 08:00", "desc": "包裹已到达附近网点"},
            {"time": "10-02 14:26", "desc": "派送中，快递员：张师傅"},
            {"time": "10-02 16:05", "desc": "已签收"},
        ],
    },
}


# 注意：固定路径 /products/search 必须声明在 /products/{product_id} 之前，
# 否则 "search" 会被当成 product_id 抢走匹配
@router.get("/products/search")
async def search_products(q: str = ""):
    """商品关键词搜索（导购）：按标题 + 标签匹配，返回前 4 件"""
    q = (q or "").strip().lower()
    if not q:
        return {"code": 0, "data": []}
    results = []
    for p in PRODUCTS.values():
        hay = (p["title"] + " " + " ".join(p["tags"])).lower()
        if any(kw in hay for kw in re.split(r"[|,，\s]+", q) if kw):
            results.append(p)
    return {"code": 0, "data": results[:4]}


@router.get("/products/{product_id}")
async def get_product(product_id: str):
    p = PRODUCTS.get(product_id.strip().upper())
    if not p:
        raise HTTPException(status_code=404, detail=f"商品 {product_id} 不存在")
    return {"code": 0, "data": p}


@router.get("/orders/{order_number}")
async def get_order(order_number: str):
    o = ORDERS.get(order_number.strip().upper())
    if not o:
        raise HTTPException(status_code=404, detail=f"订单 {order_number} 不存在")
    return {"code": 0, "data": o}


@router.get("/orders/{order_number}/logistics")
async def get_logistics(order_number: str):
    l = LOGISTICS.get(order_number.strip().upper())
    if not l:
        raise HTTPException(status_code=404, detail=f"订单 {order_number} 暂无物流信息")
    return {"code": 0, "data": l}
