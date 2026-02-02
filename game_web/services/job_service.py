from datetime import datetime, timezone

from game_web.jobs import write_log_line


def append_job_log(path: str, line: str) -> None:
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    formatted = f"{timestamp} [INFO] {line}"
    write_log_line(path, formatted)
