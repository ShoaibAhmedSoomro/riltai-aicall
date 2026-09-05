"""Org-level roles: the gate, and the two rules that keep it from locking people out.

Before this tier existed every member of an organization could do everything —
read the org's provider credentials, delete another member's agents, change
org-wide configuration — because nothing could express that one member differs
from another. `require_admin` is the gate; these tests pin the parts of it that
are easy to get subtly wrong and expensive to get wrong in production.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api.enums import OrgRole
from api.routes import organization as org_routes
from api.services.auth import depends as auth_depends


def _user(user_id=1, org_id=10, is_superuser=False):
    return SimpleNamespace(
        id=user_id,
        selected_organization_id=org_id,
        is_superuser=is_superuser,
        email=f"u{user_id}@example.com",
        name=f"User {user_id}",
    )


def _role_returns(monkeypatch, role):
    monkeypatch.setattr(
        auth_depends.db_client, "get_user_role", AsyncMock(return_value=role)
    )


# ── the gate ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_passes(monkeypatch):
    _role_returns(monkeypatch, OrgRole.ADMIN.value)
    user = _user()
    assert await auth_depends.require_admin(user) is user


@pytest.mark.asyncio
async def test_member_is_refused(monkeypatch):
    _role_returns(monkeypatch, OrgRole.MEMBER.value)
    with pytest.raises(HTTPException) as exc:
        await auth_depends.require_admin(_user())
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_superuser_passes_without_holding_the_org_role(monkeypatch):
    """The platform tier spans every org, and is how support acts inside one.

    Checked BEFORE the role lookup: a superuser acting in an org they were never
    a member of has no row to read, so requiring one would lock the platform
    owner out of the tier that exists for exactly this.
    """
    lookup = AsyncMock(return_value=OrgRole.MEMBER.value)
    monkeypatch.setattr(auth_depends.db_client, "get_user_role", lookup)
    user = _user(is_superuser=True)
    assert await auth_depends.require_admin(user) is user
    lookup.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_null_is_superuser_is_not_mistaken_for_true(monkeypatch):
    # is_superuser was added nullable with no backfill, so rows predating it
    # hold NULL rather than False. A truthiness check handles that; an
    # `is False` check would misread NULL and grant the tier.
    _role_returns(monkeypatch, OrgRole.MEMBER.value)
    user = _user()
    user.is_superuser = None
    with pytest.raises(HTTPException) as exc:
        await auth_depends.require_admin(user)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_missing_membership_row_resolves_to_admin(monkeypatch):
    """The rule that stops this shipping as an outage.

    API-key auth sets selected_organization_id in memory with no membership row
    at all, and the hosted path skips its INSERT when the selected org already
    matches. Those callers could do everything before roles existed, so absence
    has to mean admin — denying them would break working installs on deploy.
    """
    _role_returns(monkeypatch, None)
    assert await auth_depends.get_org_role(_user()) == OrgRole.ADMIN.value
    user = _user()
    assert await auth_depends.require_admin(user) is user


# ── the last-admin guard ────────────────────────────────────────────────────


def _patch_members(monkeypatch, members, admins, updated=True):
    monkeypatch.setattr(
        org_routes.db_client, "get_organization_members", AsyncMock(return_value=members)
    )
    monkeypatch.setattr(
        org_routes.db_client, "count_admins", AsyncMock(return_value=admins)
    )
    setter = AsyncMock(return_value=updated)
    monkeypatch.setattr(org_routes.db_client, "set_user_role", setter)
    return setter


@pytest.mark.asyncio
async def test_cannot_demote_the_only_admin(monkeypatch):
    """An org with no admin cannot be administered through the product again.

    There is no invite flow and no ownership transfer to recover with, so this
    would need database surgery. Self-demotion is the likeliest way to get here.
    """
    me = _user()
    setter = _patch_members(monkeypatch, [(me, OrgRole.ADMIN.value)], admins=1)
    with pytest.raises(HTTPException) as exc:
        await org_routes.update_member_role(
            me.id, org_routes.MemberRoleUpdateRequest(role=OrgRole.MEMBER), me
        )
    assert exc.value.status_code == 400
    setter.assert_not_awaited()


@pytest.mark.asyncio
async def test_can_demote_an_admin_when_another_remains(monkeypatch):
    me, other = _user(1), _user(2)
    setter = _patch_members(
        monkeypatch,
        [(me, OrgRole.ADMIN.value), (other, OrgRole.ADMIN.value)],
        admins=2,
    )
    res = await org_routes.update_member_role(
        other.id, org_routes.MemberRoleUpdateRequest(role=OrgRole.MEMBER), me
    )
    assert res.role == OrgRole.MEMBER.value
    setter.assert_awaited_once()


@pytest.mark.asyncio
async def test_promoting_is_never_blocked_by_the_guard(monkeypatch):
    # The guard must only fire on admin -> lesser. A sole admin promoting a
    # member is how you escape the guard, so it must not be blocked by it.
    me, other = _user(1), _user(2)
    setter = _patch_members(
        monkeypatch,
        [(me, OrgRole.ADMIN.value), (other, OrgRole.MEMBER.value)],
        admins=1,
    )
    res = await org_routes.update_member_role(
        other.id, org_routes.MemberRoleUpdateRequest(role=OrgRole.ADMIN), me
    )
    assert res.role == OrgRole.ADMIN.value
    setter.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_user_from_another_org_is_not_found(monkeypatch):
    """Tenant isolation: the path parameter is an arbitrary user id.

    Membership is proved from THIS org's member list before anything is written,
    so an admin of one org cannot set roles in another.
    """
    me = _user(1)
    setter = _patch_members(monkeypatch, [(me, OrgRole.ADMIN.value)], admins=1)
    with pytest.raises(HTTPException) as exc:
        await org_routes.update_member_role(
            999, org_routes.MemberRoleUpdateRequest(role=OrgRole.MEMBER), me
        )
    assert exc.value.status_code == 404
    setter.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_unknown_role_is_rejected_before_it_reaches_the_column():
    with pytest.raises(Exception):
        org_routes.MemberRoleUpdateRequest(role="superadmin")
