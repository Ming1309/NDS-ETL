#!/usr/bin/env python3
"""
Export PostgreSQL tables from NDS database (travel & staging schemas) to CSV.

Usage:
    python scripts/export_to_csv.py
    python scripts/export_to_csv.py --schema travel
    python scripts/export_to_csv.py --schema staging
    python scripts/export_to_csv.py --schema all
    python scripts/export_to_csv.py --table tour
    python scripts/export_to_csv.py --output-dir exports/my_data
"""

import os
import sys
import csv
import time
import argparse
from pathlib import Path
from typing import List, Optional
from datetime import datetime, date
from decimal import Decimal

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text
from etl.db import get_engine, check_db_connection
from etl.config import DATABASE_URL

# Default list of tables in travel schema (ordered logically)
TRAVEL_TABLES = [
    "source_system",
    "category",
    "source_entity",
    "tour",
    "location",
    "tour_destination",
    "tour_departure",
    "tour_departure_price",
    "itinerary",
    "itinerary_item",
    "itinerary_stop",
    "review",
]

# Staging tables
STAGING_TABLES = [
    "etl_run",
    "snapshot",
    "raw_record",
    "etl_issue",
    "mapping",
    "unmapped_tour_data",
    "location_alias",
    "schema_migration",
    "entity_state",
]


def format_cell_value(val) -> str:
    """Format cell value for CSV output."""
    if val is None:
        return ""
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if isinstance(val, Decimal):
        return str(val)
    if isinstance(val, (dict, list)):
        import json
        return json.dumps(val, ensure_ascii=False)
    return str(val)


def export_query_to_csv(engine, query: str, output_path: Path) -> int:
    """Execute a query and stream results into a CSV file with utf-8-sig encoding."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with engine.connect() as conn:
        result = conn.execution_options(stream_results=True).execute(text(query))
        columns = list(result.keys())
        
        with open(output_path, mode="w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
            writer.writerow(columns)
            
            row_count = 0
            for row in result:
                formatted_row = [format_cell_value(elem) for elem in row]
                writer.writerow(formatted_row)
                row_count += 1
                
    return row_count


def export_table(engine, schema_name: str, table_name: str, output_dir: Path) -> Optional[int]:
    """Export a single table to CSV."""
    file_name = f"{schema_name}_{table_name}.csv" if schema_name != "travel" else f"{table_name}.csv"
    output_file = output_dir / schema_name / file_name
    
    # Check if table exists in schema
    check_query = text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = :schema AND table_name = :table
        );
    """)
    with engine.connect() as conn:
        exists = conn.execute(check_query, {"schema": schema_name, "table": table_name}).scalar()
        if not exists:
            return None

    query = f"SELECT * FROM {schema_name}.{table_name} ORDER BY 1;"
    return export_query_to_csv(engine, query, output_file)


def export_flat_tours_summary(engine, output_dir: Path) -> int:
    """Export a denormalized, human-friendly flat tour summary view."""
    output_file = output_dir / "tours_flat_view.csv"
    query = """
        SELECT 
            se.source_entity_id,
            ss.name AS source_system,
            c.name AS category,
            se.source_record_key,
            se.name AS tour_name,
            t.duration_days,
            t.duration_nights,
            COALESCE(dep_stats.total_departures, 0) AS total_departures,
            price_stats.min_sale_price,
            price_stats.max_sale_price,
            price_stats.currency,
            dest_stats.destination_names,
            COALESCE(rev_stats.total_reviews, 0) AS total_reviews,
            rev_stats.avg_rating
        FROM travel.source_entity se
        JOIN travel.source_system ss USING (source_system_id)
        JOIN travel.category c USING (category_id)
        LEFT JOIN travel.tour t USING (source_entity_id)
        LEFT JOIN (
            SELECT tour_source_entity_id, COUNT(*) AS total_departures
            FROM travel.tour_departure
            GROUP BY tour_source_entity_id
        ) dep_stats ON se.source_entity_id = dep_stats.tour_source_entity_id
        LEFT JOIN (
            SELECT td.tour_source_entity_id,
                   MIN(tdp.sale_price) AS min_sale_price,
                   MAX(tdp.sale_price) AS max_sale_price,
                   MAX(tdp.currency) AS currency
            FROM travel.tour_departure td
            JOIN travel.tour_departure_price tdp USING (tour_departure_id)
            GROUP BY td.tour_source_entity_id
        ) price_stats ON se.source_entity_id = price_stats.tour_source_entity_id
        LEFT JOIN (
            SELECT td.tour_source_entity_id,
                   STRING_AGG(DISTINCT l.name, ', ' ORDER BY l.name) AS destination_names
            FROM travel.tour_destination td
            JOIN travel.location l USING (location_id)
            GROUP BY td.tour_source_entity_id
        ) dest_stats ON se.source_entity_id = dest_stats.tour_source_entity_id
        LEFT JOIN (
            SELECT source_entity_id,
                   COUNT(*) AS total_reviews,
                   ROUND(AVG(rating_value), 2) AS avg_rating
            FROM travel.review
            GROUP BY source_entity_id
        ) rev_stats ON se.source_entity_id = rev_stats.source_entity_id
        ORDER BY se.source_entity_id;
    """
    return export_query_to_csv(engine, query, output_file)


def main():
    parser = argparse.ArgumentParser(
        description="Export PostgreSQL tables to CSV with UTF-8 BOM encoding for easy Excel reading."
    )
    parser.add_argument(
        "--schema",
        choices=["travel", "staging", "all"],
        default="travel",
        help="Schema to export (default: travel)"
    )
    parser.add_argument(
        "--table",
        type=str,
        default=None,
        help="Export a specific table name only"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="exports",
        help="Output directory for exported CSV files (default: exports)"
    )
    parser.add_argument(
        "--skip-flat-view",
        action="store_true",
        help="Skip generating the consolidated tours_flat_view.csv"
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    start_time = time.time()

    print("=" * 70)
    print("           NDS-ETL DATABASE TO CSV EXPORT TOOL")
    print("=" * 70)
    print(f" Output Directory : {output_dir.resolve()}")
    print(f" Target Schema    : {args.schema}")
    print(f" Target Table     : {args.table or 'ALL'}")
    print("-" * 70)

    # Check DB connection
    if not check_db_connection():
        print(f"[ERROR] Cannot connect to database at: {DATABASE_URL}")
        print("Please verify the PostgreSQL Docker container is running (docker compose up -d).")
        sys.exit(1)

    engine = get_engine()
    tables_to_export = []

    if args.table:
        # Determine schema of the requested table
        if args.schema == "staging":
            tables_to_export.append(("staging", args.table))
        elif args.schema == "travel":
            tables_to_export.append(("travel", args.table))
        else:
            # Check both
            tables_to_export.append(("travel", args.table))
    else:
        if args.schema in ["travel", "all"]:
            for t in TRAVEL_TABLES:
                tables_to_export.append(("travel", t))
        if args.schema in ["staging", "all"]:
            for t in STAGING_TABLES:
                tables_to_export.append(("staging", t))

    results = []
    total_rows = 0

    for schema, table in tables_to_export:
        try:
            row_count = export_table(engine, schema, table, output_dir)
            if row_count is not None:
                file_rel = f"{schema}/{table}.csv" if schema != "travel" else f"travel/{table}.csv"
                results.append((f"{schema}.{table}", row_count, file_rel, "OK"))
                total_rows += row_count
            else:
                results.append((f"{schema}.{table}", 0, "Table not found", "SKIPPED"))
        except Exception as e:
            results.append((f"{schema}.{table}", 0, str(e)[:40], "FAILED"))

    # Generate flat summary view if travel schema was included and no specific table filtered
    if not args.skip_flat_view and (args.schema in ["travel", "all"]) and (args.table is None or args.table == "tour"):
        try:
            flat_rows = export_flat_tours_summary(engine, output_dir)
            results.append(("View: tours_flat_view", flat_rows, "tours_flat_view.csv", "OK"))
        except Exception as e:
            results.append(("View: tours_flat_view", 0, str(e)[:40], "FAILED"))

    elapsed = time.time() - start_time

    # Print summary table
    print("\n" + "=" * 70)
    print(f"{'Table / View':<30} | {'Rows':<8} | {'Status':<8} | {'File'}")
    print("-" * 70)
    for name, rows, file_rel, status in results:
        print(f"{name:<30} | {rows:<8} | {status:<8} | {file_rel}")
    print("=" * 70)
    print(f" Export completed in {elapsed:.2f}s. Total rows exported: {total_rows:,}")
    print(f" All CSV files saved with UTF-8 BOM encoding in: {output_dir.resolve()}/\n")


if __name__ == "__main__":
    main()
