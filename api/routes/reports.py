from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.db import db_client
from api.db.models import UserModel
from api.services.auth.depends import get_user
from api.services.reports import DailyReportService

router = APIRouter(prefix="/organizations/reports")


class DailyReportResponse(BaseModel):
    date: str
    timezone: str
    workflow_id: Optional[int]
    metrics: Dict[str, int]
    disposition_distribution: List[Dict[str, Any]]
    call_duration_distribution: List[Dict[str, Any]]


class WorkflowOption(BaseModel):
    id: int
    name: str


class WorkflowRunDetail(BaseModel):
    phone_number: str
    disposition: str
    duration_seconds: float
    workflow_id: int
    run_id: int
    workflow_name: str
    created_at: str


@router.get("/daily", response_model=DailyReportResponse)
async def get_daily_report(
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    timezone: str = Query(..., description="IANA timezone (e.g., 'America/New_York')"),
    workflow_id: Optional[int] = Query(
        None, description="Optional workflow ID to filter by"
    ),
    user: UserModel = Depends(get_user),
) -> DailyReportResponse:
    """
    Get daily report for the specified date and timezone.
    If workflow_id is provided, filters results to that specific workflow.
    If workflow_id is None, includes all workflows for the organization.
    """
    if not user.selected_organization_id:
        raise HTTPException(status_code=400, detail="No organization selected")

    # Validate date format
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400, detail="Invalid date format. Use YYYY-MM-DD"
        )

    report_service = DailyReportService()

    try:
        report = await report_service.get_daily_report(
            organization_id=user.selected_organization_id,
            date=date,
            timezone=timezone,
            workflow_id=workflow_id,
        )
        return DailyReportResponse(**report)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workflows", response_model=List[WorkflowOption])
async def get_workflow_options(
    user: UserModel = Depends(get_user),
) -> List[WorkflowOption]:
    """
    Get all workflows for the user's organization.
    Used to populate the workflow selector dropdown in the reports page.
    """
    if not user.selected_organization_id:
        raise HTTPException(status_code=400, detail="No organization selected")

    report_service = DailyReportService()

    workflows = await report_service.get_workflows_for_organization(
        organization_id=user.selected_organization_id
    )

    return [WorkflowOption(**w) for w in workflows]


@router.get("/daily/runs", response_model=List[WorkflowRunDetail])
async def get_daily_runs_detail(
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    timezone: str = Query(..., description="IANA timezone (e.g., 'America/New_York')"),
    workflow_id: Optional[int] = Query(
        None, description="Optional workflow ID to filter by"
    ),
    user: UserModel = Depends(get_user),
) -> List[WorkflowRunDetail]:
    """
    Get detailed workflow runs for the specified date.
    Used for CSV export functionality.
    """
    if not user.selected_organization_id:
        raise HTTPException(status_code=400, detail="No organization selected")

    # Validate date format
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400, detail="Invalid date format. Use YYYY-MM-DD"
        )

    report_service = DailyReportService()

    try:
        runs = await report_service.get_daily_runs_detail(
            organization_id=user.selected_organization_id,
            date=date,
            timezone=timezone,
            workflow_id=workflow_id,
        )
        return [WorkflowRunDetail(**run) for run in runs]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class AlertItem(BaseModel):
    severity: str
    text: str
    href: str
    count: int
    occurred_at: Optional[str] = None


class AlertsResponse(BaseModel):
    """Things worth acting on, composed from signals that already exist.

    Deliberately NOT an alerting domain: no new table, no sweeper, no rules
    engine. Three conditions the system already records are read on request.
    An empty list means nothing is wrong, which is a real answer -- the panel
    this replaces showed invented alerts.
    """

    items: List[AlertItem]


@router.get("/alerts", response_model=AlertsResponse)
async def get_alerts(user: UserModel = Depends(get_user)):
    """Current problems for the caller's organization."""
    if not user.selected_organization_id:
        raise HTTPException(status_code=400, detail="No organization selected")

    organization_id = user.selected_organization_id
    items: List[AlertItem] = []

    # 1. Webhooks that exhausted their retries. The receiving system never got
    #    the event and nothing will send it again.
    dead_letters = await db_client.count_dead_letter_deliveries(organization_id)
    if dead_letters:
        items.append(
            AlertItem(
                severity="error",
                text=f"{dead_letters} webhook {'delivery' if dead_letters == 1 else 'deliveries'} gave up after retrying",
                href="/usage",
                count=dead_letters,
            )
        )

    # 2. Campaigns the circuit breaker paused. Still-paused only: one somebody
    #    has already resumed is history, not something to act on.
    for campaign in await db_client.get_circuit_breaker_tripped_campaigns(
        organization_id
    ):
        items.append(
            AlertItem(
                severity="warning",
                text=f'Campaign "{campaign["name"]}" was paused by the failure circuit breaker',
                href=f"/campaigns/{campaign['campaign_id']}",
                count=1,
                occurred_at=campaign["occurred_at"],
            )
        )

    # 3. Telephony configs missing webhook verification. Same counts the
    #    existing warnings banner uses, so the two cannot disagree.
    telnyx = await db_client.count_telnyx_configs_missing_webhook_public_key(
        organization_id
    )
    vonage = await db_client.count_vonage_configs_missing_signature_secret(
        organization_id
    )
    for count, provider in ((telnyx, "Telnyx"), (vonage, "Vonage")):
        if count:
            items.append(
                AlertItem(
                    severity="warning",
                    text=f"{count} {provider} configuration{'' if count == 1 else 's'} cannot verify incoming webhooks",
                    href="/telephony-configurations",
                    count=count,
                )
            )

    return AlertsResponse(items=items)
