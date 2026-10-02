"""A saved contact list as a campaign source."""

import itertools
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.db.models import OrganizationModel, UserModel
from api.services.campaign.source_sync import CampaignSourceSyncService
from api.services.campaign.source_sync_factory import get_sync_service
from api.services.campaign.sources import contact_list as source_mod
from api.services.campaign.sources.contact_list import ContactListSyncService

_n = itertools.count()


async def _org_with_list(db_session, async_session, people):
    n = next(_n)
    org = OrganizationModel(provider_id=f"cl-org-{n}")
    async_session.add(org)
    await async_session.flush()
    async_session.add(UserModel(provider_id=f"cl-user-{n}", selected_organization_id=org.id))
    await async_session.flush()

    lst = await db_session.create_contact_list(org.id, name="Leads")
    ids = []
    for phone, first, attrs in people:
        c = await db_session.create_contact(
            org.id, phone_number=phone, phone_e164=phone, first_name=first, attributes=attrs
        )
        ids.append(c.id)
    await db_session.add_contacts_to_list(lst.id, org.id, ids)
    return org, lst


def test_the_factory_knows_the_new_source():
    assert isinstance(get_sync_service("contact_list"), ContactListSyncService)


@pytest.mark.asyncio
async def test_validation_exposes_every_custom_field_as_a_column(db_session, async_session):
    org, lst = await _org_with_list(
        db_session,
        async_session,
        [("+971501111111", "Ana", {"company": "Acme"}), ("+971502222222", "Bob", {"plan": "gold"})],
    )

    result = await ContactListSyncService().validate_source(lst.list_uuid, org.id)

    assert result.is_valid
    assert result.headers[:4] == ["phone_number", "first_name", "last_name", "email"]
    assert {"company", "plan"} <= set(result.headers)


@pytest.mark.asyncio
async def test_the_existing_template_check_fails_fast_when_the_list_cannot_supply_a_field(
    db_session, async_session
):
    org, lst = await _org_with_list(
        db_session, async_session, [("+971501111111", "Ana", {"company": "Acme"})]
    )
    result = await ContactListSyncService().validate_source(lst.list_uuid, org.id)

    needs_plan = CampaignSourceSyncService.validate_template_columns(
        result.headers, result.rows, {"plan"}
    )
    needs_company = CampaignSourceSyncService.validate_template_columns(
        result.headers, result.rows, {"company", "first_name"}
    )

    assert not needs_plan.is_valid and "plan" in needs_plan.error.message
    assert needs_company.is_valid


@pytest.mark.asyncio
async def test_a_field_one_contact_lacks_is_caught_too(db_session, async_session):
    org, lst = await _org_with_list(
        db_session,
        async_session,
        [("+971501111111", "Ana", {"company": "Acme"}), ("+971502222222", "Bob", {})],
    )
    result = await ContactListSyncService().validate_source(lst.list_uuid, org.id)
    check = CampaignSourceSyncService.validate_template_columns(
        result.headers, result.rows, {"company"}
    )
    assert not check.is_valid and "company" in check.error.message


@pytest.mark.asyncio
async def test_a_missing_or_empty_list_is_refused(db_session, async_session):
    org, lst = await _org_with_list(db_session, async_session, [])
    svc = ContactListSyncService()

    empty = await svc.validate_source(lst.list_uuid, org.id)
    missing = await svc.validate_source("nope", org.id)

    assert not empty.is_valid and "no contacts" in empty.error.message
    assert not missing.is_valid and "not found" in missing.error.message


@pytest.mark.asyncio
async def test_another_organizations_list_is_not_found(db_session, async_session):
    org, lst = await _org_with_list(db_session, async_session, [("+971501111111", "Ana", {})])
    other, _ = await _org_with_list(db_session, async_session, [("+971502222222", "Bob", {})])

    result = await ContactListSyncService().validate_source(lst.list_uuid, other.id)

    assert not result.is_valid


@pytest.fixture
def capture(monkeypatch):
    queued = []

    async def bulk(runs):
        queued.extend(runs)

    monkeypatch.setattr(source_mod.db_client, "bulk_create_queued_runs", bulk)
    monkeypatch.setattr(source_mod.db_client, "update_campaign", AsyncMock())
    monkeypatch.setattr(source_mod.db_client, "append_campaign_log", AsyncMock())
    return queued


@pytest.mark.asyncio
async def test_sync_queues_one_run_per_non_suppressed_member(db_session, async_session, monkeypatch, capture):
    org, lst = await _org_with_list(
        db_session,
        async_session,
        [
            ("+971501111111", "Ana", {"company": "Acme"}),
            ("+971502222222", "Bob", {}),
            ("+971503333333", "Cy", {}),
        ],
    )
    await db_session.add_suppressions_batch(org.id, ["+971502222222"])
    monkeypatch.setattr(
        source_mod.db_client,
        "get_campaign_by_id",
        AsyncMock(return_value=SimpleNamespace(id=5, organization_id=org.id, source_id=lst.list_uuid)),
    )

    count = await ContactListSyncService().sync_source_data(5)

    assert count == 2
    phones = {r["context_variables"]["phone_number"] for r in capture}
    assert phones == {"+971501111111", "+971503333333"}  # Bob is not queued


@pytest.mark.asyncio
async def test_each_run_is_stably_keyed_to_the_person_and_carries_their_fields(
    db_session, async_session, monkeypatch, capture
):
    org, lst = await _org_with_list(
        db_session, async_session, [("+971501111111", "Ana", {"company": "Acme"})]
    )
    monkeypatch.setattr(
        source_mod.db_client,
        "get_campaign_by_id",
        AsyncMock(return_value=SimpleNamespace(id=5, organization_id=org.id, source_id=lst.list_uuid)),
    )

    await ContactListSyncService().sync_source_data(5)

    run = capture[0]
    contact = (await db_session.list_contacts(org.id))[0][0][0]
    assert run["source_uuid"] == f"contact_{contact.contact_uuid}"
    ctx = run["context_variables"]
    assert ctx["first_name"] == "Ana" and ctx["company"] == "Acme"
    assert ctx["contact_uuid"] == contact.contact_uuid


@pytest.mark.asyncio
async def test_a_custom_field_can_never_overwrite_the_number_being_dialled(
    db_session, async_session, monkeypatch, capture
):
    """The API refuses those names; this is the second lock if one got in anyway."""
    org, lst = await _org_with_list(db_session, async_session, [])
    contact = await db_session.create_contact(
        org.id,
        phone_number="+971501111111",
        phone_e164="+971501111111",
        attributes={"phone_number": "+000", "first_name": "Evil"},
    )
    await db_session.add_contacts_to_list(lst.id, org.id, [contact.id])
    monkeypatch.setattr(
        source_mod.db_client,
        "get_campaign_by_id",
        AsyncMock(return_value=SimpleNamespace(id=5, organization_id=org.id, source_id=lst.list_uuid)),
    )

    await ContactListSyncService().sync_source_data(5)

    assert capture[0]["context_variables"]["phone_number"] == "+971501111111"
    assert capture[0]["context_variables"]["first_name"] == ""  # standard field wins
