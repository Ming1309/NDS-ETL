import argparse
import logging
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import List

from etl.adapters import ADAPTERS, BaseSourceAdapter, SourceBundle
from etl.config import DEFAULT_DATA_DIR, DATABASE_URL
from etl.db import get_db_session, check_db_connection
from etl.migrations.runner import run_migrations
from etl.loader.staging_loader import StagingLoader
from etl.loader.nds_loader import NdsLoader
from etl.loader.reconciler import Reconciler
from sqlalchemy import text

logger = logging.getLogger("etl")

def get_target_sources(source_arg: str) -> List[str]:
    src = source_arg.lower().strip()
    if src == "all":
        return ["bestprice", "vietravel", "pystravel"]
    if src in ADAPTERS:
        return [src]
    raise ValueError(f"Unknown source: '{source_arg}'. Allowed sources: {list(ADAPTERS.keys()) + ['all']}")

def handle_profile(args) -> int:
    data_dir = args.data_dir
    sources = get_target_sources(args.source)

    print("\n" + "=" * 78)
    print("                      NDS-ETL SOURCE PROFILING REPORT")
    print("=" * 78)
    print(f" Data Directory: {data_dir}")
    print(f" Target Sources: {', '.join(sources)}")
    print("-" * 78)

    for src_name in sources:
        adapter_cls = ADAPTERS[src_name]
        adapter: BaseSourceAdapter = adapter_cls()
        print(f"\n Profiling [{adapter.source_name}]...")
        try:
            bundle = adapter.extract_and_transform(data_dir)
            print(f"  * Files & Checksums:")
            for fname, fhash in bundle.file_hashes.items():
                print(f"    - {fname}: {fhash[:16]}...")
            print(f"  * Extracted Business Entities:")
            print(f"    - Tours:        {len(bundle.tours)}")
            print(f"    - Departures:   {len(bundle.departures)}")
            print(f"    - Prices:       {len(bundle.prices)}")
            print(f"    - Itineraries:  {len(bundle.itineraries)}")
            print(f"    - Reviews:      {len(bundle.reviews)}")
            print(f"  * Staging & Audit:")
            print(f"    - Unmapped data items: {len(bundle.unmapped_items)}")
            print(f"    - Validation issues:   {len(bundle.issues)}")
            if bundle.issues:
                print(f"    - Sample issues:")
                for iss in bundle.issues[:5]:
                    print(f"      [{iss.severity}] {iss.error_code}: {iss.message} (key={iss.record_key})")
            print(f"  * Source Metrics: {bundle.metrics}")
        except Exception as e:
            print(f"  [ERROR] Profiling failed for {src_name}: {e}")
            logger.exception(e)
            return 1

    print("\n" + "=" * 78)
    print(" Profiling complete. No database changes were made.")
    print("=" * 78 + "\n")
    return 0

def handle_run(args) -> int:
    data_dir = args.data_dir
    sources = get_target_sources(args.source)
    dry_run = args.dry_run

    reconciler = Reconciler()
    bundles: List[SourceBundle] = []
    load_counts = {}

    # If dry-run: simulate extraction & load without DB
    if dry_run:
        logger.info(f"Starting DRY-RUN for sources: {sources}")
        for src_name in sources:
            adapter_cls = ADAPTERS[src_name]
            adapter: BaseSourceAdapter = adapter_cls()
            bundle = adapter.extract_and_transform(data_dir)
            bundles.append(bundle)

            loader = NdsLoader(session=None, dry_run=True)
            counts = loader.load_bundle(bundle)
            load_counts[bundle.source_name] = counts

        report = reconciler.reconcile_run(bundles, load_counts, dry_run=True)
        reconciler.print_terminal_summary(report)
        return 0

    # Production run: Requires DB connection
    logger.info("Checking database connection...")
    if not check_db_connection():
        logger.error(f"Cannot connect to database at {DATABASE_URL}. "
                     "Please ensure PostgreSQL container is running or use --dry-run.")
        return 1

    # Run safe migrations
    logger.info("Executing safe migrations and checking duplicate constraints...")
    try:
        run_migrations()
    except Exception as e:
        logger.error(f"Migration pre-check or execution failed: {e}")
        return 1

    overall_success = True
    for src_name in sources:
        adapter_cls = ADAPTERS[src_name]
        adapter: BaseSourceAdapter = adapter_cls()
        logger.info(f"Processing source: {adapter.source_name}")

        run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{src_name}_{uuid.uuid4().hex[:6]}"
        try:
            # Persist the run before extraction; failures remain auditable.
            with get_db_session() as session:
                staging_loader = StagingLoader(session=session, dry_run=False)
                staging_loader.start_run(run_id, adapter.source_name)

            bundle = adapter.extract_and_transform(data_dir)
            bundles.append(bundle)

            # Raw payload, issues and staging-only values are durable before NDS.
            with get_db_session() as session:
                staging_loader = StagingLoader(session=session, dry_run=False)
                staging_loader.load_bundle_staging(run_id, bundle)

            # NDS and COMPLETED state are one atomic transaction.
            with get_db_session() as session:
                session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:source))"), {"source": adapter.source_name})
                staging_loader = StagingLoader(session=session, dry_run=False)
                nds_loader = NdsLoader(session=session, staging_loader=staging_loader, dry_run=False)
                counts = nds_loader.load_bundle(bundle)
                staging_loader.complete_run(run_id, status="COMPLETED", metrics=bundle.metrics)
                counts.update({"committed": True, "status": "COMPLETED", "run_id": run_id})
                load_counts[adapter.source_name] = counts

            logger.info(f"Source {adapter.source_name} loaded successfully: {counts}")
        except Exception as e:
            logger.exception(f"Error loading source {adapter.source_name}: {e}")
            overall_success = False
            # Record failed status in a separate short session if possible
            try:
                with get_db_session() as fail_session:
                    stg = StagingLoader(session=fail_session)
                    # Extraction can fail before a bundle exists; create the run
                    # in that case so the operator still has an audit record.
                    stg.start_run(run_id, adapter.source_name)
                    stg.complete_run(run_id, status="FAILED", error_message=str(e))
                load_counts[adapter.source_name] = {"committed": False, "status": "FAILED", "run_id": run_id}
            except Exception:
                pass

    report = reconciler.reconcile_run(bundles, load_counts, dry_run=False)
    reconciler.print_terminal_summary(report)

    return 0 if overall_success else 1

def handle_reset(args) -> int:
    if args.dry_run:
        print(f"[DRY-RUN] Would reset ETL data for: {', '.join(get_target_sources(args.source))}")
        return 0
    # Reset may be the first command after a deployment, so ensure its staging
    # tables exist before attempting a source-scoped delete.
    run_migrations()
    sources = [ADAPTERS[name]().source_name for name in get_target_sources(args.source)]
    with get_db_session() as session:
        for source in sources:
            session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:source))"), {"source": source})
            # Deletes are deliberately scoped to the selected source's entities.
            params = {"source": source}
            statements = [
                """
                DELETE FROM travel.tour_departure_price p USING travel.tour_departure d, travel.source_entity e, travel.source_system s
                WHERE p.tour_departure_id=d.tour_departure_id AND d.tour_source_entity_id=e.source_entity_id
                  AND e.source_system_id=s.source_system_id AND s.name=:source
                """,
                """
                DELETE FROM travel.itinerary_stop st USING travel.itinerary_item i, travel.itinerary it, travel.source_entity e, travel.source_system s
                WHERE st.itinerary_item_id=i.itinerary_item_id AND i.itinerary_id=it.itinerary_id
                  AND it.tour_source_entity_id=e.source_entity_id AND e.source_system_id=s.source_system_id AND s.name=:source
                """,
                """
                DELETE FROM travel.itinerary_item i USING travel.itinerary it, travel.source_entity e, travel.source_system s
                WHERE i.itinerary_id=it.itinerary_id AND it.tour_source_entity_id=e.source_entity_id AND e.source_system_id=s.source_system_id AND s.name=:source
                """,
                """
                DELETE FROM travel.itinerary it USING travel.source_entity e, travel.source_system s
                WHERE it.tour_source_entity_id=e.source_entity_id AND e.source_system_id=s.source_system_id AND s.name=:source
                """,
                "DELETE FROM travel.review r USING travel.source_entity e, travel.source_system s WHERE r.source_entity_id=e.source_entity_id AND e.source_system_id=s.source_system_id AND s.name=:source",
                "DELETE FROM travel.tour_departure d USING travel.source_entity e, travel.source_system s WHERE d.tour_source_entity_id=e.source_entity_id AND e.source_system_id=s.source_system_id AND s.name=:source",
                "DELETE FROM travel.tour_destination td USING travel.source_entity e, travel.source_system s WHERE td.tour_source_entity_id=e.source_entity_id AND e.source_system_id=s.source_system_id AND s.name=:source",
                "DELETE FROM travel.tour t USING travel.source_entity e, travel.source_system s WHERE t.source_entity_id=e.source_entity_id AND e.source_system_id=s.source_system_id AND s.name=:source",
                "DELETE FROM travel.source_entity e USING travel.source_system s WHERE e.source_system_id=s.source_system_id AND s.name=:source",
                "DELETE FROM staging.mapping WHERE source_name=:source",
                "DELETE FROM staging.entity_state WHERE source_name=:source",
                "DELETE FROM staging.etl_run WHERE source_name=:source",
                "DELETE FROM staging.snapshot WHERE source_name=:source",
            ]
            for statement in statements:
                session.execute(text(statement), params)
    print(f"Reset completed for: {', '.join(sources)}")
    return 0

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m etl",
        description="NDS-ETL: Multi-source Travel ETL into PostgreSQL Normalized Data Store (3NF)"
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="Subcommands: profile, run")

    # Subcommand: profile
    profile_parser = subparsers.add_parser("profile", help="Analyze and profile source data without database writes")
    profile_parser.add_argument(
        "--source",
        default="all",
        choices=["bestprice", "vietravel", "pystravel", "all"],
        help="Source system to profile (default: all)"
    )
    profile_parser.add_argument(
        "--data-dir",
        default=str(DEFAULT_DATA_DIR),
        help=f"Path to raw data directory (default: {DEFAULT_DATA_DIR})"
    )

    # Subcommand: run
    run_parser = subparsers.add_parser("run", help="Run ETL pipeline into Staging and NDS database")
    run_parser.add_argument(
        "--source",
        default="all",
        choices=["bestprice", "vietravel", "pystravel", "all"],
        help="Source system to process (default: all)"
    )
    reset_parser = subparsers.add_parser("reset", help="Delete ETL data for selected sources")
    reset_parser.add_argument("--source", default="all", choices=["bestprice", "vietravel", "pystravel", "all"])
    reset_parser.add_argument("--dry-run", action="store_true")
    run_parser.add_argument(
        "--data-dir",
        default=str(DEFAULT_DATA_DIR),
        help=f"Path to raw data directory (default: {DEFAULT_DATA_DIR})"
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate execution without committing database writes"
    )

    return parser

def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S"
    )
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "profile":
        return handle_profile(args)
    elif args.command == "run":
        return handle_run(args)
    elif args.command == "reset":
        return handle_reset(args)
    else:
        parser.print_help()
        return 1

if __name__ == "__main__":
    sys.exit(main())
