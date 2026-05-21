import json
from unittest.mock import AsyncMock

import pytest

from tools import mcp_service


@pytest.mark.asyncio
async def test_dirsearch_scan_returns_explicit_success_contract(monkeypatch):
    class FakeProcess:
        def __init__(self):
            self.stdout = AsyncMock()
            self.stdout.readline = AsyncMock(
                side_effect=[
                    b"[12:00:00] 200 -    0B  - https://api.dxmpay.com/.git/config\r\n",
                    b"",
                ]
            )

        async def wait(self):
            return 0

    async def fake_exec(*args, **kwargs):
        return FakeProcess()

    monkeypatch.setattr(mcp_service, "_resolve_dirsearch_executable", lambda: "dirsearch")
    monkeypatch.setattr(mcp_service, "_normalize_dirsearch_args", lambda extra_args: ([], []))
    monkeypatch.setattr(mcp_service.asyncio, "create_subprocess_exec", fake_exec)

    payload = json.loads(
        await mcp_service.dirsearch_scan("https://api.dxmpay.com/", "php", "")
    )

    assert payload["success"] is True
    assert payload["status"] == "success"
    assert "completed" in payload["message"].lower()
    assert payload["findings_count"] == 1


@pytest.mark.asyncio
async def test_subfinder_scan_returns_explicit_success_contract(monkeypatch):
    class FakeProcess:
        returncode = 0

        async def communicate(self):
            return (b"www.dxmpay.com\napi.dxmpay.com\n", b"")

    async def fake_exec(*args, **kwargs):
        return FakeProcess()

    monkeypatch.setattr(mcp_service, "_resolve_external_tool", lambda *args, **kwargs: "subfinder")
    monkeypatch.setattr(mcp_service.asyncio, "create_subprocess_exec", fake_exec)

    payload = json.loads(await mcp_service.subfinder_scan("dxmpay.com", silent=True))

    assert payload["success"] is True
    assert payload["status"] == "success"
    assert payload["count"] == 2
    assert "completed" in payload["message"].lower()


@pytest.mark.asyncio
async def test_nuclei_scan_timeout_returns_explicit_timeout_contract(monkeypatch):
    class FakeProcess:
        def kill(self):
            pass

        async def wait(self):
            return 0

        async def communicate(self):
            return (b"", b"")

    async def fake_exec(*args, **kwargs):
        return FakeProcess()

    async def fake_wait_for(awaitable, timeout):
        awaitable.close()
        raise asyncio.TimeoutError()

    import asyncio

    monkeypatch.setattr(mcp_service, "_resolve_external_tool", lambda *args, **kwargs: "nuclei")
    monkeypatch.setattr(mcp_service.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(mcp_service.asyncio, "wait_for", fake_wait_for)

    payload = json.loads(
        await mcp_service.nuclei_scan("https://api.dxmpay.com", timeout=60)
    )

    assert payload["success"] is False
    assert payload["status"] == "timeout"
    assert payload["error_type"] == "TIMEOUT"
