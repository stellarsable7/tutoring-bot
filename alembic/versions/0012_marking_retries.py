"""Persist marking retry state on submission attempts."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012_marking_retries"
down_revision: str | None = "0011_solution_assets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "submission_attempts",
        sa.Column(
            "marking_attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "submission_attempts",
        sa.Column("marking_retry_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "submission_attempts",
        sa.Column("marking_last_error", sa.String(length=500), nullable=True),
    )
    with op.batch_alter_table("submission_attempts") as batch:
        batch.create_check_constraint(
            op.f("ck_submission_attempts_marking_attempts_nonnegative"),
            "marking_attempts >= 0",
        )
    op.create_index(
        "ix_submission_attempts_marking_retry_at",
        "submission_attempts",
        ["marking_retry_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_submission_attempts_marking_retry_at", table_name="submission_attempts"
    )
    with op.batch_alter_table("submission_attempts") as batch:
        batch.drop_constraint(
            op.f("ck_submission_attempts_marking_attempts_nonnegative"), type_="check"
        )
        batch.drop_column("marking_last_error")
        batch.drop_column("marking_retry_at")
        batch.drop_column("marking_attempts")
