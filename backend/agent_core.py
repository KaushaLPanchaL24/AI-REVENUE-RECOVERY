"""
Core Revenue Copilot agent loop.

Every scenario (B2B receivables, failed payments, checkout abandonment)
implements the same 3 hooks:

    detect()   -> list of "at-risk" items (raw data rows)
    diagnose() -> attaches a cause + confidence/probability to each item
    decide()   -> attaches a recommended action + escalation/stop rule

The generic Agent class then runs act() / verify() / forecast() / audit()
identically for all scenarios, so behavior stays consistent and the
audit trail is uniform across the whole product.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional
import uuid


@dataclass
class RiskItem:
    """A single at-risk revenue item, regardless of scenario."""
    item_id: str
    scenario: str                  # "receivable" | "failed_payment" | "abandonment"
    customer_id: str
    amount: float
    raw: dict                      # original row data for reference

    # filled in by diagnose()
    cause: str = ""
    confidence: float = 0.0        # 0-1, e.g. predicted recovery probability

    # filled in by decide()
    action: str = ""
    escalation_rule: str = ""
    stop_rule: str = ""

    # filled in by act()/verify()
    action_result: str = ""
    verified_outcome: Optional[str] = None  # "recovered" | "pending" | "failed"


@dataclass
class AuditEntry:
    entry_id: str
    timestamp: str
    scenario: str
    item_id: str
    stage: str          # detect|diagnose|decide|act|verify
    detail: str


class RevenueAgent:
    """Generic engine. Pass in scenario-specific detect/diagnose/decide/act fns."""

    def __init__(
        self,
        scenario_name: str,
        detect_fn: Callable[[], list[RiskItem]],
        diagnose_fn: Callable[[RiskItem], RiskItem],
        decide_fn: Callable[[RiskItem], RiskItem],
        act_fn: Callable[[RiskItem], str],
        verify_fn: Callable[[RiskItem], str],
    ):
        self.scenario_name = scenario_name
        self._detect = detect_fn
        self._diagnose = diagnose_fn
        self._decide = decide_fn
        self._act = act_fn
        self._verify = verify_fn
        self.audit_log: list[AuditEntry] = []

    def _log(self, item_id: str, stage: str, detail: str):
        self.audit_log.append(AuditEntry(
            entry_id=str(uuid.uuid4())[:8],
            timestamp=datetime.utcnow().isoformat(),
            scenario=self.scenario_name,
            item_id=item_id,
            stage=stage,
            detail=detail,
        ))

    def run_cycle(self) -> list[RiskItem]:
        """Runs one full detect->diagnose->decide->act->verify pass."""
        items = self._detect()
        for item in items:
            self._log(item.item_id, "detect", f"Flagged {item.scenario} risk, amount={item.amount}")

            item = self._diagnose(item)
            self._log(item.item_id, "diagnose", f"cause={item.cause}, confidence={item.confidence}")

            item = self._decide(item)
            self._log(item.item_id, "decide", f"action={item.action}, escalation={item.escalation_rule}, stop={item.stop_rule}")

            result = self._act(item)
            item.action_result = result
            self._log(item.item_id, "act", result)

            outcome = self._verify(item)
            item.verified_outcome = outcome
            self._log(item.item_id, "verify", f"outcome={outcome}")

        return items

    def expected_recovery(self, items: list[RiskItem]) -> float:
        """Sum of amount * confidence across all items — feeds the cash forecast."""
        return sum(i.amount * i.confidence for i in items)
