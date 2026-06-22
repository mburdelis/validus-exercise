from datetime import date
from trade_approval import TradeStore, TradeDetails, Direction

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
store.submit(trade.trade_id, "User1")         # step 1

store.patch(
    trade.trade_id, "User2",
    notional_amount=1_200_000,
    counterparty="Bank ABC",
    delivery_date=date(2025, 1, 20),
)                                             # step 2

diff = store.diff(trade.trade_id, 1, 2)
print(diff)
# {
#   "notional_amount": (1000000.0, 1200000.0),
#   "counterparty": ("Bank XYZ", "Bank ABC"),
#   "delivery_date": (date(2025, 1, 15), date(2025, 1, 20))
# }
