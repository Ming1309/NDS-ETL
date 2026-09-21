import hashlib
import json
import logging
import re
import urllib.parse
from decimal import Decimal
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

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
    RawInput,
)
from etl.extractors.csv_extractor import read_csv_records
from etl.normalizers.currency import parse_decimal, normalize_currency, calculate_discounts
from etl.normalizers.datetime import parse_datetime
from etl.normalizers.location import normalize_location_name, clean_destination_candidates
from etl.normalizers.text import clean_text

logger = logging.getLogger(__name__)

def compute_file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def parse_duration_text(dur_str: Optional[str]) -> Tuple[Optional[int], Optional[int]]:
    """Parse '4 ngày 3 đêm' or similar into (days, nights)."""
    if not dur_str:
        return None, None
    days = None
    nights = None
    m_days = re.search(r'(\d+)\s*(?:ngày|N)', dur_str, re.IGNORECASE)
    if m_days:
        days = int(m_days.group(1))
    m_nights = re.search(r'(\d+)\s*(?:đêm|D|Đ)', dur_str, re.IGNORECASE)
    if m_nights:
        nights = int(m_nights.group(1))
    return days, nights

def extract_url_params(date_raw: Optional[str]) -> Dict[str, str]:
    """Safely extract query parameters from date_raw URL string."""
    if not date_raw:
        return {}
    m = re.search(r"go_url\('([^']+)'\)", str(date_raw))
    raw_url = m.group(1) if m else str(date_raw)
    try:
        parsed = urllib.parse.urlparse(raw_url)
        qs = urllib.parse.parse_qs(parsed.query)
        return {k: v[0] for k, v in qs.items()}
    except Exception:
        return {}

def _offer_identity(record: Dict[str, Any]) -> Tuple[str, str, str, str]:
    """Identity of a purchasable offer; a calendar date alone is not enough."""
    params = extract_url_params(record.get("date_raw"))
    context = clean_text(record.get("context"), preserve_newlines=False) or ""
    return (
        str(record.get("date") or "").strip(),
        params.get("departure_id", ""),
        params.get("accid", ""),
        normalize_currency(record.get("currency")),
    ) + (context,)

def _is_specific_departure(record: Dict[str, Any]) -> bool:
    """Reject crawler-derived start dates for date ranges and recurring schedules."""
    date_value = str(record.get("date") or "").strip()
    context = clean_text(record.get("context"), preserve_newlines=False) or ""
    if not parse_datetime(date_value):
        return False
    # A date range/weekly wording describes availability, not one departure.
    if re.search(r"\d{1,2}/\d{1,2}/\d{4}\s*[-–]\s*\d{1,2}/\d{1,2}/\d{4}", context):
        return False
    if re.search(r"\b(?:hàng\s+(?:ngày|tuần)|thứ\s*\d+\s+hàng\s+tuần)\b", context, re.I):
        return False
    params = extract_url_params(record.get("date_raw"))
    start_date = params.get("startdate")
    if start_date:
        parsed_start = parse_datetime(urllib.parse.unquote(start_date))
        if parsed_start and parsed_start.date() != parse_datetime(date_value).date():
            return False
    return True

class BestPriceAdapter(BaseSourceAdapter):
    @property
    def source_name(self) -> str:
        return "BestPrice"

    def extract_and_transform(self, data_dir: str) -> SourceBundle:
        base_path = Path(data_dir) / "BestPrice"
        bundle = SourceBundle(source_name=self.source_name)

        tours_file = base_path / "tour.csv"
        prices_file = base_path / "prices.csv"
        reviews_file = base_path / "reviews.csv"

        for p in [tours_file, prices_file, reviews_file]:
            if p.exists():
                bundle.file_hashes[p.name] = compute_file_hash(p)

        # 1. Extract Tours
        tour_records = read_csv_records(tours_file)
        bundle.raw_records.extend(RawInput(tours_file.name, rec, rec["__line_number__"], source_entity_key=rec.get("entity_id")) for rec in tour_records)
        tour_map: Dict[str, StandardizedTour] = {}

        for rec in tour_records:
            entity_id = rec.get("entity_id", "").strip()
            if not entity_id:
                bundle.issues.append(EtlIssue(
                    record_key=None,
                    field_name="entity_id",
                    error_code="MISSING_PRIMARY_KEY",
                    severity="QUARANTINE",
                    raw_value=str(rec),
                    message="Tour row missing entity_id"
                ))
                continue

            name = clean_text(rec.get("name"), preserve_newlines=False)
            desc = clean_text(rec.get("description"), preserve_newlines=True)

            attr_raw = rec.get("attributes", "")
            attr = {}
            if attr_raw:
                try:
                    attr = json.loads(attr_raw)
                except Exception as e:
                    bundle.issues.append(EtlIssue(
                        record_key=entity_id,
                        field_name="attributes",
                        error_code="CORRUPT_JSON",
                        severity="WARNING",
                        raw_value=attr_raw[:100],
                        message=f"Could not parse attributes JSON: {e}"
                    ))

            # Duration
            duration_str = attr.get("duration")
            days, nights = parse_duration_text(duration_str)

            # Locations
            dep_point = attr.get("departure_point")
            std_dep, _, _ = normalize_location_name(dep_point)

            journey = attr.get("journey")
            destinations = clean_destination_candidates(journey)

            tour = StandardizedTour(
                source_record_key=entity_id,
                name=name or f"Tour {entity_id}",
                description=desc,
                duration_days=days,
                duration_nights=nights,
                departure_location_name=std_dep,
                destinations=destinations,
                raw_payload=rec,
                file_name=tours_file.name,
                line_number=rec.get("__line_number__", 0)
            )
            tour_map[entity_id] = tour
            bundle.tours.append(tour)

            # Itinerary
            itinerary_items = []
            attr_itin = attr.get("itinerary")
            if attr_itin and isinstance(attr_itin, list):
                for seq_no, item in enumerate(attr_itin, start=1):
                    item_title = clean_text(item.get("title"), preserve_newlines=False)
                    item_desc = clean_text(item.get("content") or item.get("details"), preserve_newlines=True)
                    # Extract day number
                    m_day = re.search(r'Ngày\s*(\d+)', str(item_title), re.IGNORECASE)
                    day_num = int(m_day.group(1)) if m_day else seq_no

                    itinerary_items.append(StandardizedItineraryItem(
                        sequence_no=seq_no,
                        day_start=day_num,
                        day_end=day_num,
                        title=item_title,
                        description=item_desc,
                        stops=[]
                    ))
            elif rec.get("content"):
                # Fallback: single item without determined day
                content_desc = clean_text(rec.get("content"), preserve_newlines=True)
                itinerary_items.append(StandardizedItineraryItem(
                    sequence_no=1,
                    day_start=None,
                    day_end=None,
                    title="Chương trình tour",
                    description=content_desc,
                    stops=[]
                ))

            if itinerary_items:
                bundle.itineraries.append(StandardizedItinerary(
                    tour_source_key=entity_id,
                    name="source_itinerary",
                    items=itinerary_items
                ))

            # Staging: Embedded prices in tour.csv, rating alternatives, images
            if rec.get("prices"):
                bundle.unmapped_items.append(UnmappedData(
                    source_record_key=entity_id,
                    data_kind="embedded_prices",
                    payload={"raw_prices": rec.get("prices")}
                ))
            if rec.get("rating_alternatives"):
                bundle.unmapped_items.append(UnmappedData(
                    source_record_key=entity_id,
                    data_kind="rating_alternatives",
                    payload={"alternatives": rec.get("rating_alternatives")}
                ))

        # 2. Extract Prices
        price_records = read_csv_records(prices_file)
        bundle.raw_records.extend(RawInput(prices_file.name, rec, rec["__line_number__"], source_entity_key=rec.get("entity_id")) for rec in price_records)
        out_of_scope_prices = 0

        # Group tour prices by entity_id
        tour_prices_by_entity: Dict[str, list] = {}
        for prec in price_records:
            if prec.get("category") != "tour":
                out_of_scope_prices += 1
                continue
            eid = prec.get("entity_id", "").strip()
            if not eid:
                continue
            tour_prices_by_entity.setdefault(eid, []).append(prec)

        bundle.metrics["out_of_scope_prices"] = out_of_scope_prices

        # Process each tour's prices
        departure_keys_seen = set()

        for eid, plist in tour_prices_by_entity.items():
            if eid not in tour_map:
                bundle.issues.append(EtlIssue(
                    record_key=eid,
                    field_name="entity_id",
                    error_code="ORPHAN_PRICE",
                    severity="ERROR",
                    raw_value=f"Prices count: {len(plist)}",
                    message="Price references unknown tour entity_id"
                ))
                continue

            tour = tour_map[eid]
            dep_rows = [p for p in plist if p.get("kind") == "departure"]
            orig_rows = [p for p in plist if p.get("kind") == "original"]
            other_rows = [p for p in plist if p.get("kind") in ("reference", "from")]

            # Save reference / from to staging
            for o in other_rows:
                bundle.unmapped_items.append(UnmappedData(
                    source_record_key=eid,
                    data_kind="reference_or_ad_price",
                    payload=o
                ))

            # Pair departure rows with original rows
            # Map list prices by the full purchasable offer identity.
            orig_map = {}
            for o in orig_rows:
                d_str = o.get("date", "").strip()
                if d_str and _is_specific_departure(o):
                    key = _offer_identity(o)
                    if key in orig_map:
                        bundle.issues.append(EtlIssue(eid, "original_price", "AMBIGUOUS_LIST_PRICE", "WARNING", d_str,
                            "Multiple original prices match the same departure offer"))
                        orig_map[key] = None
                    else:
                        orig_map[key] = o
                else:
                    # Staging only for original without specific date
                    bundle.unmapped_items.append(UnmappedData(
                        source_record_key=eid,
                        data_kind="original_price_without_date",
                        payload=o
                    ))

            for d in dep_rows:
                date_val = d.get("date", "").strip()
                if not _is_specific_departure(d):
                    # Date ranges or 'Hàng ngày' without specific date stay in staging
                    bundle.unmapped_items.append(UnmappedData(
                        source_record_key=eid,
                        data_kind="departure_range_price",
                        payload=d
                    ))
                    continue

                # Parse date
                dep_datetime = parse_datetime(date_val)
                url_params = extract_url_params(d.get("date_raw"))
                dep_id = url_params.get("departure_id")
                accid = url_params.get("accid", "")

                if dep_id:
                    source_dep_key = f"dep_{dep_id}_{accid}_{date_val}".replace("__", "_")
                else:
                    # Deterministic key from entity, date, context
                    ctx = clean_text(d.get("context"), preserve_newlines=False) or ""
                    ctx_hash = hashlib.md5(ctx.encode()).hexdigest()[:8]
                    source_dep_key = f"dep_{eid}_{date_val}_{ctx_hash}"

                dep_unique_key = (eid, source_dep_key)
                if dep_unique_key not in departure_keys_seen:
                    departure_keys_seen.add(dep_unique_key)
                    bundle.departures.append(StandardizedDeparture(
                        tour_source_key=eid,
                        source_departure_key=source_dep_key,
                        departure_at=dep_datetime,
                        departure_location_name=tour.departure_location_name,
                        raw_payload=d
                    ))

                # Build price
                sale_price = parse_decimal(d.get("amount"))
                list_price = None
                original = orig_map.get(_offer_identity(d))
                if original:
                    list_price = parse_decimal(original.get("amount"))

                disc_percent, disc_amount = calculate_discounts(list_price, sale_price)
                observed_at = parse_datetime(d.get("fetched_at"))
                currency = normalize_currency(d.get("currency"))

                bundle.prices.append(StandardizedPrice(
                    tour_source_key=eid,
                    source_departure_key=source_dep_key,
                    list_price=list_price,
                    sale_price=sale_price,
                    discount_percent=disc_percent,
                    discount_amount=disc_amount,
                    currency=currency,
                    observed_at=observed_at,
                    raw_payload={"departure_price": d, "original_price": original}
                ))

        # 3. Extract Reviews
        review_records = read_csv_records(reviews_file)
        bundle.raw_records.extend(RawInput(reviews_file.name, rec, rec["__line_number__"], source_entity_key=rec.get("entity_id")) for rec in review_records)
        out_of_scope_reviews = 0
        tour_reviews_loaded = 0

        for rrec in review_records:
            if rrec.get("category") != "tour":
                out_of_scope_reviews += 1
                continue

            eid = rrec.get("entity_id", "").strip()
            if eid not in tour_map:
                bundle.issues.append(EtlIssue(
                    record_key=eid,
                    field_name="entity_id",
                    error_code="ORPHAN_REVIEW",
                    severity="ERROR",
                    raw_value=rrec.get("review_id"),
                    message="Review references unknown tour entity_id"
                ))
                continue

            # Only load current reviews
            is_curr = str(rrec.get("is_current", "")).strip()
            if is_curr not in ("1", "true", "True"):
                bundle.unmapped_items.append(UnmappedData(
                    source_record_key=eid,
                    data_kind="archived_review",
                    payload=rrec
                ))
                continue

            rid = rrec.get("review_id", "").strip()
            if not rid:
                # Hash fallback
                h = hashlib.sha256(f"{eid}:{rrec.get('reviewer_name')}:{rrec.get('content')}".encode()).hexdigest()[:16]
                rid = f"rev_{h}"

            rev_date = parse_datetime(rrec.get("review_date"))
            rating_val = parse_decimal(rrec.get("rating"))
            rating_scl = parse_decimal(rrec.get("rating_scale")) or Decimal("10.00")

            bundle.reviews.append(StandardizedReview(
                tour_source_key=eid,
                source_review_key=rid,
                reviewer_display_name=clean_text(rrec.get("reviewer_name"), preserve_newlines=False),
                title=clean_text(rrec.get("title"), preserve_newlines=False),
                content=clean_text(rrec.get("content"), preserve_newlines=True),
                rating_value=rating_val,
                rating_scale=rating_scl,
                reviewed_at=rev_date,
                raw_payload=rrec
            ))
            tour_reviews_loaded += 1

        bundle.metrics["out_of_scope_reviews"] = out_of_scope_reviews
        bundle.metrics["tour_reviews_loaded"] = tour_reviews_loaded
        bundle.metrics["tours_count"] = len(bundle.tours)
        bundle.metrics["departures_count"] = len(bundle.departures)
        bundle.metrics["prices_count"] = len(bundle.prices)
        observed = [parse_datetime(r.get("fetched_at")) for r in tour_records if parse_datetime(r.get("fetched_at"))]
        bundle.source_observed_at = max(observed) if observed else None

        return bundle
