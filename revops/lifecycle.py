"""Lifecycle stage + lead status engine.

The single most-used workflow in the portal (hundreds of thousands of enrollments).
Every contact passes through it whenever a deal, activity or source changes.

Rules, in priority order:
  0. Internal employees and consumers are tagged and leave the funnel.
  1. Any closed-won deal              -> Customer        / lead status "Closed Deal"
  2. Customer whose account is 120+ days past due on consumables, or has not
     ordered in 180+ days            -> churned: customer type "No Longer Customer"
  3. Any open deal                   -> Opportunity     / "Open Deal"
  4. Meets MQL qualifications        -> MQL             / "Open"
  5. Otherwise keep the lead status a rep set (New, Nurture, Unqualified),
     defaulting to Lead / "New".
  - Lifecycle never moves backward, except the churn rule (which changes customer
    type, not stage) and an explicit reset by an admin.
  - If nothing matches, an owner notification is raised instead of guessing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

STAGES = ["subscriber", "lead", "mql", "sql", "opportunity", "customer", "evangelist"]
MEDICAL = {"plastic surgery", "dermatology", "med spa"}
INTERNAL_DOMAINS = {"example-company.com"}


@dataclass
class Deal:
    stage: str              # "open" | "closed_won" | "closed_lost"
    close_date: Optional[date] = None


@dataclass
class Contact:
    email: str
    lifecycle: str = "lead"
    lead_status: str = "New"
    customer_type: str = ""
    specialty: str = ""
    is_consumer: bool = False
    form_submissions: int = 0
    has_valid_phone: bool = False
    last_consumables_order: Optional[date] = None
    days_past_due: int = 0
    deals: list[Deal] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _rank(stage: str) -> int:
    return STAGES.index(stage) if stage in STAGES else 0


def _promote(c: Contact, stage: str) -> None:
    """Move forward only."""
    if _rank(stage) > _rank(c.lifecycle):
        c.notes.append(f"lifecycle {c.lifecycle} -> {stage}")
        c.lifecycle = stage


def is_mql(c: Contact) -> bool:
    """A marketing-qualified lead: a real practice that raised its hand."""
    spec = c.specialty.strip().lower()
    return (c.form_submissions >= 1 and c.has_valid_phone
            and (spec in MEDICAL or spec == "") and not c.is_consumer)


def evaluate(c: Contact, today: date) -> Contact:
    if c.email.split("@")[-1].lower() in INTERNAL_DOMAINS:
        c.customer_type, c.lead_status = "Internal Employee", "Unqualified"
        c.notes.append("internal employee - excluded")
        return c
    if c.is_consumer:
        c.customer_type, c.lead_status = "Consumer", "Unqualified"
        c.notes.append("consumer - excluded from B2B funnel")
        return c

    won = [d for d in c.deals if d.stage == "closed_won"]
    open_ = [d for d in c.deals if d.stage == "open"]

    if won:
        _promote(c, "customer")
        c.lead_status = "Closed Deal"
        inactive = c.last_consumables_order and (today - c.last_consumables_order).days >= 180
        if c.days_past_due >= 120 or inactive:
            c.customer_type = "No Longer Customer"
            c.notes.append("churn rule: 120+ days past due or 180+ days without an order")
        else:
            c.customer_type = "Active Customer"
        return c

    if open_:
        _promote(c, "opportunity")
        c.lead_status = "Open Deal"
        return c

    if is_mql(c):
        _promote(c, "mql")
        if c.lead_status not in {"Nurture", "Unqualified"}:
            c.lead_status = "Open"
        return c

    if c.lead_status in {"New", "Nurture", "Unqualified"}:
        return c
    c.notes.append("NOTIFY OWNER: no rule matched")
    return c
