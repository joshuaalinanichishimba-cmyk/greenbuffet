# Stage 9 report — dashboards, reports and exports

No new tables. Two new Python packages (openpyxl for Excel, reportlab for PDF),
which `.\scripts\update.ps1` installs.

## The dashboard

`/reports` opens with six figures for today, 7, 30 or 90 days: what was taken,
how many orders and the average, the margin after food costs, the VAT collected,
the stock on hand with how many items need reordering, and the average time the
kitchen took from paid to ready alongside how many staff are clocked in.

Under that: sales by day as a bar chart, how people paid, the busiest hours, and
what sells. The charts are drawn in plain CSS from the same numbers — no chart
library, nothing to load, and they work on a phone.

## Nine reports, three formats each

Sales by day · What sells · How people paid · Stock on hand · Stock movements ·
Hours worked · Payroll · Trial balance · VAT collected.

Each opens on screen and downloads as **PDF** (for sending or filing), **Excel**
(for working on, with the headings frozen and columns sized) or **CSV** (for
anything else, with the byte order mark Excel on Windows needs to read Kwacha
and accented names correctly).

Every report is built once as a table and then rendered. The numbers on the
screen and the numbers in the file come from the same place, so they cannot
drift apart.

The VAT report totals sales before VAT, the VAT inside prices, and the gross, by
month — the three figures a ZRA return asks for.

## Permissions

A report is only offered to someone whose role covers it: payroll needs
`payroll.view`, stock needs `inventory.view`, the trial balance needs
`books.view`, and `reports.view` covers all of them. Inventory staff asking for
the payroll report get 403, and a cashier cannot open the dashboard at all.

## The navigation, regrouped

Sixteen links had grown into three rows. The bar now carries the five screens
someone uses all day — Dashboard, Till, Kitchen, Orders, Reports — and the rest
sit behind **More**, grouped as Menu, Stock, Money and People. One row on a
laptop, and the sheet fits a phone.

## Two fixes while testing

**Downloads arrived with the wrong name.** A browser cannot read the filename a
server sends unless the server says it may; without that the files saved as
`sales-by-day.pdf` instead of `green-buffet-sales-by-day-20261123.pdf`. One line
of CORS configuration.

**80 pixels of sideways scroll on a phone.** A grid column will not shrink below
its contents unless told to, and the payment-method bars were holding the panel
open. Fixed where it belonged, in the grid.

## Tested

Against PostgreSQL: the dashboard over 30 days, all nine reports built, all
three formats downloaded and checked for valid file headers, a bad format and an
unknown report refused, and two roles turned away from reports they may not see.
In the browser: the dashboard, switching the period, opening a report, and three
real downloads through the browser's own download handling. No horizontal
scrolling at 390 px.

## Not in this stage

- **Emailing a report on a schedule.** Needs a mail account for the business,
  which belongs with the settings work in stage 10.
- **Comparing periods** — this month against last. Worth adding once there are
  two months of real trading to compare.
- **Bank payment files for payroll.** Still waiting on which bank.
