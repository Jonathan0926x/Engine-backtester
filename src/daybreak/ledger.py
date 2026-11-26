"""Long-only portfolio ledger with explicit fees and adverse slippage."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    PENDING = "pending"
    FILLED = "filled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class Order:
    """Auditable market order; quantity uses fractional shares."""

    order_id: int
    symbol: str
    side: Side
    quantity: float
    submitted_date: date
    status: OrderStatus = OrderStatus.PENDING
    fill_date: date | None = None
    fill_price: float | None = None
    commission: float = 0.0
    slippage: float = 0.0
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class Position:
    quantity: float
    average_cost: float


@dataclass(slots=True)
class Ledger:
    """Cash and positions; average cost is volume-weighted and fees are cash expenses."""

    starting_cash: float
    commission_per_order: float = 0.0
    slippage_bps: float = 0.0
    cash: float = field(init=False)
    positions: dict[str, Position] = field(default_factory=dict)
    orders: list[Order] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not math.isfinite(self.starting_cash) or self.starting_cash <= 0:
            raise ValueError("starting_cash must be finite and positive")
        if not math.isfinite(self.commission_per_order) or not math.isfinite(self.slippage_bps):
            raise ValueError("commission and slippage must be finite")
        if self.commission_per_order < 0 or self.slippage_bps < 0:
            raise ValueError("commission and slippage must be nonnegative")
        self.cash = float(self.starting_cash)

    def submit(self, symbol: str, side: Side, quantity: float, submitted_date: date) -> Order:
        """Record an order, rejecting zero/negative quantities immediately."""
        order = Order(len(self.orders) + 1, symbol, side, float(quantity), submitted_date)
        if not math.isfinite(float(quantity)) or quantity <= 0:
            order.status = OrderStatus.REJECTED
            order.reason = "quantity must be finite and positive"
        self.orders.append(order)
        return order

    def fill(self, order: Order, session: date, open_price: float) -> None:
        """Fill at the open with adverse slippage, or record a rejection reason."""
        if order.status != OrderStatus.PENDING:
            raise ValueError("only pending orders can be filled")
        if open_price <= 0:
            self.reject(order, "fill price must be positive")
            return
        rate = self.slippage_bps / 10_000
        price = open_price * (1 + rate if order.side == Side.BUY else 1 - rate)
        if price <= 0:
            self.reject(order, "slippage-adjusted fill price must be positive")
            return
        existing = self.positions.get(order.symbol, Position(0.0, 0.0))
        if order.side == Side.BUY:
            total_cost = price * order.quantity + self.commission_per_order
            if total_cost > self.cash + 1e-9:
                self.reject(
                    order, f"insufficient cash: need {total_cost:.8f}, have {self.cash:.8f}"
                )
                return
            new_quantity = existing.quantity + order.quantity
            average_cost = (
                existing.quantity * existing.average_cost + price * order.quantity
            ) / new_quantity
            self.cash -= total_cost
            self.positions[order.symbol] = Position(new_quantity, average_cost)
        else:
            if order.quantity > existing.quantity + 1e-9:
                self.reject(
                    order,
                    f"insufficient position: need {order.quantity:.8f}, have {existing.quantity:.8f}",
                )
                return
            proceeds = price * order.quantity - self.commission_per_order
            if proceeds < 0:
                self.reject(order, "commission exceeds sale proceeds")
                return
            remaining = max(0.0, existing.quantity - order.quantity)
            self.cash += proceeds
            if remaining == 0:
                self.positions.pop(order.symbol, None)
            else:
                self.positions[order.symbol] = Position(remaining, existing.average_cost)
        order.status = OrderStatus.FILLED
        order.fill_date = session
        order.fill_price = price
        order.commission = self.commission_per_order
        order.slippage = abs(price - open_price) * order.quantity

    @staticmethod
    def reject(order: Order, reason: str) -> None:
        order.status = OrderStatus.REJECTED
        order.reason = reason

    def equity(self, marks: dict[str, float]) -> float:
        """Value positions at provided closing marks; missing marks are errors."""
        value = self.cash
        for symbol, position in self.positions.items():
            if symbol not in marks:
                raise ValueError(f"missing closing mark for held symbol {symbol}")
            value += position.quantity * marks[symbol]
        return value
