class TradeWorkflowError(Exception):
    """Base exception for all trade workflow errors."""


class InvalidStateTransitionError(TradeWorkflowError):
    """Raised when an action is not permitted in the current state."""


class UnauthorizedActionError(TradeWorkflowError):
    """Raised when a user is not authorized to perform an action."""


class TradeNotFoundError(TradeWorkflowError):
    """Raised when a trade cannot be found by its ID."""
