import hashlib
import logging
import re
from decimal import Decimal
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

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
from etl.extractors.json_extractor import read_json_records
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

def parse_pystravel_duration(dur_str: Optional[str], dur_iso: Optional[str]) -> Tuple[Optional[int], Optional[int]]:
    """
    Parse days and nights from duration and duration_iso.
    Never subtract nights by default.
    """
    days = None
    nights = None

    if dur_str:
        m_days = re.search(r'(\d+)\s*(?:ngày|N)', dur_str, re.IGNORECASE)
        if m_days:
            days = int(m_days.group(1))
        m_nights = re.search(r'(\d+)\s*(?:đêm|D|Đ)', dur_str, re.IGNORECASE)
        if m_nights:
            nights = int(m_nights.group(1))

    if days is None and dur_iso:
        # e.g. 'P8D'
        m_iso = re.search(r'P(\d+)D', dur_iso, re.IGNORECASE)
        if m_iso:
            days = int(m_iso.group(1))

    return days, nights

class PystravelAdapter(BaseSourceAdapter):
    @property
    def source_name(self) -> str:
        return "Pystravel"

    def extract_and_transform(self, data_dir: str) -> SourceBundle:
        base_path = Path(data_dir) / "Pystravel"
        bundle = SourceBundle(source_name=self.source_name)

        json_file = base_path / "all_tours_data.json"
        if not json_file.exists():
            raise FileNotFoundError(f"Pystravel file not found: {json_file}")

        bundle.file_hashes[json_file.name] = compute_file_hash(json_file)

        raw_records = read_json_records(json_file)
        bundle.raw_records.extend(
            RawInput(json_file.name, rec, rec["__line_number__"], source_entity_key=str(rec.get("tour_id") or "") or None)
            for rec in raw_records
        )
        bundle.metrics["total_raw_records"] = len(raw_records)

        # 1. Deduplicate by tour_id (handling the 4 duplicate pairs)
        tours_by_id: Dict[str, List[Dict[str, Any]]] = {}
        for rec in raw_records:
            tid = str(rec.get("tour_id") or "").strip()
            if not tid:
                bundle.issues.append(EtlIssue(
                    record_key=None,
                    field_name="tour_id",
                    error_code="MISSING_TOUR_ID",
                    severity="QUARANTINE",
                    raw_value=str(rec)[:100],
                    message="Pystravel record missing tour_id"
                ))
                continue
            tours_by_id.setdefault(tid, []).append(rec)

        merged_tour_count = sum(1 for recs in tours_by_id.values() if len(recs) > 1)
        bundle.metrics["duplicate_tour_groups_merged"] = merged_tour_count
        bundle.metrics["unique_tour_ids_count"] = len(tours_by_id)

        # 2. Process each unique tour
        departure_keys_seen = set()

        for tid, rec_list in tours_by_id.items():
            primary_rec = rec_list[0]

            # If duplicated, save secondary variants to staging
            if len(rec_list) > 1:
                for sec in rec_list[1:]:
                    bundle.unmapped_items.append(UnmappedData(
                        source_record_key=tid,
                        data_kind="duplicate_variant_url",
                        payload={"url": sec.get("url"), "slug": sec.get("slug"), "title": sec.get("title")}
                    ))

            title = clean_text(primary_rec.get("title"), preserve_newlines=False)
            desc = clean_text(primary_rec.get("short_description") or primary_rec.get("detailed_description"), preserve_newlines=True)

            # Duration
            days, nights = parse_pystravel_duration(primary_rec.get("duration"), primary_rec.get("duration_iso"))

            # Locations
            start_loc = primary_rec.get("start_location")
            std_dep, _, _ = normalize_location_name(start_loc)

            dest_addr = primary_rec.get("destination_address")
            dest_candidates = clean_destination_candidates(dest_addr)

            tour = StandardizedTour(
                source_record_key=tid,
                name=title or f"Tour Pystravel {tid}",
                description=desc,
                duration_days=days,
                duration_nights=nights,
                departure_location_name=std_dep,
                destinations=dest_candidates,
                raw_payload=primary_rec,
                file_name=json_file.name,
                line_number=primary_rec.get("__line_number__", 0)
            )
            bundle.tours.append(tour)

            # Staging: Product-level price, policies, terms, aggregate rating
            unmapped_payload = {
                "product_price": primary_rec.get("price"),
                "currency": primary_rec.get("currency", "VND"),
                "price_valid_until": primary_rec.get("price_valid_until"),
                "badge": primary_rec.get("badge"),
                "booked_count": primary_rec.get("booked_count"),
                "terms_and_policies": primary_rec.get("terms_and_policies"),
                "gallery_images": primary_rec.get("gallery_images"),
                "image": primary_rec.get("image"),
            }
            # Add aggregate rating if present
            rar = primary_rec.get("rating_and_reviews")
            if isinstance(rar, dict):
                if "score" in rar:
                    unmapped_payload["aggregate_score"] = rar.get("score")
                if "scale" in rar:
                    unmapped_payload["aggregate_scale"] = rar.get("scale")

            bundle.unmapped_items.append(UnmappedData(
                source_record_key=tid,
                data_kind="pystravel_product_attributes",
                payload=unmapped_payload
            ))

            # 3. Itinerary
            itin_list = primary_rec.get("itinerary")
            if itin_list and isinstance(itin_list, list):
                itin_items = []
                for seq_no, it in enumerate(itin_list, start=1):
                    it_title = clean_text(it.get("title"), preserve_newlines=False)
                    it_desc = clean_text(it.get("details"), preserve_newlines=True)

                    # Extract day number
                    day_str = it.get("day", "")
                    m_day = re.search(r'(\d+)', day_str)
                    day_num = int(m_day.group(1)) if m_day else seq_no

                    itin_items.append(StandardizedItineraryItem(
                        sequence_no=seq_no,
                        day_start=day_num,
                        day_end=day_num,
                        title=it_title,
                        description=it_desc,
                        stops=[]
                    ))

                    # Save meals / activities to staging
                    if it.get("meals") or it.get("activities"):
                        bundle.unmapped_items.append(UnmappedData(
                            source_record_key=tid,
                            data_kind=f"itinerary_item_details_day_{day_num}",
                            payload={"meals": it.get("meals"), "activities": it.get("activities"), "route": it.get("route")}
                        ))

                if itin_items:
                    bundle.itineraries.append(StandardizedItinerary(
                        tour_source_key=tid,
                        name="source_itinerary",
                        items=itin_items
                    ))

            # 4. Departure dates
            # Merge departure dates across duplicate records if any
            all_dep_dates = set()
            for r in rec_list:
                dates = r.get("departure_dates")
                if dates and isinstance(dates, list):
                    for d in dates:
                        if isinstance(d, str):
                            d_clean = d.strip()
                            # Check valid DD/MM/YYYY format
                            if re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', d_clean):
                                all_dep_dates.add(d_clean)
                            else:
                                bundle.unmapped_items.append(UnmappedData(
                                    source_record_key=tid,
                                    data_kind="invalid_departure_date",
                                    payload={"raw_date": d}
                                ))

            for d_clean in sorted(all_dep_dates):
                dep_dt = parse_datetime(d_clean)
                if not dep_dt:
                    continue
                d_key = f"dep_{tid}_{dep_dt.strftime('%Y%m%d')}"
                if (tid, d_key) not in departure_keys_seen:
                    departure_keys_seen.add((tid, d_key))
                    bundle.departures.append(StandardizedDeparture(
                        tour_source_key=tid,
                        source_departure_key=d_key,
                        departure_at=dep_dt,
                        departure_location_name=std_dep,
                        raw_payload={"date_str": d_clean}
                    ))
                    # NOTE: As per requirements, product-level price is NOT broadcast to departures.

            # 5. Individual Reviews
            all_reviews = []
            for r in rec_list:
                rar_item = r.get("rating_and_reviews")
                if isinstance(rar_item, dict):
                    revs = rar_item.get("reviews")
                    if revs and isinstance(revs, list):
                        for ind_rev in revs:
                            if isinstance(ind_rev, dict):
                                all_reviews.append(ind_rev)

            seen_rev_hashes = set()
            for rev in all_reviews:
                author = clean_text(rev.get("author"), preserve_newlines=False) or "Khách hàng"
                comment = clean_text(rev.get("comment"), preserve_newlines=True)
                if not comment:
                    continue

                # Hash key from tour_id, author, comment
                rev_hash = hashlib.sha256(f"{tid}:{author}:{comment}".encode()).hexdigest()[:16]
                if rev_hash in seen_rev_hashes:
                    continue
                seen_rev_hashes.add(rev_hash)

                bundle.reviews.append(StandardizedReview(
                    tour_source_key=tid,
                    source_review_key=f"rev_{rev_hash}",
                    reviewer_display_name=author,
                    title=None,
                    content=comment,
                    rating_value=None,  # Do not assign aggregate score to individual reviews
                    rating_scale=None,
                    reviewed_at=None,
                    raw_payload=rev
                ))

        bundle.metrics["tours_count"] = len(bundle.tours)
        bundle.metrics["departures_count"] = len(bundle.departures)
        bundle.metrics["reviews_count"] = len(bundle.reviews)

        return bundle
