from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Any, Optional

TRANSFORMER_VERSION = "2.0.0"

@dataclass
class RawInput:
    """A source row before filtering, de-duplication, or validation."""
    file_name: str
    payload: Dict[str, Any]
    line_number: int
    sheet_name: Optional[str] = None
    source_entity_key: Optional[str] = None

@dataclass
class StandardizedTour:
    source_record_key: str
    name: str
    description: Optional[str] = None
    duration_days: Optional[int] = None
    duration_nights: Optional[int] = None
    departure_location_name: Optional[str] = None
    destinations: List[str] = field(default_factory=list)
    raw_payload: Dict[str, Any] = field(default_factory=dict)
    file_name: str = ""
    line_number: int = 0
    destinations_state: str = "complete"  # complete, absent, invalid

@dataclass
class StandardizedDeparture:
    tour_source_key: str
    source_departure_key: str
    departure_at: Optional[datetime] = None
    departure_location_name: Optional[str] = None
    raw_payload: Dict[str, Any] = field(default_factory=dict)

@dataclass
class StandardizedPrice:
    tour_source_key: str
    source_departure_key: str
    list_price: Optional[Decimal] = None
    sale_price: Optional[Decimal] = None
    discount_percent: Optional[Decimal] = None
    discount_amount: Optional[Decimal] = None
    currency: str = "VND"
    observed_at: Optional[datetime] = None
    raw_payload: Dict[str, Any] = field(default_factory=dict)

@dataclass
class StandardizedItineraryStop:
    location_name: str
    stop_order: int

@dataclass
class StandardizedItineraryItem:
    sequence_no: int
    day_start: Optional[int] = None
    day_end: Optional[int] = None
    title: Optional[str] = None
    description: Optional[str] = None
    stops: List[StandardizedItineraryStop] = field(default_factory=list)

@dataclass
class StandardizedItinerary:
    tour_source_key: str
    name: str
    items: List[StandardizedItineraryItem] = field(default_factory=list)
    sync_state: str = "complete"  # complete, absent, invalid

@dataclass
class StandardizedReview:
    tour_source_key: str
    source_review_key: str
    reviewer_display_name: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    rating_value: Optional[Decimal] = None
    rating_scale: Optional[Decimal] = None
    reviewed_at: Optional[datetime] = None
    raw_payload: Dict[str, Any] = field(default_factory=dict)

@dataclass
class UnmappedData:
    source_record_key: str
    data_kind: str
    payload: Dict[str, Any]

@dataclass
class EtlIssue:
    record_key: Optional[str]
    field_name: Optional[str]
    error_code: str
    severity: str # WARNING, ERROR, QUARANTINE, INFO
    raw_value: Optional[str]
    message: str

@dataclass
class SourceBundle:
    source_name: str
    tours: List[StandardizedTour] = field(default_factory=list)
    departures: List[StandardizedDeparture] = field(default_factory=list)
    prices: List[StandardizedPrice] = field(default_factory=list)
    itineraries: List[StandardizedItinerary] = field(default_factory=list)
    reviews: List[StandardizedReview] = field(default_factory=list)
    unmapped_items: List[UnmappedData] = field(default_factory=list)
    issues: List[EtlIssue] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    file_hashes: Dict[str, str] = field(default_factory=dict)
    raw_records: List[RawInput] = field(default_factory=list)
    source_observed_at: Optional[datetime] = None
    transformer_version: str = TRANSFORMER_VERSION

class BaseSourceAdapter(ABC):
    @property
    @abstractmethod
    def source_name(self) -> str:
        pass

    @abstractmethod
    def extract_and_transform(self, data_dir: str) -> SourceBundle:
        pass
