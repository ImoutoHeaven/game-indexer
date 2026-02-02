import base64
import hashlib
from typing import Any, cast

from game_web.auth import hash_password, verify_password


def test_hash_password_round_trip():
    password = "correct horse battery staple"

    hashed = hash_password(password)

    assert isinstance(hashed, str)
    assert hashed
    assert verify_password(password, hashed)


def test_hash_password_uses_random_salt():
    password = "same-password"

    hashed_one = hash_password(password)
    hashed_two = hash_password(password)

    assert hashed_one != hashed_two


def test_verify_password_rejects_wrong_password():
    password = "s3cr3t"
    hashed = hash_password(password)

    assert not verify_password("not-it", hashed)


def test_verify_rejects_excessive_iterations():
    password = "lots-of-iterations"
    salt = b"0123456789abcdef"
    excessive = 999_999
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        excessive,
    )
    hashed = "pbkdf2_sha256${}${}${}".format(
        excessive,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(derived).decode("ascii"),
    )

    assert not verify_password(password, hashed)


def test_verify_rejects_short_salt():
    password = "short-salt"
    salt = b"x"
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        120_000,
    )
    hashed = "pbkdf2_sha256$120000${}${}".format(
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(derived).decode("ascii"),
    )

    assert not verify_password(password, hashed)


def test_verify_rejects_non_string_inputs():
    password = "secret"
    hashed = hash_password(password)

    assert not verify_password(cast(Any, None), hashed)
    assert not verify_password(password, cast(Any, None))
