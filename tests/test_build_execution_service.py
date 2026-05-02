import importlib
import sys
from types import SimpleNamespace

from game_web.db import connect_db, init_db
from game_web.secrets import encrypt_secret
from game_web.services import dataset_service, job_service, library_service
from game_web.services.settings_service import set_setting


def _install_fake_flag_embedding(monkeypatch):
    class FakeFlagModel:
        def __init__(self, model_name, use_fp16=False):
            self.model_name = model_name
            self.use_fp16 = use_fp16

        def encode(self, texts, batch_size=64, max_length=128, **_kwargs):
            return {"dense_vecs": [[0.0] * 1024 for _ in texts]}

    monkeypatch.setitem(sys.modules, "FlagEmbedding", SimpleNamespace(BGEM3FlagModel=FakeFlagModel))


def test_execute_build_job_uses_job_dataset_and_active_profile(monkeypatch, tmp_path):
    _install_fake_flag_embedding(monkeypatch)
    from game_web.services.build_execution_service import execute_build_job

    db_path = tmp_path / "app.db"
    data_dir = tmp_path / "data"
    init_db(str(db_path))
    conn = connect_db(str(db_path))
    try:
        library_service.create_library(
            conn,
            name="Primary Library",
            index_uid="primary-index",
            description="Main games library",
        )
        job_dataset = dataset_service.create_dataset(
            conn,
            data_dir=data_dir,
            library_id=1,
            filename="games.txt",
            content=b"A\n",
        )
        dataset_service.create_dataset(
            conn,
            data_dir=data_dir,
            library_id=1,
            filename="newer-games.txt",
            content=b"B\n",
        )
        job_id = job_service.create_job(
            conn,
            library_id=1,
            dataset_id=int(job_dataset["id"]),
            job_type="build",
            status="queued",
        )
        set_setting(conn, "meili_url", "http://127.0.0.1:7700", commit=False)
        set_setting(
            conn,
            "meili_api_key",
            encrypt_secret(data_dir, "masterKey"),
            commit=False,
        )
        conn.commit()
        job = job_service.get_job(conn, job_id)
    finally:
        conn.close()

    assert job is not None

    captured = {}

    def _build_index(config):
        captured["meili_url"] = config.meili_url
        captured["meili_api_key"] = config.meili_api_key
        captured["txt_path"] = config.txt_path
        captured["meili_index_uid"] = config.meili_index_uid
        captured["mode"] = config.mode
        captured["bge_model_name"] = config.bge_model_name
        captured["bge_use_fp16"] = config.bge_use_fp16
        captured["embedding_max_length"] = config.embedding_max_length

    monkeypatch.setattr("game_web.services.build_execution_service.build_index", _build_index)

    log_lines = []
    execute_build_job(db_path=str(db_path), data_dir=data_dir, job=job, log=log_lines.append)

    assert captured["meili_url"] == "http://127.0.0.1:7700"
    assert captured["meili_api_key"] == "masterKey"
    assert captured["txt_path"].endswith("games.txt")
    assert captured["meili_index_uid"] == "primary-index"
    assert captured["mode"] == "rebuild"
    assert captured["bge_model_name"] == "BAAI/bge-m3"
    assert captured["bge_use_fp16"] is False
    assert captured["embedding_max_length"] == 128


def test_execute_build_job_allows_url_only_meili_configuration(monkeypatch, tmp_path):
    _install_fake_flag_embedding(monkeypatch)
    from game_web.services.build_execution_service import execute_build_job
    from game_web.services.meili_health_service import get_meili_health

    class FakeHealthyClient:
        def __init__(self, _url: str, _api_key: str | None):
            pass

        def health(self) -> dict[str, str]:
            return {"status": "available"}

    monkeypatch.setattr(
        "game_web.services.meili_health_service.meilisearch.Client",
        FakeHealthyClient,
    )

    health = get_meili_health("http://127.0.0.1:7700", None)
    assert health.state == "reachable"

    db_path = tmp_path / "app.db"
    data_dir = tmp_path / "data"
    init_db(str(db_path))
    conn = connect_db(str(db_path))
    try:
        library_service.create_library(
            conn,
            name="Primary Library",
            index_uid="primary-index",
            description="Main games library",
        )
        job_dataset = dataset_service.create_dataset(
            conn,
            data_dir=data_dir,
            library_id=1,
            filename="games.txt",
            content=b"A\n",
        )
        job_id = job_service.create_job(
            conn,
            library_id=1,
            dataset_id=int(job_dataset["id"]),
            job_type="build",
            status="queued",
        )
        set_setting(conn, "meili_url", "http://127.0.0.1:7700", commit=False)
        conn.commit()
        job = job_service.get_job(conn, job_id)
    finally:
        conn.close()

    assert job is not None

    captured = {}

    def _build_index(config):
        captured["meili_url"] = config.meili_url
        captured["meili_api_key"] = config.meili_api_key

    monkeypatch.setattr("game_web.services.build_execution_service.build_index", _build_index)

    execute_build_job(db_path=str(db_path), data_dir=data_dir, job=job, log=lambda _message: None)

    assert captured["meili_url"] == "http://127.0.0.1:7700"
    assert captured["meili_api_key"] == ""


def test_get_cached_bge_m3_reuses_same_instance(monkeypatch):
    _install_fake_flag_embedding(monkeypatch)
    embedding = importlib.import_module("game_semantic.embedding")
    embedding = importlib.reload(embedding)
    created = []

    class FakeModel:
        def __init__(self, model_name, use_fp16=False):
            created.append((model_name, use_fp16))

    monkeypatch.setattr("game_semantic.embedding.BGEM3FlagModel", FakeModel)
    embedding.get_cached_bge_m3.cache_clear()

    first = embedding.get_cached_bge_m3("BAAI/bge-m3", False)
    second = embedding.get_cached_bge_m3("BAAI/bge-m3", False)

    assert first is second
    assert created == [("BAAI/bge-m3", False)]

    embedding.get_cached_bge_m3.cache_clear()
