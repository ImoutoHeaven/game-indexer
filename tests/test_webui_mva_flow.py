from pathlib import Path

from fastapi.testclient import TestClient

from game_web.app import create_app
from game_web.db import connect_db


class FakeHealthyClient:
    def __init__(self, _url: str, _api_key: str | None):
        pass

    def health(self) -> dict[str, str]:
        return {"status": "available"}


class ImmediateThread:
    def __init__(self, target, daemon: bool = True):
        self._target = target
        self.daemon = daemon

    def start(self) -> None:
        try:
            self._target()
        except Exception:
            # Match the route's fire-and-forget threading model without failing the request.
            pass


class FakeVector(list[float]):
    def tolist(self) -> list[float]:
        return list(self)


class FakeEmbedder:
    def __init__(self, model_name: str = "BAAI/bge-m3", use_fp16: bool = False):
        self.model_name = model_name
        self.use_fp16 = use_fp16

    def encode_dense(self, texts, batch_size: int = 64, max_length: int = 128):
        if not texts:
            return []
        return [FakeVector([float(max_length), float(batch_size), 1.0])]


def _csrf_token(client: TestClient) -> str:
    token = client.cookies.get("csrf_token")
    assert token
    return token


def _login(client: TestClient) -> None:
    response = client.get("/setup", follow_redirects=False)
    assert response.status_code == 200
    response = client.post(
        "/setup",
        data={"password": "secret123", "csrf_token": _csrf_token(client)},
        follow_redirects=False,
    )
    assert response.status_code == 302
    response = client.get("/login", follow_redirects=False)
    assert response.status_code == 200
    response = client.post(
        "/login",
        data={"password": "secret123", "csrf_token": _csrf_token(client)},
        follow_redirects=False,
    )
    assert response.status_code == 302


def _latest_job_id(db_path: Path) -> int:
    conn = connect_db(str(db_path))
    try:
        row = conn.execute("select max(id) from job").fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[0] is not None
    return int(row[0])


def _library_id_for_name(db_path: Path, name: str) -> int:
    conn = connect_db(str(db_path))
    try:
        row = conn.execute("select id from library where name = ?", (name,)).fetchone()
    finally:
        conn.close()
    assert row is not None
    return int(row[0])


def test_admin_can_configure_create_upload_run_and_search(monkeypatch, tmp_path):
    db_path = tmp_path / "app.db"
    data_dir = tmp_path / "data"
    app = create_app(str(db_path), data_dir=data_dir)
    client = TestClient(app, raise_server_exceptions=False)
    fake_indexes: dict[str, list[dict[str, object]]] = {}
    build_calls: list[object] = []

    def _fake_build_index(config):
        build_calls.append(config)
        with open(config.txt_path, "r", encoding="utf-8") as handle:
            names = [line.strip() for line in handle if line.strip()]
        fake_indexes[config.meili_index_uid] = [
            {"id": index + 1, "name": name}
            for index, name in enumerate(names)
        ]

    class FakeMeiliGameIndex:
        def __init__(
            self,
            url: str,
            api_key: str,
            index_uid: str = "games",
            embedder_name: str = "bge_m3",
            embedding_dim: int = 1024,
            displayed_attributes=None,
            searchable_attributes=None,
        ):
            self.url = url
            self.api_key = api_key
            self.index_uid = index_uid
            self.embedder_name = embedder_name
            self.embedding_dim = embedding_dim

        def search_by_vector(self, query_vector, limit: int = 10, embedder_key: str | None = None):
            return fake_indexes.get(self.index_uid, [])[:limit]

    monkeypatch.setattr(
        "game_web.services.meili_health_service.meilisearch.Client",
        FakeHealthyClient,
    )
    monkeypatch.setattr("game_web.routes.jobs.Thread", ImmediateThread)
    monkeypatch.setattr(
        "game_web.services.build_execution_service.build_index",
        _fake_build_index,
    )
    monkeypatch.setattr("game_semantic.embedding.BgeM3Embedder", FakeEmbedder)
    monkeypatch.setattr("game_semantic.meili_client.MeiliGameIndex", FakeMeiliGameIndex)

    _login(client)

    response = client.post(
        "/settings",
        data={
            "meili_url": "http://127.0.0.1:7700",
            "meili_api_key": "masterKey",
            "csrf_token": _csrf_token(client),
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert response.request.url.path == "/settings"
    assert "Saved and connected" in response.text

    response = client.post(
        "/libraries/create",
        data={
            "name": "Primary Library",
            "index_uid": "primary-index",
            "description": "Main games library",
            "csrf_token": _csrf_token(client),
        },
        follow_redirects=True,
    )
    library_id = _library_id_for_name(db_path, "Primary Library")

    assert response.status_code == 200
    assert response.request.url.path == "/libraries"
    assert "Library created" in response.text

    response = client.get("/search", follow_redirects=False)

    assert response.status_code == 200
    assert "Primary Library" not in response.text

    response = client.post(
        f"/libraries/{library_id}/datasets/upload",
        data={"csrf_token": _csrf_token(client)},
        files={"file": ("games.txt", b"Test Game\nAnother Game\n")},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert response.request.url.path == f"/libraries/{library_id}"
    assert "Build job queued" in response.text
    assert "Recent Build" in response.text
    assert "queued" in response.text

    response = client.get("/search", follow_redirects=False)

    assert response.status_code == 200
    assert "Primary Library" not in response.text

    response = client.post(
        "/jobs/run",
        data={
            "csrf_token": _csrf_token(client),
            "return_to": f"/libraries/{library_id}",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert response.request.url.path == f"/libraries/{library_id}"
    assert "Build started" in response.text
    assert build_calls
    build_config = build_calls[0]
    assert build_config.meili_url == "http://127.0.0.1:7700"
    assert build_config.meili_api_key == "masterKey"
    assert build_config.meili_index_uid == "primary-index"
    assert build_config.mode == "rebuild"
    assert build_config.bge_model_name == "BAAI/bge-m3"
    assert build_config.bge_use_fp16 is False
    assert build_config.embedding_max_length == 128

    response = client.get("/search", follow_redirects=False)

    assert response.status_code == 200
    assert "Primary Library" in response.text

    response = client.get(
        f"/search?library={library_id}&q=test+game",
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "Test Game" in response.text


def test_failed_build_keeps_library_out_of_search_and_surfaces_job_error(monkeypatch, tmp_path):
    db_path = tmp_path / "app.db"
    data_dir = tmp_path / "data"
    app = create_app(str(db_path), data_dir=data_dir)
    client = TestClient(app, raise_server_exceptions=False)

    def _failing_build_index(config):
        raise RuntimeError("build exploded")

    monkeypatch.setattr(
        "game_web.services.meili_health_service.meilisearch.Client",
        FakeHealthyClient,
    )
    monkeypatch.setattr("game_web.routes.jobs.Thread", ImmediateThread)
    monkeypatch.setattr(
        "game_web.services.build_execution_service.build_index",
        _failing_build_index,
    )

    _login(client)

    response = client.post(
        "/settings",
        data={
            "meili_url": "http://127.0.0.1:7700",
            "meili_api_key": "masterKey",
            "csrf_token": _csrf_token(client),
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Saved and connected" in response.text

    response = client.post(
        "/libraries/create",
        data={
            "name": "Broken Library",
            "index_uid": "broken-index",
            "description": "Broken games library",
            "csrf_token": _csrf_token(client),
        },
        follow_redirects=True,
    )
    library_id = _library_id_for_name(db_path, "Broken Library")

    assert response.status_code == 200
    assert "Library created" in response.text

    response = client.post(
        f"/libraries/{library_id}/datasets/upload",
        data={"csrf_token": _csrf_token(client)},
        files={"file": ("games.txt", b"Broken Game\n")},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert response.request.url.path == f"/libraries/{library_id}"
    assert "Build job queued" in response.text

    response = client.post(
        "/jobs/run",
        data={
            "csrf_token": _csrf_token(client),
            "return_to": f"/libraries/{library_id}",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert response.request.url.path == f"/libraries/{library_id}"
    assert "Build started" in response.text

    response = client.get("/search", follow_redirects=False)

    assert response.status_code == 200
    assert "Broken Library" not in response.text

    response = client.get(
        f"/search?library={library_id}&q=broken",
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "Last build failed" in response.text

    job_id = _latest_job_id(db_path)
    response = client.get(f"/jobs/{job_id}", follow_redirects=False)

    assert response.status_code == 200
    assert "build exploded" in response.text
