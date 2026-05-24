"""ReconStore: CRUD, deduplication, and query interface for recon_records."""
import hashlib
import json
from typing import Any, Dict, List, Optional

from sqlalchemy import select, and_, func

from core.database.utils import AsyncSessionLocal
from core.database.models import ReconRecord


class ReconStore:
    """Unified information collection warehouse with deduplication."""

    # Mapping from record_type to the key inside `value` that uniquely identifies the record
    _CORE_KEYS: Dict[str, str] = {
        "domain": "name",
        "ip": "address",
        "port": "number",
        "endpoint": "url",
        "service": "name",
        "tech": "name",
        "credential": "value",
        "sensitive": "value",
        "auth": "login_url",
        "file": "path",
    }

    async def add_record(
        self,
        task_id: str,
        record_type: str,
        target: str,
        value: Dict[str, Any],
        source_step_id: str,
        confidence: float = 1.0,
    ) -> None:
        """Insert a record, or update an existing one if it duplicates by core identifier."""
        core_id = self._extract_core_id(record_type, value)

        async with AsyncSessionLocal() as session:
            # Find candidate rows with the same task + type + target
            stmt = select(ReconRecord).where(
                and_(
                    ReconRecord.task_id == task_id,
                    ReconRecord.record_type == record_type,
                    ReconRecord.target == target,
                )
            )
            result = await session.execute(stmt)
            candidates = result.scalars().all()

            for record in candidates:
                existing_core = self._extract_core_id(record_type, record.value)
                if existing_core == core_id:
                    # Deduplicate: keep max confidence, latest source_step_id
                    record.confidence = max(record.confidence if record.confidence is not None else 0.0, confidence)
                    record.source_step_id = source_step_id
                    await session.commit()
                    return

            # No duplicate found — insert new record
            new_record = ReconRecord(
                task_id=task_id,
                record_type=record_type,
                target=target,
                value=value,
                source_step_id=source_step_id,
                confidence=confidence,
            )
            session.add(new_record)
            await session.commit()

    def _extract_core_id(self, record_type: str, value: Dict[str, Any]) -> str:
        """Return a string that uniquely identifies this record within its type."""
        key = self._CORE_KEYS.get(record_type)
        if key and key in value:
            return str(value[key])
        # Fallback: MD5 of sorted JSON
        return hashlib.md5(json.dumps(value, sort_keys=True).encode()).hexdigest()

    async def query_records(
        self,
        task_id: str,
        record_type: Optional[str] = None,
        target: Optional[str] = None,
        limit: int = 100,
    ) -> List[ReconRecord]:
        """List recon records for a task, optionally filtered."""
        async with AsyncSessionLocal() as session:
            stmt = select(ReconRecord).where(ReconRecord.task_id == task_id)
            if record_type:
                stmt = stmt.where(ReconRecord.record_type == record_type)
            if target:
                stmt = stmt.where(ReconRecord.target == target)
            stmt = stmt.order_by(ReconRecord.created_at.desc()).limit(limit)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_summary(self, task_id: str) -> Dict[str, int]:
        """Return a mapping {record_type: count} for the given task."""
        async with AsyncSessionLocal() as session:
            stmt = (
                select(ReconRecord.record_type, func.count(ReconRecord.id))
                .where(ReconRecord.task_id == task_id)
                .group_by(ReconRecord.record_type)
            )
            result = await session.execute(stmt)
            return {row[0]: row[1] for row in result.all()}

    async def get_targets(self, task_id: str) -> List[str]:
        """Return a deduplicated list of all targets for the given task."""
        async with AsyncSessionLocal() as session:
            stmt = (
                select(ReconRecord.target)
                .where(ReconRecord.task_id == task_id)
                .distinct()
            )
            result = await session.execute(stmt)
            return [row[0] for row in result.all()]
