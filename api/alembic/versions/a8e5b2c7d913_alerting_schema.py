"""alerting: channels, rules, events -- and webhook_deliveries made general

Three new tables, and one change to a table that is already carrying live traffic.

Alerts need exactly what webhook delivery already has: an atomic claim, backed-off
retries, a permanent-vs-transient split, dead-lettering and a sweeper. Building a
second copy would mean two retry loops to keep correct, so ``webhook_deliveries``
learns a second transport (email) and stops assuming every row is about one call to
one URL:

  * ``transport`` and ``destination`` say how the payload leaves;
  * ``workflow_run_id`` and ``endpoint_url`` become nullable (an alert about a window
    of calls has neither);
  * idempotency moves from (run, node) to ``(organization_id, idempotency_key)``.
    Existing rows are backfilled to ``run:<run id>:<node id>``, which is exactly what
    the producer now writes, so a retried run still finds its old row.

The old unique constraint is dropped only after the new key is filled and enforced, so
there is never a moment without dedupe. ``webhook_node_id`` stays, nullable, for
history.

Revision ID: a8e5b2c7d913
Revises: f4c8d1e9a2b7
Create Date: 2026-10-02 22:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a8e5b2c7d913"
down_revision: Union[str, None] = "f4c8d1e9a2b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _now():
    return sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "alert_channels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("channel_uuid", sa.String(36), nullable=False),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_now()),
        sa.UniqueConstraint("organization_id", "name", name="uq_alert_channels_org_name"),
    )
    op.create_index("ix_alert_channels_id", "alert_channels", ["id"])
    op.create_index("ix_alert_channels_channel_uuid", "alert_channels", ["channel_uuid"], unique=True)

    op.create_table(
        "alert_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rule_uuid", sa.String(36), nullable=False),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "scope_workflow_id",
            sa.Integer(),
            sa.ForeignKey("workflows.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("trigger", sa.String(16), nullable=False),
        sa.Column("metric", sa.String(64), nullable=False),
        sa.Column("comparator", sa.String(8), nullable=False, server_default="gt"),
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column("match_value", sa.String(), nullable=True),
        sa.Column("window_minutes", sa.Integer(), nullable=True),
        sa.Column("severity", sa.String(8), nullable=False, server_default="medium"),
        sa.Column("cooldown_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("channel_uuids", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("last_fired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_now()),
        sa.UniqueConstraint("organization_id", "name", name="uq_alert_rules_org_name"),
    )
    op.create_index("ix_alert_rules_id", "alert_rules", ["id"])
    op.create_index("ix_alert_rules_rule_uuid", "alert_rules", ["rule_uuid"], unique=True)
    op.create_index("idx_alert_rules_org_active", "alert_rules", ["organization_id", "is_active"])

    op.create_table(
        "alert_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_uuid", sa.String(36), nullable=False),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "alert_rule_id",
            sa.Integer(),
            sa.ForeignKey("alert_rules.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("severity", sa.String(8), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column(
            "workflow_run_id",
            sa.Integer(),
            sa.ForeignKey("workflow_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("observed_value", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now()),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "acknowledged_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_alert_events_id", "alert_events", ["id"])
    op.create_index("ix_alert_events_event_uuid", "alert_events", ["event_uuid"], unique=True)
    op.create_index(
        "idx_alert_events_org_created",
        "alert_events",
        ["organization_id", sa.text("created_at DESC")],
    )

    # -- webhook_deliveries, generalized ------------------------------------------
    op.add_column(
        "webhook_deliveries",
        sa.Column("transport", sa.String(16), nullable=False, server_default="http"),
    )
    op.add_column("webhook_deliveries", sa.Column("destination", sa.JSON(), nullable=True))
    op.add_column("webhook_deliveries", sa.Column("idempotency_key", sa.String(), nullable=True))
    op.execute(
        "UPDATE webhook_deliveries "
        "SET idempotency_key = 'run:' || workflow_run_id || ':' || webhook_node_id "
        "WHERE idempotency_key IS NULL"
    )
    op.alter_column("webhook_deliveries", "idempotency_key", nullable=False)
    # New key enforced before the old one goes, so dedupe never lapses.
    op.create_unique_constraint(
        "uq_webhook_deliveries_org_idempotency",
        "webhook_deliveries",
        ["organization_id", "idempotency_key"],
    )
    op.drop_constraint("uq_webhook_deliveries_run_node", "webhook_deliveries", type_="unique")
    op.alter_column("webhook_deliveries", "workflow_run_id", nullable=True)
    op.alter_column("webhook_deliveries", "endpoint_url", nullable=True)
    op.alter_column("webhook_deliveries", "webhook_node_id", nullable=True)


def downgrade() -> None:
    # Alert deliveries have no run, URL or node and cannot satisfy the old NOT NULLs.
    op.execute("DELETE FROM webhook_deliveries WHERE transport <> 'http' OR workflow_run_id IS NULL")
    op.execute(
        "UPDATE webhook_deliveries SET webhook_node_id = 'unknown' WHERE webhook_node_id IS NULL"
    )
    op.alter_column("webhook_deliveries", "webhook_node_id", nullable=False)
    op.alter_column("webhook_deliveries", "endpoint_url", nullable=False)
    op.alter_column("webhook_deliveries", "workflow_run_id", nullable=False)
    op.create_unique_constraint(
        "uq_webhook_deliveries_run_node",
        "webhook_deliveries",
        ["workflow_run_id", "webhook_node_id"],
    )
    op.drop_constraint("uq_webhook_deliveries_org_idempotency", "webhook_deliveries", type_="unique")
    op.drop_column("webhook_deliveries", "idempotency_key")
    op.drop_column("webhook_deliveries", "destination")
    op.drop_column("webhook_deliveries", "transport")

    op.drop_table("alert_events")
    op.drop_table("alert_rules")
    op.drop_table("alert_channels")
