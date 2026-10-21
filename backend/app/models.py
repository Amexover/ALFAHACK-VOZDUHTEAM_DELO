from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.enums import Status


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    full_name: Mapped[str] = mapped_column(String(200))
    first_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20))


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    legal_form: Mapped[str] = mapped_column(String(3))
    name: Mapped[str] = mapped_column(String(200))
    ogrn: Mapped[str] = mapped_column(String(15))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    owner: Mapped[User] = relationship()


class BureauRating(Base):
    """Хранилище симулятора скорингового бюро."""

    __tablename__ = "bureau_ratings"

    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), primary_key=True)
    score: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExistingLoan(Base):
    __tablename__ = "existing_loans"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    product_id: Mapped[str] = mapped_column(String(30))
    original_amount: Mapped[int] = mapped_column(Integer)
    balance: Mapped[int] = mapped_column(Integer)
    rate: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    next_payment_amount: Mapped[int] = mapped_column(Integer)
    next_payment_date: Mapped[date] = mapped_column(Date)


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str | None] = mapped_column(String(20), unique=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    borrowing_mode: Mapped[str] = mapped_column(String(20))
    product_id: Mapped[str | None] = mapped_column(String(30))
    existing_loan_id: Mapped[int | None] = mapped_column(ForeignKey("existing_loans.id"))
    amount: Mapped[int | None] = mapped_column(Integer)
    term_months: Mapped[int | None] = mapped_column(Integer)
    preliminary_rate: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    preliminary_payment: Mapped[int | None] = mapped_column(Integer)
    rating_based: Mapped[bool | None] = mapped_column(Boolean)
    rating_used: Mapped[int | None] = mapped_column(Integer)
    business_profile: Mapped[dict] = mapped_column(JSON, default=dict)
    current_step: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default=Status.DRAFT, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    company: Mapped[Company] = relationship()
    existing_loan: Mapped[ExistingLoan | None] = relationship()
    events: Mapped[list["ApplicationEvent"]] = relationship(order_by="ApplicationEvent.id")
    info_requests: Mapped[list["InfoRequest"]] = relationship(order_by="InfoRequest.id")
    decisions: Mapped[list["Decision"]] = relationship(order_by="Decision.id")


class ApplicationEvent(Base):
    __tablename__ = "application_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)
    type: Mapped[str] = mapped_column(String(30))
    actor_role: Mapped[str] = mapped_column(String(20))
    actor_name: Mapped[str] = mapped_column(String(200))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class InfoRequest(Base):
    __tablename__ = "info_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)
    message: Mapped[str] = mapped_column(Text)
    requested_fields: Mapped[list] = mapped_column(JSON, default=list)
    answer_text: Mapped[str | None] = mapped_column(Text)
    answer_fields: Mapped[dict | None] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    amount: Mapped[int | None] = mapped_column(Integer)
    term_months: Mapped[int | None] = mapped_column(Integer)
    rate: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    monthly_payment: Mapped[int | None] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text)
    reject_reason_code: Mapped[str | None] = mapped_column(String(40))
    created_by: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class News(Base):
    __tablename__ = "news"

    id: Mapped[int] = mapped_column(primary_key=True)
    tag: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0)
