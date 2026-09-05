"""
Checkout Abandonment Recovery scenario.

detect()   -> transactions with status == "abandoned"
diagnose() -> which stage they dropped off at + likely reason
decide()   -> nudge message / discount nudge
act()      -> (simulated) sends nudge
verify()   -> (simulated) checks if they completed checkout
"""
import pandas as pd
from agent_core import RiskItem
import razorpay_client

DATA_DIR = "../data"
_transactions_df = pd.read_csv(f"{DATA_DIR}/transactions.csv", keep_default_na=False)

STAGE_PROFILE = {
    "address": {"recovery_confidence": 0.25, "action": "send_reminder_nudge"},
    "payment_page": {"recovery_confidence": 0.55, "action": "send_reminder_nudge"},
    "otp_verification": {"recovery_confidence": 0.65, "action": "send_reminder_nudge"},
    "review_cart": {"recovery_confidence": 0.40, "action": "send_discount_nudge"},
}

_nudge_counts: dict[str, int] = {}


def detect() -> list[RiskItem]:
    items = []
    for _, row in _transactions_df.iterrows():
        if row["status"] != "abandoned":
            continue
        items.append(RiskItem(
            item_id=row["transaction_id"],
            scenario="abandonment",
            customer_id=row["customer_id"],
            amount=float(row["amount"]),
            raw=row.to_dict(),
        ))
    return items


def diagnose(item: RiskItem) -> RiskItem:
    stage = item.raw.get("cart_stage", "unknown")
    profile = STAGE_PROFILE.get(stage, {"recovery_confidence": 0.3, "action": "send_reminder_nudge"})
    item.confidence = profile["recovery_confidence"]
    item.cause = f"Dropped off at '{stage.replace('_', ' ')}' stage of checkout."
    item._suggested_action = profile["action"]
    return item


def decide(item: RiskItem) -> RiskItem:
    count = _nudge_counts.get(item.item_id, 0)
    suggested = getattr(item, "_suggested_action", "send_reminder_nudge")

    if count >= 1:
        item.action = "stop"
        item.escalation_rule = "none"
        item.stop_rule = "Stop after 1 nudge"
    else:
        item.action = suggested
        item.escalation_rule = "none — single nudge only for abandonment"
        item.stop_rule = "Stop after 1 nudge"
    return item


def act(item: RiskItem) -> str:
    _nudge_counts[item.item_id] = _nudge_counts.get(item.item_id, 0) + 1
    if item.action == "stop":
        return f"No further action for {item.item_id} — nudge already sent."

    link = razorpay_client.create_payment_link(
        amount_rupees=item.amount,
        description=f"Complete your order {item.item_id}",
        reference_id=item.item_id,
        customer_name=item.customer_id,
    )

    if item.action == "send_discount_nudge":
        return (
            f"Sent 10% discount nudge to {item.customer_id} to complete cart "
            f"{item.item_id}. Payment link: {link['short_url']}"
        )
    return (
        f"Sent reminder nudge to {item.customer_id} to complete cart {item.item_id} "
        f"(₹{item.amount:.0f}). Payment link: {link['short_url']}"
    )


def verify(item: RiskItem) -> str:
    return "pending"


def reset():
    """Clears in-memory nudge counters so a fresh demo run starts clean."""
    _nudge_counts.clear()
