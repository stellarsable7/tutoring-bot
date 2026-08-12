"""Persist OCR validation diagnostics and symbolic verification."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014_ocr_diagnostics"
down_revision: str | None = "0013_persist_ocr_stage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("submission_attempts", sa.Column("ocr_raw_response", sa.Text(), nullable=True))
    op.add_column(
        "submission_attempts", sa.Column("ocr_validation_error", sa.Text(), nullable=True)
    )
    op.add_column("submission_attempts", sa.Column("ocr_verification", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("submission_attempts") as batch:
        batch.drop_column("ocr_verification")
        batch.drop_column("ocr_validation_error")
        batch.drop_column("ocr_raw_response")
