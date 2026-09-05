"""
Generates settlements.csv — a simulated Razorpay-style settlement report.

This represents what actually landed in the merchant's bank account, to be
reconciled against what SHOULD have landed (paid invoices + successful
transactions in invoices.csv / transactions.csv).

Intentional exceptions are baked in so the reconciliation demo has real
mismatches to find:
  - a few paid invoices / successful transactions with NO matching settlement
    (money expected but never arrived / not yet settled)
  - a few settlements with an amount that doesn't match the expected amount
    (gateway fee deducted incorrectly, partial settlement, etc.)
  - one duplicate settlement (same reference_id settled twice)
  - one orphan settlement (money arrived with a reference_id that matches
    nothing in our records — e.g. a manual/offline payment)

Run: python generate_settlements.py   (run AFTER generate_data.py)
"""
import csv
import random
from datetime import date, timedelta

random.seed(7)

invoices = []
with open("invoices.csv") as f:
    for row in csv.DictReader(f):
        if row["status"] == "paid":
            invoices.append(row)

transactions = []
with open("transactions.csv") as f:
    for row in csv.DictReader(f):
        if row["status"] == "success":
            transactions.append(row)

settlements = []
settlement_counter = 1

def add_settlement(reference_id, amount, settle_date):
    global settlement_counter
    settlements.append({
        "settlement_id": f"SETL{settlement_counter:04d}",
        "reference_id": reference_id,
        "amount": amount,
        "settlement_date": settle_date.isoformat(),
    })
    settlement_counter += 1

# --- Invoices: settle most paid invoices correctly, a few days after paid_date ---
skip_invoice_indices = set(random.sample(range(len(invoices)), k=min(2, len(invoices))))  # missing settlement
mismatch_invoice_indices = set(random.sample(
    [i for i in range(len(invoices)) if i not in skip_invoice_indices], k=min(2, len(invoices))
))  # amount mismatch

for i, inv in enumerate(invoices):
    if i in skip_invoice_indices:
        continue  # simulate: paid but not yet settled / settlement missing
    paid_date = date.fromisoformat(inv["paid_date"])
    settle_date = paid_date + timedelta(days=random.randint(1, 3))
    amount = int(inv["amount"])
    if i in mismatch_invoice_indices:
        amount = amount - random.choice([500, 1000, 1500])  # simulate fee deduction error
    add_settlement(inv["invoice_id"], amount, settle_date)

# --- Transactions: settle most successful ones correctly ---
skip_txn_indices = set(random.sample(range(len(transactions)), k=min(2, len(transactions))))
mismatch_txn_indices = set(random.sample(
    [i for i in range(len(transactions)) if i not in skip_txn_indices], k=min(1, len(transactions))
))

for i, txn in enumerate(transactions):
    if i in skip_txn_indices:
        continue
    ts = date.fromisoformat(txn["timestamp"][:10])
    settle_date = ts + timedelta(days=random.randint(1, 2))
    amount = int(txn["amount"])
    if i in mismatch_txn_indices:
        amount = amount - random.choice([10, 20, 30])
    add_settlement(txn["transaction_id"], amount, settle_date)

# --- Duplicate settlement: re-settle one already-settled invoice ---
if invoices:
    dup = invoices[0]
    add_settlement(dup["invoice_id"], int(dup["amount"]), date.fromisoformat(dup["paid_date"]) + timedelta(days=5))

# --- Orphan settlement: money arrived with no matching record at all ---
add_settlement("MANUAL-BANKXFER-001", 12000, date(2026, 8, 20))

with open("settlements.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["settlement_id", "reference_id", "amount", "settlement_date"])
    writer.writeheader()
    writer.writerows(settlements)

print(f"Generated {len(settlements)} settlements "
      f"({len(skip_invoice_indices)} missing invoice settlements, "
      f"{len(mismatch_invoice_indices)} invoice amount mismatches, "
      f"{len(skip_txn_indices)} missing txn settlements, "
      f"{len(mismatch_txn_indices)} txn amount mismatches, "
      f"1 duplicate, 1 orphan)")
