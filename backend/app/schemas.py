"""Pydantic request/response models."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

RollNo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
PersonName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
CourseName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
CategoryCode = Literal["General", "OBC", "SC", "ST"]
ReservedCategoryCode = Literal["OBC", "SC", "ST"]


# ---------- Auth ----------
class LoginRequest(BaseModel):
    email: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=255)]
    password: Annotated[str, StringConstraints(min_length=1, max_length=256)]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    full_name: str
    role: str


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserOut


# ---------- Meta ----------
class DemoAccount(BaseModel):
    email: str
    password: str
    role: str


class MetaOut(BaseModel):
    version: str
    environment: str
    demo_mode: bool
    llm_provider: str
    llm_model: str | None
    demo_accounts: list[DemoAccount]


# ---------- Categories ----------
class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str


# ---------- Students ----------
class PreferenceIn(BaseModel):
    course_id: int
    priority: int = Field(ge=1, le=3)


class StudentCreate(BaseModel):
    roll_no: RollNo
    name: PersonName
    marks: float = Field(ge=0, le=100)
    category_code: CategoryCode
    application_date: date | None = None
    preferences: list[PreferenceIn] = Field(default_factory=list, max_length=3)


class StudentUpdate(BaseModel):
    name: PersonName | None = None
    marks: float | None = Field(default=None, ge=0, le=100)
    category_code: CategoryCode | None = None
    application_date: date | None = None
    preferences: list[PreferenceIn] | None = Field(default=None, max_length=3)


class PreferenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    course_id: int
    priority: int


class StudentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    roll_no: str
    name: str
    marks: float
    category: CategoryOut
    application_date: date
    preferences: list[PreferenceOut]


class ImportRowError(BaseModel):
    row: int  # 1-based line number in the CSV, counting the header as line 1
    message: str


class ImportResult(BaseModel):
    created: int


# ---------- Courses ----------
class QuotaIn(BaseModel):
    category_code: ReservedCategoryCode
    reserved_seats: int = Field(ge=0, le=10_000)


class CourseCreate(BaseModel):
    name: CourseName
    total_seats: int = Field(ge=0, le=10_000)
    quotas: list[QuotaIn] = Field(default_factory=list, max_length=3)


class CourseUpdate(BaseModel):
    name: CourseName | None = None
    total_seats: int | None = Field(default=None, ge=0, le=10_000)
    quotas: list[QuotaIn] | None = Field(default=None, max_length=3)


class QuotaOut(BaseModel):
    category_code: str
    reserved_seats: int


class CourseOut(BaseModel):
    id: int
    name: str
    total_seats: int
    open_seats: int
    applicants: int
    quotas: list[QuotaOut]


# ---------- Allocations ----------
class AllocationOut(BaseModel):
    student_id: int
    roll_no: str
    student_name: str
    marks: float
    category_code: str
    course_id: int
    course_name: str
    seat_type: str
    preference_rank: int


class UnallocatedStudentOut(BaseModel):
    student_id: int
    roll_no: str
    student_name: str
    marks: float
    category_code: str
    preferences: list[str]  # course names in priority order


class AllocationRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    run_at: datetime
    total_students: int
    allocated: int
    triggered_by: str | None


class AllocationRunResult(BaseModel):
    total_students: int
    allocated: int
    unallocated: int
    run: AllocationRunOut
    allocations: list[AllocationOut]


# ---------- Dashboard ----------
class CourseStat(BaseModel):
    course_id: int
    course_name: str
    total_seats: int
    allocated: int
    available_seats: int
    applicants: int
    rejection_rate: float  # fraction 0..1


class CategoryStat(BaseModel):
    category_code: str
    students: int
    allocated: int


class PreferenceStat(BaseModel):
    preference_rank: int
    allocated: int


class SeatTypeStat(BaseModel):
    seat_type: str
    allocated: int


class DashboardStats(BaseModel):
    total_students: int
    total_courses: int
    total_seats: int
    total_allocated: int
    total_unallocated: int
    allocation_rate: float  # fraction 0..1 of students allocated
    seat_fill_rate: float  # fraction 0..1 of seats filled
    course_stats: list[CourseStat]
    category_stats: list[CategoryStat]
    preference_stats: list[PreferenceStat]
    seat_type_stats: list[SeatTypeStat]
    highest_rejection_course: str | None
    last_run: AllocationRunOut | None


# ---------- AI Assistant ----------
class AssistantQuery(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class AssistantResponse(BaseModel):
    question: str
    sql: str | None
    columns: list[str]
    rows: list[dict]
    truncated: bool
    answer: str
    source: Literal["llm", "fallback", "none"]
