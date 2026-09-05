"""
Failed Payment Retry scenario.

detect()   -> transactions with status == "failed"
diagnose() -> reason for failure + retry likelihood
decide()   -> retry now / retry later / ask for alternate payment method
act()      -> (simulated) triggers Razorpay retry / sends message
verify()   -> (simulated) checks retry outcome
"""
import pandas as pd
from agent_core import RiskItem
import razorpay_client

DATA_DIR = "../data"
_transactions_df = pd.read_csv(f"{DATA_DIR}/transactions.csv", keep_default_na=False)

# Failure reasons mapped to retry viability and suggested action
REASON_PROFILE = {
    "insufficient_funds": {"retry_confidence": 0.35, "action": "retry_after_24h"},
    "card_expired": {"retry_confidence": 0.10, "action": "request_alternate_method"},
    "bank_declined": {"retry_confidence": 0.40, "action": "retry_immediately"},
    "network_timeout": {"retry_confidence": 0.85, "action": "retry_immediately"},
    "otp_failed": {"retry_confidence": 0.70, "action": "retry_immediately"},
}

_retry_counts: dict[str, int] = {}


def detect() -> list[RiskItem]:
    items = []
    for _, row in _transactions_df.iterrows():
        if row["status"] != "failed":
            continue
        items.append(RiskItem(
            item_id=row["transaction_id"],
            scenario="failed_payment",
            customer_id=row["customer_id"],
            amount=float(row["amount"]),
            raw=row.to_dict(),
        ))
    return items


def diagnose(item: RiskItem) -> RiskItem:
    reason = item.raw.get("failure_reason", "unknown")
    profile = REASON_PROFILE.get(reason, {"retry_confidence": 0.3, "action": "retry_after_24h"})
    item.confidence = profile["retry_confidence"]
    item.cause = f"Payment failed due to: {reason.replace('_', ' ')}."
    item._suggested_action = profile["action"]  # stashed for decide()
    return item


def decide(item: RiskItem) -> RiskItem:
    count = _retry_counts.get(item.item_id, 0)
    suggested = getattr(item, "_suggested_action", "retry_after_24h")

    if count >= 2:
        item.action = "stop_and_notify_merchant"
        item.escalation_rule = "none — max retries reached"
        item.stop_rule = "Stop after 2 retries"
    else:
        item.action = suggested
        item.escalation_rule = "If retry fails again, request alternate payment method"
        item.stop_rule = "Stop after 2 retries"
    return item


def act(item: RiskItem) -> str:
    _retry_counts[item.item_id] = _retry_counts.get(item.item_id, 0) + 1
    if item.action == "stop_and_notify_merchant":
        return f"Notified merchant: {item.item_id} could not be recovered after retries."

    link = razorpay_client.create_payment_link(
        amount_rupees=item.amount,
        description=f"Retry payment for order {item.item_id}",
        reference_id=item.item_id,
        customer_name=item.customer_id,
    )

    if item.action == "request_alternate_method":
        return (
            f"Sent message to {item.customer_id} asking for an alternate payment "
            f"method for {item.item_id}. Payment link: {link['short_url']}"
        )
    return (
        f"Triggered retry #{_retry_counts[item.item_id]} for {item.item_id} "
        f"(₹{item.amount:.0f}). Payment link: {link['short_url']}"
    )


def verify(item: RiskItem) -> str:
    return "pending"


def reset():
    """Clears in-memory retry counters so a fresh demo run starts clean."""
    _retry_counts.clear()
