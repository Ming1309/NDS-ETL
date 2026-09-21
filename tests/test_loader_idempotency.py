import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from etl.models.travel import (
    Base, SourceSystem, Category, SourceEntity, Tour, Location,
    TourDeparture, TourDeparturePrice, Itinerary, ItineraryItem, Review
)
from etl.adapters.base import (
    SourceBundle, StandardizedTour, StandardizedDeparture, StandardizedPrice,
    StandardizedItinerary, StandardizedItineraryItem, StandardizedReview
)
from etl.loader.nds_loader import NdsLoader
from decimal import Decimal
from datetime import datetime

@pytest.fixture
def in_memory_session():
    # SQLite in-memory engine without schemas
    engine = create_engine("sqlite:///:memory:")
    
    # Temporarily remove schema for SQLite compatibility
    for table in Base.metadata.tables.values():
        table.schema = None
    Base.metadata.create_all(engine)

    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_loader_idempotency_sample_bundle(in_memory_session):
    session = in_memory_session

    sample_bundle = SourceBundle(
        source_name="TestSource",
        tours=[
            StandardizedTour(
                source_record_key="tour_001",
                name="Hà Nội - Hạ Long 2N1Đ",
                description="Tour du lịch khám phá vịnh Hạ Long",
                duration_days=2,
                duration_nights=1,
                departure_location_name="Hà Nội",
                destinations=["Hạ Long"]
            )
        ],
        departures=[
            StandardizedDeparture(
                tour_source_key="tour_001",
                source_departure_key="dep_101",
                departure_at=datetime(2026, 10, 1, 8, 0, 0),
                departure_location_name="Hà Nội"
            )
        ],
        prices=[
            StandardizedPrice(
                tour_source_key="tour_001",
                source_departure_key="dep_101",
                list_price=Decimal("2500000.00"),
                sale_price=Decimal("2000000.00"),
                currency="VND",
                observed_at=datetime(2026, 9, 20, 12, 0, 0)
            )
        ],
        itineraries=[
            StandardizedItinerary(
                tour_source_key="tour_001",
                name="Lịch trình tiêu chuẩn",
                items=[
                    StandardizedItineraryItem(sequence_no=1, day_start=1, day_end=1, title="Ngày 1", description="Hà Nội - Hạ Long"),
                    StandardizedItineraryItem(sequence_no=2, day_start=2, day_end=2, title="Ngày 2", description="Hạ Long - Hà Nội"),
                ]
            )
        ],
        reviews=[
            StandardizedReview(
                tour_source_key="tour_001",
                source_review_key="rev_501",
                reviewer_display_name="Nguyễn Văn A",
                content="Chuyến đi rất vui!",
                rating_value=Decimal("9.0"),
                rating_scale=Decimal("10.0")
            )
        ]
    )

    loader = NdsLoader(session=session, dry_run=False)

    # First load
    counts1 = loader.load_bundle(sample_bundle)
    session.commit()

    assert counts1["tours"] == 1
    assert counts1["departures"] == 1
    assert counts1["prices"] == 1
    assert counts1["reviews"] == 1

    tour_before = session.query(SourceEntity).filter_by(source_record_key="tour_001").first()
    first_tour_id = tour_before.source_entity_id

    # Second load with identical bundle
    counts2 = loader.load_bundle(sample_bundle)
    session.commit()

    # Verify counts in DB did NOT increase
    total_tours = session.query(SourceEntity).count()
    total_deps = session.query(TourDeparture).count()
    total_prices = session.query(TourDeparturePrice).count()
    total_revs = session.query(Review).count()

    assert total_tours == 1
    assert total_deps == 1
    assert total_prices == 1
    assert total_revs == 1

    # Verify primary key did not change
    tour_after = session.query(SourceEntity).filter_by(source_record_key="tour_001").first()
    assert tour_after.source_entity_id == first_tour_id
