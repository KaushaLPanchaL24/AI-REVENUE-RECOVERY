"""
Revenue Copilot API.

Endpoints:
  GET  /run/{scenario}      -> run one scenario's full cycle, return items + audit log
  GET  /run-all             -> run all 3 scenarios, return combined results
  GET  /forecast            -> aggregate expected recovery across all scenarios
  GET  /audit               -> full combined audit trail
  POST /explain             -> turn a RiskItem's raw numbers into an LLM narrative
                                (matches the "Problem / Predicted probability / Reason /
                                 Recommended action / Escalation / Stop rule / Expected
                                 recovery" narrative style from the spec)

set GROQ_API_KEY as an environment variable before running.
like 
$env:GROQ_API_KEY="api-key"
"""
import os
from dataclasses import asdict
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent_core import RevenueAgent, RiskItem
from scenarios import receivables, failed_payments, abandonment

app = FastAPI(title="AI Merchant Revenue Copilot")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
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
        total_forecast += recovery
        result[name] = {
            "items": [asdict(i) for i in items],
            "expected_recovery": recovery,
        }
    return {"scenarios": result, "total_expected_recovery": total_forecast}

@app.get("/forecast")
def forecast():
    total = 0.0
    breakdown = {}
    for name, agent in AGENTS.items():
        items = _last_run_items.get(name, [])
        recovery = agent.expected_recovery(items)
        breakdown[name] = recovery
        total += recovery
    return {"total_expected_recovery": total, "breakdown": breakdown}

@app.get("/audit")
def full_audit():
    all_entries = []
    for agent in AGENTS.values():
        all_entries.extend(asdict(a) for a in agent.audit_log)
    all_entries.sort(key=lambda e: e["timestamp"])
    return {"audit_log": all_entries}

# ---------------------------------------------------------------------------
# LLM narrative layer - turns raw numbers into the polished explanation.
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
        raise HTTPException(500, "GROQ_API_KEY not set")

    item = req.item
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

    return {"narrative": narrative}

@app.get("/")
def root():
    return {
        "message": "AI Merchant Revenue Copilot API",
        "scenarios": list(AGENTS.keys()),
        "endpoints": ["/run/{scenario}", "/run-all", "/forecast", "/audit", "/explain (POST)"],
    }
