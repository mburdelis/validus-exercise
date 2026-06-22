"""Tests for the FastAPI REST layer (api/main.py)."""
import pytest
from fastapi.testclient import TestClient

from api.main import app, store

client = TestClient(app)

VALID_DETAILS = {
    "trading_entity": "Acme Corp",
    "counterparty": "Bank XYZ",
    "direction": "Buy",
    "notional_currency": "EUR",
    "notional_amount": 1_000_000,
    "underlying": "EURUSD",
    "trade_date": "2025-01-10",
    "value_date": "2025-01-12",
    "delivery_date": "2025-01-15",
    "strike": None,
}


@pytest.fixture(autouse=True)
def clear_store():
    """Reset the in-memory store before each test so tests don't interfere."""
    store._trades.clear()


def create_trade(requester_id="User1") -> str:
    resp = client.post("/trades", json={"requester_id": requester_id, "details": VALID_DETAILS})
    assert resp.status_code == 201
    return resp.json()["trade_id"]


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

class TestCreateTrade:
    def test_create_returns_201(self):
        resp = client.post("/trades", json={"requester_id": "User1", "details": VALID_DETAILS})
        assert resp.status_code == 201

    def test_create_returns_draft_state(self):
        resp = client.post("/trades", json={"requester_id": "User1", "details": VALID_DETAILS})
        assert resp.json()["state"] == "Draft"

    def test_create_invalid_currency_returns_422(self):
        details = {**VALID_DETAILS, "notional_currency": "XXX"}
        resp = client.post("/trades", json={"requester_id": "User1", "details": details})
        assert resp.status_code == 422

    def test_create_negative_amount_returns_422(self):
        details = {**VALID_DETAILS, "notional_amount": -1}
        resp = client.post("/trades", json={"requester_id": "User1", "details": details})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Get / List
# ---------------------------------------------------------------------------

class TestGetAndList:
    def test_get_trade(self):
        trade_id = create_trade()
        resp = client.get(f"/trades/{trade_id}")
        assert resp.status_code == 200
        assert resp.json()["trade_id"] == trade_id

    def test_get_unknown_trade_returns_404(self):
        resp = client.get("/trades/nonexistent-id")
        assert resp.status_code == 404

    def test_list_trades(self):
        create_trade()
        create_trade()
        resp = client.get("/trades")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_list_trades_filtered_by_state(self):
        trade_id = create_trade()
        client.post(f"/trades/{trade_id}/submit", json={"user_id": "User1"})
        resp = client.get("/trades?state=PendingApproval")
        assert len(resp.json()) == 1


# ---------------------------------------------------------------------------
# Workflow actions
# ---------------------------------------------------------------------------

class TestWorkflowActions:
    def test_submit(self):
        trade_id = create_trade()
        resp = client.post(f"/trades/{trade_id}/submit", json={"user_id": "User1"})
        assert resp.status_code == 200
        assert resp.json()["state"] == "PendingApproval"

    def test_approve(self):
        trade_id = create_trade()
        client.post(f"/trades/{trade_id}/submit", json={"user_id": "User1"})
        resp = client.post(f"/trades/{trade_id}/approve", json={"user_id": "User2"})
        assert resp.status_code == 200
        assert resp.json()["state"] == "Approved"

    def test_cancel(self):
        trade_id = create_trade()
        client.post(f"/trades/{trade_id}/submit", json={"user_id": "User1"})
        resp = client.post(f"/trades/{trade_id}/cancel", json={"user_id": "User1"})
        assert resp.status_code == 200
        assert resp.json()["state"] == "Cancelled"

    def test_update(self):
        trade_id = create_trade()
        client.post(f"/trades/{trade_id}/submit", json={"user_id": "User1"})
        updated = {**VALID_DETAILS, "notional_amount": 1_500_000}
        resp = client.post(f"/trades/{trade_id}/update",
                           json={"user_id": "User2", "new_details": updated})
        assert resp.status_code == 200
        assert resp.json()["state"] == "NeedsReapproval"

    def test_patch(self):
        trade_id = create_trade()
        client.post(f"/trades/{trade_id}/submit", json={"user_id": "User1"})
        resp = client.post(f"/trades/{trade_id}/patch",
                           json={"user_id": "User2", "fields": {"notional_amount": 1_500_000}})
        assert resp.status_code == 200
        assert resp.json()["state"] == "NeedsReapproval"
        assert resp.json()["current_details"]["notional_amount"] == 1_500_000

    def test_send_to_execute(self):
        trade_id = create_trade()
        client.post(f"/trades/{trade_id}/submit", json={"user_id": "User1"})
        client.post(f"/trades/{trade_id}/approve", json={"user_id": "User2"})
        resp = client.post(f"/trades/{trade_id}/send-to-execute", json={"user_id": "User2"})
        assert resp.status_code == 200
        assert resp.json()["state"] == "SentToCounterparty"

    def test_book(self):
        trade_id = create_trade()
        client.post(f"/trades/{trade_id}/submit", json={"user_id": "User1"})
        client.post(f"/trades/{trade_id}/approve", json={"user_id": "User2"})
        client.post(f"/trades/{trade_id}/send-to-execute", json={"user_id": "User2"})
        resp = client.post(f"/trades/{trade_id}/book",
                           json={"user_id": "User1", "strike": 1.0875})
        assert resp.status_code == 200
        assert resp.json()["state"] == "Executed"
        assert resp.json()["current_details"]["strike"] == 1.0875


# ---------------------------------------------------------------------------
# Error responses
# ---------------------------------------------------------------------------

class TestErrorResponses:
    def test_invalid_transition_returns_409(self):
        trade_id = create_trade()
        resp = client.post(f"/trades/{trade_id}/approve", json={"user_id": "User2"})
        assert resp.status_code == 409

    def test_unauthorized_returns_403(self):
        trade_id = create_trade()
        client.post(f"/trades/{trade_id}/submit", json={"user_id": "User1"})
        resp = client.post(f"/trades/{trade_id}/approve", json={"user_id": "User1"})
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# History and diff
# ---------------------------------------------------------------------------

class TestAllHistory:
    def test_get_all_history_empty(self):
        resp = client.get("/history")
        assert resp.status_code == 200
        assert resp.json() == {}

    def test_get_all_history_contains_all_trades(self):
        trade_id_1 = create_trade()
        trade_id_2 = create_trade()
        client.post(f"/trades/{trade_id_1}/submit", json={"user_id": "User1"})
        resp = client.get("/history")
        assert resp.status_code == 200
        data = resp.json()
        assert trade_id_1 in data
        assert trade_id_2 in data

    def test_get_all_history_draft_trade_has_empty_history(self):
        trade_id = create_trade()
        resp = client.get("/history")
        assert resp.json()[trade_id] == []

    def test_get_all_history_shows_correct_entries(self):
        trade_id = create_trade()
        client.post(f"/trades/{trade_id}/submit", json={"user_id": "User1"})
        client.post(f"/trades/{trade_id}/approve", json={"user_id": "User2"})
        resp = client.get("/history")
        entries = resp.json()[trade_id]
        assert len(entries) == 2
        assert entries[0]["action"] == "Submit"
        assert entries[1]["action"] == "Approve"


class TestHistoryAndDiff:
    def test_get_history(self):
        trade_id = create_trade()
        client.post(f"/trades/{trade_id}/submit", json={"user_id": "User1"})
        resp = client.get(f"/trades/{trade_id}/history")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["action"] == "Submit"

    def test_diff(self):
        trade_id = create_trade()
        client.post(f"/trades/{trade_id}/submit", json={"user_id": "User1"})
        client.post(f"/trades/{trade_id}/patch",
                    json={"user_id": "User2", "fields": {"notional_amount": 1_500_000}})
        resp = client.get(f"/trades/{trade_id}/diff?v1=1&v2=2")
        assert resp.status_code == 200
        assert "notional_amount" in resp.json()
