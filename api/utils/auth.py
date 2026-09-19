import hashlib
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from api.constants import (
    OSS_JWT_EXPIRY_HOURS,
    OSS_JWT_SECRET,
    PASSWORD_RESET_EXPIRY_MINUTES,
)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_jwt_token(user_id: int, email: str) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": datetime.now(UTC) + timedelta(hours=OSS_JWT_EXPIRY_HOURS),
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, OSS_JWT_SECRET, algorithm="HS256")


def decode_jwt_token(token: str) -> dict:
    return jwt.decode(token, OSS_JWT_SECRET, algorithms=["HS256"])


# ── password reset ──────────────────────────────────────────────────────────
#
# The reset token is a short-lived JWT rather than a row in a table, and it
# carries a fingerprint of the password hash it was issued against. That
# fingerprint is what makes it SINGLE USE without any storage: completing a
# reset changes the hash, so every token minted against the old one stops
# verifying -- including the one just spent, and including any still sitting
# in the inbox from earlier requests.
#
# The alternative, a password_reset_tokens table, needs a migration, a delete
# on use and a sweeper for the ones nobody spends. This needs none of them.
# The trade it makes: a token cannot be revoked without changing the password,
# so the expiry is kept short.

_RESET_PURPOSE = "password_reset"


def _password_fingerprint(password_hash: str) -> str:
    """A stable, non-reversible marker of the CURRENT password.

    A slice of the bcrypt hash: it changes whenever the password changes,
    which is the only property needed. It is not a secret being widened --
    the token is signed, so this is never readable by the holder.
    """
    return hashlib.sha256(password_hash.encode("utf-8")).hexdigest()[:16]


def create_password_reset_token(user_id: int, password_hash: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "purpose": _RESET_PURPOSE,
        "pwf": _password_fingerprint(password_hash),
        "exp": now + timedelta(minutes=PASSWORD_RESET_EXPIRY_MINUTES),
        "iat": now,
    }
    return jwt.encode(payload, OSS_JWT_SECRET, algorithm="HS256")


def verify_password_reset_token(token: str, password_hash: str) -> int | None:
    """The user id this token resets, or None if it cannot be honoured.

    None covers every rejection -- bad signature, expired, wrong purpose, and
    already-spent -- because the caller must not tell them apart: which one it
    was is information about another person's account.
    """
    try:
        payload = jwt.decode(token, OSS_JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None

    # A session token must not be usable as a reset token. Without this check
    # any logged-in user's own JWT would reset their password -- harmless
    # alone, but it also means a leaked session token becomes an account
    # takeover rather than an expiring nuisance.
    if payload.get("purpose") != _RESET_PURPOSE:
        return None

    if payload.get("pwf") != _password_fingerprint(password_hash):
        return None

    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        return None
