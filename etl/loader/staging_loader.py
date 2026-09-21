import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import text

from etl.adapters.base import SourceBundle, EtlIssue, UnmappedData
from etl.models.staging import EtlRun, Snapshot, RawRecord, EtlIssueModel, UnmappedTourData, Mapping
from etl.normalizers.datetime import VN_TZ

logger = logging.getLogger(__name__)

class StagingLoader:
    def __init__(self, session: Optional[Session] = None, dry_run: bool = False):
        self.session = session
        self.dry_run = dry_run

    def start_run(self, run_id: str, source_name: str) -> None:
        if self.dry_run or self.session is None:
            logger.info(f"[DRY-RUN] Started ETL run: {run_id} for source: {source_name}")
            return

        run_record = EtlRun(
            run_id=run_id,
            source_name=source_name,
            status="RUNNING",
            is_dry_run=self.dry_run,
            started_at=datetime.now(VN_TZ),
            metrics={}
        )
        self.session.merge(run_record)
        self.session.flush()

    def complete_run(
        self,
        run_id: str,
        status: str = "COMPLETED",
        metrics: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ) -> None:
        if self.dry_run or self.session is None:
            logger.info(f"[DRY-RUN] Completed ETL run: {run_id} with status: {status}")
            return

        run_record = self.session.query(EtlRun).filter_by(run_id=run_id).first()
        if run_record:
            run_record.status = status
            run_record.completed_at = datetime.now(VN_TZ)
            if metrics:
                run_record.metrics = metrics
            if error_message:
                run_record.error_message = error_message
            self.session.flush()

    def load_bundle_staging(self, run_id: str, bundle: SourceBundle) -> None:
        """Load snapshots, issues, raw records, and unmapped items into staging schema."""
        if self.dry_run or self.session is None:
            logger.info(f"[DRY-RUN] Simulating staging load for {bundle.source_name}: "
                        f"{len(bundle.issues)} issues, {len(bundle.unmapped_items)} unmapped items.")
            return

        now = datetime.now(VN_TZ)

        # 1. Update run checksums
        run_record = self.session.query(EtlRun).filter_by(run_id=run_id).first()
        if run_record:
            run_record.file_checksums = bundle.file_hashes

        # 2. Record snapshots
        snapshot_map = {}
        for fname, fhash in bundle.file_hashes.items():
            snapshot = self.session.query(Snapshot).filter_by(
                source_name=bundle.source_name, file_path=fname, file_hash=fhash
            ).first()
            if not snapshot:
                snapshot = Snapshot(
                    source_name=bundle.source_name,
                    file_path=fname,
                    file_hash=fhash,
                    total_raw_records=sum(1 for raw in bundle.raw_records if raw.file_name == fname),
                    created_at=now
                )
                self.session.add(snapshot)
                self.session.flush()
            snapshot_map[fname] = snapshot.snapshot_id

        # 3. Batch load raw records
        raw_objs = []
        for raw in bundle.raw_records:
            snap_id = snapshot_map.get(raw.file_name)
            raw_objs.append(RawRecord(
                run_id=run_id,
                snapshot_id=snap_id,
                source_name=bundle.source_name,
                source_entity_key=raw.source_entity_key,
                file_name=raw.file_name,
                sheet_name=raw.sheet_name,
                line_or_index=raw.line_number,
                raw_payload=raw.payload,
                created_at=now
            ))
            if len(raw_objs) >= 500:
                self.session.bulk_save_objects(raw_objs)
                self.session.flush()
                raw_objs = []
        if raw_objs:
            self.session.bulk_save_objects(raw_objs)
            self.session.flush()

        # 4. Load issues
        issue_objs = []
        for issue in bundle.issues:
            issue_objs.append(EtlIssueModel(
                run_id=run_id,
                source_name=bundle.source_name,
                record_key=issue.record_key,
                field_name=issue.field_name,
                error_code=issue.error_code,
                severity=issue.severity,
                raw_value=str(issue.raw_value)[:500] if issue.raw_value else None,
                message=issue.message,
                created_at=now
            ))
        if issue_objs:
            self.session.bulk_save_objects(issue_objs)
            self.session.flush()

        # 5. Load unmapped data
        unmapped_objs = []
        for u in bundle.unmapped_items:
            unmapped_objs.append(UnmappedTourData(
                run_id=run_id,
                source_name=bundle.source_name,
                source_record_key=u.source_record_key,
                data_kind=u.data_kind,
                payload=u.payload,
                created_at=now
            ))
            if len(unmapped_objs) >= 500:
                self.session.bulk_save_objects(unmapped_objs)
                self.session.flush()
                unmapped_objs = []
        if unmapped_objs:
            self.session.bulk_save_objects(unmapped_objs)
            self.session.flush()

    def record_mapping(self, source_name: str, entity_type: str, source_key: str, nds_id: int) -> None:
        """Record mapping between source key and NDS PK."""
        if self.dry_run or self.session is None:
            return
        existing = self.session.query(Mapping).filter_by(
            source_name=source_name,
            entity_type=entity_type,
            source_key=source_key
        ).first()
        if existing:
            existing.nds_id = nds_id
        else:
            mapping = Mapping(
                source_name=source_name,
                entity_type=entity_type,
                source_key=source_key,
                nds_id=nds_id,
                created_at=datetime.now(VN_TZ)
            )
            self.session.add(mapping)
