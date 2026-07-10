"""Cryptographically secure password generation."""

import secrets
import string

# Character classes; the generated password contains at least one of each.
CLASSES = [string.ascii_lowercase, string.ascii_uppercase,
           string.digits, string.punctuation]


def generate_password(length: int = 24) -> str:
    if length < len(CLASSES):
        raise ValueError(f"length must be at least {len(CLASSES)}")

    all_chars = "".join(CLASSES)

    # One guaranteed character per class, the rest fully random...
    chars = [secrets.choice(cls) for cls in CLASSES]
    chars += [secrets.choice(all_chars) for _ in range(length - len(chars))]

    # ...then shuffle so the guaranteed characters aren't always first.
    for i in range(len(chars) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        chars[i], chars[j] = chars[j], chars[i]

    return "".join(chars)
