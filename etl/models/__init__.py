"""
SQLAlchemy models package
"""
from etl.models.travel import (
    Base,
    SourceSystem,
    Category,
    SourceEntity,
    Tour,
    Location,
    TourDestination,
    TourDeparture,
    TourDeparturePrice,
    Itinerary,
    ItineraryItem,
    ItineraryStop,
    Review,
)
from etl.models.staging import (
    StagingBase,
    EtlRun,
    Snapshot,
    RawRecord,
    EtlIssueModel,
    Mapping,
    UnmappedTourData,
    LocationAlias,
)

__all__ = [
    "Base",
    "SourceSystem",
    "Category",
    "SourceEntity",
    "Tour",
    "Location",
    "TourDestination",
    "TourDeparture",
    "TourDeparturePrice",
    "Itinerary",
    "ItineraryItem",
    "ItineraryStop",
    "Review",
    "StagingBase",
    "EtlRun",
    "Snapshot",
    "RawRecord",
    "EtlIssueModel",
    "Mapping",
    "UnmappedTourData",
    "LocationAlias",
]
