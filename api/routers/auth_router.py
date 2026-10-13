# itzmy/api/routers/auth_router.py
"""登录认证（演示级）：手机验证码 + 微信/支付宝扫码 + 游客
设计参照问题自检项目：
  - 手机号：发码（演示环境验证码直接回显）→ 验证码登录，自动注册
  - 扫码：demo 模式，前端展示仿真二维码 → 「模拟扫码成功」调 confirm → 前端轮询 status 拿 token
  - 真实微信/支付宝 OAuth 只需配置 WX_APPID / ALI_APPID 等环境变量即可升级
"""

import re
import secrets
import time
import uuid
import asyncio
import concurrent.futures

from fastapi import APIRouter, Cookie, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import select, text

from infrastructure import database
from models.user import UserRecord

router = APIRouter()

COOKIE_NAME = "cs_token"

PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
CODE_TTL = 300          # 验证码 5 分钟有效
QR_TTL = 120            # 二维码 2 分钟有效

# 演示态存储（进程内存；重启失效，重新走流程即可）
_PHONE_CODES: dict[str, dict] = {}   # phone -> {code, exp}
_QR_TICKETS: dict[str, dict] = {}    # ticket -> {provider, exp, status, token, username}
_TOKENS: dict[str, dict] = {}        # token -> user（演示级；生产应持久化/JWT）

# ---------------- 防刷限流（滑动窗口，进程内存版） ----------------
# 同手机号：60 秒内只允许发 1 条验证码；同 IP：10 分钟内最多 5 条（防脚本轰炸）
_PHONE_COOLDOWN: dict[str, float] = {}   # phone -> 上次发送时间戳
_IP_SENDS: dict[str, list[float]] = {}   # ip -> [发送时间戳]
IP_WINDOW = 600.0
IP_LIMIT = 5


def _check_send_rate(phone: str, client_ip: str) -> None:
    now = _now()
    last = _PHONE_COOLDOWN.get(phone)
    if last and now - last < 60.0:
        raise HTTPException(status_code=429,
                            detail=f"发送太频繁，请 {int(60 - (now - last)) + 1} 秒后再试")
    stamps = [t for t in _IP_SENDS.get(client_ip, []) if now - t < IP_WINDOW]
    if len(stamps) >= IP_LIMIT:
        raise HTTPException(status_code=429,
                            detail="该网络发送验证码次数已达上限，请 10 分钟后再试")
    _PHONE_COOLDOWN[phone] = now
    stamps.append(now)
    _IP_SENDS[client_ip] = stamps
    # 顺手清理过期手机号冷却，防字典无限膨胀
    for p in [p for p, t in _PHONE_COOLDOWN.items() if now - t > 3600]:
        _PHONE_COOLDOWN.pop(p, None)


class SendCodeReq(BaseModel):
    phone: str


class PhoneLoginReq(BaseModel):
    phone: str
    code: str


class ConfirmReq(BaseModel):
    ticket: str


def _now() -> float:
    return time.time()


def _find_or_create_user(provider: str, username: str, display_name: str) -> dict:
    """按 username 查找或创建用户，返回 {id, username, display_name, provider}"""

    async def _run():
        async with database.async_session() as session:
            user = (await session.execute(
                select(UserRecord).where(UserRecord.username == username)
            )).scalar_one_or_none()
            if not user:
                user = UserRecord(provider=provider, username=username, display_name=display_name)
                session.add(user)
                await session.commit()
                await session.refresh(user)
            return {"id": user.id, "username": user.username,
                    "display_name": user.display_name, "provider": user.provider}

    # 路由在事件循环里，开独立线程跑新循环避免嵌套
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, _run()).result()


def _token_for(user: dict) -> str:
    """演示级 token：随机串 + 内存映射（重启失效，重新登录即可）"""
    token = secrets.token_hex(16)
    _TOKENS[token] = user
    return token


def _set_auth_cookie(response: Response, token: str) -> None:
    """登录成功下发 HttpOnly cookie：服务端门禁（/ 未登录 302 到登录页）凭它判断"""
    response.set_cookie(COOKIE_NAME, token, max_age=8 * 3600,
                        httponly=True, samesite="lax", path="/")


def is_valid_token(token: str | None) -> bool:
    """供服务端门禁路由调用：cookie 里的 token 必须是当前存活的登录态"""
    return bool(token) and token in _TOKENS


# ---------------- 手机号：发码 ----------------
@router.post("/api/auth/send-code")
async def send_code(req: SendCodeReq, request: Request):
    phone = req.phone.strip()
    if not PHONE_RE.match(phone):
        raise HTTPException(status_code=400, detail="手机号格式不正确")
    # 服务端防刷：同手机号 60s 冷却 + 同 IP 滑动窗口限额（前端倒计时只是体验，防不住脚本）
    _check_send_rate(phone, request.client.host if request.client else "unknown")
    code = f"{secrets.randbelow(900000) + 100000:06d}"
    _PHONE_CODES[phone] = {"code": code, "exp": _now() + CODE_TTL}
    # 真实环境此处调用短信网关；演示直接打印到服务端日志并回显
    print(f"[DEMO] 向 {phone} 发送验证码：{code}")
    return {"ok": True, "message": "验证码已发送（演示环境直接回显）", "demo_code": code}


# ---------------- 手机号：登录/自动注册 ----------------
@router.post("/api/auth/login")
async def phone_login(req: PhoneLoginReq, response: Response):
    phone = req.phone.strip()
    if not PHONE_RE.match(phone):
        raise HTTPException(status_code=400, detail="手机号格式不正确")
    rec = _PHONE_CODES.get(phone)
    if not rec or rec["exp"] < _now():
        raise HTTPException(status_code=400, detail="验证码已过期，请重新获取")
    if rec["code"] != req.code.strip():
        raise HTTPException(status_code=400, detail="验证码错误")
    del _PHONE_CODES[phone]
    user = _find_or_create_user("phone", phone, phone)
    token = _token_for(user)
    _set_auth_cookie(response, token)
    return {"ok": True, "token": token, "user": user}


# ---------------- 会话校验（前端每次进页面验 token，失效踢回登录页） ----------------
@router.get("/api/auth/me")
async def me(token: str = Query(...)):
    user = _TOKENS.get(token)
    if not user:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    return {"ok": True, "user": user}


# ---------------- 游客体验 ----------------
@router.post("/api/auth/guest")
async def guest(response: Response):
    gid = "guest_" + uuid.uuid4().hex[:10]
    user = _find_or_create_user("guest", gid, "游客")
    token = _token_for(user)
    _set_auth_cookie(response, token)
    return {"ok": True, "token": token, "user": user, "guest": True}


# ---------------- 退出登录 ----------------
@router.post("/api/auth/logout")
async def logout(response: Response, cs_token: str | None = Cookie(default=None)):
    if cs_token:
        _TOKENS.pop(cs_token, None)
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True, "message": "已退出登录"}


# ---------------- 扫码：取二维码（demo 模式） ----------------
@router.get("/api/auth/{provider}/qrcode")
async def qrcode(provider: str):
    if provider not in ("wx", "ali"):
        raise HTTPException(status_code=400, detail="不支持的登录方式")
    ticket = uuid.uuid4().hex
    _QR_TICKETS[ticket] = {"provider": provider, "exp": _now() + QR_TTL,
                           "status": "pending", "token": "", "username": ""}
    # 演示模式：二维码内容为 confirm 接口地址（前端画仿真二维码 + 模拟扫码按钮）
    url = f"/api/auth/{provider}/confirm?ticket={ticket}"
    return {"ok": True, "ticket": ticket, "url": url, "mode": "demo", "exp": QR_TTL}


# ---------------- 扫码：轮询状态 ----------------
@router.get("/api/auth/{provider}/status")
async def qr_status(provider: str, response: Response, ticket: str = Query(...)):
    s = _QR_TICKETS.get(ticket)
    if not s or s["provider"] != provider:
        raise HTTPException(status_code=404, detail="二维码不存在或已失效")
    if s["exp"] < _now():
        raise HTTPException(status_code=410, detail="二维码已过期，请刷新")
    if s["status"] == "confirmed" and s["token"]:
        _set_auth_cookie(response, s["token"])
        return {"status": "confirmed", "token": s["token"],
                "user": {"username": s["username"], "display_name": s["username"], "provider": provider}}
    return {"status": s["status"]}


# ---------------- 扫码：演示模式「模拟扫码成功」 ----------------
@router.post("/api/auth/{provider}/confirm")
async def qr_confirm(provider: str, req: ConfirmReq):
    s = _QR_TICKETS.get(req.ticket)
    if not s or s["provider"] != provider:
        raise HTTPException(status_code=404, detail="二维码不存在或已失效")
    if s["exp"] < _now():
        raise HTTPException(status_code=410, detail="二维码已过期，请刷新")
    if s["status"] != "confirmed":
        label = "微信用户" if provider == "wx" else "支付宝用户"
        username = f"{label}_{uuid.uuid4().hex[:6]}"
        user = _find_or_create_user(provider, username, username)
        s["status"] = "confirmed"
        s["token"] = _token_for(user)
        s["username"] = username
    return {"ok": True}


# ---------------- 登录页公开信息（无需登录：真实服务数据 + 运行状态） ----------------
@router.get("/api/auth/public-info")
async def public_info():
    """给登录页展示用：FAQ 条数 / 累计会话 / 注册用户 / LLM 调用次数 / 知识库块数。
    全部只读 COUNT，不含任何敏感内容；单表查询失败按 0 处理，保证登录页永不因此挂掉。"""

    async def _run():
        out = {"ok": True, "version": "V10.1", "llm_online": True,
               "faq": 0, "chats": 0, "users": 0, "llm_calls": 0, "kb": 0}
        async with database.async_session() as session:
            async def _cnt(sql: str) -> int:
                try:
                    return (await session.execute(text(sql))).scalar() or 0
                except Exception:
                    return 0
            out["faq"] = await _cnt("SELECT COUNT(*) FROM faq_entries")
            out["chats"] = await _cnt("SELECT COUNT(*) FROM chat_metrics")
            out["users"] = await _cnt("SELECT COUNT(*) FROM users")
            out["llm_calls"] = await _cnt("SELECT COUNT(*) FROM llm_traces")
            out["kb"] = await _cnt("SELECT COUNT(*) FROM kb_chunks")
        return out

    # 复用项目既有模式：独立线程跑新事件循环，避免嵌套循环问题
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, _run()).result()
