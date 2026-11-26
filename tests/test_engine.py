import math
from datetime import date

from daybreak.data import Bar
from daybreak.engine import run_backtest
from daybreak.ledger import Ledger, OrderStatus, Side
from daybreak.metrics import calculate_metrics
from daybreak.strategy import BuyAndHold, MovingAverageCross, TargetPosition


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


class PersistentTarget:
    """Always request one share of X, including on dates with no X bar."""

    name = "persistent-target"
    parameters = {}

    def targets(self, history, positions):
        return [TargetPosition("X", 1)]


def test_pending_order_is_not_duplicated_while_symbol_has_no_bar() -> None:
    data = [
        bar(2, 10, 10, "X"),
        bar(3, 20, 20, "Y"),
        bar(4, 21, 21, "Y"),
        bar(5, 12, 12, "X"),
    ]

    result = run_backtest(data, PersistentTarget(), starting_cash=100)

    assert len(result.orders) == 1
    assert result.orders[0].status == OrderStatus.FILLED
    assert result.orders[0].submitted_date == date(2024, 1, 2)
    assert result.orders[0].fill_date == date(2024, 1, 5)
    assert result.daily[-1].positions == {"X": 1}


def test_pending_target_is_reconsidered_after_fill() -> None:
    class IncreaseAfterFill:
        name = "increase-after-fill"
        parameters = {}

        def targets(self, history, positions):
            return [TargetPosition("X", 1 if not positions.get("X") else 2)]

    result = run_backtest(
        [bar(2, 10, 10), bar(3, 10, 10), bar(4, 11, 11)],
        IncreaseAfterFill(),
        starting_cash=100,
    )

    assert len(result.orders) == 2
    assert [order.fill_date for order in result.orders] == [date(2024, 1, 3), date(2024, 1, 4)]
    assert result.daily[-1].positions == {"X": 2}


def test_commission_and_slippage_are_charged_on_each_fill() -> None:
    ledger = Ledger(100, commission_per_order=2, slippage_bps=50)
    buy = ledger.submit("X", Side.BUY, 2, date(2024, 1, 1))
    ledger.fill(buy, date(2024, 1, 2), 10)

    assert math.isclose(buy.fill_price, 10.05)
    assert buy.commission == 2
    assert math.isclose(buy.slippage, 0.10)
    assert math.isclose(ledger.cash, 77.90)
    assert math.isclose(ledger.equity({"X": 10}), 97.90)


def test_rejected_buy_does_not_change_cash_or_positions() -> None:
    ledger = Ledger(10, commission_per_order=1)
    order = ledger.submit("X", Side.BUY, 1, date(2024, 1, 1))
    ledger.fill(order, date(2024, 1, 2), 10)

    assert order.status == OrderStatus.REJECTED
    assert ledger.cash == 10
    assert ledger.positions == {}
