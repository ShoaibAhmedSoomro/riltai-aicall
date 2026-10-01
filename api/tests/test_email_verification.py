"""Email verification: what the link proves, and what it must never prove.

A verification link says "whoever holds this controls the mailbox". The ways
that claim goes wrong:

  ADDRESS BINDING. If the account's email is changed after the link was sent,
  the old link must not verify the NEW address -- nobody has proved they control
  that one.

  CROSS-USE. A session JWT or a password-reset token is signed with the same
  secret. Neither may verify an address.

  IDEMPOTENCE. Mail scanners pre-fetch links and people double-click. Opening
  it twice must succeed both times and must not move the original timestamp.

  NO FALSE PROOF. An invited user is verified because the invite token only
  ever travelled by email -- but an ordinary signup must NOT be, or the whole
  feature records nothing.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from fastapi import HTTPException

from api.constants import OSS_JWT_SECRET
from api.utils.auth import (
    create_email_verification_token,
    create_jwt_token,
    create_password_reset_token,
    hash_password,
    verify_email_verification_token,
)


def test_a_fresh_token_verifies_the_address_it_was_sent_to():
    token = create_email_verification_token(7, "Sam@Example.com")
    # Case-insensitive: addresses are stored lowercased, signup input is not.
    assert verify_email_verification_token(token, "sam@example.com") == 7


def test_a_link_sent_before_an_email_change_cannot_verify_the_new_address():
    token = create_email_verification_token(7, "old@example.com")
    assert verify_email_verification_token(token, "new@example.com") is None


def test_a_session_token_cannot_verify_an_address():
    assert (
        verify_email_verification_token(create_jwt_token(7, "a@b.com"), "a@b.com")
        is None
    )


def test_a_password_reset_token_cannot_verify_an_address():
    reset = create_password_reset_token(7, hash_password("whatever-pass"))
    assert verify_email_verification_token(reset, "a@b.com") is None


def test_an_expired_token_is_refused():
    expired = jwt.encode(
        {
            "sub": "7",
            "purpose": "email_verify",
            "em": "a@b.com",
            "exp": datetime.now(UTC) - timedelta(minutes=1),
        },
        OSS_JWT_SECRET,
        algorithm="HS256",
    )
    assert verify_email_verification_token(expired, "a@b.com") is None


def test_a_token_signed_with_another_secret_is_refused():
    forged = jwt.encode(
        {"sub": "7", "purpose": "email_verify", "em": "a@b.com"},
        "not-the-real-secret",
        algorithm="HS256",
    )
    assert verify_email_verification_token(forged, "a@b.com") is None


# ── the endpoints ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verifying_marks_the_account_and_is_safe_to_repeat():
    from api.routes import auth
    from api.schemas.auth import VerifyEmailRequest

    user = SimpleNamespace(id=7, email="sam@example.com")
    token = create_email_verification_token(7, "sam@example.com")
    mark = AsyncMock(return_value=user)

    with (
        patch.object(
            auth.db_client, "get_user_by_id", new=AsyncMock(return_value=user)
        ),
        patch.object(auth.db_client, "mark_email_verified", new=mark),
    ):
        first = await auth.verify_email(VerifyEmailRequest(token=token))
        second = await auth.verify_email(VerifyEmailRequest(token=token))

    assert first == second == {"status": "verified"}
    assert mark.await_count == 2  # the DB method is the idempotent part


@pytest.mark.asyncio
async def test_a_link_for_the_old_address_is_rejected_by_the_endpoint():
    from api.routes import auth
    from api.schemas.auth import VerifyEmailRequest

    changed = SimpleNamespace(id=7, email="new@example.com")
    stale = create_email_verification_token(7, "old@example.com")
    mark = AsyncMock()

    with (
        patch.object(
            auth.db_client, "get_user_by_id", new=AsyncMock(return_value=changed)
        ),
        patch.object(auth.db_client, "mark_email_verified", new=mark),
    ):
        with pytest.raises(HTTPException) as raised:
            await auth.verify_email(VerifyEmailRequest(token=stale))

    assert raised.value.status_code == 400
    assert mark.await_count == 0


@pytest.mark.asyncio
async def test_garbage_is_a_400_not_a_500():
    from api.routes import auth
    from api.schemas.auth import VerifyEmailRequest

    with pytest.raises(HTTPException) as raised:
        await auth.verify_email(VerifyEmailRequest(token="not-a-jwt"))
    assert raised.value.status_code == 400


@pytest.mark.asyncio
async def test_resend_says_so_when_email_is_not_configured():
    from api.routes import auth

    user = SimpleNamespace(id=7, email="a@b.com", email_verified_at=None)
    with patch.object(auth, "email_is_configured", return_value=False):
        with pytest.raises(HTTPException) as raised:
            await auth.resend_verification(user)
    assert raised.value.status_code == 503


@pytest.mark.asyncio
async def test_resend_reports_a_failed_send_instead_of_pretending():
    """The user asked for this one, so "check your inbox" for a message that
    never left would be the worst possible answer."""
    from api.routes import auth

    user = SimpleNamespace(id=7, email="a@b.com", email_verified_at=None)
    with (
        patch.object(auth, "email_is_configured", return_value=True),
        patch.object(auth, "PUBLIC_BASE_URL", "https://aicall.test"),
        patch.object(auth, "send_email", new=AsyncMock(return_value=False)),
    ):
        with pytest.raises(HTTPException) as raised:
            await auth.resend_verification(user)
    assert raised.value.status_code == 502


@pytest.mark.asyncio
async def test_resend_does_nothing_for_an_already_verified_account():
    from api.routes import auth

    user = SimpleNamespace(id=7, email="a@b.com", email_verified_at=datetime.now(UTC))
    sent = AsyncMock()
    with patch.object(auth, "send_email", new=sent):
        assert await auth.resend_verification(user) == {"status": "already_verified"}
    assert sent.await_count == 0


@pytest.mark.asyncio
async def test_the_verification_email_carries_a_working_link():
    from api.routes import auth

    user = SimpleNamespace(id=7, email="sam@example.com")
    sent = AsyncMock(return_value=True)
    with (
        patch.object(auth, "email_is_configured", return_value=True),
        patch.object(auth, "send_email", new=sent),
        patch.object(auth, "PUBLIC_BASE_URL", "https://aicall.rilt.ai"),
    ):
        assert await auth._send_verification_email(user) is True

    kwargs = sent.await_args.kwargs
    assert kwargs["to"] == "sam@example.com"
    link = kwargs["text"].split("Confirm email address:\n")[1].split("\n")[0]
    assert link.startswith("https://aicall.rilt.ai/auth/verify-email?token=")
    token = link.split("token=")[1]
    # ...and the link in the message actually verifies THIS account.
    assert verify_email_verification_token(token, "sam@example.com") == 7


@pytest.mark.asyncio
async def test_verifying_twice_keeps_the_first_timestamp(db_session, async_session):
    """The WHERE email_verified_at IS NULL is what makes it idempotent. Without
    it a pre-fetching mail scanner, then the real click, would move the time."""
    from api.db.models import UserModel

    user = UserModel(provider_id="verify-test-1", email="v@example.com")
    async_session.add(user)
    await async_session.flush()
    assert user.email_verified_at is None

    first = await db_session.mark_email_verified(user.id)
    stamped = first.email_verified_at
    assert stamped is not None

    second = await db_session.mark_email_verified(user.id)
    assert second.email_verified_at == stamped


# ── "configured" includes the link base ─────────────────────────────────────


@pytest.mark.parametrize(
    "key, sender, base, expected",
    [
        ("re_x", "AICall <a@b.com>", "https://aicall.rilt.ai", True),
        (None, "AICall <a@b.com>", "https://aicall.rilt.ai", False),
        ("re_x", None, "https://aicall.rilt.ai", False),
        # The case that used to crash: a key and a sender, but no base URL, so
        # every link would be a relative path that goes nowhere from an inbox.
        ("re_x", "AICall <a@b.com>", None, False),
    ],
)
def test_email_needs_a_key_a_sender_and_a_link_base(key, sender, base, expected):
    from api.services import email

    with (
        patch.object(email, "RESEND_API_KEY", key),
        patch.object(email, "EMAIL_FROM", sender),
        patch.object(email, "PUBLIC_BASE_URL", base),
    ):
        assert email.email_is_configured() is expected


@pytest.mark.asyncio
async def test_an_invitation_is_recorded_not_lost_when_email_is_unconfigured():
    """The row is already written when the send is attempted. Rendering a link
    with no base URL used to raise here, leaving a recorded invite and a 500."""
    from api.enums import OrgRole
    from api.routes import organization as org_routes

    me = SimpleNamespace(
        id=1, selected_organization_id=1, email="admin@x.com", name=None
    )
    created = SimpleNamespace(
        id=5,
        email="new@x.com",
        role="member",
        token="tok",
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    with (
        patch.object(
            org_routes.db_client,
            "get_organization_members",
            new=AsyncMock(return_value=[]),
        ),
        patch.object(
            org_routes.db_client, "create_invite", new=AsyncMock(return_value=created)
        ),
        patch.object(org_routes, "email_is_configured", return_value=False),
    ):
        res = await org_routes.create_invite(
            org_routes.CreateInviteRequest(email="new@x.com", role=OrgRole.MEMBER), me
        )

    assert res.delivered is False
