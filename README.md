# AI Merchant Revenue Copilot - Day 1 Skeleton

## What's included
- `data/` - synthetic CSVs (customers, invoices, transactions) + the generator script.
  The invoice `INV1001` (CUST001, ₹50,000, overdue) is the flagship demo case.
- `backend/agent_core.py` - the shared Detect→Diagnose→Decide→Act→Verify→Audit loop.
  All three scenarios plug into this one engine.
- `backend/scenarios/` - the three recovery scenarios:
  - `receivables.py` - B2B overdue invoice chaser (reminders + escalation + stop rule)
  - `failed_payments.py` - failed payment retry logic
  - `abandonment.py` - checkout abandonment nudges
- `backend/main.py` - FastAPI app exposing all scenarios + a cash forecast + an
  `/explain` endpoint that turns raw numbers into the polished LLM narrative.

## Run it

```bash
cd backend
pip install -r requirements.txt
export GROQ_API_KEY=your_key_here   # only needed for /explain
uvicorn main:app --reload --port 8000
```

Then try:
- `GET http://localhost:8000/run/receivables` - runs the invoice chaser, returns items + audit log
- `GET http://localhost:8000/run-all` - runs all 3 scenarios at once
- `GET http://localhost:8000/forecast` - aggregated expected recovery across scenarios
- `GET http://localhost:8000/audit` - full combined audit trail
- `POST http://localhost:8000/explain` with body `{"item": {...one item from /run/receivables...}}`
  - returns the polished narrative in the "Problem / Predicted probability / Reason /
  Recommended action / Escalation / Stop rule / Expected recovery" format.

## Design notes
- **Rules compute the numbers, LLM writes the narrative.** Diagnose/decide are
  deterministic heuristics (fast, predictable, easy to defend to judges).
  The `/explain` endpoint uses Groq to turn those numbers into readable prose -
  this is where the "agentic" feel comes from without risking hallucinated math.
- **One engine, three scenarios.** `RevenueAgent` in `agent_core.py` doesn't know
  or care which scenario it's running - it just calls whatever detect/diagnose/
  decide/act/verify functions you hand it. This is what proves the "generalized
  revenue agent" story rather than three separate scripts glued together.
- Regenerate data anytime with `python data/generate_data.py` - it's deterministic
  (seeded) so the same demo will reproduce every run.

## Next steps (Day 2+)
- Cash forecast projection over time (not just a point-in-time sum)
- Frontend dashboard showing live agent runs + audit trail
- Wire receivables/failed-payment actions to real Razorpay test-mode APIs
  (reuse retry logic from the tailor-chalk project)
- Demo script walking through the INV1001 case end-to-end