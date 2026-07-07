"""Security helpers for password hashing and JWT handling."""

from datetime import datetime, timedelta

import bcrypt
from jose import jwt

from app.config.settings import settings


def _password_bytes(password: str) -> bytes:
    """Encode and truncate password for bcrypt's 72-byte input limit."""

    password_bytes = password.encode("utf-8")
    return password_bytes[:72]


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""

    return bcrypt.hashpw(_password_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plaintext password against a bcrypt hash."""

    return bcrypt.checkpw(_password_bytes(plain_password), hashed_password.encode("utf-8"))


def create_access_token(data: dict) -> str:
    """Create a signed JWT access token."""

    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token."""

    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
