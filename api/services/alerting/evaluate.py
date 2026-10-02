"""Deciding when an alert rule fires.

Two entry points:

* ``evaluate_run_alerts(run_id)`` -- once, when a call finishes and its post-call work
  (QA tags, safety scan) is done. Run-scoped rules.
* ``evaluate_window_alerts()`` -- on a cron every few minutes. Rules over the last N
  minutes of calls.

Both go through ``fire`` so cooldown, the event record and delivery work the same way.
Neither may raise into its caller: an alerting bug must never break billing or the
post-call pipeline.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from loguru import logger

from api.db import db_client
from api.enums import AlertComparator, AlertTrigger
from api.services.alerting.deliver import (
    alert_link,
    build_payload,
    dispatch_to_rule_channels,
)
from api.services.alerting.metrics import (
    compare,
    get_metric,
    run_observation,
    window_observation,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _fmt(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return str(int(value)) if float(value).is_integer() else f"{value:.1f}"


_SYMBOL = {
    AlertComparator.GT.value: ">",
    AlertComparator.GTE.value: "at least",
    AlertComparator.LT.value: "<",
    AlertComparator.LTE.value: "at most",
    AlertComparator.EQ.value: "=",
}


def describe_condition(rule) -> str:
    """The rule in a sentence, for the alert's title and summary."""
    metric = get_metric(rule.metric)
    label = metric.label if metric else rule.metric
    if metric and metric.value_type == "text":
        return f"{label}: {rule.match_value}"
    if metric and metric.value_type == "flag":
        return label
    unit = f" {metric.unit}" if metric and metric.unit else ""
    window = f" (last {rule.window_minutes} min)" if rule.window_minutes else ""
    return f"{label} {_SYMBOL.get(rule.comparator, rule.comparator)} {_fmt(rule.threshold)}{unit}{window}"


def run_rule_fires(rule, run) -> tuple[bool, Optional[float]]:
    """Does this finished call trip this run-scoped rule? Pure."""
    metric = get_metric(rule.metric)
    if metric is None or metric.trigger != AlertTrigger.RUN_COMPLETED.value:
        return False, None
    observed, holds = run_observation(rule.metric, run, rule.match_value)
    if metric.value_type in ("flag", "text"):
        return holds, observed
    if observed is None or rule.threshold is None:
        return False, observed
    return compare(rule.comparator, observed, rule.threshold), observed


def window_rule_fires(rule, stats: dict) -> tuple[bool, Optional[float]]:
    """Does this window of calls trip this window rule? Pure."""
    metric = get_metric(rule.metric)
    if metric is None or metric.trigger != AlertTrigger.WINDOW.value:
        return False, None
    observed = window_observation(rule.metric, stats)
    if observed is None or rule.threshold is None:
        return False, observed
    return compare(rule.comparator, observed, rule.threshold), observed


async def fire(
    rule,
    organization_id: int,
    *,
    observed: Optional[float],
    workflow_run_id: Optional[int] = None,
    workflow_id: Optional[int] = None,
    workflow_name: Optional[str] = None,
) -> bool:
    """Record the event and deliver it, unless the rule is cooling down."""
    if not await db_client.claim_alert_rule_fire(rule.id, _now()):
        return False  # fired recently; a persistent condition must not repeat itself
    condition = describe_condition(rule)
    title = f"{rule.name}"
    summary = f"{condition}. Observed: {_fmt(observed)}."
    event = await db_client.record_alert_event(
        organization_id,
        alert_rule_id=rule.id,
        severity=rule.severity,
        title=title,
        detail={"condition": condition, "workflow_name": workflow_name, "workflow_id": workflow_id},
        workflow_run_id=workflow_run_id,
        observed_value=observed,
    )
    payload = build_payload(
        event_uuid=event.event_uuid,
        title=title,
        severity=rule.severity,
        summary=summary,
        rule_name=rule.name,
        workflow_name=workflow_name,
        link=alert_link(workflow_id, workflow_run_id),
        observed_value=observed,
    )
    await dispatch_to_rule_channels(rule, organization_id, event.event_uuid, payload)
    logger.info(f"Alert fired: rule '{rule.name}' (org {organization_id}) observed {_fmt(observed)}")
    return True


def _in_scope(rule, workflow_id: int) -> bool:
    return rule.scope_workflow_id is None or rule.scope_workflow_id == workflow_id


async def evaluate_run_alerts(workflow_run_id: int) -> int:
    """Evaluate run-scoped rules against one finished call; returns how many fired."""
    try:
        run = await db_client.get_workflow_run_by_id(workflow_run_id)
        workflow = getattr(run, "workflow", None) if run else None
        if run is None or workflow is None or workflow.organization_id is None:
            return 0
        rules = await db_client.list_alert_rules(
            workflow.organization_id, active_only=True, trigger=AlertTrigger.RUN_COMPLETED.value
        )
        fired = 0
        for rule in rules:
            if not _in_scope(rule, run.workflow_id):
                continue
            hit, observed = run_rule_fires(rule, run)
            if hit and await fire(
                rule, workflow.organization_id, observed=observed,
                workflow_run_id=run.id, workflow_id=run.workflow_id, workflow_name=workflow.name,
            ):
                fired += 1
        return fired
    except Exception as e:
        logger.error(f"Alert evaluation for run {workflow_run_id} failed: {e}")
        return 0


async def evaluate_window_alerts() -> int:
    """Evaluate every active window rule; returns how many fired."""
    fired = 0
    try:
        rules = await db_client.list_all_active_alert_rules(AlertTrigger.WINDOW.value)
    except Exception as e:
        logger.error(f"Could not load window alert rules: {e}")
        return 0
    for rule in rules:
        try:
            if not rule.window_minutes:
                continue
            stats = await db_client.get_window_run_stats(
                rule.organization_id, rule.window_minutes, rule.scope_workflow_id
            )
            hit, observed = window_rule_fires(rule, stats)
            if hit and await fire(rule, rule.organization_id, observed=observed, workflow_id=rule.scope_workflow_id):
                fired += 1
        except Exception as e:
            logger.error(f"Window alert rule {rule.rule_uuid} failed: {e}")
    return fired
