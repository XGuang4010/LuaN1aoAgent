# Dirsearch Scan Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 `dirsearch_scan` 的跨平台执行稳定性，解决 Windows/Linux 路径差异、运行依赖缺失识别和黑盒失败问题。

**Architecture:** 保持 `dirsearch_scan` 的 MCP 接口不变，在 `tools/mcp_service.py` 内部引入参数规范化、可执行文件解析与错误分类辅助函数，并将 shell 字符串执行改为显式参数执行。通过新增工具层测试覆盖路径清洗、依赖缺失识别和命令构造结果，确保修复后行为可回归验证。

**Tech Stack:** Python 3.10+, asyncio subprocess, FastMCP, pytest, unittest.mock

---

## 文件结构

- 修改：`d:\Projects\LuaN1aoAgent\tools\mcp_service.py`
  - 负责 `dirsearch_scan` 的命令构造、参数规范化、工具发现和错误分类
- 新增：`d:\Projects\LuaN1aoAgent\tests\tools\test_mcp_service_dirsearch.py`
  - 负责覆盖 `dirsearch_scan` 的回归测试和辅助函数行为
- 可选修改：`d:\Projects\LuaN1aoAgent\requirements.txt`
  - 仅当需要补充运行依赖说明时调整；本计划默认不先动

## Task 1: 建立 `dirsearch_scan` 红灯测试

**Files:**
- Create: `d:\Projects\LuaN1aoAgent\tests\tools\test_mcp_service_dirsearch.py`
- Modify: `d:\Projects\LuaN1aoAgent\tools\mcp_service.py`

- [ ] **Step 1: 写词典路径清洗失败测试**

```python
from tools.mcp_service import _normalize_dirsearch_args


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
```

- [ ] **Step 2: 写运行依赖缺失分类失败测试**

```python
from tools.mcp_service import _classify_dirsearch_failure


def test_classify_dirsearch_failure_detects_missing_pkg_resources():
    result = _classify_dirsearch_failure(
        "ModuleNotFoundError: No module named 'pkg_resources'",
        return_code=1,
    )

    assert result["error_type"] == "MISSING_RUNTIME_DEPENDENCY"
    assert "pkg_resources" in result["output"]
```

- [ ] **Step 3: 写工具缺失分类失败测试**

```python
from tools.mcp_service import _classify_dirsearch_failure


def test_classify_dirsearch_failure_detects_missing_tool():
    result = _classify_dirsearch_failure(
        "'dirsearch' is not recognized as an internal or external command",
        return_code=1,
    )

    assert result["error_type"] == "MISSING_TOOL"
```

- [ ] **Step 4: 写命令构造不走 shell 字符串的失败测试**

```python
import json
from unittest.mock import AsyncMock

import pytest

from tools import mcp_service


@pytest.mark.asyncio
async def test_dirsearch_scan_uses_exec_style_arguments(monkeypatch):
    calls = {}

    class FakeProcess:
        def __init__(self):
            self.stdout = AsyncMock()
            self.stdout.readline = AsyncMock(side_effect=[b"",])

        async def wait(self):
            return 0

    async def fake_exec(*args, **kwargs):
        calls["args"] = args
        calls["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(mcp_service, "_resolve_dirsearch_executable", lambda: "dirsearch")
    monkeypatch.setattr(mcp_service, "_normalize_dirsearch_args", lambda extra_args: (["-t", "10"], []))
    monkeypatch.setattr(mcp_service.asyncio, "create_subprocess_exec", fake_exec)

    payload = json.loads(await mcp_service.dirsearch_scan("https://example.com", "php", "-t 10"))

    assert payload["success"] is True
    assert calls["args"][:5] == ("dirsearch", "-u", "https://example.com", "-e", "php")
```

- [ ] **Step 5: 运行测试确认当前失败**

Run:

```powershell
& 'd:\Projects\LuaN1aoAgent\venv\Scripts\python.exe' -m pytest d:\Projects\LuaN1aoAgent\tests\tools\test_mcp_service_dirsearch.py -v
```

Expected:

```text
FAILED
```

失败原因应包含：

```text
cannot import name '_normalize_dirsearch_args'
cannot import name '_classify_dirsearch_failure'
```

- [ ] **Step 6: 提交测试基线**

```bash
git add tests/tools/test_mcp_service_dirsearch.py
git commit -m "test: add dirsearch scan regression coverage"
```

## Task 2: 拆分辅助函数并重构命令构造

**Files:**
- Modify: `d:\Projects\LuaN1aoAgent\tools\mcp_service.py`
- Test: `d:\Projects\LuaN1aoAgent\tests\tools\test_mcp_service_dirsearch.py`

- [ ] **Step 1: 在 `mcp_service.py` 增加可执行文件解析函数**

加入：

```python
import shutil
```

```python
def _resolve_dirsearch_executable() -> str | None:
    candidates = ["dirsearch", "dirsearch.exe"]
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None
```

- [ ] **Step 2: 在 `mcp_service.py` 增加参数规范化函数**

加入：

```python
def _normalize_dirsearch_args(extra_args: str) -> tuple[list[str], list[str]]:
    incompatible_args = {
        "--recursive-level": "-r",
        "--recursion-level": "-r",
    }
    warnings: list[str] = []
    normalized: list[str] = []
    args_list = shlex.split(extra_args, posix=False) if extra_args else []

    i = 0
    while i < len(args_list):
        arg = args_list[i]

        if arg in {"-w", "--wordlist"}:
            if i + 1 < len(args_list):
                candidate = args_list[i + 1]
                if os.path.exists(candidate):
                    normalized.extend([arg, candidate])
                else:
                    warnings.append(f"Removed missing wordlist path: {candidate}")
                i += 2
                continue

        replaced = False
        for bad_arg, replacement in incompatible_args.items():
            if arg.startswith(bad_arg):
                normalized.append(replacement)
                warnings.append(f"Replaced incompatible arg {arg} with {replacement}")
                if "=" not in arg and i + 1 < len(args_list) and not args_list[i + 1].startswith("-"):
                    i += 1
                replaced = True
                break

        if not replaced:
            normalized.append(arg)
        i += 1

    return normalized, warnings
```

- [ ] **Step 3: 将 `dirsearch_scan` 改为显式参数执行**

把主流程从 shell 字符串改成：

```python
executable = _resolve_dirsearch_executable()
if not executable:
    return json.dumps(
        {
            "success": False,
            "output": "",
            "error_type": "MISSING_TOOL",
            "message": "Dirsearch executable not found.",
            "fix_suggestion": "Install dirsearch and ensure it is available on PATH.",
        }
    )

filtered_args, warnings = _normalize_dirsearch_args(extra_args)
cmd_args = [executable, "-u", url, "-e", extensions, "-q", *filtered_args]

process = await asyncio.create_subprocess_exec(
    *cmd_args,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.STDOUT,
)
```

- [ ] **Step 4: 让成功结果附带 warning**

将成功返回调整为：

```python
return json.dumps(
    {
        "success": True,
        "output": full_output,
        "error": "",
        "warnings": warnings,
    }
)
```

- [ ] **Step 5: 运行局部测试确认命令构造通过**

Run:

```powershell
& 'd:\Projects\LuaN1aoAgent\venv\Scripts\python.exe' -m pytest d:\Projects\LuaN1aoAgent\tests\tools\test_mcp_service_dirsearch.py::test_dirsearch_scan_uses_exec_style_arguments -v
```

Expected:

```text
PASSED
```

- [ ] **Step 6: 提交命令构造重构**

```bash
git add tools/mcp_service.py tests/tools/test_mcp_service_dirsearch.py
git commit -m "refactor: harden dirsearch command execution"
```

## Task 3: 增强错误分类与友好返回

**Files:**
- Modify: `d:\Projects\LuaN1aoAgent\tools\mcp_service.py`
- Test: `d:\Projects\LuaN1aoAgent\tests\tools\test_mcp_service_dirsearch.py`

- [ ] **Step 1: 增加错误分类函数**

加入：

```python
def _classify_dirsearch_failure(output: str, return_code: int) -> dict[str, str]:
    lowered = output.lower()

    if "no module named 'pkg_resources'" in lowered:
        return {
            "error_type": "MISSING_RUNTIME_DEPENDENCY",
            "message": f"Command returned non-zero exit status {return_code}.",
            "fix_suggestion": "Install setuptools so pkg_resources is available to dirsearch.",
            "output": output,
        }

    if "not recognized as an internal or external command" in lowered or "not found" in lowered:
        return {
            "error_type": "MISSING_TOOL",
            "message": f"Command returned non-zero exit status {return_code}.",
            "fix_suggestion": "Install dirsearch or ensure it is available on PATH.",
            "output": output,
        }

    if "no such option" in lowered or "unrecognized arguments" in lowered:
        return {
            "error_type": "INVALID_ARGS",
            "message": f"Command returned non-zero exit status {return_code}.",
            "fix_suggestion": "Some arguments are not supported by the installed dirsearch version. Try without extra_args.",
            "output": output,
        }

    if "wordlist" in lowered and ("no such file" in lowered or "not found" in lowered):
        return {
            "error_type": "MISSING_WORDLIST",
            "message": f"Command returned non-zero exit status {return_code}.",
            "fix_suggestion": "Use an existing wordlist path or omit the explicit wordlist argument.",
            "output": output,
        }

    return {
        "error_type": "RUNTIME",
        "message": f"Command returned non-zero exit status {return_code}.",
        "fix_suggestion": "Check tool availability, arguments, and target accessibility.",
        "output": output,
    }
```

- [ ] **Step 2: 将 `dirsearch_scan` 的失败分支切到分类函数**

把现有 `return_code != 0` 分支替换成：

```python
if return_code != 0:
    failure = _classify_dirsearch_failure(full_output, return_code)
    failure["success"] = False
    failure["warnings"] = warnings
    return json.dumps(failure)
```

- [ ] **Step 3: 运行错误分类测试**

Run:

```powershell
& 'd:\Projects\LuaN1aoAgent\venv\Scripts\python.exe' -m pytest d:\Projects\LuaN1aoAgent\tests\tools\test_mcp_service_dirsearch.py::test_classify_dirsearch_failure_detects_missing_pkg_resources d:\Projects\LuaN1aoAgent\tests\tools\test_mcp_service_dirsearch.py::test_classify_dirsearch_failure_detects_missing_tool -v
```

Expected:

```text
PASSED
```

- [ ] **Step 4: 为缺失词典再补一个失败分类测试**

在测试文件中加入：

```python
from tools.mcp_service import _classify_dirsearch_failure


def test_classify_dirsearch_failure_detects_missing_wordlist():
    result = _classify_dirsearch_failure(
        "Wordlist '/usr/share/wordlists/dirb/common.txt' does not exist",
        return_code=1,
    )

    assert result["error_type"] == "MISSING_WORDLIST"
```

- [ ] **Step 5: 运行全量工具层测试**

Run:

```powershell
& 'd:\Projects\LuaN1aoAgent\venv\Scripts\python.exe' -m pytest d:\Projects\LuaN1aoAgent\tests\tools\test_mcp_service_dirsearch.py -v
```

Expected:

```text
all passed
```

- [ ] **Step 6: 提交错误分类增强**

```bash
git add tools/mcp_service.py tests/tools/test_mcp_service_dirsearch.py
git commit -m "fix: improve dirsearch failure classification"
```

## Task 4: 做真实环境回归并检查现有测试

**Files:**
- Modify: `d:\Projects\LuaN1aoAgent\tools\mcp_service.py`
- Test: `d:\Projects\LuaN1aoAgent\tests\tools\test_mcp_service_dirsearch.py`

- [ ] **Step 1: 在当前 Windows 环境用真实参数回归**

Run:

```powershell
& 'd:\Projects\LuaN1aoAgent\venv\Scripts\python.exe' -c "import asyncio; from tools.mcp_service import dirsearch_scan; print(asyncio.run(dirsearch_scan('https://api.dxmpay.com', 'php,asp,aspx,jsp,do,action,json,xml,html,txt', '-w /usr/share/wordlists/dirb/common.txt -t 20 --timeout=15')))"
```

Expected:

```text
JSON output with either:
- success: false and error_type: MISSING_RUNTIME_DEPENDENCY
or
- success: true / runtime output

and warnings mentioning removed missing wordlist path
```

- [ ] **Step 2: 运行现有 Web 回归测试**

Run:

```powershell
& 'd:\Projects\LuaN1aoAgent\venv\Scripts\python.exe' -m pytest d:\Projects\LuaN1aoAgent\tests\web\test_server_modernization.py -q
```

Expected:

```text
passed
```

- [ ] **Step 3: 运行现有核心测试**

Run:

```powershell
& 'd:\Projects\LuaN1aoAgent\venv\Scripts\python.exe' -m pytest d:\Projects\LuaN1aoAgent\tests\core\test_graph_manager_attack_chain_summary.py -q
```

Expected:

```text
passed
```

- [ ] **Step 4: 检查诊断并修复新增问题**

Run diagnostics for:

```text
d:\Projects\LuaN1aoAgent\tools\mcp_service.py
d:\Projects\LuaN1aoAgent\tests\tools\test_mcp_service_dirsearch.py
```

Expected:

```text
No newly introduced errors
```

- [ ] **Step 5: 记录回归结论**

在提交前确认：

```text
- dirsearch_scan 不再因 Linux 词典路径黑盒失败
- pkg_resources 缺失时返回 MISSING_RUNTIME_DEPENDENCY
- 工具构造命令时不再使用 create_subprocess_shell
```

- [ ] **Step 6: 提交最终修复**

```bash
git add tools/mcp_service.py tests/tools/test_mcp_service_dirsearch.py docs/superpowers/specs/2026-05-19-dirsearch-scan-design.md docs/superpowers/plans/2026-05-19-dirsearch-scan.md
git commit -m "fix: harden dirsearch scan across platforms"
```

## 自检结果

- 规格覆盖：已覆盖接口兼容、路径清洗、依赖缺失分类、显式参数执行、测试与回归要求
- 占位检查：无 `TODO`、`TBD` 或“稍后实现”类占位
- 类型一致性：计划统一使用 `_resolve_dirsearch_executable()`、`_normalize_dirsearch_args()`、`_classify_dirsearch_failure()` 三个辅助函数与 `dirsearch_scan()` 主入口

