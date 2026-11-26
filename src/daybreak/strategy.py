"""Small strategy API and deterministic example strategies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from daybreak.data import Bar


@dataclass(frozen=True, slots=True)
class TargetPosition:
    symbol: str
    quantity: float


class Strategy(Protocol):
    """Strategies receive immutable history only through the current completed bar."""

    name: str
    parameters: dict[str, object]

    def targets(
        self, history: tuple[Bar, ...], positions: dict[str, float]
    ) -> list[TargetPosition]:
        """Return desired share quantities based on available history."""
        ...


@dataclass(frozen=True, slots=True)
class BuyAndHold:
    """Hold a configured fractional-share quantity from the first observed bar."""

    symbol: str
    quantity: float
    name: str = "buy-and-hold"

    @property
    def parameters(self) -> dict[str, object]:
        return {"symbol": self.symbol, "quantity": self.quantity}

    def targets(
        self, history: tuple[Bar, ...], positions: dict[str, float]
    ) -> list[TargetPosition]:
        if not history or history[-1].symbol != self.symbol:
            return []
        return [TargetPosition(self.symbol, self.quantity)]


@dataclass(frozen=True, slots=True)
class MovingAverageCross:
    """Long/flat close-price crossover; signals use completed daily closes only."""

    symbol: str
    short_window: int = 2
    long_window: int = 3
    quantity: float = 1.0
    name: str = "moving-average-crossover"

    def __post_init__(self) -> None:
        if self.short_window < 1 or self.long_window <= self.short_window:
            raise ValueError("windows must satisfy 1 <= short_window < long_window")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")

    @property
    def parameters(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "short_window": self.short_window,
            "long_window": self.long_window,
            "quantity": self.quantity,
        }

    def targets(
        self, history: tuple[Bar, ...], positions: dict[str, float]
    ) -> list[TargetPosition]:
        relevant = [bar.close for bar in history if bar.symbol == self.symbol]
        if len(relevant) < self.long_window:
            return []
        short_mean = sum(relevant[-self.short_window :]) / self.short_window
        long_mean = sum(relevant[-self.long_window :]) / self.long_window
        return [TargetPosition(self.symbol, self.quantity if short_mean > long_mean else 0.0)]
