"""Alert emails ride the webhook delivery engine: same claim, retry and dead-letter."""

import itertools
from unittest.mock import AsyncMock, patch

import pytest

from api.db.models import OrganizationModel
from api.services.alerting import email_channel
from api.tasks import webhook_delivery as task

_n = itertools.count()
PAYLOAD = {
    "title": "Failures", "severity": "high", "summary": "Call failed. Observed: 1.",
    "rule_name": "Failures", "workflow_name": "Sales", "link": "https://aicall.test/alerts",
}


async def _email_delivery(db_session, async_session, recipients=("ops@example.com",), max_attempts=3):
    org = OrganizationModel(provider_id=f"ad-org-{next(_n)}")
    async_session.add(org)
    await async_session.flush()
    delivery, _ = await db_session.create_delivery(
        organization_id=org.id, idempotency_key=f"alert:{next(_n)}", payload=PAYLOAD,
        max_attempts=max_attempts, transport="email", destination={"recipients": list(recipients)},
    )
    return delivery


async def _run(db_session, delivery_id):
    with patch.object(task, "_enqueue_delivery", new=AsyncMock()) as enqueue:
        await task.deliver_webhook(None, delivery_id)
    return enqueue


def _mail(ok=True):
    """Patch the mail layer; the mock is on the returned context's `.send`."""
    send = AsyncMock(return_value=ok)
    ctx = patch.multiple(email_channel, email_is_configured=lambda: True, send_email=send)
    ctx.send = send
    return ctx


@pytest.mark.asyncio
async def test_an_accepted_email_marks_the_delivery_succeeded(db_session, async_session):
    delivery = await _email_delivery(db_session, async_session, recipients=("a@x.co", "b@x.co"))

    mail = _mail(True)
    with mail:
        await _run(db_session, delivery.id)

    row = await db_session.get_webhook_delivery(delivery.id)
    assert row.status == "succeeded" and row.attempt_count == 1
    assert mail.send.await_count == 2  # one message per recipient


@pytest.mark.asyncio
async def test_a_refused_email_is_retried_with_backoff(db_session, async_session):
    delivery = await _email_delivery(db_session, async_session)

    with _mail(False):
        enqueue = await _run(db_session, delivery.id)

    row = await db_session.get_webhook_delivery(delivery.id)
    assert row.status == "pending" and row.attempt_count == 1 and row.scheduled_for is not None
    assert "not accepted" in row.last_error
    enqueue.assert_awaited_once()  # the next attempt is queued


@pytest.mark.asyncio
async def test_retries_stop_at_the_attempt_ceiling_and_park_the_delivery(db_session, async_session):
    delivery = await _email_delivery(db_session, async_session, max_attempts=1)

    with _mail(False):
        await _run(db_session, delivery.id)

    assert (await db_session.get_webhook_delivery(delivery.id)).status == "dead_letter"


@pytest.mark.asyncio
async def test_email_that_is_not_set_up_dead_letters_at_once_instead_of_looping(db_session, async_session):
    delivery = await _email_delivery(db_session, async_session)

    with patch.object(email_channel, "email_is_configured", lambda: False):
        enqueue = await _run(db_session, delivery.id)

    row = await db_session.get_webhook_delivery(delivery.id)
    assert row.status == "dead_letter" and "not configured" in row.last_error
    enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_channel_with_no_recipients_is_a_permanent_failure(db_session, async_session):
    delivery = await _email_delivery(db_session, async_session, recipients=())

    with _mail(True):
        await _run(db_session, delivery.id)

    assert (await db_session.get_webhook_delivery(delivery.id)).status == "dead_letter"


def test_the_message_names_the_alert_and_links_to_it():
    message = email_channel.render_alert_email(PAYLOAD)
    assert "Failures" in message.html and "https://aicall.test/alerts" in message.text
    assert "Sales" in message.text


def test_a_payload_with_no_link_still_renders():
    message = email_channel.render_alert_email({**PAYLOAD, "link": None})
    assert "https://" not in message.text


@pytest.mark.asyncio
async def test_an_alert_payload_carries_no_caller_number_or_transcript():
    from api.services.alerting.deliver import build_payload

    payload = build_payload(
        event_uuid="e", title="T", severity="low", summary="S", rule_name="R",
        workflow_name="W", link=None, observed_value=1.0,
    )
    assert set(payload) == {
        "kind", "event_uuid", "title", "severity", "summary", "rule_name",
        "workflow_name", "observed_value", "link", "occurred_at",
    }
