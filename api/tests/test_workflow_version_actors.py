"""Each agent version records who made and who published it."""

import itertools

import pytest

from api.db.models import OrganizationModel, UserModel
from api.routes.workflow import _actor_name

_n = itertools.count()
GRAPH = {"nodes": [{"id": "1", "type": "startCall", "data": {"name": "S", "prompt": "hi"}}], "edges": []}


async def _people(async_session, count=2):
    n = next(_n)
    org = OrganizationModel(provider_id=f"act-org-{n}")
    async_session.add(org)
    await async_session.flush()
    users = []
    for i in range(count):
        u = UserModel(
            provider_id=f"act-user-{n}-{i}",
            selected_organization_id=org.id,
            name=f"Person {i}",
            email=f"p{n}{i}@example.com",
        )
        async_session.add(u)
        users.append(u)
    await async_session.flush()
    return org, users


@pytest.mark.asyncio
async def test_the_first_version_names_its_creator(db_session, async_session):
    org, (alice, _) = await _people(async_session)
    wf = await db_session.create_workflow("a", GRAPH, alice.id, organization_id=org.id)
    versions = await db_session.get_workflow_versions(wf.id)

    v1 = versions[0]
    assert (v1.created_by, v1.published_by) == (alice.id, alice.id)
    assert _actor_name(v1.published_by_user) == "Person 0"


@pytest.mark.asyncio
async def test_a_draft_names_who_made_it_and_who_last_changed_it(db_session, async_session):
    org, (alice, bob) = await _people(async_session)
    wf = await db_session.create_workflow("a", GRAPH, alice.id, organization_id=org.id)

    draft = await db_session.save_workflow_draft(wf.id, workflow_definition=GRAPH, actor_id=alice.id)
    assert (draft.created_by, draft.updated_by) == (alice.id, alice.id)

    # Bob edits Alice's draft: the draft keeps its author and gains an editor.
    draft = await db_session.save_workflow_draft(wf.id, workflow_definition=GRAPH, actor_id=bob.id)
    assert (draft.created_by, draft.updated_by) == (alice.id, bob.id)


@pytest.mark.asyncio
async def test_publishing_names_the_publisher_not_the_author(db_session, async_session):
    org, (alice, bob) = await _people(async_session)
    wf = await db_session.create_workflow("a", GRAPH, alice.id, organization_id=org.id)
    await db_session.save_workflow_draft(wf.id, workflow_definition=GRAPH, actor_id=alice.id)

    published = await db_session.publish_workflow_draft(wf.id, actor_id=bob.id)

    assert published.created_by == alice.id
    assert published.published_by == bob.id


@pytest.mark.asyncio
async def test_a_job_with_no_user_does_not_erase_the_editor(db_session, async_session):
    org, (alice, _) = await _people(async_session)
    wf = await db_session.create_workflow("a", GRAPH, alice.id, organization_id=org.id)
    await db_session.save_workflow_draft(wf.id, workflow_definition=GRAPH, actor_id=alice.id)

    draft = await db_session.save_workflow_draft(wf.id, workflow_definition=GRAPH)  # no actor

    assert draft.updated_by == alice.id


@pytest.mark.asyncio
async def test_the_history_list_carries_names_without_lazy_loading(db_session, async_session):
    org, (alice, bob) = await _people(async_session)
    wf = await db_session.create_workflow("a", GRAPH, alice.id, organization_id=org.id)
    await db_session.save_workflow_draft(wf.id, workflow_definition=GRAPH, actor_id=bob.id)

    versions = await db_session.get_workflow_versions(wf.id)

    by_status = {v.status: v for v in versions}
    assert _actor_name(by_status["draft"].created_by_user) == "Person 1"
    assert _actor_name(by_status["published"].published_by_user) == "Person 0"


def test_a_version_with_no_recorded_actor_is_named_by_nobody():
    """Versions that predate the record: nobody can honestly be named."""
    assert _actor_name(None) is None


def test_a_user_with_no_name_falls_back_to_their_email():
    class U:
        name = None
        email = "x@example.com"

    assert _actor_name(U()) == "x@example.com"
