# itzmy/tests/conftest.py
"""
pytest 全局夹具。

关键点：必须在导入任何项目模块（api.app / conf.config）之前，
通过环境变量把 DATABASE_URL 指向临时 sqlite 文件——
pydantic-settings 中环境变量优先级高于 .env 文件，
这样测试永远不会碰真实的 customer_service.db。
"""
import os
import tempfile

_TMP_DIR = tempfile.mkdtemp(prefix="cs_test_")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP_DIR}/test.db"

import pytest
from fastapi.testclient import TestClient

from api.app import app


@pytest.fixture(scope="session")
def client():
    """TestClient 上下文管理器会触发 lifespan（建表 / FAQ 种子 / 迁移）。"""
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_client(client):
    """已登录（guest）的 client：带 cs_token cookie。"""
    r = client.post("/api/auth/guest")
    assert r.status_code == 200, r.text
    return client
