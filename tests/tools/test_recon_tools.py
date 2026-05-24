"""
TDD tests for recon MCP tools: nmap_scan, httpx_scan, info_extract.
"""

import json
from unittest.mock import AsyncMock

import pytest

from tools import mcp_service

# ---------------------------------------------------------------------------
# nmap_scan tests
# ---------------------------------------------------------------------------

class FakeNmapProcess:
    def __init__(self, stdout_lines: list, returncode: int = 0):
        self.stdout = AsyncMock()
        self.stdout.readline = AsyncMock(side_effect=stdout_lines)
        self._returncode = returncode

    async def wait(self):
        return self._returncode


@pytest.fixture(autouse=True)
def patch_resolve_tool(monkeypatch):
    monkeypatch.setattr(
        mcp_service, "_resolve_tool_path",
        lambda name, _env_var, _default_name: name
    )


@pytest.mark.asyncio
async def test_nmap_scan_parses_host_and_ports(monkeypatch):
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

    result = json.loads(await mcp_service.nmap_scan("192.168.1.1", ports="1-1000"))

    assert result["success"] is True
    assert "structured_findings" in result
    assert "raw_output" in result

    sf = result["structured_findings"]
    assert sf["summary"]["total_hosts"] == 1
    assert sf["summary"]["up_hosts"] == 1
    assert sf["summary"]["total_open_ports"] == 3

    hosts = sf["hosts"]
    assert len(hosts) == 1
    assert hosts[0]["ip"] == "192.168.1.1"

    ports = hosts[0]["ports"]
    assert len(ports) == 3
    assert ports[0] == {"number": 80, "protocol": "tcp", "state": "open", "service": {"name": "http"}}
    assert ports[1] == {"number": 443, "protocol": "tcp", "state": "open", "service": {"name": "https"}}
    assert ports[2] == {"number": 22, "protocol": "tcp", "state": "open", "service": {"name": "ssh"}}


@pytest.mark.asyncio
async def test_nmap_scan_parses_hostname_and_os(monkeypatch):
    raw_output = [
        b"Nmap scan report for router.local (192.168.1.1)\n",
        b"Host is up (0.0010s latency).\n",
        b"MAC Address: 00:11:22:33:44:55 (TP-LINK)\n",
        b"PORT   STATE SERVICE  VERSION\n",
        b"80/tcp open  http     nginx 1.18.0\n",
        b"",
    ]

    async def fake_exec(*args, **kwargs):
        return FakeNmapProcess(raw_output, returncode=0)

    monkeypatch.setattr(mcp_service.asyncio, "create_subprocess_shell", fake_exec)

    result = json.loads(await mcp_service.nmap_scan("router.local"))
    sf = result["structured_findings"]

    assert sf["hosts"][0]["ip"] == "192.168.1.1"
    assert sf["hosts"][0]["hostname"] == "router.local"
    assert sf["hosts"][0]["mac"] == "00:11:22:33:44:55"
    assert sf["hosts"][0]["vendor"] == "TP-LINK"
    assert sf["hosts"][0]["ports"][0]["service"]["name"] == "http"
    assert sf["hosts"][0]["ports"][0]["service"]["product"] == "nginx"
    assert sf["hosts"][0]["ports"][0]["service"]["version"] == "1.18.0"


@pytest.mark.asyncio
async def test_nmap_scan_empty_result(monkeypatch):
    raw_output = [
        b"Nmap scan report for 10.0.0.99\n",
        b"Host is up.\n",
        b"All 1000 scanned ports on 10.0.0.99 are in ignored states.\n",
        b"",
    ]

    async def fake_exec(*args, **kwargs):
        return FakeNmapProcess(raw_output, returncode=0)

    monkeypatch.setattr(mcp_service.asyncio, "create_subprocess_shell", fake_exec)

    result = json.loads(await mcp_service.nmap_scan("10.0.0.99"))
    sf = result["structured_findings"]
    assert sf["hosts"][0]["ports"] == []
    assert sf["summary"]["total_open_ports"] == 0


@pytest.mark.asyncio
async def test_nmap_scan_tool_failure(monkeypatch):
    async def fake_exec(*args, **kwargs):
        return FakeNmapProcess([b"nmap: command not found\n", b""], returncode=127)

    monkeypatch.setattr(mcp_service.asyncio, "create_subprocess_shell", fake_exec)

    result = json.loads(await mcp_service.nmap_scan("192.168.1.1"))
    assert result["success"] is False
    assert result["error_type"] == "MISSING_TOOL"
    assert "structured_findings" not in result


# ---------------------------------------------------------------------------
# httpx_scan tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_httpx_scan_parses_endpoints(monkeypatch):
    raw_output = [
        b"https://example.com [200] [Example Domain]\n",
        b"https://api.example.com [404] []\n",
        b"https://admin.example.com [403] [Forbidden]\n",
        b"",
    ]

    async def fake_exec(*args, **kwargs):
        return FakeNmapProcess(raw_output, returncode=0)

    monkeypatch.setattr(mcp_service.asyncio, "create_subprocess_shell", fake_exec)

    result = json.loads(await mcp_service.httpx_scan("example.com"))

    assert result["success"] is True
    assert "structured_findings" in result

    sf = result["structured_findings"]
    assert sf["summary"]["total_urls"] == 3
    assert sf["summary"]["successful"] == 3
    assert sf["summary"]["failed"] == 0

    endpoints = sf["endpoints"]
    assert len(endpoints) == 3
    assert endpoints[0] == {
        "url": "https://example.com",
        "status_code": 200,
        "title": "Example Domain",
    }
    assert endpoints[1] == {
        "url": "https://api.example.com",
        "status_code": 404,
        "title": "",
    }
    assert endpoints[2] == {
        "url": "https://admin.example.com",
        "status_code": 403,
        "title": "Forbidden",
    }


@pytest.mark.asyncio
async def test_httpx_scan_empty_input(monkeypatch):
    async def fake_exec(*args, **kwargs):
        return FakeNmapProcess([b""], returncode=0)

    monkeypatch.setattr(mcp_service.asyncio, "create_subprocess_shell", fake_exec)

    result = json.loads(await mcp_service.httpx_scan(""))
    sf = result["structured_findings"]
    assert sf["endpoints"] == []
    assert sf["summary"]["total_urls"] == 0


@pytest.mark.asyncio
async def test_httpx_scan_tool_failure(monkeypatch):
    async def fake_exec(*args, **kwargs):
        return FakeNmapProcess([b"httpx: command not found\n", b""], returncode=127)

    monkeypatch.setattr(mcp_service.asyncio, "create_subprocess_shell", fake_exec)

    result = json.loads(await mcp_service.httpx_scan("example.com"))
    assert result["success"] is False
    assert result["error_type"] == "MISSING_TOOL"


# ---------------------------------------------------------------------------
# info_extract tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_info_extract_returns_mock_empty_records():
    result = json.loads(await mcp_service.info_extract("some raw text"))
    assert result["success"] is True
    assert result["records"] == []
    assert result["note"] == "Mock implementation; LLM-driven extraction not yet enabled."


@pytest.mark.asyncio
async def test_info_extract_accepts_context():
    result = json.loads(await mcp_service.info_extract("raw text", context="nmap output"))
    assert result["success"] is True
    assert result["records"] == []
