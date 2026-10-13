# itzmy/tests/test_app.py
"""
电商小二 · 核心链路测试套件（V10 ②）。

覆盖：
- 健康检查
- 登录门（服务端 302 gate）：未登录 302 / 登录后 200 / 登出后 302
- 游客登录发 HttpOnly cookie
- 验证码限流（同手机号 60s 冷却 → 429）
- 管理员登录（错密码 401 / 对密码 200）与 FAQ 写操作鉴权
- 聊天 canned 快路径（转人工 / 告别总结，不调 LLM）
- 新话题（new-session）与任务进度（progress）

运行：uv run --with pytest pytest -q tests
"""
import time

import pytest


# ---------------- 健康检查 ----------------

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ---------------- 登录门（V9 服务端 gate） ----------------

def test_index_redirects_when_not_logged_in(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert "/login.html" in r.headers["location"]


def test_index_ok_with_cookie(auth_client):
    r = auth_client.get("/", follow_redirects=False)
    assert r.status_code == 200


def test_guest_sets_httponly_cookie(client):
    r = client.post("/api/auth/guest")
    assert r.status_code == 200
    set_cookie = r.headers.get("set-cookie", "")
    assert "cs_token=" in set_cookie
    assert "httponly" in set_cookie.lower()


def test_logout_invalidates_gate(client):
    client.post("/api/auth/guest")
    client.post("/api/auth/logout")
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302


def test_login_page_served(client):
    r = client.get("/login.html")
    assert r.status_code == 200


# ---------------- ③ 验证码限流 ----------------

def test_send_code_rate_limit(client):
    phone = f"139{int(time.time()) % 10**8:08d}"  # 每次测试用独立手机号，避免进程内冷却残留
    r1 = client.post("/api/auth/send-code", json={"phone": phone})
    assert r1.status_code == 200
    r2 = client.post("/api/auth/send-code", json={"phone": phone})
    assert r2.status_code == 429
    assert "秒" in r2.json()["detail"]


# ---------------- 管理员鉴权 + FAQ 写保护 ----------------

def test_admin_login_wrong_password(client):
    r = client.post("/api/admin/login", json={"password": "definitely-wrong"})
    assert r.status_code == 401


def test_admin_login_ok(client):
    from conf.config import settings

    r = client.post("/api/admin/login", json={"password": settings.admin_password})
    assert r.status_code == 200
    token = r.json()["token"]
    assert token


def test_faq_write_requires_admin(client):
    r = client.post("/api/faq", json={"title": "x", "keywords": [], "answer": "y"})
    assert r.status_code in (401, 403)


def test_faq_crud_with_admin(client):
    from conf.config import settings

    login = client.post("/api/admin/login", json={"password": settings.admin_password})
    headers = {"X-Admin-Token": login.json()["token"]}

    # 新增
    r = client.post(
        "/api/faq",
        json={"title": "测试FAQ", "keywords": ["测试"], "answer": "这是测试答案"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    faq_id = r.json().get("id")

    # 列表里有
    items = client.get("/api/faq").json()["items"]
    assert any(f["title"] == "测试FAQ" for f in items)

    # 改
    r = client.put(
        f"/api/faq/{faq_id}",
        json={"title": "测试FAQ改", "keywords": ["测试"], "answer": "改后答案", "enabled": False},
        headers=headers,
    )
    assert r.status_code == 200

    # 删
    r = client.delete(f"/api/faq/{faq_id}", headers=headers)
    assert r.status_code == 200


# ---------------- 聊天 canned 快路径（不调 LLM） ----------------

def test_chat_transfer_human(auth_client):
    r = auth_client.post("/api/chat", json={"sender_id": "t_transfer", "text": "转人工"})
    assert r.status_code == 200
    body = r.json()
    texts = " ".join(m["text"] or "" for m in body["messages"])
    assert "人工" in texts
    assert body.get("elapsed_ms") is not None


def test_chat_farewell_summary(auth_client):
    r = auth_client.post("/api/chat", json={"sender_id": "t_farewell", "text": "没有了，谢谢"})
    assert r.status_code == 200
    texts = " ".join(m["text"] or "" for m in r.json()["messages"])
    assert len(texts) > 0


# ---------------- 新话题 / 进度 ----------------

def test_new_session_and_progress(auth_client):
    r = auth_client.post("/api/chat/new-session", json={"sender_id": "t_newsession", "text": ""})
    assert r.status_code == 200

    r = auth_client.get("/api/chat/progress", params={"sender_id": "t_newsession"})
    assert r.status_code == 200
    data = r.json()
    # 无进行中任务时返回 {"active": false}（可能无 flow_id 字段）
    assert data.get("active") is False


# ---------------- 看板数据（⑥⑦） ----------------

def test_stats_has_wordcloud_and_llm_stats(client):
    r = client.get("/api/stats")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data.get("wordcloud"), list)
    assert "llm_stats" in data
    assert {"total_calls", "fail_calls", "by_track", "recent"} <= set(data["llm_stats"])
