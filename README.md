# AI Merchant Revenue Copilot

A single agent that combines **Track 03 (Revenue Recovery)**, **Track 04
(Finance Controller)**, and **Track 02 (Risk Manager)** into one coherent
pipeline: detect → diagnose → decide → act → verify → audit.

## What's included
- `data/` - synthetic CSVs: customers, invoices, transactions (recovery
  scenarios), settlements (reconciliation), and fraud_transactions (labeled,
  for the risk manager). The invoice `INV1001` (CUST001, ₹50,000, overdue)
  is the flagship demo case.
- `backend/agent_core.py` - the shared Detect→Diagnose→Decide→Act→Verify→Audit
  loop. All four scenarios below plug into this one engine.
- `backend/scenarios/`
  - `receivables.py` - B2B overdue invoice chaser (reminders + escalation + stop rule)
  - `failed_payments.py` - failed payment retry logic
  - `abandonment.py` - checkout abandonment nudges
  - `fraud_risk.py` - fraud-spike + risk-score detection, defense-only actions
- `backend/forecast.py` - 14-day cash forecast projection
- `backend/reconciliation.py` - settlement matching + exception reporting
- `backend/razorpay_client.py` - real Razorpay test-mode payment link creation
- `backend/main.py` - FastAPI app wiring everything together
- `frontend/index.html` - dashboard (no build step, just open in a browser)

## Run it

```bash
cd backend
pip install -r requirements.txt
export GROQ_API_KEY=your_key_here          # for /explain narrative
export RAZORPAY_KEY_ID=your_test_key_id    # for real payment links
export RAZORPAY_KEY_SECRET=your_test_secret
uvicorn main:app --reload --port 8000
```

Then open `frontend/index.html` in a browser, or hit these directly:

- `GET /run/{scenario}` - scenario is one of `receivables`, `failed_payments`,
  `abandonment`, `fraud_risk`. Runs that scenario's full cycle.
- `GET /run-all` - runs all 4 scenarios at once.
- `GET /forecast` - point-in-time expected recovery (excludes fraud_risk,
  since fraud confidence means risk exposure, not recoverable revenue).
- `GET /forecast/timeline` - 14-day cash forecast projection.
- `GET /reconcile` - matches settlements against expected paid invoices/
  successful transactions; returns match rate + categorized exceptions
  (`missing_settlement`, `amount_mismatch`, `duplicate_settlement`,
  `orphan_settlement`).
- `GET /fraud/evaluate` - precision/recall/F1 of the fraud detector against
  the full labeled dataset.
- `GET /audit` - full combined audit trail across all scenarios.
- `POST /explain` with body `{"item": {...one item from /run/receivables...}}`
  - turns raw numbers into the polished "Problem / Predicted probability /
  Reason / Recommended action / Escalation / Stop rule / Expected recovery"
  narrative via Groq.
- `POST /reset` - clears all counters and audit logs for a clean re-demo.

## Track alignment
- **Track 03 (Revenue Recovery)** - primary. Receivables chasing, failed
  payment retry, checkout abandonment, all with bounded action + escalation
  + stop rules.
- **Track 04 (Finance Controller)** - cash forecasting and reconciliation
  (match rate + categorized exceptions across 40+ settlement records).
  Settlement Q&A is not built.
- **Track 02 (Risk Manager)** - fraud-spike + risk-score detection,
  defense-only actions (block-pending-review or step-up verification, never
  retaliatory), with measured precision/recall against 50 labeled synthetic
  transactions.

Track 01 (Agentic Commerce / conversational checkout) is intentionally NOT
claimed - it's a different, customer-facing product surface and wasn't
built here.

## Design notes
- **One engine, four scenarios.** `RevenueAgent` in `agent_core.py` doesn't
  know or care which scenario it's running - it just calls whatever
  detect/diagnose/decide/act/verify functions you hand it. This is what
  proves the "generalized agent" story rather than four scripts glued
  together.
- **Rules compute the numbers, LLM writes the narrative.** Diagnose/decide
  are deterministic heuristics (fast, predictable, easy to defend to
  judges). The `/explain` endpoint uses Groq only to phrase the result -
  it never touches the actual decision.
- **Real Razorpay payment links, not simulated ones.** When
  `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET` are set, every reminder/retry/
  nudge action calls Razorpay's Payment Links API (test mode) and returns a
  real, clickable link. Falls back to a simulated string if keys are
  missing or the call fails, so the pipeline still runs offline.
- **Fraud metrics are intentionally imperfect.** ~77% precision, ~83%
  recall, F1 0.80 on the current seeded dataset - not 100%, because the
  data includes "hard" cases on both sides (a genuine large purchase that
  looks risky, and a fraud case with no classic signals). A detector
  claiming perfect accuracy on its own synthetic data would look fabricated
  to judges.
- Regenerate any dataset anytime: `generate_data.py`,
  `generate_settlements.py` (run after `generate_data.py`), and
  `generate_fraud_data.py`. All are seeded for reproducibility.

## Still open
- Demo script / narrative walkthrough for judges
- Error handling for the unhappy path (bad API keys, missing files) so a
  failure shows a clean message instead of a raw stack trace live
- Settlement Q&A (would complete Track 04 fully, not currently planned)
