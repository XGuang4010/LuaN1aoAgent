"""End-to-end integration tests for ReconStore + TestPolicy pipeline.

Scenarios:
1. 信息采集流水线: nmap_scan -> structured_findings -> ReconStore -> API query
2. Policy 注入流水线: Task with policy -> TestPolicy parse -> Planner inject -> Executor prompt
3. 跨通道去重: Same info via two channels -> ReconStore dedup with highest confidence

External dependencies (LLM, shell_exec, etc.) are mocked.
"""

import json
import sys
import os
import tempfile
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

# ---------------------------------------------------------------------------
# Conditional imports — fail fast if core modules aren't ready
# ---------------------------------------------------------------------------

pytest.importorskip("sqlalchemy.ext.asyncio")
pytest.importorskip("fastapi")

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select
from fastapi.testclient import TestClient

from core.database.models import Base, ReconRecord, TaskPolicy
from core.test_policy import TestPolicy
from core.recon_store import ReconStore

from tools import mcp_service

web_mod = pytest.importorskip("web.server")
app = web_mod.app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db_session():
    """Provide an async DB session backed by an in-memory SQLite database."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def recon_store(db_session, monkeypatch):
    """ReconStore instance wired to the in-memory DB."""
    # Patch AsyncSessionLocal inside recon_store so DB ops hit our test DB
    test_session_maker = async_sessionmaker(
        db_session.bind, expire_on_commit=False
    )
    monkeypatch.setattr(
        "core.recon_store.AsyncSessionLocal",
        test_session_maker,
    )
    store = ReconStore()
    return store


@pytest.fixture
def test_client():
    """Synchronous TestClient for FastAPI app."""
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeNmapProcess:
    """Fake asyncio subprocess-like object for nmap_scan tests."""
    def __init__(self, stdout_lines: list, returncode: int = 0):
        self.stdout = AsyncMock()
        self.stdout.readline = AsyncMock(side_effect=stdout_lines)
        self._returncode = returncode

    async def wait(self):
        return self._returncode


# ---------------------------------------------------------------------------
# Scenario 1: 信息采集流水线
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_info_collection_pipeline_nmap_scan_structured_findings(monkeypatch):
    """nmap_scan 工具执行后 structured_findings 包含正确的 host/port 信息."""
    raw_output = [
        b"Nmap scan report for 192.168.1.1\n",
        b"Host is up (0.0005s latency).\n",
        b"PORT     STATE SERVICE\n",
        b"80/tcp   open  http\n",
        b"443/tcp  open  https\n",
        b"22/tcp   open  ssh\n",
        b"\n",
        b"Nmap done: 1 IP address (1 host up) scanned in 15.20 seconds\n",
        b"",
    ]

    async def fake_exec(*args, **kwargs):
        return FakeNmapProcess(raw_output, returncode=0)

    monkeypatch.setattr(mcp_service.asyncio, "create_subprocess_shell", fake_exec)
    monkeypatch.setattr(mcp_service, "_resolve_tool_path", lambda *a, **k: "nmap")

    result_json = json.loads(await mcp_service.nmap_scan("192.168.1.1", ports="1-1000"))

    assert result_json["success"] is True
    assert "structured_findings" in result_json

    sf = result_json["structured_findings"]
    assert sf["summary"]["total_hosts"] == 1
    assert sf["summary"]["total_open_ports"] == 3

    host = sf["hosts"][0]
    assert host["ip"] == "192.168.1.1"
    ports = host["ports"]
    assert len(ports) == 3
    assert ports[0]["number"] == 80
    assert ports[0]["protocol"] == "tcp"
    assert ports[0]["state"] == "open"


@pytest.mark.asyncio
async def test_info_collection_pipeline_recon_store_write_and_query(recon_store):
    """验证 ReconStore 已写入对应记录，且通过 API 查询可检索."""
    task_id = "task_e2e_001"
    step_id = "step_nmap_42"

    await recon_store.add_record(
        task_id=task_id,
        record_type="ip",
        target="192.168.1.1",
        value={"address": "192.168.1.1", "type": "ipv4"},
        source_step_id=step_id,
        confidence=1.0,
    )
    await recon_store.add_record(
        task_id=task_id,
        record_type="port",
        target="192.168.1.1",
        value={"number": 80, "protocol": "tcp", "state": "open"},
        source_step_id=step_id,
        confidence=1.0,
    )
    await recon_store.add_record(
        task_id=task_id,
        record_type="port",
        target="192.168.1.1",
        value={"number": 443, "protocol": "tcp", "state": "open"},
        source_step_id=step_id,
        confidence=1.0,
    )

    ip_records = await recon_store.query_records(task_id, record_type="ip")
    port_records = await recon_store.query_records(task_id, record_type="port")

    assert len(ip_records) == 1
    assert ip_records[0].value["address"] == "192.168.1.1"
    assert len(port_records) == 2

    summary = await recon_store.get_summary(task_id)
    assert summary["ip"] == 1
    assert summary["port"] == 2


@pytest.mark.asyncio
async def test_info_collection_pipeline_api_query(test_client, monkeypatch):
    """通过 Web API 查询验证数据可检索.

    Uses a file-based SQLite DB so the same DB file is visible across the
    test's event loop and TestClient's internal event loop.
    """
    task_id = "task_e2e_api"
    db_file = tempfile.mktemp(suffix=".db")
    db_url = f"sqlite+aiosqlite:///{db_file}"

    try:
        # 1. Set up a shared file-based DB
        shared_engine = create_async_engine(db_url, echo=False)
        async with shared_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        shared_session_maker = async_sessionmaker(shared_engine, expire_on_commit=False)

        # 2. Patch both recon_store and web.server to use the shared DB
        monkeypatch.setattr("core.recon_store.AsyncSessionLocal", shared_session_maker)
        monkeypatch.setattr("web.server.AsyncSessionLocal", shared_session_maker)

        store = ReconStore()
        await store.add_record(
            task_id=task_id,
            record_type="endpoint",
            target="example.com",
            value={"url": "https://example.com/api/v1/users", "method": "GET", "status_code": 200},
            source_step_id="step_httpx_1",
            confidence=1.0,
        )

        response = test_client.get(f"/api/recon/{task_id}")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert any(r["record_type"] == "endpoint" for r in data["items"])

        resp_summary = test_client.get(f"/api/recon/{task_id}/summary")
        assert resp_summary.status_code == 200
        assert "type_breakdown" in resp_summary.json()
    finally:
        await shared_engine.dispose()
        if os.path.exists(db_file):
            os.unlink(db_file)


# ---------------------------------------------------------------------------
# Scenario 2: Policy 注入流水线
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_policy_injection_pipeline_parse_and_store(db_session):
    """TestPolicy 正确解析 policy 文档并持久化到 TaskPolicy 表."""
    policy = TestPolicy()
    raw = "SQL注入只允许sleep验证。SSRF使用 https://cb.net。"
    parsed = policy.parse_policy(raw)

    assert "sql_injection" in parsed
    assert "ssrf" in parsed
    assert parsed["sql_injection"]["allowed_verification"] == ["sleep"]
    assert parsed["ssrf"]["callback_url"] == "https://cb.net"

    db_session.add(
        TaskPolicy(
            task_id="task_policy_001",
            raw_policy=raw,
            parsed_policy=parsed,
            parse_status=policy.parse_status,
        )
    )
    await db_session.commit()

    result = await db_session.execute(
        select(TaskPolicy).where(TaskPolicy.task_id == "task_policy_001")
    )
    fetched = result.scalar_one()
    assert fetched.parsed_policy["sql_injection"]["allowed_verification"] == ["sleep"]


@pytest.mark.asyncio
async def test_policy_injection_pipeline_planner_subtask_has_policy_context():
    """Planner 生成的漏洞测试 subtask 包含 policy_context."""
    from core.planner import Planner
    from core.graph_manager import GraphManager

    fake_llm_client = MagicMock()
    fake_llm_client.send_message = AsyncMock(return_value=(
        {
            "graph_operations": [
                {
                    "command": "ADD_NODE",
                    "node_data": {
                        "id": "subtask_sqli_1",
                        "description": "测试登录接口的 SQL 注入漏洞",
                        "dependencies": [],
                        "priority": 1,
                    },
                }
            ]
        },
        {"prompt_tokens": 100, "completion_tokens": 50, "cost_cny": 0.01},
    ))

    planner = Planner(fake_llm_client)
    graph_manager = GraphManager("task_policy_002", "渗透测试 example.com")

    policy = TestPolicy()
    policy.parse_policy("SQL注入只允许sleep验证")

    ops, _ = await planner.plan("测试 example.com 的安全性")

    for op in ops:
        if op.get("command") == "ADD_NODE":
            node_data = op["node_data"]
            desc = node_data.get("description", "")
            vuln_type = policy.classify_vuln_type(desc)
            constraints = policy.get_constraints(vuln_type) if vuln_type else None
            extra_data = {"policy_context": constraints} if constraints else None

            graph_manager.add_subtask_node(
                subtask_id=node_data["id"],
                description=desc,
                dependencies=node_data.get("dependencies", []),
                priority=node_data.get("priority", 1),
                extra_data=extra_data,
            )

    node = graph_manager.graph.nodes["subtask_sqli_1"]
    assert "extra_data" in node
    assert "policy_context" in node["extra_data"]
    assert node["extra_data"]["policy_context"]["allowed_verification"] == ["sleep"]


@pytest.mark.asyncio
async def test_policy_injection_pipeline_executor_system_prompt_contains_constraints():
    """Executor 的 system prompt 中包含约束文本."""
    from core.executor import _build_executor_prompt
    from core.graph_manager import GraphManager

    graph_manager = GraphManager("task_policy_003", "渗透测试 example.com")
    graph_manager.add_subtask_node(
        subtask_id="subtask_sqli_1",
        description="测试登录接口的 SQL 注入漏洞",
        dependencies=[],
        priority=1,
        extra_data={"policy_context": {"allowed_verification": ["sleep"], "forbidden_keywords": ["UPDATE"]}},
    )

    messages = []
    system_prompt, updated_messages = await _build_executor_prompt(
        graph_manager=graph_manager,
        subtask_id="subtask_sqli_1",
        main_goal="渗透测试 example.com",
        global_mission_briefing="",
        messages=messages,
    )

    assert "【测试约束】" in system_prompt
    assert "sleep" in system_prompt


# ---------------------------------------------------------------------------
# Scenario 3: 跨通道去重
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cross_channel_deduplication_keeps_highest_confidence(recon_store):
    """模拟同一信息通过两个通道采集，ReconStore 中只保留一条记录，confidence 取最高值."""
    task_id = "task_dedup_001"

    # Channel 1: tool-level structured finding (high confidence)
    await recon_store.add_record(
        task_id=task_id,
        record_type="port",
        target="192.168.1.1",
        value={"number": 80, "protocol": "tcp", "state": "open"},
        source_step_id="step_nmap_1",
        confidence=1.0,
    )

    # Channel 2: LLM extraction (lower confidence)
    await recon_store.add_record(
        task_id=task_id,
        record_type="port",
        target="192.168.1.1",
        value={"number": 80, "protocol": "tcp", "state": "open"},
        source_step_id="step_llm_extract_2",
        confidence=0.8,
    )

    records = await recon_store.query_records(task_id, record_type="port")
    assert len(records) == 1
    record = records[0]
    assert record.confidence == pytest.approx(1.0)
    assert record.source_step_id == "step_llm_extract_2"  # latest wins


@pytest.mark.asyncio
async def test_cross_channel_deduplication_reverse_order(recon_store):
    """先低置信度后高置信度，结果应保留高置信度."""
    task_id = "task_dedup_002"

    # Channel 2 first (LLM extraction, lower confidence)
    await recon_store.add_record(
        task_id=task_id,
        record_type="domain",
        target="example.com",
        value={"name": "api.example.com", "is_subdomain": True},
        source_step_id="step_llm_1",
        confidence=0.75,
    )

    # Channel 1 later (tool direct, higher confidence)
    await recon_store.add_record(
        task_id=task_id,
        record_type="domain",
        target="example.com",
        value={"name": "api.example.com", "is_subdomain": True},
        source_step_id="step_subfinder_1",
        confidence=1.0,
    )

    records = await recon_store.query_records(task_id, record_type="domain")
    assert len(records) == 1
    assert records[0].confidence == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Full pipeline smoke test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_pipeline_smoke(monkeypatch, recon_store, test_client):
    """冒烟测试：验证所有关键组件可以串联运行."""
    task_id = "task_smoke_001"

    # 1. Policy setup
    policy = TestPolicy()
    policy.parse_policy("SQL注入只允许sleep验证。SSRF使用 https://cb.net。")

    # 2. Simulate nmap_scan ingestion
    raw_output = [
        b"Nmap scan report for 10.0.0.1\n",
        b"Host is up.\n",
        b"PORT   STATE SERVICE\n",
        b"8080/tcp open  http-proxy\n",
        b"",
    ]

    async def fake_exec(*args, **kwargs):
        return FakeNmapProcess(raw_output, returncode=0)

    monkeypatch.setattr(mcp_service.asyncio, "create_subprocess_shell", fake_exec)
    monkeypatch.setattr(mcp_service, "_resolve_tool_path", lambda *a, **k: "nmap")

    result = json.loads(await mcp_service.nmap_scan("10.0.0.1", ports="1-10000"))
    assert result["success"] is True
    sf = result["structured_findings"]

    # 3. Ingest into ReconStore
    for host in sf["hosts"]:
        await recon_store.add_record(
            task_id=task_id,
            record_type="ip",
            target=host["ip"],
            value={"address": host["ip"]},
            source_step_id="step_nmap_smoke",
            confidence=1.0,
        )
        for port in host.get("ports", []):
            await recon_store.add_record(
                task_id=task_id,
                record_type="port",
                target=host["ip"],
                value={"number": port["number"], "protocol": port["protocol"], "state": port["state"]},
                source_step_id="step_nmap_smoke",
                confidence=1.0,
            )

    # 4. Verify DB state
    summary = await recon_store.get_summary(task_id)
    assert summary.get("ip", 0) >= 1
    assert summary.get("port", 0) >= 1

    # 5. Verify API using a shared file-based SQLite DB
    db_file = tempfile.mktemp(suffix=".db")
    db_url = f"sqlite+aiosqlite:///{db_file}"
    try:
        shared_engine = create_async_engine(db_url, echo=False)
        async with shared_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        shared_session_maker = async_sessionmaker(shared_engine, expire_on_commit=False)
        monkeypatch.setattr("web.server.AsyncSessionLocal", shared_session_maker)

        shared_session = shared_session_maker()
        for host in sf["hosts"]:
            shared_session.add(
                ReconRecord(
                    task_id=task_id,
                    record_type="ip",
                    target=host["ip"],
                    value={"address": host["ip"]},
                    source_step_id="step_nmap_smoke",
                    confidence=1.0,
                )
            )
            for port in host.get("ports", []):
                shared_session.add(
                    ReconRecord(
                        task_id=task_id,
                        record_type="port",
                        target=host["ip"],
                        value={"number": port["number"], "protocol": port["protocol"], "state": port["state"]},
                        source_step_id="step_nmap_smoke",
                        confidence=1.0,
                    )
                )
        await shared_session.commit()

        response = test_client.get(f"/api/recon/{task_id}")
        assert response.status_code == 200
        data = response.json()
        assert any(r["record_type"] == "port" for r in data["items"])
    finally:
        await shared_engine.dispose()
        if os.path.exists(db_file):
            os.unlink(db_file)

    # 6. Verify policy constraints are queryable
    constraints = policy.get_constraints("sql_injection")
    assert constraints is not None
    assert "sleep" in constraints["allowed_verification"]
