"""Normalized (3NF) ORM schema for the course allocation system."""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)  # General/OBC/SC/ST
    name: Mapped[str] = mapped_column(String(50), nullable=False)

    students: Mapped[list["Student"]] = relationship(back_populates="category")
    quotas: Mapped[list["CourseQuota"]] = relationship(back_populates="category")


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # external Student ID
    roll_no: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    marks: Mapped[float] = mapped_column(nullable=False)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id"), nullable=False, index=True
    )
    application_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)

    category: Mapped["Category"] = relationship(back_populates="students")
    preferences: Mapped[list["Preference"]] = relationship(
        back_populates="student", cascade="all, delete-orphan", order_by="Preference.priority"
    )
    allocation: Mapped["Allocation"] = relationship(
        back_populates="student", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (CheckConstraint("marks >= 0 AND marks <= 100", name="ck_marks_range"),)


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    total_seats: Mapped[int] = mapped_column(Integer, nullable=False)

    quotas: Mapped[list["CourseQuota"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    preferences: Mapped[list["Preference"]] = relationship(back_populates="course")
    allocations: Mapped[list["Allocation"]] = relationship(back_populates="course")

    __table_args__ = (CheckConstraint("total_seats >= 0", name="ck_total_seats"),)


class CourseQuota(Base):
    """Reserved seats for a category within a course. Open seats = total - sum(reserved)."""

    __tablename__ = "course_quotas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)
    reserved_seats: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    course: Mapped["Course"] = relationship(back_populates="quotas")
    category: Mapped["Category"] = relationship(back_populates="quotas")

    __table_args__ = (
        UniqueConstraint("course_id", "category_id", name="uq_course_category"),
        CheckConstraint("reserved_seats >= 0", name="ck_reserved_seats"),
    )


class Preference(Base):
    __tablename__ = "preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False, index=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)  # 1, 2, 3

    student: Mapped["Student"] = relationship(back_populates="preferences")
    course: Mapped["Course"] = relationship(back_populates="preferences")

    __table_args__ = (
        UniqueConstraint("student_id", "priority", name="uq_student_priority"),
        UniqueConstraint("student_id", "course_id", name="uq_student_course"),
        CheckConstraint("priority >= 1 AND priority <= 3", name="ck_priority_range"),
    )


class Allocation(Base):
    """One row per allocated student. Unique student_id => a student gets at most one course."""

    __tablename__ = "allocations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), unique=True, nullable=False)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False, index=True)
    seat_type: Mapped[str] = mapped_column(String(10), nullable=False)  # 'open' or 'reserved'
    preference_rank: Mapped[int] = mapped_column(Integer, nullable=False)  # which preference (1-3)
    allocated_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())

    student: Mapped["Student"] = relationship(back_populates="allocation")
    course: Mapped["Course"] = relationship(back_populates="allocations")


class AllocationRun(Base):
    """Audit trail: one row per execution of the allocation engine."""

    __tablename__ = "allocation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    total_students: Mapped[int] = mapped_column(Integer, nullable=False)
    allocated: Mapped[int] = mapped_column(Integer, nullable=False)
    triggered_by: Mapped[str | None] = mapped_column(String(255))  # user email


class User(Base):
    """An operator account. Roles: 'admin' (full access) or 'viewer' (read-only + assistant)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (CheckConstraint("role IN ('admin', 'viewer')", name="ck_user_role"),)
