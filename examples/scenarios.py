"""Runnable examples reproducing every scenario from the case study.

Usage::

    python -m examples.scenarios          # from the project root
    # or
    python examples/scenarios.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date

from trade_approval import Direction, TradeDetails, TradeStore


def _details(notional_amount: float = 1_000_000.0) -> TradeDetails:
    return TradeDetails(
        trading_entity="Acme Corp",
        counterparty="Bank XYZ",
        direction=Direction.BUY,
        notional_currency="EUR",
        notional_amount=notional_amount,
        underlying="EURUSD",
        trade_date=date(2025, 1, 10),
        value_date=date(2025, 1, 12),
        delivery_date=date(2025, 1, 15),
    )


# ---------------------------------------------------------------------------
# Scenario 1 – Submit and Approve
# ---------------------------------------------------------------------------

def scenario_1() -> None:
    print("\n" + "=" * 70)
    print("Scenario 1: Submitting and Approving a Trade")
    print("=" * 70)

    store = TradeStore()
    trade = store.create_trade("User1", _details())
    store.submit(trade.trade_id, "User1")
    store.approve(trade.trade_id, "User2")

    print(store.format_history_table(trade.trade_id))
    print(f"\nFinal state : {trade.state.value}")
    print(f"Approver    : {trade.approver_id}")


# ---------------------------------------------------------------------------
# Scenario 2 – Update Requires Reapproval
# ---------------------------------------------------------------------------

def scenario_2() -> None:
    print("\n" + "=" * 70)
    print("Scenario 2: Updating a Trade Detail")
    print("=" * 70)

    store = TradeStore()
    trade = store.create_trade("User1", _details(notional_amount=1_000_000))
    store.submit(trade.trade_id, "User1")
    store.update(trade.trade_id, "User2", _details(notional_amount=1_200_000))
    store.approve(trade.trade_id, "User1")

    print(store.format_history_table(trade.trade_id))

    diff = store.diff(trade.trade_id, 1, 2)
    print(f"\nDiff (v1 → v2): {diff}")
    print(f"Final state   : {trade.state.value}")


# ---------------------------------------------------------------------------
# Scenario 3 – Full Execution
# ---------------------------------------------------------------------------

def scenario_3() -> None:
    print("\n" + "=" * 70)
    print("Scenario 3: Full Execution Flow")
    print("=" * 70)

    store = TradeStore()
    trade = store.create_trade("User1", _details())
    store.submit(trade.trade_id, "User1")
    store.approve(trade.trade_id, "User2")
    store.send_to_execute(trade.trade_id, "User2")
    store.book(trade.trade_id, "User1", strike=1.0875)

    print(store.format_history_table(trade.trade_id))
    print(f"\nFinal state : {trade.state.value}")
    print(f"Strike      : {trade.current_details.strike}")


# ---------------------------------------------------------------------------
# Scenario 4 – History API and Diff API
# ---------------------------------------------------------------------------

def scenario_4() -> None:
    print("\n" + "=" * 70)
    print("Scenario 4: Viewing History and Differences")
    print("=" * 70)

    store = TradeStore()
    trade = store.create_trade("User1", _details(notional_amount=1_000_000))
    store.submit(trade.trade_id, "User1")
    store.update(trade.trade_id, "User2", _details(notional_amount=1_200_000))
    store.approve(trade.trade_id, "User1")
    store.send_to_execute(trade.trade_id, "User2")
    store.book(trade.trade_id, "User2", strike=1.0923)

    print("\n--- History table ---")
    print(store.format_history_table(trade.trade_id))

    print("\n--- Trade details at version 1 (after Submit) ---")
    v1 = store.get_details_at_version(trade.trade_id, 1)
    for k, v in v1.to_dict().items():
        print(f"  {k}: {v}")

    print("\n--- Diff between version 1 and version 2 (after Update) ---")
    diff = store.diff(trade.trade_id, 1, 2)
    for field, (old, new) in diff.items():
        print(f"  {field}: {old!r} → {new!r}")

    print("\n--- Trade details at final version (after Book) ---")
    vn = store.get_details_at_version(trade.trade_id, len(store.get_history(trade.trade_id)))
    for k, v in vn.to_dict().items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    scenario_1()
    scenario_2()
    scenario_3()
    scenario_4()
