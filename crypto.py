"""Key derivation and vault encryption.

Design
------
The vault is encrypted with a random "vault key" (a Fernet key) that never
touches the disk in plain form. Instead, the vault key is stored *wrapped*
(encrypted) inside master.json, twice:

  * once under a key derived from the master password
  * once under a key derived from the secret answer (for password recovery)

Deriving keys uses PBKDF2-HMAC-SHA256 with a random per-install salt, so
nothing on disk is enough to decrypt the vault without the master password
(or the secret answer).
"""

import base64
import hashlib
import secrets

from cryptography.fernet import Fernet, InvalidToken

# PBKDF2 iteration count. OWASP recommends >= 600,000 for SHA-256 (2023+).
KDF_ITERATIONS = 600_000
SALT_BYTES = 16


def new_salt() -> str:
    """Return a new random salt, hex-encoded for easy JSON storage."""
    return secrets.token_hex(SALT_BYTES)


def derive_key(secret: str, salt_hex: str, iterations: int | None = None) -> bytes:
    """Derive a 32-byte key from a secret and salt, formatted for Fernet."""
    if iterations is None:
        iterations = KDF_ITERATIONS
    raw = hashlib.pbkdf2_hmac(
        "sha256",
        secret.encode("utf-8"),
        bytes.fromhex(salt_hex),
        iterations,
    )
    return base64.urlsafe_b64encode(raw)


def generate_vault_key() -> bytes:
    """Create a brand-new random vault key."""
    return Fernet.generate_key()


def wrap_key(vault_key: bytes, secret: str, salt_hex: str,
             iterations: int | None = None) -> str:
    """Encrypt the vault key under a key derived from `secret`."""
    kek = derive_key(secret, salt_hex, iterations)
    return Fernet(kek).encrypt(vault_key).decode("utf-8")


def unwrap_key(wrapped: str, secret: str, salt_hex: str,
               iterations: int | None = None) -> bytes | None:
    """Decrypt the vault key. Returns None if the secret is wrong."""
    kek = derive_key(secret, salt_hex, iterations)
    try:
        return Fernet(kek).decrypt(wrapped.encode("utf-8"))
    except InvalidToken:
        return None


class VaultCipher:
    """Holds the unlocked vault key in memory for the current session."""

    def __init__(self, vault_key: bytes):
        self._fernet = Fernet(vault_key)
        self._key = vault_key

    @property
    def key(self) -> bytes:
        return self._key

    def encrypt(self, text: str) -> str:
        return self._fernet.encrypt(text.encode("utf-8")).decode("utf-8")

    def decrypt(self, token: str) -> str:
        return self._fernet.decrypt(token.encode("utf-8")).decode("utf-8")
