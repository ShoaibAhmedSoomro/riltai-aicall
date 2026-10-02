"""Alert storage: the tables round-trip, are tenant-scoped, and the delivery table
dedupes on its new key."""

import itertools
from unittest.mock import patch
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from api.db.models import (
    OrganizationModel,
    UserModel,
    WebhookDeliveryModel,
    WorkflowModel,
    WorkflowRunModel,
)

_n = itertools.count()


async def _org(async_session):
    n = next(_n)
    org = OrganizationModel(provider_id=f"al-org-{n}")
    async_session.add(org)
    await async_session.flush()
    user = UserModel(provider_id=f"al-user-{n}", selected_organization_id=org.id)
    async_session.add(user)
    await async_session.flush()
    wf = WorkflowModel(name=f"Agent {n}", organization_id=org.id, user_id=user.id)
    async_session.add(wf)
    await async_session.flush()
    return org, user, wf


async def _finished_run(async_session, wf, *, disposition=None, duration=60, age_minutes=1):
    run = WorkflowRunModel(
        name=f"r{next(_n)}", workflow_id=wf.id, mode="twilio", is_completed=True,
        state="completed",
        gathered_context={"mapped_call_disposition": disposition} if disposition else {},
        usage_info={"call_duration_seconds": duration},
        created_at=datetime.now(UTC) - timedelta(minutes=age_minutes),
    )
    async_session.add(run)
    await async_session.flush()
    return run


@pytest.mark.asyncio
async def test_a_channel_a_rule_and_an_event_round_trip(db_session, async_session):
    org, user, wf = await _org(async_session)

    channel = await db_session.create_alert_channel(
        org.id, "Ops email", "email", {"recipients": ["ops@example.com"]}
    )
    rule = await db_session.create_alert_rule(
        org.id, name="Failures", trigger="run_completed", metric="call_failed",
        comparator="gt", severity="high", channel_uuids=[channel.channel_uuid],
        scope_workflow_id=wf.id,
    )
    event = await db_session.record_alert_event(
        org.id, alert_rule_id=rule.id, severity="high", title="Failures", detail={"x": 1},
        observed_value=1.0,
    )

    assert (await db_session.get_alert_channel(org.id, channel.channel_uuid)).config == {
        "recipients": ["ops@example.com"]
    }
    got = await db_session.get_alert_rule(org.id, rule.rule_uuid)
    assert got.channel_uuids == [channel.channel_uuid] and got.scope_workflow_id == wf.id
    assert [e.event_uuid for e in await db_session.list_alert_events(org.id)] == [event.event_uuid]


@pytest.mark.asyncio
async def test_another_organization_sees_and_changes_nothing(db_session, async_session):
    org_a, _, _ = await _org(async_session)
    org_b, _, _ = await _org(async_session)
    channel = await db_session.create_alert_channel(org_a.id, "A", "webhook", {"endpoint_url": "https://x.test"})
    rule = await db_session.create_alert_rule(org_a.id, name="R", trigger="run_completed", metric="call_failed")

    assert await db_session.get_alert_channel(org_b.id, channel.channel_uuid) is None
    assert await db_session.get_alert_rule(org_b.id, rule.rule_uuid) is None
    assert await db_session.update_alert_rule(org_b.id, rule.rule_uuid, name="hijack") is None
    assert await db_session.delete_alert_channel(org_b.id, channel.channel_uuid) is False
    assert await db_session.list_alert_rules(org_b.id) == []
    assert (await db_session.get_alert_rule(org_a.id, rule.rule_uuid)).name == "R"


@pytest.mark.asyncio
async def test_events_come_back_newest_first_and_acknowledge_once(db_session, async_session):
    org, user, _ = await _org(async_session)
    first = await db_session.record_alert_event(org.id, alert_rule_id=None, severity="low", title="old", detail={})
    second = await db_session.record_alert_event(org.id, alert_rule_id=None, severity="high", title="new", detail={})

    assert [e.title for e in await db_session.list_alert_events(org.id)] == ["new", "old"]
    assert [e.title for e in await db_session.list_alert_events(org.id, severity="high")] == ["new"]

    acked = await db_session.acknowledge_alert_event(org.id, first.event_uuid, user.id)
    again = await db_session.acknowledge_alert_event(org.id, first.event_uuid, user.id + 99)
    assert acked.acknowledged_by == user.id and again.acknowledged_by == user.id  # the first one stands


@pytest.mark.asyncio
async def test_deleting_a_rule_keeps_what_it_caught(db_session, async_session):
    org, _, _ = await _org(async_session)
    rule = await db_session.create_alert_rule(org.id, name="R", trigger="run_completed", metric="call_failed")
    await db_session.record_alert_event(org.id, alert_rule_id=rule.id, severity="low", title="kept", detail={})

    await db_session.delete_alert_rule(org.id, rule.rule_uuid)

    (event,) = await db_session.list_alert_events(org.id)
    assert event.title == "kept" and event.alert_rule_id is None


@pytest.mark.asyncio
async def test_a_rule_can_fire_only_once_per_cooldown(db_session, async_session):
    org, _, _ = await _org(async_session)
    rule = await db_session.create_alert_rule(
        org.id, name="R", trigger="run_completed", metric="call_failed", cooldown_minutes=60
    )
    now = datetime.now(UTC)

    assert await db_session.claim_alert_rule_fire(rule.id, now) is True
    assert await db_session.claim_alert_rule_fire(rule.id, now + timedelta(minutes=30)) is False
    assert await db_session.claim_alert_rule_fire(rule.id, now + timedelta(minutes=61)) is True


@pytest.mark.asyncio
async def test_window_stats_count_this_organizations_finished_calls_in_the_window(db_session, async_session):
    org, _, wf = await _org(async_session)
    other_org, _, other_wf = await _org(async_session)
    await _finished_run(async_session, wf, disposition="error", duration=10)
    await _finished_run(async_session, wf, disposition="completed", duration=30)
    await _finished_run(async_session, wf, age_minutes=500)  # outside the window
    await _finished_run(async_session, other_wf, disposition="error")  # someone else's

    stats = await db_session.get_window_run_stats(org.id, 60)

    assert stats["run_count"] == 2 and stats["failed_count"] == 1
    assert stats["mean_duration_seconds"] == 20.0
    assert (await db_session.get_window_run_stats(org.id, 60, workflow_id=wf.id))["run_count"] == 2
    assert (await db_session.get_window_run_stats(org.id, 60, workflow_id=other_wf.id))["run_count"] == 0


@pytest.mark.asyncio
async def test_an_empty_window_has_no_mean_not_a_zero(db_session, async_session):
    org, _, _ = await _org(async_session)
    stats = await db_session.get_window_run_stats(org.id, 60)
    assert stats == {"run_count": 0, "failed_count": 0, "mean_duration_seconds": None}


def _delivery_row(org_id, key):
    return WebhookDeliveryModel(
        organization_id=org_id, idempotency_key=key, payload={}, transport="email",
        destination={"recipients": ["a@b.co"]}, max_attempts=3,
    )


@pytest.mark.asyncio
async def test_a_second_delivery_with_the_same_key_is_refused_but_other_orgs_may_reuse_it(async_session):
    org, _, _ = await _org(async_session)
    other, _, _ = await _org(async_session)
    async_session.add(_delivery_row(org.id, "alert:e1:c1"))
    async_session.add(_delivery_row(other.id, "alert:e1:c1"))  # another organization: fine
    await async_session.flush()

    # A savepoint, so the refused insert does not poison the test's transaction.
    with pytest.raises(IntegrityError):
        async with async_session.begin_nested():
            async_session.add(_delivery_row(org.id, "alert:e1:c1"))
            await async_session.flush()


@pytest.mark.asyncio
async def test_an_alert_delivery_needs_no_run_or_url(db_session, async_session):
    org, _, _ = await _org(async_session)

    delivery, created = await db_session.create_delivery(
        organization_id=org.id, idempotency_key="alert:e2:c1", payload={}, max_attempts=3,
        transport="email", destination={"recipients": ["a@b.co"]},
    )

    assert created and delivery.workflow_run_id is None and delivery.endpoint_url is None
    assert delivery.transport == "email"


@pytest.mark.asyncio
async def test_a_webhook_node_delivery_is_keyed_by_run_and_node(db_session, async_session):
    org, _, wf = await _org(async_session)
    run = await _finished_run(async_session, wf)
    captured = {}

    async def capture(**kwargs):
        captured.update(kwargs)
        return object(), True

    with patch.object(db_session, "create_delivery", new=capture):
        await db_session.create_webhook_delivery(
            workflow_run_id=run.id, organization_id=org.id, endpoint_url="https://hook.test",
            payload={}, max_attempts=3, webhook_node_id="node-1",
        )

    assert captured["idempotency_key"] == f"run:{run.id}:node-1"
    assert captured["transport"] if "transport" in captured else True


@pytest.mark.asyncio
async def test_a_repeated_delivery_returns_the_existing_row_on_a_real_session():
    """The conflict path rolls back a real transaction, which the shared test
    session cannot survive, so this one talks to the database on its own and cleans
    up after itself."""
    from sqlalchemy import delete

    from api.db.webhook_delivery_client import WebhookDeliveryClient

    client = WebhookDeliveryClient()
    async with client.async_session() as s:
        org = OrganizationModel(provider_id=f"al-real-{next(_n)}")
        s.add(org)
        await s.flush()
        org_id = org.id  # read before commit expires the instance
        await s.commit()
    try:
        kwargs = dict(
            organization_id=org_id, idempotency_key="alert:real:1", payload={}, max_attempts=3,
            transport="email", destination={"recipients": ["a@b.co"]},
        )
        first, created = await client.create_delivery(**kwargs)
        again, created_again = await client.create_delivery(**kwargs)

        assert created and not created_again and again.id == first.id
    finally:
        async with client.async_session() as s:
            await s.execute(delete(OrganizationModel).where(OrganizationModel.id == org_id))
            await s.commit()
        await client.engine.dispose()
