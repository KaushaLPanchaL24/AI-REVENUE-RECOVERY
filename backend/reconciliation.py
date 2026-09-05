"""
Reconciliation.

Matches Razorpay-style settlement records (what actually landed in the bank)
against "expected" records (paid invoices + successful transactions) and
reports a match rate + categorized exceptions — exactly what Track 04
(Finance Controller) asks for.

Exception types:
  - matched              : settlement found, amount matches exactly
  - amount_mismatch       : settlement found, but amount differs from expected
  - missing_settlement    : expected a settlement, none arrived
  - duplicate_settlement  : more than one settlement for the same reference_id
  - orphan_settlement     : a settlement exists with no matching expected record
"""
import pandas as pd

DATA_DIR = "../data"

_invoices_df = pd.read_csv(f"{DATA_DIR}/invoices.csv", keep_default_na=False)
_transactions_df = pd.read_csv(f"{DATA_DIR}/transactions.csv", keep_default_na=False)
_settlements_df = pd.read_csv(f"{DATA_DIR}/settlements.csv", keep_default_na=False)


def _expected_records() -> dict[str, float]:
    """reference_id -> expected amount, from paid invoices + successful transactions."""
    expected = {}
    for _, row in _invoices_df.iterrows():
        if row["status"] == "paid":
            expected[row["invoice_id"]] = float(row["amount"])
    for _, row in _transactions_df.iterrows():
        if row["status"] == "success":
            expected[row["transaction_id"]] = float(row["amount"])
    return expected


def run_reconciliation() -> dict:
    expected = _expected_records()

    # Group settlements by reference_id to catch duplicates
    settlements_by_ref: dict[str, list[dict]] = {}
    for _, row in _settlements_df.iterrows():
        ref = row["reference_id"]
        settlements_by_ref.setdefault(ref, []).append({
            "settlement_id": row["settlement_id"],
            "amount": float(row["amount"]),
            "settlement_date": row["settlement_date"],
        })

    exceptions = []
    matched_count = 0
    matched_amount = 0.0

    for ref, expected_amount in expected.items():
        settles = settlements_by_ref.get(ref, [])
        if not settles:
            exceptions.append({
                "type": "missing_settlement",
                "reference_id": ref,
                "expected_amount": expected_amount,
                "settled_amount": None,
                "detail": f"Expected ₹{expected_amount:.0f} for {ref}, but no settlement found.",
            })
            continue

        if len(settles) > 1:
            total_settled = sum(s["amount"] for s in settles)
            exceptions.append({
                "type": "duplicate_settlement",
                "reference_id": ref,
                "expected_amount": expected_amount,
                "settled_amount": total_settled,
                "detail": (
                    f"{ref} was settled {len(settles)} times "
                    f"(total ₹{total_settled:.0f} vs expected ₹{expected_amount:.0f})."
                ),
            })
            continue

        settled_amount = settles[0]["amount"]
        if abs(settled_amount - expected_amount) > 0.01:
            exceptions.append({
                "type": "amount_mismatch",
                "reference_id": ref,
                "expected_amount": expected_amount,
                "settled_amount": settled_amount,
                "detail": (
                    f"{ref} settled for ₹{settled_amount:.0f}, "
                    f"expected ₹{expected_amount:.0f} "
                    f"(diff ₹{expected_amount - settled_amount:.0f})."
                ),
            })
        else:
            matched_count += 1
            matched_amount += settled_amount

    # Orphan settlements: reference_ids in settlements that aren't in expected at all
    for ref, settles in settlements_by_ref.items():
        if ref not in expected:
            for s in settles:
                exceptions.append({
                    "type": "orphan_settlement",
                    "reference_id": ref,
                    "expected_amount": None,
                    "settled_amount": s["amount"],
                    "detail": f"Settlement {s['settlement_id']} (₹{s['amount']:.0f}) has no matching invoice or transaction.",
                })

    total_expected_records = len(expected)
    match_rate = round(matched_count / total_expected_records, 4) if total_expected_records else 0.0

    return {
        "total_expected_records": total_expected_records,
        "matched_count": matched_count,
        "matched_amount": round(matched_amount, 2),
        "match_rate": match_rate,
        "exception_count": len(exceptions),
        "exceptions": exceptions,
    }
