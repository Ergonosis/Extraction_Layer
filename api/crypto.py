"""Fernet encrypt/decrypt for integration tokens. Plaintext never hits disk."""

from __future__ import annotations

from cryptography.fernet import Fernet, MultiFernet
from flask import current_app


def _encode_key(key: str | bytes) -> bytes:
    if isinstance(key, str):
        return key.encode("utf-8")
    return key


def _fernet_keys() -> list[bytes]:
    """Primary FERNET_KEY first, then optional previous keys for rotation decrypt."""
    primary = current_app.config.get("FERNET_KEY") or ""
    if not primary:
        raise RuntimeError("FERNET_KEY is not set")
    keys = [_encode_key(primary)]
    previous = current_app.config.get("FERNET_PREVIOUS_KEYS") or []
    for item in previous:
        if item:
            keys.append(_encode_key(item))
    return keys


def _fernet() -> Fernet | MultiFernet:
    keys = _fernet_keys()
    if len(keys) == 1:
        return Fernet(keys[0])
    return MultiFernet([Fernet(k) for k in keys])


def encrypt_token(plaintext: str) -> bytes:
    """Encrypt a token string. Result is stored in the database as bytes.

    Always encrypts with the primary ``FERNET_KEY`` (MultiFernet first key).
    """
    if plaintext is None:
        raise ValueError("plaintext token is required")
    return _fernet().encrypt(plaintext.encode("utf-8"))


def decrypt_token(token_enc: bytes) -> str:
    """Decrypt a stored token blob. Caller must keep the result in memory only.

    Tries primary then ``FERNET_PREVIOUS_KEYS`` during key rotation windows.
    """
    if not token_enc:
        raise ValueError("encrypted token is required")
    return _fernet().decrypt(token_enc).decode("utf-8")
