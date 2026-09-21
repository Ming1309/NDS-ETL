from etl.adapters.vietravel import VietravelAdapter, parse_vietravel_duration
from etl.config import DEFAULT_DATA_DIR

def test_parse_vietravel_duration():
    days, nights, disc = parse_vietravel_duration(6.0, "6N5Đ")
    assert days == 6
    assert nights == 5
    assert disc is None

    days_day, nights_day, _ = parse_vietravel_duration(1.0, "Trong ngày")
    assert days_day == 1
    assert nights_day == 0

def test_vietravel_adapter_counts():
    adapter = VietravelAdapter()
    bundle = adapter.extract_and_transform(DEFAULT_DATA_DIR)

    # 320 raw -> 80 dropped -> 240 deduped tours
    assert bundle.metrics["total_raw_rows"] == 320
    assert bundle.metrics["duplicate_rows_dropped"] == 80
    assert bundle.metrics["deduped_rows_count"] == 240
    assert len(bundle.tours) == 240

    # Exactly 2,352 unique nested departures
    assert len(bundle.departures) == 2352
    assert bundle.metrics["unique_nested_tour_ids"] == 2352
    assert len(bundle.prices) == 2352

    # Exactly 21 outer tourId mismatches recorded as issues
    assert bundle.metrics["outer_mismatches_count"] == 21
    outer_issues = [i for i in bundle.issues if i.error_code == "OUTER_TOUR_ID_NOT_IN_NESTED"]
    assert len(outer_issues) == 21

    # Unmapped items recorded for all 240 tours
    assert len(bundle.unmapped_items) == 240
