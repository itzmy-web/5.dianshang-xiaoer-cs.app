# itzmy/knowledge/providers.py

import json, re, asyncio
from abc import ABC, abstractmethod
from typing import Any
from pydantic import BaseModel
from conf.config import settings
from domain.state import DialogueState
from infrastructure import http_client

# 供应商  就是 具体 如何进行 知识检索（搜索）供应知识

class KnowledgeChunk(BaseModel):
    content: str


class KnowledgeProvider(ABC):
    # 知识提者的ID
    provider_id = ""

    @abstractmethod
    async def retrieve(self, state: DialogueState) -> list[KnowledgeChunk]:
        """
        提供检索方法
        :param state:
        :return:
        """
        pass

# 商品API
class ProductAPIProvider(KnowledgeProvider):
    provider_id = 'api.product'

    async def retrieve(self, state: DialogueState) -> list[KnowledgeChunk]:
        product_id = state.focused_object.id
        data: dict[str, Any] = await self._get_product_info_by_id(product_id)
        text = json.dumps(data, ensure_ascii=False, indent=2)
        return [KnowledgeChunk(content=f"商品信息:\n{text}")]

    async def _get_product_info_by_id(self, product_id: str) -> dict[str, Any]:
        url = f"{settings.commerce_api_base_url}/products/{product_id}"
        # http://127.0.0.1:18081/products/123456
        # 注意此处：
        # 文件头部 from itzmy.infrastructure import http_client
        # 此处使用 http_client.http_client.get(url) 调用

        # 不要这样做：
        # 文件头部 from itzmy.infrastructure.http_client import http_client
        # 此处使用 http_client.get(url) 调用
        # 会使拿到的 http_client 是 None
        response = await http_client.http_client.get(url)
        return response.json()["data"]


# 订单API
class OrderAPIProvider(KnowledgeProvider):
    provider_id = 'api.order'# 订单API 供应商的ID

    async def retrieve(self, state: DialogueState) -> list[KnowledgeChunk]:
        order_number = state.focused_object.id # 订单号

        order_payload, logistics_payload = await asyncio.gather(
            self._fetch_order(order_number),# 查订单信息
            self._fetch_logistics(order_number),# 查物流信息
        )

        return [
            KnowledgeChunk(
                content="订单与物流信息：\n"
                        + json.dumps(
                    {
                        "order_number": order_number,
                        "order": order_payload,
                        "logistics": logistics_payload,
                    },
                    ensure_ascii=False,# 不使用_ascii编码
                    indent=2,# 缩进2个空格
                )
            )
        ]

    async def _fetch_order(self, order_number) -> dict[str, Any]:
        url = f"{settings.commerce_api_base_url}/orders/{order_number}"
        # http://127.0.0.1:18081/orders/123456
        response = await http_client.http_client.get(url)
        return response.json()["data"]

    async def _fetch_logistics(self, order_number) -> dict[str, Any]:
        url = f"{settings.commerce_api_base_url}/orders/{order_number}/logistics"
        # http://127.0.0.1:18081/orders/123456/logistics
        response = await http_client.http_client.get(url)
        return response.json().get("data", {})

# 常见问题API
class FAQProvider(KnowledgeProvider):
    provider_id = 'faq.default'

    # 内置 FAQ 种子数据（首次启动播种进数据库；之后以数据库为准，后台可增删改）
    FAQ_DEFAULT = [
        {"title": "发货时效", "keywords": ["发货", "几天", "多久", "什么时候发"],
         "answer": "普通订单在付款后 24 小时内发出（预售商品以商品页为准），大促期间可能延长至 48 小时。发货后可在订单详情里查看物流单号。"},
        {"title": "运费政策", "keywords": ["运费", "包邮", "邮费"],
         "answer": "单笔订单满 99 元包邮；不满 99 元收取 8 元运费。偏远地区（新疆/西藏等）需补 10 元运费差价。"},
        {"title": "退换货政策", "keywords": ["退货", "退款政策", "七天无理由", "退换货"],
         "answer": "签收后 7 天内支持无理由退货（需商品完好、吊牌齐全）；质量问题 15 天内可退，来回运费由商家承担。进入「我要退款」流程输入订单号即可办理。"},
        {"title": "发票开具", "keywords": ["发票", "开票", "电子发票"],
         "answer": "支持开具电子普通发票，签收后可在订单详情-申请开票中自助开具，1 个工作日内发送到你的邮箱。增值税专用发票请联系人工客服。"},
        {"title": "会员与积分", "keywords": ["会员", "积分", "等级"],
         "answer": "消费 1 元累计 1 积分；积分可在积分商城兑换优惠券和礼品。会员等级：普通会员 → 黄金会员（年消费≥2000）→ 钻石会员（年消费≥10000），等级越高折扣越大。"},
        {"title": "优惠券活动", "keywords": ["优惠券", "优惠", "折扣", "活动"],
         "answer": "新用户自动发放 3 张无门槛券；每周五「会员日」全场 95 折起，可叠加满减券。领券中心每周一更新。"},
        {"title": "修改收货地址", "keywords": ["地址", "修改地址", "改地址"],
         "answer": "订单「待发货」状态下可在订单详情中自助修改收货地址；已发货订单无法修改，可联系快递员改派。"},
        {"title": "取消订单", "keywords": ["取消", "退单"],
         "answer": "「待发货」订单可随时在订单详情中取消并原路退款；「已发货」订单需走退货流程。"},
    ]

    async def _load_faq_items(self) -> list[dict]:
        """优先从数据库读（后台可编辑），失败时回退内置种子"""
        try:
            from sqlalchemy import select
            from infrastructure import database
            from models.faq import FaqRecord
            async with database.async_session() as session:
                rows = (await session.execute(
                    select(FaqRecord).where(FaqRecord.enabled == True)  # noqa: E712
                )).scalars().all()
            return [{"id": r.id, "title": r.title,
                     "keywords": [k.strip() for k in r.keywords.split(",") if k.strip()],
                     "answer": r.answer} for r in rows]
        except Exception:
            return [{"id": i, **item} for i, item in enumerate(self.FAQ_DEFAULT)]

    # ---- 语义检索（embedding 余弦相似度兜底，用户换个说法也能命中） ----
    _SEM_CACHE: dict = {}   # {faq_ids_sig: (items, vectors)}；FAQ 增删后签名变化自动重建
    SEM_THRESHOLD = 0.50    # bge-m3 相似度命中阈值（经验值）

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        from infrastructure import http_client
        url = settings.llm_base_url.rstrip("/") + "/embeddings"
        headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
        resp = await http_client.http_client.post(
            url, json={"model": settings.embedding_model, "input": texts},
            headers=headers, timeout=30.0)
        resp.raise_for_status()
        data = sorted(resp.json()["data"], key=lambda d: d["index"])
        return [d["embedding"] for d in data]

    @staticmethod
    def _cos(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(y * y for y in b) ** 0.5
        return dot / (na * nb) if na and nb else 0.0

    async def _semantic_hit(self, text: str, items: list[dict]) -> tuple[dict | None, float]:
        """返回 (命中的FAQ, 相似度)；embedding 缓存按 FAQ id 签名失效"""
        if not items:
            return None, 0.0
        sig = ",".join(str(it.get("id")) for it in items)
        cache = FAQProvider._SEM_CACHE
        if cache.get("sig") != sig:
            texts = [f"{it['title']}：{it['answer']}" for it in items]
            vecs = await self._embed(texts)
            cache.clear()
            cache["sig"] = sig
            cache["items"] = items
            cache["vecs"] = vecs
        qvec = (await self._embed([text]))[0]
        best, best_sim = None, 0.0
        for it, vec in zip(cache["items"], cache["vecs"]):
            sim = self._cos(qvec, vec)
            if sim > best_sim:
                best, best_sim = it, sim
        if best_sim >= self.SEM_THRESHOLD:
            return best, best_sim
        return None, best_sim

    async def retrieve(self, state: DialogueState) -> list[KnowledgeChunk]:
        # 从用户最近消息里做关键词匹配（把 pending_turn 的文本拼起来）
        text = ""
        pt = state.pending_turn
        if pt is not None and pt.user_message is not None and pt.user_message.text:
            text = pt.user_message.text
        if not text:
            return [KnowledgeChunk(content="FAQ：未检索到相关问题")]

        items = await self._load_faq_items()
        scored = []
        for item in items:
            score = sum(1 for kw in item["keywords"] if kw in text)
            if score > 0:
                scored.append((score, item))
        if scored:
            scored.sort(key=lambda x: -x[0])
            best = scored[0][1]
            # 带上标题，供回复器做「来源标注」
            return [KnowledgeChunk(content=f"FAQ 命中《{best['title']}》：\n{best['answer']}")]

        # 关键词没命中 → 语义相似度兜底
        try:
            best, sim = await self._semantic_hit(text, items)
        except Exception:
            best, sim = None, 0.0
        if best:
            return [KnowledgeChunk(
                content=f"FAQ 命中《{best['title']}》：\n{best['answer']}\n（语义相似度 {sim:.2f}）")]
        return [KnowledgeChunk(content="FAQ：未检索到相关问题，请提示用户换个说法或转人工")]


# 商品搜索/导购（对接 Mock 商城搜索接口，结果由回复器渲染成商品卡片）
class ProductSearchProvider(KnowledgeProvider):
    provider_id = 'product.search'

    # 回复器识别该前缀后不再走 LLM，直接渲染商品卡片
    SEARCH_PREFIX = "PRODUCT_SEARCH_JSON:"

    # 去掉口语虚词，留下有效搜索词
    _NOISE_RE = re.compile(
        r"[？?！!。，,.\s]|有没有|推荐一下|推荐|想买|想看看|想要|有什么|还有什么|什么|怎么样|吗|呢|吧|请问|帮我|我想|看看|一下|商城|你们|店铺")

    async def retrieve(self, state: DialogueState) -> list[KnowledgeChunk]:
        text = ""
        pt = state.pending_turn
        if pt is not None and pt.user_message is not None and pt.user_message.text:
            text = pt.user_message.text
        q = self._NOISE_RE.sub("", text or "").strip()
        url = f"{settings.commerce_api_base_url}/products/search"
        response = await http_client.http_client.get(url, params={"q": q})
        items = response.json().get("data", [])
        return [KnowledgeChunk(content=self.SEARCH_PREFIX + json.dumps(items, ensure_ascii=False))]


# RAGAPI
class RAGProvider(KnowledgeProvider):
    provider_id = 'rag.default'

    async def retrieve(self, state: DialogueState) -> list[KnowledgeChunk]:
        # TODO 接入向量检索（Qdrant + ES 双索引）
        return [KnowledgeChunk(content="RAG：未检索到相关信息")]
