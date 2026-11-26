from pathlib import Path

import pytest

from daybreak.data import load_bars

SAMPLE = Path(__file__).parents[1] / "data" / "synthetic.csv"


def test_loads_labeled_synthetic_sample() -> None:
    bars = load_bars(SAMPLE)
    assert len(bars) == 6
    assert bars[0].symbol == "DEMO"
    assert bars[0].date.isoformat() == "2024-01-02"
    assert bars[0].close == 101


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("symbol,date,open,high,low,close\nX,2024-01-01,1,1,1,1\n", "missing required columns"),
        (
            "symbol,date,open,high,low,close,volume\nX,not-a-date,1,1,1,1,0\n",
            "YYYY-MM-DD",
        ),
        (
            "symbol,date,open,high,low,close,volume\nX,2024-01-01,1,1,1,1,\n",
            "volume.*missing",
        ),
        (
            "symbol,date,open,high,low,close,volume\nX,2024-01-01,1,1,1,0,0\n",
            "close must be positive",
        ),
        (
            "symbol,date,open,high,low,close,volume\nX,2024-01-01,1,2,1,1,-1\n",
            "volume must be nonnegative",
        ),
        (
            "symbol,date,open,high,low,close,volume\nX,2024-01-01,3,2,1,2,0\n",
            "open must be between low and high",
        ),
        (
            "symbol,date,open,high,low,close,volume\nX,2024-01-02,1,2,1,2,0\nX,2024-01-01,1,2,1,2,0\n",
            "not in chronological order",
        ),
        (
            "symbol,date,open,high,low,close,volume\nX,2024-01-01,1,2,1,2,0\nX,2024-01-01,1,2,1,2,0\n",
            "duplicate symbol/date",
        ),
    ],
)
def test_rejects_invalid_csv(tmp_path: Path, contents: str, message: str) -> None:
    path = tmp_path / "bad.csv"
    path.write_text(contents)
    with pytest.raises(ValueError, match=message):
        load_bars(path)


def test_optional_adjusted_close_can_be_blank(tmp_path: Path) -> None:
    path = tmp_path / "bars.csv"
    path.write_text("symbol,date,open,high,low,close,volume,adj_close\nX,2024-01-01,1,2,1,2,0,\n")
    assert load_bars(path)[0].adj_close is None
