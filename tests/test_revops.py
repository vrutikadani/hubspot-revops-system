from datetime import date

import pytest

from revops.approvals import PriceDeal, step
from revops.assignment import MARKETING_QUEUE, Assigner, Record, Territories
from revops.lifecycle import Contact, Deal, evaluate
from revops.service import Ticket, move, on_create, reminders

TODAY = date(2026, 10, 25)


# ---------------- lifecycle
def test_closed_won_makes_customer():
    c = evaluate(Contact("a@clinic.com", deals=[Deal("closed_won")], last_consumables_order=date(2026, 9, 1)), TODAY)
    assert (c.lifecycle, c.lead_status, c.customer_type) == ("customer", "Closed Deal", "Active Customer")


def test_churn_rule_past_due_or_inactive():
    c = evaluate(Contact("a@clinic.com", deals=[Deal("closed_won")], days_past_due=130), TODAY)
    assert c.customer_type == "No Longer Customer" and c.lifecycle == "customer"
    c2 = evaluate(Contact("b@clinic.com", deals=[Deal("closed_won")], last_consumables_order=date(2026, 3, 1)), TODAY)
    assert c2.customer_type == "No Longer Customer"


def test_open_deal_makes_opportunity():
    assert evaluate(Contact("a@clinic.com", deals=[Deal("open")]), TODAY).lifecycle == "opportunity"


def test_mql_needs_form_phone_and_medical_or_blank_specialty():
    assert evaluate(Contact("a@clinic.com", form_submissions=1, has_valid_phone=True, specialty="Dermatology"), TODAY).lifecycle == "mql"
    assert evaluate(Contact("a@clinic.com", form_submissions=1, has_valid_phone=False), TODAY).lifecycle == "lead"


def test_lifecycle_never_moves_backward():
    c = evaluate(Contact("a@clinic.com", lifecycle="customer", deals=[Deal("open")]), TODAY)
    assert c.lifecycle == "customer"


def test_consumers_and_internal_are_excluded():
    assert evaluate(Contact("x@gmail.com", is_consumer=True), TODAY).customer_type == "Consumer"
    assert evaluate(Contact("me@example-company.com"), TODAY).customer_type == "Internal Employee"


# ---------------- assignment
@pytest.fixture
def assigner():
    return Assigner(Territories(
        ae_by_zip={"78701": "AE-Austin"}, ae_by_state={"TX": "AE-Texas", "FL": "AE-Florida"},
        inside_by_zip={"78701": "Inside-1"}, inside_by_state={"TX": "Inside-2"},
        inside_pool=["Inside-1", "Inside-2"],
        am_by_state={"TX": "AM-South", "CA": "AM-West"},
        corporate_east="AM-Corp-East", corporate_west="AM-Corp-West",
        east_states={"NY", "FL", "OH", "IL"}, reengagement_owner="AM-Reengage"))


def test_medical_mql_goes_to_ae_by_zip_then_state(assigner):
    assert assigner.assign(Record("1", "mql", "TX", "78701", "Dermatology")).owner == "AE-Austin"
    assert assigner.assign(Record("2", "mql", "TX", "75001", "Dermatology")).path == "outside - state (no zip match)"


def test_med_spa_without_md_goes_inside(assigner):
    assert assigner.assign(Record("1", "mql", "TX", "78701", "Med Spa", has_medical_director=False)).owner == "Inside-1"


def test_marketing_stages_and_consumers_go_to_marketing(assigner):
    assert assigner.assign(Record("1", "lead", "TX")).owner == MARKETING_QUEUE
    assert assigner.assign(Record("1", "mql", "TX", is_consumer=True)).owner == MARKETING_QUEUE


def test_manual_lock_wins(assigner):
    assert assigner.assign(Record("1", "sql", "TX", "78701", owner="Inside-2", manual_lock=True)).owner == "Inside-2"


def test_no_coverage_round_robin(assigner):
    owners = {assigner.assign(Record(str(i), "sql", "WA", "98101")).owner for i in range(2)}
    assert owners == {"Inside-1", "Inside-2"}


def test_customer_routing(assigner):
    assert assigner.assign(Record("1", "customer", "TX", is_customer=True)).owner == "AM-South"
    assert assigner.assign(Record("1", "customer", "IL", is_customer=True, is_corporate=True)).owner == "AM-Corp-East"
    assert assigner.assign(Record("1", "customer", "CA", is_churned=True, on_reengagement_list=True)).owner == "AM-Reengage"


# ---------------- approvals
def test_full_approval_chain():
    d = PriceDeal("D1", "DEVICE_X", "negotiation", amount=17_000, opening_consumables=1_000)
    step(d); assert d.status == "Pending - Reason Needed"
    d.reason = "competitive trade-in"
    step(d); assert d.status == "Pending Approval - CFO"
    d.decision, d.approver_comment = "Approved", "ok this once"
    step(d); assert d.status == "Approved" and "approved" in d.emails[-1]


def test_mid_band_goes_to_vp_and_bundled_consumables_count():
    d = PriceDeal("D2", "DEVICE_X", "closed_won", amount=19_000, opening_consumables=2_000, reason="volume")
    assert step(d).status == "Pending Approval - VP Sales"


def test_list_price_and_old_deals_skip():
    assert step(PriceDeal("D3", "DEVICE_X", "negotiation", 24_000)).status == "Not Required"
    assert step(PriceDeal("D4", "DEVICE_X", "negotiation", 10_000, close_date=date(2026, 9, 1))).status == ""


def test_steps_are_idempotent():
    d = PriceDeal("D5", "DEVICE_X", "negotiation", 15_000)
    step(d); step(d)
    assert len(d.tasks) == 1


# ---------------- service
def test_demo_tickets_auto_assign_and_shipping_gate():
    t = on_create(Ticket("T1", "demo"))
    assert t.owner == "Customer Success"
    assert not move(t, "shipped", TODAY) and "serial_number" in t.tasks[-1]
    t.fields = {"erp_account_id": "1", "serial_number": "S", "tracking_number": "Z"}
    assert move(t, "shipped", TODAY)


def test_stage_reminders():
    ts = [Ticket("T1", "repair", "on_hold", date(2026, 10, 15), "Tech-1"),
          Ticket("T2", "repair", "on_hold", date(2026, 10, 22), "Tech-1"),
          Ticket("T3", "repair", "in_progress", date(2026, 10, 22), "Tech-2")]
    out = reminders(ts, TODAY)
    assert len(out) == 2 and any("T1" in o for o in out) and any("T3" in o for o in out)
