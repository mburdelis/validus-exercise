import dataclasses
from datetime import datetime, timezone
from typing import Any

from .exceptions import InvalidStateTransitionError, UnauthorizedActionError
from .models import HistoryEntry, TradeAction, TradeDetails, TradeState
from .validation import validate_trade_details

# Maps (current_state, action) -> next_state.  Single source of truth for
# permitted transitions; adding a new state/action only requires a new entry.
_TRANSITIONS: dict[tuple[TradeState, TradeAction], TradeState] = {
    (TradeState.DRAFT, TradeAction.SUBMIT): TradeState.PENDING_APPROVAL,
    (TradeState.PENDING_APPROVAL, TradeAction.APPROVE): TradeState.APPROVED,
    (TradeState.PENDING_APPROVAL, TradeAction.UPDATE): TradeState.NEEDS_REAPPROVAL,
    (TradeState.PENDING_APPROVAL, TradeAction.CANCEL): TradeState.CANCELLED,
    (TradeState.NEEDS_REAPPROVAL, TradeAction.APPROVE): TradeState.APPROVED,
    (TradeState.NEEDS_REAPPROVAL, TradeAction.CANCEL): TradeState.CANCELLED,
    (TradeState.APPROVED, TradeAction.SEND_TO_EXECUTE): TradeState.SENT_TO_COUNTERPARTY,
    (TradeState.APPROVED, TradeAction.CANCEL): TradeState.CANCELLED,
    (TradeState.SENT_TO_COUNTERPARTY, TradeAction.BOOK): TradeState.EXECUTED,
    (TradeState.SENT_TO_COUNTERPARTY, TradeAction.CANCEL): TradeState.CANCELLED,
}


class Trade:
    """State machine for a single trade's approval workflow.

    Authorization model
    -------------------
    * ``requester_id``  – the user who submitted the trade; set on Submit.
    * ``approver_id``   – the user who first takes an approver action (Approve
      or Update); set lazily.  Before it is set, *any* non-requester may act in
      the approver role (e.g. to cancel or update a pending trade).

    Roles per action
    ----------------
    Submit          – requester only.
    Approve (Pending→Approved)   – any non-requester (becomes the approver).
    Approve (NeedsReapproval→Approved) – requester only (reconfirms changes).
    Update          – non-requester only (becomes approver if not already set).
    SendToExecute   – approver only.
    Book            – requester or approver.
    Cancel          – requester or approver (or any non-requester when no
                      approver has been designated yet).
    """

    def __init__(self, trade_id: str, requester_id: str, details: TradeDetails) -> None:
        self.trade_id: str = trade_id
        self.requester_id: str = requester_id
        self.approver_id: str | None = None
        self.state: TradeState = TradeState.DRAFT
        self.current_details: TradeDetails = details.copy()
        self.history: list[HistoryEntry] = []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _record(
        self,
        action: TradeAction,
        user_id: str,
        state_before: TradeState,
        state_after: TradeState,
        notes: str = "",
    ) -> None:
        self.history.append(
            HistoryEntry(
                step=len(self.history) + 1,
                action=action,
                user_id=user_id,
                state_before=state_before,
                state_after=state_after,
                timestamp=self._now(),
                trade_details_snapshot=self.current_details.copy(),
                notes=notes,
            )
        )

    def _transition(self, action: TradeAction) -> TradeState:
        """Return the next state or raise ``InvalidStateTransitionError``."""
        key = (self.state, action)
        if key not in _TRANSITIONS:
            allowed = [a.value for (s, a) in _TRANSITIONS if s == self.state]
            raise InvalidStateTransitionError(
                f"Action '{action.value}' is not allowed in state "
                f"'{self.state.value}'. "
                f"Allowed actions: {allowed if allowed else ['none (end state)']}."
            )
        return _TRANSITIONS[key]

    def _is_requester(self, user_id: str) -> bool:
        return user_id == self.requester_id

    def _is_approver(self, user_id: str) -> bool:
        if self.approver_id is not None:
            return user_id == self.approver_id
        # Before an approver is designated, any non-requester acts as approver.
        return not self._is_requester(user_id)

    def _can_cancel(self, user_id: str) -> bool:
        return self._is_requester(user_id) or self._is_approver(user_id)

    # ------------------------------------------------------------------
    # Public workflow actions
    # ------------------------------------------------------------------

    def submit(self, user_id: str) -> None:
        """Transition Draft → PendingApproval. Only the requester may submit."""
        next_state = self._transition(TradeAction.SUBMIT)
        if not self._is_requester(user_id):
            raise UnauthorizedActionError(
                f"Only the requester ('{self.requester_id}') may submit this trade."
            )
        state_before = self.state
        self.state = next_state
        self._record(TradeAction.SUBMIT, user_id, state_before, next_state, "Trade submitted for approval.")

    def approve(self, user_id: str) -> None:
        """Approve the trade.

        * From ``PendingApproval``: any non-requester; they become the approver.
        * From ``NeedsReapproval``: the original requester reconfirms.
        """
        next_state = self._transition(TradeAction.APPROVE)

        if self.state == TradeState.PENDING_APPROVAL:
            if self._is_requester(user_id):
                raise UnauthorizedActionError(
                    "The requester cannot approve their own trade."
                )
            self.approver_id = user_id
            notes = "Approver confirms trade."
        else:  # NEEDS_REAPPROVAL
            if not self._is_requester(user_id):
                raise UnauthorizedActionError(
                    f"Only the original requester ('{self.requester_id}') may "
                    "reapprove after an update."
                )
            notes = "Requester reapproves updated trade details."

        state_before = self.state
        self.state = next_state
        self._record(TradeAction.APPROVE, user_id, state_before, next_state, notes)

    def cancel(self, user_id: str) -> None:
        """Cancel the trade. Requester or approver may cancel."""
        next_state = self._transition(TradeAction.CANCEL)
        if not self._can_cancel(user_id):
            raise UnauthorizedActionError(
                f"Only the requester ('{self.requester_id}') or approver may cancel."
            )
        state_before = self.state
        self.state = next_state
        self._record(TradeAction.CANCEL, user_id, state_before, next_state, "Trade cancelled.")

    def update(self, user_id: str, new_details: TradeDetails) -> None:
        """Update trade details (PendingApproval → NeedsReapproval).

        Only a non-requester (approver) may update.  The updated details are
        validated before the transition occurs.
        """
        next_state = self._transition(TradeAction.UPDATE)
        if self._is_requester(user_id):
            raise UnauthorizedActionError(
                "The requester cannot update their own trade during approval; "
                "an approver must make changes."
            )
        validate_trade_details(new_details)
        if self.approver_id is None:
            self.approver_id = user_id
        state_before = self.state
        self.current_details = new_details.copy()
        self.state = next_state
        self._record(
            TradeAction.UPDATE, user_id, state_before, next_state,
            "Approver updated trade details; reapproval required."
        )

    def send_to_execute(self, user_id: str) -> None:
        """Send the approved trade to the counterparty for execution."""
        next_state = self._transition(TradeAction.SEND_TO_EXECUTE)
        if not self._is_approver(user_id):
            raise UnauthorizedActionError(
                "Only the approver may send the trade to execute."
            )
        state_before = self.state
        self.state = next_state
        self._record(TradeAction.SEND_TO_EXECUTE, user_id, state_before, next_state, "Trade sent to counterparty.")

    def book(self, user_id: str, strike: float) -> None:
        """Book an executed trade, recording the agreed strike rate."""
        next_state = self._transition(TradeAction.BOOK)
        if not self._can_cancel(user_id):
            raise UnauthorizedActionError(
                "Only the requester or approver may book the trade."
            )
        state_before = self.state
        new_details = self.current_details.copy()
        new_details.strike = strike
        self.current_details = new_details
        self.state = next_state
        self._record(
            TradeAction.BOOK, user_id, state_before, next_state,
            f"Trade executed and booked with strike {strike}."
        )

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def get_history(self) -> list[HistoryEntry]:
        """Return a copy of the full action history."""
        return list(self.history)

    def get_details_at_version(self, version: int) -> TradeDetails:
        """Return a snapshot of trade details after the *version*-th action (1-indexed)."""
        if version < 1 or version > len(self.history):
            raise ValueError(
                f"Version {version} is out of range "
                f"(trade has {len(self.history)} history entries)."
            )
        return self.history[version - 1].trade_details_snapshot.copy()

    def diff(self, version1: int, version2: int) -> dict[str, tuple[Any, Any]]:
        """Return fields that differ between two versions of trade details.

        Returns ``{field_name: (value_at_v1, value_at_v2)}`` for every field
        whose value changed between *version1* and *version2*.
        """
        d1 = self.get_details_at_version(version1)
        d2 = self.get_details_at_version(version2)
        return {
            f.name: (getattr(d1, f.name), getattr(d2, f.name))
            for f in dataclasses.fields(TradeDetails)
            if getattr(d1, f.name) != getattr(d2, f.name)
        }

    def __repr__(self) -> str:
        return (
            f"Trade(id={self.trade_id!r}, state={self.state.value!r}, "
            f"requester={self.requester_id!r}, approver={self.approver_id!r})"
        )
