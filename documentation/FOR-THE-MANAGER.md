# For the manager

## Every day

**Open the system** and glance at **Reports**: what has been taken today, the
margin after food costs, and whether anything needs reordering.

**Check the till at closing.** Each cashier closes their own till and counts the
drawer. **Reports → How people paid** shows what should have been taken by cash
against mobile money and card. A difference is recorded against the cashier's
name in the activity log.

**Look at the kitchen times.** The dashboard shows the average minutes from paid
to ready. If it climbs, something in the kitchen needs attention.

## Every week

**Count the store room** — Stock → Count on each ingredient. Until this is done
the figures are only what the system has seen move. An ingredient showing less
than nothing means either it was never counted in, a delivery was not checked
in, or a recipe is wrong.

**Check what needs ordering.** Stock shows how many items are at or below their
reorder level. Buying in → New purchase writes the order; check it in when the
goods actually arrive, and the price you paid becomes the cost used for margins.

**Look at the margins.** Menu shows each dish's ingredient cost against its
price. A margin that has slipped usually means a supplier put their price up.

## Every month

**Record the costs that are not deliveries** — rent, electricity, gas,
licences. Journal → Write an entry. Someone else approves it; that is
deliberate, so no one person both writes and blesses a figure.

**Run payroll.** Payroll → choose the month → Prepare payroll. Check the
payslips, have someone else approve it, then record it as paid once the money
has gone. Approving puts the whole month into the books.

**Read the books.** Books shows profit and loss, the balance sheet, where the
money moved, and the trial balance. Each says plainly whether it balances. If
one says it does not, something is wrong — tell whoever maintains the system.

**File the VAT.** Reports → VAT collected gives sales before VAT, the VAT
inside prices, and the gross, by month. Download it as PDF for the return.

## Staff

**A new person**: Sign-ins → create their account, which gives a temporary
password to hand over. Then Staff → add their employee record with their pay
and NAPSA number, and link it to the sign-in so they can clock themselves in.

**Someone leaves**: disable their sign-in and mark the employee as no longer
employed. Never delete either; their past sales and payslips must stay readable.

**A forgotten password**: Sign-ins → Reset password. It also clears any lockout.

**Roles** decide what each person can reach. Change the role, not the person.

## What only you can do

- Refund or cancel an order after payment.
- Change prices and the menu.
- Approve journal entries, payroll and leave.
- See the books, the reports and the activity log.

A cashier can do none of these, by design.

## Watch for

- **A till that is short more than once.** The activity log shows who, when,
  and by how much.
- **Refunds.** Each one is recorded with a reason and the person who gave it.
- **Stock that keeps going negative.** Usually a recipe that does not match
  what the kitchen actually uses.
- **Prices changed without a reason recorded.** Every change asks why.

## If something breaks

1. Check the backend window is still running.
2. Restart with `.\scripts\run.ps1`, or `.\scripts\serve.ps1` for the installed
   setup.
3. The day's figures are safe; everything is written as it happens.

Keep a backup off the computer. A disk that fails takes its own backups too.


## Comparing with the last period

**Sales analytics** now puts a small pill beside each figure: *▲ 12%* means up
on the same number of days just before, *▼ 8%* means down. Cancelled orders are
the one figure where up is bad, so that pill turns red when they rise.

## Light or dark

Each screen can choose its own colours. The round button beside your name, at
the bottom of the sidebar, cycles through **match Windows**, **always light**
and **always dark**. It is remembered on that computer only, so the kitchen
wall can stay dark while the counter stays light.

## When the system will not open

On the server computer, open PowerShell in the project folder and run:

    .\scripts\status.ps1

It says, in plain words, whether the system is running, whether two copies are
fighting over the same port, whether the database is answering, and shows the
last lines of `logs\server.log`. If it says PostgreSQL *refuses the password*, run
`.\scripts\fix-database.ps1` and enter the `postgres` password chosen when
PostgreSQL was installed. Otherwise, send that output to whoever looks after
the system and they will know where to start.

## Nobody can sign in

If the owner's password is forgotten, or the account is locked after wrong
tries, run this on the server computer, in the project folder:

    .\scripts\reset-owner.ps1

It prints a temporary password. Sign in with it and choose a new one. For a
staff member's account, the owner can reset it from **Staff & roles**. If
that isn't possible, add their email after the command.

## Everyone's first screen

Each account opens on a screen for its own job:
- owner and manager: the Overview, with the month so far, the team today,
  the store room and the system below it;
- accountant: **Money**;
- cashier: **My till**;
- kitchen: the kitchen display.

The old Administrator accounts became Manager accounts, and Inventory staff
became Kitchen accounts (the kitchen can now adjust stock).

A new role you create is placed by its permissions.

## An account for every kind of staff

To get one account for each kind (the second owner, manager, accountant,
cashier and kitchen), run this on the server computer:

    .\scripts\starter-accounts.ps1

It prints each new account's email and temporary password once, so write them
down. Then rename each account to the real person under **Staff & roles**.

## The menu

The printed menu is loaded: bowls, burritos, breakfast, dips and drinks, at
the printed prices. Check three things on the Menu screen: the build-your-own
bowl price (K75 assumed), the topping list, and ingredient costs (estimates).
To load the printed menu again, for example after a mistake, run
`.\scripts\load-menu.ps1`. It switches off anything not on the printed menu
and deletes nothing.

## Waiting for you

Your home starts with **Waiting for you**: payments to match, cash moves to
confirm, tills to review, tills left open more than 16 hours, journals, leave
and payroll waiting. Each one links to where you deal with it.

## Approving at the till

When a cashier gives a big discount or asks for a refund, the till shows an
approval box. Type **your own** email and password there, on the till. Never
give your password to a cashier. Wrong passwords count toward the lockout.

## Mobile money: matching payments

Payments the cashier did not confirm are *pending*. Every day, open
**Payments**, and under **To match against the statement** compare each one with the
operator's statement: **Arrived** or **Did not arrive**. One that did not
arrive shows the order as owing again, and the books are corrected.

## Tills and cash moves

On **End of day**:
- **Till counts to review**: each till that was out by more than the limit, with the
  cashier's note. Talk it through, write what you found and mark it reviewed.
  Repeated shortages are a pattern to look into, not proof of theft.
- **Cash moves to confirm**: drops to the safe, petty cash and cash added.
  Confirm what you saw; reject what you didn't (the books are corrected).

You can't review your own till or confirm your own cash move.

## Limits and tax (Settings)

- **Cash controls**: how far a till can be out before a note is needed (K20)
  and the biggest discount a cashier gives alone (10%).
- **Tax**: the VAT registered switch and the rate. Only the owner should
  change it, and only on the accountant's advice.

## The two owners

Both owners have full access. Neither can switch off or demote the other;
that protects each of you. A password reset or switching an account off signs
that person out everywhere at once.

## The team (stage 23)

**Setup → Team** shows everyone with an account. Each person shows:
- **Online / Away / Connection lost / Offline**: from their screen's
  heartbeat;
- **On duty / Off duty / On leave**: from clocking only.

The two are separate on purpose. Offline does not mean absent; a dropped
network or load shedding shows as *Connection lost*. Tap a person for their
profile: activity, attendance and tills, permissions, and (owners only)
sign-in history and devices.

From a profile, owners can:
- change the role;
- suspend or restore access (with a reason);
- reset the password;
- sign out one device or all of them;
- reset two-step sign-in for a lost phone;
- archive someone who has left (their records stay).

Neither owner can suspend, demote or archive the other.

**Team status** on the owner's Overview counts who is online, away, offline,
on duty, on leave and suspended.

## Locking the counter computer

Menu (your picture, top right) → **Lock screen**, or it locks by itself after
10 minutes untouched (Settings → Shared screens). Only your password unlocks
it. Someone else taps **Switch person** and signs in as themselves; anything
in your till basket waits for you. The kitchen display never locks itself.

## Two-step sign-in for the owners

Owner accounts must use a code from an authenticator app on the phone
(Google Authenticator, Microsoft Authenticator or Authy). After test mode is
switched off, each owner is asked to set it up at their next sign-in:
1. Scan the QR code with the app.
2. Type the code the app shows.
3. **Write down the eight recovery codes.** They are shown only once.

If an owner loses their phone, they sign in with a recovery code. If those are
lost too, run `.\scripts\reset-owner.ps1` on the server computer.

## Notices

The bell, top right, shows account and security notices: new accounts,
suspensions, role changes, repeated wrong passwords, new devices. Choose which
ones you get under **Notification preferences**.
