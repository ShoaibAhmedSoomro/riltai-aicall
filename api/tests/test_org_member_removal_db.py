"""Removal against a real database, because the risk is in the second write.

Deleting the association row is the obvious half. On its own it does not remove
access and it *raises* the removed user's privileges:

* `get_user_with_selected_organization` only checks that
  `users.selected_organization_id` is set. It never reads the association table,
  so every org-scoped handler keeps serving someone whose row is gone.
* `get_org_role` resolves a missing row to ADMIN on purpose, because API-key
  auth legitimately has no row. A removed *member* therefore comes back as an
  *admin* of the org they were just thrown out of.

Mocks cannot show that: the two writes happen inside one db_client method, and a
test that stubs the method asserts only that it was called. So these run against
the test database and read the rows back.
"""

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from api.db.models import (
    OrganizationModel,
    UserModel,
    organization_users_association,
)
from api.enums import OrgRole
from api.services.auth.depends import (
    get_org_role,
    get_user_with_selected_organization,
)


async def _org(async_session, suffix):
    org = OrganizationModel(provider_id=f"removal-org-{suffix}")
    async_session.add(org)
    await async_session.flush()
    return org


async def _member(async_session, org, suffix, role=OrgRole.MEMBER.value):
    user = UserModel(
        provider_id=f"removal-user-{suffix}", selected_organization_id=org.id
    )
    async_session.add(user)
    await async_session.flush()
    await async_session.execute(
        organization_users_association.insert().values(
            user_id=user.id, organization_id=org.id, role=role
        )
    )
    return user


async def _selected_org(async_session, user_id):
    return await async_session.scalar(
        select(UserModel.selected_organization_id).where(UserModel.id == user_id)
    )


async def _has_row(async_session, user_id, org_id):
    return (
        await async_session.scalar(
            select(organization_users_association.c.role).where(
                organization_users_association.c.user_id == user_id,
                organization_users_association.c.organization_id == org_id,
            )
        )
    ) is not None


@pytest.mark.asyncio
async def test_removal_does_not_leave_the_user_an_admin(db_session, async_session):
    """The whole point. Delete the row and stop there and this test fails.

    With only the DELETE, get_org_role finds no row, falls through to its
    deliberate ADMIN default, and the person just removed can now do strictly
    more than they could as a member.
    """
    org = await _org(async_session, "escalation")
    user = await _member(async_session, org, "escalation")

    assert await get_org_role(user) == OrgRole.MEMBER.value

    assert await db_session.remove_user_from_organization(user.id, org.id) is True

    assert await _has_row(async_session, user.id, org.id) is False
    assert await _selected_org(async_session, user.id) is None

    # And the access itself is gone, not merely the row: refreshed from the DB,
    # this user no longer resolves an organization at all.
    user.selected_organization_id = await _selected_org(async_session, user.id)
    with pytest.raises(HTTPException) as exc:
        await get_user_with_selected_organization(user)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_a_user_in_two_orgs_is_moved_to_the_other_one(db_session, async_session):
    """Clearing unconditionally would evict them from an org they are still in."""
    kept = await _org(async_session, "kept")
    left = await _org(async_session, "left")
    user = await _member(async_session, kept, "twoorgs")
    await async_session.execute(
        organization_users_association.insert().values(
            user_id=user.id, organization_id=left.id, role=OrgRole.MEMBER.value
        )
    )
    await async_session.execute(
        UserModel.__table__.update()
        .where(UserModel.id == user.id)
        .values(selected_organization_id=left.id)
    )

    assert await db_session.remove_user_from_organization(user.id, left.id) is True

    assert await _selected_org(async_session, user.id) == kept.id
    assert await _has_row(async_session, user.id, kept.id) is True


@pytest.mark.asyncio
async def test_removal_from_an_unselected_org_leaves_the_current_one_alone(
    db_session, async_session
):
    """Being removed from a background org must not interrupt the current one.

    Deliberately three orgs, with the selected one NOT the lowest id. With only
    two, the fallback the unguarded UPDATE would pick happens to be the org the
    user is already in, so both the correct and the broken version agree and the
    test proves nothing -- which is exactly what it did until a mutant survived.
    """
    first = await _org(async_session, "first")
    middle = await _org(async_session, "middle")
    current = await _org(async_session, "current")
    user = await _member(async_session, current, "unselected")
    for org in (first, middle):
        await async_session.execute(
            organization_users_association.insert().values(
                user_id=user.id, organization_id=org.id, role=OrgRole.MEMBER.value
            )
        )

    assert await db_session.remove_user_from_organization(user.id, middle.id) is True

    # An unconditional clear would move them to `first`, the lowest remaining id.
    assert await _selected_org(async_session, user.id) == current.id


@pytest.mark.asyncio
async def test_removing_a_non_member_changes_nothing(db_session, async_session):
    """False, and no write -- otherwise a bad id knocks a user out of their org."""
    org = await _org(async_session, "nonmember")
    stranger_org = await _org(async_session, "stranger")
    stranger = await _member(async_session, stranger_org, "stranger")

    assert await db_session.remove_user_from_organization(stranger.id, org.id) is False

    assert await _selected_org(async_session, stranger.id) == stranger_org.id
    assert await _has_row(async_session, stranger.id, stranger_org.id) is True
