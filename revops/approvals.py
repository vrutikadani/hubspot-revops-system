"""Discounted device price approval chain (four workflows working as one state machine).

Goal: protect margin without slowing deals. A deal priced below list needs a reason,
and the deeper the discount, the more senior the approver.

  Step 1  Deal in Negotiation or Closed Won, price below the product's floor, no reason
          -> status "Pending - Reason Needed", task for the deal owner
  Step 2a Reason entered, price in the mid band   -> "Pending Approval - VP Sales" + task
  Step 2b Reason entered, price in the deep band  -> "Pending Approval - CFO" + task
  Step 3  Approver sets Approved / Rejected       -> owner is emailed the decision + comments

"Price" is the device amount PLUS the opening consumables order, so reps cannot hide a
discount by bundling free product. Only deals closing on/after the policy start date.

Thresholds below are illustrative, not real pricing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

POLICY_START = date(2026, 10, 1)
ELIGIBLE_STAGES = {"negotiation", "closed_won"}

# product: (list floor, VP band floor). Below list floor needs approval;
# at/above VP floor -> VP approves; below VP floor -> CFO approves.
PRICE_BANDS = {
    "DEVICE_X_PRO": (30_000, 24_000),
    "DEVICE_X": (24_000, 20_000),
}


@dataclass
class PriceDeal:
    deal_id: str
    product: str
    stage: str
    amount: float
    opening_consumables: float = 0.0
    close_date: date = POLICY_START
    reason: str = ""
    status: str = ""
    decision: Optional[str] = None
    approver_comment: str = ""
    tasks: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)

    @property
    def check_amount(self) -> float:
        return self.amount + self.opening_consumables


def step(d: PriceDeal) -> PriceDeal:
    """Run whichever workflow would enroll this deal right now."""
    if d.close_date < POLICY_START or d.stage not in ELIGIBLE_STAGES or d.product not in PRICE_BANDS:
        return d
    list_floor, vp_floor = PRICE_BANDS[d.product]
    if d.check_amount >= list_floor:
        d.status = "Not Required"
        return d

    if d.decision in {"Approved", "Rejected"}:                     # step 3
        if d.status != f"{d.decision}":
            d.emails.append(f"owner: price {d.decision.lower()} - {d.approver_comment or 'no comment'}")
            d.status = d.decision
        return d
    if not d.reason.strip():                                        # step 1
        if d.status != "Pending - Reason Needed":
            d.status = "Pending - Reason Needed"
            d.tasks.append("owner: enter a device pricing reason")
        return d
    approver = "VP Sales" if d.check_amount >= vp_floor else "CFO"  # step 2a / 2b
    new_status = f"Pending Approval - {approver}"
    if d.status != new_status:
        d.status = new_status
        d.tasks.append(f"{approver}: approve price on {d.deal_id} (${d.check_amount/1e3:.1f}K)")
        d.emails.append(f"{approver}: approval needed")
    return d
