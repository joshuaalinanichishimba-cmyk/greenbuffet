# Stage 8 report — staff, clocking, leave and payroll

Five new tables. `.\scripts\update.ps1` creates them.

## What you can do

**Staff** (`/people`) — employees with job, department, NAPSA number, TPIN, how
they are paid, basic pay and allowances. Anyone whose sign-in is linked to their
employee record sees their own panel at the top: clock in, clock out, days of
leave left, ask for leave. Managers can clock anyone in or out. The Clocking tab
shows the last week; the Leave tab shows requests with Approve and Decline.

**Payroll** (`/payroll`) — prepare a month, have someone else approve it, record
it as paid. Each payslip prints on its own, with the employer's NAPSA and NHIMA
shown underneath.

## The calculation

Checked by hand against a K8,000 basic plus K1,000 housing allowance:

| | |
| --- | --- |
| Gross | K9,000.00 |
| PAYE: 0% to K5,100, 20% of the next K2,000, 30% of the last K1,900 | K970.00 |
| NAPSA, 5% | K450.00 |
| NHIMA, 1% of basic only | K80.00 |
| **Net** | **K7,500.00** |

NAPSA stops at its earnings ceiling — K1,708.20 a month at K50,000 gross.
Unpaid leave comes off pay in proportion to a 26-day working month.

**Confirm the rates before paying anyone.** They are the last published figures
I know, and the Payroll screen says so in yellow until someone ticks "I have
confirmed these with ZRA, NAPSA and NHIMA". The bands, percentages and ceiling
are all editable there, so a new budget year is an edit, not a new release.

A payslip keeps the figures it was calculated with. Changing the rates next year
does not rewrite this month's payslips.

## Into the books

Approving a month posts it: wages and the employer's share as costs; net pay,
PAYE, NAPSA and NHIMA as money owed. Recording it as paid moves the net pay out
of the bank. For two staff at K9,000 and K4,000: K13,770 on each side, and the
trial balance and balance sheet still balance afterwards.

## Two people, again

| Rule | Result |
| --- | --- |
| Approving a payroll you prepared | 409 |
| Approving your own leave | 409 |
| Recalculating an approved month | 409 |
| Paying a month that is not approved | 409 |
| Annual leave beyond what is left | 422, with both numbers |
| Clocking in twice | 409 |
| Clocking someone else in without attendance rights | 403 |
| A sign-in with no employee record clocking in | 409, says to ask a manager to link it |
| A cashier opening payroll | 403 |

Leave counts Monday to Saturday, since the restaurant trades six days.

## Tested

Against PostgreSQL: two employees, clocking, a six-day leave request approved
by someone else, the month prepared, refused to its preparer, approved by the
accountant, paid, and both journal entries checked. In the browser: adding an
employee, clocking them in, the leave and clocking tabs, the rates warning, a
run and a printed payslip. No horizontal scrolling at 390 px.

## Not in this stage

- **Overtime and shift premiums.** Add as an allowance per month for now.
- **Loans and salary advances.** A deduction line per payslip, worth adding
  once you know how the restaurant handles them.
- **Bank payment files.** Most Zambian banks take a CSV; the format depends on
  which bank, so it comes with stage 9's exports.
