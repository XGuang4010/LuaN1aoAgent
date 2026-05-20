from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import domain_scanner


def test_resolve_project_tool_returns_none_without_project_env(monkeypatch):
    monkeypatch.setattr(
        domain_scanner,
        "resolve_project_tool",
        lambda *args, **kwargs: None,
    )

    resolved = domain_scanner._resolve_project_tool("subfinder")

    assert resolved is None


@pytest.mark.asyncio
async def test_cmd_scan_subdomains_fails_when_subfinder_not_configured(monkeypatch):
    monkeypatch.setattr(domain_scanner, "get_domain_target", AsyncMock(return_value=SimpleNamespace(id=1)))
    monkeypatch.setattr(domain_scanner, "update_domain_target_status", AsyncMock())
    monkeypatch.setattr(domain_scanner, "_resolve_project_tool", lambda tool_name: None)
    monkeypatch.setattr(
        domain_scanner.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("subprocess.run should not be called")),
    )

    with pytest.raises(RuntimeError, match="subfinder not configured"):
        await domain_scanner.cmd_scan_subdomains("example.com")
