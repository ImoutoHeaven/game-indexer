from game_web.services.meili_health_service import get_meili_health


class FakeHealthyClient:
    def __init__(self, _url: str, _api_key: str | None):
        pass

    def health(self) -> dict[str, str]:
        return {"status": "available"}


class FakeBrokenClient:
    def __init__(self, _url: str, _api_key: str | None):
        pass

    def health(self) -> dict[str, str]:
        raise RuntimeError("boom")


def test_get_meili_health_returns_not_configured_without_url():
    result = get_meili_health(meili_url="", meili_api_key=None)

    assert result.state == "not_configured"
    assert result.message


def test_get_meili_health_returns_reachable_when_client_health_succeeds(monkeypatch):
    monkeypatch.setattr(
        "game_web.services.meili_health_service.meilisearch.Client",
        FakeHealthyClient,
    )

    result = get_meili_health(
        meili_url="http://127.0.0.1:7700",
        meili_api_key="masterKey",
    )

    assert result.state == "reachable"
    assert result.message


def test_get_meili_health_returns_connection_failed_on_client_error(monkeypatch):
    monkeypatch.setattr(
        "game_web.services.meili_health_service.meilisearch.Client",
        FakeBrokenClient,
    )

    result = get_meili_health(
        meili_url="http://127.0.0.1:7700",
        meili_api_key="masterKey",
    )

    assert result.state == "connection_failed"
    assert result.message
