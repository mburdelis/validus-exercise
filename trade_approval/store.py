import uuid
from typing import Any

from .exceptions import TradeNotFoundError
from .models import HistoryEntry, TradeDetails, TradeState
from .trade import Trade
from .validation import validate_trade_details


class TradeStore:
    """In-memory registry of trades and the primary public API.

    All workflow actions are dispatched through this class, which locates the
    ``Trade`` object and delegates to its state-machine methods.  Swapping the
    in-memory dict for a database would only require changes here.
    """

    def __init__(self) -> None:
        self._trades: dict[str, Trade] = {}

    # ------------------------------------------------------------------
    # Trade lifecycle
    # ------------------------------------------------------------------

    def create_trade(self, requester_id: str, details: TradeDetails) -> Trade:
        """Create a new trade in ``Draft`` state.

        Validates *details* before persisting.  Returns the new ``Trade``
        object (which carries its generated ``trade_id``).
        """
        validate_trade_details(details)
        trade_id = str(uuid.uuid4())
        trade = Trade(trade_id, requester_id, details)
        self._trades[trade_id] = trade
        return trade

    def get_trade(self, trade_id: str) -> Trade:
        """Return the trade or raise ``TradeNotFoundError``."""
        trade = self._trades.get(trade_id)
        if trade is None:
            raise TradeNotFoundError(f"Trade '{trade_id}' not found.")
        return trade

    # ------------------------------------------------------------------
    # Workflow actions
    # ------------------------------------------------------------------

    def submit(self, trade_id: str, user_id: str) -> Trade:
        """Submit a draft trade for approval (Draft → PendingApproval)."""
        trade = self.get_trade(trade_id)
        trade.submit(user_id)
        return trade

    def approve(self, trade_id: str, user_id: str) -> Trade:
        """Approve a trade (PendingApproval → Approved or NeedsReapproval → Approved)."""
        trade = self.get_trade(trade_id)
        trade.approve(user_id)
        return trade

    def cancel(self, trade_id: str, user_id: str) -> Trade:
        """Cancel a trade from any non-terminal state."""
        trade = self.get_trade(trade_id)
        trade.cancel(user_id)
        return trade

    def update(self, trade_id: str, user_id: str, new_details: TradeDetails) -> Trade:
        """Update trade details, triggering reapproval (PendingApproval → NeedsReapproval)."""
        trade = self.get_trade(trade_id)
        trade.update(user_id, new_details)
        return trade

    def send_to_execute(self, trade_id: str, user_id: str) -> Trade:
        """Send an approved trade to the counterparty (Approved → SentToCounterparty)."""
        trade = self.get_trade(trade_id)
        trade.send_to_execute(user_id)
        return trade

    def book(self, trade_id: str, user_id: str, strike: float) -> Trade:
        """Book an executed trade with the agreed strike rate (SentToCounterparty → Executed)."""
        trade = self.get_trade(trade_id)
        trade.book(user_id, strike)
        return trade

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def get_history(self, trade_id: str) -> list[HistoryEntry]:
        """Return the full action history for a trade."""
        return self.get_trade(trade_id).get_history()

    def get_details_at_version(self, trade_id: str, version: int) -> TradeDetails:
        """Return trade details as they were after the *version*-th action (1-indexed)."""
        return self.get_trade(trade_id).get_details_at_version(version)

    def diff(
        self, trade_id: str, version1: int, version2: int
    ) -> dict[str, tuple[Any, Any]]:
        """Return field-level differences between two historical versions.

        Example::

            store.diff(trade_id, 1, 2)
            # {"notional_amount": (1_000_000, 1_200_000)}
        """
        return self.get_trade(trade_id).diff(version1, version2)

    def list_trades(self, state: TradeState | None = None) -> list[Trade]:
        """Return all trades, optionally filtered by *state*."""
        trades = list(self._trades.values())
        if state is not None:
            trades = [t for t in trades if t.state == state]
        return trades
