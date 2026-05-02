import datetime
from typing import Any


ACTIVE_PROFILE_KEY = "bge_m3"
ACTIVE_PROFILE_VARIANT = "raw"
ACTIVE_PROFILE_ENABLED = 1
DEFAULT_MODEL_NAME = "BAAI/bge-m3"
DEFAULT_USE_FP16 = 0
DEFAULT_MAX_LENGTH = 128


def _row_to_profile(row: Any) -> dict[str, Any]:
    return {
        "id": row[0],
        "library_id": row[1],
        "key": row[2],
        "model_name": row[3],
        "use_fp16": row[4],
        "max_length": row[5],
        "variant": row[6],
        "enabled": row[7],
        "created_at": row[8],
    }


def _get_profile_row(conn: Any, library_id: int, key: str) -> dict[str, Any] | None:
    cur = conn.execute(
        """
        select id,
            library_id,
            key,
            model_name,
            use_fp16,
            max_length,
            variant,
            enabled,
            created_at
        from embedding_profile
        where library_id = ? and key = ?
        order by id
        limit 1
        """,
        (library_id, key),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return _row_to_profile(row)


def _coerce_existing_int(value: Any) -> Any:
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _normalized_existing_values(profile: dict[str, Any]) -> tuple[Any, Any, Any]:
    return (
        str(profile.get("model_name", "")).strip(),
        _coerce_existing_int(profile.get("use_fp16")),
        _coerce_existing_int(profile.get("max_length")),
    )


def _normalize_model_name(model_name: str) -> str:
    normalized = model_name.strip()
    if not normalized:
        raise ValueError("Model name must not be blank")
    return normalized


def _normalize_use_fp16(use_fp16: Any) -> int:
    try:
        normalized = int(use_fp16)
    except (TypeError, ValueError) as exc:
        raise ValueError("Use FP16 must be 0 or 1") from exc
    if normalized not in (0, 1):
        raise ValueError("Use FP16 must be 0 or 1")
    return normalized


def _normalize_max_length(max_length: Any) -> int:
    try:
        normalized = int(max_length)
    except (TypeError, ValueError) as exc:
        raise ValueError("Max length must be greater than 0") from exc
    if normalized <= 0:
        raise ValueError("Max length must be greater than 0")
    return normalized


def _default_profile_values() -> dict[str, Any]:
    return {
        "model_name": DEFAULT_MODEL_NAME,
        "use_fp16": DEFAULT_USE_FP16,
        "max_length": DEFAULT_MAX_LENGTH,
    }


def _normalize_fixed_fields(conn: Any, profile: dict[str, Any]) -> dict[str, Any]:
    updates: list[Any] = []
    assignments: list[str] = []

    if profile["variant"] != ACTIVE_PROFILE_VARIANT:
        assignments.append("variant = ?")
        updates.append(ACTIVE_PROFILE_VARIANT)
        profile["variant"] = ACTIVE_PROFILE_VARIANT
    if profile["enabled"] != ACTIVE_PROFILE_ENABLED:
        assignments.append("enabled = ?")
        updates.append(ACTIVE_PROFILE_ENABLED)
        profile["enabled"] = ACTIVE_PROFILE_ENABLED

    if assignments:
        updates.append(profile["id"])
        conn.execute(
            f"update embedding_profile set {', '.join(assignments)} where id = ?",
            tuple(updates),
        )

    return profile

def add_profile(
    conn: Any,
    library_id: int,
    key: str,
    model_name: str,
    use_fp16: int = 0,
    max_length: int = 128,
    variant: str = "raw",
    enabled: int = 1,
    commit: bool = True,
) -> None:
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    timestamp = now.isoformat()
    conn.execute(
        """
        insert into embedding_profile (
            library_id,
            key,
            model_name,
            use_fp16,
            max_length,
            variant,
            enabled,
            created_at
        )
        values (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (library_id, key, model_name, use_fp16, max_length, variant, enabled, timestamp),
    )
    if commit:
        conn.commit()


def list_profiles(conn: Any, library_id: int) -> list[dict[str, Any]]:
    cur = conn.execute(
        """
        select id,
            library_id,
            key,
            model_name,
            use_fp16,
            max_length,
            variant,
            enabled,
            created_at
        from embedding_profile
        where library_id = ?
        order by id
        """,
        (library_id,),
    )
    rows = cur.fetchall()
    return [_row_to_profile(row) for row in rows]


def get_active_profile(conn: Any, library_id: int, *, commit: bool = False) -> dict[str, Any]:
    """Return the canonical bge_m3 row, creating it from legacy data when needed."""
    profile = _get_profile_row(conn, library_id, ACTIVE_PROFILE_KEY)
    if profile is None:
        profiles = list_profiles(conn, library_id=library_id)
        source = profiles[0] if profiles else _default_profile_values()
        add_profile(
            conn,
            library_id=library_id,
            key=ACTIVE_PROFILE_KEY,
            model_name=source["model_name"],
            use_fp16=source.get("use_fp16", DEFAULT_USE_FP16),
            max_length=source.get("max_length", DEFAULT_MAX_LENGTH),
            variant=ACTIVE_PROFILE_VARIANT,
            enabled=ACTIVE_PROFILE_ENABLED,
            commit=False,
        )
        profile = _get_profile_row(conn, library_id, ACTIVE_PROFILE_KEY)

    if profile is None:
        raise ValueError("Active profile could not be created")

    return _normalize_fixed_fields(conn, profile)


def upsert_active_profile(
    conn: Any,
    *,
    library_id: int,
    model_name: str,
    use_fp16: int,
    max_length: int,
    commit: bool = False,
) -> bool:
    """Persist the canonical bge_m3 row and report whether values materially changed."""
    normalized_model_name = _normalize_model_name(model_name)
    normalized_use_fp16 = _normalize_use_fp16(use_fp16)
    normalized_max_length = _normalize_max_length(max_length)

    profile = get_active_profile(conn, library_id, commit=commit)
    changed = _normalized_existing_values(profile) != (
        normalized_model_name,
        normalized_use_fp16,
        normalized_max_length,
    )

    conn.execute(
        """
        update embedding_profile
        set model_name = ?,
            use_fp16 = ?,
            max_length = ?,
            variant = ?,
            enabled = ?
        where id = ?
        """,
        (
            normalized_model_name,
            normalized_use_fp16,
            normalized_max_length,
            ACTIVE_PROFILE_VARIANT,
            ACTIVE_PROFILE_ENABLED,
            profile["id"],
        ),
    )
    if commit:
        conn.commit()
    return changed
