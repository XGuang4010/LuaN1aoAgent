import json
from unittest.mock import AsyncMock

import pytest

from tools import mcp_service
from tools.mcp_service import _classify_dirsearch_failure, _normalize_dirsearch_args


def test_normalize_dirsearch_args_removes_missing_linux_wordlist(monkeypatch):
    monkeypatch.setattr("tools.mcp_service.os.path.exists", lambda path: False)

    args, warnings = _normalize_dirsearch_args(
        extra_args="-w /usr/share/wordlists/dirb/common.txt -t 20 --timeout=15"
    )

    assert "-w" not in args
    assert "/usr/share/wordlists/dirb/common.txt" not in args
    assert "-t" in args
    assert "--timeout=15" in args
    assert any("wordlist" in warning.lower() for warning in warnings)


def test_normalize_dirsearch_args_preserves_windows_backslashes(monkeypatch):
    monkeypatch.setattr("tools.mcp_service.os.name", "nt")
    monkeypatch.setattr("tools.mcp_service.os.path.exists", lambda path: True)

    args, warnings = _normalize_dirsearch_args(
        extra_args=r"-w C:\tools\common.txt -t 20"
    )

    assert warnings == []
    assert "-w" in args
    assert r"C:\tools\common.txt" in args
    assert r"C:toolscommon.txt" not in args


def test_classify_dirsearch_failure_detects_missing_pkg_resources():
    result = _classify_dirsearch_failure(
        "ModuleNotFoundError: No module named 'pkg_resources'",
        return_code=1,
    )

    assert result["error_type"] == "MISSING_RUNTIME_DEPENDENCY"
    assert "pkg_resources" in result["output"]


def test_classify_dirsearch_failure_detects_missing_tool():
    result = _classify_dirsearch_failure(
        "'dirsearch' is not recognized as an internal or external command",
        return_code=1,
    )

    assert result["error_type"] == "MISSING_TOOL"


def test_classify_dirsearch_failure_detects_missing_wordlist():
    result = _classify_dirsearch_failure(
        "Wordlist 'common.txt' does not exist",
        return_code=1,
    )

    assert result["error_type"] == "MISSING_WORDLIST"


@pytest.mark.asyncio
async def test_dirsearch_scan_uses_exec_style_arguments(monkeypatch):
    calls = {}

    class FakeProcess:
        def __init__(self):
            self.stdout = AsyncMock()
            self.stdout.readline = AsyncMock(side_effect=[b""])

        async def wait(self):
            return 0

    async def fake_exec(*args, **kwargs):
        calls["args"] = args
        calls["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(mcp_service, "_resolve_dirsearch_executable", lambda: "dirsearch")
    monkeypatch.setattr(
        mcp_service,
        "_normalize_dirsearch_args",
        lambda extra_args: (["-t", "10"], []),
    )
    monkeypatch.setattr(mcp_service.asyncio, "create_subprocess_exec", fake_exec)

    payload = json.loads(
        await mcp_service.dirsearch_scan("https://example.com", "php", "-t 10")
    )

    assert payload["success"] is True
    assert calls["args"][:5] == ("dirsearch", "-u", "https://example.com", "-e", "php")
