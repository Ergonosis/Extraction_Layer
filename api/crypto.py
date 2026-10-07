"""Fernet encrypt/decrypt for integration tokens. Plaintext never hits disk."""

from flask import current_app
from cryptography.fernet import Fernet


def _fernet() -> Fernet:
    key = current_app.config.get("FERNET_KEY") or ""
    if not key:
        raise RuntimeError("FERNET_KEY is not set")
    if isinstance(key, str):
        key = key.encode("utf-8")
    return Fernet(key)


def encrypt_token(plaintext: str) -> bytes:
    """Encrypt a token string. Result is stored in the database as bytes."""
    if plaintext is None:
        raise ValueError("plaintext token is required")
    return _fernet().encrypt(plaintext.encode("utf-8"))


def decrypt_token(token_enc: bytes) -> str:
    """Decrypt a stored token blob. Caller must keep the result in memory only."""
    if not token_enc:
        raise ValueError("encrypted token is required")
    return _fernet().decrypt(token_enc).decode("utf-8")
