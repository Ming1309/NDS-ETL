-- PostgreSQL migration: Add UNIQUE constraints for idempotent ETL Upserts
SET search_path TO travel, public;

-- 1. SourceSystem: unique name
ALTER TABLE travel.source_system
    ADD CONSTRAINT uq_source_system_name UNIQUE (name);

-- 2. Category: unique name
ALTER TABLE travel.category
    ADD CONSTRAINT uq_category_name UNIQUE (name);

-- 3. SourceEntity: unique record per source system and category
ALTER TABLE travel.source_entity
    ADD CONSTRAINT uq_source_entity_key UNIQUE (source_system_id, category_id, source_record_key);

-- 4. TourDeparture: unique departure per tour and source departure key
ALTER TABLE travel.tour_departure
    ADD CONSTRAINT uq_tour_departure_key UNIQUE (tour_source_entity_id, source_departure_key);

-- 5. Review: unique review per entity and source review key
ALTER TABLE travel.review
    ADD CONSTRAINT uq_review_key UNIQUE (source_entity_id, source_review_key);

-- 6. Itinerary: unique itinerary per tour and name
ALTER TABLE travel.itinerary
    ADD CONSTRAINT uq_itinerary_tour_name UNIQUE (tour_source_entity_id, name);

-- 7. ItineraryItem: unique sequence per itinerary
ALTER TABLE travel.itinerary_item
    ADD CONSTRAINT uq_itinerary_item_seq UNIQUE (itinerary_id, sequence_no);

-- 8. TourDeparturePrice: unique price per departure, observed timestamp, and currency
ALTER TABLE travel.tour_departure_price
    ADD CONSTRAINT uq_departure_price_obs UNIQUE (tour_departure_id, observed_at, currency);

-- 9. Location unique index on name and location_type and parent_location_id
CREATE UNIQUE INDEX IF NOT EXISTS uq_location_name_type_parent
    ON travel.location (name, COALESCE(location_type, ''), COALESCE(parent_location_id, 0));
