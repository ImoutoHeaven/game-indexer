import pytest
import sys
from types import SimpleNamespace

from game_web.db import connect_db, init_db
from game_web.services import dataset_service, job_service, library_service
from game_web.services.search_executor import SearchExecutionError, SearchNotReadyError, execute_search
from game_web.services.settings_service import set_setting


class FakeHealthyClient:
    def __init__(self, _url: str, _api_key: str | None):
        pass

    def health(self) -> dict[str, str]:
        return {"status": "available"}


def test_execute_search_uses_canonical_active_profile_fields(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    data_dir = tmp_path / "data"
    init_db(str(db_path))
    conn = connect_db(str(db_path))
    try:
        set_setting(conn, "meili_url", "http://127.0.0.1:7700", commit=False)
        library_service.create_library(
            conn,
            name="Main Library",
            index_uid="main-index",
            description="Primary games library",
        )
        dataset = dataset_service.create_dataset(
            conn,
            data_dir=data_dir,
            library_id=1,
            filename="games.txt",
            content=b"A\n",
            commit=False,
        )
        job_service.create_job(
            conn,
            library_id=1,
            dataset_id=int(dataset["id"]),
            job_type="build",
            status="done",
            commit=False,
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setattr(
        "game_web.services.meili_health_service.meilisearch.Client",
        FakeHealthyClient,
    )

    captured = {}

    class FakeEmbedder:
        def __init__(self, model_name: str, use_fp16: bool = False):
            captured["model_name"] = model_name
            captured["use_fp16"] = use_fp16

        def encode_dense(self, texts, batch_size=64, max_length=128):
            captured["max_length"] = max_length
            return [SimpleNamespace(tolist=lambda: [0.1, 0.2, 0.3])]

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
        SimpleNamespace(BgeM3Embedder=FakeEmbedder),
    )
    monkeypatch.setitem(
        sys.modules,
        "game_semantic.meili_client",
        SimpleNamespace(MeiliGameIndex=FakeIndex),
    )

    results = execute_search(str(db_path), 1, "zelda")

    assert results == [{"name": "Test Game"}]
    assert captured["model_name"] == "BAAI/bge-m3"
    assert captured["use_fp16"] is False
    assert captured["max_length"] == 128


def test_execute_search_does_not_fallback_to_cli_settings_when_web_settings_missing(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    data_dir = tmp_path / "data"
    init_db(str(db_path))
    conn = connect_db(str(db_path))
    try:
        library_service.create_library(
            conn,
            name="Main Library",
            index_uid="main-index",
            description="Primary games library",
        )
        dataset = dataset_service.create_dataset(
            conn,
            data_dir=data_dir,
            library_id=1,
            filename="games.txt",
            content=b"A\n",
            commit=False,
        )
        job_service.create_job(
            conn,
            library_id=1,
            dataset_id=int(dataset["id"]),
            job_type="build",
            status="done",
            commit=False,
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setattr(
        "game_web.services.meili_health_service.meilisearch.Client",
        FakeHealthyClient,
    )
    monkeypatch.setitem(
        sys.modules,
        "game_semantic.embedding",
        SimpleNamespace(BgeM3Embedder=object),
    )
    monkeypatch.setitem(
        sys.modules,
        "game_semantic.meili_client",
        SimpleNamespace(MeiliGameIndex=object),
    )

    with pytest.raises(SearchNotReadyError, match="Library is not searchable yet"):
        execute_search(str(db_path), 1, "zelda")


def test_execute_search_uses_app_configured_data_dir_for_saved_api_key(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    data_dir = tmp_path / "custom-data"
    init_db(str(db_path))
    conn = connect_db(str(db_path))
    try:
        set_setting(conn, "meili_url", "http://127.0.0.1:7700", commit=False)
        set_setting(
            conn,
            "meili_api_key",
            __import__("game_web.secrets", fromlist=["encrypt_secret"]).encrypt_secret(data_dir, "savedKey"),
            commit=False,
        )
        library_service.create_library(
            conn,
            name="Main Library",
            index_uid="main-index",
            description="Primary games library",
        )
        dataset = dataset_service.create_dataset(
            conn,
            data_dir=data_dir,
            library_id=1,
            filename="games.txt",
            content=b"A\n",
            commit=False,
        )
        job_service.create_job(
            conn,
            library_id=1,
            dataset_id=int(dataset["id"]),
            job_type="build",
            status="done",
            commit=False,
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setattr(
        "game_web.services.meili_health_service.meilisearch.Client",
        FakeHealthyClient,
    )

    captured = {}

    class FakeEmbedder:
        def __init__(self, model_name: str, use_fp16: bool = False):
            self.model_name = model_name
            self.use_fp16 = use_fp16

        def encode_dense(self, texts, batch_size=64, max_length=128):
            return [SimpleNamespace(tolist=lambda: [0.1, 0.2, 0.3])]

    class FakeIndex:
        def __init__(self, url, api_key, index_uid="games", embedder_name="bge_m3", embedding_dim=1024):
            captured["api_key"] = api_key

        def search_by_vector(self, query_vec, limit=10, embedder_key=None):
            return [{"name": "Test Game"}]

    monkeypatch.setitem(
        sys.modules,
        "game_semantic.embedding",
        SimpleNamespace(BgeM3Embedder=FakeEmbedder),
    )
    monkeypatch.setitem(
        sys.modules,
        "game_semantic.meili_client",
        SimpleNamespace(MeiliGameIndex=FakeIndex),
    )

    results = execute_search(str(db_path), 1, "zelda", data_dir=data_dir)

    assert results == [{"name": "Test Game"}]
    assert captured["api_key"] == "savedKey"


def test_execute_search_raises_actionable_error_when_vector_search_fails(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    data_dir = tmp_path / "data"
    init_db(str(db_path))
    conn = connect_db(str(db_path))
    try:
        set_setting(conn, "meili_url", "http://127.0.0.1:7700", commit=False)
        library_service.create_library(
            conn,
            name="Main Library",
            index_uid="main-index",
            description="Primary games library",
        )
        dataset = dataset_service.create_dataset(
            conn,
            data_dir=data_dir,
            library_id=1,
            filename="games.txt",
            content=b"A\n",
            commit=False,
        )
        job_service.create_job(
            conn,
            library_id=1,
            dataset_id=int(dataset["id"]),
            job_type="build",
            status="done",
            commit=False,
        )
        conn.commit()
    finally:
        conn.close()

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
            self.url = url
            self.api_key = api_key
            self.index_uid = index_uid
            self.embedder_name = embedder_name
            self.embedding_dim = embedding_dim

        def search_by_vector(self, query_vec, limit=10, embedder_key=None):
            raise RuntimeError("meili query exploded")

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

    with pytest.raises(
        SearchExecutionError,
        match="Search could not be completed. Check Meilisearch and try again.",
    ):
        execute_search(str(db_path), 1, "zelda")


def test_execute_search_raises_actionable_error_when_query_encoding_fails(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    data_dir = tmp_path / "data"
    init_db(str(db_path))
    conn = connect_db(str(db_path))
    try:
        set_setting(conn, "meili_url", "http://127.0.0.1:7700", commit=False)
        library_service.create_library(
            conn,
            name="Main Library",
            index_uid="main-index",
            description="Primary games library",
        )
        dataset = dataset_service.create_dataset(
            conn,
            data_dir=data_dir,
            library_id=1,
            filename="games.txt",
            content=b"A\n",
            commit=False,
        )
        job_service.create_job(
            conn,
            library_id=1,
            dataset_id=int(dataset["id"]),
            job_type="build",
            status="done",
            commit=False,
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setattr(
        "game_web.services.meili_health_service.meilisearch.Client",
        FakeHealthyClient,
    )

    class FakeEmbedder:
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
        SimpleNamespace(BgeM3Embedder=FakeEmbedder),
    )
    monkeypatch.setitem(
        sys.modules,
        "game_semantic.meili_client",
        SimpleNamespace(MeiliGameIndex=FakeIndex),
    )

    with pytest.raises(
        SearchExecutionError,
        match="Search could not be completed. Check Meilisearch and try again.",
    ):
        execute_search(str(db_path), 1, "zelda")


def test_execute_search_raises_actionable_error_when_index_construction_fails(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    data_dir = tmp_path / "data"
    init_db(str(db_path))
    conn = connect_db(str(db_path))
    try:
        set_setting(conn, "meili_url", "http://127.0.0.1:7700", commit=False)
        library_service.create_library(
            conn,
            name="Main Library",
            index_uid="main-index",
            description="Primary games library",
        )
        dataset = dataset_service.create_dataset(
            conn,
            data_dir=data_dir,
            library_id=1,
            filename="games.txt",
            content=b"A\n",
            commit=False,
        )
        job_service.create_job(
            conn,
            library_id=1,
            dataset_id=int(dataset["id"]),
            job_type="build",
            status="done",
            commit=False,
        )
        conn.commit()
    finally:
        conn.close()

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

    with pytest.raises(
        SearchExecutionError,
        match="Search could not be completed. Check Meilisearch and try again.",
    ):
        execute_search(str(db_path), 1, "zelda")
