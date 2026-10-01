"""Delete what a run captured once its retention deadline has passed.

Modelled on sweep_webhook_deliveries: page by run id with a fixed page size, so a
large backlog (the first run after a policy is set) drains without loading it all.

The order inside one run matters. Stored objects go FIRST; only when every one is
confirmed gone are the database pointers cleared and the run marked purged. If a
delete fails, the run is left untouched and is retried tomorrow -- clearing the
pointers first would orphan the objects with nothing left that knows their keys.
Deletes are idempotent (a missing key is success), so a retry after a half-done
run cannot fail on the part that already worked.

Only runs somebody gave a deadline are ever touched: retention_expires_at is NULL
for everything else, and a NULL deadline is never selected.
"""

from datetime import UTC, datetime

from loguru import logger

from api.db import db_client
from api.services.storage import get_storage_for_backend
from api.utils.recording_artifacts import (
    get_recording_storage_backend,
    get_recording_storage_key,
)

PAGE_SIZE = 100
TRACKS = ("mixed", "user", "bot")


def artifact_refs(run) -> set[tuple[str, str]]:
    """Every (backend, key) a run has in object storage."""
    default_backend = run.storage_backend
    refs: set[tuple[str, str]] = set()
    for key in (run.recording_url, run.transcript_url):
        if key:
            refs.add((default_backend, key))
    for track in TRACKS:
        key = get_recording_storage_key(run.extra, track)
        if key:
            backend = get_recording_storage_backend(run.extra, track) or default_backend
            refs.add((backend, key))
    return refs


async def _purge_run(run, now: datetime) -> bool:
    for backend, key in sorted(artifact_refs(run)):
        if not await get_storage_for_backend(backend).adelete_file(key):
            logger.error(
                f"Retention purge: could not delete {key} ({backend}) for run "
                f"{run.id}; leaving the run for the next pass"
            )
            return False

    governance = (run.extra or {}).get("governance") or {}
    return await db_client.delete_run_artifacts(
        run.id, clear_context=governance.get("storage_mode") == "basic_only", now=now
    )


async def purge_expired_workflow_runs(_ctx) -> None:
    now = datetime.now(UTC)
    after_id = 0
    purged = failed = 0
    while True:
        runs = await db_client.get_runs_due_for_purge(
            now=now, limit=PAGE_SIZE, after_id=after_id
        )
        if not runs:
            break
        for run in runs:
            try:
                ok = await _purge_run(run, now)
            except Exception as exc:
                # One bad run must not strand the rest of the page.
                logger.error(f"Retention purge failed for run {run.id}: {exc}")
                ok = False
            purged += ok
            failed += not ok
        after_id = runs[-1].id
        if len(runs) < PAGE_SIZE:
            break

    if purged or failed:
        logger.info(f"Retention purge: {purged} purged, {failed} left for retry")
