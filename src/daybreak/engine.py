"""Deterministic daily event loop with next-available-session open fills."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from types import MappingProxyType

from daybreak.data import Bar
from daybreak.ledger import Ledger, OrderStatus, Side
from daybreak.strategy import Strategy


@dataclass(frozen=True, slots=True)
class DailyRecord:
    date: date
    cash: float
    positions: dict[str, float]
    equity: float
    benchmark_equity: float | None


@dataclass(frozen=True, slots=True)
class BacktestResult:
    daily: list[DailyRecord]
    orders: list
    ledger: Ledger
    strategy_name: str
    strategy_parameters: dict[str, object]


def run_backtest(
    bars: list[Bar],
    strategy: Strategy,
    starting_cash: float = 10_000.0,
    commission_per_order: float = 0.0,
    slippage_bps: float = 0.0,
    start: date | None = None,
    end: date | None = None,
) -> BacktestResult:
    """Replay bars; fill old orders, reveal today's bar, signal, then mark to close."""
    if start is not None and end is not None and start > end:
        raise ValueError("start date must be on or before end date")
    selected = [
        bar
        for bar in bars
        if (start is None or bar.date >= start) and (end is None or bar.date <= end)
    ]
    if not selected:
        raise ValueError("no market bars fall within the requested date range")
    selected.sort(key=lambda bar: (bar.date, bar.symbol))
    ledger = Ledger(starting_cash, commission_per_order, slippage_bps)
    by_date: dict[date, list[Bar]] = {}
    history: list[Bar] = []
    for bar in selected:
        by_date.setdefault(bar.date, []).append(bar)
    pending: dict[str, list] = {}
    daily: list[DailyRecord] = []
    benchmark_symbol = selected[0].symbol
    benchmark_first_close: float | None = None
    last_marks: dict[str, float] = {}

    for session, session_bars in sorted(by_date.items()):
        current = {bar.symbol: bar for bar in session_bars}
        # Pending orders wait for the next available bar for that symbol.
        for symbol in sorted(current):
            eligible = pending.pop(symbol, [])
            for order in eligible:
                ledger.fill(order, session, current[symbol].open)

        history.extend(session_bars)
        history_view = tuple(history)
        holdings = MappingProxyType(
            {key: value.quantity for key, value in ledger.positions.items()}
        )
        targets = strategy.targets(history_view, holdings)
        for target in targets:
            # Keep one outstanding order per symbol. Recomputing the same target on
            # dates without a bar must not queue duplicate orders for a future open.
            if pending.get(target.symbol):
                continue
            current_quantity = ledger.positions.get(target.symbol)
            held = current_quantity.quantity if current_quantity else 0.0
            delta = target.quantity - held
            if abs(delta) <= 1e-12:
                continue
            side = Side.BUY if delta > 0 else Side.SELL
            order = ledger.submit(target.symbol, side, abs(delta), session)
            if target.quantity < 0 and order.status == OrderStatus.PENDING:
                ledger.reject(order, "negative target positions are not allowed")
            elif order.status == OrderStatus.PENDING:
                pending.setdefault(target.symbol, []).append(order)

        last_marks.update({bar.symbol: bar.close for bar in session_bars})
        # A held symbol without a bar today retains its last available close mark.
        equity = ledger.equity(last_marks)
        if benchmark_first_close is None and benchmark_symbol in current:
            benchmark_first_close = current[benchmark_symbol].close
        benchmark = None
        if benchmark_first_close is not None and benchmark_symbol in current:
            benchmark = starting_cash * current[benchmark_symbol].close / benchmark_first_close
        daily.append(
            DailyRecord(
                date=session,
                cash=ledger.cash,
                positions={key: value.quantity for key, value in sorted(ledger.positions.items())},
                equity=equity,
                benchmark_equity=benchmark,
            )
        )

    for orders in pending.values():
        for order in orders:
            order.status = OrderStatus.CANCELLED
            order.reason = "no later bar for symbol before end of data"
    return BacktestResult(
        daily=daily,
        orders=ledger.orders,
        ledger=ledger,
        strategy_name=strategy.name,
        strategy_parameters=strategy.parameters,
    )
