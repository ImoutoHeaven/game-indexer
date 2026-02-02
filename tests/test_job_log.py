from datetime import datetime

from game_web.jobs import write_log_line
from game_web.services.job_service import append_job_log


def test_write_log_line(tmp_path):
    log_path = tmp_path / "job.log"
    write_log_line(str(log_path), "hello")
    assert log_path.read_text().strip() == "hello"


def test_write_log_line_appends_multiple_lines(tmp_path):
    log_path = tmp_path / "job.log"
    write_log_line(str(log_path), "hello")
    write_log_line(str(log_path), "world")
    assert log_path.read_text().splitlines() == ["hello", "world"]


def test_write_log_line_normalizes_newlines(tmp_path):
    log_path = tmp_path / "job.log"
    write_log_line(str(log_path), "hello\nworld")
    assert log_path.read_text().strip() == "hello world"


def test_append_job_log_includes_timestamp_level_and_message(tmp_path):
    log_path = tmp_path / "job.log"
    append_job_log(str(log_path), "hello\nworld")
    line = log_path.read_text().strip()
    assert "[INFO]" in line
    assert "hello world" in line
    assert "\n" not in line
    timestamp = line.split(" ", 1)[0]
    datetime.fromisoformat(timestamp)
