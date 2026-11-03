"""Hard cap and dollar estimate for Grok vision calls. Stdlib only; no API."""

from __future__ import annotations

import os

# One vision call unless GROK_MAX_CALLS sets a different integer cap.
MAX_CALLS = int(os.environ.get("GROK_MAX_CALLS", "1"))

# Low-detail image price used for the offline demo estimate.
DEFAULT_USD_PER_CALL = 0.002694


class BudgetExceeded(Exception):
    """consume() was asked for more calls than the cap allows."""


class CallBudget:
    """Counts calls against MAX_CALLS, or against an explicit cap."""

    def __init__(self, cap: int | None = None) -> None:
        self.cap = MAX_CALLS if cap is None else cap
        self.used = 0

    def remaining(self) -> int:
        return self.cap - self.used

    def consume(self, n: int = 1) -> None:
        """Take n calls. Raises BudgetExceeded once the cap is spent."""
        if n < 0:
            raise ValueError("n must be >= 0")
        if self.used + n > self.cap:
            raise BudgetExceeded(
                f"call budget is {self.cap}; {self.used} used, refusing {n}"
            )
        self.used += n


def estimated_usd(calls: int, usd_per_call: float = DEFAULT_USD_PER_CALL) -> float:
    """Return the dollar estimate for `calls` at `usd_per_call`."""
    return float(calls) * float(usd_per_call)


def main() -> None:
    # 8 cameras, one frame every 30s: 120 frames each in an hour.
    scenarios = (
        ("1 call", 1),
        ("8 calls", 8),
        ("8 calls * 120", 8 * 120),
    )
    for label, calls in scenarios:
        print(f"{label}: {estimated_usd(calls)}")


if __name__ == "__main__":
    main()
