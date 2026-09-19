"""Password reset: the properties that make it safe, not that it works.

Reset is an account-takeover primitive. Everything asserted here is a way it
could hand someone else's account over, or leak who has one:

  SINGLE USE. The token carries a fingerprint of the password hash it was
  minted against, which is what makes it single-use with no table and no
  sweeper. Completing a reset changes the hash, so the spent token -- and any
  older token still sitting in the inbox -- stops verifying. If that
  fingerprint check is dropped, a leaked link works forever.

  PURPOSE-BOUND. A session JWT is signed with the same secret. Without the
  purpose claim, any logged-in user's ordinary token would also reset their
  password, which turns a stolen session token into a permanent takeover
  instead of an expiring one.

  NO ENUMERATION. The unauthenticated endpoint answers identically whether or
  not the address has an account, so it cannot be used to ask whether a given
  person is a customer.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import jwt
import pytest

from api.constants import OSS_JWT_SECRET
from api.utils.auth import (
    create_jwt_token,
    create_password_reset_token,
    hash_password,
    verify_password_reset_token,
)

OLD = hash_password("original-password")
NEW = hash_password("a-brand-new-password")


def test_a_fresh_token_resets_the_account_it_was_minted_for():
    token = create_password_reset_token(7, OLD)
    assert verify_password_reset_token(token, OLD) == 7


def test_the_token_stops_working_once_the_password_has_changed():
    """This is what makes it single use, with no storage of any kind."""
    token = create_password_reset_token(7, OLD)
    assert verify_password_reset_token(token, OLD) == 7
    # The reset completes; the hash is now NEW.
    assert verify_password_reset_token(token, NEW) is None


def test_an_older_outstanding_token_dies_with_the_same_change():
    """Two requests, one used. The unused link must not still be live -- it is
    sitting in an inbox that may be the reason the reset was needed."""
    first = create_password_reset_token(7, OLD)
    second = create_password_reset_token(7, OLD)
    assert verify_password_reset_token(second, OLD) == 7
    assert verify_password_reset_token(first, NEW) is None


def test_a_session_token_cannot_reset_a_password():
    """Signed with the same secret, so only the purpose claim separates them."""
    session = create_jwt_token(7, "someone@example.com")
    assert verify_password_reset_token(session, OLD) is None


def test_an_expired_token_is_refused():
    expired = jwt.encode(
        {
            "sub": "7",
            "purpose": "password_reset",
            "pwf": jwt.decode(
                create_password_reset_token(7, OLD),
                OSS_JWT_SECRET,
                algorithms=["HS256"],
            )["pwf"],
            "exp": datetime.now(UTC) - timedelta(minutes=1),
            "iat": datetime.now(UTC) - timedelta(minutes=31),
        },
        OSS_JWT_SECRET,
        algorithm="HS256",
    )
    assert verify_password_reset_token(expired, OLD) is None


def test_a_token_signed_with_another_secret_is_refused():
    forged = jwt.encode(
        {"sub": "7", "purpose": "password_reset", "pwf": "whatever"},
        "not-the-real-secret",
        algorithm="HS256",
    )
    assert verify_password_reset_token(forged, OLD) is None


def test_a_token_for_one_user_does_not_reset_another():
    """The caller compares the returned id to the user it looked up; this
    pins that the id is the one the token was minted for."""
    token = create_password_reset_token(7, OLD)
    assert verify_password_reset_token(token, OLD) != 8


# ── the endpoint's silence ──────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("user_exists", [True, False])
async def test_forgot_password_answers_the_same_either_way(user_exists):
    from types import SimpleNamespace

    from api.routes import auth
    from api.schemas.auth import ForgotPasswordRequest

    found = (
        SimpleNamespace(id=7, email="someone@example.com", password_hash=OLD)
        if user_exists
        else None
    )
    sent = AsyncMock(return_value=True)

    with (
        patch.object(auth, "email_is_configured", return_value=True),
        patch.object(auth, "send_email", new=sent),
        patch.object(
            auth.db_client, "get_user_by_email", new=AsyncMock(return_value=found)
        ),
    ):
        result = await auth.forgot_password(
            ForgotPasswordRequest(email="someone@example.com")
        )

    assert result == {"status": "sent"}
    # ...and only actually sends when there is somewhere to send it.
    assert sent.await_count == (1 if user_exists else 0)


@pytest.mark.asyncio
async def test_forgot_password_says_so_when_email_is_not_configured():
    """A fact about the deployment, not about any user -- so it IS reported.
    Staying silent here strands the caller waiting for a message that was
    never going to be sent, which is the state this deployment is in today."""
    from fastapi import HTTPException

    from api.routes import auth
    from api.schemas.auth import ForgotPasswordRequest

    with patch.object(auth, "email_is_configured", return_value=False):
        with pytest.raises(HTTPException) as raised:
            await auth.forgot_password(
                ForgotPasswordRequest(email="someone@example.com")
            )

    assert raised.value.status_code == 503
    assert "not configured" in str(raised.value.detail)
