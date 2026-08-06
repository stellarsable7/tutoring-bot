"""Allow schedules at any minute of the hour."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_schedule_minutes"
down_revision: str | None = "0008_timestamp_constraints"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "schedules",
        sa.Column("minute", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("schedules", "minute")
