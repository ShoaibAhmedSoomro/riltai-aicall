import json
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from pydantic import BaseModel

from api.db import db_client
from api.db.models import UserModel
from api.services import maintenance
from api.services.auth.depends import get_superuser
from api.services.auth.stack_auth import (
    StackAuthSessionError,
    StackAuthUserSearchError,
    stackauth,
)

router = APIRouter(prefix="/superuser", tags=["superuser"])


class ImpersonateRequest(BaseModel):
    """Request payload for superadmin impersonation.

    ``provider_user_id``, ``user_id``, or ``email`` may be supplied. If more
    than one is provided, ``provider_user_id`` takes precedence, followed by
    ``user_id`` and then ``email``.
    """

    provider_user_id: str | None = None
    user_id: int | None = None
    email: str | None = None


class ImpersonateResponse(BaseModel):
    refresh_token: str
    access_token: str


class SuperuserWorkflowRunResponse(BaseModel):
    id: int
    name: str
    workflow_id: int
    workflow_name: Optional[str]
    user_id: Optional[int]
    organization_id: Optional[int]
    organization_name: Optional[str]
    mode: str
    is_completed: bool
    recording_url: Optional[str]
    transcript_url: Optional[str]
    usage_info: Optional[dict]
    cost_info: Optional[dict]
    initial_context: Optional[dict]
    gathered_context: Optional[dict]
    created_at: datetime


class SuperuserWorkflowRunsListResponse(BaseModel):
    workflow_runs: List[SuperuserWorkflowRunResponse]
    total_count: int
    page: int
    limit: int
    total_pages: int


@router.post("/impersonate")
async def impersonate(
    request: ImpersonateRequest, user: UserModel = Depends(get_superuser)
) -> ImpersonateResponse:
    """Impersonate a user as a super-admin.
    Internally, Stack Auth requires the **provider user ID** (a UUID-ish string)
    to create an impersonation session.
    """

    provider_user_id = (
        request.provider_user_id.strip() if request.provider_user_id else None
    ) or None
    email = request.email.strip().lower() if request.email else None

    # ------------------------------------------------------------------
    # Fallback: resolve provider_user_id from internal ``user_id`` or email.
    # ------------------------------------------------------------------
    if provider_user_id is None:
        if request.user_id is not None:
            db_user = await db_client.get_user_by_id(request.user_id)

            if db_user is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"User with ID {request.user_id} not found.",
                )

            provider_user_id = db_user.provider_id
        elif email:
            db_user = await db_client.get_user_by_email(email)

            if db_user is not None:
                provider_user_id = db_user.provider_id
            else:
                try:
                    stack_users = await stackauth.find_users_by_email(email)
                except StackAuthUserSearchError as exc:
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail="Failed to search Stack Auth users.",
                    ) from exc

                if len(stack_users) == 1 and isinstance(stack_users[0].get("id"), str):
                    provider_user_id = stack_users[0]["id"]
                elif len(stack_users) > 1:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Multiple Stack Auth users matched that email.",
                    )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"User with email {email} not found.",
                    )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "One of 'provider_user_id', 'user_id', or 'email' must be provided."
                ),
            )

    # ------------------------------------------------------------------
    # Call Stack Auth to create the impersonation session
    # ------------------------------------------------------------------
    try:
        session = await stackauth.impersonate(provider_user_id)
    except StackAuthSessionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to create Stack Auth impersonation session.",
        ) from exc

    if (
        not isinstance(session, dict)
        or "refresh_token" not in session
        or "access_token" not in session
    ):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to create Stack Auth impersonation session.",
        )

    return ImpersonateResponse(
        refresh_token=session["refresh_token"],
        access_token=session["access_token"],
    )


@router.get("/workflow-runs")
async def get_workflow_runs(
    page: int = Query(1, ge=1, description="Page number (starts from 1)"),
    limit: int = Query(50, ge=1, le=100, description="Number of items per page"),
    filters: Optional[str] = Query(None, description="JSON-encoded filter criteria"),
    sort_by: Optional[str] = Query(
        None, description="Field to sort by (e.g., 'duration', 'created_at')"
    ),
    sort_order: Optional[str] = Query(
        "desc", description="Sort order ('asc' or 'desc')"
    ),
    user: UserModel = Depends(get_superuser),
) -> SuperuserWorkflowRunsListResponse:
    """
    Get paginated list of all workflow runs with organization information.
    Requires superuser privileges.

    Filters should be provided as a JSON-encoded array of filter criteria.
    Example: [{"field": "id", "type": "number", "value": {"value": 680}}]
    """
    offset = (page - 1) * limit

    # Parse filters if provided
    filter_criteria = None
    if filters:
        try:
            filter_criteria = json.loads(filters)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid filter format")

    # Validate sort_order
    if sort_order not in ("asc", "desc"):
        sort_order = "desc"

    workflow_runs, total_count = await db_client.get_workflow_runs_for_superadmin(
        limit=limit,
        offset=offset,
        filters=filter_criteria,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    total_pages = (total_count + limit - 1) // limit  # Ceiling division

    return SuperuserWorkflowRunsListResponse(
        workflow_runs=[SuperuserWorkflowRunResponse(**run) for run in workflow_runs],
        total_count=total_count,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


# ── server maintenance ──────────────────────────────────────────────────────
#
# A portal for clearing the Docker build cache, which once grew to 109 GB and
# took the disk to 81%. The API cannot and must not run Docker itself (that is
# root on the host); it files an empty request that scripts/maintenance.py,
# run from cron on the host, picks up. See api/services/maintenance.py.


class DiskUsageResponse(BaseModel):
    total_bytes: int
    used_bytes: int
    free_bytes: int
    percent: float


class LastPruneResponse(BaseModel):
    at: str
    source: str
    ok: bool
    # None, not 0, when the size could not be read either side of the prune:
    # "freed nothing" and "could not tell" are different statements.
    freed_bytes: Optional[int] = None
    error: Optional[str] = None


class MaintenancePolicyResponse(BaseModel):
    auto_keep_hours: int
    emergency_disk_percent: int


class MaintenanceStatusResponse(BaseModel):
    # False where the shared folder is not mounted (local development, another
    # host). The page then says so rather than offering a button that cannot work.
    available: bool
    disk: DiskUsageResponse
    # None until the host script has reported once.
    build_cache_bytes: Optional[int] = None
    status_updated_at: Optional[str] = None
    last_prune: Optional[LastPruneResponse] = None
    policy: Optional[MaintenancePolicyResponse] = None
    prune_requested: bool


class PruneRequestResponse(BaseModel):
    status: str  # "requested" | "already_requested"


@router.get("/maintenance", response_model=MaintenanceStatusResponse)
async def get_maintenance_status(_: UserModel = Depends(get_superuser)):
    status_ = maintenance.read_status() or {}

    def _typed(model, value):
        # A malformed section of the host's file becomes "unknown", not a 500.
        try:
            return model(**value) if isinstance(value, dict) else None
        except Exception:
            return None

    return MaintenanceStatusResponse(
        available=maintenance.is_available(),
        disk=DiskUsageResponse(**maintenance.disk_usage()),
        build_cache_bytes=status_.get("build_cache_bytes"),
        status_updated_at=status_.get("updated_at"),
        last_prune=_typed(LastPruneResponse, status_.get("last_prune")),
        policy=_typed(MaintenancePolicyResponse, status_.get("policy")),
        prune_requested=maintenance.prune_requested(),
    )


@router.post(
    "/maintenance/prune-build-cache",
    response_model=PruneRequestResponse,
    status_code=202,
)
async def request_build_cache_prune(user: UserModel = Depends(get_superuser)):
    """Ask the host to clear the Docker build cache.

    202, not 200: nothing has happened yet. The host picks the request up within
    a minute, and the page polls the status to find out how it went.
    """
    if not maintenance.is_available():
        raise HTTPException(
            status_code=503,
            detail=(
                "Server maintenance is not available here: the shared "
                "maintenance folder is not mounted on this deployment."
            ),
        )

    created = maintenance.request_prune()
    logger.info(
        "Build cache clear {} by user {}",
        "requested" if created else "already pending, requested again",
        user.id,
    )
    return PruneRequestResponse(status="requested" if created else "already_requested")
