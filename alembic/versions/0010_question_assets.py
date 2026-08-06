"""Support question-only delivery assets."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_question_assets"
down_revision: str | None = "0009_schedule_minutes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("source_questions", sa.Column("asset_path", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("source_questions", "asset_path")
