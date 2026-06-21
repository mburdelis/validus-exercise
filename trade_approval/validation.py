from .exceptions import TradeValidationError
from .models import TradeDetails, VALID_CURRENCIES


def _parse_underlying(underlying: str) -> tuple[str, str] | None:
    """Return the two 3-char currency codes from a 6-char underlying string."""
    u = underlying.upper().replace("/", "").replace("-", "")
    if len(u) == 6:
        return u[:3], u[3:]
    return None


def validate_trade_details(details: TradeDetails) -> None:
    """Raise ``TradeValidationError`` if any field in *details* is invalid."""
    errors: list[str] = []

    if not details.trading_entity or not details.trading_entity.strip():
        errors.append("Trading entity is required.")

    if not details.counterparty or not details.counterparty.strip():
        errors.append("Counterparty is required.")

    # Notional currency
    ccy = details.notional_currency
    if ccy not in VALID_CURRENCIES:
        errors.append(
            f"Notional currency '{ccy}' is not a valid IBAN currency code."
        )

    # Notional amount
    if details.notional_amount is None or details.notional_amount <= 0:
        errors.append("Notional amount must be a positive number.")

    # Underlying – must be two valid currencies and include the notional currency.
    parsed = _parse_underlying(details.underlying)
    if parsed is None:
        errors.append(
            f"Underlying '{details.underlying}' must be two concatenated currency "
            "codes (e.g. 'EURUSD' or 'EUR/USD')."
        )
    else:
        ccy1, ccy2 = parsed
        if ccy1 not in VALID_CURRENCIES:
            errors.append(
                f"First currency in underlying '{ccy1}' is not a valid IBAN code."
            )
        if ccy2 not in VALID_CURRENCIES:
            errors.append(
                f"Second currency in underlying '{ccy2}' is not a valid IBAN code."
            )
        if ccy not in (ccy1, ccy2):
            errors.append(
                f"Notional currency '{ccy}' must be one of the two currencies "
                f"in the underlying '{details.underlying}'."
            )

    # Date ordering: Trade Date ≤ Value Date ≤ Delivery Date
    td, vd, dd = details.trade_date, details.value_date, details.delivery_date
    if not td:
        errors.append("Trade date is required.")
    if not vd:
        errors.append("Value date is required.")
    if not dd:
        errors.append("Delivery date is required.")

    if td and vd and td > vd:
        errors.append(
            f"Trade date ({td}) must be ≤ value date ({vd})."
        )
    if vd and dd and vd > dd:
        errors.append(
            f"Value date ({vd}) must be ≤ delivery date ({dd})."
        )

    if errors:
        raise TradeValidationError("\n".join(errors))
