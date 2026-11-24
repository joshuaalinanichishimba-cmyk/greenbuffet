"""Employees, attendance, leave and payroll.

Payslips copy every figure at the moment the run is calculated. A rate change
next year must not rewrite this month's payslip, for the same reason a price
change must not rewrite a receipt.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, new_id

LEAVE_KINDS = ("annual", "sick", "maternity", "paternity", "compassionate", "unpaid")


class Employee(Base, TimestampMixin):
    __tablename__ = "employees"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    number: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    # The sign-in account, when this person uses the system, so they can clock in.
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, unique=True)
    job_title: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    department: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    phone: Mapped[str] = mapped_column(String(24), default="", nullable=False)
    napsa_number: Mapped[str] = mapped_column(String(24), default="", nullable=False)
    tpin: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    pay_method: Mapped[str] = mapped_column(String(16), default="bank", nullable=False)
    pay_account: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    basic_ngwee: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Housing, transport and the like: taxable, but outside NHIMA's basic-pay base.
    allowances_ngwee: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    leave_days_per_year: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Attendance(Base, TimestampMixin):
    __tablename__ = "attendance"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    clock_in: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    clock_out: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str] = mapped_column(String(160), default="", nullable=False)


class LeaveRequest(Base, TimestampMixin):
    __tablename__ = "leave_requests"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), default="annual", nullable=False)
    start: Mapped[date] = mapped_column(Date, nullable=False)
    end: Mapped[date] = mapped_column(Date, nullable=False)
    days: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(12), default="pending", nullable=False, index=True)
    decided_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PayrollRun(Base, TimestampMixin):
    __tablename__ = "payroll_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    period: Mapped[str] = mapped_column(String(7), nullable=False, unique=True)  # 2026-11
    status: Mapped[str] = mapped_column(String(12), default="draft", nullable=False)
    gross_ngwee: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    net_ngwee: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    paye_ngwee: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    napsa_ngwee: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    nhima_ngwee: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    employer_cost_ngwee: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rates_used: Mapped[str] = mapped_column(String(2000), default="", nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    payslips: Mapped[list[Payslip]] = relationship(
        back_populates="run", cascade="all, delete-orphan", lazy="selectin",
    )


class Payslip(Base):
    __tablename__ = "payslips"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("payroll_runs.id"), nullable=False, index=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), nullable=False)
    employee_name: Mapped[str] = mapped_column(String(80), nullable=False)
    employee_number: Mapped[str] = mapped_column(String(16), nullable=False)
    job_title: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    napsa_number: Mapped[str] = mapped_column(String(24), default="", nullable=False)
    tpin: Mapped[str] = mapped_column(String(16), default="", nullable=False)

    basic_ngwee: Mapped[int] = mapped_column(Integer, nullable=False)
    allowances_ngwee: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unpaid_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unpaid_deduction_ngwee: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    gross_ngwee: Mapped[int] = mapped_column(Integer, nullable=False)
    paye_ngwee: Mapped[int] = mapped_column(Integer, nullable=False)
    napsa_employee_ngwee: Mapped[int] = mapped_column(Integer, nullable=False)
    napsa_employer_ngwee: Mapped[int] = mapped_column(Integer, nullable=False)
    nhima_employee_ngwee: Mapped[int] = mapped_column(Integer, nullable=False)
    nhima_employer_ngwee: Mapped[int] = mapped_column(Integer, nullable=False)
    net_ngwee: Mapped[int] = mapped_column(Integer, nullable=False)
    days_worked: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    run: Mapped[PayrollRun] = relationship(back_populates="payslips")

    __table_args__ = (UniqueConstraint("run_id", "employee_id", name="uq_payslip"),)
