"""Encrypted vault backups.

A backup file is JSON containing a salt plus the whole vault encrypted
under a key derived from a backup passphrase — safe to store in cloud
drives or email to yourself.
"""

import json

from cryptography.fernet import Fernet, InvalidToken

import crypto
from crypto import derive_key, new_salt

FORMAT_VERSION = 1


def export_backup(entries: dict, passphrase: str, path: str) -> None:
    """Write an encrypted backup of plaintext `entries` to `path`."""
    salt = new_salt()
    iterations = crypto.KDF_ITERATIONS
    key = derive_key(passphrase, salt, iterations)
    payload = Fernet(key).encrypt(
        json.dumps(entries).encode("utf-8")).decode("utf-8")

    with open(path, "w", encoding="utf-8") as file:
        json.dump({
            "format": "password-manager-backup",
            "version": FORMAT_VERSION,
            "kdf_iterations": iterations,
            "salt": salt,
            "data": payload,
        }, file, indent=2)


def import_backup(path: str, passphrase: str) -> dict | None:
    """Read and decrypt a backup file. Returns the plaintext entries,
    or None if the passphrase is wrong or the file isn't a valid backup."""
    try:
        with open(path, "r", encoding="utf-8") as file:
            blob = json.load(file)
        if blob.get("format") != "password-manager-backup":
            return None
        key = derive_key(passphrase, blob["salt"],
                         blob.get("kdf_iterations"))
        plaintext = Fernet(key).decrypt(blob["data"].encode("utf-8"))
        return json.loads(plaintext)
    except (json.JSONDecodeError, KeyError, InvalidToken, OSError, ValueError):
        return None
