"""The alerts API: tenant isolation, validation on write, and the feed."""

import itertools
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.db.models import OrganizationModel, UserModel, WorkflowModel
from api.routes import alerting as routes
from api.schemas.alerting import (
    AlertChannelCreate,
    AlertChannelUpdate,
    AlertRuleCreate,
    AlertRuleUpdate,
    clean_channel_config,
)

_n = itertools.count()


async def _tenant(async_session):
    n = next(_n)
    org = OrganizationModel(provider_id=f"ar-org-{n}")
    async_session.add(org)
    await async_session.flush()
    user = UserModel(provider_id=f"ar-user-{n}", selected_organization_id=org.id)
    async_session.add(user)
    await async_session.flush()
    wf = WorkflowModel(name=f"Agent {n}", organization_id=org.id, user_id=user.id)
    async_session.add(wf)
    await async_session.flush()
    return user, wf


def _webhook(name="Hook"):
    return AlertChannelCreate(name=name, type="webhook", config={"endpoint_url": "https://hook.test/x"})


def _rule(**over):
    base = dict(name="Failures", metric="call_failed", severity="high")
    base.update(over)
    return AlertRuleCreate(**base)


# -- metrics ------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_metric_list_comes_from_the_registry(db_session, async_session):
    user, _ = await _tenant(async_session)
    out = await routes.list_alert_metrics(user)
    assert {"call_failed", "window_run_count"} <= {m.key for m in out.metrics}
    assert out.severities == ["low", "medium", "high"]


# -- rules -----------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_another_organizations_rule_is_a_404(db_session, async_session):
    owner, _ = await _tenant(async_session)
    intruder, _ = await _tenant(async_session)
    rule = await routes.create_rule(_rule(), owner)

    with pytest.raises(HTTPException) as e:
        await routes.get_rule(rule.rule_uuid, intruder)
    assert e.value.status_code == 404
    for call in (
        routes.update_rule(rule.rule_uuid, AlertRuleUpdate(name="x"), intruder),
        routes.delete_rule(rule.rule_uuid, intruder),
    ):
        with pytest.raises(HTTPException) as e:
            await call
        assert e.value.status_code == 404
    assert (await routes.get_rule(rule.rule_uuid, owner)).name == "Failures"


@pytest.mark.asyncio
async def test_an_unknown_metric_is_refused(db_session, async_session):
    user, _ = await _tenant(async_session)
    with pytest.raises(HTTPException) as e:
        await routes.create_rule(_rule(metric="total_cost_usd"), user)
    assert e.value.status_code == 422


@pytest.mark.asyncio
async def test_each_kind_of_metric_demands_what_it_needs(db_session, async_session):
    user, _ = await _tenant(async_session)
    cases = [
        _rule(metric="call_duration_seconds"),  # number with no threshold
        _rule(metric="call_tag_present"),  # text with no value
        _rule(metric="window_run_count", threshold=3),  # window with no window
    ]
    for rule in cases:
        with pytest.raises(HTTPException) as e:
            await routes.create_rule(rule, user)
        assert e.value.status_code == 422


@pytest.mark.asyncio
async def test_the_trigger_comes_from_the_metric_not_from_the_caller(db_session, async_session):
    user, _ = await _tenant(async_session)
    run_rule = await routes.create_rule(_rule(name="a"), user)
    window_rule = await routes.create_rule(
        _rule(name="b", metric="window_run_count", comparator="lt", threshold=1, window_minutes=60), user
    )
    assert (run_rule.trigger, window_rule.trigger) == ("run_completed", "window")


@pytest.mark.asyncio
async def test_a_rule_cannot_point_at_another_organizations_agent_or_channel(db_session, async_session):
    user, _ = await _tenant(async_session)
    other_user, other_wf = await _tenant(async_session)
    other_channel = await routes.create_channel(_webhook("theirs"), other_user)

    with pytest.raises(HTTPException) as e:
        await routes.create_rule(_rule(scope_workflow_id=other_wf.id), user)
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e:
        await routes.create_rule(_rule(channel_uuids=[other_channel.channel_uuid]), user)
    assert e.value.status_code == 422


@pytest.mark.asyncio
async def test_a_duplicate_rule_name_is_a_conflict(db_session, async_session):
    user, _ = await _tenant(async_session)
    await routes.create_rule(_rule(), user)
    with pytest.raises(HTTPException) as e:
        await routes.create_rule(_rule(), user)
    assert e.value.status_code == 409


@pytest.mark.asyncio
async def test_changing_a_rules_metric_revalidates_the_whole_rule(db_session, async_session):
    user, _ = await _tenant(async_session)
    rule = await routes.create_rule(_rule(), user)  # call_failed: needs nothing

    with pytest.raises(HTTPException) as e:
        await routes.update_rule(rule.rule_uuid, AlertRuleUpdate(metric="call_duration_seconds"), user)
    assert e.value.status_code == 422  # a number metric now, and there is no threshold

    out = await routes.update_rule(
        rule.rule_uuid, AlertRuleUpdate(metric="call_duration_seconds", threshold=120, comparator="gt"), user
    )
    assert out.threshold == 120 and out.trigger == "run_completed"


# -- channels ----------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_email_channels_are_refused_where_email_is_not_set_up(db_session, async_session):
    user, _ = await _tenant(async_session)
    request = AlertChannelCreate(name="Ops", type="email", config={"recipients": ["ops@example.com"]})

    with patch.object(routes, "email_is_configured", lambda: False):
        with pytest.raises(HTTPException) as e:
            await routes.create_channel(request, user)
    assert e.value.status_code == 400 and "not set up" in e.value.detail

    with patch.object(routes, "email_is_configured", lambda: True):
        assert (await routes.create_channel(request, user)).type == "email"


@pytest.mark.asyncio
async def test_a_webhook_credential_must_belong_to_the_organization(db_session, async_session):
    user, _ = await _tenant(async_session)
    request = AlertChannelCreate(
        name="Hook", type="webhook",
        config={"endpoint_url": "https://hook.test", "credential_uuid": "someone-elses"},
    )
    with pytest.raises(HTTPException) as e:
        await routes.create_channel(request, user)
    assert e.value.status_code == 404


@pytest.mark.asyncio
async def test_the_test_button_reports_what_the_delivery_did(db_session, async_session):
    user, _ = await _tenant(async_session)
    channel = await routes.create_channel(_webhook(), user)
    row = SimpleNamespace(id=1, status="dead_letter", last_error="HTTP 404", attempt_count=1)

    with (
        patch.object(routes, "send_test_alert", new=AsyncMock(return_value=SimpleNamespace(id=1, status="pending", last_error=None, attempt_count=0))),
        patch.object(routes.db_client, "get_webhook_delivery", new=AsyncMock(return_value=row)),
    ):
        out = await routes.test_channel(channel.channel_uuid, user)

    assert (out.status, out.error, out.attempts) == ("dead_letter", "HTTP 404", 1)


@pytest.mark.asyncio
async def test_the_test_button_says_pending_rather_than_guess(db_session, async_session, monkeypatch):
    user, _ = await _tenant(async_session)
    channel = await routes.create_channel(_webhook(), user)
    monkeypatch.setattr(routes, "TEST_WAIT_SECONDS", 0.02)
    monkeypatch.setattr(routes, "TEST_POLL_SECONDS", 0.01)
    pending = SimpleNamespace(id=1, status="pending", last_error=None, attempt_count=0)

    with (
        patch.object(routes, "send_test_alert", new=AsyncMock(return_value=pending)),
        patch.object(routes.db_client, "get_webhook_delivery", new=AsyncMock(return_value=pending)),
    ):
        out = await routes.test_channel(channel.channel_uuid, user)

    assert out.status == "pending"


def test_channel_config_is_validated_and_normalised():
    assert clean_channel_config("email", {"recipients": ["A@x.co", "a@x.co", " b@x.co "]}) == {
        "recipients": ["A@x.co", "b@x.co"]
    }
    for bad in ({"recipients": []}, {"recipients": ["nope"]}, {}):
        with pytest.raises(ValueError):
            clean_channel_config("email", bad)
    assert clean_channel_config("webhook", {"endpoint_url": "https://h.test", "junk": 1}) == {
        "endpoint_url": "https://h.test", "http_method": "POST"
    }
    for bad in ({"endpoint_url": "ftp://h"}, {"endpoint_url": "https://h", "http_method": "DELETE"}):
        with pytest.raises(ValueError):
            clean_channel_config("webhook", bad)


# -- events ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_feed_is_newest_first_and_scoped(db_session, async_session):
    user, _ = await _tenant(async_session)
    other, _ = await _tenant(async_session)
    for title in ("one", "two", "three"):
        await db_session.record_alert_event(user.selected_organization_id, alert_rule_id=None, severity="low", title=title, detail={})
    await db_session.record_alert_event(other.selected_organization_id, alert_rule_id=None, severity="low", title="theirs", detail={})

    out = await routes.list_events(limit=50, severity=None, since=None, user=user)

    assert [e.title for e in out.events] == ["three", "two", "one"]


@pytest.mark.asyncio
async def test_acknowledging_marks_it_and_a_stranger_gets_a_404(db_session, async_session):
    user, _ = await _tenant(async_session)
    stranger, _ = await _tenant(async_session)
    event = await db_session.record_alert_event(user.selected_organization_id, alert_rule_id=None, severity="low", title="t", detail={})

    out = await routes.acknowledge_event(event.event_uuid, user)
    assert out.acknowledged_at is not None
    with pytest.raises(HTTPException) as e:
        await routes.acknowledge_event(event.event_uuid, stranger)
    assert e.value.status_code == 404
