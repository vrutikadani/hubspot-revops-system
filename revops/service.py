"""Service ticket lifecycle + reminders.

Tickets cover device demos, installs, warranty and repairs. Workflows:
  * Status follows the pipeline stage (New -> Assigned -> In Progress -> Waiting on
    Feedback / On Hold -> Closed).
  * Moving to "Shipped" requires ERP account ID, serial / lot number and tracking number;
    missing fields block the move and create a task.
  * Reminders nudge the owner when a ticket sits too long in a stage:
       In Progress 2 days, Waiting on Feedback 2 days, On Hold 7 days.
  * Demo tickets are auto-assigned to the customer success queue.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

REMINDER_DAYS = {"in_progress": 2, "waiting_on_feedback": 2, "on_hold": 7}
SHIP_REQUIRED = ("erp_account_id", "serial_number", "tracking_number")


@dataclass
class Ticket:
    ticket_id: str
    kind: str                       # demo | install | warranty | repair
    stage: str = "new"
    stage_entered: date = date(2026, 1, 1)
    owner: str = ""
    fields: dict = field(default_factory=dict)
    tasks: list[str] = field(default_factory=list)


def on_create(t: Ticket) -> Ticket:
    if t.kind == "demo" and not t.owner:
        t.owner = "Customer Success"
        t.stage = "assigned"
    return t


def move(t: Ticket, to_stage: str, today: date) -> bool:
    if to_stage == "shipped":
        missing = [f for f in SHIP_REQUIRED if not t.fields.get(f)]
        if missing:
            t.tasks.append(f"fill before shipping: {', '.join(missing)}")
            return False
    t.stage, t.stage_entered = to_stage, today
    return True


def reminders(tickets: list[Ticket], today: date) -> list[str]:
    out = []
    for t in tickets:
        limit = REMINDER_DAYS.get(t.stage)
        if limit and (today - t.stage_entered).days >= limit:
            out.append(f"{t.owner or 'unassigned'}: {t.ticket_id} in {t.stage} for {(today - t.stage_entered).days} days")
    return out
