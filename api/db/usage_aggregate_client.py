"""Aggregate reads over workflow_runs: one summary, one time series.

Everything the dashboard needs to stop inventing numbers, computed in SQL.

Two rules this module exists to enforce:

**The same filters as the listing.** Both endpoints take the same
start_date/end_date/filters triple as `/usage/runs` and route it through the
same `USAGE_ALLOWED_FILTERS` allowlist and `apply_workflow_run_filters`. A
summary that answered a slightly different question from the table underneath
it would be worse than no summary: the numbers would disagree and neither
would be wrong-looking.

**One query, no Python loops over rows.** The figures these replace were
accumulated row by row over a page, which is how "total talk time" came to mean
"talk time of the page you are looking at". Aggregating in SQL is not an
optimisation here, it is the correctness fix.

The `previous` block on the summary is what kills the fabricated deltas on the
dashboard: the same figures over the immediately preceding window of equal
length, so "+12% vs last month" can be computed instead of made up. It is
returned by the SAME query, labelled by window, rather than by asking twice —
two round trips could straddle a write and disagree with each other.
"""

from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import Date, Float, case, cast, func, literal, select
from sqlalchemy.dialects.postgresql import JSONB

from api.db.base_client import BaseDBClient
from api.db.filters import apply_workflow_run_filters
from api.db.models import (
    OrganizationConfigurationModel,
    WorkflowModel,
    WorkflowRunModel,
)
from api.enums import (
    WORKFLOW_RUN_MODES_BY_CHANNEL,
    OrganizationConfigurationKey,
    TelephonyCallStatus,
    WorkflowRunChannel,
)
from api.services.workflow.disposition_codes import TRANSFER_DISPOSITION_CODES

# A run counts as unanswered only for these, which are exactly the statuses the
# telephony status processor treats as "terminal, never connected"
# (TERMINAL_NOT_CONNECTED_STATUSES). Anything else that reached a disposition
# reached a person or a machine.
NOT_CONNECTED_DISPOSITIONS: tuple[str, ...] = (
    TelephonyCallStatus.FAILED.value,
    TelephonyCallStatus.BUSY.value,
    TelephonyCallStatus.NO_ANSWER.value,
    TelephonyCallStatus.CANCELED.value,
    TelephonyCallStatus.ERROR.value,
)

VOICEMAIL_DISPOSITION = "voicemail_detected"
QUALIFIED_DISPOSITION = "user_qualified"

# A text chat cannot go unanswered, so including it would drag the answer rate
# down by a quantity that has no meaning.
CHAT_MODES: tuple[str, ...] = WORKFLOW_RUN_MODES_BY_CHANNEL[
    WorkflowRunChannel.CHAT.value
]

# postgres date_trunc units, allowlisted rather than interpolated: the value
# reaches SQL as a literal.
SERIES_BUCKETS: dict[str, str] = {
    "hour": "hour",
    "day": "day",
    "week": "week",
    "month": "month",
}

# A series longer than this is not a chart, it is a denial of service on the
# browser. Callers get the cap rather than an error so a wide date range
# degrades to coarse buckets instead of failing.
MAX_SERIES_BUCKETS = 400


def _disposition() -> Any:
    """gathered_context.mapped_call_disposition as text.

    cast-to-JSONB then ``->>`` rather than subscripting, which is the idiom in
    api/db/filters.py -- its comment notes subscripting needs PostgreSQL 14+.
    """
    return cast(WorkflowRunModel.gathered_context, JSONB).op("->>")(
        "mapped_call_disposition"
    )


class UsageAggregateClient(BaseDBClient):
    async def _organization_timezone(self, session, organization_id: int) -> str:
        """The org's configured timezone, or UTC.

        Bucketing a series in UTC when the operator reads their dashboard in
        Asia/Dubai puts calls in the wrong day, which is most visible at the
        edges of a report -- the figure for "today" is wrong all morning.
        """
        result = await session.execute(
            select(OrganizationConfigurationModel).where(
                OrganizationConfigurationModel.organization_id == organization_id,
                OrganizationConfigurationModel.key.in_(
                    [
                        OrganizationConfigurationKey.ORGANIZATION_PREFERENCES.value,
                        # Legacy fallback, same precedence the daily breakdown uses.
                        OrganizationConfigurationKey.MODEL_CONFIGURATION_PREFERENCES.value,
                    ]
                ),
            )
        )
        by_key = {row.key: row for row in result.scalars().all()}
        pref = by_key.get(
            OrganizationConfigurationKey.ORGANIZATION_PREFERENCES.value
        ) or by_key.get(
            OrganizationConfigurationKey.MODEL_CONFIGURATION_PREFERENCES.value
        )
        timezone = (pref.value or {}).get("timezone") if pref else None
        timezone = timezone or "UTC"
        try:
            ZoneInfo(timezone)
        except Exception:
            # A stored timezone that no longer resolves must not fail the whole
            # report; UTC is wrong by an offset, an exception is wrong entirely.
            return "UTC"
        return timezone

    def _scoped_query(self, organization_id: int, filters: Optional[list[dict]]):
        """Org-scoped runs with the listing's own allowlisted filters applied."""
        from api.db.organization_usage_client import USAGE_ALLOWED_FILTERS

        query = select(WorkflowRunModel).join(
            WorkflowModel, WorkflowRunModel.workflow_id == WorkflowModel.id
        )
        query = query.where(WorkflowModel.organization_id == organization_id)

        sanitized = [
            f for f in (filters or []) if f.get("attribute") in USAGE_ALLOWED_FILTERS
        ]
        return apply_workflow_run_filters(query, sanitized)

    async def get_usage_summary(
        self,
        organization_id: int,
        start_date: datetime,
        end_date: datetime,
        filters: Optional[list[dict]] = None,
    ) -> dict:
        """Headline figures for the window, plus the same over the one before it.

        Both windows come back from ONE query, labelled by window: asking twice
        could straddle a write and return two figures that do not reconcile.
        """
        span = end_date - start_date
        previous_start = start_date - span

        window = case(
            (WorkflowRunModel.created_at >= start_date, literal("current")),
            else_=literal("previous"),
        ).label("window")

        base = self._scoped_query(organization_id, filters).where(
            WorkflowRunModel.created_at >= previous_start,
            WorkflowRunModel.created_at <= end_date,
        )
        source = base.add_columns(window).subquery()

        # Re-express the predicates against the subquery's columns.
        s_disposition = cast(source.c.gathered_context, JSONB).op("->>")(
            "mapped_call_disposition"
        )
        s_is_chat = source.c.mode.in_(CHAT_MODES)
        s_unanswered = s_disposition.in_(NOT_CONNECTED_DISPOSITIONS) & ~s_is_chat
        s_duration = cast(
            cast(source.c.usage_info, JSONB).op("->>")("call_duration_seconds"), Float
        )
        s_charge = cast(cast(source.c.cost_info, JSONB).op("->>")("charge_usd"), Float)

        rows = await self._session_execute(
            select(
                source.c.window,
                func.count().label("total_runs"),
                func.count().filter(s_unanswered).label("unanswered_runs"),
                func.count().filter(~s_is_chat).label("call_runs"),
                func.count()
                .filter(s_disposition == VOICEMAIL_DISPOSITION)
                .label("voicemail_runs"),
                func.count()
                .filter(s_disposition == QUALIFIED_DISPOSITION)
                .label("qualified_runs"),
                func.count()
                .filter(s_disposition.in_(TRANSFER_DISPOSITION_CODES))
                .label("transferred_runs"),
                func.coalesce(func.sum(s_duration), 0.0).label("total_duration"),
                func.avg(s_duration).label("avg_duration"),
                func.percentile_cont(0.5)
                .within_group(s_duration.asc())
                .label("p50_duration"),
                func.percentile_cont(0.95)
                .within_group(s_duration.asc())
                .label("p95_duration"),
                func.sum(s_charge).label("total_charge_usd"),
                func.count(func.distinct(source.c.workflow_id)).label(
                    "distinct_agents"
                ),
                # Per-code breakdown of what did not connect is returned
                # separately below; counting them here would need one column per
                # code and would not extend when a provider adds one.
            )
            .select_from(source)
            .group_by(source.c.window)
        )

        by_window = {row.window: row for row in rows}
        unanswered_by_code = await self._unanswered_by_code(
            organization_id, start_date, end_date, filters
        )

        return {
            **self._summary_row(by_window.get("current"), unanswered_by_code),
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
            "previous": {
                **self._summary_row(by_window.get("previous"), {}),
                "period_start": previous_start.isoformat(),
                "period_end": start_date.isoformat(),
            },
        }

    async def _unanswered_by_code(
        self,
        organization_id: int,
        start_date: datetime,
        end_date: datetime,
        filters: Optional[list[dict]],
    ) -> dict[str, int]:
        """Which not-connected reasons, and how many of each.

        A single "unanswered" count cannot be acted on. Busy and no-answer mean
        retry; failed and error mean look at the configuration.
        """
        disposition = _disposition()
        base = self._scoped_query(organization_id, filters).where(
            WorkflowRunModel.created_at >= start_date,
            WorkflowRunModel.created_at <= end_date,
            disposition.in_(NOT_CONNECTED_DISPOSITIONS),
            WorkflowRunModel.mode.notin_(CHAT_MODES),
        )
        source = base.add_columns(disposition.label("code")).subquery()
        rows = await self._session_execute(
            select(source.c.code, func.count().label("n"))
            .select_from(source)
            .group_by(source.c.code)
        )
        return {row.code: int(row.n) for row in rows if row.code}

    @staticmethod
    def _summary_row(row: Any, unanswered_by_code: dict[str, int]) -> dict:
        """Shape one window's aggregate row, with absences left absent."""
        if row is None:
            return {
                "total_runs": 0,
                "call_runs": 0,
                "answered_runs": 0,
                "unanswered_runs": 0,
                "unanswered_by_code": unanswered_by_code,
                "voicemail_runs": 0,
                "qualified_runs": 0,
                "transferred_runs": 0,
                "answer_rate_pct": None,
                "total_duration_seconds": 0,
                "avg_duration_seconds": None,
                "p50_duration_seconds": None,
                "p95_duration_seconds": None,
                "total_charge_usd": None,
                "distinct_agents": 0,
            }

        call_runs = int(row.call_runs or 0)
        unanswered = int(row.unanswered_runs or 0)
        answered = call_runs - unanswered
        return {
            "total_runs": int(row.total_runs or 0),
            "call_runs": call_runs,
            "answered_runs": answered,
            "unanswered_runs": unanswered,
            "unanswered_by_code": unanswered_by_code,
            "voicemail_runs": int(row.voicemail_runs or 0),
            "qualified_runs": int(row.qualified_runs or 0),
            "transferred_runs": int(row.transferred_runs or 0),
            # None, not 0, when there were no calls to answer: a 0% answer rate
            # is a claim that calls were placed and none connected.
            "answer_rate_pct": (
                round(answered / call_runs * 100, 2) if call_runs else None
            ),
            "total_duration_seconds": int(round(float(row.total_duration or 0.0))),
            "avg_duration_seconds": _optional_round(row.avg_duration),
            "p50_duration_seconds": _optional_round(row.p50_duration),
            "p95_duration_seconds": _optional_round(row.p95_duration),
            # Stays None when nothing was priced. Coalescing to 0.0 here would
            # report the window as having cost nothing.
            "total_charge_usd": (
                round(float(row.total_charge_usd), 6)
                if row.total_charge_usd is not None
                else None
            ),
            "distinct_agents": int(row.distinct_agents or 0),
        }

    async def get_usage_series(
        self,
        organization_id: int,
        start_date: datetime,
        end_date: datetime,
        bucket: str = "day",
        filters: Optional[list[dict]] = None,
    ) -> dict:
        """Calls, talk time, spend and answer rate per time bucket."""
        unit = SERIES_BUCKETS.get(bucket, "day")

        async with self.async_session() as session:
            timezone = await self._organization_timezone(session, organization_id)

        base = self._scoped_query(organization_id, filters).where(
            WorkflowRunModel.created_at >= start_date,
            WorkflowRunModel.created_at <= end_date,
        )
        # Bucket in the ORG's timezone, not UTC, or calls land in the wrong day.
        local_created = func.timezone(timezone, WorkflowRunModel.created_at)
        bucket_expr = (
            cast(local_created, Date)
            if unit == "day"
            else func.date_trunc(unit, local_created)
        )
        disposition = _disposition()
        source = base.add_columns(
            bucket_expr.label("bucket"),
            disposition.label("code"),
        ).subquery()

        s_duration = cast(
            cast(source.c.usage_info, JSONB).op("->>")("call_duration_seconds"), Float
        )
        s_charge = cast(cast(source.c.cost_info, JSONB).op("->>")("charge_usd"), Float)
        s_is_chat = source.c.mode.in_(CHAT_MODES)
        s_unanswered = source.c.code.in_(NOT_CONNECTED_DISPOSITIONS) & ~s_is_chat

        rows = await self._session_execute(
            select(
                source.c.bucket,
                func.count().label("calls"),
                func.count().filter(~s_is_chat).label("call_runs"),
                func.count().filter(s_unanswered).label("unanswered"),
                func.coalesce(func.sum(s_duration), 0.0).label("duration"),
                func.sum(s_charge).label("charge"),
            )
            .select_from(source)
            .group_by(source.c.bucket)
            .order_by(source.c.bucket)
            .limit(MAX_SERIES_BUCKETS)
        )

        points = []
        for row in rows:
            call_runs = int(row.call_runs or 0)
            answered = call_runs - int(row.unanswered or 0)
            points.append(
                {
                    "bucket": row.bucket.isoformat() if row.bucket else None,
                    "calls": int(row.calls or 0),
                    "duration_seconds": int(round(float(row.duration or 0.0))),
                    "charge_usd": (
                        round(float(row.charge), 6) if row.charge is not None else None
                    ),
                    "answer_rate_pct": (
                        round(answered / call_runs * 100, 2) if call_runs else None
                    ),
                }
            )

        return {
            "bucket": unit,
            "timezone": timezone,
            "truncated": len(points) >= MAX_SERIES_BUCKETS,
            "points": points,
        }

    async def _session_execute(self, statement):
        async with self.async_session() as session:
            result = await session.execute(statement)
            return result.all()


def _optional_round(value: Any) -> Optional[float]:
    """Round a nullable aggregate, keeping None as None.

    AVG and percentile_cont over rows that all lack a duration return NULL, and
    that has to stay NULL: 0 seconds is a measurement, absent is not.
    """
    if value is None:
        return None
    return round(float(value), 2)
