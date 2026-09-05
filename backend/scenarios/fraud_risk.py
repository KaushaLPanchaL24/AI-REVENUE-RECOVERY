"""
AI Risk Manager scenario (Track 02) — fraud-spike detection + risk scoring.

Plugs into the SAME shared engine (agent_core.RevenueAgent) as the recovery
scenarios: detect flags risky transactions, diagnose explains why, decide
picks a defense-only response (never an offensive/retaliatory action),
act executes it, verify checks against ground truth for evaluation.

Risk score combines 3 explainable signals:
  - amount_ratio : transaction amount vs. that customer's typical amount
  - velocity      : transactions by that customer in the last hour
  - odd_hour      : transaction occurring at an unusual hour (1am-4am)

A separate evaluate() function reports precision/recall/F1 against the
ground-truth `is_fraud` label across the FULL dataset (not just flagged
items) — this is what the track explicitly asks for.
"""
import pandas as pd
from agent_core import RiskItem

DATA_DIR = "../data"
FLAG_THRESHOLD = 0.5  # risk_score >= this gets surfaced as a RiskItem

_df = pd.read_csv(f"{DATA_DIR}/fraud_transactions.csv", keep_default_na=False)

_action_log: dict[str, str] = {}  # transaction_id -> action taken (for reset)


def _risk_score(row) -> tuple[float, list[str]]:
    reasons = []
    score = 0.0

    amount_ratio = float(row["amount"]) / max(float(row["customer_avg_amount"]), 1)
    if amount_ratio >= 3:
        score += 0.5
        reasons.append(f"amount is {amount_ratio:.1f}x their typical order")

    velocity = int(row["txns_last_hour"])
    if velocity >= 3:
        score += 0.3
        reasons.append(f"{velocity} transactions in the last hour")

    hour = int(row["hour_of_day"])
    if hour in (1, 2, 3, 4):
        score += 0.2
        reasons.append(f"occurred at {hour}:00 (unusual hour)")

    return round(min(score, 1.0), 2), reasons


def detect() -> list[RiskItem]:
    items = []
    for _, row in _df.iterrows():
        score, reasons = _risk_score(row)
        if score >= FLAG_THRESHOLD:
            item = RiskItem(
                item_id=row["transaction_id"],
                scenario="fraud_risk",
                customer_id=row["customer_id"],
                amount=float(row["amount"]),
                raw=row.to_dict(),
            )
            item.confidence = score  # here, "confidence" means risk confidence, not recovery odds
            item._reasons = reasons
            items.append(item)
    return items


def diagnose(item: RiskItem) -> RiskItem:
    reasons = getattr(item, "_reasons", [])
    item.cause = "Flagged for: " + "; ".join(reasons) if reasons else "Flagged by combined risk signals."
    return item


def decide(item: RiskItem) -> RiskItem:
    # Defense-only: never blocks/retaliates beyond the transaction itself.
    if item.confidence >= 0.7:
        item.action = "auto_block_pending_review"
        item.escalation_rule = "Held for manual fraud review within 24h"
        item.stop_rule = "n/a — single decisive action"
    else:
        item.action = "request_step_up_verification"
        item.escalation_rule = "If verification fails, escalate to auto_block"
        item.stop_rule = "Stop after 1 verification attempt"
    return item


def act(item: RiskItem) -> str:
    if item.action == "auto_block_pending_review":
        result = f"Blocked {item.item_id} (₹{item.amount:.0f}) pending manual fraud review."
    else:
        result = f"Requested step-up verification (OTP/2FA) for {item.item_id} (₹{item.amount:.0f})."
    _action_log[item.item_id] = result
    return result


def verify(item: RiskItem) -> str:
    # Synthetic demo only: we have ground truth, so we can check immediately.
    # In production this would come back later from an investigation queue.
    actual = int(item.raw.get("is_fraud", 0))
    return "confirmed_fraud" if actual == 1 else "false_positive"


def reset():
    _action_log.clear()


def evaluate() -> dict:
    """Precision/recall/F1 of the detection logic against ALL labeled
    transactions (not just the ones that got flagged) — what Track 02 asks for."""
    tp = fp = tn = fn = 0
    for _, row in _df.iterrows():
        score, _ = _risk_score(row)
        predicted_fraud = score >= FLAG_THRESHOLD
        actual_fraud = bool(int(row["is_fraud"]))
        if predicted_fraud and actual_fraud:
            tp += 1
        elif predicted_fraud and not actual_fraud:
            fp += 1
        elif not predicted_fraud and actual_fraud:
            fn += 1
        else:
            tn += 1

    precision = round(tp / (tp + fp), 3) if (tp + fp) else 0.0
    recall = round(tp / (tp + fn), 3) if (tp + fn) else 0.0
    f1 = round(2 * precision * recall / (precision + recall), 3) if (precision + recall) else 0.0

    return {
        "total_transactions": len(_df),
        "true_positives": tp,
        "false_positives": fp,
        "true_negatives": tn,
        "false_negatives": fn,
        "precision": precision,
        "recall": recall,
        "f1_score": f1,
    }
