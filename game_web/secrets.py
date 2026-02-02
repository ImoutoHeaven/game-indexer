from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


def _secret_key_path(data_dir: Path) -> Path:
    return data_dir / "secret.key"


def _write_key(path: Path, key: bytes) -> bool:
    try:
        path.write_bytes(key)
    except OSError:
        return False
    try:
        path.chmod(0o600)
    except OSError:
        return True
    return True


def load_key(data_dir: Path) -> bytes | None:
    key_path = _secret_key_path(data_dir)
    if not key_path.exists():
        return None
    try:
        key = key_path.read_bytes()
    except OSError:
        return None
    try:
        Fernet(key)
    except ValueError:
        return None
    try:
        key_path.chmod(0o600)
    except OSError:
        pass
    return key


def load_or_create_key(data_dir: Path) -> bytes | None:
    data_dir.mkdir(parents=True, exist_ok=True)
    key_path = _secret_key_path(data_dir)
    try:
        key = load_key(data_dir)
    except OSError:
        key = None
    if key is not None:
        return key
    key = Fernet.generate_key()
    if not _write_key(key_path, key):
        return None
    return key


def encrypt_secret(data_dir: Path, value: str) -> str:
    key = load_or_create_key(data_dir)
    if key is None:
        raise OSError("failed to persist encryption key")
    token = Fernet(key).encrypt(value.encode("utf-8"))
    return token.decode("ascii")


def decrypt_secret(data_dir: Path, value: str) -> str | None:
    if not value:
        return None
    key = load_key(data_dir)
    if key is None:
        return None
    try:
        token_bytes = value.encode("utf-8")
    except UnicodeEncodeError:
        return None
    try:
        payload = Fernet(key).decrypt(token_bytes)
    except (InvalidToken, ValueError):
        return None
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        return None
