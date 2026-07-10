"""Master credentials, login verification, lockout, and recovery.

master.json layout, version 3 (nothing in it can decrypt the vault on
its own):

  {
    "version": 3,
    "username": "...",
    "kdf_iterations": 600000,
    "auth_salt": "...",  "auth_hash": "...",      # verifies the password
    "pw_salt": "...",    "wrapped_key_pw": "...", # vault key, wrapped by password
    "rec_salt": "...",   "rec_hash": "...",       # verifies the recovery key
    "rec_wrap_salt": "...", "wrapped_key_rec": "...", # vault key, wrapped by recovery key
    "lockout": {"failed_attempts": 0, "locked_until": 0, "cooldown": 30}
  }

Recovery uses a random recovery key like "K7QX-2MHD-9RWP-4TFZ"
(~79 bits of entropy) that is shown to the user exactly once.
"""

import hashlib
import hmac
import json
import os
import secrets
import tempfile
import time

import crypto
from crypto import (
    VaultCipher,
    generate_vault_key,
    new_salt,
    unwrap_key,
    wrap_key,
)

MASTER_FILE = "master.json"

MAX_ATTEMPTS = 10
BASE_COOLDOWN = 30  # seconds; doubles after each lockout

# No I/L/O/0/1 — unambiguous when written down on paper.
RECOVERY_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def generate_recovery_code() -> str:
    """A random recovery key: 4 groups of 4 chars, ~79 bits of entropy."""
    groups = ["".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(4))
              for _ in range(4)]
    return "-".join(groups)


def _normalize_code(code: str) -> str:
    """Accept the recovery key with/without dashes, spaces, lowercase."""
    return code.replace("-", "").replace(" ", "").strip().upper()


def _hash_secret(secret: str, salt_hex: str, iterations: int) -> str:
    """Slow, salted hash used only for verification (not key material)."""
    return hashlib.pbkdf2_hmac(
        "sha256", secret.encode("utf-8"), bytes.fromhex(salt_hex), iterations
    ).hex()


def load_master() -> dict | None:
    if not os.path.exists(MASTER_FILE):
        return None
    with open(MASTER_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def save_master(data: dict) -> None:
    """Atomic write: a crash mid-save can't corrupt the master file."""
    directory = os.path.dirname(os.path.abspath(MASTER_FILE))
    fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2)
        os.replace(tmp_path, MASTER_FILE)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def _recovery_fields(vault_key: bytes, iterations: int) -> tuple[str, dict]:
    """Generate a fresh recovery key and the master.json fields for it."""
    code = generate_recovery_code()
    normalized = _normalize_code(code)
    rec_salt = new_salt()
    rec_wrap_salt = new_salt()
    fields = {
        "rec_salt": rec_salt,
        "rec_hash": _hash_secret(normalized, rec_salt, iterations),
        "rec_wrap_salt": rec_wrap_salt,
        "wrapped_key_rec": wrap_key(vault_key, normalized, rec_wrap_salt,
                                    iterations),
    }
    return code, fields


def setup_master(username: str, password: str) -> tuple[VaultCipher, str]:
    """Create master.json from scratch.

    Returns (unlocked cipher, recovery key). The recovery key is shown
    to the user once and never stored in recoverable form.
    """
    vault_key = generate_vault_key()
    iterations = crypto.KDF_ITERATIONS
    auth_salt = new_salt()
    pw_salt = new_salt()
    code, rec_fields = _recovery_fields(vault_key, iterations)

    data = {
        "version": 3,
        "username": username,
        "kdf_iterations": iterations,
        "auth_salt": auth_salt,
        "auth_hash": _hash_secret(password, auth_salt, iterations),
        "pw_salt": pw_salt,
        "wrapped_key_pw": wrap_key(vault_key, password, pw_salt, iterations),
        **rec_fields,
        "lockout": {"failed_attempts": 0, "locked_until": 0,
                    "cooldown": BASE_COOLDOWN},
    }
    save_master(data)
    return VaultCipher(vault_key), code


def rotate_recovery_key(vault_key: bytes) -> str | None:
    """Retire the current recovery key and issue a fresh one.

    Requires the unlocked vault key (i.e. a logged-in session whose
    master password was just re-verified). Returns the new key."""
    data = load_master()
    if data is None:
        return None
    code, rec_fields = _recovery_fields(vault_key, data["kdf_iterations"])
    data.update(rec_fields)
    save_master(data)
    return code


def verify_master_password(password: str) -> bool:
    """Re-check the master password (e.g. before showing history).
    Does not touch lockout state."""
    data = load_master()
    if data is None:
        return False
    actual = _hash_secret(password, data["auth_salt"], data["kdf_iterations"])
    return hmac.compare_digest(data["auth_hash"], actual)


# ── Recovery (v3: recovery key) ──────────────────────────────────────────

def verify_recovery_code(code: str) -> bool:
    data = load_master()
    if data is None or "rec_hash" not in data:
        return False
    actual = _hash_secret(_normalize_code(code), data["rec_salt"],
                          data["kdf_iterations"])
    return hmac.compare_digest(data["rec_hash"], actual)


def reset_password_with_recovery(code: str, new_password: str,
                                 ) -> tuple[VaultCipher, str] | tuple[None, None]:
    """Recover access: unwrap the vault key with the recovery key, then
    re-wrap it under the new password. The used recovery key is retired
    and a fresh one issued.

    Returns (unlocked cipher, new recovery key), or (None, None) if the
    code is wrong."""
    data = load_master()
    if data is None or "wrapped_key_rec" not in data:
        return None, None

    vault_key = unwrap_key(
        data["wrapped_key_rec"], _normalize_code(code),
        data["rec_wrap_salt"], data["kdf_iterations"],
    )
    if vault_key is None:
        return None, None

    iterations = data["kdf_iterations"]
    data["auth_salt"] = new_salt()
    data["auth_hash"] = _hash_secret(new_password, data["auth_salt"], iterations)
    data["pw_salt"] = new_salt()
    data["wrapped_key_pw"] = wrap_key(vault_key, new_password,
                                      data["pw_salt"], iterations)
    new_code, rec_fields = _recovery_fields(vault_key, iterations)
    data.update(rec_fields)
    data["lockout"] = {"failed_attempts": 0, "locked_until": 0,
                       "cooldown": BASE_COOLDOWN}
    save_master(data)
    return VaultCipher(vault_key), new_code


# ── Login / lockout ──────────────────────────────────────────────────────

class AuthManager:
    """Verifies logins and enforces a persistent lockout policy."""

    def __init__(self):
        self.last_activity = time.time()

    # lockout state lives in master.json so restarting the app can't skip it
    def _lockout(self) -> dict:
        data = load_master()
        if data is None:
            return {"failed_attempts": 0, "locked_until": 0, "cooldown": BASE_COOLDOWN}
        return data.get("lockout",
                        {"failed_attempts": 0, "locked_until": 0, "cooldown": BASE_COOLDOWN})

    def _save_lockout(self, lockout: dict) -> None:
        data = load_master()
        if data is not None:
            data["lockout"] = lockout
            save_master(data)

    def is_locked_out(self) -> bool:
        return time.time() < self._lockout()["locked_until"]

    def seconds_until_unlock(self) -> int:
        return max(0, int(self._lockout()["locked_until"] - time.time()))

    def attempts_left(self) -> int:
        return MAX_ATTEMPTS - self._lockout()["failed_attempts"]

    def record_failed_attempt(self) -> None:
        lockout = self._lockout()
        lockout["failed_attempts"] += 1
        if lockout["failed_attempts"] >= MAX_ATTEMPTS:
            lockout["locked_until"] = time.time() + lockout["cooldown"]
            lockout["cooldown"] *= 2
            lockout["failed_attempts"] = 0
        self._save_lockout(lockout)

    def update_activity(self) -> None:
        self.last_activity = time.time()

    def is_inactive(self, timeout: int = 120) -> bool:
        return time.time() - self.last_activity > timeout

    def verify(self, username: str, password: str):
        """Returns ("success", VaultCipher) | ("failed", None) | ("locked", None)."""
        if self.is_locked_out():
            return "locked", None

        data = load_master()
        if data is None:
            return "failed", None

        expected = data["auth_hash"]
        actual = _hash_secret(password, data["auth_salt"], data["kdf_iterations"])

        if data["username"] == username and hmac.compare_digest(expected, actual):
            vault_key = unwrap_key(data["wrapped_key_pw"], password,
                                   data["pw_salt"], data["kdf_iterations"])
            if vault_key is None:  # shouldn't happen, but never trust files
                return "failed", None
            lockout = self._lockout()
            lockout["failed_attempts"] = 0
            lockout["cooldown"] = BASE_COOLDOWN
            self._save_lockout(lockout)
            return "success", VaultCipher(vault_key)

        self.record_failed_attempt()
        return "failed", None
