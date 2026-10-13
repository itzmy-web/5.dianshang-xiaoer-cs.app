# itzmy/infrastructure/trace.py
"""LLM 调用追踪工具：包一层 await，把轨道/耗时/成败写入 llm_traces 表。

用法（把原来的 `await chain.ainvoke(...)` 换成）：
    result = await trace_llm("knowledge", prompt_text, chain.ainvoke(...))

说明：这是自建的 mini 可观测（表 llm_traces + 运营看板展示）。
如需接入 Langfuse/LangSmith，只需在本函数里额外上报 span，
或配置 LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST 环境变量后
在 chain 上挂 callback handler，其余代码零改动。
"""

import time

from infrastructure import database
from models.trace import LlmTraceRecord


async def trace_llm(track: str, model: str, prompt_text: str, coro):
    """执行 LLM 调用并记录追踪；追踪失败绝不影响主链路"""
    t0 = time.time()
    ok = True
    try:
        return await coro
    except Exception:
        ok = False
        raise
    finally:
        try:
            async with database.async_session() as session:
                session.add(LlmTraceRecord(
                    track=track,
                    model=model,
                    latency_ms=int((time.time() - t0) * 1000),
                    prompt_chars=len(prompt_text or ""),
                    ok=ok,
                ))
                await session.commit()
        except Exception:
            pass
