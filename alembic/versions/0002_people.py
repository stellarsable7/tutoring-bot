"""Create tutors, students, and single-use invites."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_people"
down_revision: str | None = "0001_catalogue"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tutors",
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("telegram_id", name="pk_tutors"),
    )
    op.create_table(
        "invites",
        sa.Column("code", sa.String(length=120), nullable=False),
        sa.Column("tutor_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["tutor_telegram_id"], ["tutors.telegram_id"], name="fk_invites_tutor_telegram_id_tutors"
        ),
        sa.PrimaryKeyConstraint("code", name="pk_invites"),
    )
    op.create_index("ix_invites_tutor_telegram_id", "invites", ["tutor_telegram_id"])
    op.create_table(
        "students",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("tutor_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("display_name", sa.String(length=240), nullable=False),
        sa.Column("syllabus_version", sa.String(length=40), nullable=False),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paused", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["tutor_telegram_id"], ["tutors.telegram_id"], name="fk_students_tutor_telegram_id_tutors"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_students"),
        sa.UniqueConstraint("telegram_id", name="uq_students_telegram_id"),
    )
    op.create_index("ix_students_tutor_telegram_id", "students", ["tutor_telegram_id"])


def downgrade() -> None:
    op.drop_index("ix_students_tutor_telegram_id", table_name="students")
    op.drop_table("students")
    op.drop_index("ix_invites_tutor_telegram_id", table_name="invites")
    op.drop_table("invites")
    op.drop_table("tutors")
