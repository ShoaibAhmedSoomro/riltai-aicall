"""Seeding the catalog, listing it as a gallery, previewing one, and cloning one."""

import itertools
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.db.models import OrganizationModel, UserModel
from api.db.workflow_template_client import WorkflowTemplateClient
from api.routes import workflow as routes
from api.services.workflow import template_catalog

_n = itertools.count()


@pytest.fixture
def client(db_session, monkeypatch):
    """A template client on the test session, used by the routes and the seeder."""

    def make():
        c = WorkflowTemplateClient()
        c.async_session = db_session.async_session
        return c

    monkeypatch.setattr(routes, "WorkflowTemplateClient", make)
    monkeypatch.setattr("api.db.workflow_template_client.WorkflowTemplateClient", make)
    return make()


async def _user(async_session):
    n = next(_n)
    org = OrganizationModel(provider_id=f"tpl-org-{n}")
    async_session.add(org)
    await async_session.flush()
    user = UserModel(provider_id=f"tpl-user-{n}", selected_organization_id=org.id)
    async_session.add(user)
    await async_session.flush()
    return user


@pytest.mark.asyncio
async def test_seeding_writes_the_whole_catalog_and_is_safe_to_repeat(db_session, client):
    first = await template_catalog.seed_catalog()
    second = await template_catalog.seed_catalog()

    rows = await client.get_all_workflow_templates()
    assert first == second == len(template_catalog.CATEGORIES)
    assert sorted(r.slug for r in rows) == sorted(template_catalog.CATEGORIES)  # no duplicates after two boots


@pytest.mark.asyncio
async def test_seeding_again_refreshes_reworded_text_instead_of_adding_a_row(db_session, client):
    await template_catalog.seed_catalog()
    row = await client.get_workflow_template_by_slug("receptionist")
    await client.update_workflow_template(row.id, template_name="Old name", template_description="Old text")

    await template_catalog.seed_catalog()

    again = await client.get_workflow_template_by_slug("receptionist")
    assert again.id == row.id
    assert again.template_name == "Front Desk Receptionist"


@pytest.mark.asyncio
async def test_list_is_a_gallery_without_the_heavy_definitions(db_session, async_session, client):
    await template_catalog.seed_catalog()
    user = await _user(async_session)

    out = await routes.get_workflow_templates(category=None, user=user)

    assert len(out) == len(template_catalog.CATEGORIES)
    assert "template_json" not in routes.WorkflowTemplateResponse.model_fields
    assert {t.category for t in out} == set(template_catalog.CATEGORIES)


@pytest.mark.asyncio
async def test_list_filters_by_category_in_the_query(db_session, async_session, client):
    await template_catalog.seed_catalog()
    user = await _user(async_session)

    out = await routes.get_workflow_templates(category="appointment-booking", user=user)

    assert [t.slug for t in out] == ["appointment-booking"]
    assert await routes.get_workflow_templates(category="nope", user=user) == []


@pytest.mark.asyncio
async def test_preview_returns_the_full_definition_or_404(db_session, async_session, client):
    await template_catalog.seed_catalog()
    user = await _user(async_session)
    card = (await routes.get_workflow_templates(category="receptionist", user=user))[0]

    detail = await routes.get_workflow_template(card.id, user)
    assert detail.template_json["nodes"] and detail.template_json["edges"]

    with pytest.raises(HTTPException) as e:
        await routes.get_workflow_template(card.id + 9999, user)
    assert e.value.status_code == 404


@pytest.mark.asyncio
async def test_cloning_a_template_gives_the_user_their_own_agent(db_session, async_session, client):
    await template_catalog.seed_catalog()
    user = await _user(async_session)
    card = (await routes.get_workflow_templates(category="customer-support", user=user))[0]

    created = await routes.duplicate_workflow_template(
        routes.DuplicateTemplateRequest(template_id=card.id, workflow_name="My support agent"), user
    )

    assert created["name"] == "My support agent"
    node_types = [n["type"] for n in created["workflow_definition"]["nodes"]]
    assert node_types.count("startCall") == 1 and "endCall" in node_types
    # The template row is untouched by being cloned.
    assert (await routes.get_workflow_template(card.id, user)).slug == "customer-support"
