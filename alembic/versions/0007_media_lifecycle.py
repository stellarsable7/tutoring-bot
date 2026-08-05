"""Track retry-safe deletion of temporary submission media."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_media_lifecycle"
down_revision: str | None = "0006_reviews"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "submission_attempts",
        sa.Column("media_delete_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "submission_attempts", sa.Column("media_delete_retry_at", sa.DateTime(timezone=True))
    )
    op.add_column("submission_attempts", sa.Column("media_delete_error", sa.String(500)))


def downgrade() -> None:
    op.drop_column("submission_attempts", "media_delete_error")
    op.drop_column("submission_attempts", "media_delete_retry_at")
    op.drop_column("submission_attempts", "media_delete_attempts")
