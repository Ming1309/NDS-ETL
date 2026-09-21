from etl.adapters.pystravel import PystravelAdapter, parse_pystravel_duration
from etl.config import DEFAULT_DATA_DIR

def test_parse_pystravel_duration():
    days, nights = parse_pystravel_duration("8 ngày 7 đêm", "P8D")
    assert days == 8
    assert nights == 7

def test_pystravel_adapter_counts():
    adapter = PystravelAdapter()
    bundle = adapter.extract_and_transform(DEFAULT_DATA_DIR)

    # 778 raw -> 4 duplicate groups merged -> 774 tours
    assert bundle.metrics["total_raw_records"] == 778
    assert bundle.metrics["duplicate_tour_groups_merged"] == 4
    assert bundle.metrics["unique_tour_ids_count"] == 774
    assert len(bundle.tours) == 774

    # Prices should be 0 (product-level prices are in unmapped, not broadcast to departures)
    assert len(bundle.prices) == 0

    # Departures with valid dates
    assert len(bundle.departures) == 2411

    # Reviews: individual reviews from rating_and_reviews.reviews[]
    assert len(bundle.reviews) == 597
    assert bundle.metrics["reviews_count"] == 597

    # Check unmapped items include product_price and aggregate ratings
    prod_prices = [u for u in bundle.unmapped_items if u.data_kind == "pystravel_product_attributes"]
    assert len(prod_prices) == 774

    # Check duplicate variants saved
    dup_variants = [u for u in bundle.unmapped_items if u.data_kind == "duplicate_variant_url"]
    assert len(dup_variants) == 4
