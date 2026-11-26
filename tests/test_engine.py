import math
from datetime import date

from daybreak.data import Bar
from daybreak.engine import run_backtest
from daybreak.ledger import Ledger, OrderStatus, Side
from daybreak.metrics import calculate_metrics
from daybreak.strategy import BuyAndHold, MovingAverageCross


def bar(day: int, open_: float, close: float, symbol: str = "X") -> Bar:
    return Bar(
        symbol, date(2024, 1, day), open_, max(open_, close) + 1, min(open_, close) - 1, close, 100
    )


def test_ledger_buy_sell_costs_and_position_cost_basis() -> None:
    ledger = Ledger(100, commission_per_order=1, slippage_bps=100)
    buy = ledger.submit("X", Side.BUY, 2, date(2024, 1, 1))
    ledger.fill(buy, date(2024, 1, 2), 10)
    assert buy.status == OrderStatus.FILLED
    assert buy.fill_price == 10.1
    assert ledger.cash == 78.8
    assert ledger.positions["X"].average_cost == 10.1
    assert ledger.equity({"X": 11}) == 100.8

    sale = ledger.submit("X", Side.SELL, 1, date(2024, 1, 2))
    ledger.fill(sale, date(2024, 1, 3), 12)
    assert math.isclose(sale.fill_price, 11.88)
    assert math.isclose(ledger.cash, 89.68)
    assert ledger.positions["X"].quantity == 1
    assert ledger.positions["X"].average_cost == 10.1
    assert math.isclose(ledger.equity({"X": 12}), 101.68)


def test_ledger_rejects_unaffordable_and_short_orders() -> None:
    ledger = Ledger(10)
    order = ledger.submit("X", Side.BUY, 2, date(2024, 1, 1))
    ledger.fill(order, date(2024, 1, 2), 6)
    assert order.status == OrderStatus.REJECTED
    assert "insufficient cash" in order.reason
    sale = ledger.submit("X", Side.SELL, 1, date(2024, 1, 2))
    ledger.fill(sale, date(2024, 1, 3), 6)
    assert sale.status == OrderStatus.REJECTED
    assert "insufficient position" in sale.reason


def test_signal_at_close_fills_only_at_next_available_open() -> None:
    bars = [bar(2, 10, 10), bar(3, 12, 13), bar(4, 14, 14)]
    result = run_backtest(bars, BuyAndHold("X", 2), starting_cash=100)
    order = result.orders[0]
    assert order.submitted_date == date(2024, 1, 2)
    assert order.fill_date == date(2024, 1, 3)
    assert order.fill_price == 12
    assert result.daily[0].positions == {}
    assert result.daily[1].positions == {"X": 2}


def test_end_of_data_order_is_cancelled_and_mark_carries_forward() -> None:
    class LastDayBuy:
        name = "last-day-buy"

        @property
        def parameters(self):
            return {}

        def targets(self, history, positions):
            return (
                [type("Target", (), {"symbol": "X", "quantity": 1})()] if len(history) == 1 else []
            )

    data = [bar(2, 10, 10), Bar("Y", date(2024, 1, 3), 2, 3, 1, 2, 10)]
    result = run_backtest(data, LastDayBuy(), 100)
    assert result.orders[0].status == OrderStatus.CANCELLED
    assert result.daily[-1].equity == 100


def test_moving_average_uses_only_available_history() -> None:
    strategy = MovingAverageCross("X", 2, 3, 1)
    assert strategy.targets((bar(2, 1, 1), bar(3, 1, 2)), {}) == []
    target = strategy.targets((bar(2, 1, 1), bar(3, 1, 2), bar(4, 1, 3)), {})[0]
    assert target.quantity == 1


def test_metrics_known_curve_and_short_history_edges() -> None:
    result = run_backtest([bar(2, 10, 10), bar(3, 10, 11)], BuyAndHold("X", 0.5), 100)
    metrics = calculate_metrics(result, 100)
    assert metrics["ending_equity"] == 100.5
    assert math.isclose(metrics["total_return"], 0.005)
    assert metrics["annualized_volatility"] is None
    assert metrics["filled_orders"] == 1
