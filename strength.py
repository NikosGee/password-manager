"""Password strength estimation."""

import re

# A few patterns that make otherwise "complex" passwords weak.
COMMON_PASSWORDS = {
    "password", "password1", "password123", "123456", "12345678", "123456789",
    "qwerty", "qwerty123", "abc123", "letmein", "welcome", "admin", "iloveyou",
    "monkey", "dragon", "master", "sunshine", "football",
}


def check_strength(password: str) -> str:
    """Returns "weak", "medium", or "strong"."""
    if not password:
        return "weak"

    lowered = password.lower()
    if lowered in COMMON_PASSWORDS:
        return "weak"

    length = len(password)
    has_upper = bool(re.search(r"[A-Z]", password))
    has_lower = bool(re.search(r"[a-z]", password))
    has_digit = bool(re.search(r"[0-9]", password))
    has_symbol = bool(re.search(r"[^A-Za-z0-9]", password))

    score = 0
    if length >= 8:
        score += 1
    if length >= 12:
        score += 1
    if length >= 16:
        score += 1
    score += sum([has_upper, has_lower, has_digit, has_symbol])

    # Penalties for lazy patterns.
    if any(common in lowered for common in COMMON_PASSWORDS if len(common) >= 6):
        score -= 2
    if len(set(password)) <= 2:
        score = min(score, 2)
    if re.fullmatch(r"(.)\1*", password):
        score = min(score, 1)

    if score >= 6:
        return "strong"
    if score >= 4:
        return "medium"
    return "weak"
