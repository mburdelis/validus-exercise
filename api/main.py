"""FastAPI application exposing the trade approval workflow as a REST API.

Run with:
    uvicorn api.main:app --reload

Then open http://127.0.0.1:8000/docs for the interactive Swagger UI.
"""
from typing import Any

from fastapi import Body, FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from trade_approval import (
    Direction,
    InvalidStateTransitionError,
    TradeDetails,
    TradeNotFoundError,
    TradeState,
    TradeStore,
    UnauthorizedActionError,
)
from trade_approval.models import HistoryEntry

app = FastAPI(
    title="Trade Approval API",
    description="REST interface for the Validus trade approval workflow.",
    version="0.1.0",
)

store = TradeStore()


# ---------------------------------------------------------------------------
# Exception handlers — map domain exceptions to HTTP status codes
# ---------------------------------------------------------------------------

@app.exception_handler(TradeNotFoundError)
async def not_found_handler(request, exc):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(UnauthorizedActionError)
async def unauthorized_handler(request, exc):
    return JSONResponse(status_code=403, content={"detail": str(exc)})


@app.exception_handler(InvalidStateTransitionError)
async def invalid_transition_handler(request, exc):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

_EXAMPLE_DETAILS = {
    "trading_entity": "Acme Corp",
    "counterparty": "Bank XYZ",
    "direction": "Buy",
    "notional_currency": "EUR",
    "notional_amount": 1000000,
    "underlying": "EURUSD",
    "trade_date": "2025-01-10",
    "value_date": "2025-01-12",
    "delivery_date": "2025-01-15",
    "strike": None,
}


class CreateTradeRequest(BaseModel):
    model_config = {"json_schema_extra": {"example": {"requester_id": "User1", "details": _EXAMPLE_DETAILS}}}
    requester_id: str
    details: TradeDetails


class UserRequest(BaseModel):
    model_config = {"json_schema_extra": {"example": {"user_id": "User1"}}}
    user_id: str


class UpdateTradeRequest(BaseModel):
    model_config = {"json_schema_extra": {"example": {"user_id": "User2", "new_details": {**_EXAMPLE_DETAILS, "notional_amount": 1200000}}}}
    user_id: str
    new_details: TradeDetails


class BookRequest(BaseModel):
    model_config = {"json_schema_extra": {"example": {"user_id": "User1", "strike": 1.0875}}}
    user_id: str
    strike: float


class PatchTradeRequest(BaseModel):
    model_config = {"json_schema_extra": {"example": {"user_id": "User2", "fields": {"notional_amount": 1200000}}}}
    user_id: str
    fields: dict[str, Any]


class TradeResponse(BaseModel):
    trade_id: str
    requester_id: str
    approver_id: str | None
    state: TradeState
    current_details: TradeDetails


def _to_response(trade) -> TradeResponse:
    return TradeResponse(
        trade_id=trade.trade_id,
        requester_id=trade.requester_id,
        approver_id=trade.approver_id,
        state=trade.state,
        current_details=trade.current_details,
    )


def _make_serializable(v):
    """Convert a value to something JSON-safe (for diff responses)."""
    if hasattr(v, "value"):
        return v.value
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/trades", response_model=TradeResponse, status_code=201,
          summary="Create a new trade in Draft state")
def create_trade(req: CreateTradeRequest):
    trade = store.create_trade(req.requester_id, req.details)
    return _to_response(trade)


@app.get("/trades", response_model=list[TradeResponse],
         summary="List all trades, optionally filtered by state")
def list_trades(state: TradeState | None = None):
    return [_to_response(t) for t in store.list_trades(state)]


@app.get("/trades/{trade_id}", response_model=TradeResponse,
         summary="Get a single trade by ID")
def get_trade(trade_id: str):
    return _to_response(store.get_trade(trade_id))


@app.post("/trades/{trade_id}/submit", response_model=TradeResponse,
          summary="Submit a Draft trade for approval (Draft → PendingApproval)")
def submit(trade_id: str, req: UserRequest):
    return _to_response(store.submit(trade_id, req.user_id))


@app.post("/trades/{trade_id}/approve", response_model=TradeResponse,
          summary="Approve a trade (PendingApproval → Approved or NeedsReapproval → Approved)")
def approve(trade_id: str, req: UserRequest = Body(openapi_examples={"default": {"value": {"user_id": "User2"}}})):
    return _to_response(store.approve(trade_id, req.user_id))


@app.post("/trades/{trade_id}/cancel", response_model=TradeResponse,
          summary="Cancel a trade from any non-terminal state")
def cancel(trade_id: str, req: UserRequest):
    return _to_response(store.cancel(trade_id, req.user_id))


@app.post("/trades/{trade_id}/update", response_model=TradeResponse,
          summary="Update trade details, triggering reapproval (PendingApproval → NeedsReapproval)")
def update(trade_id: str, req: UpdateTradeRequest):
    return _to_response(store.update(trade_id, req.user_id, req.new_details))


@app.post("/trades/{trade_id}/patch", response_model=TradeResponse,
          summary="Partially update trade details — only supply the fields that change")
def patch(trade_id: str, req: PatchTradeRequest):
    return _to_response(store.patch(trade_id, req.user_id, **req.fields))


@app.post("/trades/{trade_id}/send-to-execute", response_model=TradeResponse,
          summary="Send an approved trade to the counterparty (Approved → SentToCounterparty)")
def send_to_execute(trade_id: str, req: UserRequest = Body(openapi_examples={"default": {"value": {"user_id": "User2"}}})):
    return _to_response(store.send_to_execute(trade_id, req.user_id))


@app.post("/trades/{trade_id}/book", response_model=TradeResponse,
          summary="Book an executed trade with the agreed strike rate (SentToCounterparty → Executed)")
def book(trade_id: str, req: BookRequest):
    return _to_response(store.book(trade_id, req.user_id, req.strike))


@app.get("/trades/{trade_id}/history", response_model=list[HistoryEntry],
         summary="Get the full action history for a trade")
def get_history(trade_id: str):
    return store.get_history(trade_id)


@app.get("/history", response_model=dict[str, list[HistoryEntry]],
         summary="Get action history for all trades, keyed by trade ID")
def get_all_history():
    return store.get_all_history()


@app.get("/trades/{trade_id}/diff",
         summary="Compare trade details between two history versions")
def diff(trade_id: str, v1: int, v2: int):
    result = store.diff(trade_id, v1, v2)
    return {
        field: [_make_serializable(before), _make_serializable(after)]
        for field, (before, after) in result.items()
    }
