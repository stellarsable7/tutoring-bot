"""Align required timestamp constraints with ORM models."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_timestamp_constraints"
down_revision: str | None = "0007_media_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    ("invites", "created_at"),
    ("marking_reviews", "created_at"),
    ("source_questions", "created_at"),
    ("source_questions", "updated_at"),
    ("students", "created_at"),
    ("submission_attempts", "created_at"),
    ("tutors", "created_at"),
)


def upgrade() -> None:
    for table, column in _COLUMNS:
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                column,
                existing_type=sa.DateTime(timezone=True),
                nullable=False,
            )


def downgrade() -> None:
    for table, column in reversed(_COLUMNS):
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                column,
                existing_type=sa.DateTime(timezone=True),
                nullable=True,
            )
