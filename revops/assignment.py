"""Owner assignment for contacts, companies and deals.

Two teams own two halves of the customer journey:
  * New business (not yet a customer): inside reps and outside reps (AEs)
  * Existing customers and churned accounts: account managers (the "SAM" team)

New-business routing (contacts):
  1. Manual handoff lock          -> never reassign
  2. Consumer                      -> marketing queue
  3. Marketing stages (subscriber / lead / other) -> marketing queue
  4. Outside-eligible (SQL / opportunity, medical MQL, med spa WITH a medical director)
       -> AE who owns the ZIP; if the ZIP is not mapped, AE who owns the state
  5. Everyone else (non-medical MQL, med spa without a medical director)
       -> inside rep who owns the ZIP, then state
  6. No coverage at all -> inside round-robin

Customer routing (companies):
  * Corporate accounts split east / west between two named account managers
  * Otherwise by state
  * Re-engagement list accounts stay with their dedicated owner

Companies follow their contacts; deals follow their company.
Mapping tables are data, not branches - so a territory change is a table edit.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .lifecycle import MEDICAL

MARKETING_QUEUE = "Marketing"


@dataclass
class Territories:
    ae_by_zip: dict[str, str]
    ae_by_state: dict[str, str]
    inside_by_zip: dict[str, str]
    inside_by_state: dict[str, str]
    inside_pool: list[str]
    am_by_state: dict[str, str]
    corporate_east: str
    corporate_west: str
    east_states: set[str]
    reengagement_owner: str


@dataclass
class Record:
    record_id: str
    lifecycle: str
    state: str = ""
    zip: str = ""
    specialty: str = ""
    has_medical_director: Optional[bool] = None
    is_consumer: bool = False
    is_customer: bool = False
    is_churned: bool = False
    is_corporate: bool = False
    on_reengagement_list: bool = False
    owner: Optional[str] = None
    manual_lock: bool = False


@dataclass
class Assignment:
    owner: str
    path: str


class Assigner:
    def __init__(self, t: Territories):
        self.t = t
        self._rr = 0

    def _pool(self) -> str:
        rep = self.t.inside_pool[self._rr % len(self.t.inside_pool)]
        self._rr += 1
        return rep

    @staticmethod
    def outside_eligible(r: Record) -> bool:
        if r.lifecycle in {"sql", "opportunity"}:
            return True
        spec = r.specialty.strip().lower()
        if r.lifecycle == "mql":
            if spec == "med spa":
                return bool(r.has_medical_director)
            return spec in MEDICAL or spec == ""
        return False

    def assign(self, r: Record) -> Assignment:
        if r.manual_lock and r.owner:
            return Assignment(r.owner, "manual handoff - do not reassign")
        if r.is_customer or r.is_churned:
            return self.assign_customer(r)
        if r.is_consumer:
            return Assignment(MARKETING_QUEUE, "consumer")
        if r.lifecycle in {"subscriber", "lead", "other"}:
            return Assignment(MARKETING_QUEUE, "marketing stage")

        if self.outside_eligible(r):
            by_zip, by_state, team = self.t.ae_by_zip, self.t.ae_by_state, "outside"
        else:
            by_zip, by_state, team = self.t.inside_by_zip, self.t.inside_by_state, "inside"
        if r.zip in by_zip:
            return Assignment(by_zip[r.zip], f"{team} - zip")
        if r.state in by_state:
            return Assignment(by_state[r.state], f"{team} - state (no zip match)")
        return Assignment(self._pool(), "no coverage - inside round-robin")

    def assign_customer(self, r: Record) -> Assignment:
        if r.on_reengagement_list:
            return Assignment(self.t.reengagement_owner, "re-engagement list")
        if r.is_corporate:
            east = r.state in self.t.east_states
            return Assignment(self.t.corporate_east if east else self.t.corporate_west,
                              f"corporate - {'east' if east else 'west'}")
        if r.state in self.t.am_by_state:
            return Assignment(self.t.am_by_state[r.state], "account manager - state")
        return Assignment(MARKETING_QUEUE, "customer with unknown state - fix data")
