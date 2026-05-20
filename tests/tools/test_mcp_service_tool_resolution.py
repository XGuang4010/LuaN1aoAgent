from tools import mcp_service


def test_resolve_external_tool_prefers_explicit_env(monkeypatch):
    monkeypatch.setenv(
        "NUCLEI_PATH", r"D:\Tools\PentestWorkspace\nuclei\nuclei.exe"
    )
    monkeypatch.setenv("TOOLS_HOME", r"D:\Tools\PentestWorkspace")
    monkeypatch.setattr(
        mcp_service.os.path,
        "exists",
        lambda path: path == r"D:\Tools\PentestWorkspace\nuclei\nuclei.exe",
    )
    monkeypatch.setattr(
        mcp_service.shutil, "which", lambda name: r"C:\Elsewhere\nuclei.exe"
    )

    resolved = mcp_service._resolve_external_tool(
        tool_name="nuclei",
        env_var_name="NUCLEI_PATH",
        tools_home_subpath=r"nuclei\nuclei.exe",
    )

    assert resolved == r"D:\Tools\PentestWorkspace\nuclei\nuclei.exe"


def test_resolve_external_tool_uses_tools_home_before_path(monkeypatch):
    monkeypatch.delenv("NUCLEI_PATH", raising=False)
    monkeypatch.setenv("TOOLS_HOME", r"D:\Tools\PentestWorkspace")
    monkeypatch.setattr(
        mcp_service.os.path,
        "exists",
        lambda path: path == r"D:\Tools\PentestWorkspace\nuclei\nuclei.exe",
    )
    monkeypatch.setattr(
        mcp_service.shutil, "which", lambda name: r"C:\Elsewhere\nuclei.exe"
    )

    resolved = mcp_service._resolve_external_tool(
        tool_name="nuclei",
        env_var_name="NUCLEI_PATH",
        tools_home_subpath=r"nuclei\nuclei.exe",
    )

    assert resolved == r"D:\Tools\PentestWorkspace\nuclei\nuclei.exe"


def test_resolve_external_tool_falls_back_to_path(monkeypatch):
    monkeypatch.delenv("NUCLEI_PATH", raising=False)
    monkeypatch.delenv("TOOLS_HOME", raising=False)
    monkeypatch.setattr(mcp_service.os.path, "exists", lambda path: False)
    monkeypatch.setattr(
        mcp_service.shutil, "which", lambda name: r"C:\Elsewhere\nuclei.exe"
    )

    resolved = mcp_service._resolve_external_tool(
        tool_name="nuclei",
        env_var_name="NUCLEI_PATH",
        tools_home_subpath=r"nuclei\nuclei.exe",
    )

    assert resolved == r"C:\Elsewhere\nuclei.exe"


def test_validate_httpx_rejects_python_httpx_cli():
    help_text = "HTTPX \U0001f98b\n\nA next generation HTTP client."

    assert mcp_service._is_compatible_projectdiscovery_httpx(help_text) is False


def test_validate_httpx_accepts_projectdiscovery_httpx():
    help_text = "httpx is a fast and multi-purpose HTTP toolkit"

    assert mcp_service._is_compatible_projectdiscovery_httpx(help_text) is True
