"""
Generates 3 CSVs for the Revenue Copilot demo:
- customers.csv     : customer profile + historical payment behavior
- invoices.csv       : B2B receivables (some overdue, some paid on time)
- transactions.csv   : B2C payments (some failed, some abandoned, some success)

Run: python generate_data.py
Outputs into ./ (same folder)
"""
import csv
import random
from datetime import date, timedelta

random.seed(42)
TODAY = date(2026, 8, 29)

# ---------------------------------------------------------------------------
# CUSTOMERS
# ---------------------------------------------------------------------------
CUSTOMER_NAMES = [
    "ABC Pvt Ltd", "Sunrise Textiles", "Metro Traders", "Kavya Enterprises",
    "Bluewave Retail", "Prakash & Sons", "Nova Garments", "Silverline Corp",
    "Ganga Distributors", "Orbit Supplies", "Vikram Traders", "Delta Fabrics",
    "Ritu Fashion House", "Anand Wholesalers", "Zenith Mart",
]

customers = []
for i, name in enumerate(CUSTOMER_NAMES, start=1):
    cust_type = "B2B" if i <= 10 else "B2C"
    avg_lag = round(random.uniform(0, 15), 1) if cust_type == "B2B" else 0
    lag_std = round(random.uniform(1, 5), 1) if cust_type == "B2B" else 0
    customers.append({
        "customer_id": f"CUST{i:03d}",
        "name": name,
        "type": cust_type,
        "avg_payment_lag_days": avg_lag,
        "payment_lag_std_days": lag_std,
        "city": random.choice(["Ahmedabad", "Mumbai", "Delhi", "Bangalore", "Pune"]),
    })

with open("customers.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=customers[0].keys())
    writer.writeheader()
    writer.writerows(customers)

# ---------------------------------------------------------------------------
# INVOICES (B2B receivables) — only for B2B customers
# ---------------------------------------------------------------------------
b2b_customers = [c for c in customers if c["type"] == "B2B"]
invoices = []
invoice_counter = 1

# Hand-crafted "textbook" demo case matching the user's example
invoices.append({
    "invoice_id": "INV1001",
    "customer_id": "CUST001",  # ABC Pvt Ltd
    "amount": 50000,
    "invoice_date": "2026-07-20",
    "due_date": "2026-08-10",
    "status": "unpaid",
    "paid_date": "",
})
invoice_counter += 1

for cust in b2b_customers:
    for _ in range(random.randint(2, 4)):
        days_ago_issued = random.randint(15, 90)
        invoice_date = TODAY - timedelta(days=days_ago_issued)
        due_date = invoice_date + timedelta(days=21)  # net-21 terms
        # Simulate payment behavior using customer's historical lag
        lag = max(0, int(random.gauss(cust["avg_payment_lag_days"], max(cust["payment_lag_std_days"], 0.5))))
        paid_date_candidate = due_date + timedelta(days=lag)

        if paid_date_candidate <= TODAY and random.random() > 0.15:
            status = "paid"
            paid_date = paid_date_candidate.isoformat()
        elif due_date < TODAY:
            status = "unpaid"  # overdue
            paid_date = ""
        else:
            status = "pending"  # not yet due
            paid_date = ""

        invoices.append({
            "invoice_id": f"INV{1000+invoice_counter}",
            "customer_id": cust["customer_id"],
            "amount": random.choice([15000, 22000, 35000, 42000, 50000, 68000, 90000]),
            "invoice_date": invoice_date.isoformat(),
            "due_date": due_date.isoformat(),
            "status": status,
            "paid_date": paid_date,
        })
        invoice_counter += 1

with open("invoices.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=invoices[0].keys())
    writer.writeheader()
    writer.writerows(invoices)

# ---------------------------------------------------------------------------
# TRANSACTIONS (B2C: failed payments + checkout abandonment + success)
# ---------------------------------------------------------------------------
b2c_customers = [c for c in customers if c["type"] == "B2C"]
FAILURE_REASONS = [
    "insufficient_funds", "card_expired", "bank_declined",
    "network_timeout", "otp_failed",
]
CART_STAGES = ["address", "payment_page", "otp_verification", "review_cart"]

transactions = []
txn_counter = 1
for cust in b2c_customers:
    for _ in range(random.randint(3, 6)):
        ts = TODAY - timedelta(days=random.randint(0, 20), hours=random.randint(0, 23))
        outcome = random.choices(
            ["success", "failed", "abandoned"], weights=[0.55, 0.25, 0.20]
        )[0]
        row = {
            "transaction_id": f"TXN{txn_counter:04d}",
            "customer_id": cust["customer_id"],
            "amount": random.choice([499, 899, 1299, 2499, 3999, 5999]),
            "status": outcome,
            "failure_reason": random.choice(FAILURE_REASONS) if outcome == "failed" else "",
            "cart_stage": random.choice(CART_STAGES) if outcome == "abandoned" else "",
            "timestamp": ts.isoformat(),
        }
        transactions.append(row)
        txn_counter += 1

with open("transactions.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=transactions[0].keys())
    writer.writeheader()
    writer.writerows(transactions)

print(f"Generated {len(customers)} customers, {len(invoices)} invoices, {len(transactions)} transactions")
