"""users, allocation run history, and foreign-key indexes

Revision ID: 0002_users_runs_indexes
Revises: 0001_initial
Create Date: 2026-09-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_users_runs_indexes"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.CheckConstraint("role IN ('admin', 'viewer')", name="ck_user_role"),
    )

    op.create_table(
        "allocation_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("total_students", sa.Integer(), nullable=False),
        sa.Column("allocated", sa.Integer(), nullable=False),
        sa.Column("triggered_by", sa.String(255), nullable=True),
    )

    # Postgres doesn't index foreign-key columns automatically; these back the
    # dashboard's per-course/per-category aggregations and ON-join lookups.
    op.create_index("ix_students_category_id", "students", ["category_id"])
    op.create_index("ix_preferences_course_id", "preferences", ["course_id"])
    op.create_index("ix_allocations_course_id", "allocations", ["course_id"])


def downgrade() -> None:
    op.drop_index("ix_allocations_course_id", table_name="allocations")
    op.drop_index("ix_preferences_course_id", table_name="preferences")
    op.drop_index("ix_students_category_id", table_name="students")
    op.drop_table("allocation_runs")
    op.drop_table("users")
