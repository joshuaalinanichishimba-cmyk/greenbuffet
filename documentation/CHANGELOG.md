# Changelog

Stage by stage. Each stage's full report is in its STAGE-*-REPORT.md.

| Stage | Date | Summary |
|---|---|---|
| 1–13 | to Nov 2026 | Till, kitchen, menu and recipes, stock, purchasing and suppliers, double-entry books, payroll (PAYE, NAPSA, NHIMA), leave, attendance, reports, backups, Windows service scripts. |
| 14–16 | Nov 2026 | Customer site, deliveries, functions, message outbox (removed in stage 20). |
| 17 | 22 Nov | Screens rebuilt to match the demo: logo, look, stamp card, promotions, feedback. |
| 18 | 23 Nov | Server status check, kitchen live updates fixed, undo and chime, period comparison, light or dark. |
| 19 | 24 Nov | A home screen for each role; sign-in by kind of account. |
| 20 | 24 Nov | Counter point of sale only; the printed menu loaded; one-tap sign-in. |
| 21 | 24 Nov | Dark mode fixed on every screen, receipt-only printing, My clocking, test sign-in. |
| Audit | 24 Nov | PROJECT_AUDIT.md, DEVELOPMENT_PLAN.md, INTEGRATION_STATUS.md, TEST_REPORT.md, DATABASE_DOCUMENTATION.md. No code changed. |
| 22 | 24 Nov | Backup before every update and a verified restore; your decisions (VAT switch, five roles, old data removed after a backup); blind till count, variance notes and review, cash drops and petty cash, mobile money pending/confirmed and unique references, discount and refund approval at the till, held orders and changing them, reprints audited; one owner can't switch off the other; password reset ends sessions; `push-to-github.ps1`. |
| 23 | 24 Nov | Profiles with photographs, the account menu and notices bell on every screen; real online status from a heartbeat (online, away, connection lost, offline, unknown) kept separate from clocking; Team directory with filters; per-device sessions that can be signed out; suspend, restore and archive; two-step sign-in (required for owners); lock screen and switching person on shared computers, with each person's till basket kept; owner notices; staff-number fix; outline buttons fixed. |
| 24 | 25 Nov | IT administrator account and IT workspace (health, diagnostics, nine integrity checks, six verified repairs, emergency controls, incidents, support tickets, error log, security centre, technical audit, resources); Report a problem for everyone; audit log append-only in PostgreSQL; rate limits; Content Security Policy; fix: failed mobile money after hand-over now owes again and is paid once. MASTER-SPEC-STATUS.md maps all 110 sections. |
| 25 | 25 Nov | Email (version 1.25.0): confirmed addresses, emailed sign-in codes as a second two-step method for owners and IT, forgotten-password links, address change needing both old and new codes, security notices by email, email log with no codes or links, IT email status and test, stronger password rule (10 characters, no common ones). `email-setup.ps1` sends from Gmail with an App Password for now. |
| 27 | 25 Nov | Installable app and offline cash sales (version 1.27.0): manifest, icons and service worker keep every screen on the device; the till takes cash with the server out of reach, saves each sale on the device first with its own id, and sends it when the server answers; the server records each id once (unique index), prices it again, dates it to when the customer paid, and tells the owners about price differences or late arrivals; problem sales listed for a manager; sign-in kept through a reload while offline. Email and two-step moved to the last step before go-live. |
