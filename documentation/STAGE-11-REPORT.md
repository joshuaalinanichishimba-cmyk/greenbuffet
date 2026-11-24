# Stage 11 report — security review, testing and load

No new features. One new table (`counters`), a test suite, and three real bugs
found and fixed.

## How the review was done

Every endpoint in the system — 100 of them — was called twice: once with no
token at all, and once as a cashier. Anything that answered with something
other than "refused" was read line by line to decide whether a cashier should
have been able to reach it.

Then the token itself was attacked, the login box was fed SQL, and the whole
thing was put under a simulated lunch rush.

## What held

| Attack | Result |
| --- | --- |
| Any of the 100 protected endpoints with no token | Refused, every one |
| A token with the account changed inside it | 401 — the signature no longer matches |
| A token with its algorithm set to "none" | 401 |
| A token signed with a different key | 401 |
| An expired token | 401 |
| `' OR 1=1 --` and friends in the login box | 401, and the users table intact |
| SQL in the menu search box | Treated as text, no rows |
| A disabled account still holding a valid token | Refused on the next request |
| A cashier trying to promote themselves | 403 |

Permissions are read from the database on every request, not from the token, so
disabling someone or changing their role takes effect immediately rather than
whenever their eight hours run out.

## Three bugs found

**A cashier could read every stored document.** The file endpoints allowed
anyone who could use the till, because the till needs dish photographs. That
also let a cashier list and open supplier contracts, employee certificates and
anything else kept in the system. Now a cashier sees dish photographs and
nothing else; the paperwork needs a role whose work involves it.

**Two tills taking an order at the same moment got the same order number.**
The number was made by counting the orders that already existed and adding one,
which is correct exactly until two people do it at once. Under the simulated
rush, **56 of 60 sales failed**. The same flaw sat in journal entries, purchase
orders and employee numbers.

A single-user test would never have shown this. It is the kind of bug that
appears on the busiest day of the year and not before.

Numbers now come from a counter the database updates in one statement, so two
tills asking together get different numbers.

**Filenames went into a response header unchecked.** A file named with the
right characters could have broken the header it was written into. Names are
now stripped to letters, digits and ordinary punctuation.

Also tidied: idempotency keys were kept for ever and are now cleared after a
day, and security headers (`X-Content-Type-Options`, `X-Frame-Options`,
`Referrer-Policy`, `Permissions-Policy`, and HSTS outside development) are sent
on every response.

## A false start worth recording

The first fix gave the counter its own database connection, so the lock would
be released immediately. That made things worse: every request then needed two
connections at once, the pool emptied, and the whole system stopped answering —
60 of 60 sales timed out.

The counter now runs on the request's own connection. The lock is held for the
few milliseconds the order takes, which is nothing next to how long a customer
takes. The connection pool was also raised from five to ten, with twenty more
under pressure, because a restaurant has several tills, a kitchen board and a
dashboard all talking at once.

## Under load

Sixty sales fired at once from six tills, with the kitchen board refreshing and
the dashboard open:

- 60 of 60 completed, no failures
- 11 complete sales a second
- The kitchen board stayed under half a second, the dashboard under 1.2 seconds
- The trial balance and balance sheet still balanced afterwards
- No duplicate order numbers

At a human pace — three tills, five sales each, with a pause between — one sale
from first tap to receipt takes **136 milliseconds**. Everything else:

| | |
| --- | --- |
| Kitchen board | 9 ms |
| Stock levels | 7 ms |
| Trial balance | 8 ms |
| Menu | 12 ms |
| Dashboard | 23 ms |
| A PDF report | 22 ms |

The machine running this is an i5-4210U from 2014. A proper server will be
faster.

## The test suite

`backend/tests/test_security.py` — 32 tests covering everything in the table
above, plus the books balancing, the same order sent twice staying one order,
nobody approving their own journal entry, and the file rules.

    cd backend
    .\.venv\Scripts\python.exe -m pytest tests -q

Run it after any change. It takes about a second.

`backend/tests/load_test.py` is the lunch rush, run by hand when you want to
know whether the system still holds up. It takes real orders, so use a test
database or expect the day's figures to include them.

## Still worth doing before real money runs through it

- **Serve it over HTTPS** once it leaves this computer. Everything is plain
  HTTP on localhost today, which is fine while the browser and the server are
  the same machine and not fine the moment they are not. That is stage 12.
- **A limit on requests per minute**, beyond the five-failures lockout on
  sign-in. Not urgent on a shop counter; necessary on the open internet.
- **An independent security review** if the system ever handles card details
  directly. It does not today — card and mobile money are taken on the
  operator's own device and only the reference is recorded, which is
  deliberately the safer arrangement.
