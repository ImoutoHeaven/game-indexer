from game_semantic.meili_client import MeiliGameIndex


class DummyIndex:
    def __init__(self):
        self.last_payload = None

    def search(self, query, payload):
        self.last_payload = payload
        return {"hits": []}


def test_search_payload_uses_embedder_key():
    index = MeiliGameIndex.__new__(MeiliGameIndex)
    index.embedder_name = "default_embedder"
    index.index = DummyIndex()

    index.search_by_vector([0.1, 0.2], embedder_key="custom_embedder")

    assert index.index.last_payload["hybrid"]["embedder"] == "custom_embedder"


def test_extract_results_unknown_shape_returns_empty_list():
    assert MeiliGameIndex._extract_results({"foo": "bar"}) == []
    assert MeiliGameIndex._extract_results(object()) == []


def test_extract_results_wraps_dict_hits():
    data = {"hits": {"id": 1}}
    assert MeiliGameIndex._extract_results(data) == [{"id": 1}]


def test_extract_results_wraps_dict_results():
    data = {"results": {"id": 1}}
    assert MeiliGameIndex._extract_results(data) == [{"id": 1}]


def test_ensure_settings_handles_non_dict_settings():
    class DummyIndex:
        def get_settings(self):
            return "not-a-dict"

        def update_settings(self, updates):
            self.last_updates = updates

    index = MeiliGameIndex.__new__(MeiliGameIndex)
    index.embedder_name = "bge_m3"
    index.embedding_dim = 1024
    index.displayed_attributes = ["id", "name"]
    index.searchable_attributes = ["name"]
    index.index = DummyIndex()

    index.ensure_settings()
    assert "embedders" in index.index.last_updates
    assert "searchableAttributes" in index.index.last_updates
    assert "displayedAttributes" in index.index.last_updates


def test_extract_results_logs_to_dict_errors(caplog):
    class Exploding:
        def dict(self):
            raise RuntimeError("explode")

    with caplog.at_level("DEBUG"):
        assert MeiliGameIndex._extract_results(Exploding()) == []

    assert "to_dict failed" in caplog.text


def test_get_or_create_index_raises_unexpected_errors():
    class DummyIndex:
        def get_stats(self):
            raise RuntimeError("boom")

    class DummyClient:
        def __init__(self):
            self.created = False

        def index(self, uid):
            return DummyIndex()

        def create_index(self, uid, options):
            self.created = True

    index = MeiliGameIndex.__new__(MeiliGameIndex)
    index.client = DummyClient()
    index.index_uid = "games"

    try:
        index._get_or_create_index()
    except RuntimeError as exc:
        assert str(exc) == "boom"
    else:
        raise AssertionError("Expected RuntimeError")
