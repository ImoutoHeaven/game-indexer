from pathlib import Path


def resolve_data_dir(path: str | Path | None, db_path: str | None = None) -> Path:
    if path is not None:
        if isinstance(path, Path):
            return path.expanduser().resolve()
        return Path(path).expanduser().resolve()
    if db_path:
        return Path(db_path).resolve().parent
    return (Path.cwd() / "data").resolve()


def resolve_jobs_dir(data_dir: Path) -> Path:
    base_dir = (data_dir / "logs" / "jobs").resolve()
    if base_dir != data_dir and data_dir in base_dir.parents:
        return base_dir
    return (data_dir / "logs_safe" / "jobs").resolve()
