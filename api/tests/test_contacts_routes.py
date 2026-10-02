"""The contacts API: tenant isolation, validation, and the small contracts the UI
leans on."""

import itertools
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from api.db.models import OrganizationModel, UserModel
from api.routes import contacts as routes
from api.schemas.contacts import (
    ColumnMapping,
    ContactBulkRequest,
    ContactCreateRequest,
    ContactImportRequest,
    ContactUpdateRequest,
)

_n = itertools.count()


async def _tenant(async_session):
    n = next(_n)
    org = OrganizationModel(provider_id=f"cr-org-{n}")
    async_session.add(org)
    await async_session.flush()
    user = UserModel(provider_id=f"cr-user-{n}", selected_organization_id=org.id)
    async_session.add(user)
    await async_session.flush()
    return SimpleNamespace(id=user.id, selected_organization_id=org.id)


# ── which files a caller may point the server at ────────────────────────────


@pytest.mark.parametrize(
    "key,ok",
    [
        ("campaigns/7/abc/contacts.csv", True),
        ("campaigns/7/contact-import-errors/x.csv", True),
        ("campaigns/70/abc/contacts.csv", False),  # a prefix match would let this through
        ("campaigns/8/abc/contacts.csv", False),
        ("knowledge_base/7/doc.pdf", False),
        ("recordings/7/1/a.wav", False),
        ("campaigns/7", False),
        ("../campaigns/7/x.csv", False),
    ],
)
def test_only_files_the_organization_uploaded_can_be_imported(key, ok):
    assert routes._owns_key(7, key) is ok


@pytest.mark.asyncio
async def test_importing_another_tenants_file_is_forbidden_before_anything_is_created(monkeypatch):
    create = AsyncMock()
    monkeypatch.setattr(routes.db_client, "create_contact_import", create)
    user = SimpleNamespace(id=1, selected_organization_id=7)

    with pytest.raises(HTTPException) as exc:
        await routes.import_contacts(
            ContactImportRequest(
                source_key="campaigns/8/secret/people.csv",
                column_mapping=ColumnMapping(phone_number="Phone"),
            ),
            user,
        )

    assert exc.value.status_code == 403
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_previewing_another_tenants_file_is_forbidden():
    with pytest.raises(HTTPException) as exc:
        await routes.preview_import("campaigns/8/secret/people.csv", SimpleNamespace(selected_organization_id=7))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_a_failed_enqueue_marks_the_import_failed_rather_than_pending_forever(
    db_session, async_session, monkeypatch
):
    user = await _tenant(async_session)
    monkeypatch.setattr(routes, "enqueue_job", AsyncMock(side_effect=RuntimeError("redis down")))

    out = await routes.import_contacts(
        ContactImportRequest(
            source_key=f"campaigns/{user.selected_organization_id}/x/people.csv",
            column_mapping=ColumnMapping(phone_number="Phone"),
        ),
        user,
    )

    assert out.status == "failed" and "Try again" in out.processing_error


# ── creating and editing ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_creating_a_contact_normalizes_the_number_and_refuses_a_duplicate(db_session, async_session):
    user = await _tenant(async_session)

    made = await routes.create_contact(ContactCreateRequest(phone_number="+1 (415) 555-1234"), user)
    assert made.phone_e164 == "+14155551234" and made.phone_number == "+1 (415) 555-1234"

    with pytest.raises(HTTPException) as dup:
        await routes.create_contact(ContactCreateRequest(phone_number="+14155551234"), user)
    assert dup.value.status_code == 409


@pytest.mark.asyncio
async def test_a_number_that_cannot_be_dialled_is_a_422_with_a_hint(db_session, async_session):
    user = await _tenant(async_session)
    with pytest.raises(HTTPException) as exc:
        await routes.create_contact(ContactCreateRequest(phone_number="050 123 4567"), user)
    assert exc.value.status_code == 422 and "country code" in exc.value.detail


@pytest.mark.parametrize("name", ["phone_number", "first_name", "email", "contact_uuid", "9lives", "has space"])
def test_a_custom_field_cannot_shadow_a_standard_one_or_be_unusable_as_a_variable(name):
    with pytest.raises(ValidationError):
        ContactCreateRequest(phone_number="+14155551234", attributes={name: "x"})


@pytest.mark.asyncio
async def test_an_update_changes_only_what_was_sent_and_null_clears(db_session, async_session):
    user = await _tenant(async_session)
    made = await routes.create_contact(
        ContactCreateRequest(phone_number="+14155551234", first_name="Ana", last_name="Lee"), user
    )

    after = await routes.update_contact(made.contact_uuid, ContactUpdateRequest(last_name="Kim"), user)
    assert (after.first_name, after.last_name) == ("Ana", "Kim")  # first name untouched

    cleared = await routes.update_contact(made.contact_uuid, ContactUpdateRequest(first_name=None), user)
    assert cleared.first_name is None and cleared.last_name == "Kim"


@pytest.mark.asyncio
async def test_a_contact_in_another_organization_does_not_exist_to_you(db_session, async_session):
    mine = await _tenant(async_session)
    theirs = await _tenant(async_session)
    made = await routes.create_contact(ContactCreateRequest(phone_number="+14155551234"), theirs)

    for call in (
        routes.get_contact(made.contact_uuid, mine),
        routes.update_contact(made.contact_uuid, ContactUpdateRequest(first_name="x"), mine),
        routes.delete_contact(made.contact_uuid, mine),
        routes.get_contact_runs(made.contact_uuid, 1, 25, mine),
    ):
        with pytest.raises(HTTPException) as exc:
            await call
        assert exc.value.status_code == 404

    out = await routes.bulk_delete_contacts(ContactBulkRequest(contact_uuids=[made.contact_uuid]), mine)
    assert out.affected == 0
    assert (await db_session.list_contacts(theirs.selected_organization_id))[1] == 1


@pytest.mark.asyncio
async def test_a_list_cannot_be_given_another_tenants_contacts(db_session, async_session):
    mine = await _tenant(async_session)
    theirs = await _tenant(async_session)
    stranger = await routes.create_contact(ContactCreateRequest(phone_number="+14155551234"), theirs)
    lst = await routes.create_contact_list(
        routes.ContactListCreateRequest(name="Mine"), mine
    )

    out = await routes.add_list_members(
        lst.list_uuid, ContactBulkRequest(contact_uuids=[stranger.contact_uuid]), mine
    )

    assert out.affected == 0


@pytest.mark.asyncio
async def test_list_names_are_unique_per_organization(db_session, async_session):
    user = await _tenant(async_session)
    other = await _tenant(async_session)
    await routes.create_contact_list(routes.ContactListCreateRequest(name="Leads"), user)
    await routes.create_contact_list(routes.ContactListCreateRequest(name="Leads"), other)  # fine
    with pytest.raises(HTTPException) as exc:
        await routes.create_contact_list(routes.ContactListCreateRequest(name="Leads"), user)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_deleting_a_list_keeps_its_contacts(db_session, async_session):
    user = await _tenant(async_session)
    made = await routes.create_contact(ContactCreateRequest(phone_number="+14155551234"), user)
    lst = await routes.create_contact_list(routes.ContactListCreateRequest(name="Leads"), user)
    await routes.add_list_members(lst.list_uuid, ContactBulkRequest(contact_uuids=[made.contact_uuid]), user)

    await routes.delete_contact_list(lst.list_uuid, user)

    assert (await db_session.list_contacts(user.selected_organization_id))[1] == 1


# ── history ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_contacts_history_asks_for_an_exact_match_on_their_number(
    db_session, async_session, monkeypatch
):
    user = await _tenant(async_session)
    made = await routes.create_contact(ContactCreateRequest(phone_number="+14155551234"), user)
    seen = {}

    async def history(org, **kw):
        seen.update(kw, org=org)
        return (
            [{"id": 1, "workflow_id": 2, "workflow_name": "A", "created_at": "2026-10-01",
              "call_duration_seconds": 42, "disposition": "qualified", "call_type": "outbound",
              "charge_usd": 0.5}],
            1, 0.5, 42,
        )

    monkeypatch.setattr(routes.db_client, "get_usage_history", history)

    out = await routes.get_contact_runs(made.contact_uuid, 1, 25, user)

    assert seen["org"] == user.selected_organization_id
    assert seen["filters"] == [
        {"attribute": "calledNumberExact", "type": "text", "value": {"value": "+14155551234"}}
    ]
    assert out.total_count == 1 and out.runs[0].disposition == "qualified"


@pytest.mark.asyncio
async def test_the_exact_number_filter_is_equality_not_a_substring(db_session, async_session):
    """The existing calledNumber filter is a LIKE. A contact's history on it would
    include every longer number that merely contains theirs."""
    from api.db.models import WorkflowModel, WorkflowRunModel

    user = await _tenant(async_session)
    org = user.selected_organization_id
    workflow = WorkflowModel(name="w", organization_id=org, user_id=user.id)
    async_session.add(workflow)
    await async_session.flush()
    for number in ["+14155551234", "+141555512345", "+4155551234"]:
        async_session.add(
            WorkflowRunModel(
                workflow_id=workflow.id,
                name="r",
                mode="voice",
                is_completed=True,
                initial_context={"called_number": number},
            )
        )
    await async_session.flush()

    _, exact_total, _, _ = await db_session.get_usage_history(
        org,
        filters=[{"attribute": "calledNumberExact", "type": "text", "value": {"value": "+14155551234"}}],
    )
    _, like_total, _, _ = await db_session.get_usage_history(
        org,
        filters=[{"attribute": "calledNumber", "type": "text", "value": {"value": "+14155551234"}}],
    )

    assert exact_total == 1
    assert like_total == 2  # the substring match is what the exact one avoids
