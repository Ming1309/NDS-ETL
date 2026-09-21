from sqlalchemy import (
    Column,
    BigInteger,
    Integer,
    Text,
    String,
    Numeric,
    DateTime,
    ForeignKey,
    PrimaryKeyConstraint,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()
BigIntPK = BigInteger().with_variant(Integer, "sqlite")

class SourceSystem(Base):
    __tablename__ = "source_system"
    __table_args__ = (
        UniqueConstraint("name", name="uq_source_system_name"),
        {"schema": "travel"}
    )

    source_system_id = Column(BigIntPK, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)

class Category(Base):
    __tablename__ = "category"
    __table_args__ = (
        UniqueConstraint("name", name="uq_category_name"),
        {"schema": "travel"}
    )

    category_id = Column(BigIntPK, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)

class SourceEntity(Base):
    __tablename__ = "source_entity"
    __table_args__ = (
        UniqueConstraint("source_system_id", "category_id", "source_record_key", name="uq_source_entity_key"),
        {"schema": "travel"}
    )

    source_entity_id = Column(BigIntPK, primary_key=True, autoincrement=True)
    source_system_id = Column(BigInteger, ForeignKey("travel.source_system.source_system_id"), nullable=False)
    category_id = Column(BigInteger, ForeignKey("travel.category.category_id"), nullable=False)
    source_record_key = Column(Text, nullable=False)
    name = Column(Text)
    description = Column(Text)

class Tour(Base):
    __tablename__ = "tour"
    __table_args__ = {"schema": "travel"}

    source_entity_id = Column(BigInteger, ForeignKey("travel.source_entity.source_entity_id"), primary_key=True)
    duration_days = Column(Integer)
    duration_nights = Column(Integer)

class Location(Base):
    __tablename__ = "location"
    __table_args__ = {"schema": "travel"}

    location_id = Column(BigIntPK, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)
    location_type = Column(Text)
    parent_location_id = Column(BigInteger, ForeignKey("travel.location.location_id"))

class TourDestination(Base):
    __tablename__ = "tour_destination"
    __table_args__ = (
        PrimaryKeyConstraint("tour_source_entity_id", "location_id"),
        {"schema": "travel"}
    )

    tour_source_entity_id = Column(BigInteger, ForeignKey("travel.tour.source_entity_id"), nullable=False)
    location_id = Column(BigInteger, ForeignKey("travel.location.location_id"), nullable=False)

class TourDeparture(Base):
    __tablename__ = "tour_departure"
    __table_args__ = (
        UniqueConstraint("tour_source_entity_id", "source_departure_key", name="uq_tour_departure_key"),
        {"schema": "travel"}
    )

    tour_departure_id = Column(BigIntPK, primary_key=True, autoincrement=True)
    tour_source_entity_id = Column(BigInteger, ForeignKey("travel.tour.source_entity_id"), nullable=False)
    departure_location_id = Column(BigInteger, ForeignKey("travel.location.location_id"))
    source_departure_key = Column(Text)
    departure_at = Column(DateTime(timezone=True))

class TourDeparturePrice(Base):
    __tablename__ = "tour_departure_price"
    __table_args__ = (
        UniqueConstraint("tour_departure_id", "observed_at", "currency", name="uq_departure_price_obs"),
        {"schema": "travel"}
    )

    tour_departure_price_id = Column(BigIntPK, primary_key=True, autoincrement=True)
    tour_departure_id = Column(BigInteger, ForeignKey("travel.tour_departure.tour_departure_id"), nullable=False)
    list_price = Column(Numeric(18, 2))
    sale_price = Column(Numeric(18, 2))
    discount_percent = Column(Numeric(7, 4))
    discount_amount = Column(Numeric(18, 2))
    currency = Column(String(3))
    observed_at = Column(DateTime(timezone=True))

class Itinerary(Base):
    __tablename__ = "itinerary"
    __table_args__ = (
        UniqueConstraint("tour_source_entity_id", "name", name="uq_itinerary_tour_name"),
        {"schema": "travel"}
    )

    itinerary_id = Column(BigIntPK, primary_key=True, autoincrement=True)
    tour_source_entity_id = Column(BigInteger, ForeignKey("travel.tour.source_entity_id"), nullable=False)
    name = Column(Text)

class ItineraryItem(Base):
    __tablename__ = "itinerary_item"
    __table_args__ = (
        UniqueConstraint("itinerary_id", "sequence_no", name="uq_itinerary_item_seq"),
        {"schema": "travel"}
    )

    itinerary_item_id = Column(BigIntPK, primary_key=True, autoincrement=True)
    itinerary_id = Column(BigInteger, ForeignKey("travel.itinerary.itinerary_id"), nullable=False)
    sequence_no = Column(Integer)
    day_start = Column(Integer)
    day_end = Column(Integer)
    title = Column(Text)
    description = Column(Text)

class ItineraryStop(Base):
    __tablename__ = "itinerary_stop"
    __table_args__ = {"schema": "travel"}

    itinerary_stop_id = Column(BigIntPK, primary_key=True, autoincrement=True)
    itinerary_item_id = Column(BigInteger, ForeignKey("travel.itinerary_item.itinerary_item_id"), nullable=False)
    location_id = Column(BigInteger, ForeignKey("travel.location.location_id"), nullable=False)
    stop_order = Column(Integer)

class Review(Base):
    __tablename__ = "review"
    __table_args__ = (
        UniqueConstraint("source_entity_id", "source_review_key", name="uq_review_key"),
        {"schema": "travel"}
    )

    review_id = Column(BigIntPK, primary_key=True, autoincrement=True)
    source_entity_id = Column(BigInteger, ForeignKey("travel.source_entity.source_entity_id"), nullable=False)
    source_review_key = Column(Text)
    reviewer_display_name = Column(Text)
    title = Column(Text)
    content = Column(Text)
    rating_value = Column(Numeric(8, 4))
    rating_scale = Column(Numeric(8, 4))
    reviewed_at = Column(DateTime(timezone=True))
