import json
from pathlib import Path

from daybreak.cli import run_config

ROOT = Path(__file__).parents[1]


def test_cli_writes_auditable_artifacts_without_overwriting(tmp_path: Path) -> None:
    config = {
        "data": str(ROOT / "data" / "synthetic.csv"),
        "strategy": {"type": "buy_and_hold", "symbol": "DEMO", "quantity": 1},
        "starting_cash": 1000,
        "commission_per_order": 1,
        "slippage_bps": 5,
        "output_dir": str(tmp_path / "results"),
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))
    output = run_config(config_path)
    assert {path.name for path in output.iterdir()} == {
        "equity_curve.csv",
        "orders.csv",
        "metrics.json",
        "run_config.json",
    }
    metadata = json.loads((output / "run_config.json").read_text())
    assert metadata["data_sha256"]
    assert metadata["raw_prices_only"] is True
    metrics = json.loads((output / "metrics.json").read_text())
    assert metrics["filled_orders"] == 1
