# WebUI Route B Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 构建单机自用的 WebUI（登录、索引库管理、索引构建、搜索、多向量选择），并通过服务层复用现有 CLI 逻辑。

**Architecture:** FastAPI 提供 Web/UI 与 API，SQLite 存元数据与会话；服务层封装索引构建/搜索/去重；后台任务负责长耗时的构建与日志流式输出；HTMX + Jinja2 渲染 UI。

**Tech Stack:** Python 3.11, FastAPI, Starlette, Jinja2, HTMX, SQLite (stdlib), Meilisearch SDK, pytest.

---

### Task 1: 测试框架与基础配置（为后续 TDD 打底）

**Files:**
- Create: `tests/__init__.py`
- Create: `pytest.ini`
- Create: `requirements-dev.txt`

**Step 1: Write the failing test**

```python
# tests/test_pytest_bootstrap.py
def test_pytest_bootstrap():
    assert True
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_pytest_bootstrap.py -v`
Expected: FAIL (因为文件不存在)

**Step 3: Write minimal implementation**

```ini
# pytest.ini
[pytest]
testpaths = tests
```

```text
# requirements-dev.txt
pytest>=9.0.0
```

```python
# tests/test_pytest_bootstrap.py
def test_pytest_bootstrap():
    assert True
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_pytest_bootstrap.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add pytest.ini requirements-dev.txt tests/__init__.py tests/test_pytest_bootstrap.py
git commit -m "test: bootstrap pytest"
```

### Task 2: FastAPI 应用骨架与健康检查

**Files:**
- Create: `game_web/__init__.py`
- Create: `game_web/app.py`
- Test: `tests/test_healthz.py`

**Step 1: Write the failing test**

```python
from fastapi.testclient import TestClient

from game_web.app import create_app


def test_healthz_ok():
    client = TestClient(create_app())
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_healthz.py -v`
Expected: FAIL (无法导入 game_web 或 create_app)

**Step 3: Write minimal implementation**

```python
# game_web/app.py
from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI()

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    return app
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_healthz.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add game_web/__init__.py game_web/app.py tests/test_healthz.py
git commit -m "feat: add FastAPI app factory with healthz"
```

### Task 3: SQLite 元数据与 schema 初始化

**Files:**
- Create: `game_web/db.py`
- Test: `tests/test_db_init.py`

**Step 1: Write the failing test**

```python
import sqlite3

from game_web.db import init_db


def test_init_db_creates_tables(tmp_path):
    db_path = tmp_path / "app.db"
    init_db(str(db_path))
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("select name from sqlite_master where type='table'")
    tables = {row[0] for row in cur.fetchall()}
    assert "admin_user" in tables
    assert "library" in tables
    assert "session" in tables
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_db_init.py -v`
Expected: FAIL (init_db 未实现)

**Step 3: Write minimal implementation**

```python
# game_web/db.py
import sqlite3


SCHEMA_SQL = """
create table if not exists admin_user (
  id integer primary key autoincrement,
  username text unique not null,
  password_hash text not null,
  created_at text not null
);
create table if not exists library (
  id integer primary key autoincrement,
  name text unique not null,
  index_uid text unique not null,
  description text,
  created_at text not null,
  updated_at text not null
);
create table if not exists session (
  id text primary key,
  user_id integer not null,
  created_at text not null,
  expires_at text not null
);
"""


def init_db(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_db_init.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add game_web/db.py tests/test_db_init.py
git commit -m "feat: add sqlite schema init"
```

### Task 4: 密码哈希与管理员账号创建

**Files:**
- Create: `game_web/auth.py`
- Test: `tests/test_auth_password.py`

**Step 1: Write the failing test**

```python
from game_web.auth import hash_password, verify_password


def test_password_hash_roundtrip():
    hashed = hash_password("secret")
    assert hashed != "secret"
    assert verify_password("secret", hashed) is True
    assert verify_password("wrong", hashed) is False
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_auth_password.py -v`
Expected: FAIL (hash_password 未实现)

**Step 3: Write minimal implementation**

```python
# game_web/auth.py
import hashlib
import hmac
import os


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return salt.hex() + ":" + digest.hex()


def verify_password(password: str, stored: str) -> bool:
    salt_hex, digest_hex = stored.split(":", 1)
    salt = bytes.fromhex(salt_hex)
    expected = bytes.fromhex(digest_hex)
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return hmac.compare_digest(actual, expected)
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_auth_password.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add game_web/auth.py tests/test_auth_password.py
git commit -m "feat: add password hashing helpers"
```

### Task 5: 登录/退出与会话存储

**Files:**
- Create: `game_web/session.py`
- Modify: `game_web/app.py`
- Test: `tests/test_login_flow.py`

**Step 1: Write the failing test**

```python
from fastapi.testclient import TestClient

from game_web.app import create_app


def test_login_sets_session_cookie(tmp_path):
    app = create_app(db_path=str(tmp_path / "app.db"))
    client = TestClient(app)
    resp = client.post("/login", data={"username": "admin", "password": "admin"})
    assert resp.status_code in (200, 302)
    assert "session" in resp.cookies
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_login_flow.py -v`
Expected: FAIL (create_app 参数/登录路由未实现)

**Step 3: Write minimal implementation**

```python
# game_web/session.py
import secrets
import sqlite3
from datetime import datetime, timedelta


def create_session(conn: sqlite3.Connection, user_id: int, ttl_hours: int = 24) -> str:
    sid = secrets.token_urlsafe(32)
    now = datetime.utcnow()
    expires = now + timedelta(hours=ttl_hours)
    conn.execute(
        "insert into session (id, user_id, created_at, expires_at) values (?, ?, ?, ?)",
        (sid, user_id, now.isoformat(), expires.isoformat()),
    )
    conn.commit()
    return sid
```

```python
# game_web/app.py (最小实现)
from fastapi import FastAPI, Form
from fastapi.responses import RedirectResponse
import sqlite3

from .db import init_db


def create_app(db_path: str = "app.db") -> FastAPI:
    app = FastAPI()
    init_db(db_path)

    @app.post("/login")
    def login(username: str = Form(...), password: str = Form(...)):
        # 单机自用：首次固定 admin/admin，后续再改为真正的用户表
        if username != "admin" or password != "admin":
            return {"error": "invalid"}
        conn = sqlite3.connect(db_path)
        conn.execute(
            "insert or ignore into admin_user (id, username, password_hash, created_at) values (1, 'admin', 'dummy', datetime('now'))"
        )
        from .session import create_session

        sid = create_session(conn, 1)
        resp = RedirectResponse("/", status_code=302)
        resp.set_cookie("session", sid, httponly=True)
        return resp

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    return app
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_login_flow.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add game_web/app.py game_web/session.py tests/test_login_flow.py
git commit -m "feat: add basic login and session cookie"
```

### Task 6: Library 服务层（创建/列表）

**Files:**
- Create: `game_web/services/library_service.py`
- Test: `tests/test_library_service.py`

**Step 1: Write the failing test**

```python
import sqlite3

from game_web.db import init_db
from game_web.services.library_service import create_library, list_libraries


def test_library_create_and_list(tmp_path):
    db_path = tmp_path / "app.db"
    init_db(str(db_path))
    conn = sqlite3.connect(db_path)
    create_library(conn, name="games", index_uid="games")
    rows = list_libraries(conn)
    assert len(rows) == 1
    assert rows[0]["name"] == "games"
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_library_service.py -v`
Expected: FAIL (service 未实现)

**Step 3: Write minimal implementation**

```python
# game_web/services/library_service.py
from datetime import datetime
import sqlite3


def create_library(conn: sqlite3.Connection, name: str, index_uid: str, description: str | None = None):
    now = datetime.utcnow().isoformat()
    conn.execute(
        "insert into library (name, index_uid, description, created_at, updated_at) values (?, ?, ?, ?, ?)",
        (name, index_uid, description, now, now),
    )
    conn.commit()


def list_libraries(conn: sqlite3.Connection):
    cur = conn.execute("select id, name, index_uid, description from library order by id asc")
    rows = cur.fetchall()
    return [
        {"id": r[0], "name": r[1], "index_uid": r[2], "description": r[3]} for r in rows
    ]
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_library_service.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add game_web/services/library_service.py tests/test_library_service.py
git commit -m "feat: add library service"
```

### Task 7: Library Web 页面与鉴权中间件（HTMX 最小页）

**Files:**
- Create: `game_web/routes/library.py`
- Create: `game_web/templates/layout.html`
- Create: `game_web/templates/library_list.html`
- Modify: `game_web/app.py`
- Test: `tests/test_library_page.py`

**Step 1: Write the failing test**

```python
from fastapi.testclient import TestClient

from game_web.app import create_app


def test_library_page_requires_login(tmp_path):
    app = create_app(db_path=str(tmp_path / "app.db"))
    client = TestClient(app)
    resp = client.get("/libraries")
    assert resp.status_code in (302, 401)
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_library_page.py -v`
Expected: FAIL (路由/鉴权未实现)

**Step 3: Write minimal implementation**

实现一个简单的 `require_login()` 依赖：当没有 session cookie 时重定向 /login。

```python
# game_web/routes/library.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
import sqlite3

from .auth_guard import require_login
from ..services.library_service import list_libraries

router = APIRouter()


@router.get("/libraries", response_class=HTMLResponse)
def library_list(request: Request, user_id: int = Depends(require_login)):
    conn = sqlite3.connect(request.app.state.db_path)
    libraries = list_libraries(conn)
    return request.app.state.templates.TemplateResponse(
        "library_list.html", {"request": request, "libraries": libraries}
    )
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_library_page.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add game_web/routes/library.py game_web/templates/layout.html game_web/templates/library_list.html game_web/app.py tests/test_library_page.py
git commit -m "feat: add library list page with auth guard"
```

### Task 8: Embedding Profile（多向量）元数据

**Files:**
- Modify: `game_web/db.py`
- Create: `game_web/services/embedding_profile.py`
- Test: `tests/test_embedding_profile.py`

**Step 1: Write the failing test**

```python
import sqlite3

from game_web.db import init_db
from game_web.services.embedding_profile import add_profile, list_profiles


def test_add_and_list_profiles(tmp_path):
    db_path = tmp_path / "app.db"
    init_db(str(db_path))
    conn = sqlite3.connect(db_path)
    add_profile(conn, library_id=1, key="v_name", model_name="BAAI/bge-m3")
    profiles = list_profiles(conn, library_id=1)
    assert profiles[0]["key"] == "v_name"
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_embedding_profile.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

在 `game_web/db.py` 增加 embedding_profile 表；实现 `add_profile/list_profiles`。

**Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_embedding_profile.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add game_web/db.py game_web/services/embedding_profile.py tests/test_embedding_profile.py
git commit -m "feat: add embedding profile metadata"
```

### Task 9: Meili Client 多向量查询参数化（基础增强）

**Files:**
- Modify: `game_semantic/meili_client.py`
- Test: `tests/test_meili_search_payload.py`

**Step 1: Write the failing test**

```python
from game_semantic.meili_client import MeiliGameIndex


def test_search_by_vector_uses_embedder_key(monkeypatch):
    index = MeiliGameIndex(url="http://localhost", api_key="x", index_uid="t")

    captured = {}

    def fake_search(query, payload):
        captured.update(payload)
        return {"hits": []}

    index.index.search = fake_search
    index.search_by_vector([0.1, 0.2], limit=5, embedder_key="v_name")
    assert captured["hybrid"]["embedder"] == "v_name"
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_meili_search_payload.py -v`
Expected: FAIL (search_by_vector 不接受 embedder_key)

**Step 3: Write minimal implementation**

为 `search_by_vector` 增加 `embedder_key` 参数；当为空时使用默认 `self.embedder_name`。

**Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_meili_search_payload.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add game_semantic/meili_client.py tests/test_meili_search_payload.py
git commit -m "feat: allow choosing embedder key in vector search"
```

### Task 10: 搜索服务层（选择向量通道）

**Files:**
- Create: `game_web/services/search_service.py`
- Test: `tests/test_search_service.py`

**Step 1: Write the failing test**

```python
from game_web.services.search_service import build_query_payload


def test_build_query_payload_includes_embedder():
    payload = build_query_payload([0.1, 0.2], limit=3, embedder_key="v_alias")
    assert payload["hybrid"]["embedder"] == "v_alias"
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_search_service.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# game_web/services/search_service.py
def build_query_payload(query_vector, limit: int, embedder_key: str):
    return {
        "vector": query_vector,
        "hybrid": {"semanticRatio": 1.0, "embedder": embedder_key},
        "limit": limit,
    }
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_search_service.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add game_web/services/search_service.py tests/test_search_service.py
git commit -m "feat: add search payload builder"
```

### Task 11: 搜索页面（选择库与向量通道）

**Files:**
- Create: `game_web/routes/search.py`
- Create: `game_web/templates/search.html`
- Modify: `game_web/app.py`
- Test: `tests/test_search_page.py`

**Step 1: Write the failing test**

```python
from fastapi.testclient import TestClient

from game_web.app import create_app


def test_search_page_renders(tmp_path):
    app = create_app(db_path=str(tmp_path / "app.db"))
    client = TestClient(app)
    resp = client.get("/search")
    assert resp.status_code in (200, 302)
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_search_page.py -v`
Expected: FAIL (路由不存在)

**Step 3: Write minimal implementation**

创建 `/search` 页面，展示库下拉与 embedder 下拉（先空列表/占位）。

**Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_search_page.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add game_web/routes/search.py game_web/templates/search.html game_web/app.py tests/test_search_page.py
git commit -m "feat: add search page skeleton"
```

### Task 12: 索引构建任务与日志（最小可用）

**Files:**
- Create: `game_web/jobs.py`
- Create: `game_web/services/job_service.py`
- Test: `tests/test_job_log.py`

**Step 1: Write the failing test**

```python
from game_web.jobs import write_log_line


def test_write_log_line(tmp_path):
    log_path = tmp_path / "job.log"
    write_log_line(str(log_path), "hello")
    assert log_path.read_text().strip() == "hello"
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_job_log.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# game_web/jobs.py
def write_log_line(path: str, line: str) -> None:
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_job_log.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add game_web/jobs.py tests/test_job_log.py
git commit -m "feat: add job log writer"
```

### Task 13: CLI 复用服务层（路线 B 核心目标）

**Files:**
- Create: `game_semantic/service.py`
- Modify: `bin/build_games_index.py`
- Modify: `bin/search_games.py`
- Modify: `bin/dedupe_items.py`
- Test: `tests/test_service_smoke.py`

**Step 1: Write the failing test**

```python
from game_semantic.service import build_index_from_config


def test_service_smoke_no_crash(tmp_path, monkeypatch):
    # 只验证函数存在与可调用，具体逻辑用集成测试覆盖
    assert callable(build_index_from_config)
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_service_smoke.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

在 `game_semantic/service.py` 中提供包装函数，内部调用现有模块。

**Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_service_smoke.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add game_semantic/service.py bin/build_games_index.py bin/search_games.py bin/dedupe_items.py tests/test_service_smoke.py
git commit -m "refactor: add service wrapper for CLI reuse"
```

---

## 验证/手动测试

1) 启动 Web：`uvicorn game_web.app:create_app --factory --reload`
2) 打开 `http://127.0.0.1:8000`，完成登录
3) 创建 Library，添加 embedding profile
4) 触发 rebuild/append，查看日志
5) 搜索页面选择 embedder，执行查询

---

## 备注与取舍

- 以上计划优先保证“单机自用可用”，多用户与 RBAC 不在范围内。
- 多向量融合（RRF/加权）留在下一阶段；本阶段先做“可选 embedder”。
- 索引构建任务先做同步/最小日志，后续再引入更完整的任务队列。
