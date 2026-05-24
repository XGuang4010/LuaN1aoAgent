"""Integration tests for Executor -> ReconExtractor -> ReconStore pipeline."""
import json
import pytest
import pytest_asyncio
from unittest.mock import patch

from core.recon_extractor import ReconExtractor
from core.recon_store import ReconStore
from core.database.utils import init_db, AsyncSessionLocal
from core.graph_manager import GraphManager
from core.executor import run_executor_cycle
from sqlalchemy import text


@pytest_asyncio.fixture(autouse=True)
async def _init_db():
    """Ensure fresh tables for each test."""
    await init_db()
    async with AsyncSessionLocal() as session:
        await session.execute(text("DELETE FROM recon_records"))
        await session.commit()


@pytest_asyncio.fixture
async def extractor():
    return ReconExtractor()


class _MockLLM:
    """Minimal LLM mock for executor cycle testing."""

    def __init__(self, replies):
        self._replies = replies
        self._index = 0

    async def send_message(self, messages, role="default", expect_json=True):
        reply = self._replies[self._index]
        self._index += 1
        return reply, {"prompt_tokens": 10, "completion_tokens": 10, "cost_cny": 0.01}

    async def summarize_conversation(self, messages):
        return "summary", {}


@pytest.mark.asyncio
async def test_executor_e2e_auto_extracts_recon():
    """End-to-end: Executor runs nmap_scan, ReconStore auto-ingests findings."""
    gm = GraphManager(task_id="e2e_task", goal="test", op_id="e2e_op", _skip_db_init=True)
    gm.add_subtask_node("subtask_1", description="scan target", dependencies=[])

    nmap_mock_result = json.dumps({
        "success": True,
        "raw_output": "Nmap scan report for 127.0.0.1\n80/tcp open http",
        "structured_findings": {
            "hosts": [
                {
                    "ip": "127.0.0.1",
                    "hostname": "localhost",
                    "ports": [
                        {
                            "number": 80,
                            "protocol": "tcp",
                            "state": "open",
                            "service": {"name": "http", "product": "nginx", "version": "1.18.0"},
                        }
                    ],
                }
            ],
            "summary": {"total_hosts": 1, "total_open_ports": 1},
        },
    })

    llm_reply = {
        "execution_operations": [
            {
                "command": "EXECUTE_NOW",
                "node_id": "step_1",
                "thought": "scan ports",
                "action": {"tool": "nmap_scan", "params": {"target": "127.0.0.1", "ports": "80"}},
            }
        ],
        "is_subtask_complete": True,
        "previous_steps_status": {},
        "staged_causal_nodes": [],
        "hypothesis_update": {},
    }

    mock_llm = _MockLLM([llm_reply])

    with patch("core.executor.call_mcp_tool_async", return_value=nmap_mock_result):
        subtask_id, status, metrics = await run_executor_cycle(
            main_goal="test goal",
            subtask_id="subtask_1",
            llm=mock_llm,
            graph_manager=gm,
            max_steps=5,
            output_mode="simple",
        )

    assert status == "completed"

    # Verify ReconStore has auto-ingested records
    store = ReconStore()
    ips = await store.query_records("e2e_task", record_type="ip")
    assert len(ips) == 1
    assert ips[0].value["address"] == "127.0.0.1"

    ports = await store.query_records("e2e_task", record_type="port")
    assert len(ports) == 1
    assert ports[0].value["number"] == 80

    services = await store.query_records("e2e_task", record_type="service")
    assert len(services) == 1
    assert services[0].value["name"] == "http"

    domains = await store.query_records("e2e_task", record_type="domain")
    assert len(domains) == 1
    assert domains[0].value["name"] == "localhost"


@pytest.mark.asyncio
async def test_extract_nmap_structured_findings(extractor):
    e = extractor
    nmap_result = json.dumps({
        "success": True,
        "raw_output": "...",
        "structured_findings": {
            "hosts": [
                {
                    "ip": "192.168.1.1",
                    "hostname": "router.local",
                    "ports": [
                        {
                            "number": 80,
                            "protocol": "tcp",
                            "state": "open",
                            "service": {"name": "http", "product": "nginx", "version": "1.18.0"},
                        },
                        {
                            "number": 443,
                            "protocol": "tcp",
                            "state": "open",
                            "service": {"name": "https"},
                        },
                    ],
                }
            ],
            "summary": {"total_hosts": 1, "total_open_ports": 2},
        },
    })

    await e.extract_from_tool_result("task_1", "step_1", "nmap_scan", {}, nmap_result)

    store = e.store
    ips = await store.query_records("task_1", record_type="ip")
    assert len(ips) == 1
    assert ips[0].value["address"] == "192.168.1.1"

    ports = await store.query_records("task_1", record_type="port")
    assert len(ports) == 2
    port_numbers = {p.value["number"] for p in ports}
    assert port_numbers == {80, 443}

    services = await store.query_records("task_1", record_type="service")
    assert len(services) == 2
    service_names = {s.value["name"] for s in services}
    assert service_names == {"http", "https"}
    http_service = next(s for s in services if s.value["name"] == "http")
    assert http_service.value["version"] == "1.18.0"

    domains = await store.query_records("task_1", record_type="domain")
    assert len(domains) == 1
    assert domains[0].value["name"] == "router.local"


@pytest.mark.asyncio
async def test_extract_httpx_structured_findings(extractor):
    e = extractor
    httpx_result = json.dumps({
        "success": True,
        "raw_output": "...",
        "structured_findings": {
            "endpoints": [
                {"url": "https://api.example.com/v1/users", "status_code": 200, "title": "User API"},
                {"url": "https://admin.example.com/login", "status_code": 301, "title": "Redirect"},
            ],
            "summary": {"total_urls": 2},
        },
    })

    await e.extract_from_tool_result("task_1", "step_2", "httpx_scan", {}, httpx_result)

    store = e.store
    endpoints = await store.query_records("task_1", record_type="endpoint")
    assert len(endpoints) == 2
    urls = {ep.value["url"] for ep in endpoints}
    assert urls == {"https://api.example.com/v1/users", "https://admin.example.com/login"}


@pytest.mark.asyncio
async def test_extract_no_structured_findings(extractor):
    e = extractor
    plain_result = json.dumps({"success": True, "output": "hello world"})

    await e.extract_from_tool_result("task_1", "step_3", "shell_exec", {}, plain_result)

    store = e.store
    all_recs = await store.query_records("task_1")
    assert len(all_recs) == 0


@pytest.mark.asyncio
async def test_extract_invalid_json(extractor):
    e = extractor
    await e.extract_from_tool_result("task_1", "step_4", "shell_exec", {}, "not json")

    store = e.store
    all_recs = await store.query_records("task_1")
    assert len(all_recs) == 0


@pytest.mark.asyncio
async def test_extract_dedup_same_records(extractor):
    e = extractor
    nmap_result = json.dumps({
        "success": True,
        "structured_findings": {
            "hosts": [
                {
                    "ip": "1.2.3.4",
                    "ports": [
                        {"number": 22, "protocol": "tcp", "state": "open", "service": {"name": "ssh"}},
                    ],
                }
            ],
        },
    })

    await e.extract_from_tool_result("task_1", "step_a", "nmap_scan", {}, nmap_result)
    await e.extract_from_tool_result("task_1", "step_b", "nmap_scan", {}, nmap_result)

    store = e.store
    ips = await store.query_records("task_1", record_type="ip")
    assert len(ips) == 1  # deduped
    assert ips[0].source_step_id == "step_b"  # latest wins

    ports = await store.query_records("task_1", record_type="port")
    assert len(ports) == 1
