# Design notes

## Event order and information boundary

For each date in chronological order, the engine:

1. Fills pending market orders at that symbol's current open, with adverse configured slippage.
2. Makes completed bars through the current session available as an immutable tuple to the strategy.
3. Converts strategy target share quantities to orders. Orders are submitted after the close and are not eligible until that symbol's next available bar.
4. Marks holdings at current closes. If a held symbol has no bar on a session, its last available close is carried forward; an unmarked position is an error.
5. Records daily cash, positions, equity, and a price-only benchmark.

Orders without a later bar for their symbol at the end of the selected input window are retained and marked cancelled with a reason. A rejected order remains in the order ledger. A strategy can see only history passed at the current step, not the engine's future input rows.

## Accounting conventions

The ledger supports USD long-only fractional shares. Buy fills deduct notional plus a fixed per-order commission. Sell fills add notional less commission. Slippage is a proportional adverse adjustment to the open: buys pay `open * (1 + bps / 10,000)` and sells receive `open * (1 - bps / 10,000)`. Average cost is quantity-weighted fill price and is preserved on partial sales; commissions are tracked as cash costs rather than folded into average cost. Cash cannot go below zero and positions cannot go short. Orders that violate constraints are rejected with a reason.

Input prices are raw and no split or dividend adjustments are processed. Do not mix raw and adjusted data. The `adj_close` field is optional descriptive data only and is not used for fills or marks. The sample CSV is synthetic, deliberately tiny, and is not a market history or a survivorship-free universe.

## Performance definitions

Returns use daily marked equity. Annualized return is `(ending / starting) ** (252 / (N - 1)) - 1`, where N includes the initial and subsequent recorded sessions; it is unavailable for fewer than two records or nonpositive ending equity. Annualized volatility is sample standard deviation of daily simple equity returns multiplied by `sqrt(252)` and is unavailable with fewer than two daily returns. Maximum drawdown is the minimum equity-to-prior-peak ratio minus one, with starting cash as the initial peak. Turnover is total absolute filled notional divided by average equity, including starting equity and each recorded close. Time in market is the fraction of recorded sessions with any holding. The benchmark is a price-only buy-and-hold series for the first symbol, scaled to starting cash and based on matching sessions where that symbol has a bar; it excludes fees and dividends, so it is only a rough reference.

These are descriptive calculations, not evidence of an exploitable edge. No Sharpe ratio is reported.

## Execution limitations

Daily OHLC bars cannot model queue priority, market impact, partial fills, halts, spreads, or intraday price paths. A next-open fill plus simple slippage and commission is an explicit approximation, not a guarantee of executable live prices. Corporate actions, taxes, borrow, leverage, multiple currencies, and live broker integration are out of scope.
