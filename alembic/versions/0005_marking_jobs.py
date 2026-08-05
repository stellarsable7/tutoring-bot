"""Persist marking job results and media lifecycle state."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_marking_jobs"
down_revision: str | None = "0004_submissions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("submission_attempts", sa.Column("result_total", sa.Integer(), nullable=True))
    op.add_column("submission_attempts", sa.Column("result_maximum", sa.Integer(), nullable=True))
    op.add_column("submission_attempts", sa.Column("feedback", sa.JSON(), nullable=True))
    op.add_column("submission_attempts", sa.Column("review_reasons", sa.JSON(), nullable=True))
    op.add_column(
        "submission_attempts", sa.Column("media_expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "submission_attempts", sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "submission_attempts", sa.Column("media_deleted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "submission_attempts", sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("submission_attempts", "notified_at")
    op.drop_column("submission_attempts", "media_deleted_at")
    op.drop_column("submission_attempts", "finalized_at")
    op.drop_column("submission_attempts", "media_expires_at")
    op.drop_column("submission_attempts", "review_reasons")
    op.drop_column("submission_attempts", "feedback")
    op.drop_column("submission_attempts", "result_maximum")
    op.drop_column("submission_attempts", "result_total")
