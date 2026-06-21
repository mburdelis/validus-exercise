"""Presentation layer: serialisation and display formatting.

All functions here take domain objects as input and produce strings or
plain dicts.  Nothing in the domain (Trade, TradeDetails, HistoryEntry)
needs to know this module exists.
"""
from .models import HistoryEntry, TradeDetails
from .trade import Trade


def trade_details_to_dict(details: TradeDetails) -> dict:
    """Serialise a TradeDetails instance to a plain dict with JSON-compatible values."""
    return details.model_dump(mode="json")


def history_entry_to_dict(entry: HistoryEntry) -> dict:
    """Serialise a HistoryEntry to a plain dict suitable for JSON export."""
    return entry.model_dump(mode="json", exclude={"trade_details_snapshot"})


def format_history_table(trade: Trade) -> str:
    """Return a human-readable table of a trade's action history."""
    col = (6, 16, 10, 22, 22, 32)
    header = (
        f"{'Step':<{col[0]}} {'Action':<{col[1]}} {'User':<{col[2]}} "
        f"{'State Before':<{col[3]}} {'State After':<{col[4]}} "
        f"{'Timestamp':<{col[5]}} Notes"
    )
    sep = "-" * (sum(col) + 10)
    rows = [header, sep]
    for h in trade.history:
        rows.append(
            f"{h.step:<{col[0]}} {h.action.value:<{col[1]}} "
            f"{h.user_id:<{col[2]}} {h.state_before.value:<{col[3]}} "
            f"{h.state_after.value:<{col[4]}} "
            f"{h.timestamp.strftime('%Y-%m-%dT%H:%M:%SZ'):<{col[5]}} "
            f"{h.notes}"
        )
    return "\n".join(rows)
