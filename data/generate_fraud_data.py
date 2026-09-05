"""
Generates fraud_transactions.csv — labeled synthetic data for the Risk
Manager scenario (Track 02).

Includes a ground-truth `is_fraud` column so precision/recall can be
genuinely measured against the detection logic, as the track requires.

Signals baked in (mirroring real fraud heuristics):
  - amount_ratio: transaction amount vs. that customer's typical amount
  - velocity: how many transactions that customer made in the last hour
  - odd_hour: transaction happening at an unusual hour (1am-4am)

Fraud cases are constructed to trigger 1+ of these signals; normal cases
mostly don't, but a few "hard" cases are included on both sides (a normal
big purchase, a fraud case with none of the classic signals) so precision
and recall aren't trivially 100%.

Run: python generate_fraud_data.py
"""
import csv
import random
from datetime import date, datetime, timedelta

random.seed(11)
TODAY = date(2026, 8, 29)

CUSTOMER_IDS = [f"CUST{i:03d}" for i in range(1, 16)]
# each customer has a "typical" order amount
CUSTOMER_AVG = {cid: random.choice([499, 899, 1299, 2499, 3999]) for cid in CUSTOMER_IDS}

rows = []
txn_counter = 1

def add_row(customer_id, amount, hour, txns_last_hour, is_fraud, day_offset):
    global txn_counter
    ts = datetime.combine(TODAY - timedelta(days=day_offset), datetime.min.time()) + timedelta(hours=hour, minutes=random.randint(0, 59))
    rows.append({
        "transaction_id": f"FTXN{txn_counter:04d}",
        "customer_id": customer_id,
        "amount": amount,
        "timestamp": ts.isoformat(),
        "customer_avg_amount": CUSTOMER_AVG[customer_id],
        "txns_last_hour": txns_last_hour,
        "hour_of_day": hour,
        "is_fraud": is_fraud,
    })
    txn_counter += 1

# --- Normal transactions (~35) ---
for _ in range(35):
    cid = random.choice(CUSTOMER_IDS)
    avg = CUSTOMER_AVG[cid]
    amount = round(avg * random.uniform(0.7, 1.4))
    hour = random.choice(list(range(7, 23)))  # normal daytime hours
    add_row(cid, amount, hour, txns_last_hour=random.choice([1, 1, 2]), is_fraud=0, day_offset=random.randint(0, 20))

# --- Clear fraud cases (~10): high amount ratio + odd hour + high velocity ---
for _ in range(10):
    cid = random.choice(CUSTOMER_IDS)
    avg = CUSTOMER_AVG[cid]
    amount = round(avg * random.uniform(4, 9))  # big spike vs typical
    hour = random.choice([1, 2, 3, 4])
    add_row(cid, amount, hour, txns_last_hour=random.choice([3, 4, 5]), is_fraud=1, day_offset=random.randint(0, 20))

# --- Hard case: normal big purchase (looks risky, but isn't fraud) ---
for _ in range(3):
    cid = random.choice(CUSTOMER_IDS)
    avg = CUSTOMER_AVG[cid]
    amount = round(avg * random.uniform(3, 4))  # somewhat elevated but genuine
    hour = random.choice(list(range(10, 20)))
    add_row(cid, amount, hour, txns_last_hour=1, is_fraud=0, day_offset=random.randint(0, 20))

# --- Hard case: fraud with no classic signals (small amount, normal hour, low velocity) ---
for _ in range(2):
    cid = random.choice(CUSTOMER_IDS)
    avg = CUSTOMER_AVG[cid]
    amount = round(avg * random.uniform(0.8, 1.1))  # blends in
    hour = random.choice(list(range(10, 18)))
    add_row(cid, amount, hour, txns_last_hour=1, is_fraud=1, day_offset=random.randint(0, 20))

random.shuffle(rows)
# reassign transaction_ids in shuffled order for a clean sequence
for i, row in enumerate(rows, start=1):
    row["transaction_id"] = f"FTXN{i:04d}"

with open("fraud_transactions.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)

fraud_count = sum(r["is_fraud"] for r in rows)
print(f"Generated {len(rows)} transactions ({fraud_count} labeled fraud, {len(rows)-fraud_count} labeled normal)")
