"""The reporting numbers that shipped wrong, pinned so they stay right.

Four independent figures the product already displayed, each wrong in a way
that looked like a measurement:

(a) `total_duration_seconds` on /usage/runs was accumulated in the row loop,
    which runs over ONE PAGE. So "total talk time" was the talk time of
    whichever 50 runs you were looking at, and it changed when you turned the
    page. This is the test that would have caught it: two pages of runs, and
    the total has to be the same on both.

(b) `total_rilt_tokens` was hardcoded 0 while titled "Total RiltAI Tokens".

(c) `usage_info.isnot(None)` filtered nothing, because 0c1223cc266f made the
    column NOT NULL — while the dashboard hint said "runs with recorded usage".

(d) The daily report counted the literal "XFER", which nothing in the platform
    writes, so its transfer count was structurally zero.

(a) and (c) run against a real database because they are SQL behaviour over
JSON columns; a mocked session would assert the query I wrote rather than the
number it returns.
"""

import itertools
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.db.models import (
    OrganizationModel,
    UserModel,
    WorkflowModel,
    WorkflowRunModel,
)
from api.services.reports.daily_report import DailyReportService
from api.services.workflow.disposition_codes import (
    SYSTEM_DISPOSITION_CODES,
    TRANSFER_DISPOSITION_CODES,
)

# ── (d) transfers ───────────────────────────────────────────────────────────


def test_the_transfer_codes_are_the_ones_the_platform_writes():
    assert TRANSFER_DISPOSITION_CODES == ("call_transferred", "transfer_call")
    # Both are real end-task reasons, so they are already in the catalogue the
    # disposition filter offers -- a transfer code the UI cannot filter by
    # would be a number you can see and not drill into.
    for code in TRANSFER_DISPOSITION_CODES:
        assert code in SYSTEM_DISPOSITION_CODES


def _run(disposition):
    """A row shaped like get_workflow_runs_for_daily_report returns."""
    return {
        "id": 1,
        "workflow_id": 1,
        "workflow_name": "agg",
        "gathered_context": {"mapped_call_disposition": disposition},
        "initial_context": {},
        "usage_info": {"call_duration_seconds": 30},
        "created_at": datetime(2026, 9, 9, 12, 0, tzinfo=UTC),
    }


@pytest.mark.asyncio
async def test_transfers_count_the_real_codes_and_not_the_literal_xfer(monkeypatch):
    """The exact case the old comparison got backwards.

    "XFER" is not written by anything in the platform. An organization may
    define it as a custom code of its own, and it must NOT be counted: a custom
    code means whatever that organization decided it means.
    """
    runs = [
        _run("call_transferred"),
        _run("transfer_call"),
        _run("XFER"),
        _run("user_hangup"),
        {**_run(None), "gathered_context": None},
    ]
    monkeypatch.setattr(
        "api.services.reports.daily_report.db_client",
        SimpleNamespace(
            get_workflow_runs_for_daily_report=AsyncMock(return_value=runs)
        ),
    )

    report = await DailyReportService().get_daily_report(
        organization_id=1, date="2026-09-09", timezone="UTC"
    )

    assert report["metrics"]["transferred_count"] == 2
    # The deprecated duplicate carries the real number for one release rather
    # than staying 0, because the reports card still reads it.
    assert report["metrics"]["xfer_count"] == 2
    assert report["metrics"]["total_runs"] == 5


@pytest.mark.asyncio
async def test_a_run_with_no_gathered_context_does_not_crash_the_count(monkeypatch):
    monkeypatch.setattr(
        "api.services.reports.daily_report.db_client",
        SimpleNamespace(
            get_workflow_runs_for_daily_report=AsyncMock(
                return_value=[{**_run(None), "gathered_context": None}]
            )
        ),
    )
    report = await DailyReportService().get_daily_report(
        organization_id=1, date="2026-09-09", timezone="UTC"
    )
    assert report["metrics"]["transferred_count"] == 0


# ── (a) (b) (c) usage totals, against a real database ───────────────────────


# A counter rather than id(): two lists in one test can share an address once
# the first is garbage-collected, which collided the unique provider_id.
_suffix = itertools.count()


async def _org_with_runs(async_session, runs):
    """One org, one workflow, and a run per (duration, charge) pair given."""
    suffix = next(_suffix)
    org = OrganizationModel(provider_id=f"agg-org-{suffix}")
    async_session.add(org)
    await async_session.flush()

    user = UserModel(provider_id=f"agg-user-{suffix}", selected_organization_id=org.id)
    async_session.add(user)
    await async_session.flush()

    workflow = WorkflowModel(name="agg", organization_id=org.id, user_id=user.id)
    async_session.add(workflow)
    await async_session.flush()

    for duration, charge in runs:
        usage_info = {} if duration is None else {"call_duration_seconds": duration}
        cost_info = {} if charge is None else {"charge_usd": charge}
        async_session.add(
            WorkflowRunModel(
                workflow_id=workflow.id,
                name="r",
                mode="voice",
                is_completed=True,
                usage_info=usage_info,
                cost_info=cost_info,
            )
        )
    await async_session.flush()
    return org, workflow


@pytest.mark.asyncio
async def test_the_totals_do_not_change_when_you_turn_the_page(
    db_session, async_session
):
    """THE regression this task exists for.

    The totals used to be summed in the row loop, over the page. Ask for page 1
    of 3 and you were told the total was a third of itself, with no indication
    the figure was partial.
    """
    org, _ = await _org_with_runs(
        async_session, [(30, 0.10), (60, 0.20), (90, 0.30), (120, 0.40)]
    )

    page1 = await db_session.get_usage_history(org.id, limit=2, offset=0)
    page2 = await db_session.get_usage_history(org.id, limit=2, offset=2)

    _, count1, charge1, duration1 = page1
    _, count2, charge2, duration2 = page2

    assert count1 == count2 == 4
    assert duration1 == duration2 == 300  # 30+60+90+120, not the page's 90
    assert charge1 == charge2 == pytest.approx(1.00)  # not the page's 0.30


@pytest.mark.asyncio
async def test_runs_with_no_duration_or_cost_contribute_nothing(
    db_session, async_session
):
    """A missing JSON key must add nothing, not raise.

    These blobs predate any schema: usage_info is NOT NULL but its contents are
    whatever the run happened to record, and casting a missing key would error
    for the whole query rather than skipping the row.
    """
    org, _ = await _org_with_runs(
        async_session, [(45, 0.15), (None, None), (None, 0.05), (15, None)]
    )

    runs, count, charge, duration = await db_session.get_usage_history(org.id, limit=50)

    # (c) Every run is returned. The old query looked like it filtered on
    # usage_info being present and did not, so this asserts the real behaviour
    # rather than the label that was on it.
    assert count == 4
    assert len(runs) == 4
    assert duration == 60  # 45 + 15
    assert charge == pytest.approx(0.20)  # 0.15 + 0.05


@pytest.mark.asyncio
async def test_each_row_reports_its_own_cost_not_zero(db_session, async_session):
    """The per-run figure was hardcoded 0 as well as the total.

    Every row of the usage table showed no token usage regardless of what the
    call cost, which is the same false measurement as the total.
    """
    org, _ = await _org_with_runs(async_session, [(60, 0.25)])

    runs, _, _, _ = await db_session.get_usage_history(org.id, limit=50)

    assert len(runs) == 1
    # Cost in cents, the unit "rilt tokens" already means elsewhere.
    assert runs[0]["rilt_token_usage"] == pytest.approx(25.0)
    assert runs[0]["charge_usd"] == pytest.approx(0.25)
    assert runs[0]["call_duration_seconds"] == 60


@pytest.mark.asyncio
async def test_a_row_with_no_cost_reports_zero_tokens_rather_than_failing(
    db_session, async_session
):
    org, _ = await _org_with_runs(async_session, [(60, None)])
    runs, _, _, _ = await db_session.get_usage_history(org.id, limit=50)
    assert runs[0]["rilt_token_usage"] == 0
    # And no charge_usd key at all, rather than a zero that reads as free.
    assert "charge_usd" not in runs[0]


@pytest.mark.asyncio
async def test_an_organization_only_sees_its_own_totals(db_session, async_session):
    mine, _ = await _org_with_runs(async_session, [(60, 1.00)])
    theirs, _ = await _org_with_runs(async_session, [(600, 99.00)])

    _, count, charge, duration = await db_session.get_usage_history(mine.id, limit=50)

    assert count == 1
    assert duration == 60
    assert charge == pytest.approx(1.00)

    _, their_count, their_charge, _ = await db_session.get_usage_history(
        theirs.id, limit=50
    )
    assert their_count == 1
    assert their_charge == pytest.approx(99.00)


@pytest.mark.asyncio
async def test_an_organization_with_no_runs_totals_zero_rather_than_failing(
    db_session, async_session
):
    org = OrganizationModel(provider_id="agg-org-empty")
    async_session.add(org)
    await async_session.flush()

    runs, count, charge, duration = await db_session.get_usage_history(org.id, limit=50)

    assert runs == []
    assert count == 0
    # SUM over no rows is NULL in SQL; coalesced so the response carries a
    # number rather than a null the response model would reject.
    assert charge == 0
    assert duration == 0
