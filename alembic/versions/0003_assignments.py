"""Create schedules and assignments."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_assignments"
down_revision: str | None = "0002_people"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "schedules",
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("weekdays", sa.JSON(), nullable=False),
        sa.Column("hour", sa.Integer(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("timezone", sa.String(length=80), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], name="fk_schedules_student_id_students"),
        sa.PrimaryKeyConstraint("student_id", name="pk_schedules"),
    )
    op.create_table(
        "assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("source_question_id", sa.Integer(), nullable=False),
        sa.Column("scheduled_date", sa.Date(), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("delivery_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("selection_reason", sa.String(length=500), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_question_id"],
            ["source_questions.id"],
            name="fk_assignments_source_question_id_source_questions",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"], ["students.id"], name="fk_assignments_student_id_students"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_assignments"),
        sa.UniqueConstraint(
            "student_id", "scheduled_date", "sequence_number", name="uq_assignment_daily_sequence"
        ),
    )
    op.create_index("ix_assignments_status", "assignments", ["status"])
    op.create_index("ix_assignments_student_id", "assignments", ["student_id"])


def downgrade() -> None:
    op.drop_index("ix_assignments_student_id", table_name="assignments")
    op.drop_index("ix_assignments_status", table_name="assignments")
    op.drop_table("assignments")
    op.drop_table("schedules")
