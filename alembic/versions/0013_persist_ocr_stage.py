"""Persist OCR separately from provisional grading."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013_persist_ocr_stage"
down_revision: str | None = "0012_marking_retries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("submission_attempts", sa.Column("ocr_transcription", sa.JSON(), nullable=True))
    op.add_column("submission_attempts", sa.Column("ocr_unclear", sa.JSON(), nullable=True))
    op.add_column("submission_attempts", sa.Column("ocr_confidence", sa.Float(), nullable=True))
    op.add_column("submission_attempts", sa.Column("ocr_complete", sa.Boolean(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("submission_attempts") as batch:
        batch.drop_column("ocr_complete")
        batch.drop_column("ocr_confidence")
        batch.drop_column("ocr_unclear")
        batch.drop_column("ocr_transcription")
