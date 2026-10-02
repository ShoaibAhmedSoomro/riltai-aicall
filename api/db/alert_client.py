"""Database access for alert channels, rules and events.

Every read and write is scoped by ``organization_id`` here, at the query, so a route
cannot forget to. See api/AGENTS.md on tenant isolation.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from api.db.base_client import BaseDBClient
from api.db.models import (
    AlertChannelModel,
    AlertEventModel,
    AlertRuleModel,
    WorkflowModel,
    WorkflowRunModel,
)
from api.enums import TelephonyCallStatus

class DuplicateAlertNameError(Exception):
    """A channel or rule with this name already exists in the organization."""


_CHANNEL_FIELDS = {"name", "config", "is_active"}
_RULE_FIELDS = {
    "name", "is_active", "scope_workflow_id", "trigger", "metric", "comparator",
    "threshold", "match_value", "window_minutes", "severity", "cooldown_minutes",
    "channel_uuids",
}


async def _commit_unique(session) -> None:
    """Commit, turning a name collision into a domain error the route can report."""
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        if "uq_alert_" in str(e.orig):
            raise DuplicateAlertNameError() from e
        raise


class AlertClient(BaseDBClient):
    # -- channels ---------------------------------------------------------------

    async def create_alert_channel(
        self, organization_id: int, name: str, type: str, config: dict, is_active: bool = True
    ) -> AlertChannelModel:
        async with self.async_session() as session:
            row = AlertChannelModel(
                organization_id=organization_id, name=name, type=type,
                config=config, is_active=is_active,
            )
            session.add(row)
            await _commit_unique(session)
            await session.refresh(row)
            return row

    async def list_alert_channels(self, organization_id: int) -> list[AlertChannelModel]:
        async with self.async_session() as session:
            result = await session.execute(
                select(AlertChannelModel)
                .where(AlertChannelModel.organization_id == organization_id)
                .order_by(AlertChannelModel.name)
            )
            return list(result.scalars().all())

    async def get_alert_channel(
        self, organization_id: int, channel_uuid: str
    ) -> Optional[AlertChannelModel]:
        async with self.async_session() as session:
            result = await session.execute(
                select(AlertChannelModel).where(
                    AlertChannelModel.organization_id == organization_id,
                    AlertChannelModel.channel_uuid == channel_uuid,
                )
            )
            return result.scalar_one_or_none()

    async def get_alert_channels_by_uuids(
        self, organization_id: int, channel_uuids: list[str]
    ) -> list[AlertChannelModel]:
        if not channel_uuids:
            return []
        async with self.async_session() as session:
            result = await session.execute(
                select(AlertChannelModel).where(
                    AlertChannelModel.organization_id == organization_id,
                    AlertChannelModel.channel_uuid.in_(channel_uuids),
                )
            )
            return list(result.scalars().all())

    async def update_alert_channel(
        self, organization_id: int, channel_uuid: str, **fields: Any
    ) -> Optional[AlertChannelModel]:
        async with self.async_session() as session:
            result = await session.execute(
                select(AlertChannelModel).where(
                    AlertChannelModel.organization_id == organization_id,
                    AlertChannelModel.channel_uuid == channel_uuid,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            for k, v in fields.items():
                if k in _CHANNEL_FIELDS:
                    setattr(row, k, v)
            await _commit_unique(session)
            await session.refresh(row)
            return row

    async def delete_alert_channel(self, organization_id: int, channel_uuid: str) -> bool:
        async with self.async_session() as session:
            result = await session.execute(
                select(AlertChannelModel).where(
                    AlertChannelModel.organization_id == organization_id,
                    AlertChannelModel.channel_uuid == channel_uuid,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    # -- rules ------------------------------------------------------------------

    async def create_alert_rule(self, organization_id: int, **fields: Any) -> AlertRuleModel:
        async with self.async_session() as session:
            row = AlertRuleModel(
                organization_id=organization_id,
                **{k: v for k, v in fields.items() if k in _RULE_FIELDS},
            )
            session.add(row)
            await _commit_unique(session)
            await session.refresh(row)
            return row

    async def list_alert_rules(
        self,
        organization_id: int,
        *,
        active_only: bool = False,
        trigger: Optional[str] = None,
    ) -> list[AlertRuleModel]:
        query = select(AlertRuleModel).where(AlertRuleModel.organization_id == organization_id)
        if active_only:
            query = query.where(AlertRuleModel.is_active.is_(True))
        if trigger:
            query = query.where(AlertRuleModel.trigger == trigger)
        async with self.async_session() as session:
            result = await session.execute(query.order_by(AlertRuleModel.name))
            return list(result.scalars().all())

    async def list_all_active_alert_rules(self, trigger: str) -> list[AlertRuleModel]:
        """Active rules of one trigger across every organization, for the cron."""
        async with self.async_session() as session:
            result = await session.execute(
                select(AlertRuleModel).where(
                    AlertRuleModel.is_active.is_(True), AlertRuleModel.trigger == trigger
                )
            )
            return list(result.scalars().all())

    async def get_alert_rule(
        self, organization_id: int, rule_uuid: str
    ) -> Optional[AlertRuleModel]:
        async with self.async_session() as session:
            result = await session.execute(
                select(AlertRuleModel).where(
                    AlertRuleModel.organization_id == organization_id,
                    AlertRuleModel.rule_uuid == rule_uuid,
                )
            )
            return result.scalar_one_or_none()

    async def update_alert_rule(
        self, organization_id: int, rule_uuid: str, **fields: Any
    ) -> Optional[AlertRuleModel]:
        async with self.async_session() as session:
            result = await session.execute(
                select(AlertRuleModel).where(
                    AlertRuleModel.organization_id == organization_id,
                    AlertRuleModel.rule_uuid == rule_uuid,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            for k, v in fields.items():
                if k in _RULE_FIELDS:
                    setattr(row, k, v)
            await _commit_unique(session)
            await session.refresh(row)
            return row

    async def delete_alert_rule(self, organization_id: int, rule_uuid: str) -> bool:
        async with self.async_session() as session:
            result = await session.execute(
                select(AlertRuleModel).where(
                    AlertRuleModel.organization_id == organization_id,
                    AlertRuleModel.rule_uuid == rule_uuid,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    async def claim_alert_rule_fire(self, rule_id: int, now: datetime) -> bool:
        """Take the right to fire this rule now, or learn it is cooling down.

        One conditional UPDATE, so two workers evaluating the same condition at the
        same moment cannot both fire: only one sees the row change.
        """
        async with self.async_session() as session:
            result = await session.execute(
                update(AlertRuleModel)
                .where(
                    AlertRuleModel.id == rule_id,
                    (AlertRuleModel.last_fired_at.is_(None))
                    | (
                        AlertRuleModel.last_fired_at
                        <= now - func.make_interval(0, 0, 0, 0, 0, AlertRuleModel.cooldown_minutes)
                    ),
                )
                .values(last_fired_at=now)
            )
            await session.commit()
            return result.rowcount == 1

    # -- events -----------------------------------------------------------------

    async def record_alert_event(
        self,
        organization_id: int,
        *,
        alert_rule_id: Optional[int],
        severity: str,
        title: str,
        detail: dict,
        workflow_run_id: Optional[int] = None,
        observed_value: Optional[float] = None,
    ) -> AlertEventModel:
        async with self.async_session() as session:
            row = AlertEventModel(
                organization_id=organization_id,
                alert_rule_id=alert_rule_id,
                severity=severity,
                title=title,
                detail=detail,
                workflow_run_id=workflow_run_id,
                observed_value=observed_value,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

    async def list_alert_events(
        self,
        organization_id: int,
        *,
        limit: int = 50,
        severity: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> list[AlertEventModel]:
        query = select(AlertEventModel).where(AlertEventModel.organization_id == organization_id)
        if severity:
            query = query.where(AlertEventModel.severity == severity)
        if since:
            query = query.where(AlertEventModel.created_at >= since)
        async with self.async_session() as session:
            result = await session.execute(
                query.order_by(AlertEventModel.created_at.desc(), AlertEventModel.id.desc()).limit(limit)
            )
            return list(result.scalars().all())

    async def acknowledge_alert_event(
        self, organization_id: int, event_uuid: str, user_id: int
    ) -> Optional[AlertEventModel]:
        async with self.async_session() as session:
            result = await session.execute(
                select(AlertEventModel).where(
                    AlertEventModel.organization_id == organization_id,
                    AlertEventModel.event_uuid == event_uuid,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            if row.acknowledged_at is None:  # acknowledging twice keeps the first
                row.acknowledged_at = datetime.now(UTC)
                row.acknowledged_by = user_id
                await session.commit()
                await session.refresh(row)
            return row

    # -- window metrics -----------------------------------------------------------

    async def get_window_run_stats(
        self,
        organization_id: int,
        window_minutes: int,
        workflow_id: Optional[int] = None,
    ) -> dict:
        """Counts and the mean duration of calls that finished in the last N minutes.

        Joins through the workflow for the organization, as the usage queries do.
        ``failed`` is a mapped disposition of ``error``, the same value
        mark_workflow_run_failed writes.
        """
        since = datetime.now(UTC) - timedelta(minutes=window_minutes)
        disposition = WorkflowRunModel.gathered_context["mapped_call_disposition"].as_string()
        query = (
            select(
                func.count(WorkflowRunModel.id),
                func.count(WorkflowRunModel.id).filter(disposition == TelephonyCallStatus.ERROR.value),
                func.avg(WorkflowRunModel.usage_info["call_duration_seconds"].as_float()),
            )
            .join(WorkflowModel, WorkflowModel.id == WorkflowRunModel.workflow_id)
            .where(
                WorkflowModel.organization_id == organization_id,
                WorkflowRunModel.is_completed.is_(True),
                WorkflowRunModel.created_at >= since,
            )
        )
        if workflow_id is not None:
            query = query.where(WorkflowRunModel.workflow_id == workflow_id)
        async with self.async_session() as session:
            total, failed, mean = (await session.execute(query)).one()
        return {
            "run_count": int(total or 0),
            "failed_count": int(failed or 0),
            "mean_duration_seconds": float(mean) if mean is not None else None,
        }
