"""The agents list says what is live and whether there is unpublished work."""

import itertools
from types import SimpleNamespace

import pytest

from api.db.models import OrganizationModel, UserModel
from api.routes import workflow as routes

_n = itertools.count()
GRAPH = {"nodes": [{"id": "1", "type": "startCall", "data": {"name": "S", "prompt": "hi"}}], "edges": []}


async def _tenant(async_session):
    n = next(_n)
    org = OrganizationModel(provider_id=f"wl-org-{n}")
    async_session.add(org)
    await async_session.flush()
    user = UserModel(provider_id=f"wl-user-{n}", selected_organization_id=org.id)
    async_session.add(user)
    await async_session.flush()
    return org, user


async def _list(user, org):
    return {
        w.name: w
        for w in await routes.get_workflows(
            user=SimpleNamespace(selected_organization_id=org.id, id=user.id), status=None
        )
    }


@pytest.mark.asyncio
async def test_a_published_agent_with_no_draft_is_just_live(db_session, async_session):
    org, user = await _tenant(async_session)
    await db_session.create_workflow("Live", GRAPH, user.id, organization_id=org.id)

    row = (await _list(user, org))["Live"]

    assert row.released_version_number == 1
    assert row.has_unpublished_draft is False


@pytest.mark.asyncio
async def test_editing_an_agent_shows_a_draft_while_the_live_version_stays(db_session, async_session):
    org, user = await _tenant(async_session)
    wf = await db_session.create_workflow("Editing", GRAPH, user.id, organization_id=org.id)
    await db_session.save_workflow_draft(wf.id, workflow_definition=GRAPH, actor_id=user.id)

    row = (await _list(user, org))["Editing"]

    assert row.released_version_number == 1  # what a call runs today
    assert row.has_unpublished_draft is True  # what the editor opens


@pytest.mark.asyncio
async def test_publishing_moves_the_live_version_and_clears_the_draft(db_session, async_session):
    org, user = await _tenant(async_session)
    wf = await db_session.create_workflow("Ship", GRAPH, user.id, organization_id=org.id)
    await db_session.save_workflow_draft(wf.id, workflow_definition=GRAPH, actor_id=user.id)
    await db_session.publish_workflow_draft(wf.id, actor_id=user.id)

    row = (await _list(user, org))["Ship"]

    assert row.released_version_number == 2
    assert row.has_unpublished_draft is False


@pytest.mark.asyncio
async def test_each_agent_is_judged_on_its_own_versions(db_session, async_session):
    org, user = await _tenant(async_session)
    a = await db_session.create_workflow("A", GRAPH, user.id, organization_id=org.id)
    await db_session.create_workflow("B", GRAPH, user.id, organization_id=org.id)
    await db_session.save_workflow_draft(a.id, workflow_definition=GRAPH, actor_id=user.id)

    rows = await _list(user, org)

    assert rows["A"].has_unpublished_draft is True
    assert rows["B"].has_unpublished_draft is False


@pytest.mark.asyncio
async def test_the_bulk_lookups_cope_with_nothing(db_session):
    assert await db_session.get_draft_workflow_ids([]) == set()
    assert await db_session.get_released_version_numbers([]) == {}
