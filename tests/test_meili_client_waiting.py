import importlib
import sys
from types import SimpleNamespace

import pytest


def _load_meili_client_module(monkeypatch):
    monkeypatch.setitem(sys.modules, "meilisearch", SimpleNamespace(Client=object))
    module = importlib.import_module("game_semantic.meili_client")
    return importlib.reload(module)


def _make_index(meili_client, *, task, client):
    class DummyIndex:
        def add_documents(self, docs):
            assert docs == [{"id": 1, "name": "Test Game"}]
            return task

    index = meili_client.MeiliGameIndex.__new__(meili_client.MeiliGameIndex)
    index.client = client
    index.index = DummyIndex()
    index.index_uid = "games"
    return index


def test_add_documents_wait_propagates_wait_for_task_failures(monkeypatch):
    meili_client = _load_meili_client_module(monkeypatch)

    class DummyClient:
        def __init__(self):
            self.waited_for = []

        def wait_for_task(self, task_uid):
            self.waited_for.append(task_uid)
            raise RuntimeError("task wait failed")

    client = DummyClient()
    index = _make_index(meili_client, task={"taskUid": 7}, client=client)

    with pytest.raises(RuntimeError, match="task wait failed"):
        index.add_documents([{"id": 1, "name": "Test Game"}], wait=True)

    assert client.waited_for == [7]


def test_add_documents_wait_uses_task_uid_from_object_response(monkeypatch):
    meili_client = _load_meili_client_module(monkeypatch)

    class TaskInfo:
        def __init__(self, task_uid):
            self.task_uid = task_uid

    class TerminalTask:
        def __init__(self, status="succeeded"):
            self.status = status

    class DummyClient:
        def __init__(self):
            self.waited_for = []

        def wait_for_task(self, task_uid):
            self.waited_for.append(task_uid)
            return TerminalTask(status="succeeded")

    client = DummyClient()
    index = _make_index(meili_client, task=TaskInfo(11), client=client)

    index.add_documents([{"id": 1, "name": "Test Game"}], wait=True)

    assert client.waited_for == [11]


def test_add_documents_wait_raises_on_failed_terminal_task(monkeypatch):
    meili_client = _load_meili_client_module(monkeypatch)

    class TaskInfo:
        def __init__(self, task_uid):
            self.task_uid = task_uid

    class TerminalTask:
        def __init__(self, status, error=None):
            self.status = status
            self.error = error

    class DummyClient:
        def wait_for_task(self, task_uid):
            assert task_uid == 12
            return TerminalTask(status="failed", error={"message": "vector indexing exploded"})

    index = _make_index(meili_client, task=TaskInfo(12), client=DummyClient())

    with pytest.raises(RuntimeError, match="vector indexing exploded"):
        index.add_documents([{"id": 1, "name": "Test Game"}], wait=True)
