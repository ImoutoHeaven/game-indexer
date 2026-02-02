from pathlib import Path

from game_web.runtime import resolve_data_dir


def test_resolve_data_dir_defaults_to_project_data(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data_dir = resolve_data_dir(None)
    assert data_dir == tmp_path / "data"


def test_resolve_data_dir_uses_parent_of_db_path(tmp_path):
    db_path = tmp_path / "data" / "app.db"
    data_dir = resolve_data_dir(None, db_path=str(db_path))
    assert data_dir == tmp_path / "data"
