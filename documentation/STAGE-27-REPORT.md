# Stage 27: installable app and offline cash sales

Version 1.27.0. Stage 26 (Lenco) is waiting for sandbox keys. Email and
two-step sign-in (stage 25) are built, but switching them on is now the last
step before go-live, as you asked. Test mode stays on until then.

## The till keeps selling when the connection drops

If the till cannot reach the server (Wi-Fi down, cable out, server computer
off, power cut at the router), it keeps taking **cash** sales:

1. A yellow bar across the top says so: "No connection to the server... The
   till keeps taking cash sales on this device."
2. The till shows **Offline**: cash only, at the menu prices it last loaded,
   with the time those prices were loaded.
3. The cashier builds the order as usual and presses **Take cash (offline)**,
   types the cash given if they want the change worked out, and presses
   **Take cash**.
4. The sale is saved on that device **before** the receipt shows. If the
   device could not save it, the till says so and the sale is not taken.
5. The receipt has a short number like **T-3 (offline)**. Print it; the
   kitchen works from the paper until the connection is back, because the
   kitchen screen cannot see the sale yet.
6. When the server answers again, the waiting sales are sent by themselves,
   oldest first, within seconds. The till goes back to normal on its own.

Each sale becomes an ordinary paid order with a real number. Stock, the
books and the till's takings all follow, dated when the customer paid, not
when the network came back. A sale from the last 20 minutes goes on the
kitchen screen as normal; an older one is recorded as already served, so the
board does not fill with food that went out an hour ago.

### What cannot happen

- **No sale counted twice.** Each sale gets its own id on the device before
  anything is sent. The server records an id once, enforced in the database
  itself, so a retry, a dropped reply or a second tab still makes one order.
- **No sale lost quietly.** A sale only leaves the device after the server
  has confirmed it has it. Closing the browser or restarting the computer
  keeps it.
- **No closing the till with sales still waiting.** The Close the till
  button is held until they are sent.
- **No sale on the wrong till.** It goes on the till of the person who took
  it. If someone else signs in on that device, their sales wait for them,
  and the bar says so.

### What is switched off while offline, and why

Discounts, promotion codes, stamp cards, mobile money and card all need the
server to decide or match, so the till refuses them offline and says why.
Changing a held order, cash drops and closing the till also wait.

### When the menu changed in between

The customer paid what the till asked; that stands. The server prices the
order again from today's menu:

- If today's price is **higher**, the difference is recorded as an
  "offline price difference", visible on the order.
- If today's price is **lower**, the order takes today's price and the
  extra cash is named, so the drawer and the books still agree.

Both owners get a notice either way, and the cashier sees a "check this"
note on the till. An item sold out or switched off since does not undo a
sale that already happened.

### When the server refuses one

Rare: a sale more than a week old, a till that belongs to someone else, or an
item deleted from the menu entirely. The sale stays on the device under
**Offline sales the server could not take**, with the reason. A manager
enters it by hand, then presses **Entered by hand, set aside** (only someone
who can review till counts can do that). **Try again** sends it again after
the cause is fixed.

### What offline needs

The till must have been opened **once with the connection up** on that
device that day, so it has the menu and knows whose till is open. A device
that has never loaded the menu says so instead of guessing. Someone already
signed in stays signed in; signing in fresh needs the server.

## Installable app

The system can now be installed like an app, from the browser:

- **Chrome or Edge on the counter computer**: the install icon at the right
  of the address bar, or menu → Install The Green Buffet.
- **Android phone or tablet**: menu → Add to home screen / Install app.
- **iPhone or iPad (Safari)**: Share → Add to Home Screen.

It opens in its own window with the logo, without the browser's bars. Every
screen is kept on the device after the first visit, so the system opens even
with the connection down. An update shows the next time the page is opened
with the connection up; nothing is cached from the API, so prices, sales and
sign-in always come from the server.

Browsers only allow installing and offline loading on `https://` addresses
or on the computer running the system (`localhost`). Tablets reaching the
counter computer by its network address (`http://192.168...`) get offline
**sales** but not offline **loading** of a fresh page; that arrives with
https at go-live (stage 29).

## Not in this stage

- **Push notifications** to phones need https and a push service; moved to
  29. Notices in the system and by email work.
- **Offline for anything but cash sales**: reports, stock, books and the
  kitchen screen need the server, and say so.

## Tests

| Suite | Result |
|---|---|
| `tests/test_offline.py`: becomes a paid order with kitchen, stock and books; the same sale sent three times records once; price higher and lower since; sold out since; someone else's till refused; future and week-old dates refused; cash given below the total refused; an old sale kept off the kitchen board; a sale arriving after its till closed; discounts ignored; needs till permission and sign-in | 12 passed |
| All earlier suites (money flows, security, profiles, IT, email) | 103 passed |
| `probe_customer_security.py` | 29 passed |
| Browser, with the server really switched off and on again: app installs its worker and manifest; till reopens after a reload with the server off; sale taken, change shown, T- receipt; waiting count shown; server back: sale sent once, till back to normal, takings right | 11 / 11 |
| Screen sweep: 57 screens × phone and desktop × light and dark | 228 / 228 clean |
| IT integrity checks after offline sales | No new findings |
