# Project Local Tool Env Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 统一 `mcp_service.py` 与 `domain_scanner.py` 的工具环境来源，使它们只依赖项目根目录 `.env` 中的 `TOOLS_HOME` 与单工具路径变量，并明确拒绝系统环境变量与 `PATH` 兜底。

**Architecture:** 新增 `tools/tool_env.py` 作为唯一的项目级工具环境读取入口，负责加载项目根目录 `.env`、解析 `TOOLS_HOME` 与单工具路径，并返回明确的解析结果。`tools/mcp_service.py` 与 `domain_scanner.py` 全部改为复用该入口；测试覆盖“存在项目级配置可解析”和“缺配置直接失败”两类行为。

**Tech Stack:** Python 3.10+, python-dotenv, pytest, pytest-asyncio, subprocess, os

---

## 文件地图

### 新增文件

- `d:\Projects\LuaN1aoAgent\tools\tool_env.py`
  - 统一加载项目根目录 `.env` 并提供工具路径解析。
- `d:\Projects\LuaN1aoAgent\tests\tools\test_tool_env.py`
  - 覆盖项目级环境加载、单工具优先、`TOOLS_HOME` 约定路径与缺配置失败。

### 修改文件

- `d:\Projects\LuaN1aoAgent\tools\mcp_service.py`
  - 去掉系统环境变量 / PATH 兜底，改为只用 `tools.tool_env`。
- `d:\Projects\LuaN1aoAgent\domain_scanner.py`
  - 不再直接 `os.getenv()` / `shutil.which()`，改为统一走 `tools.tool_env`。
- `d:\Projects\LuaN1aoAgent\tests\tools\test_mcp_service_tool_resolution.py`
  - 从“环境变量/TOOLS_HOME/PATH”改为“项目 `.env` 配置 / 缺配置失败”。
- `d:\Projects\LuaN1aoAgent\tests\test_domain_scanner_tool_resolution.py`
  - 从 PATH 兜底思路改为项目级 `.env` 统一入口。
- `d:\Projects\LuaN1aoAgent\.env.example`
  - 明确这组变量是项目级本地配置。
- `d:\Projects\LuaN1aoAgent\TOOLS_HOME_GUIDE.md`
  - 更新为“只支持项目级本地 `.env`，不支持系统环境变量/ PATH”。

---

## 约束

本次实现必须满足：

- 只读取项目根目录 `.env`
- 不使用系统环境变量作为工具路径来源
- 不使用 `PATH` 作为工具兜底
- 对缺配置行为直接失败
- `mcp_service.py` 与 `domain_scanner.py` 行为一致

---

### Task 1: 写项目级工具环境红灯测试

**Files:**
- Create: `d:\Projects\LuaN1aoAgent\tests\tools\test_tool_env.py`
- Modify: `d:\Projects\LuaN1aoAgent\tests\tools\test_mcp_service_tool_resolution.py`
- Modify: `d:\Projects\LuaN1aoAgent\tests\test_domain_scanner_tool_resolution.py`

- [ ] **Step 1: 写 `tool_env` 的失败测试**

```python
from pathlib import Path

from tools import tool_env


def test_resolve_project_tool_prefers_explicit_tool_path(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TOOLS_HOME=D:\\Tools\\PentestWorkspace\n"
        "NUCLEI_PATH=D:\\Custom\\nuclei.exe\n",
        encoding="utf-8",
    )

    resolved = tool_env.resolve_project_tool(
        tool_name="nuclei",
        env_var_name="NUCLEI_PATH",
        tools_home_subpath=r"nuclei\nuclei.exe",
        dotenv_path=env_file,
        existing_paths={
            r"D:\Custom\nuclei.exe",
            r"D:\Tools\PentestWorkspace\nuclei\nuclei.exe",
        },
    )

    assert resolved == r"D:\Custom\nuclei.exe"


def test_resolve_project_tool_returns_none_when_not_configured(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")

    resolved = tool_env.resolve_project_tool(
        tool_name="nuclei",
        env_var_name="NUCLEI_PATH",
        tools_home_subpath=r"nuclei\nuclei.exe",
        dotenv_path=env_file,
        existing_paths=set(),
    )

    assert resolved is None
```

- [ ] **Step 2: 改写 `mcp_service` 侧测试，移除 PATH 假设**

```python
from tools import mcp_service


def test_resolve_httpx_executable_uses_project_env_only(monkeypatch):
    monkeypatch.setattr(
        mcp_service,
        "resolve_project_tool",
        lambda tool_name, env_var_name, tools_home_subpath: r"D:\Tools\PentestWorkspace\httpx\httpx.exe",
    )

    resolved = mcp_service._resolve_httpx_executable()

    assert resolved == r"D:\Tools\PentestWorkspace\httpx\httpx.exe"
```

- [ ] **Step 3: 改写 `domain_scanner` 侧测试，固定缺配置直接失败**

```python
import pytest

import domain_scanner


def test_resolve_project_tool_returns_none_without_project_env(monkeypatch):
    monkeypatch.setattr(domain_scanner, "resolve_project_tool", lambda *args, **kwargs: None)

    resolved = domain_scanner._resolve_project_tool("subfinder")

    assert resolved is None
```

- [ ] **Step 4: 运行测试确认失败**

Run:

```powershell
& 'd:\Projects\LuaN1aoAgent\venv\Scripts\python.exe' -m pytest `
  d:\Projects\LuaN1aoAgent\tests\tools\test_tool_env.py `
  d:\Projects\LuaN1aoAgent\tests\tools\test_mcp_service_tool_resolution.py `
  d:\Projects\LuaN1aoAgent\tests\test_domain_scanner_tool_resolution.py -v
```

Expected:

```text
FAIL because tools.tool_env does not exist and current tests still assume PATH fallback
```

- [ ] **Step 5: 提交**

```bash
git add tests/tools/test_tool_env.py tests/tools/test_mcp_service_tool_resolution.py tests/test_domain_scanner_tool_resolution.py
git commit -m "test: add project local tool env coverage"
```

---

### Task 2: 实现统一的项目级工具环境模块

**Files:**
- Create: `d:\Projects\LuaN1aoAgent\tools\tool_env.py`
- Test: `d:\Projects\LuaN1aoAgent\tests\tools\test_tool_env.py`

- [ ] **Step 1: 写最小实现**

```python
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from dotenv import dotenv_values


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROJECT_DOTENV = PROJECT_ROOT / ".env"


def _normalize_existing_paths(existing_paths: Iterable[str] | None) -> set[str] | None:
    if existing_paths is None:
        return None
    return {str(path).strip() for path in existing_paths}


def _path_exists(path: str, existing_paths: set[str] | None = None) -> bool:
    normalized = str(path).strip()
    if not normalized:
        return False
    if existing_paths is not None:
        return normalized in existing_paths
    return Path(normalized).exists()


def load_project_tool_env(dotenv_path: str | Path | None = None) -> dict[str, str]:
    env_path = Path(dotenv_path) if dotenv_path else PROJECT_DOTENV
    if not env_path.exists():
        return {}
    return {
        key: str(value).strip()
        for key, value in dotenv_values(env_path).items()
        if value is not None and str(value).strip()
    }


def resolve_project_tool(
    tool_name: str,
    env_var_name: str,
    tools_home_subpath: str,
    *,
    dotenv_path: str | Path | None = None,
    existing_paths: Iterable[str] | None = None,
) -> str | None:
    env_map = load_project_tool_env(dotenv_path)
    normalized_existing_paths = _normalize_existing_paths(existing_paths)

    explicit = env_map.get(env_var_name, "").strip()
    if explicit and _path_exists(explicit, normalized_existing_paths):
        return explicit

    tools_home = env_map.get("TOOLS_HOME", "").strip()
    if tools_home:
        candidate = str(Path(tools_home) / tools_home_subpath)
        if _path_exists(candidate, normalized_existing_paths):
            return candidate

    return None
```

- [ ] **Step 2: 运行测试确认通过**

Run:

```powershell
& 'd:\Projects\LuaN1aoAgent\venv\Scripts\python.exe' -m pytest d:\Projects\LuaN1aoAgent\tests\tools\test_tool_env.py -v
```

Expected:

```text
PASSED
```

- [ ] **Step 3: 提交**

```bash
git add tools/tool_env.py tests/tools/test_tool_env.py
git commit -m "feat: add project local tool env loader"
```

---

### Task 3: 让 `mcp_service.py` 只依赖项目本地 `.env`

**Files:**
- Modify: `d:\Projects\LuaN1aoAgent\tools\mcp_service.py`
- Modify: `d:\Projects\LuaN1aoAgent\tests\tools\test_mcp_service_tool_resolution.py`
- Test: `d:\Projects\LuaN1aoAgent\tests\tools\test_tool_env.py`

- [ ] **Step 1: 切换到统一入口**

```python
from tools.tool_env import resolve_project_tool
```

```python
def _resolve_external_tool(
    tool_name: str,
    env_var_name: str,
    tools_home_subpath: str,
) -> str | None:
    return resolve_project_tool(
        tool_name=tool_name,
        env_var_name=env_var_name,
        tools_home_subpath=tools_home_subpath,
    )
```

- [ ] **Step 2: 去掉 PATH 相关逻辑与文案**

```python
if not sqlmap_executable:
    return json.dumps(
        {
            "success": False,
            "error": "sqlmap not configured. Checked SQLMAP_PATH and TOOLS_HOME/sqlmap/sqlmap.exe from project .env only.",
            "error_type": "TOOL_MISSING",
        },
        ensure_ascii=False,
    )
```

```python
if not httpx_executable:
    result["error"] = "httpx not configured or incompatible. Checked PD_HTTPX_PATH and TOOLS_HOME/httpx/httpx.exe from project .env only."
    return json.dumps(result, ensure_ascii=False)
```

- [ ] **Step 3: 保留 `httpx` 兼容检查，但不再依赖 PATH**

```python
def _resolve_httpx_executable() -> str | None:
    resolved = resolve_project_tool(
        tool_name="httpx",
        env_var_name="PD_HTTPX_PATH",
        tools_home_subpath=r"httpx\httpx.exe",
    )
    if not resolved:
        return None

    try:
        result = subprocess.run([resolved, "--help"], capture_output=True, text=True, timeout=5)
        if _is_compatible_projectdiscovery_httpx(result.stdout + "\n" + result.stderr):
            return resolved
    except Exception:
        return None

    return None
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```powershell
& 'd:\Projects\LuaN1aoAgent\venv\Scripts\python.exe' -m pytest `
  d:\Projects\LuaN1aoAgent\tests\tools\test_tool_env.py `
  d:\Projects\LuaN1aoAgent\tests\tools\test_mcp_service_tool_resolution.py -v
```

Expected:

```text
PASSED
```

- [ ] **Step 5: 提交**

```bash
git add tools/mcp_service.py tests/tools/test_mcp_service_tool_resolution.py
git commit -m "feat: restrict mcp tools to project local env"
```

---

### Task 4: 让 `domain_scanner.py` 只依赖项目本地 `.env`

**Files:**
- Modify: `d:\Projects\LuaN1aoAgent\domain_scanner.py`
- Modify: `d:\Projects\LuaN1aoAgent\tests\test_domain_scanner_tool_resolution.py`

- [ ] **Step 1: 替换现有解析函数**

```python
from tools.tool_env import resolve_project_tool


def _resolve_project_tool(tool_name: str) -> str | None:
    mapping = {
        "subfinder": ("SUBFINDER_PATH", r"subfinder\subfinder.exe"),
        "httpx": ("PD_HTTPX_PATH", r"httpx\httpx.exe"),
    }
    env_var_name, tools_home_subpath = mapping[tool_name]
    return resolve_project_tool(
        tool_name=tool_name,
        env_var_name=env_var_name,
        tools_home_subpath=tools_home_subpath,
    )
```

- [ ] **Step 2: 对缺配置直接失败**

```python
subfinder_executable = _resolve_project_tool("subfinder")
if not subfinder_executable:
    raise RuntimeError(
        "subfinder not configured. Checked SUBFINDER_PATH and TOOLS_HOME/subfinder/subfinder.exe from project .env only."
    )
```

```python
httpx_executable = _resolve_project_tool("httpx")
if not httpx_executable:
    raise RuntimeError(
        "httpx not configured. Checked PD_HTTPX_PATH and TOOLS_HOME/httpx/httpx.exe from project .env only."
    )
```

- [ ] **Step 3: 运行测试确认通过**

Run:

```powershell
& 'd:\Projects\LuaN1aoAgent\venv\Scripts\python.exe' -m pytest `
  d:\Projects\LuaN1aoAgent\tests\tools\test_tool_env.py `
  d:\Projects\LuaN1aoAgent\tests\test_domain_scanner_tool_resolution.py -v
```

Expected:

```text
PASSED
```

- [ ] **Step 4: 提交**

```bash
git add domain_scanner.py tests/test_domain_scanner_tool_resolution.py
git commit -m "feat: restrict domain scanner tools to project local env"
```

---

### Task 5: 更新文档与最终验收

**Files:**
- Modify: `d:\Projects\LuaN1aoAgent\.env.example`
- Modify: `d:\Projects\LuaN1aoAgent\TOOLS_HOME_GUIDE.md`
- Modify: `d:\Projects\LuaN1aoAgent\docs\issues\2026-05-20-project-local-tool-env-design.md`

- [ ] **Step 1: 更新 `.env.example`**

```ini
# Project-local tool resolution only
TOOLS_HOME=D:\Tools\PentestWorkspace
SQLMAP_PATH=
DIRSEARCH_PATH=
NUCLEI_PATH=
SUBFINDER_PATH=
PD_HTTPX_PATH=
SEARCHSPLOIT_PATH=
```

- [ ] **Step 2: 更新根目录说明文档**

```md
## Loading Rule

The project now resolves external security tools from the project root `.env` only.

- system environment variables are not used as a tool source
- PATH is not used as a tool fallback
- missing project-local configuration causes direct failure
```

- [ ] **Step 3: 运行完整回归**

Run:

```powershell
& 'd:\Projects\LuaN1aoAgent\venv\Scripts\python.exe' -m pytest `
  d:\Projects\LuaN1aoAgent\tests\tools\test_tool_env.py `
  d:\Projects\LuaN1aoAgent\tests\tools\test_mcp_service_tool_resolution.py `
  d:\Projects\LuaN1aoAgent\tests\test_domain_scanner_tool_resolution.py -v
```

Expected:

```text
PASSED
```

- [ ] **Step 4: 运行一次直接验证**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$code = @'
from tools.tool_env import resolve_project_tool
print(resolve_project_tool("nuclei", "NUCLEI_PATH", r"nuclei\nuclei.exe"))
print(resolve_project_tool("subfinder", "SUBFINDER_PATH", r"subfinder\subfinder.exe"))
print(resolve_project_tool("httpx", "PD_HTTPX_PATH", r"httpx\httpx.exe"))
'@
& 'd:\Projects\LuaN1aoAgent\venv\Scripts\python.exe' -c $code
```

Expected:

```text
D:\Tools\PentestWorkspace\nuclei\nuclei.exe
D:\Tools\PentestWorkspace\subfinder\subfinder.exe
D:\Tools\PentestWorkspace\httpx\httpx.exe
```

- [ ] **Step 5: 提交**

```bash
git add .env.example TOOLS_HOME_GUIDE.md docs/issues/2026-05-20-project-local-tool-env-design.md
git commit -m "docs: document project local tool environment"
```

---

## 自检结论

- 覆盖性：已覆盖设计中确认的全部真实代码文件 `tools/mcp_service.py`、`domain_scanner.py` 和新增统一入口 `tools/tool_env.py`。
- 占位符检查：无 `TBD` / `TODO` / 模糊步骤。
- 一致性：所有任务都以“只支持项目级本地 `.env`、不使用系统环境变量、不使用 PATH”作为统一规则。

---

Plan complete and saved to `docs/plan/2026-05-20-project-local-tool-env-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
