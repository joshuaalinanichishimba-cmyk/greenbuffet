# Stage 23: profiles, online status, the team directory and account security

Built on what was already there: the user accounts, the staff list, clocking,
leave, the till shifts, the sign-in records and the audit log. Nothing was
duplicated. The Activity tab reads the existing records; it does not keep a
second copy.

## What each person now has

**A profile** (avatar, top right → *My profile*). It shows:
- the photograph, or the person's initials if there is none;
- name, staff number, job title, role and department;
- phone and email;
- employment status, account status, online status and last active time;
- the current shift (clocked in, till open);
- when the account was made and by whom;
- responsibilities, taken from the role's permissions.

People can change their own photograph, phone, password and notices. They
cannot change their role, pay, staff number or employment status. The server
does not accept those fields from a person's own profile at all.

**The account menu** sits top right on every screen, including the kitchen
display. It holds:
- My profile, Account settings, Security settings, Notification preferences
  and My activity;
- Lock screen and Sign out;
- a bell beside it for notices.

## Online status

Each open screen sends a heartbeat every 30 seconds. The heartbeat says only
two things: the screen is there, and whether anyone touched it. Nothing about
what was typed or shown is sent.

| Status | Means |
|---|---|
| Online | A screen answered in the last 90 seconds and was used within the away time (5 minutes; Settings) |
| Away | A screen is answering but untouched, or it is locked |
| Connection lost | Signed in, but the screen stopped answering 90 seconds to 30 minutes ago: network, load shedding, a closed laptop |
| Offline | Signed out, the page was closed, or nothing for 30 minutes |
| Unknown | Signed in, but the screen has never sent a heartbeat (a sign-in from before this update, or a script) |

Being signed in is never treated as being online. When the network or power
comes back, the next heartbeat brings the status straight back. While a screen
cannot reach the server it shows a "Reconnecting" strip; what is on screen is
kept.

**Online is not attendance.** *On duty* comes from clocking in only. Someone
can be on duty with the network down, or signed in on a day off. Being offline
is never counted as absence or lateness.

## Team directory (Setup → Team)

Owners and managers see everyone with an account. Each person is shown with
their photo, name, job, department, online status, last active time, shift
and account status.

The directory can be searched, and filtered to: everyone, online, away,
offline, on duty, off duty, owners, managers, cashiers, kitchen, accountants
and suspended. Archived accounts are hidden unless "Show archived" is ticked.

## Someone else's profile

The tabs a viewer sees depend on their permissions, and the server refuses the
rest.

| Tab | Who sees it |
|---|---|
| Overview | Anyone allowed to open the profile |
| Activity | The person, owners, managers |
| Attendance & shifts | The person, owners, managers, HR |
| Roles & permissions | The person, owners, managers |
| Sign-in history | The person, owners only |
| Devices | The person, owners only |
| Employment | The person, HR (owners and managers) |
| Pay & documents | The person, payroll (owners, managers, accountants) |
| Security | The person, owners only |

**Activity** comes from the business records and the audit log, matched by
the name on the account. Each role's own kind of work comes first:
- **Counter:** takings, orders, discounts, refunds, reprints, tills opened and
  closed, till counts, cash drops.
- **Kitchen:** tickets started and marked ready, waste, stock counts.
- **Manager:** approvals, stock adjustments, purchases, staff changes,
  settings.
- **Accountant:** journals, payments confirmed, suppliers paid, payroll.
- **Owner:** price changes, permission and account changes, payroll rates.

**What owners can do from a profile:**
- change the role;
- suspend (with a reason) and restore;
- reset the password;
- sign out one device or every device;
- reset two-step sign-in for a lost phone;
- archive someone who has left.

Archiving switches the account off and hides it from the directory. Nothing
they did is removed.

The existing two-owner protection stays. Neither owner can suspend, demote,
archive or reset the two-step sign-in of the other. Either owner may sign the
other out of their devices (that is how a stolen phone is stopped), and the
other owner is told.

## Devices and sessions

Every sign-in is now a separate session for one device, so one device can be
signed out without touching the others. Each person can see and sign out their
own devices. Owners can do the same for anyone.

These all end sessions at once:
- suspending, archiving or changing the role;
- a password reset, or the person changing their own password (their other
  devices only).

## Security

**Two-step sign-in.** A six-digit code from an authenticator app (Google
Authenticator, Microsoft Authenticator or Authy), as well as the password.
- Setup is by QR code, or by typing the key.
- Eight recovery codes are shown once, for a lost phone. Each works once.
- It is **required for both owner accounts.** An owner without it is sent
  straight to set it up, and the server refuses everything else until it is
  on. The one exception is test sign-in mode on a development machine.
- Anyone else may switch it on.
- `reset-owner.ps1` now also turns two-step off, for an owner who has lost
  their phone. They set it up again straight after signing in.

The Security tab also has: change password, sign out other devices, sign-in
history and security notices.

**Notices.**
- **Both owners are told** when an account is made, suspended, restored or
  archived; when a role or a role's permissions change; when an account locks
  after 5 wrong passwords or codes; when someone's security settings change;
  and when an owner signs in on a new device.
- **The person themselves is always told** about a sign-in on a new device, a
  password change, a recovery code being used, two-step being turned on, off
  or reset, and their devices being signed out by someone else.
- People can switch off the owner notices they do not want. Security notices
  about their own account cannot be switched off.
- Going online or offline is never a notice.

## Shared counter computers

- **Lock screen** (menu → Lock screen, or automatically after 10 minutes
  untouched; Settings).
  - It covers the screen without closing anything.
  - The server refuses the locked session's requests, so the cover cannot be
    got round.
  - Only the same person's password unlocks it. Five wrong tries sign the
    device out.
  - The kitchen display never locks itself.
- **Switch person.** The locked session is signed out, and the next person
  signs in as themselves. Every sale is in the name of whoever made it.
- **The till basket is kept per person.** An unfinished order stays on that
  computer under its owner's account, and comes back when they sign in again.
  It is only a draft: nothing reaches the server until the order is placed, so
  nothing is charged twice or put under someone else's name. Baskets older
  than 12 hours are dropped.

## Audit log

The audit log now records:
- signing in (with device), signing out, switching person, locking and
  unlocking;
- own profile changes (old and new values);
- photograph changes;
- suspensions, restorations and archiving (with reasons);
- signing devices out remotely;
- two-step on, off and reset;
- recovery codes used and replaced;
- sign-in lockouts.

Passwords, codes, secrets and tokens are never written.

## Privacy

There is no webcam, screen recording, keystroke logging, GPS, personal-device
tracking or reading of anyone's messages.

The only things kept about a device are:
- its kind (computer, phone or tablet);
- the browser name;
- the network address;
- when it was last seen and last used.

A pay account number shows only its last four digits.

## Database changes (added only)

- **New tables:** `user_sessions` and `notifications`.
- **New columns on `users`:** `phone`, `photo_id`, `preferences`,
  `suspended_reason`, `archived_at`, `totp_secret`, `totp_enabled`,
  `recovery_codes`.
- **New column on `login_attempts`:** `device`.
- **New permissions:**
  - `team.view`, given to owners and managers;
  - `security.manage`, given to owners.
- **New settings:**
  - `presence.away_minutes`, 5;
  - `lock.after_minutes`, 10.

## Also fixed

- **Adding someone to the staff list could fail** with "Something went wrong"
  when the staff-number counter was behind numbers already used. It now skips
  to the next free number. It also refuses to link one account to two staff
  records.
- **Outline and red buttons had lost their borders on every screen.** A
  shared rule was clearing them; they are drawn as in the demo again.

## Tests

| Suite | Result |
|---|---|
| `tests/test_profiles.py` (new): one test for each line of the brief's testing list, plus two-step, owner two-step required, notices and the Team status figures | 16 passed |
| Money flows, security | 54 passed |
| Role and removed-feature probes | 29 passed |
| Browser run-through: Team status, account menu, directory filters, profile, remote sign-out, suspend and restore, two-step QR, lock and unlock (server refuses with 423), reconnecting strip, notices bell, two-step sign-in with a code, kitchen board menu | 21 / 21 |
| Screen sweep: 45 screens (20 new) × phone and desktop × light and dark | 180 / 180 clean |
| Each role's home, phone and desktop; stage 22 till run-through | Pass |

All of it was run on a test database here. Your live data was not touched.

## Known limits

- **Activity is matched by the name on the account,** because that is how the
  older records were kept. Work done before someone's name was changed is not
  counted under the new name. The tab says so.
- **Not shown on the Activity tab:** "Orders accepted", "production records"
  and "operational checklists". The system has no such records, so nothing is
  invented. (The counter has no accepting step, since orders go to the
  kitchen at payment.)
- **Sign-ins from before this update** show as *Unknown* until those people
  sign in again (at most 8 hours).
- **Two-step for both owners starts when test sign-in mode is switched off**
  (`test-sign-in.ps1 -Off`). Have your phone ready.
- **Password recovery** is a temporary password from an owner or manager, or
  `reset-owner.ps1` on the server computer. There is no recovery by email,
  because the system sends no email.
- **Notices appear in the system only,** on the bell and the Notifications
  tab. They are not sent by SMS or email.
