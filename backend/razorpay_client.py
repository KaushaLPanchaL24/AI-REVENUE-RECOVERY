"""
Thin Razorpay client for the Revenue Copilot.

Uses the Payment Links API (https://api.razorpay.com/v1/payment_links) since
that's what a "retry" / "reminder" / "nudge" action realistically produces:
a fresh, shareable payment link for the same amount — not a literal re-charge
of a stored card (which needs the customer's card token, which we don't have).

Reads credentials from env vars RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET.
If they're not set, or the API call fails, falls back to a simulated link
so the rest of the pipeline still works for local testing/demoing offline.
"""
import os
import time
import httpx

RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET")
RAZORPAY_BASE_URL = "https://api.razorpay.com/v1/payment_links"


def is_configured() -> bool:
    return bool(RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET)


def create_payment_link(amount_rupees: float, description: str, reference_id: str, customer_name: str = "") -> dict:
    """
    Creates a real Razorpay test-mode payment link.
    Returns {"short_url": ..., "id": ..., "simulated": False} on success,
    or {"short_url": None, "simulated": True, "error": ...} on failure/no-config.
    """
    if not is_configured():
        return {
            "short_url": f"[simulated — no Razorpay keys set] payment link for {reference_id}",
            "id": None,
            "simulated": True,
            "error": "RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET not set",
        }

    # reference_id must be unique per payment link on Razorpay's side. Since
    # our demo data reuses the same invoice/transaction IDs across repeated
    # runs, append a timestamp so re-running the demo doesn't collide with
    # a link already created in a previous run.
    unique_reference_id = f"{reference_id}-{int(time.time())}"

    payload = {
        "amount": int(round(amount_rupees * 100)),  # Razorpay expects paise
        "currency": "INR",
        "description": description,
        "reference_id": unique_reference_id,
        "notify": {"sms": False, "email": False},  # we handle notification ourselves
        "reminder_enable": False,
    }
    # NOTE: intentionally NOT sending a "customer" object — Razorpay expects
    # real contact details (email/phone) there, and we only have an internal
    # customer_id (e.g. "CUST001"), not a real name/contact. Sending a
    # customer object without one commonly causes a 400 validation error.

    try:
        resp = httpx.post(
            RAZORPAY_BASE_URL,
            json=payload,
            auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET),
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return {"short_url": data.get("short_url"), "id": data.get("id"), "simulated": False}
    except httpx.HTTPStatusError as e:
        # Surface Razorpay's actual error message in the terminal so it's
        # debuggable instead of a silent generic failure.
        error_detail = e.response.text
        print(f"[razorpay_client] Payment link creation failed for {reference_id}: "
              f"HTTP {e.response.status_code} — {error_detail}")
        return {
            "short_url": f"[simulated — Razorpay call failed] payment link for {reference_id}",
            "id": None,
            "simulated": True,
            "error": error_detail,
        }
    except Exception as e:
        print(f"[razorpay_client] Payment link creation failed for {reference_id}: {e}")
        return {
            "short_url": f"[simulated — Razorpay call failed] payment link for {reference_id}",
            "id": None,
            "simulated": True,
            "error": str(e),
        }
