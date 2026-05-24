"""Tests for ReconRecord and TaskPolicy database models."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select
from sqlalchemy.sql import func

from core.database.models import Base, ReconRecord, TaskPolicy


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_recon_record_table_created(db_session):
    result = await db_session.execute(select(func.count()).select_from(ReconRecord))
    count = result.scalar()
    assert count == 0


@pytest.mark.asyncio
async def test_task_policy_table_created(db_session):
    result = await db_session.execute(select(func.count()).select_from(TaskPolicy))
    count = result.scalar()
    assert count == 0


@pytest.mark.asyncio
async def test_recon_record_insert_and_query(db_session):
    record = ReconRecord(
        task_id="task_001",
        record_type="open_port",
        target="192.168.1.1",
        value={"port": 80, "service": "http"},
        source_step_id="step_42",
        confidence=0.95,
    )
    db_session.add(record)
    await db_session.commit()

    result = await db_session.execute(
        select(ReconRecord).where(ReconRecord.task_id == "task_001")
    )
    fetched = result.scalar_one()
    assert fetched.record_type == "open_port"
    assert fetched.target == "192.168.1.1"
    assert fetched.value["port"] == 80
    assert fetched.confidence == pytest.approx(0.95)
    assert fetched.source_step_id == "step_42"
    assert fetched.created_at is not None


@pytest.mark.asyncio
async def test_task_policy_insert_and_query(db_session):
    policy = TaskPolicy(
        task_id="task_001",
        raw_policy="Allow all ports",
        parsed_policy={"ports": [80, 443]},
        parse_status="success",
        parse_error=None,
    )
    db_session.add(policy)
    await db_session.commit()

    result = await db_session.execute(
        select(TaskPolicy).where(TaskPolicy.task_id == "task_001")
    )
    fetched = result.scalar_one()
    assert fetched.raw_policy == "Allow all ports"
    assert fetched.parsed_policy["ports"] == [80, 443]
    assert fetched.parse_status == "success"
    assert fetched.parse_error is None
    assert fetched.created_at is not None
    assert fetched.updated_at is not None


@pytest.mark.asyncio
async def test_task_policy_task_id_unique(db_session):
    policy1 = TaskPolicy(
        task_id="task_unique",
        raw_policy="First",
        parsed_policy={},
        parse_status="success",
    )
    policy2 = TaskPolicy(
        task_id="task_unique",
        raw_policy="Second",
        parsed_policy={},
        parse_status="failed",
    )
    db_session.add(policy1)
    await db_session.commit()

    db_session.add(policy2)
    with pytest.raises(Exception):
        await db_session.commit()


@pytest.mark.asyncio
async def test_recon_record_indexes_exist(db_session):
    from sqlalchemy import text
    result = await db_session.execute(
        text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='recon_records'")
    )
    index_names = {row[0] for row in result.all()}
    assert any("task_id" in name for name in index_names)
    assert any("record_type" in name for name in index_names)
    assert any("target" in name for name in index_names)


@pytest.mark.asyncio
async def test_task_policy_indexes_exist(db_session):
    from sqlalchemy import text
    result = await db_session.execute(
        text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='task_policies'")
    )
    index_names = {row[0] for row in result.all()}
    assert any("task_id" in name for name in index_names)
