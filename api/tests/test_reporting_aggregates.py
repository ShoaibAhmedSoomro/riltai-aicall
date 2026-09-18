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
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.db.models import (
    OrganizationModel,
    UserModel,
    WorkflowModel,
    WorkflowRunModel,
)
from api.enums import WorkflowRunMode, WorkflowRunState
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


# ── /usage/summary and /usage/series ────────────────────────────────────────
#
# These exist so the dashboard can stop inventing figures, which makes a wrong
# figure here worse than no figure: it looks measured. Three things are easy to
# get quietly wrong and are pinned below.
#
#   1. The answer rate's DENOMINATOR. A text chat cannot go unanswered, so
#      including chats drags the rate down by a quantity with no meaning.
#   2. The `previous` window. If it does not line up exactly with the requested
#      window's length, every "vs last period" delta on the dashboard is wrong
#      by however much the windows differ.
#   3. Absence vs zero. No calls means answer_rate_pct is None, not 0% -- and
#      nothing priced means total_charge_usd is None, not $0.00.


async def _org_with_dispositioned_runs(async_session, rows):
    """rows: (created_at, disposition, mode, duration, charge)."""
    suffix = next(_suffix)
    org = OrganizationModel(provider_id=f"sum-org-{suffix}")
    async_session.add(org)
    await async_session.flush()

    user = UserModel(provider_id=f"sum-user-{suffix}", selected_organization_id=org.id)
    async_session.add(user)
    await async_session.flush()

    workflow = WorkflowModel(name="sum", organization_id=org.id, user_id=user.id)
    async_session.add(workflow)
    await async_session.flush()

    for created_at, disposition, mode, duration, charge in rows:
        async_session.add(
            WorkflowRunModel(
                workflow_id=workflow.id,
                name="r",
                mode=mode,
                is_completed=True,
                created_at=created_at,
                usage_info=(
                    {} if duration is None else {"call_duration_seconds": duration}
                ),
                cost_info=({} if charge is None else {"charge_usd": charge}),
                gathered_context=(
                    {}
                    if disposition is None
                    else {"mapped_call_disposition": disposition}
                ),
            )
        )
    await async_session.flush()
    return org


NOW = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
WINDOW_START = NOW - timedelta(days=7)
PREV_START = WINDOW_START - timedelta(days=7)


@pytest.mark.asyncio
async def test_the_answer_rate_excludes_text_chats(db_session, async_session):
    """THE definition that decides whether the headline number means anything.

    Three calls, one of them no-answer, plus two chats. The rate is 2/3, not
    2/5: a chat has no notion of going unanswered, so counting it in the
    denominator would understate the rate for any org that uses chat at all.
    """
    inside = WINDOW_START + timedelta(days=1)
    org = await _org_with_dispositioned_runs(
        async_session,
        [
            (inside, "completed", "twilio", 60, None),
            (inside, "user_hangup", "twilio", 30, None),
            (inside, "no-answer", "twilio", 0, None),
            (inside, "user_hangup", WorkflowRunMode.TEXTCHAT.value, 10, None),
            # NOT "chat": the historical mode's value is uppercase "CHAT".
            (inside, "user_hangup", WorkflowRunMode.CHAT.value, 10, None),
        ],
    )

    summary = await db_session.get_usage_summary(org.id, WINDOW_START, NOW)

    assert summary["total_runs"] == 5
    assert summary["call_runs"] == 3
    assert summary["answered_runs"] == 2
    assert summary["unanswered_runs"] == 1
    assert summary["answer_rate_pct"] == pytest.approx(66.67, abs=0.01)


@pytest.mark.asyncio
async def test_unanswered_is_split_by_reason(db_session, async_session):
    inside = WINDOW_START + timedelta(days=1)
    org = await _org_with_dispositioned_runs(
        async_session,
        [
            (inside, "busy", "twilio", 0, None),
            (inside, "busy", "twilio", 0, None),
            (inside, "no-answer", "twilio", 0, None),
            (inside, "failed", "twilio", 0, None),
            (inside, "completed", "twilio", 60, None),
        ],
    )

    summary = await db_session.get_usage_summary(org.id, WINDOW_START, NOW)

    assert summary["unanswered_runs"] == 4
    assert summary["unanswered_by_code"] == {"busy": 2, "no-answer": 1, "failed": 1}


@pytest.mark.asyncio
async def test_the_previous_window_is_the_same_length_and_immediately_before(
    db_session, async_session
):
    """The delta on every dashboard stat card depends on this alignment.

    Two runs in the requested week, one in the week before it, and one older
    than both. The previous window must pick up exactly the middle one.
    """
    org = await _org_with_dispositioned_runs(
        async_session,
        [
            (WINDOW_START + timedelta(days=1), "completed", "twilio", 60, None),
            (WINDOW_START + timedelta(days=2), "completed", "twilio", 60, None),
            (PREV_START + timedelta(days=1), "completed", "twilio", 30, None),
            (PREV_START - timedelta(days=3), "completed", "twilio", 999, None),
        ],
    )

    summary = await db_session.get_usage_summary(org.id, WINDOW_START, NOW)

    assert summary["total_runs"] == 2
    assert summary["total_duration_seconds"] == 120
    assert summary["previous"]["total_runs"] == 1
    assert summary["previous"]["total_duration_seconds"] == 30
    # The run older than the previous window is in neither.
    assert summary["previous"]["total_duration_seconds"] != 1029


@pytest.mark.asyncio
async def test_no_calls_reports_no_answer_rate_rather_than_zero_percent(
    db_session, async_session
):
    """0% says calls were placed and none connected. None says none were placed."""
    org = await _org_with_dispositioned_runs(
        async_session,
        [
            (
                WINDOW_START + timedelta(days=1),
                "user_hangup",
                WorkflowRunMode.TEXTCHAT.value,
                10,
                None,
            )
        ],
    )

    summary = await db_session.get_usage_summary(org.id, WINDOW_START, NOW)

    assert summary["total_runs"] == 1
    assert summary["call_runs"] == 0
    assert summary["answer_rate_pct"] is None


@pytest.mark.asyncio
async def test_nothing_priced_reports_no_spend_rather_than_zero(
    db_session, async_session
):
    org = await _org_with_dispositioned_runs(
        async_session,
        [(WINDOW_START + timedelta(days=1), "completed", "twilio", 60, None)],
    )
    summary = await db_session.get_usage_summary(org.id, WINDOW_START, NOW)
    assert summary["total_charge_usd"] is None

    org2 = await _org_with_dispositioned_runs(
        async_session,
        [(WINDOW_START + timedelta(days=1), "completed", "twilio", 60, 0.25)],
    )
    summary2 = await db_session.get_usage_summary(org2.id, WINDOW_START, NOW)
    assert summary2["total_charge_usd"] == pytest.approx(0.25)


@pytest.mark.asyncio
async def test_duration_percentiles_come_from_sql(db_session, async_session):
    inside = WINDOW_START + timedelta(days=1)
    org = await _org_with_dispositioned_runs(
        async_session,
        [(inside, "completed", "twilio", d, None) for d in (10, 20, 30, 40, 100)],
    )

    summary = await db_session.get_usage_summary(org.id, WINDOW_START, NOW)

    assert summary["total_duration_seconds"] == 200
    assert summary["avg_duration_seconds"] == pytest.approx(40.0)
    assert summary["p50_duration_seconds"] == pytest.approx(30.0)
    # p95 sits between the top two, which is the point of having it next to the
    # average: one long call moves the mean and not the median.
    assert summary["p95_duration_seconds"] > summary["p50_duration_seconds"]


@pytest.mark.asyncio
async def test_transfers_and_voicemail_and_qualified_are_counted(
    db_session, async_session
):
    inside = WINDOW_START + timedelta(days=1)
    org = await _org_with_dispositioned_runs(
        async_session,
        [
            (inside, "call_transferred", "twilio", 60, None),
            (inside, "transfer_call", "twilio", 60, None),
            (inside, "voicemail_detected", "twilio", 20, None),
            (inside, "user_qualified", "twilio", 90, None),
            (inside, "XFER", "twilio", 60, None),
        ],
    )

    summary = await db_session.get_usage_summary(org.id, WINDOW_START, NOW)

    # XFER is not a transfer -- nothing in the platform writes it, and a custom
    # code means whatever the organization decided.
    assert summary["transferred_runs"] == 2
    assert summary["voicemail_runs"] == 1
    assert summary["qualified_runs"] == 1


@pytest.mark.asyncio
async def test_the_summary_is_scoped_to_one_organization(db_session, async_session):
    inside = WINDOW_START + timedelta(days=1)
    mine = await _org_with_dispositioned_runs(
        async_session, [(inside, "completed", "twilio", 60, 1.0)]
    )
    await _org_with_dispositioned_runs(
        async_session, [(inside, "completed", "twilio", 600, 99.0)]
    )

    summary = await db_session.get_usage_summary(mine.id, WINDOW_START, NOW)

    assert summary["total_runs"] == 1
    assert summary["total_duration_seconds"] == 60
    assert summary["total_charge_usd"] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_distinct_agents_counts_agents_not_runs(db_session, async_session):
    inside = WINDOW_START + timedelta(days=1)
    org = await _org_with_dispositioned_runs(
        async_session,
        [(inside, "completed", "twilio", 60, None) for _ in range(4)],
    )
    summary = await db_session.get_usage_summary(org.id, WINDOW_START, NOW)
    # All four runs belong to the single workflow the helper creates.
    assert summary["total_runs"] == 4
    assert summary["distinct_agents"] == 1


# ── the series ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_series_buckets_by_day_and_omits_empty_days(
    db_session, async_session
):
    org = await _org_with_dispositioned_runs(
        async_session,
        [
            (WINDOW_START + timedelta(days=1), "completed", "twilio", 60, 0.10),
            (
                WINDOW_START + timedelta(days=1, hours=3),
                "completed",
                "twilio",
                30,
                0.05,
            ),
            (WINDOW_START + timedelta(days=3), "no-answer", "twilio", 0, None),
        ],
    )

    series = await db_session.get_usage_series(org.id, WINDOW_START, NOW, bucket="day")

    assert series["bucket"] == "day"
    assert series["truncated"] is False
    # Two days with data, not seven: a gap is absence of calls, and inventing a
    # zero-valued point for it is the chart's job to render, not the API's to
    # assert happened.
    assert len(series["points"]) == 2
    first, second = series["points"]
    assert first["calls"] == 2
    assert first["duration_seconds"] == 90
    assert first["charge_usd"] == pytest.approx(0.15)
    assert first["answer_rate_pct"] == pytest.approx(100.0)
    assert second["calls"] == 1
    assert second["answer_rate_pct"] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_the_series_accepts_every_bucket_and_rejects_nothing_silently(
    db_session, async_session
):
    org = await _org_with_dispositioned_runs(
        async_session,
        [(WINDOW_START + timedelta(days=1), "completed", "twilio", 60, None)],
    )
    for bucket in ("hour", "day", "week", "month"):
        series = await db_session.get_usage_series(
            org.id, WINDOW_START, NOW, bucket=bucket
        )
        assert series["bucket"] == bucket
        assert len(series["points"]) == 1

    # An unknown unit falls back to day rather than reaching SQL: the value is
    # interpolated into date_trunc, so it is allowlisted, not validated.
    series = await db_session.get_usage_series(
        org.id, WINDOW_START, NOW, bucket="'; drop table workflow_runs; --"
    )
    assert series["bucket"] == "day"


@pytest.mark.asyncio
async def test_the_series_reports_the_timezone_it_bucketed_in(
    db_session, async_session
):
    org = await _org_with_dispositioned_runs(
        async_session,
        [(WINDOW_START + timedelta(days=1), "completed", "twilio", 60, None)],
    )
    series = await db_session.get_usage_series(org.id, WINDOW_START, NOW)
    # UTC with no preference configured. Returned so a chart can label its axis
    # without guessing, and so a day boundary can be explained.
    assert series["timezone"] == "UTC"


@pytest.mark.asyncio
async def test_a_chat_with_a_not_connected_disposition_is_not_unanswered(
    db_session, async_session
):
    """The guard that keeps `answered` from going negative.

    answered is call_runs minus unanswered. If a chat could be counted as
    unanswered while being excluded from call_runs, the subtraction underflows
    and the dashboard shows a negative answered count.
    """
    inside = WINDOW_START + timedelta(days=1)
    org = await _org_with_dispositioned_runs(
        async_session,
        [
            (inside, "completed", "twilio", 60, None),
            # A chat should never carry a telephony status, but nothing in the
            # schema stops one, and a stray value must not corrupt the rate.
            (inside, "no-answer", WorkflowRunMode.TEXTCHAT.value, 5, None),
            (inside, "busy", WorkflowRunMode.CHAT.value, 5, None),
        ],
    )

    summary = await db_session.get_usage_summary(org.id, WINDOW_START, NOW)

    assert summary["call_runs"] == 1
    assert summary["unanswered_runs"] == 0
    assert summary["answered_runs"] == 1
    assert summary["answer_rate_pct"] == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_the_series_is_scoped_to_one_organization(db_session, async_session):
    """Tenant isolation, asserted rather than assumed.

    The aggregate builds its own subquery, so the org predicate has to be on
    THAT query -- it is not inherited from anywhere. Without this test, an
    aggregate over every organization's runs passes every other assertion here.
    """
    inside = WINDOW_START + timedelta(days=1)
    mine = await _org_with_dispositioned_runs(
        async_session, [(inside, "completed", "twilio", 60, 1.0)]
    )
    await _org_with_dispositioned_runs(
        async_session, [(inside, "completed", "twilio", 600, 99.0)]
    )

    series = await db_session.get_usage_series(mine.id, WINDOW_START, NOW)

    assert len(series["points"]) == 1
    assert series["points"][0]["calls"] == 1
    assert series["points"][0]["duration_seconds"] == 60
    assert series["points"][0]["charge_usd"] == pytest.approx(1.0)


# ── the current-period meter ────────────────────────────────────────────────
#
# get_current_usage used to read organization_usage_cycles.used_dograh_tokens
# and .total_duration_seconds. NOTHING has ever written either column -- there
# is no accrual path in the codebase -- so both sat at 0 forever, and two
# unbadged surfaces presented that zero as a measurement: the Talk time tile
# and the header's period meter.


@pytest.mark.asyncio
async def test_the_period_meter_measures_instead_of_reading_a_dead_column(
    db_session, async_session
):
    """The figure has to come from the runs, not from a column nothing fills.

    A run placed inside the current period must move the number. Before this,
    it could not: the value was read straight off the cycle row.
    """
    org = await _org_with_dispositioned_runs(
        async_session,
        [(datetime.now(UTC), "completed", "twilio", 120, 0.20)],
    )

    usage = await db_session.get_current_usage(org.id)

    assert usage["total_duration_seconds"] == 120
    assert usage["used_amount_usd"] == pytest.approx(0.20)
    assert usage["currency"] == "USD"
    # Cost in cents, the unit "rilt tokens" means everywhere else.
    assert usage["used_dograh_tokens"] == pytest.approx(20.0)


@pytest.mark.asyncio
async def test_the_period_meter_omits_money_when_nothing_was_priced(
    db_session, async_session
):
    """No cost source means no money keys, so the meter renders no spend.

    Returning 0.0 would put "$0.00" in the header, which claims the period's
    calls were free rather than unpriced.
    """
    org = await _org_with_dispositioned_runs(
        async_session,
        [(datetime.now(UTC), "completed", "twilio", 60, None)],
    )

    usage = await db_session.get_current_usage(org.id)

    assert usage["total_duration_seconds"] == 60
    assert "used_amount_usd" not in usage
    assert "currency" not in usage


@pytest.mark.asyncio
async def test_the_period_meter_excludes_runs_outside_the_period(
    db_session, async_session
):
    """The period bound has to be applied, or the meter reports all of history."""
    now = datetime.now(UTC)
    org = await _org_with_dispositioned_runs(
        async_session,
        [
            (now, "completed", "twilio", 60, None),
            # Comfortably outside any calendar-month period containing `now`.
            (now - timedelta(days=90), "completed", "twilio", 9999, None),
        ],
    )

    usage = await db_session.get_current_usage(org.id)

    assert usage["total_duration_seconds"] == 60


@pytest.mark.asyncio
async def test_the_period_meter_still_reports_the_period_boundary(
    db_session, async_session
):
    # The cycle row is kept and still creates on first read; only the three
    # never-written usage columns stopped being consulted.
    org = await _org_with_dispositioned_runs(async_session, [])
    usage = await db_session.get_current_usage(org.id)
    assert usage["period_start"] < usage["period_end"]
    assert usage["total_duration_seconds"] == 0


# ── live concurrency ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_running_runs_counts_only_this_org_and_only_running(
    db_session, async_session
):
    """The Redis-independent half of the live tile.

    It has to be scoped AND state-filtered: without the state filter it reports
    every run ever made as in progress.
    """
    suffix = next(_suffix)
    org = OrganizationModel(provider_id=f"live-org-{suffix}")
    other = OrganizationModel(provider_id=f"live-other-{suffix}")
    async_session.add_all([org, other])
    await async_session.flush()

    user = UserModel(provider_id=f"live-user-{suffix}", selected_organization_id=org.id)
    async_session.add(user)
    await async_session.flush()

    mine = WorkflowModel(name="live", organization_id=org.id, user_id=user.id)
    theirs = WorkflowModel(name="live2", organization_id=other.id, user_id=user.id)
    async_session.add_all([mine, theirs])
    await async_session.flush()

    for workflow, state in [
        (mine, WorkflowRunState.RUNNING.value),
        (mine, WorkflowRunState.RUNNING.value),
        (mine, WorkflowRunState.COMPLETED.value),
        (mine, WorkflowRunState.INITIALIZED.value),
        (theirs, WorkflowRunState.RUNNING.value),
    ]:
        async_session.add(
            WorkflowRunModel(
                workflow_id=workflow.id, name="r", mode="twilio", state=state
            )
        )
    await async_session.flush()

    assert await db_session.count_running_runs(org.id) == 2
    assert await db_session.count_running_runs(other.id) == 1


@pytest.mark.asyncio
async def test_a_redis_failure_reports_unknown_rather_than_idle(monkeypatch):
    """THE rule for this tile.

    rate_limiter.get_concurrent_count returns 0 when Redis is unreachable,
    which is right for a limiter -- it must not block calls -- and wrong for a
    dashboard, where 0 says "nothing is running". The reader used by the tile
    has to be able to say "I do not know".
    """
    from api.services.call_concurrency.rate_limiter import RateLimiter

    class _FailingCommands:
        """Connects, then fails on the command -- a timeout or a MISCONF."""

        async def zremrangebyscore(self, *a, **k):
            raise RuntimeError("READONLY You can not write against a replica")

        async def zcard(self, *a, **k):
            raise RuntimeError("unreachable")

    limiter = RateLimiter()

    async def _connects_but_fails():
        return _FailingCommands()

    monkeypatch.setattr(limiter, "_get_redis", _connects_but_fails)
    # The forgiving reader answers 0 here, because a limiter that cannot read
    # the count must not stop a call from starting.
    assert await limiter.get_concurrent_count(1) == 0
    # The honest reader says it does not know.
    assert await limiter.get_concurrent_count_or_none(1) is None

    async def _cannot_connect():
        raise ConnectionError("redis is down")

    monkeypatch.setattr(limiter, "_get_redis", _cannot_connect)
    # A CONNECTION failure is not caught by the forgiving reader at all -- its
    # try block starts after _get_redis(), so this propagates. Worth pinning:
    # it means the tile cannot simply call that method and hope.
    with pytest.raises(ConnectionError):
        await limiter.get_concurrent_count(1)
    # The honest reader wraps the connection too, so the tile degrades to
    # "unknown" instead of failing the request.
    assert await limiter.get_concurrent_count_or_none(1) is None


# ── queue summary and alerts ────────────────────────────────────────────────


async def _campaign_with_queued(async_session, rows):
    """rows: (state, retry_count, scheduled) tuples."""
    from api.db.models import CampaignModel, QueuedRunModel

    suffix = next(_suffix)
    org = OrganizationModel(provider_id=f"q-org-{suffix}")
    async_session.add(org)
    await async_session.flush()
    user = UserModel(provider_id=f"q-user-{suffix}", selected_organization_id=org.id)
    async_session.add(user)
    await async_session.flush()
    workflow = WorkflowModel(name="q", organization_id=org.id, user_id=user.id)
    async_session.add(workflow)
    await async_session.flush()
    campaign = CampaignModel(
        name="c",
        organization_id=org.id,
        workflow_id=workflow.id,
        created_by=user.id,
        source_id="test",
    )
    async_session.add(campaign)
    await async_session.flush()

    for state, retry_count, scheduled in rows:
        async_session.add(
            QueuedRunModel(
                campaign_id=campaign.id,
                source_uuid=str(next(_suffix)),
                state=state,
                retry_count=retry_count,
                scheduled_for=datetime.now(UTC) if scheduled else None,
                context_variables={},
            )
        )
    await async_session.flush()
    return org, campaign


@pytest.mark.asyncio
async def test_queue_stats_break_down_by_state(db_session, async_session):
    _, campaign = await _campaign_with_queued(
        async_session,
        [
            ("queued", 0, False),
            ("queued", 2, False),
            ("queued", 0, True),
            ("processing", 0, False),
            ("processed", 0, False),
            ("processed", 0, False),
            ("failed", 3, False),
        ],
    )

    stats = (await db_session.get_queued_runs_stats_for_campaigns([campaign.id]))[
        campaign.id
    ]

    assert stats["total"] == 7
    assert stats["queued"] == 3
    assert stats["processing"] == 1
    assert stats["processed"] == 2
    assert stats["failed"] == 1
    # retrying and scheduled are views OVER queued, not states beside it, so
    # the segments deliberately do not sum to total.
    assert stats["retrying"] == 1
    assert stats["scheduled"] == 1
    assert stats["queued"] + stats["retrying"] + stats["scheduled"] != stats["total"]


@pytest.mark.asyncio
async def test_the_two_existing_callers_keep_their_keys(db_session, async_session):
    """total/executed are read by two routes already; widening must not move them."""
    _, campaign = await _campaign_with_queued(
        async_session, [("processed", 0, False), ("queued", 0, False)]
    )
    stats = (await db_session.get_queued_runs_stats_for_campaigns([campaign.id]))[
        campaign.id
    ]
    assert stats["total"] == 2
    assert stats["executed"] == 1
    assert stats["executed"] == stats["processed"]


@pytest.mark.asyncio
async def test_a_campaign_with_no_queued_runs_reports_zeros(db_session, async_session):
    _, campaign = await _campaign_with_queued(async_session, [])
    stats = (await db_session.get_queued_runs_stats_for_campaigns([campaign.id]))[
        campaign.id
    ]
    assert stats["total"] == 0
    assert stats["failed"] == 0


@pytest.mark.asyncio
async def test_a_tripped_breaker_is_found_from_the_campaign_log(
    db_session, async_session
):
    """The trip lives in campaigns.logs, NOT in orchestrator_metadata.

    orchestrator_metadata.circuit_breaker is the breaker's CONFIG. Looking
    there for a trip finds the threshold and reports every configured campaign
    as tripped.
    """
    from api.db.models import CampaignModel

    suffix = next(_suffix)
    org = OrganizationModel(provider_id=f"cb-org-{suffix}")
    async_session.add(org)
    await async_session.flush()
    user = UserModel(provider_id=f"cb-user-{suffix}", selected_organization_id=org.id)
    async_session.add(user)
    await async_session.flush()
    workflow = WorkflowModel(name="cb", organization_id=org.id, user_id=user.id)
    async_session.add(workflow)
    await async_session.flush()

    tripped = CampaignModel(
        name="tripped",
        source_id="test",
        organization_id=org.id,
        workflow_id=workflow.id,
        created_by=user.id,
        state="paused",
        logs=[{"event": "circuit_breaker_tripped", "message": "paused"}],
        # Configured, which is what orchestrator_metadata actually holds.
        orchestrator_metadata={"circuit_breaker": {"threshold": 0.5}},
    )
    # Paused by hand, not by the breaker.
    paused_by_hand = CampaignModel(
        name="manual",
        source_id="test",
        organization_id=org.id,
        workflow_id=workflow.id,
        created_by=user.id,
        state="paused",
        logs=[{"event": "paused", "message": "user paused"}],
        orchestrator_metadata={"circuit_breaker": {"threshold": 0.5}},
    )
    # Tripped once, since resumed -- history, not something to act on.
    resumed = CampaignModel(
        name="resumed",
        source_id="test",
        organization_id=org.id,
        workflow_id=workflow.id,
        created_by=user.id,
        state="running",
        logs=[{"event": "circuit_breaker_tripped", "message": "paused"}],
    )
    async_session.add_all([tripped, paused_by_hand, resumed])
    await async_session.flush()

    # Another tenant, tripped and paused exactly the same way. Leaking this one
    # would put another organization's campaign name on the caller's alerts.
    other_org = OrganizationModel(provider_id=f"cb-org2-{suffix}")
    async_session.add(other_org)
    await async_session.flush()
    other_workflow = WorkflowModel(
        name="cb2", organization_id=other_org.id, user_id=user.id
    )
    async_session.add(other_workflow)
    await async_session.flush()
    async_session.add(
        CampaignModel(
            name="other-tenant",
            source_id="test",
            organization_id=other_org.id,
            workflow_id=other_workflow.id,
            created_by=user.id,
            state="paused",
            logs=[{"event": "circuit_breaker_tripped", "message": "paused"}],
        )
    )
    await async_session.flush()

    found = await db_session.get_circuit_breaker_tripped_campaigns(org.id)

    assert [c["name"] for c in found] == ["tripped"]


@pytest.mark.asyncio
async def test_dead_letter_deliveries_are_counted_per_org(db_session, async_session):
    """Nothing in the product surfaced these before: a dead letter means the
    receiving system never got the event and nothing will resend it."""
    from api.db.models import WebhookDeliveryModel

    suffix = next(_suffix)
    org = OrganizationModel(provider_id=f"dl-org-{suffix}")
    other = OrganizationModel(provider_id=f"dl-other-{suffix}")
    async_session.add_all([org, other])
    await async_session.flush()
    user = UserModel(provider_id=f"dl-user-{suffix}", selected_organization_id=org.id)
    async_session.add(user)
    await async_session.flush()
    workflow = WorkflowModel(name="dl", organization_id=org.id, user_id=user.id)
    async_session.add(workflow)
    await async_session.flush()
    run = WorkflowRunModel(workflow_id=workflow.id, name="r", mode="twilio")
    async_session.add(run)
    await async_session.flush()

    for node, (organization, status) in enumerate(
        [
            (org, "dead_letter"),
            (org, "dead_letter"),
            (org, "succeeded"),
            (org, "pending"),
            (other, "dead_letter"),
        ]
    ):
        async_session.add(
            WebhookDeliveryModel(
                workflow_run_id=run.id,
                organization_id=organization.id,
                endpoint_url="https://example.invalid/hook",
                # Distinct per row: there is a unique constraint on
                # (workflow_run_id, webhook_node_id).
                webhook_node_id=f"node-{node}",
                status=status,
            )
        )
    await async_session.flush()

    assert await db_session.count_dead_letter_deliveries(org.id) == 2
    assert await db_session.count_dead_letter_deliveries(other.id) == 1


# ── call-history filters and the CSV cost column ────────────────────────────
#
# Four attributes were mapped in ATTRIBUTE_FIELD_MAPPING and offered by the UI's
# catalog but missing from USAGE_ALLOWED_FILTERS, so the org-wide page sent them
# and the backend dropped them silently -- the worst failure mode a filter has,
# because the unfiltered list looks like a result.


async def _org_with_filterable_runs(async_session, rows):
    """One org, one workflow, one run per row.

    Each row is (is_completed, recording_url, total_cost_usd, call_tags).
    """
    suffix = next(_suffix)
    org = OrganizationModel(provider_id=f"filt-org-{suffix}")
    async_session.add(org)
    await async_session.flush()
    user = UserModel(provider_id=f"filt-user-{suffix}", selected_organization_id=org.id)
    async_session.add(user)
    await async_session.flush()
    workflow = WorkflowModel(name="filt", organization_id=org.id, user_id=user.id)
    async_session.add(workflow)
    await async_session.flush()

    for is_completed, recording_url, cost, tags in rows:
        async_session.add(
            WorkflowRunModel(
                workflow_id=workflow.id,
                name="r",
                mode=WorkflowRunMode.TWILIO.value,
                is_completed=is_completed,
                recording_url=recording_url,
                usage_info={"call_duration_seconds": 60},
                cost_info={} if cost is None else {"total_cost_usd": cost},
                gathered_context={} if tags is None else {"call_tags": tags},
            )
        )
    await async_session.flush()
    return org


async def _filtered_ids(db_session, org, filters):
    runs, _, _, _ = await db_session.get_usage_history(org.id, filters=filters)
    return {run["id"] for run in runs}


@pytest.mark.asyncio
async def test_the_completion_filter_reaches_the_org_wide_listing(
    db_session, async_session
):
    """`status` was in the mapping and in the UI, but not in the allowlist."""
    org = await _org_with_filterable_runs(
        async_session, [(True, None, None, None), (False, None, None, None)]
    )
    all_ids = await _filtered_ids(db_session, org, None)
    assert len(all_ids) == 2

    completed = await _filtered_ids(
        db_session,
        org,
        [{"attribute": "status", "type": "radio", "value": {"status": "completed"}}],
    )
    in_progress = await _filtered_ids(
        db_session,
        org,
        [{"attribute": "status", "type": "radio", "value": {"status": "in_progress"}}],
    )
    assert len(completed) == 1
    assert len(in_progress) == 1
    assert completed != in_progress


@pytest.mark.asyncio
async def test_the_recording_filter_splits_runs_by_whether_one_exists(
    db_session, async_session
):
    """recording_url is a plain nullable column, so "has one" is NOT NULL."""
    org = await _org_with_filterable_runs(
        async_session,
        [(True, "s3://bucket/a.wav", None, None), (True, None, None, None)],
    )
    with_rec = await _filtered_ids(
        db_session,
        org,
        [{"attribute": "hasRecording", "type": "radio", "value": {"status": "yes"}}],
    )
    without = await _filtered_ids(
        db_session,
        org,
        [{"attribute": "hasRecording", "type": "radio", "value": {"status": "no"}}],
    )
    assert len(with_rec) == 1
    assert len(without) == 1
    assert with_rec.isdisjoint(without)

    # "All" must not narrow anything -- the radio's default.
    everything = await _filtered_ids(
        db_session,
        org,
        [{"attribute": "hasRecording", "type": "radio", "value": {"status": "all"}}],
    )
    assert everything == with_rec | without


@pytest.mark.asyncio
async def test_the_cost_filter_ranges_over_money_despite_its_name(
    db_session, async_session
):
    """`tokenUsage` has always pointed at cost_info.total_cost_usd.

    Nothing wrote that key until runs started being priced, so the filter
    matched nothing and the "Token Usage" label was never contradicted.
    """
    org = await _org_with_filterable_runs(
        async_session,
        [(True, None, 0.05, None), (True, None, 0.50, None), (True, None, None, None)],
    )
    cheap = await _filtered_ids(
        db_session,
        org,
        [
            {
                "attribute": "tokenUsage",
                "type": "numberRange",
                "value": {"min": 0, "max": 0.1},
            }
        ],
    )
    dear = await _filtered_ids(
        db_session,
        org,
        [
            {
                "attribute": "tokenUsage",
                "type": "numberRange",
                "value": {"min": 0.1, "max": 10},
            }
        ],
    )
    assert len(cheap) == 1
    assert len(dear) == 1
    # The unpriced run is in neither: absent is not zero.
    assert len(cheap | dear) == 2


@pytest.mark.asyncio
async def test_the_tags_filter_reaches_the_org_wide_listing(db_session, async_session):
    org = await _org_with_filterable_runs(
        async_session,
        [
            (True, None, None, ["vip"]),
            (True, None, None, ["other"]),
            (True, None, None, None),
        ],
    )
    vip = await _filtered_ids(
        db_session,
        org,
        [{"attribute": "callTags", "type": "tags", "value": {"codes": ["vip"]}}],
    )
    assert len(vip) == 1


def test_the_csv_carries_the_cost_and_leaves_it_blank_when_unpriced():
    """A zero here would read as a free call rather than an unknown one."""
    import csv as _csv

    from api.services.reports.run_report import build_run_report_csv

    def _row(cost_info):
        return SimpleNamespace(
            id=1,
            campaign_id=None,
            workflow_id=2,
            definition_id=None,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            initial_context={},
            gathered_context={},
            usage_info={"call_duration_seconds": 60},
            cost_info=cost_info,
            public_access_token=None,
        )

    rows = list(
        _csv.reader(
            build_run_report_csv([_row({"charge_usd": 0.1}), _row({}), _row(None)])
            .getvalue()
            .splitlines()
        )
    )
    cost = rows[0].index("Cost (USD)")
    assert [r[cost] for r in rows[1:]] == ["0.1", "", ""]
