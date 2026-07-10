"""Check passwords against the Have I Been Pwned database.

Uses the k-anonymity range API: only the first 5 characters of the
password's SHA-1 hash ever leave the machine, so HIBP never sees the
password (or even enough of the hash to identify it).
"""

import hashlib
import urllib.error
import urllib.request

API_URL = "https://api.pwnedpasswords.com/range/"
TIMEOUT = 8  # seconds


def check_breach(password: str) -> int | None:
    """Returns how many times the password appears in known breaches
    (0 = not found), or None if the check couldn't be performed
    (offline, timeout, API error)."""
    sha1 = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    prefix, suffix = sha1[:5], sha1[5:]

    request = urllib.request.Request(
        API_URL + prefix,
        headers={"User-Agent": "PersonalPasswordManager"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            body = response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError):
        return None

    for line in body.splitlines():
        candidate, _, count = line.partition(":")
        if candidate.strip() == suffix:
            return int(count.strip())
    return 0
