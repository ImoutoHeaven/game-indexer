import importlib.util
import os
from pathlib import Path

import game_web.app as app_module


ROOT = Path(__file__).resolve().parents[1]
WEB_UI_PATH = ROOT / "bin" / "web_ui.py"


def _load_web_ui_module():
    spec = importlib.util.spec_from_file_location("test_bin_web_ui", WEB_UI_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_web_ui_main_uses_reload_compatible_factory(tmp_path, monkeypatch):
    module = _load_web_ui_module()
    captured: dict[str, object] = {}

    def _run(app, **kwargs):
        captured["app"] = app
        captured["kwargs"] = kwargs

    monkeypatch.setattr(module.uvicorn, "run", _run)
    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "web_ui.py",
            "--data-dir",
            str(tmp_path / "web-data"),
            "--host",
            "0.0.0.0",
            "--port",
            "9001",
            "--reload",
        ],
    )
    monkeypatch.delenv("GAME_WEB_DB_PATH", raising=False)
    monkeypatch.delenv("GAME_WEB_DATA_DIR", raising=False)

    module.main()

    data_dir = (tmp_path / "web-data").resolve()
    assert captured["app"] == "game_web.app:create_web_ui_app"
    assert captured["kwargs"] == {
        "factory": True,
        "host": "0.0.0.0",
        "port": 9001,
        "reload": True,
    }
    assert os.environ["GAME_WEB_DB_PATH"] == str(data_dir / "app.db")
    assert os.environ["GAME_WEB_DATA_DIR"] == str(data_dir)


def test_create_web_ui_app_reads_runtime_paths_from_env(tmp_path, monkeypatch):
    data_dir = tmp_path / "runtime-data"
    db_path = data_dir / "app.db"
    monkeypatch.setenv("GAME_WEB_DB_PATH", str(db_path))
    monkeypatch.setenv("GAME_WEB_DATA_DIR", str(data_dir))

    app = app_module.create_web_ui_app()

    assert app.state.db_path == str(db_path)
    assert app.state.data_dir == data_dir


def test_create_web_ui_app_defaults_db_path_under_data_dir(tmp_path, monkeypatch):
    data_dir = tmp_path / "factory-default-data"
    monkeypatch.setenv("GAME_WEB_DATA_DIR", str(data_dir))
    monkeypatch.delenv("GAME_WEB_DB_PATH", raising=False)

    app = app_module.create_web_ui_app()

    assert app.state.db_path == str(data_dir / "app.db")
    assert app.state.data_dir == data_dir
