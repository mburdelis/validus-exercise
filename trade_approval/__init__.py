"""trade_approval – Trade Approval Workflow Library.

Public API surface:

    from trade_approval import (
        TradeStore,      # entry point – create and drive trades
        TradeDetails,    # value object describing a trade
        Direction,       # Buy / Sell enum
        TradeState,      # state enum
        TradeAction,     # action enum
        HistoryEntry,    # history record
        VALID_CURRENCIES,
        # Exceptions
        TradeWorkflowError,
        InvalidStateTransitionError,
        UnauthorizedActionError,
        TradeNotFoundError,
    )
"""

from .exceptions import (
    InvalidStateTransitionError,
    TradeNotFoundError,
    TradeWorkflowError,
    UnauthorizedActionError,
)
from .models import (
    Direction,
    HistoryEntry,
    TradeAction,
    TradeDetails,
    TradeState,
    VALID_CURRENCIES,
)
from .presentation import format_history_table, history_entry_to_dict, trade_details_to_dict
from .store import TradeStore
from .trade import Trade

__all__ = [
    "TradeStore",
    "Trade",
    "format_history_table",
    "trade_details_to_dict",
    "history_entry_to_dict",
    "TradeDetails",
    "TradeState",
    "TradeAction",
    "Direction",
    "HistoryEntry",
    "VALID_CURRENCIES",
    "TradeWorkflowError",
    "InvalidStateTransitionError",
    "UnauthorizedActionError",
    "TradeNotFoundError",
]
