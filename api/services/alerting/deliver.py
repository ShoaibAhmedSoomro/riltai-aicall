"""Hand an alert to its channels, on the durable delivery engine.

One delivery row per (alert, channel). The row is keyed so a retried evaluation cannot
send the same alert twice, and the engine (tasks/webhook_delivery.py) owns retry,
backoff and dead-lettering. This module only decides what the row says.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Optional

from loguru import logger

from api.constants import DEFAULT_WEBHOOK_DELIVERY_CONFIG, PUBLIC_BASE_URL
from api.db import db_client
from api.enums import AlertChannelType


def alert_link(workflow_id: Optional[int], workflow_run_id: Optional[int]) -> Optional[str]:
    """Where to look, or None when the deployment has no public address to link to."""
    if not PUBLIC_BASE_URL:
        return None
    base = PUBLIC_BASE_URL.rstrip("/")
    if workflow_id and workflow_run_id:
        return f"{base}/workflow/{workflow_id}/run/{workflow_run_id}"
    return f"{base}/alerts"


def build_payload(
    *,
    event_uuid: str,
    title: str,
    severity: str,
    summary: str,
    rule_name: str,
    workflow_name: Optional[str],
    link: Optional[str],
    observed_value: Optional[float],
) -> dict:
    """What a channel receives. No caller numbers or transcript text: an alert says
    that something happened and where to look, and the link needs a login."""
    return {
        "kind": "alert",
        "event_uuid": event_uuid,
        "title": title,
        "severity": severity,
        "summary": summary,
        "rule_name": rule_name,
        "workflow_name": workflow_name,
        "observed_value": observed_value,
        "link": link,
        "occurred_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


async def dispatch_to_channel(
    organization_id: int, channel, payload: dict, idempotency_key: str
):
    """Create the delivery for one channel and enqueue its first attempt.

    Returns ``(delivery, created)``; ``created`` is False on a repeat of the same key.
    """
    from api.tasks.webhook_delivery import _enqueue_delivery  # avoid import cycle

    config = channel.config or {}
    common = dict(
        organization_id=organization_id,
        idempotency_key=idempotency_key,
        payload=payload,
        max_attempts=DEFAULT_WEBHOOK_DELIVERY_CONFIG["max_attempts"],
        webhook_name=channel.name,
    )
    if channel.type == AlertChannelType.EMAIL.value:
        delivery, created = await db_client.create_delivery(
            transport="email", destination={"recipients": config.get("recipients", [])}, **common
        )
    else:
        delivery, created = await db_client.create_delivery(
            transport="http",
            endpoint_url=config.get("endpoint_url"),
            http_method=config.get("http_method", "POST"),
            custom_headers=config.get("custom_headers"),
            credential_uuid=config.get("credential_uuid"),
            **common,
        )
    if created:
        await _enqueue_delivery(delivery.id, attempt_count=0)
    return delivery, created


async def dispatch_to_rule_channels(rule, organization_id: int, event_uuid: str, payload: dict) -> int:
    """Send an event to every active channel the rule names. A channel that has been
    deleted since is skipped with a warning, never a failure."""
    channels = await db_client.get_alert_channels_by_uuids(organization_id, list(rule.channel_uuids or []))
    sent = 0
    for channel in channels:
        if not channel.is_active:
            continue
        try:
            _, created = await dispatch_to_channel(
                organization_id, channel, payload, f"alert:{event_uuid}:{channel.channel_uuid}"
            )
            sent += int(created)
        except Exception as e:
            logger.error(f"Alert {event_uuid}: could not queue delivery to channel {channel.channel_uuid}: {e}")
    return sent


async def send_test_alert(organization_id: int, channel):
    """Fire a synthetic alert through the real delivery path; returns the delivery.

    The key is unique per call, so pressing Test twice sends twice. The caller reads
    the outcome from the delivery row.
    """
    test_id = uuid.uuid4()
    payload = build_payload(
        event_uuid=str(test_id),
        title="Test alert from AICall",
        severity="low",
        summary="This is a test. If you can read it, this channel works.",
        rule_name="Test",
        workflow_name=None,
        link=alert_link(None, None),
        observed_value=None,
    )
    delivery, _ = await dispatch_to_channel(
        organization_id, channel, payload, f"alert-test:{channel.channel_uuid}:{test_id}"
    )
    return delivery
