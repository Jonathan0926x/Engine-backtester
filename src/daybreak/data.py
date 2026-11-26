"""Canonical daily bars and strict CSV loading."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path

REQUIRED_COLUMNS = ("symbol", "date", "open", "high", "low", "close", "volume")
OPTIONAL_COLUMNS = ("adj_close",)


@dataclass(frozen=True, slots=True)
class Bar:
    """One completed daily session, labeled by its exchange-local trading date."""

    symbol: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    adj_close: float | None = None


def load_bars(path: str | Path) -> list[Bar]:
    """Read and validate bars from a CSV file, preserving input order.

    Columns are lowercase and named symbol,date,open,high,low,close,volume;
    adj_close is optional. Dates must be ISO-8601 YYYY-MM-DD.
    """
    source = Path(path)
    try:
        handle = source.open("r", newline="", encoding="utf-8-sig")
    except OSError as exc:
        raise ValueError(f"Cannot read CSV {source}: {exc}") from exc

    with handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"{source}: CSV is empty or has no header")
        fields = [field.strip().lower() for field in reader.fieldnames]
        if len(fields) != len(set(fields)):
            raise ValueError(f"{source}: duplicate column names")
        reader.fieldnames = fields
        missing = sorted(set(REQUIRED_COLUMNS) - set(fields))
        if missing:
            raise ValueError(f"{source}: missing required columns: {', '.join(missing)}")

        bars: list[Bar] = []
        seen: set[tuple[str, date]] = set()
        last_date: dict[str, date] = {}
        for row_number, row in enumerate(reader, start=2):
            symbol = (row.get("symbol") or "").strip().upper()
            if not symbol:
                raise ValueError(f"{source}: row {row_number}: field 'symbol' is missing")
            raw_date = (row.get("date") or "").strip()
            try:
                session = date.fromisoformat(raw_date)
            except ValueError as exc:
                raise ValueError(
                    f"{source}: row {row_number}: field 'date' must be YYYY-MM-DD, got {raw_date!r}"
                ) from exc
            key = (symbol, session)
            if key in seen:
                raise ValueError(
                    f"{source}: row {row_number}: duplicate symbol/date {symbol} {session}"
                )
            if symbol in last_date and session <= last_date[symbol]:
                raise ValueError(
                    f"{source}: row {row_number}: dates for {symbol} are not in chronological order"
                )
            seen.add(key)
            last_date[symbol] = session

            numbers: dict[str, float] = {}
            for field in ("open", "high", "low", "close", "volume", "adj_close"):
                if field not in fields:
                    continue
                raw = (row.get(field) or "").strip()
                if not raw:
                    if field == "adj_close":
                        continue
                    raise ValueError(f"{source}: row {row_number}: field '{field}' is missing")
                try:
                    value = float(raw)
                except ValueError as exc:
                    raise ValueError(
                        f"{source}: row {row_number}: field '{field}' must be numeric, got {raw!r}"
                    ) from exc
                if not math.isfinite(value):
                    raise ValueError(f"{source}: row {row_number}: field '{field}' must be finite")
                if field == "volume":
                    if value < 0:
                        raise ValueError(f"{source}: row {row_number}: volume must be nonnegative")
                elif value <= 0:
                    raise ValueError(f"{source}: row {row_number}: {field} must be positive")
                numbers[field] = value

            if not (numbers["low"] <= numbers["open"] <= numbers["high"]):
                raise ValueError(f"{source}: row {row_number}: open must be between low and high")
            if not (numbers["low"] <= numbers["close"] <= numbers["high"]):
                raise ValueError(f"{source}: row {row_number}: close must be between low and high")
            bars.append(Bar(symbol=symbol, date=session, **numbers))

    if not bars:
        raise ValueError(f"{source}: CSV contains no data rows")
    return bars
