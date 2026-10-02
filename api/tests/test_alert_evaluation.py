"""When a rule fires: the pure matching, and the path from a finished call to an event."""

import itertools
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.db.models import OrganizationModel, UserModel, WorkflowModel, WorkflowRunModel
from api.services.alerting import evaluate
from api.services.alerting.metrics import METRICS, MIN_WINDOW_RUNS_FOR_RATE

_n = itertools.count()


def _rule(**over):
    base = dict(
        id=1, name="R", metric="call_failed", comparator="gt", threshold=None,
        match_value=None, window_minutes=None, scope_workflow_id=None, severity="high",
        channel_uuids=[],
    )
    base.update(over)
    return SimpleNamespace(**base)


def _run(**over):
    base = dict(gathered_context={}, usage_info={}, annotations={})
    base.update(over)
    return SimpleNamespace(**base)


# -- pure: run-scoped ---------------------------------------------------------------


def test_call_failed_fires_on_an_error_outcome_only():
    rule = _rule(metric="call_failed")
    assert evaluate.run_rule_fires(rule, _run(gathered_context={"mapped_call_disposition": "error"}))[0]
    assert not evaluate.run_rule_fires(rule, _run(gathered_context={"mapped_call_disposition": "completed"}))[0]
    assert not evaluate.run_rule_fires(rule, _run())[0]


def test_duration_uses_the_comparator_and_ignores_a_call_with_no_duration():
    rule = _rule(metric="call_duration_seconds", comparator="lt", threshold=10)
    assert evaluate.run_rule_fires(rule, _run(usage_info={"call_duration_seconds": 4}))[0]
    assert not evaluate.run_rule_fires(rule, _run(usage_info={"call_duration_seconds": 40}))[0]
    assert not evaluate.run_rule_fires(rule, _run(usage_info={}))[0]  # unknown is not zero


def test_outcome_and_tag_matching_ignore_case():
    outcome = _rule(metric="call_disposition_is", match_value="Busy")
    assert evaluate.run_rule_fires(outcome, _run(gathered_context={"mapped_call_disposition": "busy"}))[0]
    tag = _rule(metric="call_tag_present", match_value="Escalate")
    assert evaluate.run_rule_fires(tag, _run(gathered_context={"call_tags": ["escalate", "x"]}))[0]
    assert not evaluate.run_rule_fires(tag, _run(gathered_context={"call_tags": ["other"]}))[0]
    assert not evaluate.run_rule_fires(_rule(metric="call_tag_present", match_value=""), _run())[0]


def test_safety_violation_reads_the_scan_result():
    rule = _rule(metric="safety_violation")
    assert evaluate.run_rule_fires(rule, _run(annotations={"safety": {"violations": [{"category": "x"}]}}))[0]
    assert evaluate.run_rule_fires(rule, _run(annotations={"safety": {"jailbreak_attempt": True}}))[0]
    assert not evaluate.run_rule_fires(rule, _run(annotations={"safety": {"violations": []}}))[0]
    assert not evaluate.run_rule_fires(rule, _run())[0]


def test_a_window_metric_is_never_evaluated_as_a_run_rule_and_vice_versa():
    assert not evaluate.run_rule_fires(_rule(metric="window_run_count", threshold=0), _run())[0]
    assert not evaluate.window_rule_fires(_rule(metric="call_failed"), {"run_count": 9, "failed_count": 9, "mean_duration_seconds": 1})[0]
    assert not evaluate.run_rule_fires(_rule(metric="no_such_metric"), _run())[0]


# -- pure: windows ------------------------------------------------------------------------


def _stats(runs, failed, mean=30.0):
    return {"run_count": runs, "failed_count": failed, "mean_duration_seconds": mean}


def test_a_window_rule_under_its_threshold_does_not_fire():
    rule = _rule(metric="window_failed_rate_percent", comparator="gt", threshold=50, window_minutes=60)
    assert evaluate.window_rule_fires(rule, _stats(10, 2)) == (False, 20.0)
    assert evaluate.window_rule_fires(rule, _stats(10, 8)) == (True, 80.0)


def test_a_rate_over_a_handful_of_calls_is_not_judged():
    rule = _rule(metric="window_failed_rate_percent", comparator="gt", threshold=10, window_minutes=60)
    few = MIN_WINDOW_RUNS_FOR_RATE - 1
    assert evaluate.window_rule_fires(rule, _stats(few, few)) == (False, None)


def test_silence_can_be_alerted_on():
    rule = _rule(metric="window_run_count", comparator="lt", threshold=1, window_minutes=60)
    assert evaluate.window_rule_fires(rule, _stats(0, 0))[0]
    assert not evaluate.window_rule_fires(rule, _stats(3, 0))[0]


def test_an_empty_window_has_no_mean_to_compare():
    rule = _rule(metric="window_mean_duration_seconds", comparator="lt", threshold=5, window_minutes=60)
    assert evaluate.window_rule_fires(rule, _stats(0, 0, mean=None)) == (False, None)


def test_the_registry_never_offers_money_or_tokens():
    assert not [k for k in METRICS if any(w in k for w in ("cost", "charge", "token", "xfer"))]


def test_the_condition_reads_as_a_sentence():
    rule = _rule(metric="window_failed_rate_percent", comparator="gt", threshold=20, window_minutes=30)
    assert evaluate.describe_condition(rule) == "Failure rate in the window > 20 % (last 30 min)"
    assert evaluate.describe_condition(_rule(metric="call_tag_present", match_value="escalate")) == "Call has tag: escalate"


# -- through the database ---------------------------------------------------------------------


async def _setup(async_session):
    n = next(_n)
    org = OrganizationModel(provider_id=f"ev-org-{n}")
    async_session.add(org)
    await async_session.flush()
    user = UserModel(provider_id=f"ev-user-{n}", selected_organization_id=org.id)
    async_session.add(user)
    await async_session.flush()
    wf = WorkflowModel(name="Sales", organization_id=org.id, user_id=user.id)
    async_session.add(wf)
    await async_session.flush()
    return org, wf


async def _finished(async_session, wf, disposition):
    run = WorkflowRunModel(
        name=f"r{next(_n)}", workflow_id=wf.id, mode="twilio", is_completed=True, state="completed",
        gathered_context={"mapped_call_disposition": disposition}, usage_info={"call_duration_seconds": 30},
    )
    async_session.add(run)
    await async_session.flush()
    return run


@pytest.mark.asyncio
async def test_a_failed_call_fires_the_rule_records_an_event_and_queues_the_delivery(db_session, async_session):
    org, wf = await _setup(async_session)
    channel = await db_session.create_alert_channel(org.id, "Hook", "webhook", {"endpoint_url": "https://hook.test"})
    await db_session.create_alert_rule(
        org.id, name="Any failure", trigger="run_completed", metric="call_failed",
        severity="high", channel_uuids=[channel.channel_uuid],
    )
    run = await _finished(async_session, wf, "error")

    with patch("api.tasks.webhook_delivery._enqueue_delivery", new=AsyncMock()) as enqueue:
        fired = await evaluate.evaluate_run_alerts(run.id)

    assert fired == 1
    (event,) = await db_session.list_alert_events(org.id)
    assert event.title == "Any failure" and event.workflow_run_id == run.id and event.severity == "high"
    enqueue.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_second_failure_inside_the_cooldown_does_not_alert_again(db_session, async_session):
    org, wf = await _setup(async_session)
    await db_session.create_alert_rule(
        org.id, name="Any failure", trigger="run_completed", metric="call_failed", cooldown_minutes=60
    )
    first = await _finished(async_session, wf, "error")
    second = await _finished(async_session, wf, "error")

    with patch("api.tasks.webhook_delivery._enqueue_delivery", new=AsyncMock()):
        assert await evaluate.evaluate_run_alerts(first.id) == 1
        assert await evaluate.evaluate_run_alerts(second.id) == 0

    assert len(await db_session.list_alert_events(org.id)) == 1


@pytest.mark.asyncio
async def test_a_healthy_call_and_a_rule_for_another_agent_stay_quiet(db_session, async_session):
    org, wf = await _setup(async_session)
    await db_session.create_alert_rule(org.id, name="All", trigger="run_completed", metric="call_failed")
    other_agent = WorkflowModel(name="Support", organization_id=org.id, user_id=wf.user_id)
    async_session.add(other_agent)
    await async_session.flush()
    await db_session.create_alert_rule(
        org.id, name="Other agent", trigger="run_completed", metric="call_failed",
        scope_workflow_id=other_agent.id,
    )
    ok = await _finished(async_session, wf, "completed")
    bad = await _finished(async_session, wf, "error")

    with patch("api.tasks.webhook_delivery._enqueue_delivery", new=AsyncMock()):
        assert await evaluate.evaluate_run_alerts(ok.id) == 0
        assert await evaluate.evaluate_run_alerts(bad.id) == 1  # only the unscoped rule

    assert [e.title for e in await db_session.list_alert_events(org.id)] == ["All"]


@pytest.mark.asyncio
async def test_a_window_rule_over_its_threshold_fires_and_under_it_does_not(db_session, async_session):
    org, wf = await _setup(async_session)
    await db_session.create_alert_rule(
        org.id, name="Calls dried up", trigger="window", metric="window_run_count",
        comparator="lt", threshold=3, window_minutes=60,
    )
    await _finished(async_session, wf, "completed")  # 1 call in the window: below 3

    with patch("api.tasks.webhook_delivery._enqueue_delivery", new=AsyncMock()):
        assert await evaluate.evaluate_window_alerts() >= 1

    assert [e.title for e in await db_session.list_alert_events(org.id)] == ["Calls dried up"]


@pytest.mark.asyncio
async def test_evaluation_never_raises_into_the_caller(db_session):
    with patch.object(evaluate.db_client, "get_workflow_run_by_id", new=AsyncMock(side_effect=RuntimeError("db down"))):
        assert await evaluate.evaluate_run_alerts(1) == 0
