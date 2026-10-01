"""A run's retention deadline is fixed when it is created, from the policy then."""

import itertools
from datetime import timedelta

import pytest

from api.db.models import (
    OrganizationConfigurationModel,
    OrganizationModel,
    UserModel,
    WorkflowDefinitionModel,
    WorkflowModel,
)
from api.enums import OrganizationConfigurationKey

_n = itertools.count()


async def _setup(async_session, *, org_prefs=None, agent_config=None):
    n = next(_n)
    org = OrganizationModel(provider_id=f"ret-org-{n}")
    async_session.add(org)
    await async_session.flush()
    user = UserModel(provider_id=f"ret-user-{n}", selected_organization_id=org.id)
    async_session.add(user)
    await async_session.flush()
    workflow = WorkflowModel(name="ret", organization_id=org.id, user_id=user.id)
    async_session.add(workflow)
    await async_session.flush()
    definition = WorkflowDefinitionModel(
        workflow_id=workflow.id,
        workflow_json={},
        is_current=True,
        workflow_configurations=agent_config or {},
    )
    async_session.add(definition)
    if org_prefs is not None:
        async_session.add(
            OrganizationConfigurationModel(
                organization_id=org.id,
                key=OrganizationConfigurationKey.ORGANIZATION_PREFERENCES.value,
                value=org_prefs,
            )
        )
    await async_session.flush()
    return org, user, workflow, definition


async def _create(db, org, user, workflow, **kw):
    return await db.create_workflow_run(
        name="r",
        workflow_id=workflow.id,
        mode="voice",
        user_id=user.id,
        organization_id=org.id,
        **kw,
    )


@pytest.mark.asyncio
async def test_no_policy_means_no_deadline_and_an_untouched_extra(db_session, async_session):
    org, user, wf, _ = await _setup(async_session)
    run = await _create(db_session, org, user, wf)
    assert run.retention_expires_at is None
    assert run.extra == {}


@pytest.mark.asyncio
async def test_the_organization_default_stamps_a_deadline(db_session, async_session):
    org, user, wf, _ = await _setup(async_session, org_prefs={"data_retention_days": 30})
    run = await _create(db_session, org, user, wf)

    gap = run.retention_expires_at - run.created_at
    assert gap == timedelta(days=30)
    assert run.extra["governance"] == {"storage_mode": "everything", "retention_days": 30}
    assert run.purged_at is None


@pytest.mark.asyncio
async def test_the_agent_overrides_and_zero_means_forever(db_session, async_session):
    org, user, wf, _ = await _setup(
        async_session,
        org_prefs={"data_retention_days": 30},
        agent_config={"governance_configuration": {"retention_days": 7}},
    )
    run = await _create(db_session, org, user, wf)
    assert run.retention_expires_at - run.created_at == timedelta(days=7)

    org2, user2, wf2, _ = await _setup(
        async_session,
        org_prefs={"data_retention_days": 30},
        agent_config={"governance_configuration": {"retention_days": 0}},
    )
    forever = await _create(db_session, org2, user2, wf2)
    assert forever.retention_expires_at is None


@pytest.mark.asyncio
async def test_a_pinned_version_decides_not_the_current_one(db_session, async_session):
    """A run is governed by the version it runs, so editing the agent later does
    not change what an in-flight or historic run is held to."""
    org, user, wf, current = await _setup(
        async_session,
        agent_config={"governance_configuration": {"retention_days": 5}},
    )
    older = WorkflowDefinitionModel(
        workflow_id=wf.id,
        workflow_json={},
        is_current=False,
        workflow_configurations={"governance_configuration": {"retention_days": 90}},
    )
    async_session.add(older)
    await async_session.flush()

    pinned = await _create(db_session, org, user, wf, definition_id=older.id)
    assert pinned.retention_expires_at - pinned.created_at == timedelta(days=90)
    default = await _create(db_session, org, user, wf)
    assert default.retention_expires_at - default.created_at == timedelta(days=5)


@pytest.mark.asyncio
async def test_basic_only_is_recorded_even_with_no_deadline(db_session, async_session):
    """The purge reads the mode off the run, so it has to be written even when
    there is no retention window yet."""
    org, user, wf, _ = await _setup(
        async_session,
        agent_config={"governance_configuration": {"storage_mode": "basic_only"}},
    )
    run = await _create(db_session, org, user, wf)
    assert run.retention_expires_at is None
    assert run.extra["governance"]["storage_mode"] == "basic_only"


@pytest.mark.asyncio
async def test_a_policy_change_does_not_re_age_existing_runs(db_session, async_session):
    org, user, wf, definition = await _setup(
        async_session, org_prefs={"data_retention_days": 30}
    )
    run = await _create(db_session, org, user, wf)
    stamped = run.retention_expires_at

    definition.workflow_configurations = {
        "governance_configuration": {"retention_days": 1}
    }
    await async_session.flush()

    assert run.retention_expires_at == stamped


@pytest.mark.asyncio
async def test_a_broken_policy_never_stops_a_call_being_created(db_session, async_session):
    org, user, wf, _ = await _setup(
        async_session,
        org_prefs={"data_retention_days": "not a number"},
        agent_config={"governance_configuration": "garbage"},
    )
    run = await _create(db_session, org, user, wf)
    assert run.id is not None
    assert run.retention_expires_at is None
