from dataclasses import dataclass
from types import SimpleNamespace
from typing import Literal

try:
    import meilisearch as _meilisearch
except ModuleNotFoundError:
    class _MissingClient:
        def __init__(self, *_args, **_kwargs):
            raise ModuleNotFoundError("meilisearch")

    meilisearch = SimpleNamespace(Client=_MissingClient)
else:
    meilisearch = _meilisearch


@dataclass(frozen=True)
class MeiliHealthResult:
    state: Literal["not_configured", "reachable", "connection_failed"]
    message: str


def get_meili_health(meili_url: str, meili_api_key: str | None) -> MeiliHealthResult:
    """Return the deterministic Meili health state for the submitted settings."""
    url = meili_url.strip()
    if not url:
        return MeiliHealthResult(
            state="not_configured",
            message="Meilisearch is not configured.",
        )

    try:
        client = meilisearch.Client(url, meili_api_key)
        client.health()
    except Exception:
        return MeiliHealthResult(
            state="connection_failed",
            message="Could not connect to Meilisearch.",
        )

    return MeiliHealthResult(
        state="reachable",
        message="Connected to Meilisearch.",
    )
