"""Vault storage: fully encrypted vault (entries, history, categories).

Vault format (version 2): the entire entry structure is encrypted as one
blob under the vault key, so the file on disk reveals nothing — not even
which sites you have accounts on, usernames, or timestamps.

  vault.json = {"format": "vault", "version": 2, "data": "<Fernet token>"}
"""

import datetime
import json
import os
import tempfile

from strength import check_strength

VAULT_FILE = "vault.json"
VAULT_FORMAT = "vault"
VAULT_VERSION = 3

DEFAULT_CATEGORIES = ["Work", "Banking", "Social", "Personal", "Other"]


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _atomic_write(path: str, text: str) -> None:
    """Write via a temp file + rename so a crash can't corrupt the vault."""
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(text)
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


class PasswordManager:
    """The vault is one encrypted blob, unlocked by the session's
    VaultCipher (only available after a successful login)."""

    def __init__(self, cipher, filename: str = VAULT_FILE):
        self.cipher = cipher
        self.filename = filename
        if not os.path.exists(self.filename):
            self._save_payload({"entries": {},
                                "categories": list(DEFAULT_CATEGORIES)})
        else:
            self.load_data()   # fails fast on a wrong key or bad format

    # ── persistence ──────────────────────────────────────────────────

    def _read_file(self) -> dict:
        try:
            with open(self.filename, "r", encoding="utf-8") as file:
                return json.load(file)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def _load_payload(self) -> dict:
        raw = self._read_file()
        if raw.get("format") != VAULT_FORMAT:
            raise ValueError("Unsupported vault format")
        payload = json.loads(self.cipher.decrypt(raw["data"]))
        if "entries" not in payload:   # blob v2 payload: bare entries dict
            payload = {"entries": payload,
                       "categories": list(DEFAULT_CATEGORIES)}
        return payload

    def _save_payload(self, payload: dict) -> None:
        blob = {
            "format": VAULT_FORMAT,
            "version": VAULT_VERSION,
            "data": self.cipher.encrypt(json.dumps(payload)),
        }
        _atomic_write(self.filename, json.dumps(blob, indent=2))

    def load_data(self) -> dict:
        return self._load_payload()["entries"]

    def save_data(self, data: dict) -> None:
        payload = self._load_payload()
        payload["entries"] = data
        self._save_payload(payload)

    # ── categories ───────────────────────────────────────────────────

    def get_categories(self) -> list:
        return list(self._load_payload().get("categories",
                                             DEFAULT_CATEGORIES))

    def add_category(self, name: str) -> bool:
        """Add a custom category (stored inside the encrypted vault).
        Returns False if the name is empty or already exists."""
        name = " ".join(name.split())
        if not name:
            return False
        payload = self._load_payload()
        categories = payload.get("categories", list(DEFAULT_CATEGORIES))
        if any(c.lower() == name.lower() for c in categories):
            return False
        categories.append(name)
        payload["categories"] = categories
        self._save_payload(payload)
        return True

    def delete_category(self, name: str) -> int | None:
        """Delete a category; its entries move to "Other". Returns the
        number of entries reassigned, or None if the category can't be
        deleted ("Other", or not found)."""
        payload = self._load_payload()
        categories = payload.get("categories", list(DEFAULT_CATEGORIES))
        if name == "Other" or name not in categories:
            return None
        moved = 0
        for entry in payload["entries"].values():
            if entry.get("category", "Other") == name:
                entry["category"] = "Other"
                moved += 1
        categories.remove(name)
        payload["categories"] = categories
        self._save_payload(payload)
        return moved

    # ── entries ──────────────────────────────────────────────────────

    def add_password(self, website: str, username: str, password: str,
                     category: str, notes: str = "") -> None:
        data = self.load_data()

        if website in data:
            old_entry = data[website]
            history = old_entry.get("history", [])
            # Only record history when the password actually changed.
            if old_entry["password"] != password:
                history.append({
                    "password": old_entry["password"],
                    "changed_at": old_entry.get("updated_at", _now()),
                })
        else:
            history = []

        data[website] = {
            "username": username,
            "password": password,
            "notes": notes,
            "history": history,
            "category": category,
            "updated_at": _now(),
        }
        self.save_data(data)

    def get_password(self, website: str) -> dict | None:
        data = self.load_data()
        if website not in data:
            return None
        entry = data[website]
        return {
            "username": entry["username"],
            "password": entry["password"],
            "notes": entry.get("notes", ""),
            "category": entry.get("category", "Other"),
            "updated_at": entry.get("updated_at", ""),
        }

    def get_history(self, website: str) -> list:
        data = self.load_data()
        if website not in data:
            return []
        return list(data[website].get("history", []))

    def delete_password(self, website: str) -> bool:
        data = self.load_data()
        if website in data:
            del data[website]
            self.save_data(data)
            return True
        return False

    def get_websites(self) -> list:
        return list(self.load_data().keys())

    def get_websites_by_category(self, category: str) -> list:
        return [
            website for website, entry in self.load_data().items()
            if entry.get("category", "Other") == category
        ]

    # ── health check ─────────────────────────────────────────────────

    def health_report(self, stale_days: int = 180) -> list:
        """Flags weak, reused, and old passwords across the whole vault.

        Returns a list of {website, issues: [..]} dicts, worst first.
        """
        data = self.load_data()

        # Count identical passwords for reuse detection.
        counts: dict[str, int] = {}
        for entry in data.values():
            counts[entry["password"]] = counts.get(entry["password"], 0) + 1

        today = datetime.datetime.now()
        report = []
        for site, entry in data.items():
            password = entry["password"]
            issues = []
            strength = check_strength(password)
            if strength != "strong":
                issues.append(f"{strength} password")
            if counts[password] > 1:
                issues.append(f"reused on {counts[password]} sites")
            updated_at = entry.get("updated_at")
            if updated_at:
                age = (today - datetime.datetime.strptime(
                    updated_at, "%Y-%m-%d %H:%M:%S")).days
                if age > stale_days:
                    issues.append(f"unchanged for {age} days")
            if issues:
                report.append({"website": site, "issues": issues})

        report.sort(key=lambda item: -len(item["issues"]))
        return report

    # ── backup support ───────────────────────────────────────────────

    def all_entries_decrypted(self) -> dict:
        """Full plaintext dump — used only for encrypted backup export."""
        return self.load_data()

    def restore_entries(self, entries: dict) -> int:
        """Merge plaintext entries (from a backup) into the vault.
        Existing sites are overwritten. Returns the number restored."""
        data = self.load_data()
        for site, entry in entries.items():
            data[site] = {
                "username": entry["username"],
                "password": entry["password"],
                "notes": entry.get("notes", ""),
                "category": entry.get("category", "Other"),
                "updated_at": entry.get("updated_at") or _now(),
                "history": list(entry.get("history", [])),
            }
        self.save_data(data)
        return len(entries)
