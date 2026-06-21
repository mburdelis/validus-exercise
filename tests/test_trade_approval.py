"""Unit tests covering all key actions, state transitions, and validations."""
import pytest
from datetime import date

from trade_approval import (
    Direction,
    InvalidStateTransitionError,
    TradeAction,
    TradeDetails,
    TradeNotFoundError,
    TradeState,
    TradeStore,
    TradeValidationError,
    UnauthorizedActionError,
    format_history_table,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_details(**overrides) -> TradeDetails:
    defaults = dict(
        trading_entity="Acme Corp",
        counterparty="Bank XYZ",
        direction=Direction.BUY,
        notional_currency="EUR",
        notional_amount=1_000_000.0,
        underlying="EURUSD",
        trade_date=date(2025, 1, 10),
        value_date=date(2025, 1, 12),
        delivery_date=date(2025, 1, 15),
    )
    defaults.update(overrides)
    return TradeDetails(**defaults)


@pytest.fixture
def store() -> TradeStore:
    return TradeStore()


@pytest.fixture
def submitted_trade(store):
    trade = store.create_trade("User1", make_details())
    store.submit(trade.trade_id, "User1")
    return trade


@pytest.fixture
def approved_trade(store, submitted_trade):
    store.approve(submitted_trade.trade_id, "User2")
    return submitted_trade


# ---------------------------------------------------------------------------
# Scenario 1 – Submit and Approve
# ---------------------------------------------------------------------------

class TestScenario1SubmitAndApprove:
    def test_create_starts_in_draft(self, store):
        trade = store.create_trade("User1", make_details())
        assert trade.state == TradeState.DRAFT

    def test_submit_moves_to_pending_approval(self, store):
        trade = store.create_trade("User1", make_details())
        store.submit(trade.trade_id, "User1")
        assert trade.state == TradeState.PENDING_APPROVAL

    def test_approve_moves_to_approved(self, store, submitted_trade):
        store.approve(submitted_trade.trade_id, "User2")
        assert submitted_trade.state == TradeState.APPROVED
        assert submitted_trade.approver_id == "User2"

    def test_history_contains_two_entries(self, store, approved_trade):
        history = store.get_history(approved_trade.trade_id)
        assert len(history) == 2
        assert history[0].action == TradeAction.SUBMIT
        assert history[0].state_before == TradeState.DRAFT
        assert history[0].state_after == TradeState.PENDING_APPROVAL
        assert history[0].user_id == "User1"
        assert history[1].action == TradeAction.APPROVE
        assert history[1].state_before == TradeState.PENDING_APPROVAL
        assert history[1].state_after == TradeState.APPROVED
        assert history[1].user_id == "User2"


# ---------------------------------------------------------------------------
# Scenario 2 – Update and Reapproval
# ---------------------------------------------------------------------------

class TestScenario2UpdateAndReapproval:
    def test_update_moves_to_needs_reapproval(self, store, submitted_trade):
        store.update(submitted_trade.trade_id, "User2", make_details(notional_amount=1_200_000))
        assert submitted_trade.state == TradeState.NEEDS_REAPPROVAL

    def test_requester_reapproves_updated_trade(self, store, submitted_trade):
        store.update(submitted_trade.trade_id, "User2", make_details(notional_amount=1_200_000))
        store.approve(submitted_trade.trade_id, "User1")
        assert submitted_trade.state == TradeState.APPROVED

    def test_current_details_reflect_update(self, store, submitted_trade):
        updated = make_details(notional_amount=1_200_000)
        store.update(submitted_trade.trade_id, "User2", updated)
        assert submitted_trade.current_details.notional_amount == 1_200_000


# ---------------------------------------------------------------------------
# Scenario 3 – Full Execution Flow
# ---------------------------------------------------------------------------

class TestScenario3Execution:
    def test_send_to_execute(self, store, approved_trade):
        store.send_to_execute(approved_trade.trade_id, "User2")
        assert approved_trade.state == TradeState.SENT_TO_COUNTERPARTY

    def test_book_moves_to_executed(self, store, approved_trade):
        store.send_to_execute(approved_trade.trade_id, "User2")
        store.book(approved_trade.trade_id, "User1", strike=1.0875)
        assert approved_trade.state == TradeState.EXECUTED
        assert approved_trade.current_details.strike == 1.0875

    def test_full_happy_path_history(self, store):
        trade = store.create_trade("User1", make_details())
        store.submit(trade.trade_id, "User1")
        store.approve(trade.trade_id, "User2")
        store.send_to_execute(trade.trade_id, "User2")
        store.book(trade.trade_id, "User1", strike=1.0875)

        history = store.get_history(trade.trade_id)
        actions = [h.action for h in history]
        assert actions == [
            TradeAction.SUBMIT,
            TradeAction.APPROVE,
            TradeAction.SEND_TO_EXECUTE,
            TradeAction.BOOK,
        ]
        assert trade.state == TradeState.EXECUTED


# ---------------------------------------------------------------------------
# Scenario 4 – History and Diff
# ---------------------------------------------------------------------------

class TestScenario4HistoryAndDiff:
    def test_diff_detects_notional_amount_change(self, store, submitted_trade):
        store.update(submitted_trade.trade_id, "User2", make_details(notional_amount=1_200_000))
        diff = store.diff(submitted_trade.trade_id, 1, 2)
        assert "notional_amount" in diff
        assert diff["notional_amount"] == (1_000_000.0, 1_200_000.0)

    def test_diff_is_empty_when_no_changes(self, store, approved_trade):
        diff = store.diff(approved_trade.trade_id, 1, 2)
        assert diff == {}

    def test_get_details_at_version_returns_snapshot(self, store, submitted_trade):
        store.update(submitted_trade.trade_id, "User2", make_details(notional_amount=1_500_000))
        v1 = store.get_details_at_version(submitted_trade.trade_id, 1)
        v2 = store.get_details_at_version(submitted_trade.trade_id, 2)
        assert v1.notional_amount == 1_000_000.0
        assert v2.notional_amount == 1_500_000.0

    def test_strike_recorded_in_book_snapshot(self, store, approved_trade):
        store.send_to_execute(approved_trade.trade_id, "User2")
        store.book(approved_trade.trade_id, "User1", strike=1.09)
        history = store.get_history(approved_trade.trade_id)
        book_entry = history[-1]
        assert book_entry.trade_details_snapshot.strike == 1.09

    def test_format_history_table_returns_string(self, store, approved_trade):
        table = format_history_table(store.get_trade(approved_trade.trade_id))
        assert "Submit" in table
        assert "Approve" in table
        assert "User1" in table
        assert "User2" in table


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_invalid_notional_currency(self, store):
        with pytest.raises(TradeValidationError, match="IBAN"):
            store.create_trade("User1", make_details(notional_currency="ZZZ"))

    def test_notional_currency_not_in_underlying(self, store):
        with pytest.raises(TradeValidationError, match="underlying"):
            store.create_trade("User1", make_details(notional_currency="EUR", underlying="GBPUSD"))

    def test_invalid_underlying_format(self, store):
        with pytest.raises(TradeValidationError, match="(?i)underlying"):
            store.create_trade("User1", make_details(underlying="INVALID_PAIR_XYZ"))

    def test_underlying_with_invalid_currencies(self, store):
        with pytest.raises(TradeValidationError):
            store.create_trade("User1", make_details(underlying="XXXYYY"))

    def test_trade_date_after_value_date(self, store):
        with pytest.raises(TradeValidationError, match="(?i)trade date"):
            store.create_trade("User1", make_details(
                trade_date=date(2025, 1, 15),
                value_date=date(2025, 1, 10),
            ))

    def test_value_date_after_delivery_date(self, store):
        with pytest.raises(TradeValidationError, match="(?i)value date"):
            store.create_trade("User1", make_details(
                value_date=date(2025, 1, 20),
                delivery_date=date(2025, 1, 15),
            ))

    def test_equal_dates_are_valid(self, store):
        trade = store.create_trade("User1", make_details(
            trade_date=date(2025, 1, 10),
            value_date=date(2025, 1, 10),
            delivery_date=date(2025, 1, 10),
        ))
        assert trade.state == TradeState.DRAFT

    def test_negative_notional_amount(self, store):
        with pytest.raises(TradeValidationError, match="positive"):
            store.create_trade("User1", make_details(notional_amount=-500_000))

    def test_zero_notional_amount(self, store):
        with pytest.raises(TradeValidationError, match="positive"):
            store.create_trade("User1", make_details(notional_amount=0))

    def test_empty_trading_entity(self, store):
        with pytest.raises(TradeValidationError, match="Trading entity"):
            store.create_trade("User1", make_details(trading_entity=""))

    def test_update_also_validates_details(self, store, submitted_trade):
        bad_details = make_details(notional_amount=-1)
        with pytest.raises(TradeValidationError):
            store.update(submitted_trade.trade_id, "User2", bad_details)

    def test_underlying_slash_separator_accepted(self, store):
        trade = store.create_trade("User1", make_details(underlying="EUR/USD"))
        assert trade.current_details.underlying == "EURUSD"

    def test_direction_string_accepted(self, store):
        trade = store.create_trade("User1", make_details(direction="Buy"))
        assert trade.current_details.direction == Direction.BUY


# ---------------------------------------------------------------------------
# State Transitions – invalid paths
# ---------------------------------------------------------------------------

class TestInvalidStateTransitions:
    def test_cannot_approve_from_draft(self, store):
        trade = store.create_trade("User1", make_details())
        with pytest.raises(InvalidStateTransitionError):
            store.approve(trade.trade_id, "User2")

    def test_cannot_submit_twice(self, store, submitted_trade):
        with pytest.raises(InvalidStateTransitionError):
            store.submit(submitted_trade.trade_id, "User1")

    def test_cannot_book_without_send_to_execute(self, store, approved_trade):
        with pytest.raises(InvalidStateTransitionError):
            store.book(approved_trade.trade_id, "User1", strike=1.05)

    def test_cannot_send_to_execute_from_pending(self, store, submitted_trade):
        with pytest.raises(InvalidStateTransitionError):
            store.send_to_execute(submitted_trade.trade_id, "User2")

    def test_cannot_update_from_approved(self, store, approved_trade):
        with pytest.raises(InvalidStateTransitionError):
            store.update(approved_trade.trade_id, "User2", make_details())

    def test_cannot_act_on_cancelled_trade(self, store, submitted_trade):
        store.cancel(submitted_trade.trade_id, "User1")
        assert submitted_trade.state == TradeState.CANCELLED
        with pytest.raises(InvalidStateTransitionError):
            store.approve(submitted_trade.trade_id, "User2")

    def test_cannot_act_on_executed_trade(self, store, approved_trade):
        store.send_to_execute(approved_trade.trade_id, "User2")
        store.book(approved_trade.trade_id, "User1", strike=1.0)
        with pytest.raises(InvalidStateTransitionError):
            store.cancel(approved_trade.trade_id, "User1")

    def test_cancel_from_needs_reapproval(self, store, submitted_trade):
        store.update(submitted_trade.trade_id, "User2", make_details())
        store.cancel(submitted_trade.trade_id, "User1")
        assert submitted_trade.state == TradeState.CANCELLED

    def test_cancel_from_approved(self, store, approved_trade):
        store.cancel(approved_trade.trade_id, "User2")
        assert approved_trade.state == TradeState.CANCELLED

    def test_cancel_from_sent_to_counterparty(self, store, approved_trade):
        store.send_to_execute(approved_trade.trade_id, "User2")
        store.cancel(approved_trade.trade_id, "User1")
        assert approved_trade.state == TradeState.CANCELLED


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------

class TestAuthorization:
    def test_non_requester_cannot_submit(self, store):
        trade = store.create_trade("User1", make_details())
        with pytest.raises(UnauthorizedActionError, match="requester"):
            store.submit(trade.trade_id, "User2")

    def test_requester_cannot_approve_own_trade(self, store, submitted_trade):
        with pytest.raises(UnauthorizedActionError, match="requester cannot approve"):
            store.approve(submitted_trade.trade_id, "User1")

    def test_requester_cannot_update_own_trade(self, store, submitted_trade):
        with pytest.raises(UnauthorizedActionError, match="requester cannot update"):
            store.update(submitted_trade.trade_id, "User1", make_details())

    def test_only_requester_can_reapprove_after_update(self, store, submitted_trade):
        store.update(submitted_trade.trade_id, "User2", make_details(notional_amount=1_200_000))
        with pytest.raises(UnauthorizedActionError, match="requester"):
            store.approve(submitted_trade.trade_id, "User3")

    def test_only_approver_can_send_to_execute(self, store, approved_trade):
        with pytest.raises(UnauthorizedActionError):
            store.send_to_execute(approved_trade.trade_id, "User3")

    def test_third_party_cannot_cancel_after_approver_set(self, store, approved_trade):
        with pytest.raises(UnauthorizedActionError):
            store.cancel(approved_trade.trade_id, "User3")

    def test_approver_can_cancel(self, store, approved_trade):
        store.cancel(approved_trade.trade_id, "User2")
        assert approved_trade.state == TradeState.CANCELLED

    def test_requester_can_cancel(self, store, submitted_trade):
        store.cancel(submitted_trade.trade_id, "User1")
        assert submitted_trade.state == TradeState.CANCELLED

    def test_approver_can_book(self, store, approved_trade):
        store.send_to_execute(approved_trade.trade_id, "User2")
        store.book(approved_trade.trade_id, "User2", strike=1.1)
        assert approved_trade.state == TradeState.EXECUTED


# ---------------------------------------------------------------------------
# Store utilities
# ---------------------------------------------------------------------------

class TestStoreUtilities:
    def test_get_trade_not_found(self, store):
        with pytest.raises(TradeNotFoundError):
            store.get_trade("nonexistent-id")

    def test_list_trades_no_filter(self, store):
        store.create_trade("User1", make_details())
        store.create_trade("User1", make_details())
        assert len(store.list_trades()) == 2

    def test_list_trades_filtered_by_state(self, store):
        t1 = store.create_trade("User1", make_details())
        t2 = store.create_trade("User1", make_details())
        store.submit(t1.trade_id, "User1")
        drafts = store.list_trades(state=TradeState.DRAFT)
        pending = store.list_trades(state=TradeState.PENDING_APPROVAL)
        assert len(drafts) == 1
        assert len(pending) == 1
        assert drafts[0].trade_id == t2.trade_id

    def test_version_out_of_range_raises(self, store, submitted_trade):
        with pytest.raises(ValueError, match="out of range"):
            store.get_details_at_version(submitted_trade.trade_id, 99)

    def test_history_snapshots_are_independent(self, store, submitted_trade):
        """Mutating current_details must not corrupt history snapshots."""
        v1_before = store.get_details_at_version(submitted_trade.trade_id, 1)
        store.update(
            submitted_trade.trade_id, "User2", make_details(notional_amount=9_999_999)
        )
        v1_after = store.get_details_at_version(submitted_trade.trade_id, 1)
        assert v1_before.notional_amount == v1_after.notional_amount == 1_000_000.0
