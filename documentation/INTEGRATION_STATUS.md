# Integration status

Each connection to the outside world, and what state it is really in. Nothing
here is shown as working unless it has been used and checked.

| Integration | Status | What it does today | What is needed |
|---|---|---|---|
| Airtel Money, MTN MoMo, Zamtel Kwacha | **Manual** | The cashier takes the payment on the operator's phone or till and types the transaction reference. There is no live link. Since stage 22 a reference can't be used twice, and a payment stays *pending* until the cashier ticks that they saw the operator's message, or a manager matches it against the statement (Payments → To match against the statement). | A merchant API agreement with each operator, if the volume justifies it. Until then: manual confirmation and an end-of-day match (Phase 1). |
| Card | **Manual** | Taken on the bank's machine; the slip reference is typed in. | Settlement matching against the bank statement (Phase 3). |
| ZRA Smart Invoice | **Not configured** | Nothing is sent to ZRA. Receipts carry no fiscal reference. | The tax registration answer (VAT / turnover tax), a TPIN, ZRA's official integration specification, and test then production credentials. |
| Email | **Not configured** | No email is sent. | An SMTP account, if owners want the daily summary by email. |
| SMS / WhatsApp | **Not configured** | None. The customer message outbox was removed in stage 20. | Only if a critical-alert channel is justified by cost. |
| Backups | **Working, restore not verified on the PC** | `backup.ps1` makes a PostgreSQL dump, and `schedule-backup.ps1` runs it nightly. | A restore drill (Phase 0) and a copy kept off the PC (USB or cloud). |
| Remote access | **Not configured** | The system is only reachable on the restaurant network. | A secure tunnel for the owners (Phase 6). |
