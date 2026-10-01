"""The purge deletes only what somebody gave a deadline, and only after the
stored objects are really gone."""

import itertools
from datetime import UTC, datetime, timedelta

import pytest

from api.db.models import (
    OrganizationModel,
    UserModel,
    WorkflowModel,
    WorkflowRunModel,
)
from api.tasks import data_retention

_n = itertools.count()
NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
PAST = NOW - timedelta(days=1)
FUTURE = NOW + timedelta(days=1)


class FakeStorage:
    """Records deletes; can be told to fail for chosen keys."""

    def __init__(self, fail=()):
        self.deleted = []
        self.fail = set(fail)

    async def adelete_file(self, key):
        if key in self.fail:
            return False
        self.deleted.append(key)
        return True


@pytest.fixture
def storage(monkeypatch):
    fs = FakeStorage()
    monkeypatch.setattr(data_retention, "get_storage_for_backend", lambda backend: fs)
    return fs


async def _workflow(async_session):
    n = next(_n)
    org = OrganizationModel(provider_id=f"purge-org-{n}")
    async_session.add(org)
    await async_session.flush()
    user = UserModel(provider_id=f"purge-user-{n}", selected_organization_id=org.id)
    async_session.add(user)
    await async_session.flush()
    wf = WorkflowModel(name="p", organization_id=org.id, user_id=user.id)
    async_session.add(wf)
    await async_session.flush()
    return wf


async def _run(async_session, wf, *, deadline, **kw):
    run = WorkflowRunModel(
        workflow_id=wf.id,
        name="r",
        mode="voice",
        is_completed=True,
        storage_backend="minio",
        retention_expires_at=deadline,
        recording_url=f"recordings/{next(_n)}.wav",
        transcript_url=f"transcripts/{next(_n)}.txt",
        extra={
            "recordings": {
                "user": {"storage_key": f"recordings/{next(_n)}/user.wav", "storage_backend": "minio"},
                "bot": {"storage_key": f"recordings/{next(_n)}/bot.wav", "storage_backend": "minio"},
            }
        },
        logs={"realtime_feedback_events": [{"text": "my card is 4111"}], "keep": 1},
        gathered_context={"name": "Sam"},
        initial_context={"phone": "+1555"},
        usage_info={"call_duration_seconds": 42},
        cost_info={"total_cost_usd": 0.5},
        public_access_token=f"tok-{next(_n)}",
        **kw,
    )
    async_session.add(run)
    await async_session.flush()
    return run


async def _purge(monkeypatch):
    class _Now(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr(data_retention, "datetime", _Now)
    await data_retention.purge_expired_workflow_runs({})


@pytest.mark.asyncio
async def test_an_expired_run_loses_its_content_but_keeps_its_numbers(
    db_session, async_session, storage, monkeypatch
):
    wf = await _workflow(async_session)
    run = await _run(async_session, wf, deadline=PAST)
    keys = {run.recording_url, run.transcript_url, *(r["storage_key"] for r in run.extra["recordings"].values())}

    await _purge(monkeypatch)
    await async_session.refresh(run)

    assert set(storage.deleted) == keys
    assert run.recording_url is None and run.transcript_url is None
    assert "recordings" not in run.extra
    assert "realtime_feedback_events" not in run.logs
    assert run.logs["keep"] == 1  # only the transcript-bearing key goes
    assert run.public_access_token is None
    assert run.purged_at is not None
    # Reports and cost figures must not change retroactively.
    assert run.usage_info == {"call_duration_seconds": 42}
    assert run.cost_info == {"total_cost_usd": 0.5}
    # Not basic_only, so the contexts stay (they feed integrations).
    assert run.gathered_context == {"name": "Sam"}


@pytest.mark.asyncio
async def test_a_run_with_no_deadline_is_never_touched(db_session, async_session, storage, monkeypatch):
    """The standing decision: a missing date means never purge."""
    wf = await _workflow(async_session)
    run = await _run(async_session, wf, deadline=None)

    await _purge(monkeypatch)
    await async_session.refresh(run)

    assert storage.deleted == []
    assert run.recording_url is not None and run.purged_at is None


@pytest.mark.asyncio
async def test_a_run_not_yet_due_is_left_alone(db_session, async_session, storage, monkeypatch):
    wf = await _workflow(async_session)
    run = await _run(async_session, wf, deadline=FUTURE)

    await _purge(monkeypatch)
    await async_session.refresh(run)

    assert storage.deleted == [] and run.purged_at is None


@pytest.mark.asyncio
async def test_a_failed_delete_leaves_the_run_whole_so_it_is_retried(
    db_session, async_session, storage, monkeypatch
):
    """Clearing the pointers first would orphan the objects with nothing left
    that knows their keys."""
    wf = await _workflow(async_session)
    run = await _run(async_session, wf, deadline=PAST)
    storage.fail = {run.transcript_url}

    await _purge(monkeypatch)
    await async_session.refresh(run)

    assert run.purged_at is None
    assert run.recording_url is not None and "recordings" in run.extra
    assert "realtime_feedback_events" in run.logs

    storage.fail = set()  # storage recovers; tomorrow's pass finishes the job
    await _purge(monkeypatch)
    await async_session.refresh(run)
    assert run.purged_at is not None


@pytest.mark.asyncio
async def test_basic_only_also_clears_the_context(db_session, async_session, storage, monkeypatch):
    wf = await _workflow(async_session)
    run = await _run(
        async_session, wf, deadline=PAST
    )
    run.extra = {**run.extra, "governance": {"storage_mode": "basic_only", "retention_days": 1}}
    await async_session.flush()

    await _purge(monkeypatch)
    await async_session.refresh(run)

    assert run.gathered_context == {} and run.initial_context == {}


@pytest.mark.asyncio
async def test_one_bad_run_does_not_strand_the_rest(db_session, async_session, storage, monkeypatch):
    wf = await _workflow(async_session)
    bad = await _run(async_session, wf, deadline=PAST)
    good = await _run(async_session, wf, deadline=PAST)
    storage.fail = {bad.recording_url}

    await _purge(monkeypatch)
    await async_session.refresh(bad)
    await async_session.refresh(good)

    assert bad.purged_at is None
    assert good.purged_at is not None


@pytest.mark.asyncio
async def test_a_second_pass_does_nothing(db_session, async_session, storage, monkeypatch):
    wf = await _workflow(async_session)
    await _run(async_session, wf, deadline=PAST)

    await _purge(monkeypatch)
    first = list(storage.deleted)
    await _purge(monkeypatch)

    assert storage.deleted == first
