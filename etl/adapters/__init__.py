"""
Adapters package
"""
from etl.adapters.base import (
    BaseSourceAdapter,
    SourceBundle,
    StandardizedTour,
    StandardizedDeparture,
    StandardizedPrice,
    StandardizedItinerary,
    StandardizedItineraryItem,
    StandardizedReview,
    UnmappedData,
    EtlIssue,
)
from etl.adapters.bestprice import BestPriceAdapter
from etl.adapters.vietravel import VietravelAdapter
from etl.adapters.pystravel import PystravelAdapter

ADAPTERS = {
    "bestprice": BestPriceAdapter,
    "vietravel": VietravelAdapter,
    "pystravel": PystravelAdapter,
}

__all__ = [
    "BaseSourceAdapter",
    "SourceBundle",
    "StandardizedTour",
    "StandardizedDeparture",
    "StandardizedPrice",
    "StandardizedItinerary",
    "StandardizedItineraryItem",
    "StandardizedReview",
    "UnmappedData",
    "EtlIssue",
    "BestPriceAdapter",
    "VietravelAdapter",
    "PystravelAdapter",
    "ADAPTERS",
]
