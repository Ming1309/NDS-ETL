import pytest
from decimal import Decimal
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from etl.models.travel import Base, SourceEntity, TourDeparture, TourDeparturePrice
from etl.adapters.base import (
    StandardizedTour, StandardizedDeparture, StandardizedPrice,
    StandardizedItinerary, StandardizedItineraryItem, StandardizedReview,
    SourceBundle, EtlIssue
)
from etl.loader.nds_loader import NdsLoader
from etl.normalizers.currency import parse_decimal
from etl.normalizers.datetime import parse_datetime
from etl.normalizers.location import normalize_location_name

@pytest.fixture
def in_memory_session():
    engine = create_engine("sqlite:///:memory:")
    for table in Base.metadata.tables.values():
        table.schema = None
    Base.metadata.create_all(engine)

    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_missing_price_does_not_become_zero():
    assert parse_decimal(None) is None
    assert parse_decimal("") is None
    assert parse_decimal("   ") is None
    assert parse_decimal("abc") is None

def test_ambiguous_or_excluded_location():
    std, loc_type, _ = normalize_location_name("Tour Trong Nước")
    assert std is None

    std2, loc_type2, _ = normalize_location_name("Khởi hành hàng tuần")
    assert std2 is None

def test_departure_without_price_is_allowed(in_memory_session):
    session = in_memory_session
    bundle = SourceBundle(
        source_name="TestSource",
        tours=[
            StandardizedTour(
                source_record_key="tour_no_price",
                name="Tour Không Giá",
                duration_days=1,
                duration_nights=0
            )
        ],
        departures=[
            StandardizedDeparture(
                tour_source_key="tour_no_price",
                source_departure_key="dep_no_price_01",
                departure_at=datetime(2026, 12, 1, 0, 0, 0)
            )
        ],
        prices=[] # No price!
    )

    loader = NdsLoader(session=session, dry_run=False)
    counts = loader.load_bundle(bundle)
    session.commit()

    assert counts["tours"] == 1
    assert counts["departures"] == 1
    assert counts["prices"] == 0

    dep = session.query(TourDeparture).filter_by(source_departure_key="dep_no_price_01").first()
    assert dep is not None

def test_transaction_rollback_preserves_clean_state(in_memory_session):
    session = in_memory_session

    bundle = SourceBundle(
        source_name="TestSource",
        tours=[
            StandardizedTour(
                source_record_key="tour_valid",
                name="Tour Hợp Lệ"
            )
        ]
    )

    loader = NdsLoader(session=session, dry_run=False)
    loader.load_bundle(bundle)

    # Rollback instead of commit
    session.rollback()

    assert session.query(SourceEntity).count() == 0
