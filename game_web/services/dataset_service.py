import datetime
import io
from pathlib import Path
from typing import Any

UPLOAD_MAX_BYTES = 10 * 1024 * 1024
UPLOAD_CHUNK_SIZE = 64 * 1024


class UploadTooLarge(Exception):
    pass


def _safe_filename(filename: str) -> str:
    name = Path(filename).name
    return name or "upload.bin"


def _unique_path(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem = Path(filename).stem or "upload"
    suffix = Path(filename).suffix
    counter = 1
    while True:
        candidate = directory / f"{stem}-{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def _write_stream(path: Path, file_obj: Any) -> int:
    bytes_written = 0
    try:
        with open(path, "wb") as handle:
            while True:
                chunk = file_obj.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > UPLOAD_MAX_BYTES:
                    raise UploadTooLarge()
                handle.write(chunk)
    except UploadTooLarge:
        if path.exists():
            path.unlink()
        raise
    except OSError:
        if path.exists():
            path.unlink()
        raise
    return bytes_written


def save_upload(
    conn: Any,
    data_dir: Path,
    library_id: int,
    filename: str,
    file_obj: Any,
    commit: bool = True,
) -> dict[str, Any]:
    uploads_dir = data_dir / "uploads" / str(library_id)
    uploads_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_filename(filename)
    path = _unique_path(uploads_dir, safe_name)
    size_bytes = _write_stream(path, file_obj)
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    timestamp = now.isoformat()
    storage_path = str(path.relative_to(data_dir))
    try:
        cur = conn.execute(
            """
            insert into dataset (library_id, filename, storage_path, size_bytes, created_at)
            values (?, ?, ?, ?, ?)
            """,
            (library_id, path.name, storage_path, size_bytes, timestamp),
        )
        if commit:
            conn.commit()
    except Exception:
        if path.exists():
            path.unlink()
        raise
    return {
        "id": cur.lastrowid,
        "library_id": library_id,
        "filename": path.name,
        "storage_path": storage_path,
        "size_bytes": size_bytes,
        "created_at": timestamp,
        "path": path,
    }


def create_dataset(
    conn: Any,
    data_dir: Path,
    library_id: int,
    filename: str,
    content: bytes,
    commit: bool = True,
) -> dict[str, Any]:
    return save_upload(
        conn,
        data_dir=data_dir,
        library_id=library_id,
        filename=filename,
        file_obj=io.BytesIO(content),
        commit=commit,
    )
