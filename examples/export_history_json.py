"""Demonstrates exporting a trade's full history to a JSON file.

The presentation layer produces JSON-compatible dicts; this script shows
how to persist them to disk using the standard library's json module.
Output file: examples/trade_history.json
"""
import json
from datetime import date
from pathlib import Path

from trade_approval import (
    Direction,
    TradeDetails,
    TradeStore,
    history_entry_to_dict,
    trade_details_to_dict,
)

store = TradeStore()

details = TradeDetails(
    trading_entity="Acme Corp",
    counterparty="Bank XYZ",
    direction=Direction.BUY,
    notional_currency="EUR",
    notional_amount=1_000_000,
    underlying="EURUSD",
    trade_date=date(2025, 1, 10),
    value_date=date(2025, 1, 12),
    delivery_date=date(2025, 1, 15),
)

trade = store.create_trade("User1", details)
store.submit(trade.trade_id, "User1")
store.patch(trade.trade_id, "User2", notional_amount=1_200_000)
store.approve(trade.trade_id, "User1")
store.send_to_execute(trade.trade_id, "User2")
store.book(trade.trade_id, "User1", strike=1.0875)

export = {
    "trade_id": trade.trade_id,
    "state": trade.state.value,
    "current_details": trade_details_to_dict(trade.current_details),
    "history": [history_entry_to_dict(e) for e in store.get_history(trade.trade_id)],
}

output_path = Path(__file__).parent / "trade_history.json"
with open(output_path, "w") as f:
    json.dump(export, f, indent=2)

print(f"Exported {len(export['history'])} history entries to {output_path}")
print(json.dumps(export, indent=2))
