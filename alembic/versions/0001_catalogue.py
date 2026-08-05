"""Create source question catalogue."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_catalogue"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_questions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=False),
        sa.Column("solution_url", sa.String(length=2048), nullable=True),
        sa.Column("provider", sa.String(length=120), nullable=False),
        sa.Column("school", sa.String(length=240), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("paper", sa.String(length=40), nullable=False),
        sa.Column("question_number", sa.String(length=40), nullable=False),
        sa.Column("syllabus_version", sa.String(length=40), nullable=False),
        sa.Column("objective_codes", sa.JSON(), nullable=False),
        sa.Column("marks", sa.Integer(), nullable=False),
        sa.Column("solution_kind", sa.String(length=40), nullable=True),
        sa.Column("marking_steps", sa.JSON(), nullable=False),
        sa.Column("tutor_validated", sa.Boolean(), nullable=False),
        sa.Column("eligible", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_source_questions"),
        sa.UniqueConstraint(
            "provider",
            "school",
            "year",
            "paper",
            "question_number",
            name="uq_source_identity",
        ),
    )
    op.create_index("ix_source_questions_eligible", "source_questions", ["eligible"])
    op.create_index(
        "ix_source_questions_syllabus_version", "source_questions", ["syllabus_version"]
    )


def downgrade() -> None:
    op.drop_index("ix_source_questions_syllabus_version", table_name="source_questions")
    op.drop_index("ix_source_questions_eligible", table_name="source_questions")
    op.drop_table("source_questions")
