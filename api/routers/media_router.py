# itzmy/api/routers/media_router.py
"""图片识别（多模态）：用户上传商品截图/报错截图，走 Qwen-VL 理解并回复"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from conf.config import settings
from infrastructure import http_client

router = APIRouter()


class ImageChatRequest(BaseModel):
    sender_id: str
    image: str                 # dataURL（data:image/jpeg;base64,xxx）或纯 base64
    caption: str | None = None # 用户随图补充的文字说明，可为空


@router.post("/api/chat/image")
async def image_chat(req: ImageChatRequest):
    # 1. 组装图片 dataURL：前端传完整 dataURL 就原样用（保留 png/jpeg 真实类型），纯 base64 才补 jpeg 前缀
    data_url = req.image.strip() if req.image.strip().startswith("data:") else f"data:image/jpeg;base64,{req.image}"
    # 1.5 尺寸校验（按 base64 主体长度估算）
    b64 = data_url.split(",", 1)[-1]
    if not b64 or len(b64) < 100:
        raise HTTPException(status_code=400, detail="图片数据无效")
    if len(b64) > 6 * 1024 * 1024:  # ~4.5MB 原图上限（前端已压缩）
        raise HTTPException(status_code=400, detail="图片太大，请换一张小一些的")

    # 2. 组装多模态消息（OpenAI 兼容格式，SiliconFlow 直接支持）
    prompt = "你是电商客服小二。用户发来一张图片，请先简述你在图片里看到了什么，再结合电商客服场景给出帮助建议。"
    if req.caption:
        prompt += f"\n用户补充说明：{req.caption}"
    payload = {
        "model": settings.vl_model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }],
        "max_tokens": 500,
        "temperature": 0.2,
    }
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}

    # 3. 调用视觉模型（全局 client 超时 10s，此处单独放宽到 60s）
    try:
        resp = await http_client.http_client.post(
            settings.llm_base_url.rstrip("/") + "/chat/completions",
            json=payload, headers=headers, timeout=60.0,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"视觉模型连接失败：{e}")
    if resp.status_code != 200:
        detail = f"视觉模型返回 {resp.status_code}"
        try:
            detail += "：" + str(resp.json().get("message", ""))[:200]
        except Exception:
            pass
        raise HTTPException(status_code=502, detail=detail)

    try:
        reply = resp.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        raise HTTPException(status_code=502, detail="视觉模型返回格式异常")
    if not reply:
        raise HTTPException(status_code=502, detail="视觉模型返回为空")

    return {"ok": True, "reply": reply}
