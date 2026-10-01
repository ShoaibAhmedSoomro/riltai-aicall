"""What actually goes over the wire to Resend, and what happens when it fails.

send_email is the only code that touches the provider, and it runs inside
request handlers and background jobs. The two promises worth pinning:

  It NEVER raises. A provider outage or a rejected sender must degrade to
  "not sent", because the caller has already written a row or created an
  account and cannot be left in a 500.

  A rejection is reported as a failure, not swallowed as success. "Check your
  inbox" for a message Resend refused is the worst outcome available.

The transport is httpx's own MockTransport, so the real client code runs and
only the network is replaced.
"""

import json
from unittest.mock import patch

import httpx
import pytest

from api.services import email


def _client_factory(handler):
    real = httpx.AsyncClient

    def make(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    return make


def _configured():
    return (
        patch.object(email, "RESEND_API_KEY", "re_test"),
        patch.object(email, "EMAIL_FROM", "AICall <noreply@example.com>"),
        patch.object(email, "PUBLIC_BASE_URL", "https://aicall.example.com"),
    )


@pytest.mark.asyncio
async def test_the_request_carries_sender_recipient_html_and_text():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "abc"})

    a, b, c = _configured()
    with a, b, c, patch.object(email.httpx, "AsyncClient", _client_factory(handler)):
        ok = await email.send_email(
            to="sam@example.com", subject="Hi", html="<p>x</p>", text="x"
        )

    assert ok is True
    assert seen["auth"] == "Bearer re_test"
    assert seen["body"]["from"] == "AICall <noreply@example.com>"
    assert seen["body"]["to"] == ["sam@example.com"]
    assert seen["body"]["subject"] == "Hi"
    assert seen["body"]["html"] == "<p>x</p>"
    # Without a text part, spam filters score the message down.
    assert seen["body"]["text"] == "x"


@pytest.mark.asyncio
async def test_a_message_with_no_text_part_omits_the_field_entirely():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={})

    a, b, c = _configured()
    with a, b, c, patch.object(email.httpx, "AsyncClient", _client_factory(handler)):
        await email.send_email(to="a@b.com", subject="s", html="<p>x</p>")

    # Not "text": null -- Resend would reject an explicit null.
    assert "text" not in seen["body"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 403, 422, 429, 500])
async def test_a_rejection_is_reported_as_not_sent(status):
    """403 is the usual one: a valid key with an unverified sender domain."""

    def handler(request):
        return httpx.Response(status, json={"message": "nope"})

    a, b, c = _configured()
    with a, b, c, patch.object(email.httpx, "AsyncClient", _client_factory(handler)):
        assert await email.send_email(to="a@b.com", subject="s", html="x") is False


@pytest.mark.asyncio
async def test_a_network_failure_degrades_instead_of_raising():
    def handler(request):
        raise httpx.ConnectError("provider unreachable")

    a, b, c = _configured()
    with a, b, c, patch.object(email.httpx, "AsyncClient", _client_factory(handler)):
        assert await email.send_email(to="a@b.com", subject="s", html="x") is False


@pytest.mark.asyncio
async def test_nothing_is_attempted_when_unconfigured():
    called = []

    def handler(request):
        called.append(request)
        return httpx.Response(200, json={})

    with (
        patch.object(email, "RESEND_API_KEY", None),
        patch.object(email, "EMAIL_FROM", None),
        patch.object(email.httpx, "AsyncClient", _client_factory(handler)),
    ):
        assert await email.send_email(to="a@b.com", subject="s", html="x") is False

    assert called == []


def test_recipients_are_redacted_for_the_logs():
    assert email._redact("sam@example.com") == "s***@example.com"
    assert email._redact("not-an-address") == "***"
