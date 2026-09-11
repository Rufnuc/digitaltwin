"""Phase 4: AI business assistant (offline rule-based provider)."""
from __future__ import annotations

from app.seed.demo_data import seed
from app.services.ai.assistant import ask, get_provider
from app.services.ai.providers.rule_based import RuleBasedProvider
from app.services.ai.tools import execute_tool
from app.services.analytics import dashboard_summary


def test_default_provider_is_offline_rule_based():
    assert isinstance(get_provider(), RuleBasedProvider)


def test_business_summary_numbers_come_from_tools_not_invented(db):
    seed(db)
    # The exact revenue figure the tool would return.
    revenue = dashboard_summary(db)["kpis"]["revenue"]
    expected = f"₦{revenue:,.0f}"

    res = ask(db, "How is my business doing?")
    assert res["provider"] == "rule_based"
    assert res["provenance"] == "AI_INTERPRETATION"
    assert res["tool_calls"], "assistant must call a tool to obtain figures"
    assert res["tool_calls"][0]["name"] == "get_business_summary"
    # No fabrication: the figure in the answer is exactly the tool's figure.
    assert expected in res["answer"]


def test_price_question_runs_scenario_engine(db):
    seed(db)
    res = ask(db, "What happens if I raise prices by 10%?")
    names = [c["name"] for c in res["tool_calls"]]
    assert "run_scenario" in names
    call = next(c for c in res["tool_calls"] if c["name"] == "run_scenario")
    assert call["args"]["change_percent"] == 10.0
    # Answer reflects the engine's revenue projection (verbatim).
    rev = next(m for m in call["result"]["results"] if m["metric"] == "revenue")
    assert f"₦{rev['scenario']:,.0f}" in res["answer"]


def test_price_cut_detected_as_negative(db):
    seed(db)
    res = ask(db, "what if we cut prices by 5%")
    call = next(c for c in res["tool_calls"] if c["name"] == "run_scenario")
    assert call["args"]["change_percent"] == -5.0


def test_risk_question_uses_customer_and_quality_tools(db):
    seed(db)
    res = ask(db, "What are my biggest risks?")
    names = {c["name"] for c in res["tool_calls"]}
    assert {"get_customer_intelligence", "get_data_quality"} <= names


def test_monte_carlo_via_assistant_is_forecast(db):
    seed(db)
    res = ask(db, "run a monte carlo on raising prices 10%")
    call = next(c for c in res["tool_calls"] if c["name"] == "run_monte_carlo")
    assert call["provenance"] == "FORECAST"
    assert "probability" in res["answer"].lower()


def test_execute_unknown_tool_is_safe(db):
    assert "error" in execute_tool(db, "does_not_exist", {})


def test_assistant_writes_audit_log(db):
    seed(db)
    from app.models.system import AuditLog

    before = db.query(AuditLog).count()
    ask(db, "How is my business?", user=None)
    after = db.query(AuditLog).count()
    assert after == before + 1
    last = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
    assert last.action == "AI_QUERY"


def test_assistant_api(client, auth_headers, db):
    seed(db)
    r = client.post("/api/v1/assistant/ask", headers=auth_headers("VIEWER"),
                    json={"question": "How is my business doing?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provenance"] == "AI_INTERPRETATION"
    assert body["tool_calls"]

    tools = client.get("/api/v1/assistant/tools", headers=auth_headers("VIEWER"))
    assert tools.status_code == 200
    assert any(t["name"] == "run_scenario" for t in tools.json()["tools"])


# --- Phase: assistant as a control layer (mutating actions) ---
def _mk_user(db, role):
    from app.core.security import hash_password
    from app.models.user import User
    u = db.query(User).filter_by(email=f"{role.lower()}@act.example.com").first()
    if not u:
        u = User(email=f"{role.lower()}@act.example.com", full_name=role,
                 hashed_password=hash_password("pw123456"), role=role)
        db.add(u)
        db.commit()
        db.refresh(u)
    return u


def test_assistant_creates_customer_via_action(db):
    from sqlalchemy import func, select

    from app.models.customer import Customer
    seed(db)
    user = _mk_user(db, "STAFF")
    before = db.scalar(select(func.count(Customer.id)))
    res = ask(db, "create a customer called Test Motors in Lagos", user=user)
    assert "create_customer" in res["actions_taken"]
    assert db.scalar(select(func.count(Customer.id))) == before + 1
    c = db.scalar(select(Customer).where(Customer.name == "Test Motors"))
    assert c is not None and c.location == "Lagos" and c.data_origin == "REAL"


def test_assistant_action_respects_permissions(db):
    seed(db)
    viewer = _mk_user(db, "VIEWER")
    res = ask(db, "add customer Blocked Ltd", user=viewer)
    call = next(c for c in res["tool_calls"] if c["name"] == "create_customer")
    assert "error" in call["result"]          # role-gated
    assert res["actions_taken"] == []          # nothing changed


def test_assistant_sets_product_price(db):
    from sqlalchemy import select

    from app.models.product import Product
    seed(db)
    user = _mk_user(db, "MANAGER")
    res = ask(db, "set the price of Timing belt 209 to 250000", user=user)
    assert "set_product_price" in res["actions_taken"]
    p = db.scalar(select(Product).where(Product.name == "Timing belt 209"))
    assert float(p.selling_price) == 250000.0
