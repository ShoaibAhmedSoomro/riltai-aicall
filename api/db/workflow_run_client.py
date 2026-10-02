import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, or_
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload, selectinload

from loguru import logger

from api.constants import PUBLIC_ARTIFACT_TOKEN_TTL_DAYS
from api.db.base_client import BaseDBClient
from api.db.filters import apply_workflow_run_filters, get_workflow_run_order_clause
from api.db.models import (
    OrganizationConfigurationModel,
    OrganizationModel,
    UserModel,
    WorkflowDefinitionModel,
    WorkflowModel,
    WorkflowRunModel,
)
from api.enums import (
    CallType,
    OrganizationConfigurationKey,
    StorageBackend,
    WorkflowRunState,
)
from api.schemas.organization_preferences import OrganizationPreferences
from api.schemas.workflow import WorkflowRunResponseSchema
from api.services.governance.policy import resolve_governance_policy, retention_deadline
from api.services.workflow.run_usage_response import format_public_cost_info
from api.utils.recording_artifacts import get_recording_storage_key


# Matches RateLimiter.stale_call_timeout (services/call_concurrency/rate_limiter.py):
# a run older than this has lost its concurrency slot, so it is not "live".
LIVE_RUN_MAX_AGE_SECONDS = 1200


class WorkflowRunClient(BaseDBClient):
    async def create_workflow_run(
        self,
        name: str,
        workflow_id: int,
        mode: str,
        user_id: int,
        call_type: CallType = CallType.OUTBOUND,
        initial_context: dict = None,
        gathered_context: dict = None,
        logs: dict = None,
        campaign_id: int = None,
        queued_run_id: int = None,
        organization_id: int | None = None,
        definition_id: int | None = None,
    ) -> WorkflowRunModel:
        async with self.async_session() as session:
            workflow_query = (
                select(WorkflowModel)
                .options(joinedload(WorkflowModel.user))
                .where(WorkflowModel.id == workflow_id)
            )
            if organization_id is not None:
                workflow_query = workflow_query.where(
                    WorkflowModel.organization_id == organization_id
                )
            elif user_id is not None:
                workflow_query = workflow_query.where(WorkflowModel.user_id == user_id)

            workflow = await session.execute(workflow_query)
            workflow = workflow.scalars().first()
            if not workflow:
                raise ValueError(f"Workflow with ID {workflow_id} not found")

            if definition_id is not None:
                definition_result = await session.execute(
                    select(WorkflowDefinitionModel.id).where(
                        WorkflowDefinitionModel.id == definition_id,
                        WorkflowDefinitionModel.workflow_id == workflow.id,
                    )
                )
                if definition_result.scalar_one_or_none() is None:
                    raise ValueError(
                        f"Workflow definition {definition_id} does not belong to "
                        f"workflow {workflow.id}"
                    )

            # Get the current storage backend based on ENABLE_AWS_S3 flag
            current_backend = StorageBackend.get_current_backend()

            created_at = datetime.now(UTC)
            retention_expires_at, governance_extra = await self._stamp_governance(
                session, workflow, definition_id, created_at
            )

            new_run = WorkflowRunModel(
                created_at=created_at,
                retention_expires_at=retention_expires_at,
                extra=governance_extra,
                name=name,
                workflow=workflow,
                mode=mode,
                definition_id=definition_id,
                initial_context=initial_context or {},
                gathered_context=gathered_context or {},
                logs=logs or {},
                campaign_id=campaign_id,
                queued_run_id=queued_run_id,
                storage_backend=current_backend.value,
                call_type=call_type.value,
            )
            session.add(new_run)
            try:
                await session.commit()
            except Exception as e:
                await session.rollback()
                raise e
            await session.refresh(new_run)
        return new_run

    async def _stamp_governance(
        self,
        session,
        workflow: WorkflowModel,
        definition_id: int | None,
        created_at: datetime,
    ) -> tuple[datetime | None, dict]:
        """The retention deadline (and the policy it came from) for a new run.

        Stamped at creation rather than joined in at purge time: the purge is
        then one indexed scan, and a later policy change does not re-age or
        resurrect runs that already exist.

        Never raises. A run that fails to get a deadline is kept forever, which
        is the safe direction; failing here would refuse a call over a
        bookkeeping column.
        """
        try:
            config_query = select(WorkflowDefinitionModel.workflow_configurations)
            if definition_id is not None:
                config_query = config_query.where(
                    WorkflowDefinitionModel.id == definition_id
                )
            else:
                config_query = config_query.where(
                    WorkflowDefinitionModel.workflow_id == workflow.id,
                    WorkflowDefinitionModel.is_current.is_(True),
                )
            workflow_configurations = (
                await session.execute(config_query)
            ).scalars().first()

            prefs = OrganizationPreferences()
            if workflow.organization_id is not None:
                raw = (
                    await session.execute(
                        select(OrganizationConfigurationModel.value).where(
                            OrganizationConfigurationModel.organization_id
                            == workflow.organization_id,
                            OrganizationConfigurationModel.key
                            == OrganizationConfigurationKey.ORGANIZATION_PREFERENCES.value,
                        )
                    )
                ).scalars().first()
                if isinstance(raw, dict):
                    prefs = OrganizationPreferences.model_validate(raw)

            policy = resolve_governance_policy(workflow_configurations, prefs)
            deadline = retention_deadline(created_at, policy)
            if deadline is None and policy.storage_mode == "everything":
                return None, {}
            # Recorded so the purge knows what to clear without re-resolving a
            # policy that may have changed since this call happened.
            return deadline, {
                "governance": {
                    "storage_mode": policy.storage_mode,
                    "retention_days": policy.retention_days,
                }
            }
        except Exception as exc:
            logger.error(
                f"Could not resolve governance policy for workflow {workflow.id}; "
                f"the run will be kept: {exc}"
            )
            return None, {}

    async def get_runs_due_for_purge(
        self, now: datetime, limit: int, after_id: int = 0
    ) -> list[WorkflowRunModel]:
        """Runs past their retention deadline whose artifacts still exist."""
        async with self.async_session() as session:
            result = await session.execute(
                select(WorkflowRunModel)
                .options(selectinload(WorkflowRunModel.text_session))
                .where(
                    WorkflowRunModel.retention_expires_at.is_not(None),
                    WorkflowRunModel.retention_expires_at <= now,
                    WorkflowRunModel.purged_at.is_(None),
                    WorkflowRunModel.id > after_id,
                )
                .order_by(WorkflowRunModel.id)
                .limit(limit)
            )
            return list(result.scalars().all())

    async def delete_run_artifacts(
        self, run_id: int, *, clear_context: bool, now: datetime
    ) -> bool:
        """Forget what a purged run captured, and mark it purged.

        Called only after the stored objects are gone. Keeps the row, its
        timestamps, usage and cost: removing them would change reports for calls
        that were already counted.

        Clears the places a call's content lives besides object storage: the
        recording/transcript pointers, the realtime events in ``logs`` (which
        carry the transcript turn by turn), and a text chat's conversation. Under
        ``basic_only`` also the gathered and initial context.
        """
        async with self.async_session() as session:
            run = (
                await session.execute(
                    select(WorkflowRunModel)
                    .options(selectinload(WorkflowRunModel.text_session))
                    .where(WorkflowRunModel.id == run_id)
                )
            ).scalars().first()
            if run is None:
                return False

            run.recording_url = None
            run.transcript_url = None
            # Reassign, never mutate in place: JSON columns do not track it.
            run.extra = {k: v for k, v in (run.extra or {}).items() if k != "recordings"}
            run.logs = {
                k: v
                for k, v in (run.logs or {}).items()
                if k != "realtime_feedback_events"
            }
            if clear_context:
                run.gathered_context = {}
                run.initial_context = {}
            if run.text_session is not None:
                run.text_session.session_data = {}
            # The artifacts are gone, so a link to them should not keep answering.
            run.public_access_token = None
            run.public_access_token_expires_at = None
            run.purged_at = now

            await session.commit()
            return True

    async def get_all_workflow_runs(self) -> list[WorkflowRunModel]:
        async with self.async_session() as session:
            result = await session.execute(select(WorkflowRunModel))
            return result.scalars().all()

    async def get_workflow_runs_for_superadmin(
        self,
        limit: int = 50,
        offset: int = 0,
        filters: Optional[List[Dict[str, Any]]] = None,
        sort_by: Optional[str] = None,
        sort_order: str = "desc",
    ) -> tuple[list[dict], int]:
        """
        Get paginated workflow runs for superadmin with organization information.
        Returns tuple of (workflow_runs, total_count).

        Args:
            sort_by: Field to sort by ('duration', 'created_at', etc.)
            sort_order: 'asc' or 'desc'
        """
        async with self.async_session() as session:
            # Build base query with joins
            base_query = (
                select(WorkflowRunModel)
                .join(WorkflowModel, WorkflowRunModel.workflow_id == WorkflowModel.id)
                .join(UserModel, WorkflowModel.user_id == UserModel.id)
                .outerjoin(
                    OrganizationModel,
                    UserModel.selected_organization_id == OrganizationModel.id,
                )
            )

            # Apply filters
            base_query = apply_workflow_run_filters(base_query, filters)

            # Count total with filters
            count_query = base_query.with_only_columns(func.count(WorkflowRunModel.id))
            count_result = await session.execute(count_query)
            total_count = count_result.scalar()

            # Get paginated results with filters and sorting
            order_clause = get_workflow_run_order_clause(sort_by, sort_order)
            result = await session.execute(
                base_query.options(
                    joinedload(WorkflowRunModel.workflow).joinedload(
                        WorkflowModel.user
                    ),
                    joinedload(WorkflowRunModel.workflow)
                    .joinedload(WorkflowModel.user)
                    .joinedload(UserModel.selected_organization),
                )
                .order_by(order_clause)
                .limit(limit)
                .offset(offset)
            )
            workflow_runs = result.scalars().all()

            # Format the response
            formatted_runs = []
            for run in workflow_runs:
                organization = (
                    run.workflow.user.selected_organization
                    if run.workflow.user
                    else None
                )
                formatted_runs.append(
                    {
                        "id": run.id,
                        "name": run.name,
                        "workflow_id": run.workflow_id,
                        "workflow_name": run.workflow.name if run.workflow else None,
                        "user_id": run.workflow.user_id if run.workflow else None,
                        "organization_id": organization.id if organization else None,
                        "organization_name": (
                            organization.provider_id if organization else None
                        ),
                        "mode": run.mode,
                        "is_completed": run.is_completed,
                        "recording_url": run.recording_url,
                        "transcript_url": run.transcript_url,
                        "user_recording_url": get_recording_storage_key(
                            run.extra, "user"
                        ),
                        "bot_recording_url": get_recording_storage_key(
                            run.extra, "bot"
                        ),
                        "usage_info": run.usage_info,
                        "cost_info": run.cost_info,
                        "initial_context": run.initial_context,
                        "gathered_context": run.gathered_context,
                        "created_at": run.created_at,
                    }
                )

            return formatted_runs, total_count

    async def get_live_workflow_runs(
        self, organization_id: int, limit: int = 100
    ) -> list[dict]:
        """Runs in state 'running' for one organization, newest first.

        A run is only listed if it started within LIVE_RUN_MAX_AGE_SECONDS. A pipeline
        that died without writing state='completed' would otherwise sit in the live
        list forever; that window is the call-concurrency limiter's own stale-call
        timeout, so "live" here means the same as "holds a slot" there.
        """
        cutoff = datetime.now(UTC) - timedelta(seconds=LIVE_RUN_MAX_AGE_SECONDS)
        async with self.async_session() as session:
            result = await session.execute(
                select(
                    WorkflowRunModel.id,
                    WorkflowRunModel.workflow_id,
                    WorkflowModel.name.label("workflow_name"),
                    WorkflowRunModel.mode,
                    WorkflowRunModel.call_type,
                    WorkflowRunModel.created_at,
                    WorkflowRunModel.initial_context,
                )
                .join(WorkflowModel, WorkflowModel.id == WorkflowRunModel.workflow_id)
                .where(
                    WorkflowModel.organization_id == organization_id,
                    WorkflowRunModel.state == WorkflowRunState.RUNNING.value,
                    WorkflowRunModel.created_at > cutoff,
                )
                .order_by(WorkflowRunModel.created_at.desc())
                .limit(limit)
            )
            return [dict(row._mapping) for row in result.all()]

    async def get_workflow_run(
        self, run_id: int, user_id: int = None, organization_id: int = None
    ) -> WorkflowRunModel | None:
        async with self.async_session() as session:
            query = (
                select(WorkflowRunModel)
                .options(selectinload(WorkflowRunModel.definition))
                .join(WorkflowRunModel.workflow)
            )

            if organization_id:
                # Filter by organization_id when provided
                query = query.where(
                    WorkflowRunModel.id == run_id,
                    WorkflowModel.organization_id == organization_id,
                )
            elif user_id:
                # Fallback to user_id for backwards compatibility
                query = query.where(
                    WorkflowRunModel.id == run_id,
                    WorkflowModel.user_id == user_id,
                )
            else:
                query = query.where(WorkflowRunModel.id == run_id)

            result = await session.execute(query)
            return result.scalars().first()

    async def get_workflow_run_by_id(self, run_id: int) -> WorkflowRunModel | None:
        """Get workflow run by ID without user filtering - for background tasks"""
        async with self.async_session() as session:
            result = await session.execute(
                select(WorkflowRunModel)
                .options(
                    joinedload(WorkflowRunModel.workflow).joinedload(WorkflowModel.user)
                )
                .where(WorkflowRunModel.id == run_id)
            )
            return result.scalars().first()

    async def get_workflow_run_configurations(
        self, run_id: int, organization_id: int
    ) -> dict:
        """Load the immutable workflow configuration snapshot for one run."""

        async with self.async_session() as session:
            result = await session.execute(
                select(WorkflowDefinitionModel.workflow_configurations)
                .join(
                    WorkflowRunModel,
                    WorkflowRunModel.definition_id == WorkflowDefinitionModel.id,
                )
                .join(WorkflowModel, WorkflowRunModel.workflow_id == WorkflowModel.id)
                .where(
                    WorkflowRunModel.id == run_id,
                    WorkflowModel.organization_id == organization_id,
                )
            )
            return result.scalar_one_or_none() or {}

    async def get_organization_id_by_workflow_run_id(
        self, run_id: int | None
    ) -> int | None:
        """Resolve organization_id from a workflow run via workflow.user."""
        if not run_id:
            return None
        async with self.async_session() as session:
            result = await session.execute(
                select(WorkflowModel.organization_id)
                .join(
                    WorkflowRunModel, WorkflowRunModel.workflow_id == WorkflowModel.id
                )
                .where(WorkflowRunModel.id == run_id)
            )
            return result.scalar_one_or_none()

    async def get_workflow_runs_by_workflow_id(
        self,
        workflow_id: int,
        user_id: int = None,
        organization_id: int = None,
        limit: int = 50,
        offset: int = 0,
        filters: Optional[List[Dict[str, Any]]] = None,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = "desc",
    ) -> tuple[list[WorkflowRunResponseSchema], int]:
        async with self.async_session() as session:
            # Build base query
            base_query = (
                select(WorkflowRunModel)
                .join(WorkflowModel, WorkflowRunModel.workflow_id == WorkflowModel.id)
                .where(WorkflowRunModel.workflow_id == workflow_id)
            )

            if organization_id:
                # Filter by organization_id when provided
                base_query = base_query.where(
                    WorkflowModel.organization_id == organization_id
                )
            elif user_id:
                # Fallback to user_id for backwards compatibility
                base_query = base_query.where(WorkflowModel.user_id == user_id)

            # Apply filters
            base_query = apply_workflow_run_filters(base_query, filters)

            # Count total with filters
            count_query = base_query.with_only_columns(func.count(WorkflowRunModel.id))
            count_result = await session.execute(count_query)
            total_count = count_result.scalar()

            # Get paginated results with filters and sorting
            order_clause = get_workflow_run_order_clause(sort_by, sort_order)
            result = await session.execute(
                base_query.order_by(order_clause).limit(limit).offset(offset)
            )
            runs = [
                WorkflowRunResponseSchema.model_validate(
                    {
                        "id": run.id,
                        "workflow_id": run.workflow_id,
                        "name": run.name,
                        "mode": run.mode,
                        "created_at": run.created_at,
                        "is_completed": run.is_completed,
                        "recording_url": run.recording_url,
                        "transcript_url": run.transcript_url,
                        "user_recording_url": get_recording_storage_key(
                            run.extra, "user"
                        ),
                        "bot_recording_url": get_recording_storage_key(
                            run.extra, "bot"
                        ),
                        "cost_info": format_public_cost_info(
                            run.cost_info, run.usage_info
                        ),
                        "definition_id": run.definition_id,
                        "initial_context": run.initial_context,
                        "gathered_context": run.gathered_context,
                        "call_type": run.call_type,
                    }
                )
                for run in result.scalars().all()
            ]
            return runs, total_count

    async def update_workflow_run(
        self,
        run_id: int,
        is_completed: bool = False,
        recording_url: str | None = None,
        transcript_url: str | None = None,
        storage_backend: str | None = None,
        usage_info: dict | None = None,
        cost_info: dict | None = None,
        initial_context: dict | None = None,
        gathered_context: dict | None = None,
        logs: dict | None = None,
        state: str | None = None,
        annotations: dict | None = None,
        extra: dict | None = None,
    ) -> WorkflowRunModel:
        async with self.async_session() as session:
            # Use SELECT FOR UPDATE to lock the row during the update
            result = await session.execute(
                select(WorkflowRunModel)
                .where(WorkflowRunModel.id == run_id)
                .with_for_update()
            )
            run = result.scalars().first()
            if not run:
                raise ValueError(f"Workflow run with ID {run_id} not found")
            if recording_url:
                run.recording_url = recording_url
            if transcript_url:
                run.transcript_url = transcript_url
            if storage_backend:
                run.storage_backend = storage_backend
            if usage_info:
                run.usage_info = usage_info
            if cost_info:
                run.cost_info = cost_info
            if initial_context:
                # Merge initial context patches so independent call-start/runtime
                # writers do not erase keys stored earlier in the run lifecycle.
                run.initial_context = {
                    **(run.initial_context or {}),
                    **initial_context,
                }
            if gathered_context:
                # Lets merge the incoming gathered context keys with the existing ones
                run.gathered_context = {
                    **run.gathered_context,
                    **gathered_context,
                }
            if logs:
                # Lets merge the incoming logs key with existing ones
                run.logs = {**run.logs, **logs}
            if annotations:
                run.annotations = {**run.annotations, **annotations}
            if extra:
                run.extra = {**run.extra, **extra}
            if is_completed:
                run.is_completed = is_completed
            if state:
                run.state = state
            try:
                await session.commit()
            except Exception as e:
                await session.rollback()
                raise e
            await session.refresh(run)
        return run

    async def get_workflow_run_with_context(
        self, workflow_run_id: int
    ) -> Tuple[Optional[WorkflowRunModel], Optional[int]]:
        """
        Get workflow run with all related data and return organization_id.

        Returns:
            Tuple of (workflow_run, organization_id) or (None, None) if not found
        """
        async with self.async_session() as session:
            result = await session.execute(
                select(WorkflowRunModel)
                .options(
                    selectinload(WorkflowRunModel.definition),
                    selectinload(WorkflowRunModel.workflow).options(
                        selectinload(WorkflowModel.user),
                        selectinload(WorkflowModel.current_definition),
                    ),
                )
                .where(WorkflowRunModel.id == workflow_run_id)
            )
            workflow_run = result.scalars().first()

            if not workflow_run:
                return None, None

            if not workflow_run.workflow:
                return workflow_run, None

            organization_id = workflow_run.workflow.organization_id
            return workflow_run, organization_id

    async def ensure_public_access_token(self, workflow_run_id: int) -> Optional[str]:
        """Generate a public access token if not exists, return existing if present (idempotent).

        Args:
            workflow_run_id: The ID of the workflow run

        Returns:
            The public access token string, or None if workflow run not found
        """
        async with self.async_session() as session:
            result = await session.execute(
                select(WorkflowRunModel).where(WorkflowRunModel.id == workflow_run_id)
            )
            run = result.scalars().first()
            if not run:
                return None

            now = datetime.now(UTC)

            # Return the existing token while it is still valid. A NULL expiry
            # means "never expires" and belongs to tokens minted before expiry
            # existed -- those URLs are already out in webhook payloads and
            # exported CSVs, so they keep working.
            if run.public_access_token:
                expires = run.public_access_token_expires_at
                if expires is None or expires > now:
                    return run.public_access_token
                # Expired: rotate rather than extend. Extending would let any
                # authenticated view silently resurrect a link shared months ago,
                # which would make the expiry meaningless for the only party it
                # is meant to constrain -- whoever is holding the old URL.

            # Generate and persist a new token
            token = str(uuid.uuid4())
            run.public_access_token = token
            run.public_access_token_expires_at = now + timedelta(
                days=PUBLIC_ARTIFACT_TOKEN_TTL_DAYS
            )

            try:
                await session.commit()
            except Exception as e:
                await session.rollback()
                raise e
            await session.refresh(run)

            return run.public_access_token

    async def get_workflow_run_by_public_token(
        self, token: str
    ) -> Optional[WorkflowRunModel]:
        """Lookup workflow run by public access token.

        Args:
            token: The public access token

        Returns:
            The WorkflowRunModel if found and unexpired, None otherwise

        The single validation choke point for the whole public download surface:
        the route does no other checking, so the expiry predicate lives here.

        An expired token returns None, which the caller turns into the same 404
        an unknown token gets. That sameness is deliberate -- the endpoint is
        unauthenticated and unrate-limited, so distinguishing "expired" from
        "never existed" would turn it into an oracle for probing token validity.
        """
        async with self.async_session() as session:
            result = await session.execute(
                select(WorkflowRunModel).where(
                    WorkflowRunModel.public_access_token == token,
                    # NULL expiry means never expires: tokens minted before this
                    # column existed keep working, because their URLs were handed
                    # to third parties as durable.
                    or_(
                        WorkflowRunModel.public_access_token_expires_at.is_(None),
                        WorkflowRunModel.public_access_token_expires_at
                        > datetime.now(UTC),
                    ),
                )
            )
            return result.scalars().first()

    async def get_workflow_run_by_call_id(
        self, call_id: str
    ) -> Optional[WorkflowRunModel]:
        """Find workflow run by call_id stored in gathered_context.

        Args:
            call_id: The telephony call ID to search for

        Returns:
            The WorkflowRunModel if found, None otherwise
        """
        async with self.async_session() as session:
            # Use JSON text extraction to find matching call_id
            # This leverages the idx_workflow_runs_call_id index
            result = await session.execute(
                select(WorkflowRunModel)
                .options(
                    joinedload(WorkflowRunModel.workflow).joinedload(WorkflowModel.user)
                )
                .where(
                    WorkflowRunModel.gathered_context.op("->>")("call_id") == call_id
                )
                .order_by(WorkflowRunModel.created_at.desc())
                .limit(1)
            )
            return result.scalars().first()
