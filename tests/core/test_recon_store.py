"""Tests for ReconStore CRUD, deduplication, and queries."""
import pytest
import pytest_asyncio

from core.recon_store import ReconStore
from core.database.utils import init_db, AsyncSessionLocal
from core.database.models import ReconRecord
from sqlalchemy import select, func, text


@pytest_asyncio.fixture(autouse=True)
async def _init_db():
    """Ensure fresh tables for each test."""
    await init_db()
    async with AsyncSessionLocal() as session:
        await session.execute(text("DELETE FROM recon_records"))
        await session.commit()


@pytest_asyncio.fixture
async def store():
    return ReconStore()


@pytest.mark.asyncio
async def test_add_record_basic(store):
    s = store
    await s.add_record("task_1", "domain", "example.com", {"name": "api.example.com"}, "step_1", 1.0)

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(ReconRecord))
        records = result.scalars().all()

    assert len(records) == 1
    assert records[0].task_id == "task_1"
    assert records[0].record_type == "domain"
    assert records[0].target == "example.com"
    assert records[0].value["name"] == "api.example.com"
    assert records[0].source_step_id == "step_1"
    assert records[0].confidence == 1.0


@pytest.mark.asyncio
async def test_dedup_same_core_id_updates_confidence_and_step(store):
    s = store
    await s.add_record("task_1", "domain", "example.com", {"name": "api.example.com"}, "step_1", 1.0)
    await s.add_record("task_1", "domain", "example.com", {"name": "api.example.com"}, "step_2", 0.9)

    records = await s.query_records("task_1", record_type="domain")
    assert len(records) == 1
    assert records[0].confidence == 1.0  # max wins
    assert records[0].source_step_id == "step_2"  # latest wins


@pytest.mark.asyncio
async def test_dedup_different_core_id_inserts_new(store):
    s = store
    await s.add_record("task_1", "domain", "example.com", {"name": "api.example.com"}, "step_1", 1.0)
    await s.add_record("task_1", "domain", "example.com", {"name": "admin.example.com"}, "step_2", 1.0)

    records = await s.query_records("task_1", record_type="domain")
    assert len(records) == 2


@pytest.mark.asyncio
async def test_dedup_fallback_md5(store):
    s = store
    # record_type without a known core key falls back to MD5 of full JSON
    await s.add_record("task_1", "unknown_type", "example.com", {"foo": "bar", "baz": 1}, "step_1", 1.0)
    await s.add_record("task_1", "unknown_type", "example.com", {"foo": "bar", "baz": 1}, "step_2", 0.8)

    records = await s.query_records("task_1", record_type="unknown_type")
    assert len(records) == 1
    assert records[0].confidence == 1.0
    assert records[0].source_step_id == "step_2"


@pytest.mark.asyncio
async def test_dedup_cross_task_isolated(store):
    s = store
    await s.add_record("task_a", "ip", "example.com", {"address": "1.2.3.4"}, "step_1", 1.0)
    await s.add_record("task_b", "ip", "example.com", {"address": "1.2.3.4"}, "step_1", 1.0)

    records_a = await s.query_records("task_a", record_type="ip")
    records_b = await s.query_records("task_b", record_type="ip")
    assert len(records_a) == 1
    assert len(records_b) == 1


@pytest.mark.asyncio
async def test_query_records_with_filters(store):
    s = store
    await s.add_record("task_1", "domain", "example.com", {"name": "api.example.com"}, "s1", 1.0)
    await s.add_record("task_1", "ip", "example.com", {"address": "1.2.3.4"}, "s2", 1.0)
    await s.add_record("task_1", "domain", "other.com", {"name": "sub.other.com"}, "s3", 1.0)

    all_recs = await s.query_records("task_1")
    assert len(all_recs) == 3

    domain_recs = await s.query_records("task_1", record_type="domain")
    assert len(domain_recs) == 2

    target_recs = await s.query_records("task_1", target="example.com")
    assert len(target_recs) == 2

    filtered = await s.query_records("task_1", record_type="domain", target="example.com")
    assert len(filtered) == 1
    assert filtered[0].value["name"] == "api.example.com"


@pytest.mark.asyncio
async def test_query_records_limit(store):
    s = store
    for i in range(5):
        await s.add_record("task_1", "domain", "example.com", {"name": f"sub{i}.example.com"}, f"s{i}", 1.0)

    records = await s.query_records("task_1", limit=2)
    assert len(records) == 2


@pytest.mark.asyncio
async def test_get_summary(store):
    s = store
    await s.add_record("task_1", "domain", "example.com", {"name": "a.example.com"}, "s1", 1.0)
    await s.add_record("task_1", "domain", "example.com", {"name": "b.example.com"}, "s2", 1.0)
    await s.add_record("task_1", "ip", "example.com", {"address": "1.2.3.4"}, "s3", 1.0)

    summary = await s.get_summary("task_1")
    assert summary["domain"] == 2
    assert summary["ip"] == 1


@pytest.mark.asyncio
async def test_get_summary_empty(store):
    s = store
    summary = await s.get_summary("no_task")
    assert summary == {}


@pytest.mark.asyncio
async def test_get_targets(store):
    s = store
    await s.add_record("task_1", "domain", "example.com", {"name": "a.example.com"}, "s1", 1.0)
    await s.add_record("task_1", "ip", "example.com", {"address": "1.2.3.4"}, "s2", 1.0)
    await s.add_record("task_1", "domain", "other.com", {"name": "b.other.com"}, "s3", 1.0)

    targets = await s.get_targets("task_1")
    assert sorted(targets) == ["example.com", "other.com"]


@pytest.mark.asyncio
async def test_get_targets_empty(store):
    s = store
    targets = await s.get_targets("no_task")
    assert targets == []


@pytest.mark.asyncio
async def test_extract_core_id_known_types():
    s = ReconStore()
    assert s._extract_core_id("domain", {"name": "x.com"}) == "x.com"
    assert s._extract_core_id("ip", {"address": "1.2.3.4"}) == "1.2.3.4"
    assert s._extract_core_id("port", {"number": 80, "protocol": "tcp"}) == "80"
    assert s._extract_core_id("endpoint", {"url": "http://x.com"}) == "http://x.com"
    assert s._extract_core_id("service", {"name": "nginx"}) == "nginx"
    assert s._extract_core_id("tech", {"name": "Spring"}) == "Spring"
    assert s._extract_core_id("credential", {"value": "secret"}) == "secret"
    assert s._extract_core_id("sensitive", {"value": "leak"}) == "leak"
    assert s._extract_core_id("auth", {"login_url": "/login"}) == "/login"
    assert s._extract_core_id("file", {"path": "/admin"}) == "/admin"


@pytest.mark.asyncio
async def test_extract_core_id_fallback_md5():
    s = ReconStore()
    val = {"foo": "bar"}
    import hashlib, json
    expected = hashlib.md5(json.dumps(val, sort_keys=True).encode()).hexdigest()
    assert s._extract_core_id("unknown", val) == expected
