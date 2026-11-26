"""Run a configured local-CSV backtest and save reproducible artifacts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

from daybreak import __version__
from daybreak.data import load_bars
from daybreak.engine import run_backtest
from daybreak.metrics import calculate_metrics
from daybreak.strategy import BuyAndHold, MovingAverageCross


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def run_config(config_path: Path) -> Path:
    """Run one JSON configuration and return its newly created output folder."""
    config_path = config_path.resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    for required in ("data", "strategy", "starting_cash", "output_dir"):
        if required not in config:
            raise ValueError(f"configuration is missing required key {required!r}")
    data_path = (config_path.parent / config["data"]).resolve()
    bars = load_bars(data_path)
    strategy_config = config["strategy"]
    kind = strategy_config.get("type")
    if kind == "buy_and_hold":
        strategy = BuyAndHold(strategy_config["symbol"], float(strategy_config["quantity"]))
    elif kind == "moving_average_cross":
        strategy = MovingAverageCross(
            strategy_config["symbol"],
            int(strategy_config.get("short_window", 2)),
            int(strategy_config.get("long_window", 3)),
            float(strategy_config.get("quantity", 1)),
        )
    else:
        raise ValueError("strategy.type must be 'buy_and_hold' or 'moving_average_cross'")
    start = _parse_date(config.get("start"))
    end = _parse_date(config.get("end"))
    result = run_backtest(
        bars,
        strategy,
        float(config["starting_cash"]),
        float(config.get("commission_per_order", 0)),
        float(config.get("slippage_bps", 0)),
        start,
        end,
    )
    metrics = calculate_metrics(result, float(config["starting_cash"]))
    data_hash = hashlib.sha256(data_path.read_bytes()).hexdigest()
    run_timestamp = datetime.now(UTC).replace(microsecond=0).isoformat()
    run_id = f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{data_hash[:8]}"
    root = (config_path.parent / config["output_dir"]).resolve()
    output = root / run_id
    output.mkdir(parents=True, exist_ok=False)

    with (output / "equity_curve.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["date", "cash", "equity", "benchmark_equity", "positions_json"])
        for record in result.daily:
            writer.writerow(
                [
                    record.date.isoformat(),
                    f"{record.cash:.10f}",
                    f"{record.equity:.10f}",
                    "" if record.benchmark_equity is None else f"{record.benchmark_equity:.10f}",
                    json.dumps(record.positions, sort_keys=True),
                ]
            )
    with (output / "orders.csv").open("w", newline="", encoding="utf-8") as file:
        fields = [
            "order_id",
            "symbol",
            "side",
            "quantity",
            "submitted_date",
            "status",
            "fill_date",
            "fill_price",
            "commission",
            "slippage",
            "reason",
        ]
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for order in result.orders:
            writer.writerow(
                {
                    "order_id": order.order_id,
                    "symbol": order.symbol,
                    "side": order.side.value,
                    "quantity": order.quantity,
                    "submitted_date": order.submitted_date.isoformat(),
                    "status": order.status.value,
                    "fill_date": order.fill_date.isoformat() if order.fill_date else "",
                    "fill_price": order.fill_price if order.fill_price is not None else "",
                    "commission": order.commission,
                    "slippage": order.slippage,
                    "reason": order.reason or "",
                }
            )
    (output / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n")
    metadata = {
        "run_timestamp_utc": run_timestamp,
        "run_id": run_id,
        "engine_version": __version__,
        "data_file": data_path.name,
        "data_sha256": data_hash,
        "strategy": {"name": result.strategy_name, "parameters": result.strategy_parameters},
        "date_range": {
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
        },
        "starting_cash": config["starting_cash"],
        "costs": {
            "commission_per_order": config.get("commission_per_order", 0),
            "slippage_bps": config.get("slippage_bps", 0),
        },
        "raw_prices_only": True,
    }
    (output / "run_config.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    print(f"Run saved: {output}")
    print(
        f"Equity: {metrics['starting_equity']:.2f} -> {metrics['ending_equity']:.2f} "
        f"({metrics['total_return']:.2%})"
    )
    print(
        f"Filled orders: {metrics['filled_orders']}; rejected: {metrics['rejected_orders']}; "
        f"cancelled: {metrics['cancelled_orders']}"
    )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a deterministic daily-bar backtest.")
    parser.add_argument("config", type=Path, help="path to JSON run configuration")
    args = parser.parse_args()
    try:
        run_config(args.config)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
