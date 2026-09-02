"""
detect()   -> overdue unpaid invoices
diagnose() -> payment probability from customer's historical lag pattern
decide()   -> reminder / escalation / stop rule
act()      -> (simulated) sends reminder
verify()   -> (simulated) checks if invoice got paid
"""
import pandas as pd
from datetime import date
from agent_core import RiskItem

TODAY = date(2026, 8, 29)
DATA_DIR = "../data"

_customers_df = pd.read_csv(f"{DATA_DIR}/customers.csv", keep_default_na=False)
_invoices_df = pd.read_csv(f"{DATA_DIR}/invoices.csv", keep_default_na=False)

# in-memory reminder counter per invoice (stand-in for a real DB)
_reminder_counts: dict[str, int] = {}

def detect() -> list[RiskItem]:
    items = []
    for _, row in _invoices_df.iterrows():
        if row["status"] != "unpaid":
            continue
        due = date.fromisoformat(row["due_date"])
        if due >= TODAY:
            continue  # not actually overdue yet
        items.append(RiskItem(
            item_id=row["invoice_id"],
            scenario="receivable",
            customer_id=row["customer_id"],
            amount=float(row["amount"]),
            raw=row.to_dict(),
        ))
    return items

def diagnose(item: RiskItem) -> RiskItem:
    cust = _customers_df[_customers_df["customer_id"] == item.customer_id].iloc[0]
    due = date.fromisoformat(item.raw["due_date"])
    days_overdue = (TODAY - due).days
    avg_lag = float(cust["avg_payment_lag_days"])
    std_lag = max(float(cust["payment_lag_std_days"]), 0.5)

    # Simple, explainable heuristic: start high (customer usually does pay),
    # and decay gently for every day beyond their typical lag. A customer who
    # is only slightly beyond their normal pattern still looks likely to pay;
    # one who is *far* beyond it (many std-deviations) looks increasingly risky.
    days_beyond_typical = max(0, days_overdue - avg_lag)
    decay_per_day = 0.03 / max(std_lag / 3, 0.5)  # more variable customers decay slower
    probability = max(0.10, min(0.90, 0.90 - decay_per_day * days_beyond_typical))

    item.confidence = round(probability, 2)
    item.cause = (
        f"{days_overdue} days overdue. Customer historically pays "
        f"~{avg_lag:.1f} days late (±{std_lag:.1f} days)."
    )
    return item

def decide(item: RiskItem) -> RiskItem:
    count = _reminder_counts.get(item.item_id, 0)
    if count == 0:
        item.action = "send_first_reminder"
        item.escalation_rule = "If unpaid after 3 days, send second reminder"
        item.stop_rule = "Stop after 2 reminders"
    elif count == 1:
        item.action = "send_second_reminder"
        item.escalation_rule = "If unpaid after 3 more days, flag for manual collections"
        item.stop_rule = "Stop after 2 reminders"
    else:
        item.action = "flag_for_manual_collections"
        item.escalation_rule = "none - handed off to human"
        item.stop_rule = "n/a"
    return item

def act(item: RiskItem) -> str:
    _reminder_counts[item.item_id] = _reminder_counts.get(item.item_id, 0) + 1
    if item.action == "flag_for_manual_collections":
        return f"Escalated {item.item_id} to manual collections queue."
    return f"Sent reminder #{_reminder_counts[item.item_id]} to {item.customer_id} for {item.item_id} (₹{item.amount:.0f})."

def verify(item: RiskItem) -> str:
    # Simulated - in production this would re-check invoice status after a delay.
    return "pending"