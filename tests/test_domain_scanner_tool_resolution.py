import types

import pytest

import domain_scanner


class _FakeTempFile:
    def __init__(self, path):
        self.name = path
        self._content = []

    def write(self, text):
        self._content.append(text)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_cmd_scan_subdomains_uses_resolved_subfinder(monkeypatch):
    calls = []

    async def fake_get_domain_target(domain):
        return types.SimpleNamespace(id=1, domain=domain)

    async def fake_async_noop(*args, **kwargs):
        return None

    class FakeResult:
        def __init__(self, stdout="", stderr=""):
            self.stdout = stdout
            self.stderr = stderr

    monkeypatch.setattr(
        domain_scanner,
        "get_domain_target",
        fake_get_domain_target,
    )
    monkeypatch.setattr(
        domain_scanner, "update_domain_target_status", fake_async_noop
    )
    monkeypatch.setattr(domain_scanner, "add_subdomain", fake_async_noop)
    monkeypatch.setattr(
        domain_scanner,
        "_resolve_project_tool",
        lambda tool: (
            r"D:\Tools\PentestWorkspace\subfinder\subfinder.exe"
            if tool == "subfinder"
            else r"D:\Tools\PentestWorkspace\httpx\httpx.exe"
        ),
    )

    def fake_run(args, **kwargs):
        calls.append(args)
        if "subfinder" in args[0].lower():
            return FakeResult(stdout="a.example.com\n")
        return FakeResult(stdout="")

    monkeypatch.setattr(domain_scanner.subprocess, "run", fake_run)
    monkeypatch.setattr(
        domain_scanner.tempfile,
        "NamedTemporaryFile",
        lambda **kwargs: _FakeTempFile("fake-subdomains.txt"),
    )
    monkeypatch.setattr(domain_scanner.os, "unlink", lambda path: None)

    await domain_scanner.cmd_scan_subdomains("example.com", use_subfinder=True)

    assert calls[0][0] == r"D:\Tools\PentestWorkspace\subfinder\subfinder.exe"


@pytest.mark.asyncio
async def test_cmd_scan_subdomains_uses_resolved_httpx(monkeypatch):
    calls = []

    async def fake_get_domain_target(domain):
        return types.SimpleNamespace(id=1, domain=domain)

    async def fake_async_noop(*args, **kwargs):
        return None

    class FakeResult:
        def __init__(self, stdout="", stderr=""):
            self.stdout = stdout
            self.stderr = stderr

    monkeypatch.setattr(
        domain_scanner,
        "get_domain_target",
        fake_get_domain_target,
    )
    monkeypatch.setattr(
        domain_scanner, "update_domain_target_status", fake_async_noop
    )
    monkeypatch.setattr(domain_scanner, "add_subdomain", fake_async_noop)
    monkeypatch.setattr(
        domain_scanner,
        "_resolve_project_tool",
        lambda tool: (
            r"D:\Tools\PentestWorkspace\subfinder\subfinder.exe"
            if tool == "subfinder"
            else r"D:\Tools\PentestWorkspace\httpx\httpx.exe"
        ),
    )

    def fake_run(args, **kwargs):
        calls.append(args)
        if "subfinder" in args[0].lower():
            return FakeResult(stdout="a.example.com\n")
        return FakeResult(stdout="")

    monkeypatch.setattr(domain_scanner.subprocess, "run", fake_run)
    monkeypatch.setattr(
        domain_scanner.tempfile,
        "NamedTemporaryFile",
        lambda **kwargs: _FakeTempFile("fake-subdomains.txt"),
    )
    monkeypatch.setattr(domain_scanner.os, "unlink", lambda path: None)

    await domain_scanner.cmd_scan_subdomains("example.com", use_subfinder=True)

    assert calls[1][0] == r"D:\Tools\PentestWorkspace\httpx\httpx.exe"
