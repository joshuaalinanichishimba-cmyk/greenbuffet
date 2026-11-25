# For IT support

You keep the system running. You do not handle money, pay, prices or
refunds, and the system will not let you.

## Every morning

1. IT workspace → **Health**. Anything not "Operational" has a line saying why.
2. **Run diagnostics** once a day, or after any fault.
3. **Tickets**: answer new ones. Your message appears on the reporter's
   profile.

## When something breaks

1. Open an **incident**: what is wrong, which part, how bad, who it affects.
2. Look at **Errors**. The reference staff see on screen ("reference 3fa21c")
   is the same reference there, and in `logs\server.log` on the server.
3. If a check found records out of step, use a **repair**. Read what it will
   touch first. Write why. It checks itself afterwards. If it says "still
   found", do not run it again blindly; find out why.
4. If the till must keep going while you work, use a **control**:
   - **Mobile money and card off**: cash only, for example when a network is
     down.
   - **Taking new orders off**: when the kitchen cannot cook.
   - **Read-only**: while the books are being fixed.

   The owners are told each time. Switch it back as soon as you can.
5. Close the incident only with what fixed it and how to stop it happening
   again.

## Email

IT workspace → **Email** shows whether email is set up and every message the
system tried to send, with the reason when one failed. It never shows a
message, a code or a link.

- **Send a test** goes to your own confirmed address only.
- "Username and Password not accepted" (535): the Google App Password was
  deleted or mistyped. Ask Joshua or an owner to make a new one and run
  `.\scripts\email-setup.ps1` on the server, then `.\scripts\update.ps1`.
- Codes that failed are not resent; the person asks for a new one.
- You cannot see anyone's code and there is no bypass. Someone without their
  email uses a recovery code, or an owner resets their two-step on the Team
  page.

## What you cannot do from here, on purpose

- Change or delete the audit log (nobody can).
- Confirm a payment, change an amount, refund, or approve anything.
- Sign an owner out (the other owner does that, from the Team page).
- Restore a backup. That is `scripts\restore.ps1` on the server, and it
  tests the backup in a separate database first.
- Run commands or SQL.

## If the system itself is down

See `EMERGENCY-RECOVERY.md`.
