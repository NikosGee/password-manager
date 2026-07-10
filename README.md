# 🔐 Password Manager

A secure, offline desktop password manager built with Python and CustomTkinter. Your entire vault — including site names, usernames, notes, and categories — is encrypted at rest under a key that never touches the disk in plaintext.

<!-- Add a screenshot to make this shine: drop an image at docs/screenshot.png and it will render here -->
<!-- ![Password Manager](docs/screenshot.png) -->

## Features

- **Fully encrypted vault** — the whole vault is stored as a single encrypted blob; the file on disk reveals nothing, not even which sites you have accounts on.
- **Master password + recovery key** — access is protected by your master password, with a one-time random recovery key as the only backup path.
- **Password generator** — cryptographically secure, with guaranteed character-class coverage.
- **Strength meter & health check** — flags weak, reused, and stale passwords across the whole vault.
- **Breach checking** — checks passwords against Have I Been Pwned using k-anonymity (your password never leaves your machine).
- **Encrypted backups** — export/import the vault under a separate passphrase.
- **Password history** — tracks previous passwords per entry, gated behind master-password re-entry.
- **Custom categories, undo/redo, three UI themes** (Twitch, Claude, Default) with light and dark modes.
- **Auto-lock** on inactivity and a persistent lockout after repeated failed logins.

## Security model

Security is the core of this project, so here is exactly how it works:

- A random 256-bit **vault key** encrypts the vault (Fernet / AES-128-CBC + HMAC). This key is never stored in plaintext.
- The vault key is stored **wrapped** (encrypted) twice inside `master.json`: once under a key derived from your master password, and once under a key derived from your recovery key. Either can unlock the vault; neither is stored in recoverable form.
- Keys are derived with **PBKDF2-HMAC-SHA256 at 600,000 iterations** (OWASP-recommended) with a unique random salt per install.
- The master password and recovery key are verified via separate salted PBKDF2 hashes — they are never compared in plaintext.
- All vault and master-file writes are **atomic** (temp file + rename), so a crash mid-write cannot corrupt your data.

Because the vault key exists only wrapped under two secrets, **losing both your master password and recovery key means the vault is unrecoverable by design** — there is no backdoor.

## Tech stack

Python 3 · CustomTkinter (UI) · cryptography (encryption) · tkcalendar · Pillow

## Installation

```bash
# clone
git clone https://github.com/NikosGee/password-manager.git
cd password-manager

# create and activate a virtual environment
python -m venv .venv
# Windows:
.\.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

# install dependencies
pip install -r requirements.txt
```

## Usage

```bash
python main.py
```

On first launch you'll create a master password and receive a one-time recovery key — **write it down and store it safely**, it is shown only once.

## Running the tests

The non-GUI logic (encryption, vault, recovery, categories) is covered by a headless test suite:

```bash
python test_logic.py
```

## Project structure

```
main.py          # entry point
gui.py           # CustomTkinter interface
auth.py          # master credentials, recovery keys, login lockout
crypto.py        # key derivation and vault encryption
manager.py       # encrypted vault storage
backup.py        # encrypted vault export/import
breach.py        # Have I Been Pwned k-anonymity check
generator.py     # secure password generation
strength.py      # password strength estimation
make_icons.py    # generates the UI icon set
test_logic.py    # headless test suite
icons/           # generated UI icons
themes/          # color theme definitions
```

## Scope & disclaimer

This is a personal/educational project. It builds on the well-vetted [`cryptography`](https://cryptography.io) library rather than implementing cryptographic primitives from scratch. It is not audited and is intended for learning and personal use, not as a replacement for a professionally maintained password manager.

## License

Released under the MIT License — see [LICENSE](LICENSE).
