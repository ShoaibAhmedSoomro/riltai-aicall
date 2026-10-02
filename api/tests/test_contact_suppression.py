"""The do-not-call list is enforced on every path that can place a call.

There are three outbound entry points and only one of them is the campaign
engine, so a check wired into only one leaks through the others. Each is pinned
here, along with the property that makes the list trustworthy: a suppressed
number stays suppressed when the contact row is deleted.
"""

import itertools
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from api.db.models import OrganizationModel, UserModel
from api.schemas.organization_preferences import OrganizationPreferences
from api.services.campaign import campaign_call_dispatcher as dispatcher_mod
from api.services.campaign.campaign_call_dispatcher import CampaignCallDispatcher
from api.services.contacts import suppression
from api.tasks import run_integrations

_n = itertools.count()
BLOCKED = "+971501111111"
OK = "+971502222222"


async def _org(async_session):
    n = next(_n)
    org = OrganizationModel(provider_id=f"sp-org-{n}")
    async_session.add(org)
    await async_session.flush()
    user = UserModel(provider_id=f"sp-user-{n}", selected_organization_id=org.id)
    async_session.add(user)
    await async_session.flush()
    return org, user


# ── the check itself ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_number_is_suppressed_however_it_is_written(db_session, async_session):
    org, _ = await _org(async_session)
    await db_session.add_suppressions_batch(org.id, ["+14155551234"])

    for raw in ["+14155551234", "+1 (415) 555-1234", "14155551234"]:
        assert await suppression.is_suppressed(org.id, raw), raw
    assert not await suppression.is_suppressed(org.id, "+14155559999")


@pytest.mark.asyncio
async def test_a_sip_address_is_never_on_a_phone_list(db_session, async_session):
    org, _ = await _org(async_session)
    assert not await suppression.is_suppressed(org.id, "sip:alice@example.com")
    assert not await suppression.is_suppressed(org.id, None)


@pytest.mark.asyncio
async def test_the_list_is_per_organization(db_session, async_session):
    a, _ = await _org(async_session)
    b, _ = await _org(async_session)
    await db_session.add_suppressions_batch(a.id, ["+14155551234"])
    assert await suppression.is_suppressed(a.id, "+14155551234")
    assert not await suppression.is_suppressed(b.id, "+14155551234")


@pytest.mark.asyncio
async def test_suppression_survives_deleting_the_contact(db_session, async_session):
    """THE reason it is a table and not a flag on the contact."""
    org, _ = await _org(async_session)
    contact = await db_session.create_contact(
        org.id, phone_number="+14155551234", phone_e164="+14155551234"
    )
    await db_session.add_suppressions_batch(org.id, ["+14155551234"])

    await db_session.delete_contacts(org.id, [contact.contact_uuid])

    assert await suppression.is_suppressed(org.id, "+14155551234")


@pytest.mark.asyncio
async def test_a_number_never_imported_can_still_be_suppressed(db_session, async_session):
    org, _ = await _org(async_session)  # a regulator's file names strangers
    assert await suppression.record_suppression(org.id, "+14155551234", source="manual")
    assert await suppression.is_suppressed(org.id, "+14155551234")


@pytest.mark.asyncio
async def test_suppressing_twice_is_not_an_error(db_session, async_session):
    org, _ = await _org(async_session)
    assert await suppression.record_suppression(org.id, "+14155551234", source="manual")
    assert not await suppression.record_suppression(org.id, "+14155551234", source="manual")


@pytest.mark.asyncio
async def test_a_contact_list_marks_who_is_suppressed_without_a_flag(db_session, async_session):
    org, _ = await _org(async_session)
    await db_session.create_contact(org.id, phone_number=BLOCKED, phone_e164=BLOCKED)
    await db_session.create_contact(org.id, phone_number=OK, phone_e164=OK)
    await db_session.add_suppressions_batch(org.id, [BLOCKED])

    rows, _ = await db_session.list_contacts(org.id)
    flags = {c.phone_e164: s for c, s in rows}
    assert flags == {BLOCKED: True, OK: False}
    only_blocked, total = await db_session.list_contacts(org.id, suppressed=True)
    assert total == 1 and only_blocked[0][0].phone_e164 == BLOCKED


# ── path 1: the campaign dispatcher ─────────────────────────────────────────


def _queued(i, phone):
    return SimpleNamespace(id=i, context_variables={"phone_number": phone}, source_uuid=f"s{i}")


def _dispatcher(monkeypatch, runs, suppressed):
    fake_db = SimpleNamespace(
        get_campaign_by_id=AsyncMock(
            return_value=SimpleNamespace(
                id=1, state="running", organization_id=9, rate_limit_per_second=1, processed_rows=0
            )
        ),
        claim_queued_runs_for_processing=AsyncMock(return_value=runs),
        update_queued_run=AsyncMock(),
        update_campaign=AsyncMock(),
        append_campaign_log=AsyncMock(),
    )
    monkeypatch.setattr(dispatcher_mod, "db_client", fake_db)
    monkeypatch.setattr(dispatcher_mod, "rate_limiter", MagicMock(initialize_from_number_pool=AsyncMock()))
    d = CampaignCallDispatcher()
    d.get_provider_for_campaign = AsyncMock(return_value=SimpleNamespace(from_numbers=[]))
    d.apply_rate_limit = AsyncMock()
    d.acquire_concurrent_slot = AsyncMock(return_value=object())
    d.dispatch_call = AsyncMock(return_value=SimpleNamespace(id=100))
    d._return_unprocessed_claims = AsyncMock()
    if isinstance(suppressed, Exception):
        monkeypatch.setattr(dispatcher_mod, "suppressed_among", AsyncMock(side_effect=suppressed))
    else:
        monkeypatch.setattr(dispatcher_mod, "suppressed_among", AsyncMock(return_value=suppressed))
    return d, fake_db


@pytest.mark.asyncio
async def test_a_suppressed_row_is_skipped_before_it_costs_a_slot_or_a_caller_id(monkeypatch):
    d, db = _dispatcher(monkeypatch, [_queued(1, BLOCKED), _queued(2, OK)], {BLOCKED})

    done = await d.process_batch(1, batch_size=10)

    assert done == 1
    # only the allowed row consumed rate limit, a concurrency slot and a dial
    assert d.apply_rate_limit.await_count == 1
    assert d.acquire_concurrent_slot.await_count == 1
    assert d.dispatch_call.await_count == 1
    assert d.dispatch_call.await_args.args[0].id == 2
    # the blocked row is retired as failed (so a redial schedule never returns to it)
    retired = [c.kwargs for c in db.update_queued_run.await_args_list if c.kwargs.get("queued_run_id") == 1]
    assert retired and retired[0]["state"] == "failed"


@pytest.mark.asyncio
async def test_the_skip_is_logged_on_the_campaign_without_the_full_number(monkeypatch):
    d, db = _dispatcher(monkeypatch, [_queued(1, BLOCKED)], {BLOCKED})

    await d.process_batch(1, batch_size=10)

    args = db.append_campaign_log.await_args.args
    assert args[2] == "number_suppressed"
    details = db.append_campaign_log.await_args.args[4]
    assert details["number_ending"] == "1111"
    assert BLOCKED not in str(db.append_campaign_log.await_args)


@pytest.mark.asyncio
async def test_if_the_list_cannot_be_read_nothing_is_dialled(monkeypatch):
    """Fail closed: a compliance check that fails open is not one."""
    d, db = _dispatcher(monkeypatch, [_queued(1, OK)], RuntimeError("db down"))

    with pytest.raises(RuntimeError):
        await d.process_batch(1, batch_size=10)

    d.dispatch_call.assert_not_awaited()
    d._return_unprocessed_claims.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_batch_with_nobody_suppressed_is_unchanged(monkeypatch):
    d, db = _dispatcher(monkeypatch, [_queued(1, OK), _queued(2, "+971503333333")], set())
    assert await d.process_batch(1, batch_size=10) == 2
    db.append_campaign_log.assert_not_awaited()


# ── path 2: the public trigger API ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_public_trigger_refuses_a_suppressed_number(monkeypatch):
    from api.routes import public_agent

    check = AsyncMock(return_value=True)
    monkeypatch.setattr(public_agent, "is_suppressed", check)
    target = SimpleNamespace(workflow=SimpleNamespace(user_id=1), organization_id=7)
    request = SimpleNamespace(phone_number=BLOCKED, telephony_configuration_id=None)

    with pytest.raises(HTTPException) as exc:
        await public_agent._execute_resolved_target(
            target, request, use_draft=False, api_key_id=None, api_key_created_by=None
        )

    assert exc.value.status_code == 403 and "do-not-call" in exc.value.detail
    check.assert_awaited_once_with(7, BLOCKED)


@pytest.mark.asyncio
async def test_the_public_trigger_does_not_swallow_a_failed_check(monkeypatch):
    from api.routes import public_agent

    monkeypatch.setattr(public_agent, "is_suppressed", AsyncMock(side_effect=RuntimeError("down")))
    target = SimpleNamespace(workflow=SimpleNamespace(user_id=1), organization_id=7)
    request = SimpleNamespace(phone_number=OK, telephony_configuration_id=None)

    with pytest.raises(RuntimeError):  # a 500, never a placed call
        await public_agent._execute_resolved_target(
            target, request, use_draft=False, api_key_id=None, api_key_created_by=None
        )


# ── path 3: the web test call ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_test_call_is_refused_for_a_suppressed_number(monkeypatch):
    from api.routes import telephony

    monkeypatch.setattr(telephony, "is_suppressed", AsyncMock(return_value=True))
    monkeypatch.setattr(telephony, "resolve_outbound_configuration_id", AsyncMock(return_value=3))
    monkeypatch.setattr(
        telephony,
        "get_telephony_provider_by_id",
        AsyncMock(return_value=SimpleNamespace(validate_config=lambda: True)),
    )
    monkeypatch.setattr(
        "api.services.organization_preferences.get_organization_preferences",
        AsyncMock(return_value=OrganizationPreferences()),
    )
    request = SimpleNamespace(phone_number=BLOCKED, telephony_configuration_id=None, workflow_id=1)
    user = SimpleNamespace(selected_organization_id=7)

    with pytest.raises(HTTPException) as exc:
        await telephony.initiate_call(request, user)

    assert exc.value.status_code == 403
    assert "do-not-call" in exc.value.detail


# ── after the call: stats, and honouring an opt-out ─────────────────────────


def _finished_run(disposition, **ctx):
    return SimpleNamespace(
        annotations={},
        initial_context={"direction": "outbound", "called_number": "+14155551234", **ctx},
        gathered_context={"mapped_call_disposition": disposition},
    )


@pytest.fixture
def post_call(monkeypatch):
    marked = AsyncMock()
    monkeypatch.setattr(run_integrations.db_client, "update_workflow_run", marked)
    monkeypatch.setattr(
        run_integrations,
        "get_organization_preferences",
        AsyncMock(return_value=OrganizationPreferences(do_not_call_dispositions=["do_not_call"])),
    )
    return marked


@pytest.mark.asyncio
async def test_a_finished_call_updates_the_contact(db_session, async_session, post_call):
    org, _ = await _org(async_session)
    await db_session.create_contact(org.id, phone_number="+14155551234", phone_e164="+14155551234")

    await run_integrations._update_contact_after_call(_finished_run("qualified"), 1, org.id)

    contact = (await db_session.list_contacts(org.id))[0][0][0]
    assert contact.call_count == 1 and contact.last_disposition == "qualified"
    assert contact.last_called_at is not None
    assert not await suppression.is_suppressed(org.id, "+14155551234")


@pytest.mark.asyncio
async def test_an_opt_out_outcome_puts_the_number_on_the_list(db_session, async_session, post_call):
    org, _ = await _org(async_session)

    await run_integrations._update_contact_after_call(_finished_run("do_not_call"), 1, org.id)

    assert await suppression.is_suppressed(org.id, "+14155551234")


@pytest.mark.asyncio
async def test_the_same_run_is_not_counted_twice(db_session, async_session, post_call):
    org, _ = await _org(async_session)
    await db_session.create_contact(org.id, phone_number="+14155551234", phone_e164="+14155551234")
    run = _finished_run("qualified")

    await run_integrations._update_contact_after_call(run, 1, org.id)
    run.annotations = {"contact_recorded": True}  # what the marker write leaves behind
    await run_integrations._update_contact_after_call(run, 1, org.id)

    assert (await db_session.list_contacts(org.id))[0][0][0].call_count == 1


@pytest.mark.asyncio
async def test_inbound_calls_do_not_touch_a_contacts_outbound_stats(db_session, async_session, post_call):
    org, _ = await _org(async_session)
    await db_session.create_contact(org.id, phone_number="+14155551234", phone_e164="+14155551234")

    await run_integrations._update_contact_after_call(
        _finished_run("qualified", direction="inbound"), 1, org.id
    )

    assert (await db_session.list_contacts(org.id))[0][0][0].call_count == 0


@pytest.mark.asyncio
async def test_a_failed_opt_out_write_is_left_to_be_retried(monkeypatch, post_call):
    """Someone asked not to be called. Marking the run done would lose that."""
    monkeypatch.setattr(run_integrations.db_client, "record_contact_call", AsyncMock())
    monkeypatch.setattr(
        run_integrations, "record_suppression", AsyncMock(side_effect=RuntimeError("db down"))
    )

    await run_integrations._update_contact_after_call(_finished_run("do_not_call"), 1, 7)

    post_call.assert_not_awaited()  # the "done" marker was NOT written
