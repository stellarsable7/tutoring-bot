"""Create grouped submission attempts and ordered media."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_submissions"
down_revision: str | None = "0003_assignments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "submission_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("assignment_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["assignment_id"], ["assignments.id"], name="fk_submission_attempts_assignment_id_assignments"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_submission_attempts"),
    )
    op.create_index("ix_submission_attempts_assignment_id", "submission_attempts", ["assignment_id"])
    op.create_index("ix_submission_attempts_status", "submission_attempts", ["status"])
    op.create_table(
        "submission_media",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("attempt_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("telegram_file_id", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("media_kind", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["submission_attempts.id"],
            name="fk_submission_media_attempt_id_submission_attempts",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_submission_media"),
        sa.UniqueConstraint("attempt_id", "position", name="uq_submission_media_position"),
    )
    op.create_index("ix_submission_media_attempt_id", "submission_media", ["attempt_id"])


def downgrade() -> None:
    op.drop_index("ix_submission_media_attempt_id", table_name="submission_media")
    op.drop_table("submission_media")
    op.drop_index("ix_submission_attempts_status", table_name="submission_attempts")
    op.drop_index("ix_submission_attempts_assignment_id", table_name="submission_attempts")
    op.drop_table("submission_attempts")
