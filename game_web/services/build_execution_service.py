from pathlib import Path
from typing import Any, Callable

from game_semantic.config import Config
from game_semantic.service import build_index
from game_web.db import connect_db
from game_web.secrets import decrypt_secret
from game_web.services.embedding_profile import get_active_profile
from game_web.services.library_service import get_library
from game_web.services.settings_service import get_setting


def _get_job_dataset(conn: Any, dataset_id: int) -> dict[str, Any] | None:
    cur = conn.execute(
        """
        select id,
            library_id,
            filename,
            storage_path,
            size_bytes,
            created_at
        from dataset
        where id = ?
        """,
        (dataset_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "library_id": row[1],
        "filename": row[2],
        "storage_path": row[3],
        "size_bytes": row[4],
        "created_at": row[5],
    }


def _resolve_owned_dataset_path(data_dir: Path, storage_path: str) -> Path:
    candidate = (data_dir / storage_path).resolve()
    if candidate == data_dir or data_dir.resolve() not in candidate.parents:
        raise RuntimeError("Dataset path is outside the application data directory")
    return candidate


def _normalize_profile(profile: dict[str, Any]) -> tuple[str, bool, int]:
    model_name = str(profile.get("model_name", "")).strip()
    if not model_name:
        raise RuntimeError("Active search configuration is invalid: model name is blank")

    try:
        use_fp16_value = int(profile.get("use_fp16", 0))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Active search configuration is invalid: use_fp16") from exc
    if use_fp16_value not in (0, 1):
        raise RuntimeError("Active search configuration is invalid: use_fp16")

    try:
        max_length = int(profile.get("max_length", 0))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Active search configuration is invalid: max_length") from exc
    if max_length <= 0:
        raise RuntimeError("Active search configuration is invalid: max_length")

    return model_name, bool(use_fp16_value), max_length


def execute_build_job(*, db_path: str, data_dir: Path, job: dict[str, Any], log: Callable[[str], None]) -> None:
    """Resolve build inputs from job + app settings and run the semantic build path."""
    conn = connect_db(db_path)
    try:
        library = get_library(conn, int(job["library_id"]))
        dataset = _get_job_dataset(conn, int(job["dataset_id"]))
        active_profile = get_active_profile(conn, int(job["library_id"]))
        meili_url = (get_setting(conn, "meili_url") or "").strip()
        encrypted_api_key = get_setting(conn, "meili_api_key")
        conn.commit()
    finally:
        conn.close()

    if library is None:
        raise RuntimeError(f"Library {job['library_id']} was not found for job {job['id']}")
    if dataset is None:
        raise RuntimeError(f"Dataset {job['dataset_id']} was not found for job {job['id']}")
    if not meili_url:
        raise RuntimeError("Meilisearch URL is not configured")

    meili_api_key = decrypt_secret(data_dir, encrypted_api_key or "") if encrypted_api_key else ""

    model_name, use_fp16, max_length = _normalize_profile(active_profile)
    txt_path = _resolve_owned_dataset_path(data_dir, str(dataset["storage_path"]))

    log(f"Resolved dataset {dataset['filename']} for job {job['id']}")
    log(f"Running rebuild for library {library['index_uid']}")

    build_index(
        Config(
            meili_url=meili_url,
            meili_api_key=meili_api_key,
            meili_index_uid=str(library["index_uid"]),
            mode="rebuild",
            bge_model_name=model_name,
            bge_use_fp16=use_fp16,
            embedding_max_length=max_length,
            txt_path=str(txt_path),
        )
    )

    log(f"Build completed for job {job['id']}")
