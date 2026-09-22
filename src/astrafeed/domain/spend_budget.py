"""Personal provider spend limits, distinct from report-stage progress."""


class BudgetExceeded(Exception):
    """A paid request would exceed the user's remaining daily allowance."""
