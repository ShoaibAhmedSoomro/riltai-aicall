from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta
from sqlalchemy import Date, Float, and_, cast, func, select
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.orm import joinedload

from api.db.base_client import BaseDBClient
from api.db.filters import (
    apply_workflow_run_filters,
    get_workflow_run_order_clause,
)
from api.db.models import (
    OrganizationConfigurationModel,
    OrganizationUsageCycleModel,
    WorkflowModel,
    WorkflowRunModel,
)
from api.enums import OrganizationConfigurationKey
from api.utils.recording_artifacts import get_recording_storage_key

# Filters the org-wide usage surfaces accept. Anything else in the request is
# dropped, so a caller can't reach fields the usage page doesn't expose. The
# listing and the CSV export share this so they can't drift apart.
USAGE_ALLOWED_FILTERS = frozenset(
    {
        "duration",
        "dispositionCode",
        "callerNumber",
        "calledNumber",
        "runId",
        "workflowId",
        "campaignId",
        "callDirection",
        "callChannel",
        # All four are mapped in ATTRIBUTE_FIELD_MAPPING and defined in the UI's
        # attribute catalog, but were missing here, so the org-wide page sent
        # them and the backend dropped them without a word.
        "status",
        "callTags",
        "tokenUsage",
        "hasRecording",
    }
)


class OrganizationUsageClient(BaseDBClient):
    """Client for managing organization usage reporting aggregates."""

    async def get_or_create_current_cycle(
        self, organization_id: int, session=None
    ) -> OrganizationUsageCycleModel:
        """Get or create the current usage cycle for an organization.

        Args:
            organization_id: The organization ID
            session: Optional session to use for the operation. If provided,
                    the caller is responsible for committing.
        """
        if session is None:
            async with self.async_session() as session:
                return await self._get_or_create_current_cycle_impl(
                    organization_id, session, commit=True
                )
        else:
            return await self._get_or_create_current_cycle_impl(
                organization_id, session, commit=False
            )

    async def _get_or_create_current_cycle_impl(
        self, organization_id: int, session, commit: bool
    ) -> OrganizationUsageCycleModel:
        """Internal implementation for get_or_create_current_cycle."""
        period_start, period_end = self._calculate_current_period()

        # Try to get existing cycle
        cycle_result = await session.execute(
            select(OrganizationUsageCycleModel).where(
                and_(
                    OrganizationUsageCycleModel.organization_id == organization_id,
                    OrganizationUsageCycleModel.period_start == period_start,
                    OrganizationUsageCycleModel.period_end == period_end,
                )
            )
        )
        cycle = cycle_result.scalar_one_or_none()

        if cycle:
            return cycle

        # Create new cycle if it doesn't exist
        stmt = insert(OrganizationUsageCycleModel).values(
            organization_id=organization_id,
            period_start=period_start,
            period_end=period_end,
            # Deprecated non-null column retained for historical schema compatibility.
            quota_dograh_tokens=0,
        )
        # Handle concurrent inserts gracefully
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["organization_id", "period_start", "period_end"]
        )

        await session.execute(stmt)

        if commit:
            await session.commit()

        # Fetch the created cycle
        cycle_result = await session.execute(
            select(OrganizationUsageCycleModel).where(
                and_(
                    OrganizationUsageCycleModel.organization_id == organization_id,
                    OrganizationUsageCycleModel.period_start == period_start,
                    OrganizationUsageCycleModel.period_end == period_end,
                )
            )
        )
        return cycle_result.scalar_one()

    async def get_current_usage(self, organization_id: int) -> dict:
        """Current reporting-period usage, MEASURED from the period's runs.

        This used to read organization_usage_cycles.used_dograh_tokens and
        .total_duration_seconds. Nothing has ever written either column -- there
        is no accrual path in the codebase -- so both were permanently 0, and
        two unbadged surfaces presented that zero as a measurement: the Talk
        time tile on the overview and PeriodUsageMeter, whose own docstring
        claimed the backend was computing it.

        Fixed by deletion rather than by building an accrual path: the figures
        are aggregated from workflow_runs on read, by the same query that backs
        /usage/summary, bounded to the period. One source for the period meter
        and the usage page means they cannot disagree.

        The cycle ROW is still created and returned -- it is the record of where
        the period boundary falls, and that part was never wrong.
        """
        async with self.async_session() as session:
            # Creates the cycle row if this is the first read of the period.
            cycle = await self._get_or_create_current_cycle_impl(
                organization_id, session, commit=True
            )
            period_start = cycle.period_start
            period_end = cycle.period_end

        summary = await self.get_usage_summary(
            organization_id, start_date=period_start, end_date=period_end
        )

        total_charge_usd = summary["total_charge_usd"]
        result = {
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            # Cost in cents, the unit "rilt tokens" means everywhere else that
            # computes it. 0.0 when nothing in the period was priced -- which is
            # a real total of a priced-at-nothing period, not a placeholder.
            "used_dograh_tokens": round((total_charge_usd or 0.0) * 100, 2),
            "total_duration_seconds": summary["total_duration_seconds"],
        }

        # Money only when there IS money. None would break the response model's
        # float contract downstream; omitting the keys is what the UI already
        # treats as "no cost source", and it renders nothing rather than $0.00.
        if total_charge_usd is not None:
            result["used_amount_usd"] = total_charge_usd
            result["currency"] = "USD"

        return result

    async def get_usage_history(
        self,
        organization_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
        filters: Optional[list[dict]] = None,
        sort_by: Optional[str] = None,
        sort_order: str = "desc",
    ) -> tuple[list[dict], int, float, int]:
        """Get paginated workflow runs with usage for an organization.

        Returns (runs, total_count, total_charge_usd, total_duration_seconds),
        where the two totals span the whole filtered set rather than the page
        being returned.

        Args:
            sort_by: Field to sort by ('duration', 'created_at'); defaults to created_at
            sort_order: 'asc' or 'desc'
        """
        async with self.async_session() as session:
            query = (
                select(WorkflowRunModel)
                .join(WorkflowModel, WorkflowRunModel.workflow_id == WorkflowModel.id)
                .where(WorkflowModel.organization_id == organization_id)
            )

            # NOT filtered on usage_info being present. It reads as though it
            # were -- there used to be an `isnot(None)` here -- but usage_info
            # was made NOT NULL by 0c1223cc266f, so that predicate excluded
            # nothing and every run appeared regardless. Removing it changes no
            # results; it just stops the query claiming a filter it never had.
            # The UI hint that said "runs with recorded usage" was wrong for the
            # same reason and is corrected alongside this.

            # Apply date filters if provided
            if start_date:
                query = query.where(WorkflowRunModel.created_at >= start_date)
            if end_date:
                query = query.where(WorkflowRunModel.created_at <= end_date)

            # Only allow specific filters for usage history endpoint
            # This ensures security and prevents unexpected filter attributes
            sanitized_filters = []

            if filters:
                for filter_item in filters:
                    attribute = filter_item.get("attribute")

                    # Only process allowed filters
                    if attribute in USAGE_ALLOWED_FILTERS:
                        sanitized_filters.append(filter_item)

            # Apply filters using the common filter function
            query = apply_workflow_run_filters(query, sanitized_filters)

            # Count and totals come from the SAME filtered subquery, before
            # paging is applied. That is the whole fix: the totals used to be
            # accumulated in the row loop below, which runs over ONE PAGE, so
            # "total duration" was the duration of whatever 50 runs you happened
            # to be looking at -- and it changed when you turned the page.
            totals_source = query.subquery()
            totals_result = await session.execute(
                select(
                    func.count(),
                    # ->> yields text; cast per row rather than casting the
                    # column, because these JSON blobs predate any schema and a
                    # missing key must contribute nothing instead of raising.
                    func.coalesce(
                        func.sum(
                            cast(
                                cast(totals_source.c.usage_info, JSONB).op("->>")(
                                    "call_duration_seconds"
                                ),
                                Float,
                            )
                        ),
                        0.0,
                    ),
                    func.coalesce(
                        func.sum(
                            cast(
                                cast(totals_source.c.cost_info, JSONB).op("->>")(
                                    "charge_usd"
                                ),
                                Float,
                            )
                        ),
                        0.0,
                    ),
                ).select_from(totals_source)
            )
            total_count, total_duration_float, total_charge_usd = totals_result.one()
            # No `or 0.0` fallbacks here: SUM over no rows is NULL, and the
            # coalesce above is what turns that into a number. Guarding it twice
            # meant neither guard was load-bearing and either could be deleted
            # without a test noticing.
            total_count = int(total_count)
            total_duration_seconds = int(round(float(total_duration_float)))
            total_charge_usd = round(float(total_charge_usd), 6)

            # Tie-break on id so paging stays stable when many runs share the
            # same duration (or timestamp) — without it, rows can repeat or be
            # skipped across pages.
            order_clause = get_workflow_run_order_clause(sort_by, sort_order)
            results = await session.execute(
                query.options(joinedload(WorkflowRunModel.workflow))
                .order_by(order_clause, WorkflowRunModel.id.desc())
                .limit(limit)
                .offset(offset)
            )
            runs = results.scalars().all()

            # Format runs. The TOTALS are not accumulated here any more (see
            # the SQL aggregate above), but each row still reports its own
            # duration and cost.
            formatted_runs = []
            for run in runs:
                call_duration = (run.usage_info or {}).get("call_duration_seconds", 0)
                # Per-run counterpart of total_rilt_tokens: cost in cents, the
                # same unit run_usage_response uses. It was hardcoded 0 here as
                # well, so every row in the usage table showed no token usage.
                run_charge_usd = (run.cost_info or {}).get("charge_usd")
                try:
                    rilt_tokens = round(float(run_charge_usd) * 100, 2)
                except (TypeError, ValueError):
                    rilt_tokens = 0

                ic = run.initial_context or {}
                caller_number = ic.get("caller_number")
                called_number = ic.get("called_number") or ic.get("phone_number")
                # DEPRECATED: phone_number — use caller_number/called_number.
                # Inbound runs only have caller_number/called_number; the
                # caller_number is the customer. Outbound runs use the
                # phone_number key written by the dispatchers.
                if run.call_type == "inbound":
                    phone_number = caller_number
                else:
                    phone_number = ic.get("phone_number")

                # Extract disposition from gathered_context
                disposition = None
                if run.gathered_context:
                    disposition = run.gathered_context.get("mapped_call_disposition")

                run_data = {
                    "id": run.id,
                    "workflow_id": run.workflow_id,
                    "workflow_name": run.workflow.name if run.workflow else None,
                    "name": run.name,
                    "created_at": run.created_at.isoformat(),
                    "rilt_token_usage": rilt_tokens,
                    "call_duration_seconds": int(round(call_duration)),
                    "recording_url": run.recording_url,
                    "transcript_url": run.transcript_url,
                    "user_recording_url": get_recording_storage_key(run.extra, "user"),
                    "bot_recording_url": get_recording_storage_key(run.extra, "bot"),
                    "extra": run.extra,
                    "public_access_token": run.public_access_token,
                    "phone_number": phone_number,
                    "caller_number": caller_number,
                    "called_number": called_number,
                    "call_type": run.call_type,
                    "mode": run.mode,
                    "disposition": disposition,
                    "initial_context": run.initial_context,
                    "gathered_context": run.gathered_context,
                }

                # Add USD cost if available in cost_info
                if run.cost_info and "charge_usd" in run.cost_info:
                    run_data["charge_usd"] = run.cost_info["charge_usd"]

                formatted_runs.append(run_data)

            return (
                formatted_runs,
                total_count,
                total_charge_usd,
                total_duration_seconds,
            )

    async def get_usage_runs_for_report(
        self,
        organization_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        filters: Optional[list[dict]] = None,
    ) -> list:
        """Get filtered runs for an organization-scoped usage CSV report.

        Mirrors the filter allowlist used by `get_usage_history`, but selects
        only the columns needed by `build_run_report_csv` and returns every
        matching run (no pagination).
        """
        async with self.async_session() as session:
            query = (
                select(
                    WorkflowRunModel.id,
                    WorkflowRunModel.workflow_id,
                    WorkflowRunModel.definition_id,
                    WorkflowRunModel.campaign_id,
                    WorkflowRunModel.created_at,
                    WorkflowRunModel.initial_context,
                    WorkflowRunModel.gathered_context,
                    WorkflowRunModel.cost_info,
                    WorkflowRunModel.usage_info,
                    WorkflowRunModel.public_access_token,
                )
                .join(WorkflowModel, WorkflowRunModel.workflow_id == WorkflowModel.id)
                # See get_usage_history: the usage_info isnot(None) predicate
                # that used to sit here filtered nothing, because the column is
                # NOT NULL.
                .where(WorkflowModel.organization_id == organization_id)
                .order_by(WorkflowRunModel.created_at.desc())
            )

            if start_date:
                query = query.where(WorkflowRunModel.created_at >= start_date)
            if end_date:
                query = query.where(WorkflowRunModel.created_at <= end_date)

            sanitized_filters = []
            if filters:
                for filter_item in filters:
                    if filter_item.get("attribute") in USAGE_ALLOWED_FILTERS:
                        sanitized_filters.append(filter_item)

            query = apply_workflow_run_filters(query, sanitized_filters)

            result = await session.execute(query)
            return list(result.all())

    async def get_daily_usage_breakdown(
        self,
        organization_id: int,
        start_date: datetime,
        end_date: datetime,
        price_per_second_usd: float,
    ) -> dict:
        """Get daily usage breakdown for an organization with pricing."""

        async with self.async_session() as session:
            # Get org timezone preference first, then fall back to legacy user config.
            user_timezone = "UTC"  # Default timezone
            pref_result = await session.execute(
                select(OrganizationConfigurationModel).where(
                    OrganizationConfigurationModel.organization_id == organization_id,
                    OrganizationConfigurationModel.key.in_(
                        [
                            OrganizationConfigurationKey.ORGANIZATION_PREFERENCES.value,
                            OrganizationConfigurationKey.MODEL_CONFIGURATION_PREFERENCES.value,
                        ]
                    ),
                )
            )
            pref_rows = pref_result.scalars().all()
            pref_by_key = {pref.key: pref for pref in pref_rows}
            pref_obj = pref_by_key.get(
                OrganizationConfigurationKey.ORGANIZATION_PREFERENCES.value
            ) or pref_by_key.get(
                OrganizationConfigurationKey.MODEL_CONFIGURATION_PREFERENCES.value
            )
            if pref_obj and pref_obj.value:
                user_timezone = pref_obj.value.get("timezone") or user_timezone

            # Validate timezone string
            try:
                # Test if timezone is valid
                ZoneInfo(user_timezone)
            except Exception:
                # Fallback to UTC if timezone is invalid
                user_timezone = "UTC"
            # Query to get daily aggregates
            # Use AT TIME ZONE to convert to user's timezone before grouping by date
            date_expr = cast(
                func.timezone(user_timezone, WorkflowRunModel.created_at), Date
            )

            daily_usage = await session.execute(
                select(
                    date_expr.label("date"),
                    func.sum(
                        WorkflowRunModel.usage_info["call_duration_seconds"].as_float()
                    ).label("total_seconds"),
                    func.count(WorkflowRunModel.id).label("call_count"),
                )
                .join(WorkflowModel, WorkflowModel.id == WorkflowRunModel.workflow_id)
                .where(
                    WorkflowModel.organization_id == organization_id,
                    WorkflowRunModel.created_at >= start_date,
                    WorkflowRunModel.created_at <= end_date,
                    WorkflowRunModel.is_completed == True,
                )
                .group_by(date_expr)
                .order_by(date_expr.desc())
            )

            breakdown = []
            total_minutes = 0
            total_cost_usd = 0
            total_rilt_tokens = 0

            for row in daily_usage:
                seconds = row.total_seconds or 0
                minutes = seconds / 60
                cost_usd = seconds * price_per_second_usd
                rilt_tokens = cost_usd * 100  # 1 cent = 1 token

                total_minutes += minutes
                total_cost_usd += cost_usd
                total_rilt_tokens += rilt_tokens

                breakdown.append(
                    {
                        "date": row.date.isoformat(),
                        "minutes": round(minutes, 1),
                        "cost_usd": round(cost_usd, 2),
                        "rilt_tokens": round(rilt_tokens, 0),
                        "call_count": row.call_count,
                    }
                )

            return {
                "breakdown": breakdown,
                "total_minutes": round(total_minutes, 1),
                "total_cost_usd": round(total_cost_usd, 2),
                "total_rilt_tokens": round(total_rilt_tokens, 0),
                "currency": "USD",
            }

    def _calculate_current_period(self) -> tuple[datetime, datetime]:
        """Calculate the current calendar-month reporting period."""
        now = datetime.now(timezone.utc)

        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        period_end = period_start + relativedelta(months=1) - relativedelta(seconds=1)

        return period_start, period_end
