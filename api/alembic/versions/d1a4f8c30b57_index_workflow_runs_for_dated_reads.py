"""index workflow_runs for date-ranged reads, and webhook_deliveries by org

Every org-scoped reporting read joins WorkflowModel on organization_id and then
bounds created_at (api/db/organization_usage_client.py, api/db/reports_client.py),
and the per-agent run history sorts on the same pair. workflow_runs has an index
on workflow_id alone, so those queries get the rows for an agent and then sort
and discard by date in memory. It is the largest table in the schema, so that
cost grows with total history rather than with the window being asked for.

webhook_deliveries has indexes on scheduled_for, workflow_run_id and the
run/node unique constraint -- nothing on organization_id at all, which is the
column the alerts feed counts by.

BUILT CONCURRENTLY, and that is the point of this migration rather than a
detail. A plain CREATE INDEX takes an ACCESS EXCLUSIVE lock for the whole build;
on the biggest table in the schema that blocks every insert for the duration,
and inserts on workflow_runs happen on the call path. Since migrations run
inside the api container's CMD before uvicorn starts
(scripts/start_services_docker.sh), a long lock here is a deploy that stalls
with live calls in flight.

CONCURRENTLY cannot run inside a transaction, hence autocommit_block(). The
trade-off is that a concurrent build can fail and leave an INVALID index behind
rather than rolling back; IF NOT EXISTS on the way up and IF EXISTS on the way
down keep a re-run from erroring, and an invalid index has to be dropped by hand
(the downgrade does that).

Revision ID: d1a4f8c30b57
Revises: c9e3a71f4d20
Create Date: 2026-09-09 12:05:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "d1a4f8c30b57"
down_revision: Union[str, None] = "c9e3a71f4d20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (name, table, DDL column list)
INDEXES = (
    # The load-bearing one: agent-scoped reads bounded and sorted by date.
    (
        "idx_workflow_runs_workflow_created",
        "workflow_runs",
        "(workflow_id, created_at DESC)",
    ),
    # The org-agnostic superadmin listing default-sorts created_at desc with no
    # workflow predicate, so the composite above cannot serve it.
    ("idx_workflow_runs_created_at", "workflow_runs", "(created_at DESC)"),
    (
        "idx_webhook_deliveries_org_status",
        "webhook_deliveries",
        "(organization_id, status)",
    ),
)


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for name, table, columns in INDEXES:
            op.execute(
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {table} {columns}"
            )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for name, _table, _columns in reversed(INDEXES):
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
