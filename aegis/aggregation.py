"""Harmless synthetic measurement aggregation; not a design calculation."""

from collections.abc import Callable
from dataclasses import dataclass

MAX_ITEMS = 100
MAX_VALUE = 1_000_000
Candidate = Callable[[tuple[int, ...]], dict[str, int]]


@dataclass(frozen=True)
class Fixture:
    identity: str
    micrometres: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.identity or not 1 <= len(self.micrometres) <= MAX_ITEMS:
            raise ValueError("invalid fixture size or identity")
        if any(type(x) is not int or not 0 <= x <= MAX_VALUE
               for x in self.micrometres):
            raise ValueError("invalid synthetic measurement")


def premature_rounding(values: tuple[int, ...]) -> dict[str, int]:
    """Intentionally defective baseline: rounds before summing."""
    return {"total_mm": sum((x + 500) // 1000 for x in values)}


def aggregate_first(values: tuple[int, ...]) -> dict[str, int]:
    """Sum exact integer measurements; round only the final value."""
    return {"total_mm": (sum(values) + 500) // 1000}
