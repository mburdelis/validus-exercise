# Trade Approval Workflow Library

A Python library implementing the trade approval workflow described in the Validus case study.

## Requirements

- Python 3.11+
- [pydantic](https://docs.pydantic.dev/) ≥ 2.0
- [fastapi](https://fastapi.tiangolo.com/) ≥ 0.100 + uvicorn (for the REST API)
- pytest (for tests only)

Set up the virtual environment and install all dependencies:

```bash
uv venv                                                # create .venv
uv pip install --python .venv/bin/python -e ".[dev,api]"  # install everything
```

The `-e .` installs the `trade_approval` package itself in editable mode (so it is importable from any script). `[dev,api]` pulls in the optional extras: `pytest`, `fastapi`, and `uvicorn`.

---

## Project Structure

```
trade_approval/
├── exceptions.py     # Domain exceptions
├── models.py         # TradeDetails, HistoryEntry (Pydantic models), enums
├── trade.py          # Trade – the state machine
├── store.py          # TradeStore – in-memory registry and public API
└── presentation.py   # Serialisation and display formatting (presentation layer)

tests/
└── test_trade_approval.py  # 52 unit tests

examples/
└── scenarios.py    # All four case-study scenarios runnable end-to-end

api/
└── main.py         # FastAPI REST interface (wraps TradeStore as HTTP endpoints)
```

---

## Workflow Overview

```
Draft ──[Submit]──► PendingApproval ──[Approve]──────────────────► Approved
                           │                                            │
                        [Update]                                  [SendToExecute]
                           │                                            │
                     NeedsReapproval ──[Approve]──► Approved   SentToCounterparty
                           │                                            │
                        [Cancel]                                    [Book]
                           │                                            │
                       Cancelled ◄──[Cancel]──────────────────►  Executed
```

**States:** `Draft`, `PendingApproval`, `NeedsReapproval`, `Approved`,
`SentToCounterparty`, `Executed` (end), `Cancelled` (end).

---

## Quick Start

```python
from datetime import date
from trade_approval import TradeStore, TradeDetails, Direction

store = TradeStore()

details = TradeDetails(
    trading_entity="Acme Corp",
    counterparty="Bank XYZ",
    direction=Direction.BUY,       # or "Buy"
    notional_currency="EUR",
    notional_amount=1_000_000,
    underlying="EURUSD",           # "EUR/USD" also accepted
    trade_date=date(2025, 1, 10),
    value_date=date(2025, 1, 12),
    delivery_date=date(2025, 1, 15),
)

trade = store.create_trade("User1", details)   # → Draft
store.submit(trade.trade_id, "User1")           # → PendingApproval
store.approve(trade.trade_id, "User2")          # → Approved
store.send_to_execute(trade.trade_id, "User2")  # → SentToCounterparty
store.book(trade.trade_id, "User1", strike=1.0875)  # → Executed
```

---

## API Reference

### `TradeStore`

The single entry-point.  All methods return the `Trade` object.

| Method | Signature | Description |
|---|---|---|
| `create_trade` | `(requester_id, details) → Trade` | Create a trade in `Draft` state. Validates details. |
| `submit` | `(trade_id, user_id) → Trade` | Draft → PendingApproval. Only the requester. |
| `approve` | `(trade_id, user_id) → Trade` | PendingApproval → Approved (any non-requester). NeedsReapproval → Approved (requester only). |
| `cancel` | `(trade_id, user_id) → Trade` | → Cancelled. Requester or approver. |
| `update` | `(trade_id, user_id, new_details) → Trade` | PendingApproval → NeedsReapproval. Approver only. |
| `send_to_execute` | `(trade_id, user_id) → Trade` | Approved → SentToCounterparty. Approver only. |
| `book` | `(trade_id, user_id, strike) → Trade` | SentToCounterparty → Executed. Requester or approver. Records the strike rate. |
| `get_history` | `(trade_id) → list[HistoryEntry]` | Full ordered action history. |
| `get_details_at_version` | `(trade_id, version) → TradeDetails` | Snapshot after the *n*-th action (1-indexed). |
| `diff` | `(trade_id, v1, v2) → dict` | Fields that changed between two versions: `{field: (old, new)}`. |
| `list_trades` | `(state=None) → list[Trade]` | All trades, optionally filtered by state. |
| `get_trade` | `(trade_id) → Trade` | Fetch a trade by ID. |

### `presentation` module

Serialisation and display functions. Import from `trade_approval` directly:

```python
from trade_approval import format_history_table, trade_details_to_dict, history_entry_to_dict
```

| Function | Signature | Description |
|---|---|---|
| `format_history_table` | `(trade: Trade) → str` | Human-readable tabular history. |
| `trade_details_to_dict` | `(details: TradeDetails) → dict` | Serialise trade details to a plain dict with string values. |
| `history_entry_to_dict` | `(entry: HistoryEntry) → dict` | Serialise a history entry to a plain dict (suitable for JSON export). |

### `TradeDetails`

A frozen [Pydantic](https://docs.pydantic.dev/) `BaseModel` — all validation runs automatically at construction time.

```python
class TradeDetails(BaseModel):
    trading_entity: str
    counterparty: str
    direction: Direction          # Direction.BUY / Direction.SELL (or "Buy"/"Sell")
    notional_currency: str        # ISO 4217 code, e.g. "EUR"
    notional_amount: float        # must be > 0
    underlying: str               # two-currency pair, e.g. "EURUSD" or "EUR/USD"
    trade_date: date
    value_date: date
    delivery_date: date
    style: str = "Forward"
    strike: float | None = None   # set by Book action
```

**Validation rules enforced at construction (raises `pydantic.ValidationError`):**

- `trading_entity` and `counterparty` must be non-empty.
- `notional_currency` must be a valid ISO 4217 / IBAN code.
- `notional_amount` must be positive.
- `underlying` must be exactly two valid ISO 4217 codes (`"EURUSD"`, `"EUR/USD"` etc.).
- `notional_currency` must be one of the two currencies in `underlying`.
- `trade_date ≤ value_date ≤ delivery_date`.

### `HistoryEntry`

A frozen Pydantic `BaseModel` — immutable once created.

```python
class HistoryEntry(BaseModel):
    step: int
    action: TradeAction
    user_id: str
    state_before: TradeState
    state_after: TradeState
    timestamp: datetime           # UTC
    trade_details_snapshot: TradeDetails
    notes: str
```

Use `history_entry_to_dict(entry)` from `trade_approval.presentation` to serialise to a plain dict for JSON export.

### Exceptions

| Exception | When raised |
|---|---|
| `pydantic.ValidationError` | `TradeDetails` constructed with invalid data. |
| `InvalidStateTransitionError` | Action not permitted in the current state. |
| `UnauthorizedActionError` | User not authorised to perform the action. |
| `TradeNotFoundError` | `trade_id` not found in the store. |
| `TradeWorkflowError` | Base class for all workflow exceptions. |

---

## Authorization Model

Each trade tracks two principals:

- **Requester** (`trade.requester_id`) – set when the trade is created (the user who will submit it).
- **Approver** (`trade.approver_id`) – set lazily on the first `approve` or `update` action. Until then any non-requester may act in the approver role.

| Action | Authorized users |
|---|---|
| Submit | Requester only |
| Approve (from PendingApproval) | Any non-requester (becomes the approver) |
| Approve (from NeedsReapproval) | Requester only (reconfirms changes) |
| Update | Non-requester only |
| SendToExecute | Approver only |
| Book | Requester or approver |
| Cancel | Requester or approver |

---

## Example Scenarios

### Scenario 1 – Submit and Approve

```python
store.submit(trade.trade_id, "User1")   # Draft → PendingApproval
store.approve(trade.trade_id, "User2")  # PendingApproval → Approved
```

### Scenario 2 – Update Requiring Reapproval

```python
store.submit(trade.trade_id, "User1")                    # → PendingApproval
store.update(trade.trade_id, "User2", updated_details)   # → NeedsReapproval
store.approve(trade.trade_id, "User1")                   # → Approved

diff = store.diff(trade.trade_id, 1, 2)
# {"notional_amount": (1000000, 1200000)}
```

### Scenario 3 – Full Execution

```python
store.submit(trade.trade_id, "User1")
store.approve(trade.trade_id, "User2")
store.send_to_execute(trade.trade_id, "User2")
store.book(trade.trade_id, "User1", strike=1.0875)
# trade.state → Executed,  trade.current_details.strike → 1.0875
```

### Scenario 4 – History and Diff

```python
history = store.get_history(trade.trade_id)
# list of HistoryEntry, one per action

from trade_approval import format_history_table, trade_details_to_dict

print(format_history_table(store.get_trade(trade.trade_id)))
# Step   Action  User   State Before  State After  Timestamp  Notes
# …

v1 = store.get_details_at_version(trade.trade_id, 1)
print(trade_details_to_dict(v1))           # plain dict, ready for JSON

diff = store.diff(trade.trade_id, 1, 2)   # changes made by Update
```

Run all scenarios:

```bash
.venv/bin/python examples/scenarios.py
```

---

## Running Tests

```bash
.venv/bin/python -m pytest tests/ -v
```

52 tests covering:
- All four case-study scenarios end-to-end
- Full validation rule coverage
- Every invalid state transition
- All authorization edge cases
- History snapshot isolation (mutations don't corrupt past versions)

---

## Running the REST API

Start the server:

```bash
.venv/bin/uvicorn api.main:app --reload
```

Then open **http://127.0.0.1:8000/docs** in your browser for the interactive Swagger UI — every endpoint is listed there with request/response schemas and an "Execute" button to call it directly. No frontend required.

Available endpoints:

| Method | Path | Description |
|---|---|---|
| `POST` | `/trades` | Create a trade in Draft state |
| `GET` | `/trades` | List all trades (optional `?state=Draft`) |
| `GET` | `/trades/{id}` | Get a single trade |
| `POST` | `/trades/{id}/submit` | Draft → PendingApproval |
| `POST` | `/trades/{id}/approve` | → Approved |
| `POST` | `/trades/{id}/update` | → NeedsReapproval |
| `POST` | `/trades/{id}/cancel` | → Cancelled |
| `POST` | `/trades/{id}/send-to-execute` | → SentToCounterparty |
| `POST` | `/trades/{id}/book` | → Executed (records strike rate) |
| `GET` | `/trades/{id}/history` | Full action history |
| `GET` | `/trades/{id}/diff?v1=1&v2=2` | Field-level diff between two versions |

---

## Design Notes

**State machine as a dict.** The single `_TRANSITIONS` dict in [trade.py](trade_approval/trade.py) is the sole source of truth for permitted transitions. Adding a new state or action requires only a new entry there.

**Immutable history snapshots.** Each `HistoryEntry` stores a `copy.deepcopy` of `TradeDetails` at the moment of the action, so past versions are never corrupted by subsequent updates.

**Diff between any two versions.** `diff(v1, v2)` compares snapshots at arbitrary steps, not just consecutive ones.

**Pydantic models.** `TradeDetails` and `HistoryEntry` are frozen Pydantic `BaseModel` subclasses. All field-level and cross-field validation runs automatically at construction time, so by the time a `TradeDetails` reaches the store or trade, it is guaranteed valid. `model_dump(mode="json")` in `presentation.py` gives JSON-safe serialisation with zero boilerplate.

**Layered architecture.** The code is split into three distinct layers with one-way dependencies: domain (`models.py`, `trade.py`) → infrastructure (`store.py`) → presentation (`presentation.py`). Domain objects have no knowledge of how they are stored or displayed. Serialisation (`trade_details_to_dict`, `history_entry_to_dict`) and formatting (`format_history_table`) live exclusively in `presentation.py`.

**Storage abstraction.** `TradeStore` wraps an in-memory dict. Replacing it with a database adapter would only require changes inside `store.py`; the `Trade` state-machine logic is unaffected.

**UTC timestamps.** All history entries are stamped with `datetime.now(timezone.utc)`.

---

## AI Usage Disclosure

This implementation was developed with the assistance of Claude Code (Anthropic). My specific contributions included:
- Designing the overall architecture (state machine dict, snapshot strategy, two-principal authorization model).
- Specifying the validation rules for the `underlying` field (parse as two 3-char ISO 4217 codes, verify notional currency is one of them, accept `"EUR/USD"` separator notation).
- Choosing the lazy-approver approach (approver_id set on first approver action rather than requiring pre-registration).
- Authoring the test scenarios and edge cases, including the snapshot-isolation test.
- Reviewing and correcting generated code throughout.
