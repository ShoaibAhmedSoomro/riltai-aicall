"""The live-runs query: running, this organization's, recent."""

import itertools
from datetime import UTC, datetime, timedelta

import pytest

from api.db.models import OrganizationModel, UserModel, WorkflowModel, WorkflowRunModel
from api.enums import WorkflowRunState

_n = itertools.count()


async def _org_with_agent(async_session, name="Agent"):
    n = next(_n)
    org = OrganizationModel(provider_id=f"live-org-{n}")
    async_session.add(org)
    await async_session.flush()
    user = UserModel(provider_id=f"live-user-{n}", selected_organization_id=org.id)
    async_session.add(user)
    await async_session.flush()
    wf = WorkflowModel(name=name, organization_id=org.id, user_id=user.id)
    async_session.add(wf)
    await async_session.flush()
    return org, wf


async def _run(async_session, wf, *, state="running", age_seconds=30, ctx=None):
    run = WorkflowRunModel(
        name=f"run-{next(_n)}",
        workflow_id=wf.id,
        mode="twilio",
        state=state,
        initial_context=ctx or {},
        created_at=datetime.now(UTC) - timedelta(seconds=age_seconds),
    )
    async_session.add(run)
    await async_session.flush()
    return run


@pytest.mark.asyncio
async def test_only_running_recent_runs_of_this_organization(db_session, async_session):
    org_a, wf_a = await _org_with_agent(async_session, "Sales")
    org_b, wf_b = await _org_with_agent(async_session, "Other")
    live = await _run(async_session, wf_a, ctx={"caller_number": "+971501234567"})
    await _run(async_session, wf_b)  # a different organization's live call
    await _run(async_session, wf_a, age_seconds=7200)  # running, but long dead
    await _run(async_session, wf_a, state=WorkflowRunState.COMPLETED.value)
    await _run(async_session, wf_a, state=WorkflowRunState.INITIALIZED.value)

    rows = await db_session.get_live_workflow_runs(org_a.id)

    assert [r["id"] for r in rows] == [live.id]
    assert rows[0]["workflow_name"] == "Sales"
    assert rows[0]["initial_context"]["caller_number"] == "+971501234567"


@pytest.mark.asyncio
async def test_newest_first_and_limited(db_session, async_session):
    org, wf = await _org_with_agent(async_session)
    older = await _run(async_session, wf, age_seconds=300)
    newer = await _run(async_session, wf, age_seconds=10)

    rows = await db_session.get_live_workflow_runs(org.id)
    assert [r["id"] for r in rows] == [newer.id, older.id]
    assert [r["id"] for r in await db_session.get_live_workflow_runs(org.id, limit=1)] == [newer.id]
