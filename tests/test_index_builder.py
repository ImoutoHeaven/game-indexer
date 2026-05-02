import importlib
import sys
from types import SimpleNamespace

import numpy as np


def _install_fake_flag_embedding(monkeypatch):
    class FakeFlagModel:
        def __init__(self, model_name, use_fp16=False):
            self.model_name = model_name
            self.use_fp16 = use_fp16

        def encode(self, texts, batch_size=64, max_length=128, **_kwargs):
            return {"dense_vecs": [[0.0] * 1024 for _ in texts]}

    monkeypatch.setitem(sys.modules, "FlagEmbedding", SimpleNamespace(BGEM3FlagModel=FakeFlagModel))


def _install_fake_meilisearch(monkeypatch):
    monkeypatch.setitem(sys.modules, "meilisearch", SimpleNamespace(Client=object))


def test_build_index_uses_config_embedding_max_length(monkeypatch, tmp_path):
    _install_fake_flag_embedding(monkeypatch)
    _install_fake_meilisearch(monkeypatch)
    from game_semantic.config import Config

    index_builder = importlib.import_module("game_semantic.index_builder")
    index_builder = importlib.reload(index_builder)

    captured = {}

    class FakeIndex:
        def __init__(self, **_kwargs):
            pass

        def delete_index(self):
            return None

        def ensure_settings(self):
            return None

        def add_documents(self, docs, wait=False):
            captured["docs"] = docs
            captured["wait"] = wait

    class FakeEmbedder:
        def encode_dense(self, texts, batch_size=64, max_length=128):
            captured["texts"] = texts
            captured["batch_size"] = batch_size
            captured["max_length"] = max_length
            return np.array([[1.0, 2.0, 3.0]], dtype=np.float32)

    monkeypatch.setattr(index_builder, "MeiliGameIndex", FakeIndex)
    monkeypatch.setattr(index_builder, "get_cached_bge_m3", lambda model_name, use_fp16: FakeEmbedder())

    txt_path = tmp_path / "games.txt"
    txt_path.write_text("Test Game\n", encoding="utf-8")

    config = Config(
        meili_url="http://127.0.0.1:7700",
        meili_api_key="masterKey",
        meili_index_uid="games",
        txt_path=str(txt_path),
        embedding_max_length=256,
    )

    index_builder.build_index(config)

    assert captured["max_length"] == 256
    assert captured["wait"] is True
