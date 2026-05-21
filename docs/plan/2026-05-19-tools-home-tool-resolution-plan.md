# TOOLS_HOME Tool Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让当前项目中已有的外部工具调用点支持 `TOOLS_HOME=D:\Tools\PentestWorkspace` 与单工具环境变量，并避免 `httpx` 误命中 Python CLI。

**Architecture:** 以 `tools/mcp_service.py` 作为统一工具解析入口，新增一个最小 `_resolve_external_tool()` 能力，并把 `sqlmap`、`dirsearch`、`nuclei`、`subfinder`、`httpx`、`searchsploit` 的所有现有调用点切到该入口。对 `domain_scanner.py` 只做同样的最小接线，不扩展其它模块；`httpx` 增加一个轻量校验，防止回退到 `PATH` 时误用 Python 版本。

**Tech Stack:** Python 3.10+, pytest, pytest-asyncio, subprocess, shutil, os

---

## 文件地图

### 新增文件

- `d:\Projects\LuaN1aoAgent\tests\tools\test_mcp_service_tool_resolution.py`
  - 覆盖统一工具解析逻辑、`httpx` 校验与 `mcp_service.py` 中关键调用点的命令构造。
- `d:\Projects\LuaN1aoAgent\tests\test_domain_scanner_tool_resolution.py`
  - 覆盖 `domain_scanner.py` 中 `subfinder` / `httpx` 的直接调用点。

### 修改文件

- `d:\Projects\LuaN1aoAgent\tools\mcp_service.py`
  - 增加统一工具解析函数、`httpx` 兼容校验，并替换所有外部工具调用点。
- `d:\Projects\LuaN1aoAgent\domain_scanner.py`
  - 复用统一工具解析逻辑或复制最小兼容辅助函数，使扫描路径也受 `TOOLS_HOME` 控制。
- `d:\Projects\LuaN1aoAgent\.env.example`
  - 补充 `TOOLS_HOME` 与单工具环境变量示例。

---

## 环境约定

实现和验收统一按以下目录：

```ini
TOOLS_HOME=D:\Tools\PentestWorkspace
SQLMAP_PATH=
DIRSEARCH_PATH=
NUCLEI_PATH=
SUBFINDER_PATH=
PD_HTTPX_PATH=
SEARCHSPLOIT_PATH=
```

默认期望文件：

```text
D:\Tools\PentestWorkspace\sqlmap\sqlmap.exe
D:\Tools\PentestWorkspace\dirsearch\dirsearch.exe
D:\Tools\PentestWorkspace\nuclei\nuclei.exe
D:\Tools\PentestWorkspace\subfinder\subfinder.exe
D:\Tools\PentestWorkspace\httpx\httpx.exe
D:\Tools\PentestWorkspace\searchsploit\searchsploit.exe
```

---

### Task 1: 写统一工具解析红灯测试

**Files:**
- Create: `d:\Projects\LuaN1aoAgent\tests\tools\test_mcp_service_tool_resolution.py`

- [ ] **Step 1: 写失败测试，固定解析优先级**

```python
from tools import mcp_service


def test_resolve_external_tool_prefers_explicit_env(monkeypatch):
    monkeypatch.setenv("NUCLEI_PATH", r"D:\Tools\PentestWorkspace\nuclei\nuclei.exe")
    monkeypatch.setenv("TOOLS_HOME", r"D:\Tools\PentestWorkspace")
    monkeypatch.setattr(mcp_service.os.path, "exists", lambda path: path == r"D:\Tools\PentestWorkspace\nuclei\nuclei.exe")
    monkeypatch.setattr(mcp_service.shutil, "which", lambda name: r"C:\Elsewhere\nuclei.exe")

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
    monkeypatch.setattr(mcp_service.shutil, "which", lambda name: r"C:\Elsewhere\nuclei.exe")

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
    monkeypatch.setattr(mcp_service.shutil, "which", lambda name: r"C:\Elsewhere\nuclei.exe")

    resolved = mcp_service._resolve_external_tool(
        tool_name="nuclei",
        env_var_name="NUCLEI_PATH",
        tools_home_subpath=r"nuclei\nuclei.exe",
    )

    assert resolved == r"C:\Elsewhere\nuclei.exe"
```

- [ ] **Step 2: 写失败测试，固定 `httpx` 误命中规则**

```python
from tools import mcp_service


def test_validate_httpx_rejects_python_httpx_cli():
    help_text = "HTTPX \U0001f98b\n\nA next generation HTTP client."
    assert mcp_service._is_compatible_projectdiscovery_httpx(help_text) is False


def test_validate_httpx_accepts_projectdiscovery_httpx():
    help_text = "httpx is a fast and multi-purpose HTTP toolkit"
    assert mcp_service._is_compatible_projectdiscovery_httpx(help_text) is True
```

- [ ] **Step 3: 运行测试确认失败**

Run:

```powershell
& 'd:\Projects\LuaN1aoAgent\venv\Scripts\python.exe' -m pytest d:\Projects\LuaN1aoAgent\tests\tools\test_mcp_service_tool_resolution.py -v
```

Expected:

```text
AttributeError: module 'tools.mcp_service' has no attribute '_resolve_external_tool'
```

- [ ] **Step 4: 提交**

```bash
git add tests/tools/test_mcp_service_tool_resolution.py
git commit -m "test: add tools home resolution coverage"
```

---

### Task 2: 在 `mcp_service.py` 实现统一工具解析

**Files:**
- Modify: `d:\Projects\LuaN1aoAgent\tools\mcp_service.py`
- Test: `d:\Projects\LuaN1aoAgent\tests\tools\test_mcp_service_tool_resolution.py`

- [ ] **Step 1: 增加最小工具解析与 `httpx` 校验函数**

```python
def _resolve_external_tool(
    tool_name: str,
    env_var_name: str,
    tools_home_subpath: str,
    fallback_names: list[str] | None = None,
) -> str | None:
    explicit = os.getenv(env_var_name, "").strip()
    if explicit and os.path.exists(explicit):
        return explicit

    tools_home = os.getenv("TOOLS_HOME", "").strip()
    if tools_home:
        candidate = os.path.join(tools_home, tools_home_subpath)
        if os.path.exists(candidate):
            return candidate

    for name in [tool_name, *(fallback_names or [])]:
        resolved = shutil.which(name)
        if resolved:
            return resolved

    return None


def _is_compatible_projectdiscovery_httpx(help_text: str) -> bool:
    lowered = help_text.lower()
    if "a next generation http client" in lowered:
        return False
    return "projectdiscovery" in lowered or "http toolkit" in lowered or "-tech-detect" in lowered


def _resolve_httpx_executable() -> str | None:
    explicit = _resolve_external_tool(
        tool_name="httpx",
        env_var_name="PD_HTTPX_PATH",
        tools_home_subpath=os.path.join("httpx", "httpx.exe"),
    )
    if not explicit:
        return None

    if os.getenv("PD_HTTPX_PATH", "").strip() or (
        os.getenv("TOOLS_HOME", "").strip()
        and explicit.lower().startswith(os.getenv("TOOLS_HOME", "").strip().lower())
    ):
        return explicit

    try:
        result = subprocess.run([explicit, "--help"], capture_output=True, text=True, timeout=5)
        if _is_compatible_projectdiscovery_httpx(result.stdout + "\n" + result.stderr):
            return explicit
    except Exception:
        pass

    return None
```

- [ ] **Step 2: 替换 `mcp_service.py` 中所有工具命令入口**

```python
sqlmap_executable = _resolve_external_tool("sqlmap", "SQLMAP_PATH", os.path.join("sqlmap", "sqlmap.exe"))
if not sqlmap_executable:
    return json.dumps({
        "success": False,
        "error": "sqlmap command not found. Checked SQLMAP_PATH, TOOLS_HOME, and PATH.",
        "error_type": "TOOL_MISSING",
    }, ensure_ascii=False)
cmd = [sqlmap_executable]
```

```python
def _resolve_dirsearch_executable() -> str | None:
    return _resolve_external_tool(
        tool_name="dirsearch",
        env_var_name="DIRSEARCH_PATH",
        tools_home_subpath=os.path.join("dirsearch", "dirsearch.exe"),
        fallback_names=["dirsearch.py"],
    )
```

```python
nuclei_executable = _resolve_external_tool("nuclei", "NUCLEI_PATH", os.path.join("nuclei", "nuclei.exe"))
subfinder_executable = _resolve_external_tool("subfinder", "SUBFINDER_PATH", os.path.join("subfinder", "subfinder.exe"))
searchsploit_executable = _resolve_external_tool("searchsploit", "SEARCHSPLOIT_PATH", os.path.join("searchsploit", "searchsploit.exe"))
httpx_executable = _resolve_httpx_executable()
```

- [ ] **Step 3: 写命令构造测试，确保传入的是绝对路径**

```python
import json
from unittest.mock import AsyncMock

import pytest

from tools import mcp_service


@pytest.mark.asyncio
async def test_nuclei_scan_uses_resolved_executable(monkeypatch):
    calls = {}

    class FakeProcess:
        async def communicate(self):
            return b"", b""

        async def wait(self):
            return 0

    async def fake_exec(*args, **kwargs):
        calls["args"] = args
        return FakeProcess()

    monkeypatch.setattr(
        mcp_service,
        "_resolve_external_tool",
        lambda tool_name, env_var_name, tools_home_subpath, fallback_names=None: r"D:\Tools\PentestWorkspace\nuclei\nuclei.exe",
    )
    monkeypatch.setattr(mcp_service.asyncio, "create_subprocess_exec", fake_exec)

    payload = json.loads(await mcp_service.nuclei_scan("https://example.com"))

    assert payload["status"] == "success"
    assert calls["args"][0] == r"D:\Tools\PentestWorkspace\nuclei\nuclei.exe"
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```powershell
& 'd:\Projects\LuaN1aoAgent\venv\Scripts\python.exe' -m pytest d:\Projects\LuaN1aoAgent\tests\tools\test_mcp_service_tool_resolution.py -v
```

Expected:

```text
PASSED
```

- [ ] **Step 5: 提交**

```bash
git add tools/mcp_service.py tests/tools/test_mcp_service_tool_resolution.py
git commit -m "feat: add tools home resolution for mcp service"
```

---

### Task 3: 让 `domain_scanner.py` 接入同一解析规则

**Files:**
- Modify: `d:\Projects\LuaN1aoAgent\domain_scanner.py`
- Test: `d:\Projects\LuaN1aoAgent\tests\test_domain_scanner_tool_resolution.py`

- [ ] **Step 1: 写失败测试，固定 `subfinder` / `httpx` 的调用路径**

```python
import pytest

import domain_scanner


@pytest.mark.asyncio
async def test_cmd_scan_subdomains_uses_resolved_subfinder(monkeypatch):
    calls = {}

    async def fake_add_subdomain(*args, **kwargs):
        return None

    class FakeResult:
        stdout = "a.example.com\n"
        stderr = ""

    monkeypatch.setattr(domain_scanner, "get_domain_target", lambda domain: type("Target", (), {"id": 1})())
    monkeypatch.setattr(domain_scanner, "update_domain_target_status", fake_add_subdomain)
    monkeypatch.setattr(domain_scanner, "add_subdomain", fake_add_subdomain)
    monkeypatch.setattr(domain_scanner, "_resolve_project_tool", lambda tool: r"D:\Tools\PentestWorkspace\subfinder\subfinder.exe")

    def fake_run(args, **kwargs):
        calls["args"] = args
        return FakeResult()

    monkeypatch.setattr(domain_scanner.subprocess, "run", fake_run)

    await domain_scanner.cmd_scan_subdomains("example.com", use_subfinder=True)

    assert calls["args"][0] == r"D:\Tools\PentestWorkspace\subfinder\subfinder.exe"
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
& 'd:\Projects\LuaN1aoAgent\venv\Scripts\python.exe' -m pytest d:\Projects\LuaN1aoAgent\tests\test_domain_scanner_tool_resolution.py -v
```

Expected:

```text
AttributeError: module 'domain_scanner' has no attribute '_resolve_project_tool'
```

- [ ] **Step 3: 在 `domain_scanner.py` 增加最小接线**

```python
def _resolve_project_tool(tool_name: str) -> str | None:
    mapping = {
        "subfinder": ("SUBFINDER_PATH", os.path.join("subfinder", "subfinder.exe")),
        "httpx": ("PD_HTTPX_PATH", os.path.join("httpx", "httpx.exe")),
    }
    env_var, subpath = mapping[tool_name]

    explicit = os.getenv(env_var, "").strip()
    if explicit and os.path.exists(explicit):
        return explicit

    tools_home = os.getenv("TOOLS_HOME", "").strip()
    if tools_home:
        candidate = os.path.join(tools_home, subpath)
        if os.path.exists(candidate):
            return candidate

    resolved = shutil.which(tool_name)
    return resolved
```

```python
subfinder_executable = _resolve_project_tool("subfinder") or "subfinder"
result = subprocess.run(
    [subfinder_executable, "-d", domain, "-silent"],
    capture_output=True,
    text=True,
    timeout=300,
)
```

```python
httpx_executable = _resolve_project_tool("httpx") or "httpx"
result = subprocess.run(
    [httpx_executable, "-l", temp_file, "-sc", "-silent"],
    capture_output=True,
    text=True,
    timeout=300,
)
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```powershell
& 'd:\Projects\LuaN1aoAgent\venv\Scripts\python.exe' -m pytest d:\Projects\LuaN1aoAgent\tests\test_domain_scanner_tool_resolution.py -v
```

Expected:

```text
PASSED
```

- [ ] **Step 5: 提交**

```bash
git add domain_scanner.py tests/test_domain_scanner_tool_resolution.py
git commit -m "feat: route domain scanner tools through tools home"
```

---

### Task 4: 配置示例与工具安装

**Files:**
- Modify: `d:\Projects\LuaN1aoAgent\.env.example`

- [ ] **Step 1: 在 `.env.example` 增加工具环境变量示例**

```ini
# Project-level tool resolution
TOOLS_HOME=D:\Tools\PentestWorkspace
# SQLMAP_PATH=
# DIRSEARCH_PATH=
# NUCLEI_PATH=
# SUBFINDER_PATH=
# PD_HTTPX_PATH=
# SEARCHSPLOIT_PATH=
```

- [ ] **Step 2: 创建工具目录**

Run:

```powershell
New-Item -ItemType Directory -Force D:\Tools\PentestWorkspace\sqlmap | Out-Null
New-Item -ItemType Directory -Force D:\Tools\PentestWorkspace\dirsearch | Out-Null
New-Item -ItemType Directory -Force D:\Tools\PentestWorkspace\nuclei | Out-Null
New-Item -ItemType Directory -Force D:\Tools\PentestWorkspace\subfinder | Out-Null
New-Item -ItemType Directory -Force D:\Tools\PentestWorkspace\httpx | Out-Null
New-Item -ItemType Directory -Force D:\Tools\PentestWorkspace\searchsploit | Out-Null
```

Expected:

```text
No errors
```

- [ ] **Step 3: 安装或复制可执行文件到目标目录**

Run:

```powershell
Copy-Item C:\Users\davii\AppData\Roaming\Python\Python314\Scripts\sqlmap.exe D:\Tools\PentestWorkspace\sqlmap\sqlmap.exe -Force
Copy-Item C:\Users\davii\AppData\Roaming\Python\Python314\Scripts\dirsearch.exe D:\Tools\PentestWorkspace\dirsearch\dirsearch.exe -Force
```

Run:

```powershell
go install github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest
go install github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest
go install github.com/projectdiscovery/httpx/cmd/httpx@latest
Copy-Item C:\Users\davii\sdk\go\bin\nuclei.exe D:\Tools\PentestWorkspace\nuclei\nuclei.exe -Force
Copy-Item C:\Users\davii\sdk\go\bin\subfinder.exe D:\Tools\PentestWorkspace\subfinder\subfinder.exe -Force
Copy-Item C:\Users\davii\sdk\go\bin\httpx.exe D:\Tools\PentestWorkspace\httpx\httpx.exe -Force
```

Run:

```powershell
# Windows 原生若无 searchsploit，可暂不安装；先用显式环境变量占位策略保留支持
```

- [ ] **Step 4: 写入本地 `.env`**

Run:

```powershell
Add-Content d:\Projects\LuaN1aoAgent\.env \"`nTOOLS_HOME=D:\Tools\PentestWorkspace\"
```

Expected:

```text
TOOLS_HOME is present in .env
```

- [ ] **Step 5: 提交**

```bash
git add .env.example
git commit -m "docs: add tools home environment examples"
```

---

### Task 5: 回归验证与服务侧验收

**Files:**
- Modify: `d:\Projects\LuaN1aoAgent\tools\mcp_service.py`
- Modify: `d:\Projects\LuaN1aoAgent\domain_scanner.py`
- Test: `d:\Projects\LuaN1aoAgent\tests\tools\test_mcp_service_tool_resolution.py`
- Test: `d:\Projects\LuaN1aoAgent\tests\test_domain_scanner_tool_resolution.py`

- [ ] **Step 1: 运行全部新增测试**

Run:

```powershell
& 'd:\Projects\LuaN1aoAgent\venv\Scripts\python.exe' -m pytest `
  d:\Projects\LuaN1aoAgent\tests\tools\test_mcp_service_tool_resolution.py `
  d:\Projects\LuaN1aoAgent\tests\test_domain_scanner_tool_resolution.py -v
```

Expected:

```text
PASSED
```

- [ ] **Step 2: 直接验证解析结果**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$code = @'
from tools.mcp_service import _resolve_external_tool, _resolve_httpx_executable
import os
os.environ["TOOLS_HOME"] = r"D:\Tools\PentestWorkspace"
print(_resolve_external_tool("nuclei", "NUCLEI_PATH", r"nuclei\nuclei.exe"))
print(_resolve_external_tool("subfinder", "SUBFINDER_PATH", r"subfinder\subfinder.exe"))
print(_resolve_httpx_executable())
'@
& 'd:\Projects\LuaN1aoAgent\venv\Scripts\python.exe' -c $code
```

Expected:

```text
D:\Tools\PentestWorkspace\nuclei\nuclei.exe
D:\Tools\PentestWorkspace\subfinder\subfinder.exe
D:\Tools\PentestWorkspace\httpx\httpx.exe
```

- [ ] **Step 3: 重启服务并验证任务链路**

Run:

```powershell
# 重启 web.server 与 agent 任务后，观察 mcp_service 不再报 MISSING_TOOL
```

Expected:

```text
工具缺失错误消失，调用路径命中 TOOLS_HOME
```

- [ ] **Step 4: 提交**

```bash
git add tools/mcp_service.py domain_scanner.py tests/tools/test_mcp_service_tool_resolution.py tests/test_domain_scanner_tool_resolution.py .env.example
git commit -m "feat: support tools home tool resolution"
```

---

## 自检结论

- 覆盖性：已覆盖设计文档要求的所有调用点、`httpx` 特殊规则、测试与安装验证。
- 占位符检查：无 `TBD` / `TODO` / “稍后实现”。
- 一致性：统一使用 `TOOLS_HOME + 单工具环境变量 + PATH` 三层解析规则，`httpx` 始终使用 `PD_HTTPX_PATH` 命名。

---

Plan complete and saved to `docs/plan/2026-05-19-tools-home-tool-resolution-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
