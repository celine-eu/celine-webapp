"""Tests for the forecast route helpers."""
from celine.webapp.api.forecast import _first_value, _parse_ts, _sort_dedup
from celine.webapp.api.schemas import ForecastHourItem


def _item(ts: str, value: float) -> ForecastHourItem:
    return ForecastHourItem(ts=ts, value=value, lower=None, upper=None, period="forecast")


def test_sort_dedup_orders_chronologically():
    """Out-of-order rows are returned sorted by timestamp."""
    items = [
        _item("2026-07-03T12:00:00+00:00", 3.0),
        _item("2026-07-03T05:00:00+00:00", 1.0),
        _item("2026-07-03T09:00:00+00:00", 2.0),
    ]
    result = _sort_dedup(items)
    assert [it.value for it in result] == [1.0, 2.0, 3.0]


def test_sort_dedup_drops_duplicate_timestamps_keeping_first():
    """Duplicate instants (e.g. stale forecast runs) collapse to one row."""
    items = [
        _item("2026-07-03T05:00:00+00:00", 1.0),
        _item("2026-07-03T05:00:00+00:00", 99.0),
        _item("2026-07-03T06:00:00+00:00", 2.0),
    ]
    result = _sort_dedup(items)
    assert len(result) == 2
    assert result[0].value == 1.0


def test_sort_dedup_handles_mixed_timestamp_formats():
    """Space/UTC and T/local strings for the same instant dedupe together."""
    items = [
        # Same instant written by two pipeline code paths.
        _item("2026-07-03 05:00:00+00:00", 1.0),
        _item("2026-07-03T07:00:00+02:00", 99.0),
        _item("2026-07-03T08:00:00+02:00", 2.0),
    ]
    result = _sort_dedup(items)
    assert len(result) == 2
    assert [it.value for it in result] == [1.0, 2.0]


def test_parse_ts_naive_assumed_utc():
    """Naive timestamps (timestamp-without-tz columns) must sort with aware ones."""
    naive = _parse_ts("2026-07-03 05:00:00")
    aware = _parse_ts("2026-07-03T06:00:00+00:00")
    assert naive < aware


def test_parse_ts_unparseable_sorts_last():
    items = [_item("not-a-date", 9.0), _item("2026-07-03T05:00:00+00:00", 1.0)]
    result = _sort_dedup(items)
    assert result[0].value == 1.0
    assert result[-1].value == 9.0


def test_first_value_falls_back_to_grid_columns():
    """Post-refactor rows have total_* NULL and grid_* populated."""
    row = {"total_consumption_kwh": None, "grid_import_kwh": 2.5}
    assert _first_value(row, "total_consumption_kwh", "grid_import_kwh") == 2.5


def test_first_value_prefers_legacy_column_when_present():
    row = {"total_consumption_kwh": 1.0, "grid_import_kwh": 2.5}
    assert _first_value(row, "total_consumption_kwh", "grid_import_kwh") == 1.0


def test_first_value_all_null_returns_none():
    row = {"total_consumption_kwh": None, "grid_import_kwh": None}
    assert _first_value(row, "total_consumption_kwh", "grid_import_kwh") is None


def test_first_value_zero_is_a_value():
    row = {"total_consumption_kwh": 0.0, "grid_import_kwh": 2.5}
    assert _first_value(row, "total_consumption_kwh", "grid_import_kwh") == 0.0
