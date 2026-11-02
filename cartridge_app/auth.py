"""Offline shared access-key gate. The key itself is never stored in source."""
from __future__ import annotations

import hashlib
import hmac
from typing import Optional


# Public verifier only. The matching access key is distributed by the owner.
_SALT = bytes.fromhex('cde2fa526fceb9a2320e660bd450b6e9')
_EXPECTED = bytes.fromhex('b499a03ea8b898ad3ec61dde2c7e7db5aabb5b99499165099de39a7c782be96f')
_ITERATIONS = 310_000


def derive_key_digest(key: str, salt: bytes, iterations: Optional[int] = None) -> bytes:
    iterations = _ITERATIONS if iterations is None else iterations
    return hashlib.pbkdf2_hmac('sha256', key.encode('utf-8'), salt, iterations, dklen=32)


def verify_access_key(candidate: str) -> bool:
    """Verify the shared key without embedding its plaintext in the public app."""
    if not isinstance(candidate, str):
        return False
    value = candidate.strip()
    if not value or len(value) > 160:
        return False
    digest = derive_key_digest(value, _SALT)
    return hmac.compare_digest(digest, _EXPECTED)
