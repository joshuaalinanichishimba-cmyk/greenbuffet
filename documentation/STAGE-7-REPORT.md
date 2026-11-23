# Stage 7 report — the books

Three new tables and a chart of accounts. `.\scripts\update.ps1` creates them
and loads the chart; nothing already recorded is touched.

## Proper double entry

Everything that reaches the ledger goes through one function, which refuses any
entry whose debits and credits do not match. That single check is what keeps
the trial balance at zero no matter what else happens in the system.

A posted entry is never edited. A mistake is reversed by a second entry that
mirrors the first, and **both stay in the books** — together they come to
nothing, which is what a reversal means.

## The books write themselves

| When | What is posted |
| --- | --- |
| An order is paid | Money into the account for each method used; sales and VAT out |
| The same order's food | Cost of food sold up, stock on hand down |
| A refund | Sales and VAT reduced, money out of the same account |
| A delivery is checked in | Stock on hand up, money owed to the supplier up |
| Stock is wasted | Wasted stock up, stock on hand down |
| A till is counted | The over or short against its own account |

A sale of K135 including K18.62 of VAT posts as: cash in the drawer K135 debit,
food and drink sales K116.38 credit, VAT owed to ZRA K18.62 credit — and
separately, cost of food sold K29.18 against stock on hand. Both entries carry
the order number, so any figure in a statement traces back to its receipt.

Each payment method has its own account — cash, Airtel Money, MTN MoMo, Zamtel
Kwacha, card settlements — so mobile money can be matched against the
operators' own statements rather than being lumped in with the drawer.

**The books never stop the till.** If an entry cannot be written for any
reason, the sale still stands and the gap shows in the trial balance. Losing a
sale because the ledger objected would be the worse failure.

## What you can do

**Books** (`/books`) — profit and loss, balance sheet, where the money moved,
and the trial balance, each for a chosen month. The balance sheet and the trial
balance say plainly whether they balance, and by how much if not.

**Journal** (`/books/journal`) — every entry with its lines, filtered by where
it came from. Hand-written entries for rent, electricity, a bank charge or the
owner putting money in: the form refuses to submit until debits equal credits
and shows what it is out by while you type.

The chart of accounts tab lists all 36 accounts with their balances, and
"Ledger" opens any account's running history.

## Two people, not one

A hand-written entry is saved as a draft and must be approved by **someone
other than whoever wrote it** before it reaches the books. The owner writing an
entry and then approving it is refused with that in plain words. This is the
ordinary control that stops one person both creating and blessing a figure.

Entries the system writes for itself are posted directly — they come from a
receipt or a delivery note, which is the evidence.

## The chart of accounts

36 accounts for a small restaurant: the drawer, the bank, an account per mobile
money operator, card settlements, money owed to and by the business, stock,
equipment, VAT, PAYE, NAPSA and NHIMA, sales, cost of food, waste, and the
running costs a Liberty Mall restaurant actually has — rent, electricity, gas,
packaging, cleaning, bank charges, licences.

Accounts can be added. The ones the posting rules need are marked system and
cannot be switched off, and no account with entries against it can be removed,
because the record has to stay readable.

## Rules

| Rule | Result |
| --- | --- |
| Debits that do not equal credits | 422, with the difference |
| An account code not in the chart | 422 |
| A line with both a debit and a credit | 422 |
| Approving your own entry | 409 |
| Approving something already posted | 409 |
| Reversing a draft, or reversing twice | 409 |
| Reversing a reversal | 409 |
| Switching off a system account | 409 |
| Switching off an account with entries | 409, with the count |
| A cashier opening the books | 403 |

## Tested

Against PostgreSQL: a sale, its cost of food, a delivery, a hand-written rent
entry refused to its own author then approved by the accountant, a reversal,
and both statements checked for balance after each. In the browser: all four
statements, the out-by figure while typing an unbalanced entry, the disabled
write button, the approval refusal, the source filter, the chart and a ledger.
No horizontal scrolling at 390 px.

## The bug this stage found

A reversal originally marked the original entry as "reversed" and dropped it
from the ledger. The mirror then stood alone, and every statement moved by its
value — the reversed rent showed as **negative** K4,500 of costs. Both entries
now stay posted and net to zero. Caught by reading the profit and loss rather
than the tests: a restaurant cannot have negative running costs.

## Not in this stage

- **Paying suppliers.** The books record what is owed; marking an invoice paid
  and the creditors ageing that goes with it is small and can follow.
- **Depreciation.** The accounts are there; the monthly run belongs with the
  fixed asset register.
- **Statements as PDF or Excel.** That is stage 9, with the rest of the
  reporting.
