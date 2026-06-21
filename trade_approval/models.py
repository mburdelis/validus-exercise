from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


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


class TradeDetails(BaseModel):
    """Validated, immutable value object describing a single trade.

    All validation rules are enforced at construction time by Pydantic:
    - trading_entity and counterparty must be non-empty.
    - notional_currency must be a valid ISO 4217 / IBAN code.
    - notional_amount must be positive.
    - underlying must be two valid ISO 4217 codes (e.g. 'EURUSD' or 'EUR/USD').
    - notional_currency must be one of the two currencies in underlying.
    - trade_date ≤ value_date ≤ delivery_date.
    - strike is None until the trade is executed (Book action).
    """

    model_config = ConfigDict(frozen=True)

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

    @field_validator("trading_entity")
    @classmethod
    def trading_entity_required(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Trading entity is required and must not be blank.")
        return v

    @field_validator("counterparty")
    @classmethod
    def counterparty_required(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Counterparty is required and must not be blank.")
        return v

    @field_validator("notional_currency", mode="before")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        normalised = v.upper()
        if normalised not in VALID_CURRENCIES:
            raise ValueError(f"'{v}' is not a valid IBAN currency code.")
        return normalised

    @field_validator("underlying", mode="before")
    @classmethod
    def normalise_underlying(cls, v: str) -> str:
        return v.upper().replace("/", "").replace("-", "")

    @field_validator("notional_amount")
    @classmethod
    def must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("notional_amount must be a positive number.")
        return v

    @model_validator(mode="after")
    def validate_underlying_and_dates(self) -> "TradeDetails":
        u = self.underlying
        if len(u) != 6:
            raise ValueError(
                f"Underlying '{u}' must be two concatenated currency codes "
                "(e.g. 'EURUSD' or 'EUR/USD')."
            )
        ccy1, ccy2 = u[:3], u[3:]
        if ccy1 not in VALID_CURRENCIES:
            raise ValueError(f"First currency in underlying '{ccy1}' is not a valid IBAN code.")
        if ccy2 not in VALID_CURRENCIES:
            raise ValueError(f"Second currency in underlying '{ccy2}' is not a valid IBAN code.")
        if self.notional_currency not in (ccy1, ccy2):
            raise ValueError(
                f"Notional currency '{self.notional_currency}' must be one of the "
                f"currencies in the underlying '{self.underlying}'."
            )
        if self.trade_date > self.value_date:
            raise ValueError(
                f"Trade date ({self.trade_date}) must be ≤ value date ({self.value_date})."
            )
        if self.value_date > self.delivery_date:
            raise ValueError(
                f"Value date ({self.value_date}) must be ≤ delivery date ({self.delivery_date})."
            )
        return self


class HistoryEntry(BaseModel):
    """Immutable record of a single action taken on a trade."""

    model_config = ConfigDict(frozen=True)

    step: int
    action: TradeAction
    user_id: str
    state_before: TradeState
    state_after: TradeState
    timestamp: datetime
    trade_details_snapshot: TradeDetails
    notes: str = ""
