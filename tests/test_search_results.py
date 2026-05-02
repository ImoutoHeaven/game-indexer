import sys
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from game_web.app import create_app
from game_web.db import connect_db
from game_web.services import dataset_service, job_service
from game_web.services.library_service import create_library, list_libraries
from game_web.services.search_executor import (
    SearchExecutionError,
    SearchConnectionError,
    SearchModelError,
    SearchNotReadyError,
)
from game_web.services.settings_service import set_setting


class FakeHealthyClient:
    def __init__(self, _url: str, _api_key: str | None):
        pass

    def health(self) -> dict[str, str]:
        return {"status": "available"}


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


def _create_searchable_library(conn, data_dir, *, name: str, index_uid: str) -> int:
    create_library(
        conn,
        name=name,
        index_uid=index_uid,
        description="Primary",
    )
    library_id = list_libraries(conn)[-1]["id"]
    dataset = dataset_service.create_dataset(
        conn,
        data_dir=data_dir,
        library_id=library_id,
        filename=f"{index_uid}.txt",
        content=b"A\n",
        commit=False,
    )
    job_service.create_job(
        conn,
        library_id=library_id,
        dataset_id=int(dataset["id"]),
        job_type="build",
        status="done",
        commit=False,
    )
    return library_id


def test_search_route_uses_active_config_without_embedder_query(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    app.state.data_dir = tmp_path / "data"
    client = TestClient(app)

    conn = connect_db(str(db_path))
    try:
        set_setting(conn, "meili_url", "http://127.0.0.1:7700", commit=False)
        library_id = _create_searchable_library(
            conn,
            app.state.data_dir,
            name="Main Library",
            index_uid="main-index",
        )
        conn.commit()
    finally:
        conn.close()

    _login(client)
    monkeypatch.setattr(
        "game_web.services.meili_health_service.meilisearch.Client",
        FakeHealthyClient,
    )

    called = {}

    def _fake_execute(db_path_value, library_id_value, query_value, limit_value=None, data_dir=None):
        called["args"] = (db_path_value, library_id_value, query_value, limit_value, data_dir)
        return [{"name": "Test Game"}]

    import game_web.routes.search as search_routes

    monkeypatch.setattr(search_routes, "execute_search", _fake_execute, raising=False)

    response = client.get(
        f"/search?library={library_id}&q=zelda",
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert called["args"] == (str(db_path), library_id, "zelda", None, app.state.data_dir)


def test_search_manual_library_id_cannot_bypass_searchable_gating_when_settings_missing(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    app.state.data_dir = tmp_path / "data"
    client = TestClient(app)

    conn = connect_db(str(db_path))
    try:
        library_id = _create_searchable_library(
            conn,
            app.state.data_dir,
            name="Manual Query Library",
            index_uid="manual-index",
        )
        conn.commit()
    finally:
        conn.close()

    _login(client)

    response = client.get(
        f"/search?library={library_id}&q=zelda",
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "Library is not searchable yet" in response.text


def test_search_page_only_lists_searchable_libraries(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    app.state.data_dir = tmp_path / "data"
    client = TestClient(app)

    conn = connect_db(str(db_path))
    try:
        set_setting(conn, "meili_url", "http://127.0.0.1:7700", commit=False)
        _create_searchable_library(
            conn,
            app.state.data_dir,
            name="Main Library",
            index_uid="main-index",
        )
        create_library(
            conn,
            name="Broken Library",
            index_uid="broken-index",
            description="Primary",
        )
        conn.commit()
    finally:
        conn.close()

    _login(client)
    monkeypatch.setattr(
        "game_web.services.meili_health_service.meilisearch.Client",
        FakeHealthyClient,
    )

    response = client.get("/search", follow_redirects=False)

    assert response.status_code == 200
    assert "Main Library" in response.text
    assert "Broken Library" not in response.text


def test_search_shows_library_not_searchable_yet_message(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app)

    conn = connect_db(str(db_path))
    try:
        create_library(
            conn,
            name="Broken Library",
            index_uid="broken-index",
            description="Primary",
        )
        library_id = list_libraries(conn)[0]["id"]
    finally:
        conn.close()

    _login(client)

    def _boom(*args, **kwargs):
        raise SearchNotReadyError("Library is not searchable yet")

    import game_web.routes.search as search_routes

    monkeypatch.setattr(search_routes, "execute_search", _boom, raising=False)

    response = client.get(
        f"/search?library={library_id}&q=zelda",
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "Library is not searchable yet" in response.text


def test_search_shows_last_build_failed_message(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app)

    conn = connect_db(str(db_path))
    try:
        create_library(
            conn,
            name="Broken Library",
            index_uid="broken-index",
            description="Primary",
        )
        library_id = list_libraries(conn)[0]["id"]
    finally:
        conn.close()

    _login(client)

    def _boom(*args, **kwargs):
        raise SearchNotReadyError("Last build failed")

    import game_web.routes.search as search_routes

    monkeypatch.setattr(search_routes, "execute_search", _boom, raising=False)

    response = client.get(
        f"/search?library={library_id}&q=zelda",
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "Last build failed" in response.text


def test_search_shows_meili_connection_failed_message(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app)

    conn = connect_db(str(db_path))
    try:
        create_library(
            conn,
            name="Broken Library",
            index_uid="broken-index",
            description="Primary",
        )
        library_id = list_libraries(conn)[0]["id"]
    finally:
        conn.close()

    _login(client)

    def _boom(*args, **kwargs):
        raise SearchConnectionError("Meili connection failed")

    import game_web.routes.search as search_routes

    monkeypatch.setattr(search_routes, "execute_search", _boom, raising=False)

    response = client.get(
        f"/search?library={library_id}&q=zelda",
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "Meili connection failed" in response.text


def test_search_shows_specific_error_message_when_model_load_fails(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    client = TestClient(app)

    conn = connect_db(str(db_path))
    try:
        create_library(
            conn,
            name="Broken Library",
            index_uid="broken-index",
            description="Primary",
        )
        library_id = list_libraries(conn)[0]["id"]
    finally:
        conn.close()

    _login(client)

    def _boom(*args, **kwargs):
        raise SearchModelError("Model failed to load")

    import game_web.routes.search as search_routes

    monkeypatch.setattr(search_routes, "execute_search", _boom, raising=False)

    response = client.get(
        f"/search?library={library_id}&q=zelda",
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "Model failed to load" in response.text


def test_search_shows_exact_no_hit_message(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    app.state.data_dir = tmp_path / "data"
    client = TestClient(app)

    conn = connect_db(str(db_path))
    try:
        set_setting(conn, "meili_url", "http://127.0.0.1:7700", commit=False)
        library_id = _create_searchable_library(
            conn,
            app.state.data_dir,
            name="Main Library",
            index_uid="main-index",
        )
        conn.commit()
    finally:
        conn.close()

    _login(client)
    monkeypatch.setattr(
        "game_web.services.meili_health_service.meilisearch.Client",
        FakeHealthyClient,
    )

    def _empty(*args, **kwargs):
        return []

    import game_web.routes.search as search_routes

    monkeypatch.setattr(search_routes, "execute_search", _empty, raising=False)

    response = client.get(
        f"/search?library={library_id}&q=zelda",
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "No similar results found" in response.text


def test_search_shows_actionable_error_when_backend_search_fails(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    app.state.data_dir = tmp_path / "data"
    client = TestClient(app)

    conn = connect_db(str(db_path))
    try:
        set_setting(conn, "meili_url", "http://127.0.0.1:7700", commit=False)
        library_id = _create_searchable_library(
            conn,
            app.state.data_dir,
            name="Main Library",
            index_uid="main-index",
        )
        conn.commit()
    finally:
        conn.close()

    _login(client)
    monkeypatch.setattr(
        "game_web.services.meili_health_service.meilisearch.Client",
        FakeHealthyClient,
    )

    def _boom(*args, **kwargs):
        raise SearchExecutionError("Search could not be completed. Check Meilisearch and try again.")

    import game_web.routes.search as search_routes

    monkeypatch.setattr(search_routes, "execute_search", _boom, raising=False)

    response = client.get(
        f"/search?library={library_id}&q=zelda",
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "Search could not be completed. Check Meilisearch and try again." in response.text
    assert "No similar results found" not in response.text


def test_search_shows_actionable_error_when_query_encoding_fails(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    app.state.data_dir = tmp_path / "data"
    client = TestClient(app, raise_server_exceptions=False)

    conn = connect_db(str(db_path))
    try:
        set_setting(conn, "meili_url", "http://127.0.0.1:7700", commit=False)
        library_id = _create_searchable_library(
            conn,
            app.state.data_dir,
            name="Main Library",
            index_uid="main-index",
        )
        conn.commit()
    finally:
        conn.close()

    _login(client)
    monkeypatch.setattr(
        "game_web.services.meili_health_service.meilisearch.Client",
        FakeHealthyClient,
    )

    class ExplodingEmbedder:
        def __init__(self, model_name: str, use_fp16: bool = False):
            self.model_name = model_name
            self.use_fp16 = use_fp16

        def encode_dense(self, texts, batch_size=64, max_length=128):
            raise RuntimeError("encode exploded")

    class FakeIndex:
        def __init__(self, url, api_key, index_uid="games", embedder_name="bge_m3", embedding_dim=1024):
            self.url = url
            self.api_key = api_key
            self.index_uid = index_uid
            self.embedder_name = embedder_name
            self.embedding_dim = embedding_dim

        def search_by_vector(self, query_vec, limit=10, embedder_key=None):
            return [{"name": "Test Game"}]

    monkeypatch.setitem(
        sys.modules,
        "game_semantic.embedding",
        SimpleNamespace(BgeM3Embedder=ExplodingEmbedder),
    )
    monkeypatch.setitem(
        sys.modules,
        "game_semantic.meili_client",
        SimpleNamespace(MeiliGameIndex=FakeIndex),
    )

    response = client.get(
        f"/search?library={library_id}&q=zelda",
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "Search could not be completed. Check Meilisearch and try again." in response.text
    assert "No similar results found" not in response.text


def test_search_shows_actionable_error_when_index_construction_fails(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    app = create_app(str(db_path))
    app.state.data_dir = tmp_path / "data"
    client = TestClient(app, raise_server_exceptions=False)

    conn = connect_db(str(db_path))
    try:
        set_setting(conn, "meili_url", "http://127.0.0.1:7700", commit=False)
        library_id = _create_searchable_library(
            conn,
            app.state.data_dir,
            name="Main Library",
            index_uid="main-index",
        )
        conn.commit()
    finally:
        conn.close()

    _login(client)
    monkeypatch.setattr(
        "game_web.services.meili_health_service.meilisearch.Client",
        FakeHealthyClient,
    )

    class FakeEmbedder:
        def __init__(self, model_name: str, use_fp16: bool = False):
            self.model_name = model_name
            self.use_fp16 = use_fp16

        def encode_dense(self, texts, batch_size=64, max_length=128):
            return [SimpleNamespace(tolist=lambda: [0.1, 0.2, 0.3])]

    class ExplodingIndex:
        def __init__(self, url, api_key, index_uid="games", embedder_name="bge_m3", embedding_dim=1024):
            raise RuntimeError("ctor exploded")

    monkeypatch.setitem(
        sys.modules,
        "game_semantic.embedding",
        SimpleNamespace(BgeM3Embedder=FakeEmbedder),
    )
    monkeypatch.setitem(
        sys.modules,
        "game_semantic.meili_client",
        SimpleNamespace(MeiliGameIndex=ExplodingIndex),
    )

    response = client.get(
        f"/search?library={library_id}&q=zelda",
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "Search could not be completed. Check Meilisearch and try again." in response.text
    assert "No similar results found" not in response.text
