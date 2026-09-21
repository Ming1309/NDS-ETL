from sqlalchemy import (
    Column,
    BigInteger,
    Integer,
    Text,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base

StagingBase = declarative_base()

class EtlRun(StagingBase):
    __tablename__ = "etl_run"
    __table_args__ = {"schema": "staging"}

    run_id = Column(String(64), primary_key=True)
    source_name = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False, default="RUNNING")
    is_dry_run = Column(Boolean, nullable=False, default=False)
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True))
    file_checksums = Column(JSONB, default=dict)
    metrics = Column(JSONB, default=dict)
    error_message = Column(Text)

class Snapshot(StagingBase):
    __tablename__ = "snapshot"
    __table_args__ = {"schema": "staging"}

    snapshot_id = Column(BigInteger, primary_key=True, autoincrement=True)
    source_name = Column(String(32), nullable=False)
    file_path = Column(Text, nullable=False)
    file_hash = Column(String(64), nullable=False)
    total_raw_records = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True))

class EntityState(StagingBase):
    __tablename__ = "entity_state"
    __table_args__ = {"schema": "staging"}

    source_name = Column(String(32), primary_key=True)
    entity_type = Column(String(32), primary_key=True)
    source_key = Column(Text, primary_key=True)
    snapshot_id = Column(BigInteger, ForeignKey("staging.snapshot.snapshot_id"))
    source_observed_at = Column(DateTime(timezone=True))
    transformer_version = Column(Text, nullable=False)
    payload_hash = Column(String(64), nullable=False)
    applied_at = Column(DateTime(timezone=True), nullable=False)

class RawRecord(StagingBase):
    __tablename__ = "raw_record"
    __table_args__ = {"schema": "staging"}

    raw_id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(String(64), ForeignKey("staging.etl_run.run_id", ondelete="CASCADE"))
    snapshot_id = Column(BigInteger, ForeignKey("staging.snapshot.snapshot_id", ondelete="SET NULL"))
    source_name = Column(String(32), nullable=False)
    source_entity_key = Column(Text)
    file_name = Column(Text, nullable=False)
    sheet_name = Column(Text)
    line_or_index = Column(Integer)
    raw_payload = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True))

class EtlIssueModel(StagingBase):
    __tablename__ = "etl_issue"
    __table_args__ = {"schema": "staging"}

    issue_id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(String(64), ForeignKey("staging.etl_run.run_id", ondelete="CASCADE"))
    source_name = Column(String(32), nullable=False)
    record_key = Column(Text)
    field_name = Column(Text)
    error_code = Column(String(64), nullable=False)
    severity = Column(String(16), nullable=False, default="WARNING")
    raw_value = Column(Text)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True))

class Mapping(StagingBase):
    __tablename__ = "mapping"
    __table_args__ = (
        UniqueConstraint("source_name", "entity_type", "source_key", name="uq_staging_mapping"),
        {"schema": "staging"}
    )

    mapping_id = Column(BigInteger, primary_key=True, autoincrement=True)
    source_name = Column(String(32), nullable=False)
    entity_type = Column(String(32), nullable=False)
    source_key = Column(Text, nullable=False)
    nds_id = Column(BigInteger, nullable=False)
    created_at = Column(DateTime(timezone=True))

class UnmappedTourData(StagingBase):
    __tablename__ = "unmapped_tour_data"
    __table_args__ = {"schema": "staging"}

    unmapped_id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(String(64), ForeignKey("staging.etl_run.run_id", ondelete="CASCADE"))
    source_name = Column(String(32), nullable=False)
    source_record_key = Column(Text, nullable=False)
    data_kind = Column(String(64), nullable=False)
    payload = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True))

class LocationAlias(StagingBase):
    __tablename__ = "location_alias"
    __table_args__ = {"schema": "staging"}

    alias_id = Column(BigInteger, primary_key=True, autoincrement=True)
    alias_name = Column(Text, nullable=False, unique=True)
    standard_name = Column(Text, nullable=False)
    location_type = Column(Text)
    parent_name = Column(Text)
    is_verified = Column(Boolean, default=True)
