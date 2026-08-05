"""Persist marking decisions and immutable tutor reviews."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_reviews"
down_revision: str | None = "0005_marking_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("submission_attempts", sa.Column("grade_decisions", sa.JSON(), nullable=True))
    op.create_table(
        "marking_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("attempt_id", sa.Integer(), nullable=False),
        sa.Column("tutor_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("original_total", sa.Integer(), nullable=False),
        sa.Column("final_total", sa.Integer(), nullable=True),
        sa.Column("original_decisions", sa.JSON(), nullable=False),
        sa.Column("final_decisions", sa.JSON(), nullable=False),
        sa.Column("original_feedback", sa.JSON(), nullable=False),
        sa.Column("final_feedback", sa.JSON(), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["submission_attempts.id"],
            name="fk_marking_reviews_attempt_id_submission_attempts",
        ),
        sa.ForeignKeyConstraint(
            ["tutor_id"], ["tutors.telegram_id"], name="fk_marking_reviews_tutor_id_tutors"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_marking_reviews"),
    )
    op.create_index("ix_marking_reviews_attempt_id", "marking_reviews", ["attempt_id"])


def downgrade() -> None:
    op.drop_index("ix_marking_reviews_attempt_id", table_name="marking_reviews")
    op.drop_table("marking_reviews")
    op.drop_column("submission_attempts", "grade_decisions")
