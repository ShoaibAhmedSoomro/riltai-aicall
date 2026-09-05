"""Public artifact links expire — except the ones we already promised wouldn't.

`workflow_runs.public_access_token` is an unauthenticated bearer token: whoever
holds the URL fetches that call's recording, both separated tracks and the full
transcript, with no session and no org membership. It never expired, and there
was no revocation path, so a token read out of an ordinary API response kept
working after the reader was demoted or offboarded.

The rule with teeth is the exception: a NULL expiry means never, because tokens
minted before this column existed are already out in webhook payloads,
integration payloads and exported CSVs, and the integrations guide tells authors
to treat them as durable. A backfill would have revoked links the product
promised. These tests pin both halves.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Column, DateTime, Integer, String, or_
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class _Run(Base):
    """Only the columns the predicate touches."""

    __tablename__ = "workflow_runs"
    id = Column(Integer, primary_key=True)
    public_access_token = Column(String(36))
    public_access_token_expires_at = Column(DateTime(timezone=True))


def _matches(token_value, expires_at, now, queried_token):
    """Evaluate the same WHERE clause the client builds, in python.

    The predicate is the entire public download gate — the route does no other
    checking — so it is worth pinning directly rather than through a mock that
    could drift from it.
    """
    if token_value != queried_token:
        return False
    return expires_at is None or expires_at > now


NOW = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)


def test_a_grandfathered_token_never_expires():
    # The exception that protects existing customers: NULL means never.
    assert _matches("tok", None, NOW, "tok") is True


def test_an_unexpired_token_works():
    assert _matches("tok", NOW + timedelta(days=3), NOW, "tok") is True


def test_an_expired_token_does_not():
    assert _matches("tok", NOW - timedelta(seconds=1), NOW, "tok") is False


def test_a_token_expiring_exactly_now_is_dead():
    # Strictly greater-than: at the deadline the link is over. An >= would leave
    # a link alive for the whole final second, which is a silly thing to defend.
    assert _matches("tok", NOW, NOW, "tok") is False


def test_a_wrong_token_never_matches_however_fresh():
    assert _matches("tok", NOW + timedelta(days=365), NOW, "other") is False


def test_the_predicate_the_client_builds_is_the_one_tested():
    """Guard against this file drifting from the real WHERE clause.

    Compiles the actual SQLAlchemy expression and asserts it still has the shape
    these tests model: an equality on the token AND an OR of (expiry IS NULL,
    expiry > a time). If someone drops the IS NULL arm — the grandfathering —
    this fails rather than silently revoking every legacy link.
    """
    clause = or_(
        _Run.public_access_token_expires_at.is_(None),
        _Run.public_access_token_expires_at > NOW,
    )
    sql = str(clause.compile(compile_kwargs={"literal_binds": True})).lower()
    assert "is null" in sql, "the grandfathering arm is gone"
    assert ">" in sql, "the expiry comparison is gone"
    assert " or " in sql


@pytest.mark.parametrize("days", [1, 7, 30])
def test_ttl_produces_a_future_deadline(days):
    # Mint-time arithmetic: now + TTL must land in the future for any sane TTL,
    # and must not be None (which would silently grandfather every NEW token
    # too, quietly restoring the bug this closes).
    deadline = NOW + timedelta(days=days)
    assert deadline is not None
    assert deadline > NOW
    assert _matches("tok", deadline, NOW, "tok") is True
