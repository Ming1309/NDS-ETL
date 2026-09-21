import logging
from pathlib import Path
from sqlalchemy import text
from etl.config import BASE_DIR
from etl.db import get_engine

logger = logging.getLogger(__name__)

CHECK_DUPLICATES_QUERIES = [
    {
        "table": "travel.source_system",
        "description": "Unique source_system name",
        "query": "SELECT name, COUNT(*) as cnt FROM travel.source_system GROUP BY name HAVING COUNT(*) > 1;"
    },
    {
        "table": "travel.category",
        "description": "Unique category name",
        "query": "SELECT name, COUNT(*) as cnt FROM travel.category GROUP BY name HAVING COUNT(*) > 1;"
    },
    {
        "table": "travel.source_entity",
        "description": "Unique (source_system_id, category_id, source_record_key)",
        "query": """
            SELECT source_system_id, category_id, source_record_key, COUNT(*) as cnt
            FROM travel.source_entity
            GROUP BY source_system_id, category_id, source_record_key
            HAVING COUNT(*) > 1;
        """
    },
    {
        "table": "travel.tour_departure",
        "description": "Unique (tour_source_entity_id, source_departure_key)",
        "query": """
            SELECT tour_source_entity_id, source_departure_key, COUNT(*) as cnt
            FROM travel.tour_departure
            GROUP BY tour_source_entity_id, source_departure_key
            HAVING COUNT(*) > 1;
        """
    },
    {
        "table": "travel.review",
        "description": "Unique (source_entity_id, source_review_key)",
        "query": """
            SELECT source_entity_id, source_review_key, COUNT(*) as cnt
            FROM travel.review
            GROUP BY source_entity_id, source_review_key
            HAVING COUNT(*) > 1;
        """
    },
    {
        "table": "travel.itinerary",
        "description": "Unique (tour_source_entity_id, name)",
        "query": """
            SELECT tour_source_entity_id, name, COUNT(*) as cnt
            FROM travel.itinerary
            GROUP BY tour_source_entity_id, name
            HAVING COUNT(*) > 1;
        """
    },
    {
        "table": "travel.itinerary_item",
        "description": "Unique (itinerary_id, sequence_no)",
        "query": """
            SELECT itinerary_id, sequence_no, COUNT(*) as cnt
            FROM travel.itinerary_item
            GROUP BY itinerary_id, sequence_no
            HAVING COUNT(*) > 1;
        """
    },
    {
        "table": "travel.tour_departure_price",
        "description": "Unique (tour_departure_id, observed_at, currency)",
        "query": """
            SELECT tour_departure_id, observed_at, currency, COUNT(*) as cnt
            FROM travel.tour_departure_price
            GROUP BY tour_departure_id, observed_at, currency
            HAVING COUNT(*) > 1;
        """
    }
]

def check_pre_migration_duplicates(engine) -> list:
    """Check for duplicate records before adding UNIQUE constraints."""
    conflicts = []
    with engine.connect() as conn:
        for check in CHECK_DUPLICATES_QUERIES:
            table_name = check["table"]
            # Check if table exists
            schema, tab = table_name.split(".")
            exists_query = text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = :schema AND table_name = :tab
                );
            """)
            exists = conn.execute(exists_query, {"schema": schema, "tab": tab}).scalar()
            if not exists:
                continue

            try:
                res = conn.execute(text(check["query"])).fetchall()
                if res:
                    conflicts.append({
                        "table": table_name,
                        "description": check["description"],
                        "conflicting_rows": [dict(r._mapping) for r in res]
                    })
            except Exception as e:
                logger.warning(f"Could not execute duplicate check on {table_name}: {e}")
    return conflicts

def run_migrations(db_url: str = None) -> dict:
    """
    Safely runs all migrations:
    1. Check for table duplicate conflicts. Halts if duplicates found.
    2. Initializes base travel schema if not present.
    3. Runs staging schema migration (02_staging_schema.sql).
    4. Runs constraints migration (03_travel_constraints.sql).
    """
    engine = get_engine(db_url)
    
    # 1. Check duplicate records
    conflicts = check_pre_migration_duplicates(engine)
    if conflicts:
        err_msg = f"Migration aborted! Duplicates found in existing tables:\n"
        for c in conflicts:
            err_msg += f"- {c['table']} ({c['description']}): {len(c['conflicting_rows'])} duplicate keys\n"
        logger.error(err_msg)
        raise RuntimeError(err_msg)

    sql_dir = BASE_DIR / "sql"
    migration_files = [
        sql_dir / "travel_schema.sql",
        sql_dir / "02_staging_schema.sql",
        sql_dir / "03_travel_constraints.sql",
    ]

    applied = []
    with engine.begin() as conn:
        # Check if base travel schema already initialized
        base_exists = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'travel' AND table_name = 'source_system'
            );
        """)).scalar()

        for fpath in migration_files:
            if not fpath.exists():
                logger.warning(f"Migration file not found: {fpath}")
                continue

            # Skip base travel_schema.sql if tables already exist
            if fpath.name == "travel_schema.sql" and base_exists:
                logger.info("Base travel schema tables already exist. Skipping travel_schema.sql.")
                continue
            if fpath.name == "02_staging_schema.sql":
                staging_ready = conn.execute(text("SELECT to_regclass('staging.entity_state') IS NOT NULL")).scalar()
                if staging_ready:
                    conn.execute(text("INSERT INTO staging.schema_migration (migration_name) VALUES (:name) ON CONFLICT DO NOTHING"), {"name": fpath.name})
                    continue

            if fpath.name != "travel_schema.sql":
                # 02 creates this registry.  Old installations may already have
                # a constraint migration applied, so detect it before rerunning.
                if fpath.name == "03_travel_constraints.sql":
                    exists = conn.execute(text("""
                        SELECT EXISTS (SELECT 1 FROM pg_constraint
                        WHERE conname = 'uq_source_entity_key')
                    """)).scalar()
                    if exists:
                        conn.execute(text("INSERT INTO staging.schema_migration (migration_name) VALUES (:name) ON CONFLICT DO NOTHING"), {"name": fpath.name})
                        continue
                already = conn.execute(text("""
                    SELECT EXISTS (SELECT 1 FROM staging.schema_migration WHERE migration_name=:name)
                """), {"name": fpath.name}).scalar()
                if already:
                    continue

            logger.info(f"Applying migration: {fpath.name}")
            sql_content = fpath.read_text(encoding="utf-8")
            conn.execute(text(sql_content))
            if fpath.name != "travel_schema.sql":
                conn.execute(text("INSERT INTO staging.schema_migration (migration_name) VALUES (:name) ON CONFLICT DO NOTHING"), {"name": fpath.name})
            applied.append(fpath.name)

    logger.info("All migrations successfully applied.")
    return {"status": "SUCCESS", "applied_migrations": applied}

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    res = run_migrations()
    print("Migration result:", res)
