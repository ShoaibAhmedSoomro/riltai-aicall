"""Organization invites: who can create them, and what makes one acceptable.

There was no invite path at all before this, so an OSS organization could never
gain a second person and the admin/member tier was real in the database and
unusable in the product.

Delivery is deliberately absent — nothing in this codebase can send email — so
the token is generated and stored but never transmitted. That makes the
acceptance rules the part worth pinning: an invite that is honoured when it
should not be silently hands someone access to another organization's calls,
credentials and recordings.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api.db.organization_invite_client import normalize_invite_email
from api.enums import OrgRole
from api.routes import auth as auth_routes
from api.routes import organization as org_routes
from api.schemas.auth import SignupRequest


def _admin(user_id=1, org_id=10):
    return SimpleNamespace(
        id=user_id,
        selected_organization_id=org_id,
        is_superuser=False,
        email="admin@x.com",
        name="Admin",
    )


# ── email normalisation ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("  A@X.com ", "a@x.com"),
        ("b@x.com", "b@x.com"),
        ("MiXeD@Case.IO", "mixed@case.io"),
    ],
)
def test_invite_emails_are_normalised(raw, expected):
    # Every email lookup in this codebase is an exact match, so an invite stored
    # as "A@x.com" would never be found by a signup as "a@x.com".
    assert normalize_invite_email(raw) == expected


# ── creating ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_inviting_an_existing_member_is_refused(monkeypatch):
    me = _admin()
    monkeypatch.setattr(
        org_routes.db_client,
        "get_organization_members",
        AsyncMock(return_value=[(SimpleNamespace(id=2, email="Bob@X.com"), "member")]),
    )
    create = AsyncMock()
    monkeypatch.setattr(org_routes.db_client, "create_invite", create)
    with pytest.raises(HTTPException) as exc:
        await org_routes.create_invite(
            org_routes.CreateInviteRequest(email="bob@x.com"), me
        )
    assert exc.value.status_code == 409
    # Case-insensitively: the member list is not normalised, the comparison is.
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_default_role_is_member(monkeypatch):
    # The safe tier is the one you get by not thinking about it.
    assert org_routes.CreateInviteRequest(email="x@y.com").role is OrgRole.MEMBER


@pytest.mark.asyncio
async def test_an_admin_can_invite_a_co_admin(monkeypatch):
    me = _admin()
    monkeypatch.setattr(
        org_routes.db_client, "get_organization_members", AsyncMock(return_value=[])
    )
    created = SimpleNamespace(
        id=5,
        email="new@x.com",
        role="admin",
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    create = AsyncMock(return_value=created)
    monkeypatch.setattr(org_routes.db_client, "create_invite", create)
    res = await org_routes.create_invite(
        org_routes.CreateInviteRequest(email="new@x.com", role=OrgRole.ADMIN), me
    )
    assert res.role == "admin"
    assert create.await_args.kwargs["role"] == "admin"


@pytest.mark.asyncio
async def test_the_token_is_never_returned_to_the_client(monkeypatch):
    """Returning it would quietly turn this into a copy-a-link flow.

    That shape was considered and not chosen; the token exists so that adding
    email later is only the sending step.
    """
    me = _admin()
    monkeypatch.setattr(
        org_routes.db_client, "get_organization_members", AsyncMock(return_value=[])
    )
    created = SimpleNamespace(
        id=5,
        email="new@x.com",
        role="member",
        token="inv_supersecret",
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    monkeypatch.setattr(
        org_routes.db_client, "create_invite", AsyncMock(return_value=created)
    )
    res = await org_routes.create_invite(
        org_routes.CreateInviteRequest(email="new@x.com"), me
    )
    assert "inv_supersecret" not in res.model_dump_json()
    assert not hasattr(res, "token")


# ── revoking ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_revoking_is_scoped_to_your_own_organization(monkeypatch):
    # invite_id arrives from a URL and proves nothing about ownership.
    me = _admin()
    revoke = AsyncMock(return_value=False)
    monkeypatch.setattr(org_routes.db_client, "revoke_invite", revoke)
    with pytest.raises(HTTPException) as exc:
        await org_routes.revoke_invite(999, me)
    assert exc.value.status_code == 404
    assert revoke.await_args.args[1] == me.selected_organization_id


# ── accepting, via signup ───────────────────────────────────────────────────


def _signup_deps(monkeypatch, *, invite, enable_signup=True):
    monkeypatch.setattr(auth_routes, "ENABLE_SIGNUP", enable_signup)
    monkeypatch.setattr(
        auth_routes.db_client, "get_acceptable_invite", AsyncMock(return_value=invite)
    )
    monkeypatch.setattr(
        auth_routes.db_client, "get_user_by_email", AsyncMock(return_value=None)
    )


@pytest.mark.asyncio
async def test_an_unusable_invite_is_refused_without_saying_why(monkeypatch):
    """Unknown, revoked, used and expired all give the same message.

    signup is unauthenticated, so distinguishing them would let anyone probe
    which tokens exist.
    """
    _signup_deps(monkeypatch, invite=None)
    with pytest.raises(HTTPException) as exc:
        await auth_routes.signup(
            SignupRequest(email="a@x.com", password="password1", invite_token="inv_x")
        )
    assert exc.value.status_code == 400
    assert "no longer valid" in exc.value.detail


@pytest.mark.asyncio
async def test_an_invite_cannot_be_redeemed_by_a_different_address(monkeypatch):
    # Otherwise a leaked token is a free account in someone else's org.
    invite = SimpleNamespace(
        id=1, email="invited@x.com", role="member", organization_id=10
    )
    _signup_deps(monkeypatch, invite=invite)
    with pytest.raises(HTTPException) as exc:
        await auth_routes.signup(
            SignupRequest(
                email="attacker@x.com", password="password1", invite_token="inv_x"
            )
        )
    assert exc.value.status_code == 400
    assert "different email" in exc.value.detail


@pytest.mark.asyncio
async def test_signup_stays_closed_without_an_invite_when_disabled(monkeypatch):
    _signup_deps(monkeypatch, invite=None, enable_signup=False)
    with pytest.raises(HTTPException) as exc:
        await auth_routes.signup(SignupRequest(email="a@x.com", password="password1"))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_an_invite_opens_signup_on_an_invite_only_install(monkeypatch):
    """ENABLE_SIGNUP=false means invite-only, not closed.

    An invitation is exactly the permission that flag withholds from the public,
    so refusing an invited person would make the setting useless rather than
    strict.
    """
    invite = SimpleNamespace(id=1, email="a@x.com", role="member", organization_id=10)
    _signup_deps(monkeypatch, invite=invite, enable_signup=False)

    user = SimpleNamespace(
        id=7,
        provider_id="oss_7",
        email="a@x.com",
        name=None,
        profile={},
        created_at=None,
        is_superuser=False,
    )
    monkeypatch.setattr(auth_routes, "hash_password", lambda p: "h")
    monkeypatch.setattr(
        auth_routes.db_client, "create_user_with_email", AsyncMock(return_value=user)
    )
    monkeypatch.setattr(
        auth_routes.db_client, "mark_invite_accepted", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        auth_routes.db_client,
        "get_organization_by_id",
        AsyncMock(return_value=SimpleNamespace(id=10)),
    )
    link = AsyncMock()
    monkeypatch.setattr(auth_routes.db_client, "add_user_to_organization", link)
    monkeypatch.setattr(
        auth_routes.db_client, "update_user_selected_organization", AsyncMock()
    )
    monkeypatch.setattr(auth_routes, "ensure_organization_bootstrapped", AsyncMock())
    monkeypatch.setattr(auth_routes, "create_jwt_token", lambda *a: "tok")
    monkeypatch.setattr(auth_routes, "capture_event", lambda **k: None)
    personal_org = AsyncMock()
    monkeypatch.setattr(
        auth_routes.db_client, "get_or_create_organization_by_provider_id", personal_org
    )

    res = await auth_routes.signup(
        SignupRequest(email="a@x.com", password="password1", invite_token="inv_x")
    )

    assert res.token == "tok"
    # Joined the inviting org with the invited role...
    assert link.await_args.args[1] == 10
    assert link.await_args.kwargs["role"] == "member"
    # ...and did NOT get a personal organization of their own.
    personal_org.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_consumed_invite_cannot_be_used_twice(monkeypatch):
    """mark_invite_accepted is conditional, so the loser of a race gets False.

    Without honouring that return value, two concurrent signups on one token
    would both produce a membership.
    """
    invite = SimpleNamespace(id=1, email="a@x.com", role="member", organization_id=10)
    _signup_deps(monkeypatch, invite=invite)
    user = SimpleNamespace(
        id=7,
        provider_id="oss_7",
        email="a@x.com",
        name=None,
        profile={},
        created_at=None,
        is_superuser=False,
    )
    monkeypatch.setattr(auth_routes, "hash_password", lambda p: "h")
    monkeypatch.setattr(
        auth_routes.db_client, "create_user_with_email", AsyncMock(return_value=user)
    )
    monkeypatch.setattr(
        auth_routes.db_client, "mark_invite_accepted", AsyncMock(return_value=False)
    )
    link = AsyncMock()
    monkeypatch.setattr(auth_routes.db_client, "add_user_to_organization", link)

    with pytest.raises(HTTPException) as exc:
        await auth_routes.signup(
            SignupRequest(email="a@x.com", password="password1", invite_token="inv_x")
        )
    assert exc.value.status_code == 400
    link.assert_not_awaited()
