"""
Revenue Copilot API.

Endpoints:
  GET  /run/{scenario}      -> run one scenario's full cycle, return items + audit log
  GET  /run-all             -> run all 4 scenarios, return combined results
  GET  /forecast            -> aggregate expected recovery across all scenarios
  GET  /forecast/timeline   -> 14-day cash forecast projection
  GET  /reconcile           -> settlement matching + exception report
  GET  /fraud/evaluate      -> precision/recall/F1 of the fraud detector
  GET  /audit               -> full combined audit trail
  POST /explain             -> turn a RiskItem's raw numbers into an LLM narrative
  POST /reset               -> clear all counters/audit logs for a fresh demo run

Set GROQ_API_KEY, RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET as environment
variables before running (see README for what each one enables).
"""
import os
import sys
import traceback
from dataclasses import asdict
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Startup check — verify required data files exist BEFORE importing anything
# that reads them. Several modules below (reconciliation, scenarios/*) load
# their CSVs at import time, so this check must run first, or a missing file
# produces a raw pandas traceback instead of this friendly message.
# ---------------------------------------------------------------------------
REQUIRED_DATA_FILES = {
    "../data/customers.csv": "python data/generate_data.py",
    "../data/invoices.csv": "python data/generate_data.py",
    "../data/transactions.csv": "python data/generate_data.py",
    "../data/settlements.csv": "python data/generate_settlements.py (run AFTER generate_data.py)",
    "../data/fraud_transactions.csv": "python data/generate_fraud_data.py",
}


def check_data_files():
    missing = [(path, cmd) for path, cmd in REQUIRED_DATA_FILES.items() if not os.path.exists(path)]
    if missing:
        print("\n" + "=" * 70)
        print("STARTUP CHECK FAILED — missing required data files:")
        for path, cmd in missing:
            print(f"  MISSING: {path}")
            print(f"    -> fix by running: {cmd}")
        print("Run the commands above from inside the backend/ folder, then restart.")
        print("=" * 70 + "\n")
        sys.exit(1)


check_data_files()

from agent_core import RevenueAgent, RiskItem
from scenarios import receivables, failed_payments, abandonment, fraud_risk
import forecast as forecast_module
import reconciliation as reconciliation_module

app = FastAPI(title="AI Merchant Revenue Copilot")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Global exception handler — catches anything not explicitly handled below
# and returns clean JSON instead of a raw stack trace. Full traceback still
# prints to the terminal for debugging; the dashboard just gets a readable
# error message instead of a broken response.
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def catch_all_exception_handler(request: Request, exc: Exception):
    print(f"\n[ERROR] Unhandled exception on {request.method} {request.url.path}:")
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={
            "error": "Something went wrong on the server.",
            "detail": str(exc),
            "path": str(request.url.path),
        },
    )


AGENTS = {
    "receivables": RevenueAgent(
        "receivable",
        receivables.detect, receivables.diagnose, receivables.decide,
        receivables.act, receivables.verify,
    ),
    "failed_payments": RevenueAgent(
        "failed_payment",
        failed_payments.detect, failed_payments.diagnose, failed_payments.decide,
        failed_payments.act, failed_payments.verify,
    ),
    "abandonment": RevenueAgent(
        "abandonment",
        abandonment.detect, abandonment.diagnose, abandonment.decide,
        abandonment.act, abandonment.verify,
    ),
    "fraud_risk": RevenueAgent(
        "fraud_risk",
        fraud_risk.detect, fraud_risk.diagnose, fraud_risk.decide,
        fraud_risk.act, fraud_risk.verify,
    ),
}

_last_run_items: dict[str, list[RiskItem]] = {}


@app.get("/run/{scenario}")
def run_scenario(scenario: str):
    if scenario not in AGENTS:
        raise HTTPException(404, f"Unknown scenario '{scenario}'. Choose from {list(AGENTS)}")
    agent = AGENTS[scenario]
    items = agent.run_cycle()
    _last_run_items[scenario] = items
    return {
        "scenario": scenario,
        "items": [asdict(i) for i in items],
        "expected_recovery": agent.expected_recovery(items),
        "audit_log": [asdict(a) for a in agent.audit_log[-len(items) * 5:]],
    }


@app.get("/run-all")
def run_all():
    result = {}
    total_forecast = 0.0
    for name, agent in AGENTS.items():
        items = agent.run_cycle()
        _last_run_items[name] = items
        recovery = agent.expected_recovery(items)
        result[name] = {
            "items": [asdict(i) for i in items],
            "expected_recovery": recovery,
        }
        if name != "fraud_risk":  # fraud confidence = risk exposure, not recoverable revenue
            total_forecast += recovery
    return {"scenarios": result, "total_expected_recovery": total_forecast}


@app.get("/forecast")
def forecast():
    total = 0.0
    breakdown = {}
    for name, agent in AGENTS.items():
        items = _last_run_items.get(name, [])
        recovery = agent.expected_recovery(items)
        breakdown[name] = recovery
        if name != "fraud_risk":  # fraud confidence = risk exposure, not recoverable revenue
            total += recovery
    return {"total_expected_recovery": total, "breakdown": breakdown}


@app.get("/forecast/timeline")
def forecast_timeline():
    """Day-by-day cash forecast for the next 14 days, combining at-risk item
    recovery with pending (not-yet-due) invoice inflows."""
    items_by_scenario = {
        "receivable": _last_run_items.get("receivables", []),
        "failed_payment": _last_run_items.get("failed_payments", []),
        "abandonment": _last_run_items.get("abandonment", []),
    }
    timeline = forecast_module.build_timeline(items_by_scenario)
    return {"horizon_days": forecast_module.HORIZON_DAYS, "timeline": timeline}


@app.get("/audit")
def full_audit():
    all_entries = []
    for agent in AGENTS.values():
        all_entries.extend(asdict(a) for a in agent.audit_log)
    all_entries.sort(key=lambda e: e["timestamp"])
    return {"audit_log": all_entries}


@app.get("/reconcile")
def reconcile():
    """Runs reconciliation: matches settlements against expected paid invoices
    and successful transactions, reporting match rate and categorized exceptions."""
    return reconciliation_module.run_reconciliation()


@app.get("/fraud/evaluate")
def fraud_evaluate():
    """Precision/recall/F1 of the fraud detector against the full labeled
    dataset — the metric Track 02 explicitly asks for."""
    return fraud_risk.evaluate()


@app.post("/reset")
def reset_state():
    """Clears in-memory reminder/retry/nudge counters AND audit logs, so a
    fresh demo run starts from a clean slate."""
    receivables.reset()
    failed_payments.reset()
    abandonment.reset()
    fraud_risk.reset()
    for agent in AGENTS.values():
        agent.audit_log.clear()
    _last_run_items.clear()
    return {"status": "reset complete"}


# ---------------------------------------------------------------------------
# LLM narrative layer — turns raw numbers into the polished explanation.
# Rules/heuristics already computed confidence, cause, action, etc. above;
# this endpoint just asks the LLM to phrase it the way a finance ops person
# would want to read it. This keeps the actual DECISION deterministic while
# making the OUTPUT feel agentic.
# ---------------------------------------------------------------------------
class ExplainRequest(BaseModel):
    item: dict


@app.post("/explain")
async def explain(req: ExplainRequest):
    import httpx

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise HTTPException(500, "GROQ_API_KEY not set. Set it as an environment variable and restart the server.")

    item = req.item
    if not item:
        raise HTTPException(400, "No item data provided. Pass a full item object from /run/{scenario} in the request body.")

    prompt = f"""You are a finance ops assistant. Given this structured data about
an at-risk revenue item, write a short, plain-language narrative in EXACTLY this format:

Problem: <one line>
Predicted recovery probability: <confidence as %>
Reason: <cause, in plain language>
Recommended action: <action, in plain language>
Escalation: <escalation_rule>
Stop rule: <stop_rule>
Expected recovery: ₹<amount * confidence, rounded>

Data:
{item}

Output ONLY the formatted narrative, no preamble."""

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "openai/gpt-oss-20b",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            narrative = data["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as e:
        print(f"[explain] Groq API error: HTTP {e.response.status_code} — {e.response.text}")
        raise HTTPException(
            502,
            f"Groq API returned an error (HTTP {e.response.status_code}). "
            f"Check that GROQ_API_KEY is valid. Details logged to server terminal.",
        )
    except httpx.TimeoutException:
        raise HTTPException(504, "Groq API timed out. Check your network connection and try again.")
    except Exception as e:
        print(f"[explain] Unexpected error calling Groq: {e}")
        raise HTTPException(500, f"Failed to generate narrative: {e}")

    return {"narrative": narrative}


@app.get("/")
def root():
    return {
        "message": "AI Merchant Revenue Copilot API",
        "scenarios": list(AGENTS.keys()),
        "endpoints": ["/run/{scenario}", "/run-all", "/forecast", "/forecast/timeline", "/reconcile", "/fraud/evaluate", "/audit", "/explain (POST)", "/reset (POST)"],
    }
