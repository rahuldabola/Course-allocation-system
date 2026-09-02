"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-02

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
        sa.UniqueConstraint("code", name="uq_categories_code"),
    )

    op.create_table(
        "courses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("total_seats", sa.Integer(), nullable=False),
        sa.UniqueConstraint("name", name="uq_courses_name"),
        sa.CheckConstraint("total_seats >= 0", name="ck_total_seats"),
    )

    op.create_table(
        "students",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("roll_no", sa.String(30), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("marks", sa.Float(), nullable=False),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id"), nullable=False),
        sa.Column("application_date", sa.Date(), nullable=False),
        sa.UniqueConstraint("roll_no", name="uq_students_roll_no"),
        sa.CheckConstraint("marks >= 0 AND marks <= 100", name="ck_marks_range"),
    )

    op.create_table(
        "course_quotas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id"), nullable=False),
        sa.Column("reserved_seats", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("course_id", "category_id", name="uq_course_category"),
        sa.CheckConstraint("reserved_seats >= 0", name="ck_reserved_seats"),
    )

    op.create_table(
        "preferences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id"), nullable=False),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.UniqueConstraint("student_id", "priority", name="uq_student_priority"),
        sa.UniqueConstraint("student_id", "course_id", name="uq_student_course"),
        sa.CheckConstraint("priority >= 1 AND priority <= 3", name="ck_priority_range"),
    )

    op.create_table(
        "allocations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id"), nullable=False),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("seat_type", sa.String(10), nullable=False),
        sa.Column("preference_rank", sa.Integer(), nullable=False),
        sa.Column("allocated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("student_id", name="uq_allocations_student_id"),
    )


def downgrade() -> None:
    op.drop_table("allocations")
    op.drop_table("preferences")
    op.drop_table("course_quotas")
    op.drop_table("students")
    op.drop_table("courses")
    op.drop_table("categories")
