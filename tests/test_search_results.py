from fastapi.testclient import TestClient
import pytest
import sys
from types import SimpleNamespace

from game_web.app import create_app
from game_web.db import connect_db
from game_web.services.embedding_profile import add_profile
from game_web.services.library_service import create_library, list_libraries
from game_web.services.search_executor import execute_search


def _csrf_token(client: TestClient) -> str:
    token = client.cookies.get("csrf_token")
    assert token
    return token


def _login(client: TestClient) -> None:
    response = client.get("/setup", follow_redirects=False)
    assert response.status_code == 200
    csrf_token = _csrf_token(client)
    response = client.post(
        "/setup",
        data={"password": "secret123", "csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert response.status_code == 302
    response = client.get("/login", follow_redirects=False)
    assert response.status_code == 200
    csrf_token = _csrf_token(client)
    response = client.post(
        "/login",
        data={"password": "secret123", "csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert response.status_code == 302


def test_search_executes_query_for_library_and_embedder(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app)

    conn = connect_db(str(db_path))
    try:
        create_library(
            conn,
            name="Main Library",
            index_uid="main-index",
            description="Primary",
        )
        library_id = list_libraries(conn)[0]["id"]
        add_profile(conn, library_id=library_id, key="v_name", model_name="BAAI/bge-m3")
    finally:
        conn.close()

    _login(client)

    called = {}

    def _fake_execute(db_path_value, library_id_value, embedder_key_value, query_value, limit_value=None):
        called["args"] = (
            db_path_value,
            library_id_value,
            embedder_key_value,
            query_value,
            limit_value,
        )
        return [{"name": "Test Game"}]

    import game_web.routes.search as search_routes

    monkeypatch.setattr(search_routes, "execute_search", _fake_execute, raising=False)

    response = client.get(
        f"/search?library={library_id}&embedder=v_name&q=zelda",
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert called["args"][1:] == (library_id, "v_name", "zelda", None)


def test_search_shows_error_when_executor_fails(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app)

    conn = connect_db(str(db_path))
    try:
        create_library(
            conn,
            name="Main Library",
            index_uid="main-index",
            description="Primary",
        )
        library_id = list_libraries(conn)[0]["id"]
        add_profile(conn, library_id=library_id, key="v_name", model_name="BAAI/bge-m3")
    finally:
        conn.close()

    _login(client)

    def _boom(*args, **kwargs):
        raise RuntimeError("kaboom")

    import game_web.routes.search as search_routes

    monkeypatch.setattr(search_routes, "execute_search", _boom, raising=False)

    response = client.get(
        f"/search?library={library_id}&embedder=v_name&q=zelda",
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "Search failed" in response.text


def test_search_shows_no_results_message(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app)

    conn = connect_db(str(db_path))
    try:
        create_library(
            conn,
            name="Main Library",
            index_uid="main-index",
            description="Primary",
        )
        library_id = list_libraries(conn)[0]["id"]
        add_profile(conn, library_id=library_id, key="v_name", model_name="BAAI/bge-m3")
    finally:
        conn.close()

    _login(client)

    def _empty(*args, **kwargs):
        return []

    import game_web.routes.search as search_routes

    monkeypatch.setattr(search_routes, "execute_search", _empty, raising=False)

    response = client.get(
        f"/search?library={library_id}&embedder=v_name&q=zelda",
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "No results" in response.text


def test_search_ignores_empty_library_and_embedder(tmp_path):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app)

    _login(client)

    response = client.get(
        "/search?library=&embedder=&q=zelda",
        follow_redirects=False,
    )

    assert response.status_code == 200


def test_execute_search_raises_when_embedder_fails(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))

    conn = connect_db(str(db_path))
    try:
        create_library(
            conn,
            name="Main Library",
            index_uid="main-index",
            description="Primary",
        )
        library_id = list_libraries(conn)[0]["id"]
        add_profile(conn, library_id=library_id, key="v_name", model_name="BAAI/bge-m3")
    finally:
        conn.close()

    class BoomEmbedder:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("embedder down")

    monkeypatch.setitem(
        sys.modules,
        "game_semantic.embedding",
        SimpleNamespace(BgeM3Embedder=BoomEmbedder),
    )

    with pytest.raises(RuntimeError, match="embedder down"):
        execute_search(str(db_path), library_id, "v_name", "zelda")
