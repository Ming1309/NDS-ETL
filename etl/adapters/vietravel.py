import hashlib
import json
import logging
import re
from decimal import Decimal
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, Set

from etl.adapters.base import (
    BaseSourceAdapter,
    SourceBundle,
    StandardizedTour,
    StandardizedDeparture,
    StandardizedPrice,
    UnmappedData,
    EtlIssue,
    RawInput,
)
from etl.extractors.excel_extractor import read_excel_sheet
from etl.normalizers.currency import parse_decimal, normalize_currency
from etl.normalizers.datetime import parse_datetime
from etl.normalizers.location import normalize_location_name, clean_destination_candidates
from etl.normalizers.text import clean_text, normalize_id

logger = logging.getLogger(__name__)

def compute_file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def parse_vietravel_duration(day_stay: Any, day_stay_text: Any) -> Tuple[Optional[int], Optional[int], Optional[str]]:
    """
    Returns (days, nights, discrepancy_message).
    """
    days = None
    if day_stay is not None:
        try:
            days = int(float(day_stay))
        except (ValueError, TypeError):
            pass

    nights = None
    days_from_text = None
    dst_str = str(day_stay_text or "").strip()

    if dst_str.lower() in ("trong ngày", "1 ngày", "1n"):
        days_from_text = 1
        nights = 0
    elif dst_str:
        m = re.search(r'(\d+)\s*(?:N|ngày)\s*(\d+)\s*(?:D|Đ|đêm)', dst_str, re.IGNORECASE)
        if m:
            days_from_text = int(m.group(1))
            nights = int(m.group(2))
        else:
            m_days = re.search(r'(\d+)\s*(?:N|ngày)', dst_str, re.IGNORECASE)
            m_nights = re.search(r'(\d+)\s*(?:D|Đ|đêm)', dst_str, re.IGNORECASE)
            if m_days:
                days_from_text = int(m_days.group(1))
            if m_nights:
                nights = int(m_nights.group(1))

    discrepancy = None
    if days is not None and days_from_text is not None and days != days_from_text:
        discrepancy = f"dayStay ({days}) differs from text '{dst_str}' ({days_from_text} days)"

    final_days = days if days is not None else days_from_text
    return final_days, nights, discrepancy

class VietravelAdapter(BaseSourceAdapter):
    @property
    def source_name(self) -> str:
        return "Vietravel"

    def extract_and_transform(self, data_dir: str) -> SourceBundle:
        base_path = Path(data_dir) / "Vietravel"
        bundle = SourceBundle(source_name=self.source_name)

        excel_file = base_path / "Vietravel_Crawled_Data.xlsx"
        if not excel_file.exists():
            raise FileNotFoundError(f"Vietravel file not found: {excel_file}")

        bundle.file_hashes[excel_file.name] = compute_file_hash(excel_file)

        # 1. Read sheet Vietravel_Raw_Data
        raw_records = read_excel_sheet(excel_file, sheet_name="Vietravel_Raw_Data")
        bundle.raw_records.extend(
            RawInput(excel_file.name, rec, rec["__line_number__"], sheet_name="Vietravel_Raw_Data", source_entity_key=normalize_id(rec.get("pageId")))
            for rec in raw_records
        )
        bundle.metrics["total_raw_rows"] = len(raw_records)

        # 2. Complete deduplication of rows
        seen_row_signatures: Set[Tuple] = set()
        deduped_records = []
        duplicate_rows_count = 0

        for r in raw_records:
            # Exclude '__line_number__' from signature
            sig = tuple(sorted((k, str(v)) for k, v in r.items() if k != "__line_number__"))
            if sig in seen_row_signatures:
                duplicate_rows_count += 1
                continue
            seen_row_signatures.add(sig)
            deduped_records.append(r)

        bundle.metrics["duplicate_rows_dropped"] = duplicate_rows_count
        bundle.metrics["deduped_rows_count"] = len(deduped_records)

        # 3. Process each deduped tour
        nested_tour_ids_seen = set()
        outer_mismatches_count = 0

        for rec in deduped_records:
            page_id = normalize_id(rec.get("pageId"))
            if not page_id:
                bundle.issues.append(EtlIssue(
                    record_key=None,
                    field_name="pageId",
                    error_code="MISSING_PAGE_ID",
                    severity="QUARANTINE",
                    raw_value=str(rec)[:100],
                    message="Vietravel row missing pageId"
                ))
                continue

            title = clean_text(rec.get("pageTitle"), preserve_newlines=False)
            if not title:
                title = clean_text(rec.get("destination"), preserve_newlines=False) or f"Tour Vietravel {page_id}"

            # Duration
            days, nights, disc = parse_vietravel_duration(rec.get("dayStay"), rec.get("dayStayText"))
            if disc:
                bundle.issues.append(EtlIssue(
                    record_key=page_id,
                    field_name="dayStay",
                    error_code="DURATION_DISCREPANCY",
                    severity="WARNING",
                    raw_value=f"dayStay={rec.get('dayStay')}, text={rec.get('dayStayText')}",
                    message=disc
                ))

            # Departure location
            dep_name = rec.get("departureName")
            std_dep, _, _ = normalize_location_name(dep_name)

            # Destination locations
            dest_json = rec.get("listDestination")
            dest_candidates = []
            if dest_json:
                try:
                    d_parsed = json.loads(dest_json)
                    dest_candidates = clean_destination_candidates(d_parsed)
                except Exception:
                    dest_candidates = clean_destination_candidates(str(dest_json))

            tour = StandardizedTour(
                source_record_key=page_id,
                name=title,
                description=None,  # Vietravel raw data has no long description in current sheet
                duration_days=days,
                duration_nights=nights,
                departure_location_name=std_dep,
                destinations=dest_candidates,
                raw_payload=rec,
                file_name=excel_file.name,
                line_number=rec.get("__line_number__", 0)
            )
            bundle.tours.append(tour)

            # Store unmapped fields into staging
            unmapped_payload = {
                "endDate": rec.get("endDate"),
                "transportName": rec.get("transportName"),
                "transportType": rec.get("transportType"),
                "tourLineName": rec.get("tourLineName"),
                "promotionInfor": rec.get("promotionInfor"),
                "score": rec.get("score"),
                "rating": rec.get("rating"),
                "ratingText": rec.get("ratingText"),
                "rateCount": rec.get("rateCount"),
                "esgScore": rec.get("esgScore"),
                "leiScore": rec.get("leiScore"),
                "imgUrl": rec.get("imgUrl"),
                "hotel": rec.get("hotel"),
                "meetingPlace": rec.get("meetingPlace"),
            }
            bundle.unmapped_items.append(UnmappedData(
                source_record_key=page_id,
                data_kind="vietravel_extended_attributes",
                payload=unmapped_payload
            ))

            # 4. Expand listDepartureDate[].tours[]
            ldd_raw = rec.get("listDepartureDate")
            nested_tours_for_page = []
            if ldd_raw:
                try:
                    ldd_data = json.loads(ldd_raw)
                    if isinstance(ldd_data, list):
                        for date_group in ldd_data:
                            tours_list = date_group.get("tours", [])
                            for t_item in tours_list:
                                tid = str(t_item.get("tourId") or "").strip()
                                if tid:
                                    nested_tours_for_page.append(t_item)
                except Exception as e:
                    bundle.issues.append(EtlIssue(
                        record_key=page_id,
                        field_name="listDepartureDate",
                        error_code="CORRUPT_JSON",
                        severity="ERROR",
                        raw_value=str(ldd_raw)[:100],
                        message=f"Failed to parse listDepartureDate JSON: {e}"
                    ))

            # Check outer tourId vs nested tours
            outer_tour_id = normalize_id(rec.get("tourId"))
            nested_ids_set = {normalize_id(t.get("tourId")) for t in nested_tours_for_page}

            if outer_tour_id and outer_tour_id not in nested_ids_set:
                outer_mismatches_count += 1
                bundle.issues.append(EtlIssue(
                    record_key=page_id,
                    field_name="tourId",
                    error_code="OUTER_TOUR_ID_NOT_IN_NESTED",
                    severity="WARNING",
                    raw_value=outer_tour_id,
                    message=f"Outer tourId '{outer_tour_id}' not found in nested listDepartureDate[].tours[]"
                ))

            # Add nested departures & prices
            observed_at = parse_datetime(rec.get("crawl_time"))

            for t_item in nested_tours_for_page:
                tid = normalize_id(t_item.get("tourId"))
                if tid in nested_tour_ids_seen:
                    # Rare case: same tourId in multiple places
                    continue
                nested_tour_ids_seen.add(tid)

                dep_date = parse_datetime(t_item.get("departureDate"))
                sale_price = parse_decimal(t_item.get("salePrice"))

                bundle.departures.append(StandardizedDeparture(
                    tour_source_key=page_id,
                    source_departure_key=tid,
                    departure_at=dep_date,
                    departure_location_name=std_dep,
                    raw_payload=t_item
                ))

                if sale_price is not None:
                    bundle.prices.append(StandardizedPrice(
                        tour_source_key=page_id,
                        source_departure_key=tid,
                        list_price=None,
                        sale_price=sale_price,
                        discount_percent=None,
                        discount_amount=None,
                        currency="VND",
                        observed_at=observed_at,
                        raw_payload=t_item
                    ))

        bundle.metrics["outer_mismatches_count"] = outer_mismatches_count
        bundle.metrics["nested_departures_count"] = len(bundle.departures)
        bundle.metrics["unique_nested_tour_ids"] = len(nested_tour_ids_seen)
        bundle.metrics["tours_count"] = len(bundle.tours)
        bundle.metrics["prices_count"] = len(bundle.prices)
        observed = [parse_datetime(r.get("crawl_time")) for r in deduped_records if parse_datetime(r.get("crawl_time"))]
        bundle.source_observed_at = max(observed) if observed else None

        return bundle
