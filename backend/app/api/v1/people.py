"""Employees, clocking in, leave and payroll.

The statutory rates live in the settings table, not in code, so a new budget
year is an edit on the Payroll screen rather than a new release. The defaults
below are Zambia's published rates as last known and are marked for checking:
confirm them with ZRA, NAPSA and NHIMA before anyone is paid from this.
"""
import json
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import current_user, requires
from app.models.access import Setting, User
from app.models.people import LEAVE_KINDS, Attendance, Employee, LeaveRequest, PayrollRun, Payslip
from app.services.audit import record
from app.services.numbering import numbered
from app.services.posting import Unbalanced, already_posted, post

router = APIRouter(prefix="/people", tags=["people"])

can_see_people = requires("hr.view", "hr.manage", "payroll.view")
can_manage_people = requires("hr.manage")
can_see_pay = requires("payroll.view", "payroll.manage")
can_prepare_pay = requires("payroll.manage")
can_approve_pay = requires("payroll.approve")
can_pay = requires("payroll.pay")
can_manage_attendance = requires("attendance.manage", "hr.manage")
can_approve_leave = requires("leave.approve", "hr.manage")

LUSAKA = timezone(timedelta(hours=2))

# Monthly, in ngwee. Bands are the upper limit of each band and its rate.
DEFAULT_RATES = {
    "paye_bands": [[510000, 0], [710000, 20], [920000, 30], [None, 37]],
    "napsa_percent": 5,
    "napsa_ceiling_ngwee": 3416400,  # maximum earnings NAPSA is charged on
    "nhima_percent": 1,
    "working_days": 26,
    "checked": False,
    "note": "Last known published rates. Confirm with ZRA, NAPSA and NHIMA before paying.",
}
RATES_KEY = "payroll_rates"


def _rates(db: Session) -> dict:
    row = db.get(Setting, RATES_KEY)
    if not row:
        return dict(DEFAULT_RATES)
    try:
        return {**DEFAULT_RATES, **json.loads(row.value)}
    except (TypeError, ValueError):
        return dict(DEFAULT_RATES)


def paye(taxable: int, bands: list) -> int:
    """Tax on monthly taxable pay, band by band."""
    tax = 0
    lower = 0
    for upper, rate in bands:
        top = taxable if upper is None else min(taxable, upper)
        if top > lower:
            tax += (top - lower) * rate / 100
        if upper is None or taxable <= upper:
            break
        lower = upper
    return round(tax)


def calculate(basic: int, allowances: int, rates: dict, unpaid_days: int = 0) -> dict:
    """One employee's month. Every figure the payslip shows comes from here."""
    working_days = max(int(rates.get("working_days", 26)), 1)
    deduction = round((basic + allowances) * unpaid_days / working_days) if unpaid_days else 0
    gross = max(basic + allowances - deduction, 0)
    napsa_base = min(gross, int(rates["napsa_ceiling_ngwee"]))
    napsa_emp = round(napsa_base * rates["napsa_percent"] / 100)
    # NHIMA is charged on basic pay only, after any unpaid leave.
    basic_after = max(basic - round(basic * unpaid_days / working_days), 0) if unpaid_days else basic
    nhima_emp = round(basic_after * rates["nhima_percent"] / 100)
    tax = paye(gross, rates["paye_bands"])
    return {
        "unpaid_deduction": deduction,
        "gross": gross,
        "paye": tax,
        "napsa_employee": napsa_emp,
        "napsa_employer": napsa_emp,
        "nhima_employee": nhima_emp,
        "nhima_employer": nhima_emp,
        "net": gross - tax - napsa_emp - nhima_emp,
    }


# ---------------------------------------------------------------------------
# shapes
# ---------------------------------------------------------------------------

class EmployeeIn(BaseModel):
    name: str = Field(min_length=3, max_length=80)
    job_title: str = Field(default="", max_length=60)
    department: str = Field(default="", max_length=40)
    phone: str = Field(default="", max_length=24)
    napsa_number: str = Field(default="", max_length=24)
    tpin: str = Field(default="", max_length=16)
    pay_method: str = Field(default="bank", max_length=16)
    pay_account: str = Field(default="", max_length=40)
    basic_ngwee: int = Field(ge=0, le=100_000_000)
    allowances_ngwee: int = Field(default=0, ge=0, le=100_000_000)
    leave_days_per_year: int = Field(default=24, ge=0, le=60)
    start_date: date | None = None
    user_id: str | None = None
    is_active: bool = True


class EmployeeOut(EmployeeIn):
    id: str
    number: str
    leave_taken: int
    leave_left: int
    clocked_in: bool


class LeaveIn(BaseModel):
    employee_id: str
    kind: str = "annual"
    start: date
    end: date
    reason: str = Field(default="", max_length=200)


class LeaveOut(BaseModel):
    id: str
    employee_id: str
    employee_name: str
    kind: str
    start: str
    end: str
    days: int
    reason: str
    status: str
    decided_by: str | None


class DecisionIn(BaseModel):
    approve: bool


class AttendanceOut(BaseModel):
    id: str
    employee_id: str
    employee_name: str
    day: str
    clock_in: str
    clock_out: str | None
    hours: float | None


class ClockIn(BaseModel):
    employee_id: str | None = None
    note: str = Field(default="", max_length=160)


class RunIn(BaseModel):
    period: str = Field(pattern=r"^\d{4}-\d{2}$")


class PayslipOut(BaseModel):
    id: str
    employee_id: str
    employee_name: str
    employee_number: str
    job_title: str
    napsa_number: str
    tpin: str
    basic_ngwee: int
    allowances_ngwee: int
    unpaid_days: int
    unpaid_deduction_ngwee: int
    gross_ngwee: int
    paye_ngwee: int
    napsa_employee_ngwee: int
    napsa_employer_ngwee: int
    nhima_employee_ngwee: int
    nhima_employer_ngwee: int
    net_ngwee: int
    days_worked: int


class RunOut(BaseModel):
    id: str
    period: str
    status: str
    gross_ngwee: int
    net_ngwee: int
    paye_ngwee: int
    napsa_ngwee: int
    nhima_ngwee: int
    employer_cost_ngwee: int
    created_by: str | None
    approved_by: str | None
    paid_by: str | None
    payslips: list[PayslipOut]


class RatesIn(BaseModel):
    paye_bands: list[list[int | None]]
    napsa_percent: float = Field(ge=0, le=50)
    napsa_ceiling_ngwee: int = Field(ge=0)
    nhima_percent: float = Field(ge=0, le=50)
    working_days: int = Field(ge=1, le=31)
    checked: bool = False
    note: str = Field(default="", max_length=300)


# ---------------------------------------------------------------------------
# employees
# ---------------------------------------------------------------------------

def _leave_taken(db: Session, employee_id: str, year: int) -> int:
    return db.scalar(
        select(func.coalesce(func.sum(LeaveRequest.days), 0)).where(
            LeaveRequest.employee_id == employee_id,
            LeaveRequest.status == "approved",
            LeaveRequest.kind == "annual",
            LeaveRequest.start >= date(year, 1, 1),
            LeaveRequest.start <= date(year, 12, 31),
        )
    ) or 0


def _employee_out(db: Session, e: Employee) -> EmployeeOut:
    taken = _leave_taken(db, e.id, datetime.now(LUSAKA).year)
    open_shift = db.scalar(
        select(Attendance).where(Attendance.employee_id == e.id, Attendance.clock_out.is_(None))
    )
    return EmployeeOut(
        id=e.id, number=e.number, name=e.name, job_title=e.job_title, department=e.department,
        phone=e.phone, napsa_number=e.napsa_number, tpin=e.tpin, pay_method=e.pay_method,
        pay_account=e.pay_account, basic_ngwee=e.basic_ngwee, allowances_ngwee=e.allowances_ngwee,
        leave_days_per_year=e.leave_days_per_year, start_date=e.start_date, user_id=e.user_id,
        is_active=e.is_active, leave_taken=taken, leave_left=e.leave_days_per_year - taken,
        clocked_in=bool(open_shift),
    )


@router.get("/employees", response_model=list[EmployeeOut])
def employees(include_left: bool = False, db: Session = Depends(get_db), _: User = Depends(can_see_people)):
    stmt = select(Employee).order_by(Employee.name)
    if not include_left:
        stmt = stmt.where(Employee.is_active.is_(True))
    return [_employee_out(db, e) for e in db.scalars(stmt).all()]


@router.post("/employees", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
def create_employee(body: EmployeeIn, db: Session = Depends(get_db), user: User = Depends(can_manage_people)):
    employee = Employee(number=numbered(db, "GB", width=3), created_by=user.name, **body.model_dump())
    employee.name = employee.name.strip()
    db.add(employee)
    record(db, user.name, "people", "Employee added", employee.name, employee.number)
    db.commit()
    db.refresh(employee)
    return _employee_out(db, employee)


@router.put("/employees/{employee_id}", response_model=EmployeeOut)
def update_employee(
    employee_id: str, body: EmployeeIn, db: Session = Depends(get_db), user: User = Depends(can_manage_people),
):
    employee = db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found.")
    before = {"basic": employee.basic_ngwee, "allowances": employee.allowances_ngwee}
    for field, value in body.model_dump().items():
        setattr(employee, field, value)
    record(db, user.name, "people", "Employee changed", employee.name, employee.number,
           before=before, after={"basic": employee.basic_ngwee, "allowances": employee.allowances_ngwee})
    db.commit()
    db.refresh(employee)
    return _employee_out(db, employee)


# ---------------------------------------------------------------------------
# attendance
# ---------------------------------------------------------------------------

def _who_is_clocking(db: Session, body: ClockIn, user: User) -> Employee:
    if body.employee_id:
        allowed = {"attendance.manage", "hr.manage"} & set(user.role.permission_codes)
        employee = db.get(Employee, body.employee_id)
        if not employee:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found.")
        if employee.user_id != user.id and not allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only clock yourself in.")
        return employee
    employee = db.scalar(select(Employee).where(Employee.user_id == user.id))
    if not employee:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Your sign-in is not linked to an employee record. Ask a manager to link it.",
        )
    return employee


@router.post("/clock-in", response_model=AttendanceOut)
def clock_in(body: ClockIn, db: Session = Depends(get_db), user: User = Depends(requires("attendance.clock", "attendance.manage", "hr.manage"))):
    employee = _who_is_clocking(db, body, user)
    if db.scalar(select(Attendance).where(Attendance.employee_id == employee.id, Attendance.clock_out.is_(None))):
        raise HTTPException(status.HTTP_409_CONFLICT, f"{employee.name} is already clocked in.")
    now = datetime.now(timezone.utc)
    row = Attendance(employee_id=employee.id, day=now.astimezone(LUSAKA).date(), clock_in=now,
                     note=body.note.strip(), created_by=user.name)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _attendance_out(row, employee.name)


@router.post("/clock-out", response_model=AttendanceOut)
def clock_out(body: ClockIn, db: Session = Depends(get_db), user: User = Depends(requires("attendance.clock", "attendance.manage", "hr.manage"))):
    employee = _who_is_clocking(db, body, user)
    row = db.scalar(select(Attendance).where(Attendance.employee_id == employee.id, Attendance.clock_out.is_(None)))
    if not row:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{employee.name} is not clocked in.")
    row.clock_out = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return _attendance_out(row, employee.name)


def _attendance_out(row: Attendance, name: str) -> AttendanceOut:
    hours = None
    if row.clock_out:
        hours = round((row.clock_out - row.clock_in).total_seconds() / 3600, 2)
    return AttendanceOut(
        id=row.id, employee_id=row.employee_id, employee_name=name, day=row.day.isoformat(),
        clock_in=row.clock_in.isoformat(), clock_out=row.clock_out.isoformat() if row.clock_out else None,
        hours=hours,
    )


@router.get("/me")
def my_clocking(
    db: Session = Depends(get_db),
    user: User = Depends(requires("attendance.clock", "attendance.manage", "hr.manage")),
):
    """My own clocking, for anyone who clocks in but may not see the staff
    list: cashiers, kitchen and store-room staff. Only their own rows."""
    employee = db.scalar(select(Employee).where(Employee.user_id == user.id, Employee.is_active.is_(True)))
    if not employee:
        return {"linked": False, "name": user.name, "rows": [], "clocked_in": False}
    since = datetime.now(LUSAKA).date() - timedelta(days=13)
    rows = db.scalars(
        select(Attendance).where(Attendance.employee_id == employee.id, Attendance.day >= since)
        .order_by(Attendance.clock_in.desc())
    ).all()
    return {
        "linked": True, "name": employee.name, "employee_id": employee.id,
        "clocked_in": any(r.clock_out is None for r in rows),
        "rows": [_attendance_out(r, employee.name).model_dump() for r in rows],
    }


@router.get("/attendance", response_model=list[AttendanceOut])
def attendance(
    days: int = Query(default=7, ge=1, le=62),
    db: Session = Depends(get_db), _: User = Depends(can_see_people),
):
    since = datetime.now(LUSAKA).date() - timedelta(days=days - 1)
    names = {e.id: e.name for e in db.scalars(select(Employee)).all()}
    rows = db.scalars(select(Attendance).where(Attendance.day >= since).order_by(Attendance.clock_in.desc())).all()
    return [_attendance_out(r, names.get(r.employee_id, "")) for r in rows]


# ---------------------------------------------------------------------------
# leave
# ---------------------------------------------------------------------------

def _weekdays(start: date, end: date) -> int:
    """Days of leave, Monday to Saturday, since the restaurant trades six days."""
    days = 0
    current = start
    while current <= end:
        if current.weekday() != 6:
            days += 1
        current += timedelta(days=1)
    return days


def _leave_out(row: LeaveRequest, name: str) -> LeaveOut:
    return LeaveOut(
        id=row.id, employee_id=row.employee_id, employee_name=name, kind=row.kind,
        start=row.start.isoformat(), end=row.end.isoformat(), days=row.days,
        reason=row.reason, status=row.status, decided_by=row.decided_by,
    )


@router.get("/leave", response_model=list[LeaveOut])
def leave(db: Session = Depends(get_db), _: User = Depends(can_see_people)):
    names = {e.id: e.name for e in db.scalars(select(Employee)).all()}
    rows = db.scalars(select(LeaveRequest).order_by(LeaveRequest.start.desc()).limit(100)).all()
    return [_leave_out(r, names.get(r.employee_id, "")) for r in rows]


@router.post("/leave", response_model=LeaveOut, status_code=status.HTTP_201_CREATED)
def request_leave(body: LeaveIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    employee = db.get(Employee, body.employee_id)
    if not employee:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found.")
    is_self = employee.user_id == user.id
    may_manage = {"hr.manage", "leave.approve"} & set(user.role.permission_codes)
    if not is_self and not may_manage:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only ask for your own leave.")
    if body.kind not in LEAVE_KINDS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown kind of leave.")
    if body.end < body.start:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The leave ends before it starts.")
    days = _weekdays(body.start, body.end)
    if body.kind == "annual":
        left = employee.leave_days_per_year - _leave_taken(db, employee.id, body.start.year)
        if days > left:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                f"{employee.name} has {left} days of annual leave left; this asks for {days}.")
    row = LeaveRequest(employee_id=employee.id, kind=body.kind, start=body.start, end=body.end,
                       days=days, reason=body.reason.strip(), created_by=user.name)
    db.add(row)
    record(db, user.name, "people", "Leave requested", f"{employee.name}: {days} days {body.kind}", employee.number)
    db.commit()
    db.refresh(row)
    return _leave_out(row, employee.name)


@router.post("/leave/{leave_id}/decide", response_model=LeaveOut)
def decide_leave(leave_id: str, body: DecisionIn, db: Session = Depends(get_db), user: User = Depends(can_approve_leave)):
    row = db.get(LeaveRequest, leave_id)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Leave request not found.")
    if row.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, "That request has already been decided.")
    employee = db.get(Employee, row.employee_id)
    if employee and employee.user_id == user.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Your own leave is approved by someone else.")
    row.status = "approved" if body.approve else "declined"
    row.decided_by = user.name
    row.decided_at = datetime.now(timezone.utc)
    record(db, user.name, "people", f"Leave {row.status}", f"{employee.name if employee else ''}: {row.days} days")
    db.commit()
    db.refresh(row)
    return _leave_out(row, employee.name if employee else "")


# ---------------------------------------------------------------------------
# payroll
# ---------------------------------------------------------------------------

@router.get("/payroll/rates")
def get_rates(db: Session = Depends(get_db), _: User = Depends(can_see_pay)):
    return _rates(db)


@router.put("/payroll/rates")
def set_rates(body: RatesIn, db: Session = Depends(get_db), user: User = Depends(can_prepare_pay)):
    bands = body.paye_bands
    if not bands or bands[-1][0] is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The last tax band must have no upper limit.")
    uppers = [b[0] for b in bands[:-1]]
    if any(u is None for u in uppers) or uppers != sorted(uppers):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Tax bands must rise in order.")
    value = json.dumps(body.model_dump())
    row = db.get(Setting, RATES_KEY)
    before = row.value if row else ""
    if row:
        row.value = value
    else:
        db.add(Setting(key=RATES_KEY, value=value))
    record(db, user.name, "people", "Payroll rates changed", "PAYE, NAPSA, NHIMA", before=before, after=value)
    db.commit()
    return _rates(db)


def _run_out(run: PayrollRun) -> RunOut:
    return RunOut(
        id=run.id, period=run.period, status=run.status, gross_ngwee=run.gross_ngwee,
        net_ngwee=run.net_ngwee, paye_ngwee=run.paye_ngwee, napsa_ngwee=run.napsa_ngwee,
        nhima_ngwee=run.nhima_ngwee, employer_cost_ngwee=run.employer_cost_ngwee,
        created_by=run.created_by, approved_by=run.approved_by, paid_by=run.paid_by,
        payslips=[
            PayslipOut(**{c: getattr(p, c) for c in PayslipOut.model_fields})
            for p in sorted(run.payslips, key=lambda p: p.employee_name)
        ],
    )


@router.get("/payroll/runs", response_model=list[RunOut])
def runs(db: Session = Depends(get_db), _: User = Depends(can_see_pay)):
    return [_run_out(r) for r in db.scalars(select(PayrollRun).order_by(PayrollRun.period.desc())).all()]


@router.post("/payroll/runs", response_model=RunOut, status_code=status.HTTP_201_CREATED)
def prepare_run(body: RunIn, db: Session = Depends(get_db), user: User = Depends(can_prepare_pay)):
    """Calculates a month for everyone employed. Re-running a draft recalculates it."""
    year, month = (int(x) for x in body.period.split("-"))
    if not 1 <= month <= 12:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Use a month like 2026-11.")
    start = date(year, month, 1)
    end = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)

    run = db.scalar(select(PayrollRun).where(PayrollRun.period == body.period))
    if run and run.status != "draft":
        raise HTTPException(status.HTTP_409_CONFLICT, f"{body.period} is already {run.status} and cannot be recalculated.")
    if run:
        run.payslips.clear()
        db.flush()
    else:
        run = PayrollRun(period=body.period, created_by=user.name)
        db.add(run)
        db.flush()

    rates = _rates(db)
    staff = db.scalars(select(Employee).where(Employee.is_active.is_(True)).order_by(Employee.name)).all()
    if not staff:
        raise HTTPException(status.HTTP_409_CONFLICT, "Add employees before running payroll.")
    totals = {"gross": 0, "net": 0, "paye": 0, "napsa": 0, "nhima": 0, "employer": 0}
    for employee in staff:
        unpaid = db.scalar(
            select(func.coalesce(func.sum(LeaveRequest.days), 0)).where(
                LeaveRequest.employee_id == employee.id, LeaveRequest.status == "approved",
                LeaveRequest.kind == "unpaid", LeaveRequest.start >= start, LeaveRequest.start <= end,
            )
        ) or 0
        worked = db.scalar(
            select(func.count(func.distinct(Attendance.day))).where(
                Attendance.employee_id == employee.id, Attendance.day >= start, Attendance.day <= end,
            )
        ) or 0
        figures = calculate(employee.basic_ngwee, employee.allowances_ngwee, rates, unpaid)
        db.add(Payslip(
            run_id=run.id, employee_id=employee.id, employee_name=employee.name,
            employee_number=employee.number, job_title=employee.job_title,
            napsa_number=employee.napsa_number, tpin=employee.tpin,
            basic_ngwee=employee.basic_ngwee, allowances_ngwee=employee.allowances_ngwee,
            unpaid_days=unpaid, unpaid_deduction_ngwee=figures["unpaid_deduction"],
            gross_ngwee=figures["gross"], paye_ngwee=figures["paye"],
            napsa_employee_ngwee=figures["napsa_employee"], napsa_employer_ngwee=figures["napsa_employer"],
            nhima_employee_ngwee=figures["nhima_employee"], nhima_employer_ngwee=figures["nhima_employer"],
            net_ngwee=figures["net"], days_worked=worked,
        ))
        totals["gross"] += figures["gross"]
        totals["net"] += figures["net"]
        totals["paye"] += figures["paye"]
        totals["napsa"] += figures["napsa_employee"] + figures["napsa_employer"]
        totals["nhima"] += figures["nhima_employee"] + figures["nhima_employer"]
        totals["employer"] += figures["gross"] + figures["napsa_employer"] + figures["nhima_employer"]

    run.gross_ngwee, run.net_ngwee, run.paye_ngwee = totals["gross"], totals["net"], totals["paye"]
    run.napsa_ngwee, run.nhima_ngwee, run.employer_cost_ngwee = totals["napsa"], totals["nhima"], totals["employer"]
    run.rates_used = json.dumps(rates)
    record(db, user.name, "people", "Payroll prepared", f"{body.period}: {len(staff)} people, net {totals['net']} ngwee", body.period)
    db.commit()
    db.refresh(run)
    return _run_out(run)


@router.post("/payroll/runs/{run_id}/approve", response_model=RunOut)
def approve_run(run_id: str, db: Session = Depends(get_db), user: User = Depends(can_approve_pay)):
    """Approval puts the month in the books: wages and the employer's share as
    costs, and what is owed to staff, ZRA, NAPSA and NHIMA as liabilities."""
    run = db.get(PayrollRun, run_id)
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payroll not found.")
    if run.status != "draft":
        raise HTTPException(status.HTTP_409_CONFLICT, f"That payroll is already {run.status}.")
    if run.created_by == user.name:
        raise HTTPException(status.HTTP_409_CONFLICT, "Payroll is approved by someone other than whoever prepared it.")
    employer_napsa = sum(p.napsa_employer_ngwee for p in run.payslips)
    employer_nhima = sum(p.nhima_employer_ngwee for p in run.payslips)
    try:
        if not already_posted(db, "payroll", run.period):
            post(db, [
                ("6000", run.gross_ngwee, 0, "Gross pay"),
                ("6010", employer_napsa + employer_nhima, 0, "Employer NAPSA and NHIMA"),
                ("2200", 0, run.net_ngwee, "Net pay owed to staff"),
                ("2210", 0, run.paye_ngwee, "PAYE"),
                ("2220", 0, run.napsa_ngwee, "NAPSA, both shares"),
                ("2230", 0, run.nhima_ngwee, "NHIMA, both shares"),
            ], f"Payroll {run.period}", source="payroll", reference=run.period, who=user.name)
    except Unbalanced as problem:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"The payroll does not balance: {problem}")
    run.status = "approved"
    run.approved_by = user.name
    run.approved_at = datetime.now(timezone.utc)
    record(db, user.name, "people", "Payroll approved", run.period, run.period)
    db.commit()
    db.refresh(run)
    return _run_out(run)


@router.post("/payroll/runs/{run_id}/pay", response_model=RunOut)
def pay_run(run_id: str, db: Session = Depends(get_db), user: User = Depends(can_pay)):
    """Records that the net pay has left the bank."""
    run = db.get(PayrollRun, run_id)
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payroll not found.")
    if run.status != "approved":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only an approved payroll can be paid.")
    try:
        post(db, [("2200", run.net_ngwee, 0, "Net pay"), ("1010", 0, run.net_ngwee, "Paid from the bank")],
             f"Wages paid {run.period}", source="payroll", reference=f"{run.period}-PAID", who=user.name)
    except Unbalanced as problem:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(problem))
    run.status = "paid"
    run.paid_by = user.name
    run.paid_at = datetime.now(timezone.utc)
    record(db, user.name, "people", "Wages paid", f"{run.period}: {run.net_ngwee} ngwee", run.period)
    db.commit()
    db.refresh(run)
    return _run_out(run)
