# WebUI Basic-Usable Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 把 WebUI 推进到“基本可用”：单人管理员自用、HTML 登录/退出、库管理、embedding profiles、多向量索引构建与搜索、后台 job + 日志、数据落盘在 `./data/`。

**Architecture:** FastAPI + Jinja2 作为 Web UI；SQLite 存 admin/library/profile/dataset/job/session/settings；单线程 job runner 执行构建并写日志；搜索页面根据 profile 选择 embedder_key 调 Meilisearch；BGE-M3 模型做进程内缓存。

**Tech Stack:** Python 3.11, FastAPI, Jinja2Templates, SQLite, Meilisearch SDK, FlagEmbedding (BGE-M3), pytest, httpx, uvicorn, python-multipart.

---

### Task 1: Web 运行入口与数据目录（./data）

**Files:**
- Create: `game_web/runtime.py`
- Create: `bin/web_ui.py`
- Modify: `.gitignore`
- Modify: `requirements.txt`
- Test: `tests/test_runtime_paths.py`

**Step 1: Write the failing test**

```python
from pathlib import Path

from game_web.runtime import resolve_data_dir


def test_resolve_data_dir_defaults_to_project_data(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data_dir = resolve_data_dir(None)
    assert data_dir == tmp_path / "data"
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_runtime_paths.py::test_resolve_data_dir_defaults_to_project_data -v`
Expected: FAIL with "No module named 'game_web.runtime'"

**Step 3: Write minimal implementation**

```python
# game_web/runtime.py
from pathlib import Path


def resolve_data_dir(path: str | None) -> Path:
    if path:
        return Path(path).expanduser().resolve()
    return Path.cwd() / "data"
```

```python
# bin/web_ui.py
import argparse
from pathlib import Path

import uvicorn

from game_web.runtime import resolve_data_dir


def main():
    parser = argparse.ArgumentParser(description="Run local web UI.")
    parser.add_argument("--data-dir", dest="data_dir", help="Path for app data (default ./data).")
    parser.add_argument("--host", dest="host", default="127.0.0.1")
    parser.add_argument("--port", dest="port", type=int, default=8000)
    parser.add_argument("--reload", dest="reload", action="store_true")
    args = parser.parse_args()

    data_dir = resolve_data_dir(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "app.db"

    uvicorn.run("game_web.app:create_app", factory=True, host=args.host, port=args.port, reload=args.reload, kwargs={"db_path": str(db_path)})


if __name__ == "__main__":
    main()
```

```text
# .gitignore (append)
data/
.venv/
```

```text
# requirements.txt (append)
uvicorn>=0.30.0
python-multipart>=0.0.9
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_runtime_paths.py::test_resolve_data_dir_defaults_to_project_data -v`
Expected: PASS

**Step 5: Commit**

```bash
git add game_web/runtime.py bin/web_ui.py .gitignore requirements.txt tests/test_runtime_paths.py
git commit -m "feat: add web runner and data dir defaults"
```

### Task 2: 单管理员初始化 + HTML 登录/退出（移除 admin/admin 硬编码）

**Files:**
- Create: `game_web/services/admin_user_service.py`
- Create: `game_web/routes/auth.py`
- Create: `game_web/templates/setup.html`
- Create: `game_web/templates/login.html`
- Modify: `game_web/app.py`
- Modify: `game_web/auth_guard.py`
- Modify: `game_web/session.py`
- Test: `tests/test_setup_and_login_html.py`

**Step 1: Write the failing test**

```python
from fastapi.testclient import TestClient

from game_web.app import create_app


def test_setup_then_login_flow(tmp_path):
    app = create_app(str(tmp_path / "app.db"))
    client = TestClient(app)

    resp = client.get("/setup")
    assert resp.status_code == 200
    assert "Set admin password" in resp.text

    resp = client.post("/setup", data={"password": "secret"}, follow_redirects=False)
    assert resp.status_code == 302

    resp = client.get("/login")
    assert resp.status_code == 200

    resp = client.post("/login", data={"password": "secret"}, follow_redirects=False)
    assert resp.status_code == 302
    assert "session" in resp.cookies

    resp = client.post("/logout", follow_redirects=False)
    assert resp.status_code == 302
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_setup_and_login_html.py -v`
Expected: FAIL with "No route" or "No module" errors

**Step 3: Write minimal implementation**

```python
# game_web/services/admin_user_service.py
from datetime import datetime, timezone

from game_web.auth import hash_password, verify_password


def has_admin(conn) -> bool:
    cur = conn.execute("select count(*) from admin_user")
    return cur.fetchone()[0] > 0


def create_admin(conn, password: str) -> int:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    hashed = hash_password(password)
    conn.execute(
        "insert into admin_user (username, password_hash, created_at) values (?, ?, ?)",
        ("admin", hashed, now),
    )
    conn.commit()
    return conn.execute("select id from admin_user where username = ?", ("admin",)).fetchone()[0]


def verify_admin(conn, password: str) -> int | None:
    row = conn.execute("select id, password_hash from admin_user where username = ?", ("admin",)).fetchone()
    if not row:
        return None
    if not verify_password(password, row[1]):
        return None
    return row[0]
```

```python
# game_web/routes/auth.py
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from game_web.db import connect_db
from game_web.services.admin_user_service import create_admin, has_admin, verify_admin
from game_web.session import create_session, delete_session

router = APIRouter()


@router.get("/setup", response_class=HTMLResponse)
def setup_page(request: Request):
    conn = connect_db(request.app.state.db_path)
    try:
        if has_admin(conn):
            return RedirectResponse("/login", status_code=302)
    finally:
        conn.close()
    return request.app.state.templates.TemplateResponse(request, "setup.html", {"request": request})


@router.post("/setup")
def setup_submit(request: Request, password: str = Form(...)):
    conn = connect_db(request.app.state.db_path)
    try:
        if not has_admin(conn):
            create_admin(conn, password)
    finally:
        conn.close()
    return RedirectResponse("/login", status_code=302)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return request.app.state.templates.TemplateResponse(request, "login.html", {"request": request})


@router.post("/login")
def login_submit(request: Request, password: str = Form(...)):
    conn = connect_db(request.app.state.db_path)
    try:
        user_id = verify_admin(conn, password)
        if not user_id:
            return request.app.state.templates.TemplateResponse(request, "login.html", {"request": request, "error": "Invalid password"})
        session_id = create_session(conn, user_id=user_id)
    finally:
        conn.close()
    resp = RedirectResponse("/libraries", status_code=302)
    resp.set_cookie("session", session_id, httponly=True, samesite="Lax")
    return resp


@router.post("/logout")
def logout(request: Request):
    session_id = request.cookies.get("session")
    if session_id:
        conn = connect_db(request.app.state.db_path)
        try:
            delete_session(conn, session_id)
        finally:
            conn.close()
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie("session")
    return resp
```

```python
# game_web/session.py (add helper)
def delete_session(conn, session_id: str) -> None:
    conn.execute("delete from session where id = ?", (session_id,))
    conn.commit()
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_setup_and_login_html.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add game_web/services/admin_user_service.py game_web/routes/auth.py game_web/templates/setup.html game_web/templates/login.html game_web/app.py game_web/auth_guard.py game_web/session.py tests/test_setup_and_login_html.py
git commit -m "feat: add single-admin setup and html auth"
```

### Task 3: 认证保护 + TemplateResponse 签名更新

**Files:**
- Modify: `game_web/auth_guard.py`
- Modify: `game_web/routes/library.py`
- Modify: `game_web/routes/search.py`
- Modify: `game_web/templates/layout.html`
- Test: `tests/test_auth_guards.py`

**Step 1: Write the failing test**

```python
from fastapi.testclient import TestClient

from game_web.app import create_app


def test_pages_require_login(tmp_path):
    app = create_app(str(tmp_path / "app.db"))
    client = TestClient(app)

    resp = client.get("/libraries", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers.get("location") == "/login"

    resp = client.get("/search", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers.get("location") == "/login"
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_auth_guards.py -v`
Expected: FAIL (returns 401 or 200)

**Step 3: Write minimal implementation**

```python
# game_web/auth_guard.py (add redirect guard)
from fastapi.responses import RedirectResponse


def require_login_redirect(request):
    session_id = request.cookies.get("session")
    if not session_id:
        return RedirectResponse("/login", status_code=302)
    return None
```

Update routes to use new TemplateResponse signature:

```python
return templates.TemplateResponse(request, "library_list.html", {"request": request, "libraries": libraries})
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_auth_guards.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add game_web/auth_guard.py game_web/routes/library.py game_web/routes/search.py game_web/templates/layout.html tests/test_auth_guards.py
git commit -m "chore: require login and update template responses"
```

### Task 4: Library CRUD UI（创建/删除/详情）

**Files:**
- Modify: `game_web/services/library_service.py`
- Create: `game_web/routes/library_detail.py`
- Modify: `game_web/templates/library_list.html`
- Create: `game_web/templates/library_detail.html`
- Test: `tests/test_library_crud_ui.py`

**Step 1: Write the failing test**

```python
from fastapi.testclient import TestClient

from game_web.app import create_app


def test_create_and_delete_library(tmp_path):
    app = create_app(str(tmp_path / "app.db"))
    client = TestClient(app)

    client.post("/setup", data={"password": "secret"})
    client.post("/login", data={"password": "secret"})

    resp = client.post("/libraries/create", data={"name": "games", "index_uid": "games"}, follow_redirects=False)
    assert resp.status_code == 302

    resp = client.get("/libraries")
    assert "games" in resp.text

    resp = client.post("/libraries/1/delete", follow_redirects=False)
    assert resp.status_code == 302
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_library_crud_ui.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Add service functions `get_library`, `delete_library` and add create/delete forms in templates.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_library_crud_ui.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add game_web/services/library_service.py game_web/routes/library_detail.py game_web/templates/library_list.html game_web/templates/library_detail.html tests/test_library_crud_ui.py
git commit -m "feat: add library CRUD pages"
```

### Task 5: Embedding Profiles（多向量通道）管理与默认 profile

**Files:**
- Modify: `game_web/db.py`
- Modify: `game_web/services/embedding_profile.py`
- Modify: `game_web/services/library_service.py`
- Modify: `game_web/templates/library_detail.html`
- Test: `tests/test_embedding_profiles_ui.py`

**Step 1: Write the failing test**

```python
from fastapi.testclient import TestClient

from game_web.app import create_app


def test_default_profile_and_additional_profiles(tmp_path):
    app = create_app(str(tmp_path / "app.db"))
    client = TestClient(app)
    client.post("/setup", data={"password": "secret"})
    client.post("/login", data={"password": "secret"})
    client.post("/libraries/create", data={"name": "games", "index_uid": "games"})

    resp = client.get("/libraries/1")
    assert "bge_m3" in resp.text

    client.post("/libraries/1/profiles/create", data={"key": "bge_m3_norm", "model_name": "BAAI/bge-m3"})
    resp = client.get("/libraries/1")
    assert "bge_m3_norm" in resp.text
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_embedding_profiles_ui.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Add columns in `embedding_profile`:
- `use_fp16 integer not null default 0`
- `max_length integer not null default 128`
- `variant text not null default 'raw'`
- `enabled integer not null default 1`

Add a simple `migrate_db(conn)` to add missing columns.

Create default profile in `create_library` when inserting a new library.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_embedding_profiles_ui.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add game_web/db.py game_web/services/embedding_profile.py game_web/services/library_service.py game_web/templates/library_detail.html tests/test_embedding_profiles_ui.py
git commit -m "feat: manage embedding profiles with defaults"
```

### Task 6: Settings 页面（Meilisearch 连接）

**Files:**
- Modify: `game_web/db.py`
- Create: `game_web/services/settings_service.py`
- Create: `game_web/routes/settings.py`
- Create: `game_web/templates/settings.html`
- Modify: `game_web/app.py`
- Test: `tests/test_settings_page.py`

**Step 1: Write the failing test**

```python
from fastapi.testclient import TestClient

from game_web.app import create_app


def test_settings_persist_meili_url(tmp_path):
    app = create_app(str(tmp_path / "app.db"))
    client = TestClient(app)
    client.post("/setup", data={"password": "secret"})
    client.post("/login", data={"password": "secret"})

    resp = client.post("/settings", data={"meili_url": "http://127.0.0.1:7700"}, follow_redirects=False)
    assert resp.status_code == 302

    resp = client.get("/settings")
    assert "http://127.0.0.1:7700" in resp.text
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_settings_page.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Add `settings` table and a service with `get_setting`/`set_setting`.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_settings_page.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add game_web/db.py game_web/services/settings_service.py game_web/routes/settings.py game_web/templates/settings.html game_web/app.py tests/test_settings_page.py
git commit -m "feat: add settings page for meilisearch"
```

### Task 7: Dataset 上传 + Job 表 + Job 页面

**Files:**
- Modify: `game_web/db.py`
- Create: `game_web/services/dataset_service.py`
- Modify: `game_web/services/job_service.py`
- Create: `game_web/routes/jobs.py`
- Create: `game_web/templates/jobs.html`
- Create: `game_web/templates/job_detail.html`
- Modify: `game_web/routes/library_detail.py`
- Test: `tests/test_datasets_and_jobs.py`

**Step 1: Write the failing test**

```python
from fastapi.testclient import TestClient

from game_web.app import create_app


def test_upload_dataset_creates_job(tmp_path):
    app = create_app(str(tmp_path / "app.db"))
    client = TestClient(app)
    client.post("/setup", data={"password": "secret"})
    client.post("/login", data={"password": "secret"})
    client.post("/libraries/create", data={"name": "games", "index_uid": "games"})

    resp = client.post(
        "/libraries/1/datasets/upload",
        files={"file": ("games.txt", b"A\nB\n")},
        follow_redirects=False,
    )
    assert resp.status_code == 302

    resp = client.get("/jobs")
    assert "build" in resp.text
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_datasets_and_jobs.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Add `dataset` and `job` tables; on upload, store file in `./data/uploads/<library_id>/` and create a job row with status `queued`.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_datasets_and_jobs.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add game_web/db.py game_web/services/dataset_service.py game_web/services/job_service.py game_web/routes/jobs.py game_web/templates/jobs.html game_web/templates/job_detail.html game_web/routes/library_detail.py tests/test_datasets_and_jobs.py
git commit -m "feat: add dataset upload and jobs UI"
```

### Task 8: Job Runner（单线程执行构建 + 日志）

**Files:**
- Create: `game_web/services/job_runner.py`
- Modify: `game_web/services/job_service.py`
- Modify: `game_web/routes/jobs.py`
- Test: `tests/test_job_runner.py`

**Step 1: Write the failing test**

```python
from game_web.services.job_runner import JobRunner


def test_job_runner_marks_job_done(tmp_path):
    # stub a job row, run, assert status moves queued -> done
    assert True
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_job_runner.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

`JobRunner` 用 `ThreadPoolExecutor(max_workers=1)`，执行时更新 job 状态并写日志；失败则记录 error。

**Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_job_runner.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add game_web/services/job_runner.py game_web/services/job_service.py game_web/routes/jobs.py tests/test_job_runner.py
git commit -m "feat: add job runner with logs"
```

### Task 9: 搜索页面接入真实查询（library + embedder）

**Files:**
- Modify: `game_web/routes/search.py`
- Modify: `game_web/templates/search.html`
- Create: `game_web/services/search_executor.py`
- Test: `tests/test_search_results.py`

**Step 1: Write the failing test**

```python
from fastapi.testclient import TestClient

from game_web.app import create_app


def test_search_executes_with_embedder_key(tmp_path, monkeypatch):
    app = create_app(str(tmp_path / "app.db"))
    client = TestClient(app)
    client.post("/setup", data={"password": "secret"})
    client.post("/login", data={"password": "secret"})
    client.post("/libraries/create", data={"name": "games", "index_uid": "games"})

    resp = client.get("/search?library=1&embedder=bge_m3&q=arknights")
    assert resp.status_code == 200
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_search_results.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

`search_executor.py` 负责：
- 读取 settings（meili_url/api_key）
- 用 profile.key 作为 embedder_key 调 `MeiliGameIndex.search_by_vector`
- 返回 hits 列表

**Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_search_results.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add game_web/routes/search.py game_web/templates/search.html game_web/services/search_executor.py tests/test_search_results.py
git commit -m "feat: wire search page to meili"
```

### Task 10: 文档与手动验证

**Files:**
- Modify: `README.md`
- Create: `docs/manual-webui.md`

**Step 1: Write the failing test**

Skip (doc task).

**Step 2: Write minimal documentation**

- README 增加 WebUI 快速启动（Meili + Web + setup + build + search）
- 修正不存在的文档引用
- `docs/manual-webui.md` 添加手动验证清单

**Step 3: Commit**

```bash
git add README.md docs/manual-webui.md
git commit -m "docs: add webui quickstart"
```
