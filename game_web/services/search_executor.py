from game_web.db import connect_db
from game_web.runtime import resolve_data_dir
from game_web.secrets import decrypt_secret
from game_web.services.embedding_profile import get_active_profile
from game_web.services.job_service import get_latest_dataset_for_library, get_latest_relevant_build_job
from game_web.services.library_service import list_libraries
from game_web.services.library_status import derive_library_status
from game_web.services.meili_health_service import get_meili_health
from game_web.services.settings_service import get_setting


class SearchNotReadyError(RuntimeError):
    """Raised when a library is outside the Searchable readiness state."""


class SearchConnectionError(RuntimeError):
    """Raised when Meilisearch connectivity prevents a truthful query."""


class SearchModelError(RuntimeError):
    """Raised when the configured model cannot be loaded for query embedding."""


class SearchExecutionError(RuntimeError):
    """Raised when a search request cannot complete truthfully."""


def _as_int(value, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed:
            return default
        try:
            return int(trimmed)
        except ValueError:
            return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def execute_search(
    db_path: str,
    library_id: int,
    query: str,
    limit: int | None = None,
    *,
    data_dir=None,
) -> list[dict]:
    if not query:
        return []

    conn = connect_db(db_path)
    try:
        libraries = list_libraries(conn)
        library = next((item for item in libraries if item["id"] == library_id), None)
        if library is None:
            return []
        profile = get_active_profile(conn, library_id)
        latest_dataset = get_latest_dataset_for_library(conn, library_id)
        latest_job = get_latest_relevant_build_job(conn, library_id)
        meili_url = (get_setting(conn, "meili_url") or "").strip()
        api_key_value = get_setting(conn, "meili_api_key")
    finally:
        conn.close()

    meili_api_key = None
    if api_key_value:
        resolved_data_dir = resolve_data_dir(data_dir, db_path)
        decrypted = decrypt_secret(resolved_data_dir, api_key_value)
        if decrypted:
            meili_api_key = decrypted

    meili_health = get_meili_health(meili_url, meili_api_key)
    status = derive_library_status(
        meili_state=meili_health.state,
        has_dataset=latest_dataset is not None,
        config_valid=bool(str(profile.get("model_name", "")).strip())
        and _as_int(profile.get("use_fp16", 0), -1) in (0, 1)
        and _as_int(profile.get("max_length", 0), 0) > 0,
        latest_relevant_job_status=latest_job["status"] if latest_job else None,
    )
    if meili_health.state == "connection_failed":
        raise SearchConnectionError("Meili connection failed")
    if status.state == "Failed" and latest_job is not None and latest_job.get("status") == "failed":
        raise SearchNotReadyError("Last build failed")
    if status.state != "Searchable":
        raise SearchNotReadyError("Library is not searchable yet")

    from game_semantic.embedding import BgeM3Embedder
    from game_semantic.meili_client import MeiliGameIndex

    use_fp16 = _as_int(profile.get("use_fp16", 0), 0)
    max_length = _as_int(profile.get("max_length", 128), 128)

    try:
        embedder = BgeM3Embedder(
            model_name=profile["model_name"],
            use_fp16=bool(use_fp16),
        )
    except Exception as exc:
        raise SearchModelError("Model failed to load") from exc
    try:
        dense = embedder.encode_dense(
            [query],
            batch_size=1,
            max_length=max_length,
        )
        if len(dense) == 0:
            return []
        query_vec = dense[0].tolist()

        game_index = MeiliGameIndex(
            url=meili_url,
            api_key=meili_api_key,
            index_uid=library["index_uid"],
            embedder_name="bge_m3",
            embedding_dim=len(query_vec),
        )
        return game_index.search_by_vector(
            query_vec,
            limit=limit or 10,
            embedder_key="bge_m3",
        )
    except Exception as exc:  # noqa: BLE001
        raise SearchExecutionError(
            "Search could not be completed. Check Meilisearch and try again."
        ) from exc
