"""Live monitoring: which calls are running now, and a socket to watch one.

Endpoints:
    GET /monitor/live-calls          -> calls running now in the caller's organization
    WS  /monitor/ws/{workflow_run_id} -> backfill, then the call's events as they happen

Watching is open to any member of the organization (call history already is).
Listening in to the audio is not: it needs an organization admin, and it is refused
outright for calls whose data policy withholds or redacts what was said.
"""

from fastapi import APIRouter, Depends, WebSocket

from api.db import db_client
from api.db.models import UserModel
from api.enums import OrgRole, WorkflowRunState
from api.schemas.live_monitor import LiveCall, LiveCallsResponse
from api.sdk_expose import sdk_expose
from api.services.auth.depends import (
    get_org_role,
    get_user_with_selected_organization,
    get_user_ws,
)
from api.services.live_monitor import live_calls, monitor_run

router = APIRouter(prefix="/monitor")


@router.get(
    "/live-calls",
    response_model=LiveCallsResponse,
    **sdk_expose(
        method="list_live_calls",
        description="List the calls running right now in the authenticated organization.",
    ),
)
async def list_live_calls(
    user: UserModel = Depends(get_user_with_selected_organization),
) -> LiveCallsResponse:
    calls = await live_calls(user.selected_organization_id)
    return LiveCallsResponse(calls=[LiveCall(**c) for c in calls])


@router.websocket("/ws/{workflow_run_id}")
async def monitor_websocket(
    websocket: WebSocket,
    workflow_run_id: int,
    user: UserModel = Depends(get_user_ws),
):
    """Watch one live call. Same organization guard as the signaling socket: a run
    id from another organization is refused, not merely hidden."""
    if not user.selected_organization_id:
        await websocket.close(code=1008, reason="No organization selected")
        return
    run = await db_client.get_workflow_run(
        workflow_run_id, organization_id=user.selected_organization_id
    )
    if not run:
        await websocket.close(code=1008, reason="Unknown run")
        return

    can_listen = user.is_superuser or (await get_org_role(user)) == OrgRole.ADMIN.value
    await websocket.accept()

    async def still_running() -> bool:
        fresh = await db_client.get_workflow_run(
            workflow_run_id, organization_id=user.selected_organization_id
        )
        return bool(fresh) and fresh.state == WorkflowRunState.RUNNING.value

    await monitor_run(
        websocket, workflow_run_id, can_listen=can_listen, still_running=still_running
    )
