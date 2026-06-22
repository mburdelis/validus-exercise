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

trade = store.create_trade("User1", details)
print(f"Created:          {trade.state.value}")

store.submit(trade.trade_id, "User1")
print(f"After submit:     {trade.state.value}")

store.approve(trade.trade_id, "User2")
print(f"After approve:    {trade.state.value}")

store.send_to_execute(trade.trade_id, "User2")
print(f"After send:       {trade.state.value}")

store.book(trade.trade_id, "User1", strike=1.0875)
print(f"After book:       {trade.state.value}")
print(f"Strike:           {trade.current_details.strike}")