"""Authenticate course demonstration users without persisting plaintext codes."""

from hashlib import sha256
import hmac


def authenticate(username: str, code: str, users: dict[str, str]) -> bool:
    digest = sha256(code.encode("utf-8")).hexdigest()
    expected = users.get(username, "0" * 64)
    return bool(username in users and code and hmac.compare_digest(digest, expected))
