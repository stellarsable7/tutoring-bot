"""Store tutor-only, question-scoped published solution assets."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_solution_assets"
down_revision: str | None = "0010_question_assets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "source_questions", sa.Column("solution_asset_path", sa.String(500), nullable=True)
    )
    for question_number in range(1, 14):
        op.execute(
            sa.text(
                "UPDATE source_questions SET solution_asset_path = :path "
                "WHERE school = :school AND year = 2025 AND paper = '1' "
                "AND question_number = :question_number"
            ).bindparams(
                path=(
                    f"/app/data/solution_assets/"
                    f"sps-2025-p1-q{question_number}-solution.pdf"
                ),
                school="St. Patrick's School",
                question_number=str(question_number),
            )
        )


def downgrade() -> None:
    op.drop_column("source_questions", "solution_asset_path")
