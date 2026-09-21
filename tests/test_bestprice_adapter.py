from decimal import Decimal
from etl.adapters.bestprice import BestPriceAdapter, _is_specific_departure
from etl.config import DEFAULT_DATA_DIR

def test_bestprice_adapter_counts():
    adapter = BestPriceAdapter()
    bundle = adapter.extract_and_transform(DEFAULT_DATA_DIR)

    # 509 tours
    assert len(bundle.tours) == 509
    assert bundle.metrics["tours_count"] == 509

    # Only concrete dated departures: 36 range/recurring offers stay in staging.
    assert len(bundle.departures) == 1043
    assert len(bundle.prices) == 1043

    # Reviews: 1056
    assert len(bundle.reviews) == 1056
    assert bundle.metrics["tour_reviews_loaded"] == 1056

    # Out of scope counts
    assert bundle.metrics["out_of_scope_prices"] == 6131
    assert bundle.metrics["out_of_scope_reviews"] == 611

    # Check that 5 đ reference prices are NOT in bundle.prices
    five_vnd_prices = [p for p in bundle.prices if p.sale_price == Decimal("5.00")]
    assert len(five_vnd_prices) == 0

    # Check unmapped items include reference / from prices
    unmapped_ref = [u for u in bundle.unmapped_items if u.data_kind == "reference_or_ad_price"]
    assert len(unmapped_ref) > 0

    # Itineraries exist for all 509 tours
    assert len(bundle.itineraries) == 509

def test_bestprice_rejects_range_and_keeps_airline_wording():
    assert not _is_specific_departure({
        "date": "2026-07-21",
        "context": "Thứ 5 hàng tuần (21/07/2026 - 31/12/2026) Khách sạn 3 sao",
    })
    assert _is_specific_departure({
        "date": "2026-09-19",
        "context": "19/09/2026 Còn chỗ Hàng không Qatar Airways",
    })
