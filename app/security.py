import hashlib
import secrets
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError

hasher = PasswordHasher()
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))

def hash_password(password: str) -> str:
    if not 12 <= len(password) <= 256:
        raise ValueError("Password must contain 12 to 256 characters")
    return hasher.hash(password)

def verify_password(encoded: str, password: str) -> bool:
    try:
        return hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False

def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
