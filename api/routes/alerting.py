"""Alert rules, channels and events.

Reading the feed and acknowledging an alert is open to any member. Creating or changing
rules and channels is admin-only: a webhook channel sends organization data to a URL,
so it is the same class of change as an integration.

Everything is scoped to the caller's organization at the query. A rule is validated on
write -- the metric must exist, the agent must be this organization's, every channel
must resolve -- because a rule that silently never fires is worse than a 400.
"""

import asyncio
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.db import db_client
from api.db.alert_client import DuplicateAlertNameError
from api.db.models import AlertChannelModel, AlertEventModel, AlertRuleModel, UserModel
from api.enums import AlertChannelType, AlertComparator, AlertSeverity
from api.schemas.alerting import (
    AlertChannelCreate,
    AlertChannelResponse,
    AlertChannelTestResponse,
    AlertChannelUpdate,
    AlertEventResponse,
    AlertEventsResponse,
    AlertMetricResponse,
    AlertMetricsResponse,
    AlertRuleCreate,
    AlertRuleResponse,
    AlertRuleUpdate,
    clean_channel_config,
)
from api.services.alerting.deliver import send_test_alert
from api.services.alerting.metrics import METRICS, get_metric
from api.services.auth.depends import get_user_with_selected_organization, require_admin
from api.services.email import email_is_configured

router = APIRouter(prefix="/alerts")

TEST_WAIT_SECONDS = 10.0
TEST_POLL_SECONDS = 0.5


def _channel(row: AlertChannelModel) -> AlertChannelResponse:
    return AlertChannelResponse(
        channel_uuid=row.channel_uuid, name=row.name, type=row.type,
        config=row.config or {}, is_active=row.is_active, created_at=row.created_at,
    )


def _rule(row: AlertRuleModel) -> AlertRuleResponse:
    return AlertRuleResponse(
        rule_uuid=row.rule_uuid, name=row.name, is_active=row.is_active,
        scope_workflow_id=row.scope_workflow_id, trigger=row.trigger, metric=row.metric,
        comparator=row.comparator, threshold=row.threshold, match_value=row.match_value,
        window_minutes=row.window_minutes, severity=row.severity,
        cooldown_minutes=row.cooldown_minutes, channel_uuids=list(row.channel_uuids or []),
        last_fired_at=row.last_fired_at, created_at=row.created_at,
    )


def _event(row: AlertEventModel) -> AlertEventResponse:
    return AlertEventResponse(
        event_uuid=row.event_uuid, severity=row.severity, title=row.title,
        detail=row.detail or {}, workflow_run_id=row.workflow_run_id,
        observed_value=row.observed_value, created_at=row.created_at,
        acknowledged_at=row.acknowledged_at,
    )


# -- metrics ------------------------------------------------------------------------------


@router.get("/metrics", response_model=AlertMetricsResponse)
async def list_alert_metrics(
    user: UserModel = Depends(get_user_with_selected_organization),
) -> AlertMetricsResponse:
    """What a rule may be about. The UI builds its form from this, so it can never
    offer a metric the evaluator does not compute."""
    return AlertMetricsResponse(
        metrics=[AlertMetricResponse(**vars(m)) for m in METRICS.values()],
        comparators=[c.value for c in AlertComparator],
        severities=[s.value for s in AlertSeverity],
    )


# -- channels ---------------------------------------------------------------------------------


async def _validated_config(user: UserModel, channel_type: str, config: dict) -> dict:
    if channel_type == AlertChannelType.EMAIL.value and not email_is_configured():
        raise HTTPException(
            status_code=400,
            detail="Email is not set up on this deployment, so an email channel could not "
            "send. Ask your administrator to configure it, or use a webhook channel.",
        )
    try:
        cleaned = clean_channel_config(channel_type, config)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    credential = cleaned.get("credential_uuid")
    if credential and not await db_client.get_credential_by_uuid(
        credential, user.selected_organization_id
    ):
        raise HTTPException(status_code=404, detail="Credential not found")
    return cleaned


@router.get("/channels", response_model=list[AlertChannelResponse])
async def list_channels(
    user: UserModel = Depends(get_user_with_selected_organization),
) -> list[AlertChannelResponse]:
    return [_channel(r) for r in await db_client.list_alert_channels(user.selected_organization_id)]


@router.post("/channels", response_model=AlertChannelResponse)
async def create_channel(
    request: AlertChannelCreate, user: UserModel = Depends(require_admin)
) -> AlertChannelResponse:
    config = await _validated_config(user, request.type.value, request.config)
    try:
        row = await db_client.create_alert_channel(
            user.selected_organization_id, request.name, request.type.value, config, request.is_active
        )
    except DuplicateAlertNameError:
        raise HTTPException(status_code=409, detail=f"A channel named '{request.name}' already exists")
    return _channel(row)


@router.get("/channels/{channel_uuid}", response_model=AlertChannelResponse)
async def get_channel(
    channel_uuid: str, user: UserModel = Depends(get_user_with_selected_organization)
) -> AlertChannelResponse:
    row = await db_client.get_alert_channel(user.selected_organization_id, channel_uuid)
    if not row:
        raise HTTPException(status_code=404, detail="Channel not found")
    return _channel(row)


@router.patch("/channels/{channel_uuid}", response_model=AlertChannelResponse)
async def update_channel(
    channel_uuid: str, request: AlertChannelUpdate, user: UserModel = Depends(require_admin)
) -> AlertChannelResponse:
    current = await db_client.get_alert_channel(user.selected_organization_id, channel_uuid)
    if not current:
        raise HTTPException(status_code=404, detail="Channel not found")
    fields = request.model_dump(exclude_unset=True)
    if fields.get("config") is not None:
        fields["config"] = await _validated_config(user, current.type, fields["config"])
    try:
        row = await db_client.update_alert_channel(user.selected_organization_id, channel_uuid, **fields)
    except DuplicateAlertNameError:
        raise HTTPException(status_code=409, detail="A channel with that name already exists")
    return _channel(row)


@router.delete("/channels/{channel_uuid}")
async def delete_channel(channel_uuid: str, user: UserModel = Depends(require_admin)) -> dict:
    if not await db_client.delete_alert_channel(user.selected_organization_id, channel_uuid):
        raise HTTPException(status_code=404, detail="Channel not found")
    return {"deleted": True}


@router.post("/channels/{channel_uuid}/test", response_model=AlertChannelTestResponse)
async def test_channel(
    channel_uuid: str, user: UserModel = Depends(require_admin)
) -> AlertChannelTestResponse:
    """Send a synthetic alert through the real delivery path and report what happened."""
    channel = await db_client.get_alert_channel(user.selected_organization_id, channel_uuid)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    delivery = await send_test_alert(user.selected_organization_id, channel)

    # Poll the delivery row. A worker usually finishes within a second or two; if it
    # has not, say so rather than claim success or failure.
    waited = 0.0
    row = delivery
    while waited < TEST_WAIT_SECONDS:
        row = await db_client.get_webhook_delivery(delivery.id) or row
        if row.status != "pending" or row.last_error:
            break
        await asyncio.sleep(TEST_POLL_SECONDS)
        waited += TEST_POLL_SECONDS
    return AlertChannelTestResponse(
        status=row.status, error=row.last_error, attempts=row.attempt_count
    )


# -- rules --------------------------------------------------------------------------------------


async def _check_rule(user: UserModel, fields: dict) -> dict:
    """Validate a complete rule and return its stored form (trigger filled in)."""
    org = user.selected_organization_id
    metric = get_metric(fields.get("metric", ""))
    if metric is None:
        raise HTTPException(status_code=422, detail=f"Unknown metric '{fields.get('metric')}'")
    if metric.value_type == "number" and fields.get("threshold") is None:
        raise HTTPException(status_code=422, detail=f"'{metric.label}' needs a threshold")
    if metric.value_type == "text" and not (fields.get("match_value") or "").strip():
        raise HTTPException(status_code=422, detail=f"'{metric.label}' needs a value to match")
    if metric.trigger == "window" and not fields.get("window_minutes"):
        raise HTTPException(status_code=422, detail=f"'{metric.label}' needs a window in minutes")
    if metric.trigger != "window":
        fields["window_minutes"] = None
    if metric.value_type != "number":
        fields["threshold"] = None
    if metric.value_type != "text":
        fields["match_value"] = None

    scope = fields.get("scope_workflow_id")
    if scope is not None and not await db_client.get_workflow(scope, organization_id=org):
        raise HTTPException(status_code=404, detail="Agent not found")

    uuids = list(dict.fromkeys(fields.get("channel_uuids") or []))
    found = {c.channel_uuid for c in await db_client.get_alert_channels_by_uuids(org, uuids)}
    missing = [u for u in uuids if u not in found]
    if missing:
        raise HTTPException(status_code=422, detail="A selected channel no longer exists")
    fields["channel_uuids"] = uuids
    fields["trigger"] = metric.trigger
    return fields


@router.get("/rules", response_model=list[AlertRuleResponse])
async def list_rules(
    user: UserModel = Depends(get_user_with_selected_organization),
) -> list[AlertRuleResponse]:
    return [_rule(r) for r in await db_client.list_alert_rules(user.selected_organization_id)]


@router.post("/rules", response_model=AlertRuleResponse)
async def create_rule(
    request: AlertRuleCreate, user: UserModel = Depends(require_admin)
) -> AlertRuleResponse:
    fields = await _check_rule(user, request.model_dump(mode="json"))
    try:
        row = await db_client.create_alert_rule(user.selected_organization_id, **fields)
    except DuplicateAlertNameError:
        raise HTTPException(status_code=409, detail=f"A rule named '{request.name}' already exists")
    return _rule(row)


@router.get("/rules/{rule_uuid}", response_model=AlertRuleResponse)
async def get_rule(
    rule_uuid: str, user: UserModel = Depends(get_user_with_selected_organization)
) -> AlertRuleResponse:
    row = await db_client.get_alert_rule(user.selected_organization_id, rule_uuid)
    if not row:
        raise HTTPException(status_code=404, detail="Rule not found")
    return _rule(row)


@router.patch("/rules/{rule_uuid}", response_model=AlertRuleResponse)
async def update_rule(
    rule_uuid: str, request: AlertRuleUpdate, user: UserModel = Depends(require_admin)
) -> AlertRuleResponse:
    current = await db_client.get_alert_rule(user.selected_organization_id, rule_uuid)
    if not current:
        raise HTTPException(status_code=404, detail="Rule not found")
    changes = request.model_dump(mode="json", exclude_unset=True)
    clear_scope = changes.pop("clear_scope", False)
    merged = {
        "name": current.name, "is_active": current.is_active,
        "scope_workflow_id": current.scope_workflow_id, "metric": current.metric,
        "comparator": current.comparator, "threshold": current.threshold,
        "match_value": current.match_value, "window_minutes": current.window_minutes,
        "severity": current.severity, "cooldown_minutes": current.cooldown_minutes,
        "channel_uuids": list(current.channel_uuids or []),
    }
    merged.update(changes)
    if clear_scope:
        merged["scope_workflow_id"] = None
    fields = await _check_rule(user, merged)
    try:
        row = await db_client.update_alert_rule(user.selected_organization_id, rule_uuid, **fields)
    except DuplicateAlertNameError:
        raise HTTPException(status_code=409, detail="A rule with that name already exists")
    return _rule(row)


@router.delete("/rules/{rule_uuid}")
async def delete_rule(rule_uuid: str, user: UserModel = Depends(require_admin)) -> dict:
    if not await db_client.delete_alert_rule(user.selected_organization_id, rule_uuid):
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"deleted": True}


# -- events -----------------------------------------------------------------------------------------


@router.get("/events", response_model=AlertEventsResponse)
async def list_events(
    limit: int = Query(50, ge=1, le=200),
    severity: Optional[AlertSeverity] = None,
    since: Optional[datetime] = None,
    user: UserModel = Depends(get_user_with_selected_organization),
) -> AlertEventsResponse:
    rows = await db_client.list_alert_events(
        user.selected_organization_id, limit=limit,
        severity=severity.value if severity else None, since=since,
    )
    return AlertEventsResponse(events=[_event(r) for r in rows])


@router.post("/events/{event_uuid}/acknowledge", response_model=AlertEventResponse)
async def acknowledge_event(
    event_uuid: str, user: UserModel = Depends(get_user_with_selected_organization)
) -> AlertEventResponse:
    row = await db_client.acknowledge_alert_event(user.selected_organization_id, event_uuid, user.id)
    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")
    return _event(row)
