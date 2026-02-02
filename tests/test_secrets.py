from pathlib import Path
import stat

from cryptography.fernet import Fernet

from game_web.secrets import (
    _write_key,
    decrypt_secret,
    encrypt_secret,
    load_key,
    load_or_create_key,
)


def test_load_or_create_key_sets_permissions(tmp_path: Path):
    token = encrypt_secret(tmp_path, "value")
    assert token
    key_path = tmp_path / "secret.key"
    mode = stat.S_IMODE(key_path.stat().st_mode)
    assert mode == 0o600


def test_load_or_create_key_recovers_invalid_key(tmp_path: Path):
    key_path = tmp_path / "secret.key"
    key_path.write_text("not-a-valid-key")
    token = encrypt_secret(tmp_path, "value")
    assert token
    key = key_path.read_bytes()
    Fernet(key)


def test_decrypt_invalid_returns_none(tmp_path: Path):
    assert decrypt_secret(tmp_path, "not-a-token") is None


def test_decrypt_without_key_returns_none_and_no_key_file(tmp_path: Path):
    key_path = tmp_path / "secret.key"
    assert not key_path.exists()
    assert decrypt_secret(tmp_path, "not-a-token") is None
    assert not key_path.exists()


def test_decrypt_non_ascii_returns_none(tmp_path: Path):
    encrypt_secret(tmp_path, "value")
    token = "not-a-token" + bytes([169]).decode("latin1")
    assert decrypt_secret(tmp_path, token) is None


def test_load_key_handles_read_error(tmp_path: Path, monkeypatch):
    encrypt_secret(tmp_path, "value")

    def _raise(*args, **kwargs):
        raise OSError("read failed")

    monkeypatch.setattr(Path, "read_bytes", _raise)
    assert load_key(tmp_path) is None


def test_load_key_handles_chmod_error(tmp_path: Path, monkeypatch):
    encrypt_secret(tmp_path, "value")

    def _raise(*args, **kwargs):
        raise OSError("chmod failed")

    monkeypatch.setattr(Path, "chmod", _raise)
    assert load_key(tmp_path) is not None


def test_decrypt_invalid_utf8_returns_none(tmp_path: Path):
    key = Fernet.generate_key()
    token = Fernet(key).encrypt(b"\xff")
    key_path = tmp_path / "secret.key"
    key_path.write_bytes(key)
    key_path.chmod(0o600)
    assert decrypt_secret(tmp_path, token.decode("ascii")) is None


def test_load_or_create_key_handles_write_error(tmp_path: Path, monkeypatch):
    def _raise(*args, **kwargs):
        raise OSError("write failed")

    monkeypatch.setattr(Path, "write_bytes", _raise)
    assert load_or_create_key(tmp_path) is None


def test_write_key_handles_chmod_error(tmp_path: Path, monkeypatch):
    key_path = tmp_path / "secret.key"

    def _raise(*args, **kwargs):
        raise OSError("chmod failed")

    monkeypatch.setattr(Path, "chmod", _raise)
    assert _write_key(key_path, Fernet.generate_key()) is True
