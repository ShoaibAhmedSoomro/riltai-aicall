"""Transactional email, over Resend's HTTP API.

One POST to one endpoint, so this uses httpx directly rather than adding the
`resend` SDK for a single call.

The central decision here is what happens when email is NOT configured, which
is the state every self-hosted deployment starts in and the state this one is
in today. Sending returns False and logs; it never raises. Callers must treat
a False as "the message did not go" and tell the user so -- an invite that was
recorded but not delivered is a real and useful state, and the invitations
screen already says exactly that. What must never happen is a silent success:
a password reset that reports "check your inbox" when nothing was sent is
worse than an error, because the user waits instead of retrying.
"""

import httpx
from loguru import logger

from api.constants import EMAIL_FROM, RESEND_API_KEY

_ENDPOINT = "https://api.resend.com/emails"
_TIMEOUT_SECONDS = 10.0


def email_is_configured() -> bool:
    """Whether outbound email can be sent at all.

    Read this before offering a flow that depends on delivery, so the UI can
    say "email is not set up" instead of accepting a request that goes nowhere.
    """
    return bool(RESEND_API_KEY and EMAIL_FROM)


async def send_email(*, to: str, subject: str, html: str) -> bool:
    """Send one message. Returns whether it was accepted for delivery.

    Never raises: this is called from request handlers and background jobs
    where a provider outage must not become a 500 or kill a job.
    """
    if not email_is_configured():
        logger.warning(
            "Email not sent to {}: RESEND_API_KEY / EMAIL_FROM not configured",
            _redact(to),
        )
        return False

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(
                _ENDPOINT,
                headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
                json={"from": EMAIL_FROM, "to": [to], "subject": subject, "html": html},
            )
    except Exception as exc:
        # Provider unreachable, DNS, timeout. The caller degrades; the address
        # is redacted because logs are not the place for a recipient list.
        logger.warning("Email to {} failed: {}", _redact(to), exc)
        return False

    if response.status_code >= 400:
        # Resend puts the reason in the body -- a rejected From domain reads as
        # a generic 403 otherwise, and that is the most common setup mistake.
        logger.warning(
            "Email to {} rejected with {}: {}",
            _redact(to),
            response.status_code,
            response.text[:300],
        )
        return False

    logger.info("Email sent to {}", _redact(to))
    return True


def _redact(address: str) -> str:
    """j***@example.com -- enough to correlate, not enough to harvest."""
    local, _, domain = (address or "").partition("@")
    if not domain:
        return "***"
    return f"{local[:1]}***@{domain}"
