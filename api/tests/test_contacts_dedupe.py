"""One person is one row, however their number was typed.

The dedupe key is (organization, E.164). These tests pin that, the two
strategies for a duplicate, and that a bad cell in a spreadsheet rejects its own
row rather than the import.
"""

import csv
import io
import itertools
import tempfile
from types import SimpleNamespace

import pytest

from api.db.models import OrganizationModel, UserModel
from api.services.contacts import import_service
from api.services.contacts.phone import to_e164

_n = itertools.count()


# ── the key itself ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw",
    ["+14155551234", "+1 (415) 555-1234", "+1-415-555-1234", "  +14155551234 ", "14155551234"],
)
def test_every_way_of_writing_a_number_is_the_same_key(raw):
    assert to_e164(raw) == ("+14155551234", None)


def test_a_local_number_needs_a_country_to_become_a_key():
    assert to_e164("050 123 4567") is None  # no country: refuse to guess
    assert to_e164("050 123 4567", "AE") == ("+971501234567", "AE")


@pytest.mark.parametrize("raw", [None, "", "  ", "abc", "sip:alice@example.com", "1234", "+0501234567"])
def test_things_that_are_not_dialable_numbers_have_no_key(raw):
    assert to_e164(raw) is None


# ── the upsert ──────────────────────────────────────────────────────────────


async def _org(async_session):
    n = next(_n)
    org = OrganizationModel(provider_id=f"ct-org-{n}")
    async_session.add(org)
    await async_session.flush()
    user = UserModel(provider_id=f"ct-user-{n}", selected_organization_id=org.id)
    async_session.add(user)
    await async_session.flush()
    return org, user


def _row(phone, **kw):
    e164 = to_e164(phone)[0]
    return {"phone_number": phone, "phone_e164": e164, "attributes": {}, **kw}


@pytest.mark.asyncio
async def test_the_same_number_in_two_formats_is_one_contact(db_session, async_session):
    org, _ = await _org(async_session)
    first = await db_session.upsert_contacts_batch(org.id, [_row("+14155551234")], "skip")
    second = await db_session.upsert_contacts_batch(org.id, [_row("+1 (415) 555-1234")], "skip")

    assert first["created"] == 1
    assert second["created"] == 0 and second["skipped"] == 1
    _, total = await db_session.list_contacts(org.id)
    assert total == 1


@pytest.mark.asyncio
async def test_skip_leaves_an_existing_contact_exactly_as_it_was(db_session, async_session):
    org, _ = await _org(async_session)
    await db_session.upsert_contacts_batch(
        org.id, [_row("+14155551234", first_name="Ana", attributes={"plan": "gold"})], "skip"
    )
    await db_session.upsert_contacts_batch(
        org.id,
        [_row("+14155551234", first_name="Bob", attributes={"plan": "free", "city": "X"})],
        "skip",
    )
    rows, _ = await db_session.list_contacts(org.id)
    contact = rows[0][0]
    assert contact.first_name == "Ana"
    assert contact.attributes == {"plan": "gold"}


@pytest.mark.asyncio
async def test_update_merges_attributes_and_takes_new_names_but_never_blanks_one(
    db_session, async_session
):
    org, _ = await _org(async_session)
    await db_session.upsert_contacts_batch(
        org.id,
        [_row("+14155551234", first_name="Ana", email="a@x.co", attributes={"plan": "gold"})],
        "skip",
    )
    result = await db_session.upsert_contacts_batch(
        org.id,
        [_row("+14155551234", first_name="", last_name="Lee", attributes={"city": "Dubai"})],
        "update",
    )
    assert result["updated"] == 1 and result["created"] == 0
    contact = (await db_session.list_contacts(org.id))[0][0][0]
    assert contact.first_name == "Ana"  # an empty cell does not erase a name
    assert contact.last_name == "Lee"
    assert contact.email == "a@x.co"
    assert contact.attributes == {"plan": "gold", "city": "Dubai"}


@pytest.mark.asyncio
async def test_two_rows_for_one_number_in_one_batch_do_not_crash(db_session, async_session):
    """PostgreSQL refuses a single INSERT that touches a row twice; the batch
    folds them first."""
    org, _ = await _org(async_session)
    rows = [_row("+14155551234", first_name="Ana"), _row("+1 415 555 1234", last_name="Lee")]

    result = await db_session.upsert_contacts_batch(org.id, rows, "update")

    assert result["created"] == 1
    contact = (await db_session.list_contacts(org.id))[0][0][0]
    assert (contact.first_name, contact.last_name) == ("Ana", "Lee")


@pytest.mark.asyncio
async def test_a_repeat_in_one_batch_under_skip_keeps_the_first_and_counts_the_repeat(
    db_session, async_session
):
    org, _ = await _org(async_session)
    result = await db_session.upsert_contacts_batch(
        org.id, [_row("+14155551234", first_name="Ana"), _row("+14155551234", first_name="Bob")], "skip"
    )
    assert result["created"] == 1 and result["skipped"] == 1
    assert (await db_session.list_contacts(org.id))[0][0][0].first_name == "Ana"


@pytest.mark.asyncio
async def test_the_same_number_in_two_organizations_is_two_contacts(db_session, async_session):
    a, _ = await _org(async_session)
    b, _ = await _org(async_session)
    await db_session.upsert_contacts_batch(a.id, [_row("+14155551234")], "skip")
    await db_session.upsert_contacts_batch(b.id, [_row("+14155551234")], "skip")
    assert (await db_session.list_contacts(a.id))[1] == 1
    assert (await db_session.list_contacts(b.id))[1] == 1


# ── the import job, end to end ──────────────────────────────────────────────


def _csv_tempfile(text: str):
    tmp = tempfile.SpooledTemporaryFile(mode="w+b")
    tmp.write(text.encode("utf-8"))
    tmp.seek(0)
    return tmp


@pytest.fixture
def fake_storage(monkeypatch):
    written = {}

    async def create(key, data):
        written[key] = data
        return True

    monkeypatch.setattr(import_service.storage_fs, "acreate_file_from_bytes", create)
    return written


def _serve(monkeypatch, text):
    async def download(_key):
        return _csv_tempfile(text)

    monkeypatch.setattr(import_service, "_download_to_tempfile", download)


async def _import(db_session, org, user, *, mapping, strategy="skip", list_id=None):
    return await db_session.create_contact_import(
        org.id,
        source_key=f"campaigns/{org.id}/contacts.csv",
        column_mapping=mapping,
        dedupe_strategy=strategy,
        contact_list_id=list_id,
        created_by=user.id,
    )


MAPPING = {
    "phone_number": "Mobile",
    "first_name": "First",
    "email": "Email",
    "attributes": {"company": "Employer"},
    "country_hint": "AE",
    "mode": "contacts",
}
FILE = (
    "First,Mobile,Email,Employer\n"
    "Ana,+971 50 111 2222,ana@x.co,Acme\n"
    "Ana again,0501112222,,Acme Ltd\n"  # same person, written locally
    "Bob,not-a-number,bob@x.co,Initech\n"
    ",,,\n"  # a blank line is not a row
    "Cy,+971 55 333 4444,cy@x.co,\n"
)


@pytest.mark.asyncio
async def test_an_import_creates_merges_rejects_and_reports(
    db_session, async_session, monkeypatch, fake_storage
):
    org, user = await _org(async_session)
    _serve(monkeypatch, FILE)
    lst = await db_session.create_contact_list(org.id, name="Leads")
    imp = await _import(db_session, org, user, mapping=MAPPING, strategy="update", list_id=lst.id)

    await import_service.run_contact_import(imp.import_uuid)

    done = await db_session.get_contact_import(imp.import_uuid)
    assert done.status == "completed"
    assert done.total_rows == 4
    assert done.invalid_count == 1
    # Ana and "Ana again" are one person: created once, then merged in-batch.
    assert done.created_count == 2

    rows, total = await db_session.list_contacts(org.id)
    assert total == 2
    ana = next(c for c, _ in rows if c.phone_e164 == "+971501112222")
    assert ana.attributes == {"company": "Acme Ltd"}
    # imported contacts landed in the chosen list
    assert (await db_session.get_contact_list_by_uuid(lst.list_uuid, org.id)).contact_count == 2

    # the bad row is in a downloadable report, with the reason, ready to fix
    report = fake_storage[done.error_report_key].decode()
    parsed = list(csv.reader(io.StringIO(report)))
    assert parsed[0][:2] == ["line", "reason"]
    assert parsed[1][0] == "4" and "valid phone" in parsed[1][1] and "Bob" in parsed[1]


@pytest.mark.asyncio
async def test_a_mapping_that_points_at_nothing_fails_the_import_with_a_reason(
    db_session, async_session, monkeypatch, fake_storage
):
    org, user = await _org(async_session)
    _serve(monkeypatch, FILE)
    imp = await _import(db_session, org, user, mapping={**MAPPING, "phone_number": "Telephone"})

    await import_service.run_contact_import(imp.import_uuid)

    done = await db_session.get_contact_import(imp.import_uuid)
    assert done.status == "failed"
    assert "Telephone" in done.processing_error
    assert (await db_session.list_contacts(org.id))[1] == 0  # nothing half-imported


@pytest.mark.asyncio
async def test_a_job_that_is_run_twice_does_not_import_twice(
    db_session, async_session, monkeypatch, fake_storage
):
    org, user = await _org(async_session)
    _serve(monkeypatch, FILE)
    imp = await _import(db_session, org, user, mapping=MAPPING)

    await import_service.run_contact_import(imp.import_uuid)
    first = await db_session.get_contact_import(imp.import_uuid)
    await import_service.run_contact_import(imp.import_uuid)
    second = await db_session.get_contact_import(imp.import_uuid)

    assert second.created_count == first.created_count


@pytest.mark.asyncio
async def test_a_do_not_call_file_imports_as_suppressions_not_contacts(
    db_session, async_session, monkeypatch, fake_storage
):
    org, user = await _org(async_session)
    _serve(monkeypatch, "Number\n+971501112222\n+971501112222\nnope\n+971553334444\n")
    imp = await _import(
        db_session, org, user, mapping={"phone_number": "Number", "mode": "suppression"}
    )

    await import_service.run_contact_import(imp.import_uuid)

    done = await db_session.get_contact_import(imp.import_uuid)
    assert done.status == "completed"
    assert done.created_count == 2 and done.invalid_count == 1
    assert (await db_session.list_contacts(org.id))[1] == 0  # no contacts created
    hit = await db_session.filter_suppressed_e164(org.id, ["+971501112222", "+971559999999"])
    assert hit == {"+971501112222"}


def test_the_resolver_names_the_missing_column():
    with pytest.raises(import_service.ContactImportError, match="Nope"):
        import_service.resolve_columns(["A", "B"], {"phone_number": "A", "email": "Nope"})
    with pytest.raises(import_service.ContactImportError, match="phone number"):
        import_service.resolve_columns(["A"], {})


def test_headers_match_regardless_of_case_and_spacing():
    cols = import_service.resolve_columns(["  Mobile "], {"phone_number": "mobile"})
    assert cols["phone"] == 0


def test_build_contact_reports_why_a_row_is_rejected():
    cols = {"phone": 0, "first_name": None, "last_name": None, "email": None, "attributes": {}}
    assert import_service.build_contact(["  "], cols, None) == (None, "Missing phone number")
    assert import_service.build_contact(["abc"], cols, None)[1] == "Not a valid phone number"
    contact, reason = import_service.build_contact(["+14155551234"], cols, None)
    assert reason is None and contact["phone_e164"] == "+14155551234"
