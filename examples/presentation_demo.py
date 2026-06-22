"""Demonstrates the three presentation.py functions and their output."""
import json
from datetime import date

from trade_approval import (
    Direction,
    TradeDetails,
    TradeStore,
    format_history_table,
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
store.submit(trade.trade_id, "User1")                            # → PendingApproval
store.patch(trade.trade_id, "User2", notional_amount=1_200_000)  # → NeedsReapproval
store.approve(trade.trade_id, "User1")                           # → Approved

# ------------------------------------------------------------------
# 1. trade_details_to_dict — serialise TradeDetails to a plain dict
# ------------------------------------------------------------------
print("=" * 60)
print("1. trade_details_to_dict()")
print("=" * 60)
d = trade_details_to_dict(trade.current_details)
print(json.dumps(d, indent=2))

# ------------------------------------------------------------------
# 2. history_entry_to_dict — serialise a single HistoryEntry to dict
# ------------------------------------------------------------------
print()
print("=" * 60)
print("2. history_entry_to_dict()  [showing the Update entry]")
print("=" * 60)
update_entry = store.get_history(trade.trade_id)[1]  # step 2 = patch/update
print(json.dumps(history_entry_to_dict(update_entry), indent=2))

# ------------------------------------------------------------------
# 3. format_history_table — human-readable table of all actions
# ------------------------------------------------------------------
print()
print("=" * 60)
print("3. format_history_table()")
print("=" * 60)
print(format_history_table(store.get_trade(trade.trade_id)))
