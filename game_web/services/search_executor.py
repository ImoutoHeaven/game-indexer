from types import SimpleNamespace

from game_semantic.config import load_config_from_env_and_args
from game_web.db import connect_db
from game_web.runtime import resolve_data_dir
from game_web.secrets import decrypt_secret
from game_web.services.embedding_profile import list_profiles
from game_web.services.library_service import list_libraries
from game_web.services.settings_service import get_setting


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
    embedder_key: str,
    query: str,
    limit: int | None = None,
) -> list[dict]:
    if not query:
        return []
    config = load_config_from_env_and_args(SimpleNamespace())

    conn = connect_db(db_path)
    try:
        libraries = list_libraries(conn)
        library = next((item for item in libraries if item["id"] == library_id), None)
        if library is None:
            return []
        profiles = list_profiles(conn, library_id)
        profile = next((item for item in profiles if item["key"] == embedder_key), None)
        if profile is None:
            return []
        enabled = _as_int(profile.get("enabled", 1), 1)
        if enabled == 0:
            return []
        meili_url = get_setting(conn, "meili_url") or config.meili_url
        api_key_value = get_setting(conn, "meili_api_key")
    finally:
        conn.close()

    meili_api_key = config.meili_api_key
    if api_key_value:
        data_dir = resolve_data_dir(None, db_path)
        decrypted = decrypt_secret(data_dir, api_key_value)
        if decrypted:
            meili_api_key = decrypted

    from game_semantic.embedding import BgeM3Embedder
    from game_semantic.meili_client import MeiliGameIndex

    use_fp16 = _as_int(profile.get("use_fp16", 0), 0)
    max_length = _as_int(profile.get("max_length", 128), 128)

    embedder = BgeM3Embedder(
        model_name=profile["model_name"],
        use_fp16=bool(use_fp16),
    )
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
        embedder_name=embedder_key,
        embedding_dim=len(query_vec),
    )
    return game_index.search_by_vector(
        query_vec,
        limit=limit or config.top_k,
        embedder_key=embedder_key,
    )
