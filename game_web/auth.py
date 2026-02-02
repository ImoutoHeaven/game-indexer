import base64
import binascii
import hashlib
import hmac
import os


_ALGORITHM = "sha256"
_ITERATIONS = 120_000
_MIN_ITERATIONS = 120_000
_MAX_ITERATIONS = 200_000
_SALT_BYTES = 16
_FORMAT_PREFIX = "pbkdf2_sha256"
_DERIVED_BYTES = hashlib.new(_ALGORITHM).digest_size


def _encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _decode(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def hash_password(password: str) -> str:
    salt = os.urandom(_SALT_BYTES)
    derived = hashlib.pbkdf2_hmac(
        _ALGORITHM,
        password.encode("utf-8"),
        salt,
        _ITERATIONS,
    )
    return f"{_FORMAT_PREFIX}${_ITERATIONS}${_encode(salt)}${_encode(derived)}"


def verify_password(password: str, hashed: str) -> bool:
    if not isinstance(password, str) or not isinstance(hashed, str):
        return False
    try:
        prefix, iterations_raw, salt_b64, hash_b64 = hashed.split("$", 3)
        if prefix != _FORMAT_PREFIX:
            return False
        iterations = int(iterations_raw)
        if not (_MIN_ITERATIONS <= iterations <= _MAX_ITERATIONS):
            return False
        salt = _decode(salt_b64)
        expected = _decode(hash_b64)
    except (ValueError, TypeError, binascii.Error):
        return False

    if len(salt) != _SALT_BYTES:
        return False
    if len(expected) != _DERIVED_BYTES:
        return False

    derived = hashlib.pbkdf2_hmac(
        _ALGORITHM,
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(derived, expected)
