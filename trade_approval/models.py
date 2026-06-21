import copy
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum


# ISO 4217 currency codes (IBAN-eligible subset).
VALID_CURRENCIES: frozenset[str] = frozenset({
    "AED", "AFN", "ALL", "AMD", "ANG", "AOA", "ARS", "AUD", "AWG", "AZN",
    "BAM", "BBD", "BDT", "BGN", "BHD", "BIF", "BMD", "BND", "BOB", "BRL",
    "BSD", "BTN", "BWP", "BYN", "BZD", "CAD", "CDF", "CHF", "CLP", "CNY",
    "COP", "CRC", "CUP", "CVE", "CZK", "DJF", "DKK", "DOP", "DZD", "EGP",
    "ERN", "ETB", "EUR", "FJD", "FKP", "GBP", "GEL", "GHS", "GIP", "GMD",
    "GNF", "GTQ", "GYD", "HKD", "HNL", "HRK", "HTG", "HUF", "IDR", "ILS",
    "INR", "IQD", "IRR", "ISK", "JMD", "JOD", "JPY", "KES", "KGS", "KHR",
    "KMF", "KPW", "KRW", "KWD", "KYD", "KZT", "LAK", "LBP", "LKR", "LRD",
    "LSL", "LYD", "MAD", "MDL", "MGA", "MKD", "MMK", "MNT", "MOP", "MRO",
    "MUR", "MVR", "MWK", "MXN", "MYR", "MZN", "NAD", "NGN", "NIO", "NOK",
    "NPR", "NZD", "OMR", "PAB", "PEN", "PGK", "PHP", "PKR", "PLN", "PYG",
    "QAR", "RON", "RSD", "RUB", "RWF", "SAR", "SBD", "SCR", "SDG", "SEK",
    "SGD", "SHP", "SLL", "SOS", "SRD", "STN", "SVC", "SYP", "SZL", "THB",
    "TJS", "TMT", "TND", "TOP", "TRY", "TTD", "TWD", "TZS", "UAH", "UGX",
    "USD", "UYU", "UZS", "VES", "VND", "VUV", "WST", "XAF", "XCD", "XOF",
    "XPF", "YER", "ZAR", "ZMW", "ZWL",
})


class TradeState(str, Enum):
    DRAFT = "Draft"
    PENDING_APPROVAL = "PendingApproval"
    NEEDS_REAPPROVAL = "NeedsReapproval"
    APPROVED = "Approved"
    SENT_TO_COUNTERPARTY = "SentToCounterparty"
    EXECUTED = "Executed"
    CANCELLED = "Cancelled"


class TradeAction(str, Enum):
    SUBMIT = "Submit"
    APPROVE = "Approve"
    CANCEL = "Cancel"
    UPDATE = "Update"
    SEND_TO_EXECUTE = "SendToExecute"
    BOOK = "Book"


class Direction(str, Enum):
    BUY = "Buy"
    SELL = "Sell"


@dataclass
class TradeDetails:
    """All fields that describe a single trade.

    ``underlying`` may be provided as ``"EURUSD"`` or ``"EUR/USD"``; separators
    are stripped and the value is normalised to uppercase on construction.
    ``strike`` is ``None`` until the trade is executed (Book action).
    """

    trading_entity: str
    counterparty: str
    direction: Direction
    notional_currency: str
    notional_amount: float
    underlying: str
    trade_date: date
    value_date: date
    delivery_date: date
    style: str = "Forward"
    strike: float | None = None

    def __post_init__(self) -> None:
        if isinstance(self.direction, str):
            self.direction = Direction(self.direction)
        self.notional_currency = self.notional_currency.upper()
        self.underlying = (
            self.underlying.upper().replace("/", "").replace("-", "")
        )

    def copy(self) -> "TradeDetails":
        return copy.deepcopy(self)

    def to_dict(self) -> dict:
        return {
            "trading_entity": self.trading_entity,
            "counterparty": self.counterparty,
            "direction": self.direction.value,
            "style": self.style,
            "notional_currency": self.notional_currency,
            "notional_amount": self.notional_amount,
            "underlying": self.underlying,
            "trade_date": str(self.trade_date),
            "value_date": str(self.value_date),
            "delivery_date": str(self.delivery_date),
            "strike": self.strike,
        }


@dataclass
class HistoryEntry:
    """Immutable record of a single action taken on a trade."""

    step: int
    action: TradeAction
    user_id: str
    state_before: TradeState
    state_after: TradeState
    timestamp: datetime
    trade_details_snapshot: TradeDetails
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "step": self.step,
            "action": self.action.value,
            "user_id": self.user_id,
            "state_before": self.state_before.value,
            "state_after": self.state_after.value,
            "timestamp": self.timestamp.isoformat(),
            "notes": self.notes,
        }
