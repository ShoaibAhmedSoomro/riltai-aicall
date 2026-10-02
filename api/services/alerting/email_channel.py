"""Email transport for alert deliveries.

Sends through the deployment's existing email layer (services/email.py, Resend over
HTTP), so there is one place that knows how mail leaves and whether it is configured.
This module only turns an alert payload into a message and says whether a failed send
is worth retrying.
"""

from api.services.email import email_is_configured, send_email
from api.services.email_templates import render_email


class EmailDeliveryError(Exception):
    """A send that did not go. ``transient`` decides retry vs dead-letter."""

    def __init__(self, message: str, *, transient: bool):
        super().__init__(message)
        self.transient = transient


def render_alert_email(payload: dict):
    """The message for one alert, from the same payload a webhook channel receives."""
    severity = str(payload.get("severity", "")).upper()
    title = str(payload.get("title") or "Alert")
    paragraphs = [str(payload["summary"])] if payload.get("summary") else []
    for label, key in (("Agent", "workflow_name"), ("Rule", "rule_name"), ("Time", "occurred_at")):
        if payload.get(key):
            paragraphs.append(f"{label}: {payload[key]}")
    link = payload.get("link")
    return render_email(
        preheader=f"{severity} alert: {title}" if severity else title,
        heading=title,
        paragraphs=paragraphs,
        cta_label="Open in AICall" if link else None,
        cta_url=link or None,
        footnote="You are receiving this because an alert channel in your organization includes you.",
    )


async def send_alert_email(*, recipients: list[str], payload: dict) -> None:
    """Send to every recipient; raise if any did not go.

    Not configured is permanent (retrying cannot fix a missing key). A provider
    failure is transient: retried with backoff, then dead-lettered.
    """
    if not email_is_configured():
        raise EmailDeliveryError("Email is not configured on this deployment", transient=False)
    if not recipients:
        raise EmailDeliveryError("The channel has no recipients", transient=False)

    try:
        message = render_alert_email(payload)
    except ValueError as exc:  # e.g. a link that is not http(s): retrying cannot fix it
        raise EmailDeliveryError(str(exc), transient=False) from exc

    subject = f"[{str(payload.get('severity', 'alert')).upper()}] {payload.get('title', 'Alert')}"
    failed = [
        to for to in recipients
        if not await send_email(to=to, subject=subject, html=message.html, text=message.text)
    ]
    if failed:
        # send_email reports only yes/no, so a rejection and an outage look alike
        # and both are retried; the dead-letter cap bounds that.
        raise EmailDeliveryError(
            f"{len(failed)} of {len(recipients)} recipients not accepted", transient=True
        )
