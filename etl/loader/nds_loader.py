import logging
import hashlib
import json
from datetime import datetime
from typing import Dict, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text

from etl.adapters.base import SourceBundle
from etl.loader.staging_loader import StagingLoader
from etl.models.travel import (
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
from etl.models.staging import EntityState, Snapshot

logger = logging.getLogger(__name__)

class NdsLoader:
    def __init__(self, session: Session, staging_loader: Optional[StagingLoader] = None, dry_run: bool = False):
        self.session = session
        self.staging_loader = staging_loader
        self.dry_run = dry_run
        self._location_cache: Dict[Tuple[str, Optional[str]], int] = {}
        self._is_postgres = False
        if session and session.bind:
            self._is_postgres = session.bind.dialect.name == "postgresql"

    def _is_stale_tour(self, bundle: SourceBundle, tour) -> bool:
        """Reject an older source observation without relying on run order."""
        if not self._is_postgres:
            return False
        state = self.session.query(EntityState).filter_by(
            source_name=bundle.source_name, entity_type="tour", source_key=tour.source_record_key
        ).first()
        if not state:
            return False
        if bundle.source_observed_at and state.source_observed_at:
            return bundle.source_observed_at < state.source_observed_at
        # Pystravel has no source timestamp: retain the first received snapshot,
        # except when a transformer version explicitly requests reprocessing.
        candidate = self.session.query(Snapshot).filter_by(
            source_name=bundle.source_name, file_path=tour.file_name, file_hash=bundle.file_hashes.get(tour.file_name)
        ).first()
        return bool(candidate and state.snapshot_id != candidate.snapshot_id and state.transformer_version == bundle.transformer_version)

    def _record_tour_state(self, bundle: SourceBundle, tour) -> None:
        if not self._is_postgres:
            return
        payload_hash = hashlib.sha256(json.dumps(tour.raw_payload, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()
        snapshot = self.session.query(Snapshot).filter_by(
            source_name=bundle.source_name, file_path=tour.file_name, file_hash=bundle.file_hashes.get(tour.file_name)
        ).first()
        state = self.session.query(EntityState).filter_by(
            source_name=bundle.source_name, entity_type="tour", source_key=tour.source_record_key
        ).first()
        values = dict(snapshot_id=snapshot.snapshot_id if snapshot else None, source_observed_at=bundle.source_observed_at,
                      transformer_version=bundle.transformer_version, payload_hash=payload_hash, applied_at=datetime.now().astimezone())
        if state:
            for key, value in values.items():
                setattr(state, key, value)
        else:
            self.session.add(EntityState(source_name=bundle.source_name, entity_type="tour", source_key=tour.source_record_key, **values))

    def _get_or_create_source_system(self, name: str) -> int:
        sys = self.session.query(SourceSystem).filter_by(name=name).first()
        if not sys:
            sys = SourceSystem(name=name)
            self.session.add(sys)
            self.session.flush()
        return sys.source_system_id

    def _get_or_create_category(self, name: str) -> int:
        cat = self.session.query(Category).filter_by(name=name).first()
        if not cat:
            cat = Category(name=name)
            self.session.add(cat)
            self.session.flush()
        return cat.category_id

    def _get_or_create_location(self, name: str, location_type: Optional[str] = None, parent_id: Optional[int] = None) -> int:
        if not name:
            return None
        cache_key = (name.strip().lower(), location_type)
        if cache_key in self._location_cache:
            return self._location_cache[cache_key]

        loc = self.session.query(Location).filter(
            Location.name == name
        ).first()

        if not loc:
            loc = Location(name=name, location_type=location_type, parent_location_id=parent_id)
            self.session.add(loc)
            self.session.flush()

        self._location_cache[cache_key] = loc.location_id
        return loc.location_id

    def load_bundle(self, bundle: SourceBundle) -> Dict[str, int]:
        """
        Idempotently loads bundle into travel schema in FK dependency order.
        Returns counts of loaded records.
        """
        counts = {
            "tours": 0,
            "departures": 0,
            "prices": 0,
            "itineraries": 0,
            "itinerary_items": 0,
            "reviews": 0,
            "stale": 0,
        }

        if self.dry_run:
            logger.info(f"[DRY-RUN] Simulating NDS load for {bundle.source_name}: "
                        f"{len(bundle.tours)} tours, {len(bundle.departures)} departures, "
                        f"{len(bundle.prices)} prices, {len(bundle.reviews)} reviews.")
            return {
                "tours": len(bundle.tours),
                "departures": len(bundle.departures),
                "prices": len(bundle.prices),
                "itineraries": len(bundle.itineraries),
                "itinerary_items": sum(len(it.items) for it in bundle.itineraries),
                "reviews": len(bundle.reviews),
            }

        source_system_id = self._get_or_create_source_system(bundle.source_name)
        category_id = self._get_or_create_category("Tour")

        # 1. Upsert SourceEntity & Tour
        tour_id_map: Dict[str, int] = {}  # source_record_key -> source_entity_id

        for t in bundle.tours:
            if self._is_stale_tour(bundle, t):
                logger.info("Skipping stale %s tour %s", bundle.source_name, t.source_record_key)
                counts["stale"] += 1
                continue
            entity = self.session.query(SourceEntity).filter_by(
                source_system_id=source_system_id,
                category_id=category_id,
                source_record_key=t.source_record_key
            ).first()

            if not entity:
                entity = SourceEntity(
                    source_system_id=source_system_id,
                    category_id=category_id,
                    source_record_key=t.source_record_key,
                    name=t.name,
                    description=t.description
                )
                self.session.add(entity)
                self.session.flush()
            else:
                entity.name = t.name
                entity.description = t.description
                self.session.flush()

            eid = entity.source_entity_id
            tour_id_map[t.source_record_key] = eid

            if self.staging_loader:
                self.staging_loader.record_mapping(bundle.source_name, "tour", t.source_record_key, eid)

            # Upsert Tour child
            tour_rec = self.session.query(Tour).filter_by(source_entity_id=eid).first()
            if not tour_rec:
                tour_rec = Tour(
                    source_entity_id=eid,
                    duration_days=t.duration_days,
                    duration_nights=t.duration_nights
                )
                self.session.add(tour_rec)
            else:
                tour_rec.duration_days = t.duration_days
                tour_rec.duration_nights = t.duration_nights
            self.session.flush()
            counts["tours"] += 1
            self._record_tour_state(bundle, t)

            # A complete destination list is authoritative for this tour.  Do not
            # remove old relations for absent/invalid source sections.
            if t.destinations_state == "complete":
                self.session.query(TourDestination).filter_by(tour_source_entity_id=eid).delete()
            for dest_name in t.destinations:
                loc_id = self._get_or_create_location(dest_name, "Destination")
                if loc_id:
                    # check junction
                    td = self.session.query(TourDestination).filter_by(
                        tour_source_entity_id=eid,
                        location_id=loc_id
                    ).first()
                    if not td:
                        td = TourDestination(tour_source_entity_id=eid, location_id=loc_id)
                        self.session.add(td)
            self.session.flush()

        # 2. Upsert Departures
        departure_id_map: Dict[Tuple[str, str], int] = {}  # (tour_key, dep_key) -> tour_departure_id

        for dep in bundle.departures:
            tour_eid = tour_id_map.get(dep.tour_source_key)
            if not tour_eid:
                continue

            dep_loc_id = None
            if dep.departure_location_name:
                dep_loc_id = self._get_or_create_location(dep.departure_location_name, "Province")

            dep_rec = self.session.query(TourDeparture).filter_by(
                tour_source_entity_id=tour_eid,
                source_departure_key=dep.source_departure_key
            ).first()

            if not dep_rec:
                dep_rec = TourDeparture(
                    tour_source_entity_id=tour_eid,
                    departure_location_id=dep_loc_id,
                    source_departure_key=dep.source_departure_key,
                    departure_at=dep.departure_at
                )
                self.session.add(dep_rec)
                self.session.flush()
            else:
                dep_rec.departure_at = dep.departure_at
                if dep_loc_id:
                    dep_rec.departure_location_id = dep_loc_id
                self.session.flush()

            departure_id_map[(dep.tour_source_key, dep.source_departure_key)] = dep_rec.tour_departure_id
            if self.staging_loader:
                self.staging_loader.record_mapping(
                    bundle.source_name, "departure",
                    f"{dep.tour_source_key}:{dep.source_departure_key}",
                    dep_rec.tour_departure_id
                )
            counts["departures"] += 1

        # 3. Upsert Prices
        for pr in bundle.prices:
            dep_id = departure_id_map.get((pr.tour_source_key, pr.source_departure_key))
            if not dep_id:
                continue

            price_rec = self.session.query(TourDeparturePrice).filter_by(
                tour_departure_id=dep_id,
                observed_at=pr.observed_at,
                currency=pr.currency
            ).first()

            if not price_rec:
                price_rec = TourDeparturePrice(
                    tour_departure_id=dep_id,
                    list_price=pr.list_price,
                    sale_price=pr.sale_price,
                    discount_percent=pr.discount_percent,
                    discount_amount=pr.discount_amount,
                    currency=pr.currency,
                    observed_at=pr.observed_at
                )
                self.session.add(price_rec)
            else:
                price_rec.list_price = pr.list_price
                price_rec.sale_price = pr.sale_price
                price_rec.discount_percent = pr.discount_percent
                price_rec.discount_amount = pr.discount_amount
            self.session.flush()
            counts["prices"] += 1

        # 4. Upsert Itineraries & Items
        for itin in bundle.itineraries:
            tour_eid = tour_id_map.get(itin.tour_source_key)
            if not tour_eid:
                continue

            itin_rec = self.session.query(Itinerary).filter_by(
                tour_source_entity_id=tour_eid,
                name=itin.name
            ).first()

            if not itin_rec:
                itin_rec = Itinerary(
                    tour_source_entity_id=tour_eid,
                    name=itin.name
                )
                self.session.add(itin_rec)
                self.session.flush()

            counts["itineraries"] += 1

            for it_item in itin.items:
                item_rec = self.session.query(ItineraryItem).filter_by(
                    itinerary_id=itin_rec.itinerary_id,
                    sequence_no=it_item.sequence_no
                ).first()

                if not item_rec:
                    item_rec = ItineraryItem(
                        itinerary_id=itin_rec.itinerary_id,
                        sequence_no=it_item.sequence_no,
                        day_start=it_item.day_start,
                        day_end=it_item.day_end,
                        title=it_item.title,
                        description=it_item.description
                    )
                    self.session.add(item_rec)
                else:
                    item_rec.day_start = it_item.day_start
                    item_rec.day_end = it_item.day_end
                    item_rec.title = it_item.title
                    item_rec.description = it_item.description
                self.session.flush()
                counts["itinerary_items"] += 1

            # The source supplied a complete itinerary: remove obsolete items and
            # their dependent stops after the current sequence has been upserted.
            if itin.sync_state == "complete":
                current_sequences = [item.sequence_no for item in itin.items]
                stale_items = self.session.query(ItineraryItem).filter(
                    ItineraryItem.itinerary_id == itin_rec.itinerary_id,
                    ~ItineraryItem.sequence_no.in_(current_sequences or [-1])
                ).all()
                for stale_item in stale_items:
                    self.session.query(ItineraryStop).filter_by(itinerary_item_id=stale_item.itinerary_item_id).delete()
                    self.session.delete(stale_item)
                self.session.flush()

        # 5. Upsert Reviews
        for rev in bundle.reviews:
            tour_eid = tour_id_map.get(rev.tour_source_key)
            if not tour_eid:
                continue

            rev_rec = self.session.query(Review).filter_by(
                source_entity_id=tour_eid,
                source_review_key=rev.source_review_key
            ).first()

            if not rev_rec:
                rev_rec = Review(
                    source_entity_id=tour_eid,
                    source_review_key=rev.source_review_key,
                    reviewer_display_name=rev.reviewer_display_name,
                    title=rev.title,
                    content=rev.content,
                    rating_value=rev.rating_value,
                    rating_scale=rev.rating_scale,
                    reviewed_at=rev.reviewed_at
                )
                self.session.add(rev_rec)
            else:
                rev_rec.reviewer_display_name = rev.reviewer_display_name
                rev_rec.title = rev.title
                rev_rec.content = rev.content
                rev_rec.rating_value = rev.rating_value
                rev_rec.rating_scale = rev.rating_scale
                rev_rec.reviewed_at = rev.reviewed_at
            self.session.flush()
            counts["reviews"] += 1

        return counts
