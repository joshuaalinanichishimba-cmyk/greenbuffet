# The Green Buffet: development plan

This plan follows PROJECT_AUDIT.md. Each phase fixes the gaps the audit found,
most costly first: money first, then stock, then purchasing and books, then
people, then oversight. Nothing that works now is rebuilt.

Each new feature answers four questions: the problem it solves, who uses it,
how often, and how we will know it worked. Features that couldn't answer
them are listed at the end as **not planned**.

Every phase ends the same way:
- tests for everything it touched, plus the existing 36 tests and 29 probes;
- a sweep of every screen in light and dark mode, on phone and desktop;
- a changelog entry and an updated TEST_REPORT.md;
- a zip with `update.ps1`.

Database changes only **add**. Nothing is dropped without your written yes
and a backup first.

---

## Phase 0: protection (half a day): done in stage 22

| Item | Why |
|---|---|
| A Git repository on the PC, with the current code as the first commit | Any change can be rolled back. It costs nothing and needs no internet. |
| `update.ps1` takes a database backup before every update | An update can never lose data. |
| A restore test: `restore.ps1` into a test database, with a row count compared against the live one | Backups only count once a restore has worked. |
| A baseline test pack of money flows: the audit's sales, split payments, retries, stock deducted once, refund, close till, books balanced | Proves later phases broke nothing. |

**Approval needed:** none (adds only).

## Phase 1: cash and the till, where money goes missing (about 1 week): done in stage 22

Done except **till handover**, the **daily discount report** and **PDF receipt
download**, which move to stage 23. Kitchen tickets were already sent at
payment. Defaults chosen: variance K20, cashier discount 10%, both in Settings.

| Item | Problem solved | Who and how often |
|---|---|---|
| **Blind till count**: the cashier types the counted cash before seeing what was expected. A variance over a set amount (default K20) needs an explanation, and goes to a manager to review. | Cashiers adjust the count to match the screen. | Every cashier, every shift. |
| **Cash movements**: cash drop to the safe, petty cash out with a reason, cash added, each with who and a manager confirmation. Moving cash is not a sale or an expense, but petty cash *spent* is an expense. | Today a drop to the safe looks like a shortage. | Several times a day. |
| **Till handover**: a cashier hands the till to another, both confirm the count, and each person's sales stay their own. | Two cashiers on one drawer, with no way to tell whose shortage it is. | At shift change. |
| **Mobile money status**: pending, then confirmed or failed. The cashier confirms after seeing the operator's SMS. A reference can't be used twice. An end-of-day match screen lists anything left pending. | A payment counted as received just because it was typed in, and duplicate references. | Every mobile money sale, plus once a day. |
| **Discount limits**: a per-role limit (for example a cashier up to 10%). Above it needs a manager's PIN on the till, with a reason. A daily discount report. | Today a cashier gave a 98% discount with no approval. | Daily. |
| **Refund requests**: a cashier asks, a manager approves on the spot or later, with a limit by role. | Refunds go through managers only, so cashiers can't even start one. | Weekly. |
| **Reprints audited**, and a PDF receipt download. | Reprinted receipts used to repeat a refund or claim. | Occasionally. |
| **Hold and recall**, and changing an unpaid order. | Re-entering an order to change one item. | Daily. |
| **Kitchen gets the ticket at payment** (a setting, with "at order" kept as an option). The wait figure counts only the last 2 hours. | Food made for orders never paid for, and a meaningless "386 min". | Every order. |

**Database:** new columns on payments (status, confirmed_by, confirmed_at), a
unique mobile reference per method, new tables `cash_movements` and
`till_handovers`, and new columns on shifts (variance_reason, reviewed_by).
**Approval needed:** default limits (variance K20, cashier discount 10%) and
whether the kitchen gets tickets at payment. Both can be changed later in
Settings.

## Phase 2: stock and waste, where food goes missing (about 1 week)

| Item | Problem solved |
|---|---|
| **Count sheets**: a daily sheet for chicken, beef and drinks, and a weekly sheet for everything. It shows theoretical against counted with the variance in kwacha. Large variances need a manager's note. | Stock disappearing unexplained. |
| **Waste log**: item, quantity, reason (expired, spoiled, burnt, wrong order, unsold, staff meal, free meal), who and when. It feeds stock, the books and a waste report. Staff and free meals are kept apart from accidents. | No record of what is thrown away. |
| **Expiry dates on receiving** for perishables, and an "expires in 2 days" list. | Spoilage noticed too late. |
| **Pack sizes**: buy by crate or bag, use by the piece or gram, with fixed conversions per ingredient. | Market purchases don't match recipe units. |
| **Margins marked as estimates** until each ingredient has a real cost from a purchase. | Owners trusting made-up margins. |

**Database:** new tables `stock_counts`, `stock_count_lines`, `waste_entries`
and `ingredient_packs`, and new columns on purchase lines (expiry_date).

## Phase 3: purchasing and the books (about 1 week)

| Item | Problem solved |
|---|---|
| **Partial and damaged deliveries** when receiving. | Paying for goods that didn't arrive. |
| **Duplicate invoice check** (same supplier and invoice number). | Paying twice. |
| **Supplier price history**: last price paid, and who is cheaper for this item. | Not knowing the market moved. |
| **Receipt photos** attached to purchases and expenses (the existing file storage). | No evidence for spending. |
| **Expenses screen**: rent, ZESCO, water, gas, generator fuel, transport, repairs, internet, bank and mobile money charges, licences. It is paid from the till (petty cash), the bank or mobile money, and posts to the books. | Expenses kept outside the system, so the profit figure is wrong. |
| **Closing a month**: nothing can be posted into a closed month, and reopening needs an owner. | Back-dated changes to finished figures. |
| **Bank, mobile money and card reconciliation**: tick the statement lines against the system. | Money that never reached the bank. |

## Phase 4: people (about 1 week)

| Item | Problem solved |
|---|---|
| **Weekly roster**: morning, afternoon, evening and custom shifts, plus rest days. | Lateness and absence can't be measured without a plan. |
| **Late and missed shifts** from roster against clocking, and attendance corrections with approval. | Paying for hours not worked. |
| **Payroll additions**: overtime (approved), bonuses, salary advances, daily and hourly wages. Rates are **checked against current ZRA, NAPSA and NHIMA figures** before the first real run. | Real pay arrangements. |
| **No automatic deductions for shortages or damage.** | Required by the brief and by fairness. |

## Phase 5: owner oversight (about 1 week)

*Done early, in stage 22:* one owner can't switch off or demote the other;
password reset, change or switching off ends sessions; the second owner
account is made by `starter-accounts.ps1` with a temporary password.

| Item | Problem solved |
|---|---|
| **Two equal owners, protected.** The last active owner can't be switched off. Switching off or changing the other owner needs the other owner to confirm. Owner sign-in uses a second step (an authenticator app code). An owner can flag the other's account as compromised, which forces a password change without removing ownership. | One owner, or a stolen password, locking the other out. |
| **Sessions**: a list of active sign-ins per person, sign out one or all. A password reset ends old sessions. | Today a reset leaves the old session working for 8 hours. |
| **Several roles per person**, plus extra or removed permissions for one person. Roles become reusable templates (Standard cashier, Senior cashier, Kitchen supervisor). A preview shows what the person will see. | Today you need a new role for every exception. |
| **Approval centre**: refunds, discounts above the limit, stock adjustments, expenses and purchases above a threshold, payroll, sensitive permission changes. You choose for each: no approval, a manager, either owner, or both owners. You can't approve your own request, and each request can be processed only once. | Approvals scattered or missing. |
| **Notifications**, three levels (critical, high, routine), in the app. Email only if you set it up; SMS and WhatsApp not until justified by cost. | Owners away from the restaurant. |
| **Alerts from real rules**: till short over K20; discounts over limit; refunds over N a day; stock variance over K; supplier overdue; order waiting over 20 min; roster no-show; till left open overnight; backup older than a day. Thresholds are in Settings. They flag a problem for investigation, never an accusation. | Problems found weeks late. |
| **Owner dashboard additions**: yesterday, week, month; actual vs estimated figures marked; cash, mobile and card received; shortages; waste value; expenses; owed to suppliers; delayed orders; who is on duty. A daily summary at closing. | Seeing the day in seconds. |
| **Audit log**: role at the time, success or failure, device; CSV export; filters by person, area and date. | Answering "who changed this?". |
| **System health**: green, amber, red and grey from real checks (database, last backup, pending mobile money, unposted entries, stuck tickets, ZRA "not configured"). | Knowing whether the system is healthy. |
| **Opening and closing checklists**, with fridge temperatures and cleaning. **Equipment list** with fault reports. | Kept as one small "Daily checks" screen. |

## Phase 6: production readiness (about 1 week)

| Item | Note |
|---|---|
| **Power and network**: a UPS for the PC, router and receipt printer, giving at least 30 minutes. Documented in DEPLOYMENT_GUIDE.md. | The cheapest protection against load shedding. The till keeps working as long as the PC and router have power. Internet isn't needed. |
| **Offline till (only if still needed after the UPS)**: the till keeps cash sales in the browser while the PC is unreachable, numbered per device, and sends them once the PC is back. Mobile money is never confirmed offline. | Built only if a UPS isn't enough in practice: it adds real risk of double sales. |
| **ZRA Smart Invoice**: built against ZRA's official specification once you have the TPIN, device registration and test credentials. Until then it is shown as *pending configuration*, and nothing is ever faked. | Needs you to start registration with ZRA. |
| **Remote access for owners** over a secure tunnel (for example Tailscale, free for a few devices), without exposing the PC to the internet. | Monitoring away from the restaurant. |
| Security review, restore drill, staff guides (USER_GUIDE.md), deployment guide. | |

---

## Not planned (couldn't justify)

- **Customer accounts, online ordering, delivery fleet, tracking links, a
  marketing outbox.** These were removed in stage 20, and you confirmed the
  restaurant is counter-only.
- **Table management.** You serve at the counter; eat-in is enough.
- **Multi-branch.** Every record can carry a branch later if you open a
  second shop. Nothing is built now.
- **Chatbots, AI scores, cryptocurrency, animations, decorative charts.**
- **Biometric clocking.** A personal sign-in with a roster check is enough.
- **Webcam, keystroke or screen monitoring.** Explicitly excluded.

---

## Decisions you made (24 November)

1. VAT registered at 16%; the owner can change it in Settings → Tax.
2. Administrator and Inventory staff removed; accounts moved to Manager and Kitchen.
3. Old delivery, catering and messages data removed after a backup.
4. Cash and till first; the code goes to GitHub when done.

## Decisions needed from you (as first asked)

1. **VAT.** Is The Green Buffet registered for VAT, on turnover tax, or
   neither? Every receipt currently says "VAT included" at 16%.
2. **Account types.** The brief lists five types: owner (two), manager,
   cashier, kitchen, accountant. Today there are also *Administrator* and
   *Inventory staff*. Should they become permission templates (no accounts
   lost), or stay as they are?
3. **Leftover delivery, catering and messages tables and columns.** Keep them
   (harmless), or remove them after a backup?
4. **Order of work.** Start Phase 0 then Phase 1 as above, or move owner
   protection (Phase 5's two-owner safeguards and sessions) to the front?
5. **Second owner's details**: name and email, so the account can be made
   securely with a temporary password, not set in code.
