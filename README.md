# Daybreak Backtest

Daybreak is a small, documented Python simulator for replaying local daily stock-bar CSVs under explicit timing and accounting rules. It demonstrates simulation engineering, not investment advice. A profitable historical simulation does not establish a live trading edge.

## Features and non-goals

- Python 3.11+, a `src/` package, standard-library CSV/JSON, and no runtime dependencies.
- Strict CSV validation, a long-only USD ledger, fractional shares, market orders, fixed per-order commissions, adverse basis-point slippage, close-based signals, next-available-session open fills, and daily close marks.
- Buy-and-hold and simple moving-average-crossover examples. Neither is a recommendation and parameters are illustrative, not optimized.
- Deterministic simulation outputs for identical inputs. Run timestamp and output folder are intentionally variable metadata.
- Out of scope: shorting, leverage, intraday simulation, limit/stop orders, partial fills, broker connectivity, options, machine learning, multiple currencies, taxes, splits, and dividends.

## Install and test

Python 3.11 or later is required. The package has no runtime dependencies; pytest and Ruff are optional development dependencies.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
pytest
ruff check src tests
ruff format --check src tests
```

## Quick start

From the project root, run the included clearly labeled synthetic example:

```bash
daybreak examples/config.json
```

Or without installing the console script:

```bash
python -m daybreak.cli examples/config.json
```

Each run creates a new timestamp-and-data-hash folder under `results/` (the CLI fails rather than overwrite an existing folder). It writes `equity_curve.csv`, `orders.csv`, `metrics.json`, and `run_config.json`. The example data has six hand-authored rows for a fictional `DEMO` instrument. It is not historical market data or a representative universe.

## Data format and corporate actions

Required lowercase CSV columns are `symbol,date,open,high,low,close,volume`; optional `adj_close` may be blank. Dates must be `YYYY-MM-DD`, ordered chronologically for each symbol, with no duplicate symbol/date. Prices must be finite and positive; low must not exceed open or close, and high must not be below them. Volume must be finite and nonnegative. Errors name the file, row, and field when possible. The loader does not silently repair data.

The engine executes and marks **raw OHLC** only. It does not process splits or dividends. Optional `adj_close` is retained on loaded bars as descriptive data but is not used for execution, marking, or benchmark. Avoid mixing raw and adjusted values. For real research, source a properly licensed, point-in-time dataset and explicitly reconcile corporate actions and delisted securities. This example does not establish data-source quality or universe completeness.

## Strategy, timing, and fills

A strategy gets an immutable tuple of bars up to and including the completed current session and a read-only snapshot of current quantities. It returns target share quantities. Signals are considered after the close; any resulting market order can fill only at that symbol's **next available bar open**, never the close that generated the signal. Orders stay pending through dates with no bar for their symbol. Orders still pending at end of data are recorded as cancelled.

At each daily session the engine fills eligible earlier orders at the open, exposes the completed bar to the strategy, submits new orders, then marks portfolio equity at the close. A held instrument with no bar today retains its last available close mark. Strategies should avoid repeated pending target orders if extended to asynchronous instruments; this starter engine is designed for ordinary daily bars.

Buy price is `open * (1 + slippage_bps / 10,000)`; sell price is `open * (1 - slippage_bps / 10,000)`. Fixed commission is charged per filled order. The order record retains the submitted date, fill date/price, fee, estimated slippage, and rejection/cancellation reason.

## Accounting conventions

All amounts are USD; fractional shares are allowed. A buy subtracts fill notional plus commission; a sale adds notional less commission. Average cost is quantity-weighted fill price and is preserved after partial sales; fees are separately recorded as cash costs. Cash may not become negative, positions may not go short, and rejected orders remain auditable. Held positions are marked at the latest available close.

## Metrics

Metrics are computed from daily marked equity. Annualized return is `(ending / starting) ** (252 / (N - 1)) - 1` for N recorded sessions, unavailable with fewer than two observations or nonpositive ending equity. Annualized volatility is sample standard deviation of daily simple returns times `sqrt(252)`, unavailable with fewer than two daily returns. Maximum drawdown is the minimum equity/prior-peak minus one, with starting cash as the initial peak. Turnover is total absolute filled notional divided by average equity (starting equity plus recorded daily equity values). Time in market is the fraction of recorded sessions with any holdings.

The benchmark is price-only buy-and-hold for the first symbol, scaled to starting cash, using that symbol's available bars. It excludes transaction costs and dividends, so it is a rough reference, not a fully cost-matched benchmark. Annualized figures based on a short sample are especially unstable and should not be read as forecasts. Sharpe ratio is intentionally omitted. Metric definitions and limitations are also recorded in `docs/design.md`.

## Limitations

Daily OHLC simulation cannot model queue position, market impact, partial fills, spreads, halts, intraday price paths, or all live execution conditions. The sample is synthetic and tiny. Historical results can be distorted by data errors, survivorship bias, look-ahead bias, corporate actions, parameter selection, and unmodeled costs. Do not infer expected live returns from this engine.

## Roadmap

Possible future work includes richer corporate-action-aware adjusted-data contracts, explicit exchange calendars, stronger multi-symbol missing-data rules, more detailed realized-P&L accounting, and independent review against trusted reference cases. None of those capabilities is claimed today.
