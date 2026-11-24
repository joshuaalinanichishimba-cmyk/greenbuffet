# Stage 21 report: the look in dark mode, printing, and tap-and-Enter sign-in

Fixes from the screenshots taken on the counter computer, which runs Windows
in dark mode.

## 1. Dark mode, screen by screen

Several screens had colours fixed for a light screen. In dark mode they
showed white boxes with white writing, or pale writing on a white card. Every
fixed colour on every screen now follows the light or dark theme:

- **Choose a new password:** used to be a white card with invisible labels.
  It now matches the sign-in screen, with the logo on top.
- **Till, payment:** the payment-method buttons were white with white text.
  They are now rounded pills with a 44 px touch target, and the chosen one
  is green.
- **Kitchen display:** tickets were white with pale text. They are now light
  cards with dark writing in both themes, so they read the same from across
  the kitchen.
- Purchases, Payroll, Books, Journal, Reports, Roles, Menu, the item editor
  and Settings: highlighted rows, warnings and chips all follow the theme.
- White text on green buttons is now dark text in dark mode, where the green
  is brighter.
- The logo sits on a small cream plate on the sign-in and password screens,
  so its brown lettering shows on the dark background.

A sweep of all 25 screens in dark mode found no errors and no sideways
scrolling, on phone or desktop.

## 2. Receipts print on their own

Printing a receipt used to include the top bar and the menu button. Now any
printout from the system has no sidebar, top bar or dark background: just
the receipt, in black on white, 72 mm wide for an 80 mm till roll.

## 3. My clocking

A cashier who opened *Staff clocking* got "Cashier accounts cannot do this",
because that screen is the staff list. Anyone who clocks in but doesn't
manage staff (cashiers, the kitchen, the store room) now gets **My
clocking**: a Clock in / Clock out button and their own last two weeks. That
comes from the new endpoint `GET /api/v1/people/me`. If their account isn't
linked to anyone on the staff list yet, the screen says so.

## 4. Tap a card, press Enter

    .\scripts\test-sign-in.ps1        switch it on
    .\scripts\test-sign-in.ps1 -Off   switch it off

**For trying the system out.** Every active account gets the test password
`greenbuffet2026`. The sign-in screen then fills it in, so you tap a card
(and a name, if there are several) and press Enter, as in the demo. A yellow
"Test mode" note shows on the sign-in screen while it is on.

The script refuses to run on a computer set to production, and the server
never fills passwords in production, even if the switch was left on. Before
real use, switch it off and give each person their own password from Staff &
roles.

**Outside test mode**, a tap still fills the email and puts the cursor in
the password box. After signing in with a temporary password, the "current
password" box is already filled, so only the new password is typed.

## Checks

- Dark mode: the sign-in, password, till payment, kitchen and My clocking
  screens were checked by eye. All 25 screens were swept on phone and
  desktop.
- Tap Cashier, then Till Two, then Enter: signed in and landed on My till.
- The receipt print preview shows the receipt alone.
- The test script refused with `ENVIRONMENT=production`.
- 36 automated tests and 29 permission checks pass.

## Installing

    Expand-Archive green-buffet-stage21.zip -DestinationPath "D:\The Green Buffet" -Force
    cd "D:\The Green Buffet"
    .\scripts\update.ps1
    .\scripts\test-sign-in.ps1

No database changes.
