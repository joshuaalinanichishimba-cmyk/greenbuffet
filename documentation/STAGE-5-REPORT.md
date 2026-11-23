# Stage 5 report — the kitchen display

One new table, nothing existing altered, so `.\scripts\update.ps1` is all an
installed copy needs.

## What the kitchen sees

A board in three columns — New, Being made, Ready to hand over — with the
oldest ticket first, because that is the order the kitchen works in. Each
ticket shows the order number, whether it is takeaway, eat in or delivery, the
customer's name if one was taken, every item with its choices, and any note the
cashier typed. One button moves the whole ticket on: Start, Ready, Handed over.
Once handed over it leaves the board.

A ticket turns amber after eight minutes and red after fifteen, with the
waiting time counted in the browser so it keeps climbing between refreshes.

The station buttons — Kitchen, Cold station, Juice bar — filter the board to
one screen's work, using the station already recorded against each menu item.

## Live, with a safety net

Orders reach the board the moment they are paid. The screen holds a WebSocket
to the backend and refreshes when it hears that something changed; the header
says "Live" when that connection is up.

Underneath it, the board also asks for the tickets on a timer — every ten
seconds while live, every five when not — and tries to reconnect. A kitchen
screen that has silently stopped updating is worse than one that is a few
seconds behind, so the poll runs either way rather than trusting the socket.

The WebSocket carries the same sign-in token as everything else, passed as a
query parameter because a browser cannot set headers on a socket. It is checked
the same way, and the socket is closed on anyone not allowed to see orders.

## Why a separate table

A kitchen item is its own row rather than extra columns on the order. That
means an installed copy gains this stage by creating one table, with nothing
that holds money touched, and it leaves room for each step to carry its own
time — started, ready, handed over. Stage 9 can then report how long food
actually takes instead of guessing.

The item also copies the name, choices and note from the order line, so the
board reads without joining back to the menu, and a dish renamed next month
does not rewrite tickets from today.

## Rules

| Rule | Result |
| --- | --- |
| An unpaid order | Not on the board; it arrives when payment completes |
| The same order paid twice (a retry) | One set of tickets, not two |
| A ticket with one item ready and one still cooking | Stays in Being made until all are done |
| An unknown step, or an unknown station | 422 |
| A ticket already handed over | 404 when touched again |
| Kitchen staff taking an order at the till | 403 |
| A WebSocket with no token, or one from a disabled account | Closed immediately |

Kitchen staff, cashiers and anyone with `orders.view` can read the board; that
includes the accountant role, which already sees orders.

## Tested

Against PostgreSQL and in two browser tabs at once: a till in one, the board in
the other. An order paid at the till appeared on the board without a reload,
moved through Start, Ready and Handed over, left the board, and the station
filters separated the bowl from the smoothie. Every rule above was checked. No
horizontal scrolling at 390 px.

## Not in this stage

- **A bell or a sound** when an order arrives. Worth adding once the screen is
  actually in the kitchen and you know whether it would be heard or ignored.
- **Returning an item to an earlier step.** The buttons only move forward; a
  mistake is fixed by handing over and taking a new order, which is rare enough
  to leave until someone asks.
- **Stock coming out as items are made.** That is stage 6, which is next.
