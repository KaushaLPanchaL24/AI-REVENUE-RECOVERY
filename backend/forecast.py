"""
Cash Forecast Projection.

Turns the point-in-time `expected_recovery` sum into a day-by-day projection:
  - At-risk items (already detected) contribute amount*confidence on a date
    computed PER ITEM: more confident items resolve sooner (a customer likely
    to pay responds fast to a reminder), less confident items take longer.
    This spreads recovery across several days instead of bunching everything
    from one scenario onto a single date.
  - Pending invoices (not yet due) contribute their full amount on the day
    they're expected to be paid, based on that customer's historical lag.

This gives judges an actual forecast curve, not just a single number.
"""
from datetime import date, timedelta
import pandas as pd

from agent_core import RiskItem

TODAY = date(2026, 8, 29)
DATA_DIR = "../data"
HORIZON_DAYS = 14

# Base resolution lag per scenario (days), before per-item confidence adjustment.
BASE_LAG = {
    "receivable": 3,
    "failed_payment": 1,
    "abandonment": 1,
}

_customers_df = pd.read_csv(f"{DATA_DIR}/customers.csv", keep_default_na=False)
_invoices_df = pd.read_csv(f"{DATA_DIR}/invoices.csv", keep_default_na=False)


def _pending_invoice_inflows() -> dict[str, float]:
    """Invoices not yet due -> expected payment date (due_date + customer's avg lag)."""
    inflows: dict[str, float] = {}
    for _, row in _invoices_df.iterrows():
        if row["status"] != "pending":
            continue
        due = date.fromisoformat(row["due_date"])
        cust = _customers_df[_customers_df["customer_id"] == row["customer_id"]].iloc[0]
        avg_lag = int(round(float(cust["avg_payment_lag_days"])))
        expected_date = due + timedelta(days=avg_lag)
        offset = (expected_date - TODAY).days
        if 0 <= offset <= HORIZON_DAYS:
            key = expected_date.isoformat()
            inflows[key] = inflows.get(key, 0.0) + float(row["amount"])
    return inflows


def _item_expected_date(scenario: str, item: RiskItem) -> date:
    """
    Computes a PER-ITEM expected resolution date, not a shared per-scenario one.

    Logic: start from the scenario's base lag (e.g. 3 days for a reminder to
    get a response), then adjust by this item's own confidence — a customer
    we're 90% confident will pay responds fast; one we're 10% confident about
    likely needs the full escalation chain (reminder -> wait -> 2nd reminder),
    so their money (if it comes at all) lands later. This is what makes each
    invoice/transaction land on its own day instead of every item in a
    scenario bunching onto one shared date.
    """
    base_lag = BASE_LAG.get(scenario, 3)
    # confidence near 1.0 -> resolves close to base_lag
    # confidence near 0.0 -> resolves up to base_lag * 3 later (full escalation chain)
    spread = round(base_lag * 2 * (1 - item.confidence))
    offset_days = max(1, base_lag + spread)
    offset_days = min(offset_days, HORIZON_DAYS)  # clamp to forecast window
    return TODAY + timedelta(days=offset_days)


def _at_risk_inflows(items_by_scenario: dict[str, list[RiskItem]]) -> dict[str, float]:
    """Already-detected at-risk items -> expected recovery date, computed per item.
    Excludes fraud_risk: risk score there means exposure, not recoverable revenue."""
    inflows: dict[str, float] = {}
    for scenario, items in items_by_scenario.items():
        if scenario == "fraud_risk":
            continue
        for item in items:
            expected_date = _item_expected_date(scenario, item)
            key = expected_date.isoformat()
            inflows[key] = inflows.get(key, 0.0) + (item.amount * item.confidence)
    return inflows


def build_timeline(items_by_scenario: dict[str, list[RiskItem]]) -> list[dict]:
    """Returns a list of {date, expected_inflow, cumulative} for the next 14 days."""
    pending = _pending_invoice_inflows()
    at_risk = _at_risk_inflows(items_by_scenario)

    timeline = []
    cumulative = 0.0
    for offset in range(HORIZON_DAYS + 1):
        day = TODAY + timedelta(days=offset)
        key = day.isoformat()
        day_total = pending.get(key, 0.0) + at_risk.get(key, 0.0)
        cumulative += day_total
        timeline.append({
            "date": key,
            "expected_inflow": round(day_total, 2),
            "cumulative": round(cumulative, 2),
        })
    return timeline