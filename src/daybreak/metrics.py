"""Performance metrics derived exclusively from daily equity records."""

from __future__ import annotations

import math

from daybreak.engine import BacktestResult

TRADING_SESSIONS_PER_YEAR = 252


def calculate_metrics(result: BacktestResult, starting_cash: float) -> dict[str, object]:
    """Compute transparent daily-equity metrics and return null where unavailable."""
    equity = [record.equity for record in result.daily]
    if not equity or starting_cash <= 0:
        raise ValueError("metrics require daily records and positive starting cash")
    ending = equity[-1]
    total_return = ending / starting_cash - 1
    returns = [equity[i] / equity[i - 1] - 1 for i in range(1, len(equity))]
    annualized_return = None
    annualized_volatility = None
    if len(equity) > 1 and ending > 0:
        annualized_return = (ending / starting_cash) ** (
            TRADING_SESSIONS_PER_YEAR / (len(equity) - 1)
        ) - 1
    if len(returns) > 1:
        mean = sum(returns) / len(returns)
        sample_variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
        annualized_volatility = math.sqrt(sample_variance * TRADING_SESSIONS_PER_YEAR)

    peak = starting_cash
    max_drawdown = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak > 0:
            max_drawdown = min(max_drawdown, value / peak - 1)
    filled = [order for order in result.orders if order.status.value == "filled"]
    rejected = [order for order in result.orders if order.status.value == "rejected"]
    canceled = [order for order in result.orders if order.status.value == "cancelled"]
    traded_notional = sum((order.fill_price or 0) * order.quantity for order in filled)
    average_equity = sum([starting_cash, *equity]) / (len(equity) + 1)
    benchmark_values = [r.benchmark_equity for r in result.daily if r.benchmark_equity is not None]
    benchmark_return = (
        benchmark_values[-1] / benchmark_values[0] - 1 if len(benchmark_values) > 1 else None
    )
    exposure_days = sum(bool(record.positions) for record in result.daily)
    return {
        "starting_equity": starting_cash,
        "ending_equity": ending,
        "total_return": total_return,
        "annualized_return": annualized_return,
        "annualized_volatility": annualized_volatility,
        "max_drawdown": max_drawdown,
        "filled_orders": len(filled),
        "rejected_orders": len(rejected),
        "cancelled_orders": len(canceled),
        "total_commissions": sum(order.commission for order in filled),
        "estimated_slippage": sum(order.slippage for order in filled),
        "turnover": traded_notional / average_equity if average_equity else None,
        "time_in_market": exposure_days / len(result.daily),
        "benchmark_total_return": benchmark_return,
        "annualization_sessions_per_year": TRADING_SESSIONS_PER_YEAR,
        "turnover_definition": "sum(abs(fill price * filled quantity)) / average daily equity including starting equity",
        "benchmark_definition": "price-only buy-and-hold return for the first symbol; no dividends or costs",
    }
