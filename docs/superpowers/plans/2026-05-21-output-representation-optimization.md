# 输出表征优化与证据可视化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or TeamCreate to implement.

**Goal:** Replace flat string observation with StructuredObservation, add tool output parsers, and build interactive DAG detail panel + evidence view.

**Architecture:** 4-phase incremental delivery. P1 changes `core/data_contracts.py` and `core/executor.py` to use structured data. P2 adds `core/parsers/` module. P3 enhances existing `showDetails()` in `web/static/app.js` into a tabbed panel. P4 adds evidence browser with causal chain visualization.

**Tech Stack:** Python 3.10+, NetworkX (existing), FastAPI (existing), Vanilla JS (existing), D3.js v7 (existing)

**Key Existing Code:** 
- `app.js:1872` `showDetails(d)` — flat detail panel to enhance into tabbed view
- `app.js:434` `drawForceGraph(data)` — main DAG renderer; node data bundled from graph API
- `graph_manager.py:214` `add_causal_node(artifact)` — creates causal evidence/hypothesis/vuln nodes
- No single-node API endpoint; all node data comes via `/api/graph/execution?op_id=`

---

## File Structure

### New Files
| File | Purpose |
|------|---------|
| `core/parsers/__init__.py` | Parser registry + `parse_tool_output()` dispatch |
| `core/parsers/nmap_parser.py` | Nmap XML/plain output parser |
| `core/parsers/dirsearch_parser.py` | Dirsearch URL list parser |
| `core/parsers/httpx_parser.py` | httpx JSON output parser |
| `core/parsers/http_parser.py` | Generic http_request response parser |
| `core/parsers/subfinder_parser.py` | Subfinder subdomain parser |
| `core/parsers/nuclei_parser.py` | Nuclei JSON results parser |
| `core/parsers/sqlmap_parser.py` | sqlmap output parser |
| `tests/core/test_data_contracts_structured.py` | Tests for new data classes |
| `tests/core/test_parsers.py` | Tests for parser registry + each parser |
| `tests/web/test_node_detail_api.py` | Tests for node detail API endpoints |

### Modified Files
| File | Changes |
|------|---------|
| `core/data_contracts.py` | Add ToolFinding, ToolError, StructuredObservation |
| `core/executor.py` | Replace flat string with StructuredObservation, new LLM formatting, expanded error classification |
| `core/graph_manager.py` | Add `add_evidence()` method |
| `conf/config.py` | Add `EXECUTOR_DB_OUTPUT_LENGTH` (200K for DB), keep existing `EXECUTOR_MAX_OUTPUT_LENGTH` for LLM |
| `web/server.py` | Add `/api/node/{node_id}/detail`, `/api/task/{op_id}/chat` (SSE), `/api/task/{op_id}/evidence`, `/api/evidence/{evidence_id}/chain` |
| `web/static/app.js` | Add click handler on DAG nodes, slide-out detail panel, chat dialog, evidence view page |
| `web/templates/index.html` | Add CSS for detail panel, chat dialog, evidence view |

---

### Task 1: P1 Data Classes + Config

**Files:**
- Modify: `core/data_contracts.py` — append after line 82 (after ExploitNode)
- Modify: `conf/config.py` — add DB output length after line 218
- Create: `tests/core/test_data_contracts_structured.py`

- [ ] **Step 1: Add ToolFinding, ToolError, StructuredObservation to data_contracts.py**

```python
# ==================================================
# 结构化观测数据契约（输出表征优化 P1）
# ==================================================

from typing import Literal

@dataclass
class ToolFinding:
    """工具执行结果中提取的结构化发现项."""
    category: str           # "open_port" / "service" / "subdomain" / "tech_stack" / "vuln" / "http_header" / "url" / "os"
    key: str                # 唯一标识，如 "80/tcp"
    value: str | dict       # 核心值
    confidence: float       # 0.0-1.0
    evidence_ref: str | None = None  # 原始输出行引用

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "key": self.key,
            "value": self.value,
            "confidence": self.confidence,
            "evidence_ref": self.evidence_ref,
        }


@dataclass
class ToolError:
    """工具执行错误信息（7类分类）. """
    error_type: str         # MISSING_TOOL / TIMEOUT / AUTH / SYNTAX / NETWORK / RUNTIME / UNKNOWN
    message: str
    fix_suggestion: str
    is_correctable: bool

    CORRECTABLE_TYPES = {"SYNTAX", "TIMEOUT", "NETWORK"}
    PARTIALLY_CORRECTABLE = {"MISSING_TOOL"}

    def to_dict(self) -> dict:
        return {
            "error_type": self.error_type,
            "message": self.message,
            "fix_suggestion": self.fix_suggestion,
            "is_correctable": self.is_correctable,
        }

    @classmethod
    def from_json_response(cls, data: dict) -> Optional["ToolError"]:
        """从 MCP 工具 JSON 响应解析错误."""
        if data.get("success") is not False:
            return None
        error_type = data.get("error_type", "UNKNOWN")
        message = data.get("message", str(data))
        fix_suggestion = data.get("fix_suggestion", "")
        is_correctable = error_type in cls.CORRECTABLE_TYPES or (
            error_type in cls.PARTIALLY_CORRECTABLE
        )
        return cls(
            error_type=error_type,
            message=message,
            fix_suggestion=fix_suggestion,
            is_correctable=is_correctable,
        )


@dataclass
class StructuredObservation:
    """结构化观测结果，替代扁平字符串传递给 LLM."""
    step_id: str
    tool: str
    status: Literal["success", "partial", "failed"]
    summary: str                     # LLM 友好摘要（2-3 行）
    raw_output: str                  # 完整原始输出（按需截断）
    findings: list[ToolFinding]
    errors: list[ToolError]
    evidence_ids: list[str]
    truncated: bool = False
    truncation_info: str | None = None

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "tool": self.tool,
            "status": self.status,
            "summary": self.summary,
            "raw_output": self.raw_output,
            "findings": [f.to_dict() for f in self.findings],
            "errors": [e.to_dict() for e in self.errors],
            "evidence_ids": self.evidence_ids,
            "truncated": self.truncated,
            "truncation_info": self.truncation_info,
        }

    def format_for_llm(self) -> str:
        """生成 LLM 友好摘要（替代旧的全量字符串拼接）. """
        status_icon = {"success": "✅", "partial": "⚠️", "failed": "❌"}[self.status]
        parts = [f"{status_icon} [{self.tool}] {self.step_id}: {self.summary}"]
        if self.findings:
            cats = ", ".join(sorted(set(f.category for f in self.findings)))
            parts.append(f"  → 发现: {len(self.findings)} 项 ({cats})")
        if self.errors:
            for err in self.errors:
                parts.append(f"  → 错误: [{err.error_type}] {err.message}")
        if self.truncated and self.truncation_info:
            parts.append(f"  → ⚠️ 输出截断: {self.truncation_info}")
        return "\n".join(parts)
```

- [ ] **Step 2: Add DB output length config**

```python
# After EXECUTER_MAX_OUTPUT_LENGTH (config.py:218)
EXECUTOR_DB_OUTPUT_LENGTH = int(os.getenv("EXECUTOR_DB_OUTPUT_LENGTH", "200000"))
```

- [ ] **Step 3: Write tests for data classes**

```python
"""Tests for P1 structured observation data contracts."""
import json
import sys
sys.path.insert(0, "d:/Projects/LuaN1aoAgent")

from core.data_contracts import ToolFinding, ToolError, StructuredObservation


def test_tool_finding_to_dict():
    f = ToolFinding(category="open_port", key="80/tcp", value="Apache httpd", confidence=0.9)
    d = f.to_dict()
    assert d["category"] == "open_port"
    assert d["key"] == "80/tcp"
    assert d["confidence"] == 0.9


def test_tool_error_from_json_response_syntax():
    data = {"success": False, "error_type": "SYNTAX", "message": "Bad arg", "fix_suggestion": "Fix args"}
    err = ToolError.from_json_response(data)
    assert err is not None
    assert err.error_type == "SYNTAX"
    assert err.is_correctable is True


def test_tool_error_from_json_response_success():
    data = {"success": True, "result": "ok"}
    err = ToolError.from_json_response(data)
    assert err is None


def test_tool_error_from_json_response_unknown():
    data = {"success": False, "error_type": "RUNTIME", "message": "Crash", "fix_suggestion": ""}
    err = ToolError.from_json_response(data)
    assert err is not None
    assert err.error_type == "RUNTIME"
    assert err.is_correctable is False  # RUNTIME not in correctable types


def test_structured_observation_to_dict():
    obs = StructuredObservation(
        step_id="step_1",
        tool="nmap",
        status="success",
        summary="Found 3 open ports",
        raw_output="PORT STATE SERVICE\n80/tcp open http\n",
        findings=[
            ToolFinding(category="open_port", key="80/tcp", value="http", confidence=0.9),
        ],
        errors=[],
        evidence_ids=[],
        truncated=False,
    )
    d = obs.to_dict()
    assert d["step_id"] == "step_1"
    assert d["status"] == "success"
    assert len(d["findings"]) == 1
    assert d["findings"][0]["category"] == "open_port"


def test_structured_observation_format_for_llm():
    obs = StructuredObservation(
        step_id="step_1",
        tool="nmap",
        status="success",
        summary="Found 3 open ports",
        raw_output="...",
        findings=[
            ToolFinding(category="open_port", key="80/tcp", value="http", confidence=0.9),
            ToolFinding(category="service", key="80/tcp", value="Apache", confidence=0.8),
        ],
        errors=[
            ToolError(error_type="NETWORK", message="timeout", fix_suggestion="retry", is_correctable=True),
        ],
        evidence_ids=[],
        truncated=True,
        truncation_info="raw_output truncated from 60000 chars",
    )
    result = obs.format_for_llm()
    # Should include status icon, summary, findings count, errors, truncation
    assert "✅" in result
    assert "Found 3 open ports" in result
    assert "发现" in result and "2" in result
    assert "NETWORK" in result
    assert "截断" in result
```

- [ ] **Step 4: Run tests to verify**

```bash
cd d:/Projects/LuaN1aoAgent
python -m pytest tests/core/test_data_contracts_structured.py -v
```
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add core/data_contracts.py conf/config.py tests/core/test_data_contracts_structured.py
git commit -m "feat(P1): add StructuredObservation data classes with ToolFinding/ToolError"
```

---

### Task 2: P1 Executor Changes

**Files:**
- Modify: `core/executor.py` — lines 835-945 (reconstruct observation loop)
- Test: existing `tests/core/test_data_contracts_structured.py` (extend)

- [ ] **Step 1: Replace observation construction loop in executor.py**

Replace lines 872-897 (truncation + observation append + graph update):

```python
                # Truncation logic — dual buffer: truncate for LLM, keep full for DB
                original_length = len(result_str)
                was_truncated = False
                raw_for_db = result_str  # full output for DB
                raw_for_llm = result_str  # truncated for LLM
                if original_length > EXECUTOR_MAX_OUTPUT_LENGTH:
                    raw_for_llm = result_str[:EXECUTOR_MAX_OUTPUT_LENGTH] + f"\n... (Truncated from {original_length})"
                    was_truncated = True
                    _get_console().print(Panel(f"⚠️ 动作 {step_id} 结果过长已截断", title="警告", style="yellow"))
                    truncated_steps.append({
                        "step_id": step_id,
                        "tool_name": tool_name,
                        "original_length": original_length,
                        "sent_length": EXECUTOR_MAX_OUTPUT_LENGTH,
                    })

                # Build structured observation
                tool_errors = []
                tool_findings = []  # P2 will fill this with real parsers
                try:
                    json_data = json.loads(result_str) if isinstance(result_str, str) else {}
                    if isinstance(json_data, dict):
                        tool_error = ToolError.from_json_response(json_data)
                        if tool_error:
                            tool_errors.append(tool_error)
                            if tool_error.error_type in ("SYNTAX", "MISSING_TOOL"):
                                has_correctable_error = True
                                correction_feedback.append(
                                    f"- Step {step_id} (Tool: {tool_name}) failed: {tool_error.message} -> {tool_error.fix_suggestion}"
                                )
                except (json.JSONDecodeError, TypeError):
                    pass

                obs = StructuredObservation(
                    step_id=step_id,
                    tool=tool_name,
                    status=step_status,  # "completed" or "failed"
                    summary=f"Tool {tool_name} executed (status={step_status})",  # P2 will improve
                    raw_output=raw_for_db,
                    findings=tool_findings,
                    errors=tool_errors,
                    evidence_ids=[],
                    truncated=was_truncated,
                    truncation_info=f"Truncated from {original_length}" if was_truncated else None,
                )
                observations.append(obs)  # List[StructuredObservation]

                # Update graph node — save structured data to data[...]
                graph_manager.update_node(
                    step_id,
                    {
                        "observation": obs.to_dict(),
                        "findings": [f.to_dict() for f in tool_findings],
                        "raw_output": raw_for_db,
                        "observation_truncated": was_truncated,
                        "observation_original_length": original_length,
                        "status": step_status,
                    },
                )
```

- [ ] **Step 2: Replace LLM message formatting logic (lines 932-933)**

```python
            # Build LLM message from structured observations
            formatted = f"你并行执行了 {len(last_step_ids)} 个动作：\n"
            for obs in observations:
                formatted += "  " + obs.format_for_llm() + "\n"
            messages.append({"role": "user", "content": formatted})
```

- [ ] **Step 3: Update debug output (lines 935-942)**

```python
            if output_mode == "debug":
                _get_console().print(
                    Panel(
                        f"工具执行结果:\n{formatted}",
                        title="[bold green]Debug Tool Results[/bold green]",
                        style="green"
                    )
                )
```

- [ ] **Step 4: Run existing tests to verify no regression**

```bash
cd d:/Projects/LuaN1aoAgent
python -m pytest tests/core/test_data_contracts_structured.py -v
```
Expected: 6 passed

```bash
python -m pytest tests/tools/ -v
```
Expected: existing tests pass

- [ ] **Step 5: Add executor-specific tests**

Add to `tests/core/test_data_contracts_structured.py`:

```python
def test_structured_observation_parse_mcp_syntax_error():
    """Simulate parsing a SYNTAX error response from executor loop."""
    result_str = json.dumps({
        "success": False,
        "error_type": "SYNTAX",
        "message": "Invalid argument --bad-flag",
        "fix_suggestion": "Use --correct-flag instead",
    })
    data = json.loads(result_str)
    err = ToolError.from_json_response(data)
    assert err is not None
    assert err.error_type == "SYNTAX"
    assert err.is_correctable is True
    assert "correct-flag" in err.fix_suggestion


def test_structured_observation_backward_compat():
    """Simulate reading old string data from DB."""
    raw = data.get("observation", "")
    if isinstance(raw, str):
        # Old format fallback
        obs = StructuredObservation(
            step_id="old_step",
            tool="unknown",
            status="partial",
            summary="Legacy observation (raw text)",
            raw_output=raw,
            findings=[],
            errors=[],
            evidence_ids=[],
        )
        assert obs.status == "partial"
```

- [ ] **Step 6: Commit**

```bash
git add core/executor.py tests/core/test_data_contracts_structured.py
git commit -m "feat(P1): replace flat string observations with StructuredObservation in executor"
```

---

### Task 3: P2 Parser Module

**Files:**
- Create: `core/parsers/__init__.py`
- Create: `core/parsers/nmap_parser.py`
- Create: `core/parsers/dirsearch_parser.py`
- Create: `core/parsers/httpx_parser.py`
- Create: `core/parsers/http_parser.py`
- Create: `core/parsers/subfinder_parser.py`
- Create: `core/parsers/nuclei_parser.py`
- Create: `core/parsers/sqlmap_parser.py`
- Create: `tests/core/test_parsers.py`
- Modify: `core/executor.py` — integrate parsers into observation building

- [ ] **Step 1: Create core/parsers/__init__.py**

```python
"""Tool output parser registry. Maps tool names to parser functions."""
from typing import Callable
from core.data_contracts import ToolFinding

# Parser registry: tool_name -> parser function
PARSER_REGISTRY: dict[str, Callable[[str], list[ToolFinding]]] = {}


def register_parser(tool_name: str):
    """Decorator to register a parser function for a tool."""
    def decorator(func: Callable[[str], list[ToolFinding]]):
        PARSER_REGISTRY[tool_name] = func
        return func
    return decorator


def parse_tool_output(tool_name: str, raw_output: str) -> list[ToolFinding]:
    """Dispatch to the registered parser, or fallback."""
    parser = PARSER_REGISTRY.get(tool_name)
    if parser:
        return parser(raw_output)
    return fallback_parser(raw_output)


def fallback_parser(output: str) -> list[ToolFinding]:
    """Fallback: return raw output as a single finding."""
    return [
        ToolFinding(
            category="raw_output",
            key="full",
            value=output[:2000] + ("..." if len(output) > 2000 else ""),
            confidence=1.0,
        )
    ]


# Import parsers to register them
from core.parsers import nmap_parser
from core.parsers import dirsearch_parser
from core.parsers import httpx_parser
from core.parsers import http_parser
from core.parsers import subfinder_parser
from core.parsers import nuclei_parser
from core.parsers import sqlmap_parser
```

- [ ] **Step 2: Create each parser with at least basic regex/extraction**

nmap_parser.py:
```python
import re
from core.parsers import register_parser
from core.data_contracts import ToolFinding


@register_parser("nmap")
def parse_nmap_output(output: str) -> list[ToolFinding]:
    findings = []
    # Parse open ports: "80/tcp   open  http  Apache httpd 2.4.41"
    port_pattern = re.compile(r"(\d+)/(tcp|udp)\s+open\s+(\S+)(?:\s+(.*))?")
    for match in port_pattern.finditer(output):
        port = f"{match.group(1)}/{match.group(2)}"
        service = match.group(3) or ""
        version = (match.group(4) or "").strip()
        findings.append(ToolFinding(
            category="open_port",
            key=port,
            value=service,
            confidence=0.9,
        ))
        if version:
            findings.append(ToolFinding(
                category="service",
                key=port,
                value=version,
                confidence=0.7,
            ))
    return findings
```

dirsearch_parser.py:
```python
import re
from core.parsers import register_parser
from core.data_contracts import ToolFinding


@register_parser("dirsearch")
def parse_dirsearch_output(output: str) -> list[ToolFinding]:
    findings = []
    # Pattern: "[12:00:00] 200 -    0B  - /path"
    line_pattern = re.compile(r"\]\s+(\d+)\s+-\s+\S+\s+-\s+(\/\S*)")
    for match in line_pattern.finditer(output):
        status = match.group(1)
        path = match.group(2)
        findings.append(ToolFinding(
            category="url",
            key=path,
            value={"status": int(status), "path": path},
            confidence=0.9,
        ))
    return findings
```

httpx_parser.py:
```python
import json
from core.parsers import register_parser
from core.data_contracts import ToolFinding


@register_parser("httpx")
def parse_httpx_output(output: str) -> list[ToolFinding]:
    findings = []
    for line in output.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            data = {"url": line}
        url = data.get("url", data.get("input", ""))
        if url:
            findings.append(ToolFinding(
                category="service",
                key=url,
                value={
                    "status_code": data.get("status_code"),
                    "title": data.get("title", ""),
                    "webserver": data.get("webserver", ""),
                    "content_type": data.get("content_type", ""),
                },
                confidence=0.8,
            ))
        tech = data.get("tech", [])
        if tech:
            for t in tech:
                findings.append(ToolFinding(
                    category="tech_stack",
                    key=t,
                    value=f"{t} detected",
                    confidence=0.7,
                ))
    return findings
```

http_parser.py:
```python
import re
from core.parsers import register_parser
from core.data_contracts import ToolFinding


@register_parser("http_request")
def parse_http_response(output: str) -> list[ToolFinding]:
    findings = []
    # Extract status line
    status_match = re.search(r"HTTP/\d+\.\d+\s+(\d+)", output)
    if status_match:
        findings.append(ToolFinding(
            category="service",
            key="status_code",
            value=int(status_match.group(1)),
            confidence=1.0,
        ))
    # Extract headers
    header_pattern = re.compile(r"^([\w-]+):\s(.+)$", re.MULTILINE)
    for match in header_pattern.finditer(output):
        header_name = match.group(1).lower()
        header_val = match.group(2).strip()
        if header_name in ("server", "x-powered-by", "x-frame-options"):
            findings.append(ToolFinding(
                category="http_header",
                key=header_name,
                value=header_val,
                confidence=0.9,
            ))
    return findings
```

subfinder_parser.py:
```python
from core.parsers import register_parser
from core.data_contracts import ToolFinding


@register_parser("subfinder")
def parse_subfinder_output(output: str) -> list[ToolFinding]:
    findings = []
    for line in output.strip().split("\n"):
        line = line.strip()
        if line and not line.startswith("["):
            findings.append(ToolFinding(
                category="subdomain",
                key=line,
                value=line,
                confidence=0.8,
            ))
    return findings
```

nuclei_parser.py:
```python
import json
from core.parsers import register_parser
from core.data_contracts import ToolFinding


@register_parser("nuclei")
def parse_nuclei_output(output: str) -> list[ToolFinding]:
    findings = []
    for line in output.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        template_id = data.get("template-id", data.get("info", {}).get("name", "unknown"))
        severity = data.get("info", {}).get("severity", "unknown")
        matched = data.get("matched-at", "")
        findings.append(ToolFinding(
            category="vuln",
            key=template_id,
            value={
                "template": template_id,
                "severity": severity,
                "matched_at": matched,
                "description": data.get("info", {}).get("description", ""),
            },
            confidence=0.7,
        ))
    return findings
```

sqlmap_parser.py:
```python
import re
from core.parsers import register_parser
from core.data_contracts import ToolFinding


@register_parser("sqlmap")
def parse_sqlmap_output(output: str) -> list[ToolFinding]:
    findings = []
    # Look for "Parameter: ... (GET/POST)" patterns
    vuln_pattern = re.compile(r"Parameter:\s+(.+?)\s+\((.+?)\).*?(?=Parameter:|$)", re.DOTALL)
    for match in vuln_pattern.finditer(output):
        param = match.group(1).strip()
        method = match.group(2).strip()
        findings.append(ToolFinding(
            category="vuln",
            key=f"sqli_{param}",
            value={
                "parameter": param,
                "method": method,
                "type": "SQL Injection",
            },
            confidence=0.8,
        ))
    return findings
```

- [ ] **Step 3: Write parser tests**

```python
"""Tests for P2 tool output parsers."""
import sys
sys.path.insert(0, "d:/Projects/LuaN1aoAgent")

from core.parsers import parse_tool_output, PARSER_REGISTRY
from core.data_contracts import ToolFinding


def test_parser_registry_has_all_parsers():
    assert "nmap" in PARSER_REGISTRY
    assert "dirsearch" in PARSER_REGISTRY
    assert "httpx" in PARSER_REGISTRY
    assert "http_request" in PARSER_REGISTRY
    assert "subfinder" in PARSER_REGISTRY
    assert "nuclei" in PARSER_REGISTRY
    assert "sqlmap" in PARSER_REGISTRY


def test_fallback_parser():
    findings = parse_tool_output("unknown_tool", "some raw output")
    assert len(findings) == 1
    assert findings[0].category == "raw_output"


def test_nmap_open_port_parsing():
    output = """Nmap scan report for example.com (1.2.3.4)
PORT      STATE  SERVICE
80/tcp    open   http    Apache httpd 2.4.41
443/tcp   open   https   nginx 1.18.0
22/tcp    closed ssh
"""
    findings = parse_tool_output("nmap", output)
    assert len(findings) >= 3  # 2 open_port + at least 1 service
    ports = [f for f in findings if f.category == "open_port"]
    assert len(ports) == 2
    assert ports[0].key == "80/tcp"


def test_dirsearch_url_parsing():
    output = """[12:00:00] 200 -    0B  - /admin
[12:00:01] 301 -    0B  - /api
"""
    findings = parse_tool_output("dirsearch", output)
    assert len(findings) == 2
    assert findings[0].category == "url"
    assert "/admin" in findings[0].key


def test_subfinder_subdomain_parsing():
    output = """www.example.com
api.example.com
"""
    findings = parse_tool_output("subfinder", output)
    assert len(findings) == 2
    assert findings[0].category == "subdomain"


def test_http_header_parsing():
    output = """HTTP/1.1 200 OK
Server: nginx/1.18.0
Content-Type: text/html
X-Powered-By: PHP/7.4
"""
    findings = parse_tool_output("http_request", output)
    assert len(findings) >= 2  # status_code + at least 1 header
    headers = [f for f in findings if f.category == "http_header"]
    assert len(headers) >= 1
```

- [ ] **Step 4: Integrate parsers into executor observation building**

Replace the placeholder in executor.py (where `tool_findings = []` was):

```python
                # Parse tool output using P2 parsers
                try:
                    tool_findings = parse_tool_output(tool_name, result_str)
                except Exception:
                    tool_findings = fallback_parser(result_str)
```

And add import at top of executor.py:
```python
from core.parsers import parse_tool_output, fallback_parser
```

- [ ] **Step 5: Update summary generation to reflect parser findings**

Replace the placeholder summary in executor.py:
```python
                    summary=f"Tool {tool_name} executed (status={step_status})",  # P2 will improve
```

With:
```python
                    # Generate summary from findings
                    if tool_findings:
                        cats = ", ".join(sorted(set(f.category for f in tool_findings)))
                        summary = f"{tool_name}: found {len(tool_findings)} items ({cats})"
                    elif tool_errors:
                        summary = f"{tool_name}: {tool_errors[0].error_type} - {tool_errors[0].message[:80]}"
                    else:
                        summary = f"{tool_name}: executed, no findings extracted",
                    ...,
```

- [ ] **Step 6: Run parser tests**

```bash
cd d:/Projects/LuaN1aoAgent
python -m pytest tests/core/test_parsers.py -v
```
Expected: 8+ passed

- [ ] **Step 7: Commit**

```bash
git add core/parsers/ core/executor.py tests/core/test_parsers.py
git commit -m "feat(P2): add tool output parsers and integrate into executor"
```

---

### Task 4: GraphManager add_evidence() + P1/P2 Evidence Writing

**Files:**
- Modify: `core/graph_manager.py` — add `add_evidence()` method
- Modify: `core/executor.py` — call `add_evidence()` when building StructuredObservation

- [ ] **Step 1: Add add_evidence() wrapper to GraphManager**

`add_evidence()` wraps the existing `add_causal_node()` to provide a simpler Evidence-specific API:

```python
def add_evidence(
    self,
    evidence_id: str,
    category: str,
    content: str | dict,
    source_step: str,
    confidence: float,
    hypothesis_id: str | None = None,
) -> str:
    """Create an Evidence node via add_causal_node() and link to source step.
    
    Args:
        evidence_id: Unique ID for the evidence node
        category: Finding category (e.g. "open_port", "vuln")
        content: Evidence content (string or dict)
        source_step: Source step_id that produced this evidence
        confidence: Confidence score 0.0-1.0
        hypothesis_id: Optional hypothesis to link to
        
    Returns:
        The evidence node ID (same as evidence_id if accepted, may differ if dedup'd)
    """
    artifact = {
        "id": evidence_id,
        "node_type": "Evidence",
        "category": category,
        "content": str(content)[:500] if isinstance(content, str) else str(content)[:500],
        "source_step_id": source_step,
        "confidence": confidence,
        "raw_output": str(content)[:500],
        "hypothesis_id": hypothesis_id or "",
    }
    # Use set_traceability or the traceability field for finding context
    node_id = self.add_causal_node(artifact)
    
    # Add causal edge: source_step --PRODUCES--> evidence
    if source_step and self.causal_graph.has_node(source_step):
        self.add_causal_edge(source_step, node_id, "PRODUCES", confidence=confidence)
    
    return node_id
```

- [ ] **Step 2: Integrate add_evidence() into executor observation loop**

After building `obs` and before `observations.append(obs)`, add:

```python
                # Write evidence to causal graph
                for finding in tool_findings:
                    if finding.confidence >= 0.3:
                        evidence_id = f"ev_{step_id}_{finding.category}_{finding.key.replace('/', '_')[:40]}"
                        graph_manager.add_evidence(
                            evidence_id=evidence_id,
                            category=finding.category,
                            content=finding.value,
                            source_step=step_id,
                            confidence=finding.confidence,
                        )
                        obs.evidence_ids.append(evidence_id)
```

- [ ] **Step 3: Commit**

```bash
git add core/graph_manager.py core/executor.py
git commit -m "feat(P2): add GraphManager.add_evidence() and evidence auto-write in executor"
```

---

### Task 5: P3 Web UI — Node Detail Panel + Chat Dialog

**Files:**
- Modify: `web/server.py` — add `POST /api/task/{op_id}/chat` SSE endpoint
- Modify: `web/static/app.js` — **enhance existing `showDetails()` at line 1872** with tabs; add chat dialog functionality
- Modify: `web/templates/index.html` — add CSS for tabs + chat dialog

**Key Insight:** The existing `showDetails(d)` at `app.js:1872` renders a flat property dump. Node data comes bundled from the graph API and is accessed via `dagreGraph.node(nodeId)`. We enhance it with tabbed structure rather than replacing.

- [ ] **Step 1: Replace showDetails() in app.js with tabbed version**

Replace the existing `showDetails()` function (lines 1872-1945) with a tabbed version:

```javascript
function showDetails(d) {
  const c = document.getElementById('node-detail-content');
  
  // Header with Type, ID, Status (keep existing style)
  const typeLabel = d.type === 'root' ? t('type.root') :
    d.type === 'task' ? t('type.task') :
      d.type === 'action' ? t('type.action') :
        (d.type || 'NODE');
  const typeColor = d.type === 'root' ? '#3b82f6' :
    d.type === 'task' ? '#8b5cf6' :
      d.type === 'action' ? '#f59e0b' : '#64748b';
  const statusColor = nodeColors[d.status] || '#64748b';
  const statusText = d.status ? t('status.' + d.status) || d.status : 'UNKNOWN';

  let h = `<div class="panel-header" style="display:flex;align-items:center;gap:8px;padding:12px;border-bottom:1px solid var(--border-color);cursor:move">
      <div style="flex:1">
        <div style="font-size:10px;text-transform:uppercase;color:${typeColor};font-weight:bold;display:inline-block;background:${typeColor}22;padding:2px 6px;border-radius:3px;">${typeLabel}</div>
        <div style="font-size:13px;font-weight:bold;word-break:break-all;margin-top:4px;">${d.label || d.description || d.id}</div>
        <div style="font-size:10px;color:var(--text-muted);margin-top:2px">${d.id}</div>
      </div>
      <div style="text-align:right">
        <span style="background:${statusColor};color:white;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:bold">${statusText}</span>
      </div>
    </div>
    <div class="panel-tabs" style="display:flex;border-bottom:1px solid var(--border-color);">
      <button class="tab-btn active" onclick="switchDetailTab('overview',this)">概览</button>
      <button class="tab-btn" onclick="switchDetailTab('findings',this)">发现</button>
      <button class="tab-btn" onclick="switchDetailTab('evidence',this)">证据</button>
      <button class="tab-btn" onclick="switchDetailTab('raw',this)">原始输出</button>
      <button class="tab-btn" onclick="switchDetailTab('suggestions',this)">建议</button>
    </div>
    <div class="panel-body" style="flex:1;overflow-y:auto;padding:12px;">
      <div id="tab-overview" class="tab-pane active">${renderOverviewTab(d)}</div>
      <div id="tab-findings" class="tab-pane">${renderFindingsTab(d)}</div>
      <div id="tab-evidence" class="tab-pane">${renderEvidenceTab(d)}</div>
      <div id="tab-raw" class="tab-pane">${renderRawTab(d)}</div>
      <div id="tab-suggestions" class="tab-pane">${renderSuggestionsTab(d)}</div>
    </div>
    <div class="panel-footer" style="padding:8px 12px;border-top:1px solid var(--border-color);">
      <button onclick="openChatDialog('${d.id}')" style="background:#4a9eff;border:none;color:white;padding:6px 12px;border-radius:4px;cursor:pointer;font-size:12px;">💬 提问</button>
    </div>`;

  c.innerHTML = h;
  document.getElementById('node-details-panel').classList.add('show');
}

function switchDetailTab(tabName, btn) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  const tab = document.getElementById('tab-' + tabName);
  if (tab) tab.classList.add('active');
}

function renderOverviewTab(d) {
  const obs = d.observation || {};
  const obsData = typeof obs === 'string' ? {summary: obs} : obs;
  let h = '<table class="detail-table">';
  const fields = [
    ['节点类型', d.type],
    ['状态', d.status],
    ['工具', d.tool_name || (d.action && d.action.tool) || '-'],
    ['概要', obsData.summary || '-'],
  ];
  if (obsData.truncated) {
    fields.push(['截断', obsData.truncation_info || '是']);
  }
  fields.forEach(([k, v]) => {
    h += `<tr><td class="detail-key">${escapeHtml(k)}</td><td class="detail-val">${escapeHtml(String(v))}</td></tr>`;
  });
  h += '</table>';
  return h;
}

function renderFindingsTab(d) {
  // Try structured findings from data, then fallback to parsing observation
  const findings = d.findings || (d.data && d.data.findings) || [];
  if (!findings.length) {
    return '<p style="color:var(--text-muted);padding:16px;">暂无结构化发现数据</p>';
  }
  const grouped = {};
  findings.forEach(f => {
    const cat = f.category || 'uncategorized';
    if (!grouped[cat]) grouped[cat] = [];
    grouped[cat].push(f);
  });
  let h = '';
  Object.keys(grouped).forEach(cat => {
    h += `<div class="finding-group" style="margin-bottom:16px;">
      <h4 style="color:#4a9eff;font-size:11px;text-transform:uppercase;margin:0 0 8px 0;">${cat} (${grouped[cat].length})</h4>`;
    grouped[cat].forEach(f => {
      const val = typeof f.value === 'object' ? JSON.stringify(f.value) : String(f.value);
      h += `<div class="finding-item" style="display:flex;align-items:center;gap:8px;padding:6px 8px;background:var(--bg-secondary);border-radius:4px;margin-bottom:4px;font-size:12px;">
        <span style="color:#4caf50;min-width:100px;font-family:monospace;font-size:11px;">${escapeHtml(f.key)}</span>
        <span style="flex:1;overflow:hidden;text-overflow:ellipsis;color:var(--text-color);">${escapeHtml(val)}</span>
        <div style="width:60px;display:flex;align-items:center;gap:4px;">
          <div style="height:6px;background:#4a9eff;border-radius:3px;width:${Math.round((f.confidence||0)*100)}%;min-width:2px;"></div>
          <span style="color:var(--text-muted);font-size:10px;">${Math.round((f.confidence||0)*100)}%</span>
        </div>
      </div>`;
    });
    h += '</div>';
  });
  return h;
}

function renderEvidenceTab(d) {
  const evIds = d.evidence_ids || (d.data && d.data.evidence_ids) || [];
  if (!evIds.length) {
    return '<p style="color:var(--text-muted);padding:16px;">暂无关联证据</p>';
  }
  let h = `<p style="font-size:12px;color:var(--text-muted);">关联证据 (${evIds.length})：</p><ul style="list-style:none;padding:0;">`;
  evIds.forEach(id => {
    h += `<li style="padding:6px 8px;background:var(--bg-secondary);border-radius:4px;margin-bottom:4px;font-size:11px;font-family:monospace;">
      <a href="#" onclick="event.preventDefault();openEvidenceDetail('${escapeHtml(id)}')" style="color:#4a9eff;text-decoration:none;">${escapeHtml(id)}</a>
    </li>`;
  });
  h += '</ul>';
  return h;
}

function renderRawTab(d) {
  const raw = d.observation || (d.data && d.data.raw_output) || d.result || '';
  const rawStr = typeof raw === 'string' ? raw : (typeof raw === 'object' ? JSON.stringify(raw, null, 2) : String(raw));
  const truncated = rawStr.length > 50000;
  return `<pre class="code-block" style="max-height:50vh;overflow-y:auto;font-size:11px;">${escapeHtml(truncated ? rawStr.slice(0, 50000) + '\n... (truncated)' : rawStr)}</pre>
    <p style="font-size:11px;color:var(--text-muted);margin-top:4px;">${rawStr.length} chars${truncated ? ' (truncated for display)' : ''}</p>`;
}

function renderSuggestionsTab(d) {
  const categories = new Set();
  const findings = d.findings || (d.data && d.data.findings) || [];
  findings.forEach(f => { if (f.category) categories.add(f.category); });
  
  const suggestionMap = {
    'open_port': '对开放端口进行服务版本探测',
    'subdomain': '探测发现的子域名上的 Web 服务',
    'url': '测试发现的 URL 是否存在漏洞',
    'vuln': '尝试利用已发现的漏洞',
    'service': '深入识别服务版本和配置',
    'tech_stack': '查找技术栈相关漏洞',
    'http_header': '分析 HTTP 安全头配置',
  };
  
  const suggestions = [];
  categories.forEach(cat => {
    if (suggestionMap[cat]) suggestions.push(suggestionMap[cat]);
  });
  if (!suggestions.length) {
    suggestions.push('暂无特定建议 — 考虑扩大侦察范围');
  }
  
  let h = '<ul style="list-style:none;padding:0;">';
  suggestions.forEach(s => {
    h += `<li style="padding:8px 12px;background:var(--bg-secondary);border-radius:4px;margin-bottom:6px;font-size:13px;border-left:3px solid #4a9eff;">→ ${escapeHtml(s)}</li>`;
  });
  h += '</ul>';
  return h;
}
```

Also add CSS styles in index.html for the tabs:
```css
.tab-btn {
  padding: 8px 12px; background: none; border: none;
  color: var(--text-muted); cursor: pointer; font-size: 11px;
  white-space: nowrap; border-bottom: 2px solid transparent;
}
.tab-btn.active {
  color: #4a9eff; border-bottom-color: #4a9eff;
}
.tab-pane { display: none; }
.tab-pane.active { display: block; }
.finding-group { margin-bottom: 16px; }
.finding-item:hover { background: var(--bg-hover) !important; }
```

- [ ] **Step 1: Add node detail API endpoint to web/server.py**

```python
# Import data_contracts for parsing
from core.data_contracts import StructuredObservation, ToolFinding

# Add to server routes
@app.get("/api/node/{node_id}/detail")
async def get_node_detail(node_id: str):
    """Return structured detail for a DAG node."""
    graph_manager = get_graph_manager()
    node = graph_manager.get_node(node_id)
    if not node:
        return {"error": "Node not found", "node_id": node_id}
    
    node_data = node.get("data", node)  # Could be dict or object with .data
    if isinstance(node_data, dict):
        data = node_data
    else:
        data = node_data if isinstance(node_data, dict) else {}
    
    # Extract observation
    observation_raw = data.get("observation")
    observation = None
    if isinstance(observation_raw, dict):
        try:
            observation = observation_raw
        except Exception:
            observation = {"summary": "Failed to parse observation"}
    elif isinstance(observation_raw, str):
        observation = {"summary": observation_raw[:200], "raw_output": observation_raw, "status": "legacy"}
    
    return {
        "node_id": node_id,
        "node_type": data.get("node_type", data.get("type", "unknown")),
        "status": data.get("status", "unknown"),
        "tool": data.get("tool", data.get("action", {})),
        "observation": observation,
        "findings": data.get("findings", []),
        "evidence_ids": data.get("evidence_ids", []),
        "next_steps": _generate_next_steps(data.get("findings", [])),
    }


def _generate_next_steps(findings: list) -> list:
    """Generate human-readable next-step suggestions based on findings."""
    suggestions = []
    categories = {f.get("category") for f in findings if isinstance(f, dict)}
    
    if "open_port" in categories:
        suggestions.append("Perform service version detection on open ports")
    if "subdomain" in categories:
        suggestions.append("Probe discovered subdomains for web services")
    if "url" in categories:
        suggestions.append("Test discovered URLs for vulnerabilities")
    if "vuln" in categories:
        suggestions.append("Attempt exploitation of discovered vulnerabilities")
    if not suggestions:
        suggestions.append("No specific next steps — consider broader reconnaissance")
    
    return suggestions
```

- [ ] **Step 2: Add chat API endpoint with SSE**

```python
import json
import asyncio
from fastapi.responses import StreamingResponse

@app.post("/api/task/{op_id}/chat")
async def chat_with_task(op_id: str, request: dict):
    """Task-level chat dialog. Read-only, does not affect P-E-R loop."""
    question = request.get("question", "")
    graph_manager = get_graph_manager()
    
    # Collect task context
    task_nodes = graph_manager.get_all_nodes() if hasattr(graph_manager, "get_all_nodes") else []
    findings_summary = []
    for nid, ndata in task_nodes:
        node_data = ndata.get("data", ndata) if isinstance(ndata, dict) else {}
        findings = node_data.get("findings", [])
        if findings:
            findings_summary.append(f"Node {nid}: {len(findings)} findings")
    
    context = f"""You are a read-only analysis assistant for a penetration test.
Current task ID: {op_id}
Task has {len(task_nodes)} nodes.
Node findings summary: {" | ".join(findings_summary[:10])}

Answer the user's question about the task progress and findings.
Do NOT suggest executing any tools — you are read-only.
"""
    
    async def stream_response():
        # In production, this would call the LLM API
        # For now, return a simple structured response
        response_text = f"Based on the current task state ({op_id}):\n"
        response_text += f"- Task has {len(task_nodes)} nodes\n"
        if findings_summary:
            response_text += f"- Discovered: {'; '.join(findings_summary[:5])}\n"
        response_text += f"\nRegarding your question: \"{question}\"\n"
        response_text += "This is a read-only analysis interface. The P-E-R loop continues independently."
        
        for char in response_text:
            yield f"data: {json.dumps({'content': char})}\n\n"
            await asyncio.sleep(0.02)
        yield "data: [DONE]\n\n"
    
    return StreamingResponse(stream_response(), media_type="text/event-stream")
```

- [ ] **Step 3: Add DAG node click handler + detail panel to app.js**

Add to `web/static/app.js`:

```javascript
// ============================================================
// P3: DAG Node Detail Panel
// ============================================================

let detailPanelVisible = false;

// Modify existing DAG node click handler
document.addEventListener('click', function(e) {
    const nodeEl = e.target.closest('.dag-node');
    if (nodeEl) {
        const nodeId = nodeEl.dataset.nodeId;
        if (nodeId) {
            openNodeDetail(nodeId);
        }
    }
});

async function openNodeDetail(nodeId) {
    try {
        const resp = await fetch(`/api/node/${nodeId}/detail`);
        const data = await resp.json();
        renderDetailPanel(data);
    } catch (err) {
        console.error('Failed to load node detail:', err);
    }
}

function renderDetailPanel(data) {
    detailPanelVisible = true;
    const panel = document.getElementById('detail-panel') || createDetailPanel();
    panel.innerHTML = `
        <div class="panel-header">
            <h3>${data.node_id}</h3>
            <span class="node-status-badge ${data.status}">${data.status}</span>
            <button class="panel-close-btn" onclick="closeDetailPanel()">×</button>
        </div>
        <div class="panel-tabs">
            <button class="tab-btn active" data-tab="overview">概览</button>
            <button class="tab-btn" data-tab="findings">发现</button>
            <button class="tab-btn" data-tab="evidence">证据</button>
            <button class="tab-btn" data-tab="raw">原始输出</button>
            <button class="tab-btn" data-tab="suggestions">建议</button>
        </div>
        <div class="panel-content">
            ${renderTabOverview(data)}
            ${renderTabFindings(data)}
            ${renderTabEvidence(data)}
            ${renderTabRaw(data)}
            ${renderTabSuggestions(data)}
        </div>
        <div class="panel-footer">
            <button onclick="openChatDialog('${data.node_id}')">💬 提问</button>
        </div>
    `;
    panel.classList.add('visible');
    
    // Tab switching
    panel.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            panel.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            panel.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            this.classList.add('active');
            const tab = document.getElementById('tab-' + this.dataset.tab);
            if (tab) tab.classList.add('active');
        });
    });
}

function renderTabOverview(data) {
    const obs = data.observation || {};
    return `
        <div id="tab-overview" class="tab-content active">
            <table class="detail-table">
                <tr><td>节点类型</td><td>${data.node_type}</td></tr>
                <tr><td>状态</td><td><span class="status-badge ${data.status}">${data.status}</span></td></tr>
                <tr><td>概要</td><td>${obs.summary || '-'}</td></tr>
                ${data.observation?.truncated ? `<tr><td>截断</td><td class="warning">${data.observation.truncation_info || 'yes'}</td></tr>` : ''}
            </table>
        </div>
    `;
}

function renderTabFindings(data) {
    const findings = data.findings || [];
    const grouped = {};
    findings.forEach(f => {
        if (!grouped[f.category]) grouped[f.category] = [];
        grouped[f.category].push(f);
    });
    let html = `<div id="tab-findings" class="tab-content">`;
    Object.keys(grouped).forEach(cat => {
        html += `<div class="finding-group">
            <h4 class="finding-category">${cat} (${grouped[cat].length})</h4>`;
        grouped[cat].forEach(f => {
            const val = typeof f.value === 'object' ? JSON.stringify(f.value) : f.value;
            html += `<div class="finding-item">
                <span class="finding-key">${f.key}</span>
                <span class="finding-value">${val}</span>
                <span class="confidence-bar" style="width:${f.confidence * 100}%"></span>
                <span class="confidence-label">${Math.round(f.confidence * 100)}%</span>
            </div>`;
        });
        html += `</div>`;
    });
    html += `</div>`;
    return html;
}

function renderTabEvidence(data) {
    const evIds = data.evidence_ids || [];
    let html = `<div id="tab-evidence" class="tab-content">
        <p>关联证据节点 (${evIds.length})</p>
        <ul class="evidence-list">`;
    evIds.forEach(id => {
        html += `<li><a href="/evidence#${id}" onclick="openEvidenceView('${id}')">${id}</a></li>`;
    });
    html += `</ul></div>`;
    return html;
}

function renderTabRaw(data) {
    const raw = data.observation?.raw_output || '';
    const truncated = raw.length > 50000 ? ' (raw_output truncated)' : '';
    return `<div id="tab-raw" class="tab-content">
        <pre class="raw-output">${escapeHtml(raw)}</pre>
        <p class="truncated-note">${raw.length} chars${truncated}</p>
        <button onclick="copyRawOutput()">📋 复制全文</button>
    </div>`;
}

function renderTabSuggestions(data) {
    const next = data.next_steps || [];
    let html = `<div id="tab-suggestions" class="tab-content"><ul class="suggestion-list">`;
    next.forEach(s => { html += `<li>→ ${s}</li>`; });
    html += `</ul></div>`;
    return html;
}

function createDetailPanel() {
    const panel = document.createElement('div');
    panel.id = 'detail-panel';
    panel.className = 'detail-panel';
    document.body.appendChild(panel);
    return panel;
}

function closeDetailPanel() {
    const panel = document.getElementById('detail-panel');
    if (panel) {
        panel.classList.remove('visible');
        detailPanelVisible = false;
    }
}

// ============================================================
// P3: Task-Level Chat Dialog
// ============================================================

let chatDialogOpen = false;
let currentChatNodeId = null;

function openChatDialog(nodeId) {
    currentChatNodeId = nodeId;
    chatDialogOpen = true;
    const dialog = document.getElementById('chat-dialog') || createChatDialog();
    dialog.classList.add('visible');
    document.getElementById('chat-messages').innerHTML = '<div class="chat-msg system">输入问题以了解当前任务进度</div>';
}

function createChatDialog() {
    const html = `
        <div id="chat-dialog" class="chat-dialog">
            <div class="chat-header">
                <span>任务对话</span>
                <button onclick="closeChatDialog()">×</button>
            </div>
            <div id="chat-messages" class="chat-messages"></div>
            <div class="chat-input-area">
                <div class="quick-questions">
                    <button onclick="askChat('当前进度如何？')">当前进度？</button>
                    <button onclick="askChat('发现了哪些关键信息？')">关键发现？</button>
                    <button onclick="askChat('下一步建议？')">下一步？</button>
                </div>
                <div class="chat-input-row">
                    <input id="chat-input" type="text" placeholder="输入问题..." onkeydown="if(event.key==='Enter') askChat(this.value)">
                    <button onclick="askChat(document.getElementById('chat-input').value)">发送</button>
                </div>
            </div>
        </div>
    `;
    document.body.insertAdjacentHTML('beforeend', html);
    return document.getElementById('chat-dialog');
}

function closeChatDialog() {
    const dialog = document.getElementById('chat-dialog');
    if (dialog) dialog.classList.remove('visible');
    chatDialogOpen = false;
}

async function askChat(question) {
    if (!question.trim()) return;
    const messagesDiv = document.getElementById('chat-messages');
    messagesDiv.innerHTML += `<div class="chat-msg user">${escapeHtml(question)}</div>`;
    document.getElementById('chat-input').value = '';
    
    const resp = await fetch('/api/task/${currentChatNodeId}/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({question: question}),
    });
    
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let answerDiv = document.createElement('div');
    answerDiv.className = 'chat-msg assistant';
    messagesDiv.appendChild(answerDiv);
    
    while (true) {
        const {done, value} = await reader.read();
        if (done) break;
        const text = decoder.decode(value);
        const lines = text.split('\n');
        for (const line of lines) {
            if (line.startsWith('data: ') && line !== 'data: [DONE]') {
                try {
                    const data = JSON.parse(line.slice(6));
                    answerDiv.textContent += data.content;
                } catch(e) {}
            }
        }
    }
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
```

- [ ] **Step 4: Add CSS to index.html**

Add inside `<style>` tag in `web/templates/index.html`:

```css
/* P3: Detail Panel */
.detail-panel {
    position: fixed;
    top: 0;
    right: -500px;
    width: 480px;
    height: 100vh;
    background: #1a1a2e;
    color: #eee;
    box-shadow: -4px 0 20px rgba(0,0,0,0.5);
    transition: right 0.3s ease;
    z-index: 1000;
    display: flex;
    flex-direction: column;
}
.detail-panel.visible { right: 0; }
.panel-header {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 16px;
    border-bottom: 1px solid #333;
}
.panel-header h3 { margin: 0; font-size: 14px; flex: 1; }
.panel-close-btn {
    background: none; border: none; color: #999; font-size: 22px; cursor: pointer;
}
.panel-close-btn:hover { color: #fff; }
.panel-tabs {
    display: flex;
    border-bottom: 1px solid #333;
    overflow-x: auto;
}
.tab-btn {
    padding: 10px 14px;
    background: none;
    border: none;
    color: #999;
    cursor: pointer;
    font-size: 12px;
    white-space: nowrap;
}
.tab-btn.active { color: #4a9eff; border-bottom: 2px solid #4a9eff; }
.panel-content {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
}
.tab-content { display: none; }
.tab-content.active { display: block; }
.panel-footer {
    padding: 12px 16px;
    border-top: 1px solid #333;
}
.detail-table { width: 100%; border-collapse: collapse; }
.detail-table td {
    padding: 8px 10px;
    border-bottom: 1px solid #2a2a3e;
    font-size: 13px;
}
.detail-table td:first-child { color: #999; width: 100px; }
.status-badge { padding: 2px 8px; border-radius: 4px; font-size: 12px; }
.status-badge.completed { background: #1a3a1a; color: #4caf50; }
.status-badge.failed { background: #3a1a1a; color: #f44336; }
.status-badge.in_progress { background: #1a2a3a; color: #2196f3; }
.finding-group { margin-bottom: 16px; }
.finding-category {
    font-size: 13px;
    color: #4a9eff;
    margin: 0 0 8px 0;
    text-transform: uppercase;
}
.finding-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 8px;
    background: #16162a;
    border-radius: 4px;
    margin-bottom: 4px;
    font-size: 12px;
}
.finding-key { color: #4caf50; min-width: 120px; }
.finding-value { color: #ddd; flex: 1; overflow: hidden; text-overflow: ellipsis; }
.confidence-bar { height: 6px; background: #4a9eff; border-radius: 3px; min-width: 4px; }
.confidence-label { color: #999; font-size: 11px; min-width: 35px; }
.raw-output {
    background: #0d0d1a;
    padding: 12px;
    border-radius: 4px;
    font-size: 12px;
    overflow-x: auto;
    max-height: 60vh;
    white-space: pre-wrap;
    word-break: break-all;
}
.suggestion-list { list-style: none; padding: 0; }
.suggestion-list li {
    padding: 8px 12px;
    background: #16162a;
    border-radius: 4px;
    margin-bottom: 6px;
    font-size: 13px;
    border-left: 3px solid #4a9eff;
}

/* P3: Chat Dialog */
.chat-dialog {
    position: fixed;
    bottom: 0;
    right: 20px;
    width: 380px;
    height: 450px;
    background: #1a1a2e;
    border: 1px solid #333;
    border-radius: 8px 8px 0 0;
    display: none;
    flex-direction: column;
    z-index: 1001;
    box-shadow: 0 -4px 20px rgba(0,0,0,0.3);
}
.chat-dialog.visible { display: flex; }
.chat-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 14px;
    border-bottom: 1px solid #333;
    font-size: 13px;
}
.chat-header button { background: none; border: none; color: #999; cursor: pointer; font-size: 18px; }
.chat-messages {
    flex: 1;
    overflow-y: auto;
    padding: 12px;
    font-size: 12px;
}
.chat-msg {
    padding: 8px 12px;
    border-radius: 6px;
    margin-bottom: 8px;
    max-width: 85%;
}
.chat-msg.user {
    background: #2a4a7a;
    margin-left: auto;
}
.chat-msg.assistant {
    background: #2a2a3e;
}
.chat-msg.system {
    background: #1a2a1a;
    color: #8bc34a;
    text-align: center;
}
.chat-input-area {
    padding: 10px;
    border-top: 1px solid #333;
}
.quick-questions {
    display: flex;
    gap: 6px;
    margin-bottom: 8px;
    flex-wrap: wrap;
}
.quick-questions button {
    background: #2a2a3e;
    border: 1px solid #444;
    color: #bbb;
    padding: 4px 10px;
    border-radius: 12px;
    font-size: 11px;
    cursor: pointer;
}
.quick-questions button:hover { background: #3a3a4e; }
.chat-input-row {
    display: flex;
    gap: 8px;
}
.chat-input-row input {
    flex: 1;
    padding: 8px 12px;
    background: #0d0d1a;
    border: 1px solid #444;
    border-radius: 4px;
    color: #eee;
    font-size: 12px;
}
.chat-input-row button {
    padding: 8px 16px;
    background: #4a9eff;
    border: none;
    border-radius: 4px;
    color: #fff;
    cursor: pointer;
}
```

- [ ] **Step 5: Commit**

```bash
git add web/server.py web/static/app.js web/templates/index.html
git commit -m "feat(P3): add DAG node detail panel and task-level chat dialog"
```

---

### Task 6: P4 Evidence View + Causal Chain Visualization

**Files:**
- Modify: `web/server.py` — add `/api/task/{op_id}/evidence`, `/api/evidence/{evidence_id}/chain`
- Modify: `web/static/app.js` — add evidence view page
- Modify: `web/templates/index.html` — add evidence view CSS

- [ ] **Step 1: Add evidence API endpoints**

```python
@app.get("/api/task/{op_id}/evidence")
async def list_evidence(op_id: str, category: str = None, min_confidence: float = 0.0):
    """List all evidence nodes for a task, with optional filters."""
    graph_manager = get_graph_manager()
    if not hasattr(graph_manager, "causal_graph") or graph_manager.causal_graph is None:
        return {"evidence": [], "total": 0}
    
    evidence_list = []
    for node_id, node_data in graph_manager.causal_graph.nodes(data=True):
        if node_data.get("node_type") == "Evidence":
            if category and node_data.get("category") != category:
                continue
            if node_data.get("confidence", 0) < min_confidence:
                continue
            evidence_list.append({
                "id": node_id,
                "category": node_data.get("category"),
                "content": node_data.get("content"),
                "confidence": node_data.get("confidence"),
                "source_step": node_data.get("source_step"),
                "hypothesis_id": node_data.get("hypothesis_id"),
            })
    
    return {"evidence": evidence_list, "total": len(evidence_list)}


@app.get("/api/evidence/{evidence_id}")
async def get_evidence_detail(evidence_id: str):
    """Return detail for a single evidence node."""
    graph_manager = get_graph_manager()
    if not hasattr(graph_manager, "causal_graph") or not graph_manager.causal_graph.has_node(evidence_id):
        return {"error": "Evidence not found"}
    
    data = graph_manager.causal_graph.nodes[evidence_id]
    return {
        "id": evidence_id,
        "category": data.get("category"),
        "content": data.get("content"),
        "confidence": data.get("confidence"),
        "source_step": data.get("source_step"),
        "hypothesis_id": data.get("hypothesis_id"),
    }


@app.get("/api/evidence/{evidence_id}/chain")
async def get_evidence_chain(evidence_id: str):
    """Return the full causal chain: Evidence -> Hypothesis -> Vulnerability."""
    graph_manager = get_graph_manager()
    if not hasattr(graph_manager, "causal_graph"):
        return {"nodes": [], "edges": []}
    
    g = graph_manager.causal_graph
    nodes = {}
    edges = []
    
    # Walk forward from evidence
    visited = set()
    queue = [evidence_id]
    while queue:
        nid = queue.pop(0)
        if nid in visited:
            continue
        visited.add(nid)
        if g.has_node(nid):
            ndata = dict(g.nodes[nid])
            ndata["id"] = nid
            nodes[nid] = ndata
            for _, target in g.out_edges(nid):
                edges.append({"source": nid, "target": target, "label": g.edges[nid, target].get("label", "")})
                if target not in visited:
                    queue.append(target)
    
    # Walk backward to evidence
    queue = [evidence_id]
    while queue:
        nid = queue.pop(0)
        if g.has_node(nid):
            for source, _ in g.in_edges(nid):
                if source not in visited:
                    visited.add(source)
                    ndata = dict(g.nodes[source])
                    ndata["id"] = source
                    nodes[source] = ndata
                    edges.append({"source": source, "target": nid, "label": g.edges[source, nid].get("label", "")})
                    queue.append(source)
    
    return {
        "nodes": [n for n in nodes.values()],
        "edges": edges,
    }
```

- [ ] **Step 2: Add evidence view JavaScript to app.js**

```javascript
// ============================================================
// P4: Evidence View
// ============================================================

let evidenceData = [];
let evidenceFilter = { category: '', minConfidence: 0, search: '' };

function openEvidenceView() {
    document.getElementById('main-content').style.display = 'none';
    const evView = document.getElementById('evidence-view') || createEvidenceView();
    evView.style.display = 'block';
    loadEvidence();
}

function closeEvidenceView() {
    document.getElementById('evidence-view').style.display = 'none';
    document.getElementById('main-content').style.display = 'block';
}

function createEvidenceView() {
    const html = `
        <div id="evidence-view" style="display:none;">
            <div class="ev-header">
                <h2>证据浏览器</h2>
                <button onclick="closeEvidenceView()">← 返回</button>
            </div>
            <div class="ev-layout">
                <div class="ev-filter">
                    <h4>过滤</h4>
                    <label>分类</label>
                    <select id="ev-category-filter" onchange="applyEvidenceFilter()">
                        <option value="">全部</option>
                        <option value="open_port">开放端口</option>
                        <option value="service">服务</option>
                        <option value="subdomain">子域名</option>
                        <option value="tech_stack">技术栈</option>
                        <option value="vuln">漏洞</option>
                        <option value="url">URL</option>
                        <option value="http_header">HTTP头</option>
                        <option value="os">OS</option>
                    </select>
                    <label>最低置信度: <span id="confidence-label">0%</span></label>
                    <input type="range" id="ev-confidence" min="0" max="100" value="0"
                        oninput="document.getElementById('confidence-label').textContent=this.value+'%'; applyEvidenceFilter()">
                    <label>搜索</label>
                    <input type="text" id="ev-search" placeholder="关键词..." oninput="applyEvidenceFilter()">
                </div>
                <div class="ev-list">
                    <h4>证据列表 (<span id="ev-count">0</span>)</h4>
                    <div id="ev-items"></div>
                </div>
                <div class="ev-detail" id="ev-detail">
                    <p class="placeholder">选择一条证据查看详情</p>
                </div>
            </div>
        </div>
    `;
    document.body.insertAdjacentHTML('beforeend', html);
    return document.getElementById('evidence-view');
}

async function loadEvidence() {
    try {
        const resp = await fetch('/api/task/${currentTaskId || ''}/evidence');
        const data = await resp.json();
        evidenceData = data.evidence || [];
        renderEvidenceList();
    } catch (err) {
        console.error('Failed to load evidence:', err);
    }
}

function applyEvidenceFilter() {
    evidenceFilter.category = document.getElementById('ev-category-filter').value;
    evidenceFilter.minConfidence = parseInt(document.getElementById('ev-confidence').value) / 100;
    evidenceFilter.search = document.getElementById('ev-search').value.toLowerCase();
    renderEvidenceList();
}

function renderEvidenceList() {
    const filtered = evidenceData.filter(ev => {
        if (evidenceFilter.category && ev.category !== evidenceFilter.category) return false;
        if (ev.confidence < evidenceFilter.minConfidence) return false;
        if (evidenceFilter.search) {
            const content = JSON.stringify(ev.content || '').toLowerCase();
            if (!content.includes(evidenceFilter.search)) return false;
        }
        return true;
    });
    
    document.getElementById('ev-count').textContent = filtered.length;
    const container = document.getElementById('ev-items');
    
    if (filtered.length === 0) {
        container.innerHTML = '<p class="empty-state">没有匹配的证据</p>';
        return;
    }
    
    container.innerHTML = filtered.map(ev => `
        <div class="ev-item" onclick="showEvidenceDetail('${ev.id}')">
            <span class="ev-cat-tag ${ev.category}">${ev.category}</span>
            <span class="ev-preview">${String(ev.content || '').slice(0, 80)}</span>
            <span class="ev-confidence">${Math.round(ev.confidence * 100)}%</span>
        </div>
    `).join('');
}

async function showEvidenceDetail(evidenceId) {
    const detailDiv = document.getElementById('ev-detail');
    detailDiv.innerHTML = '<p>加载中...</p>';
    
    try {
        const [evResp, chainResp] = await Promise.all([
            fetch(`/api/evidence/${evidenceId}`),
            fetch(`/api/evidence/${evidenceId}/chain`),
        ]);
        const ev = await evResp.json();
        const chain = await chainResp.json();
        
        let html = `
            <h4>证据详情</h4>
            <table class="detail-table">
                <tr><td>ID</td><td>${ev.id}</td></tr>
                <tr><td>分类</td><td><span class="ev-cat-tag ${ev.category}">${ev.category}</span></td></tr>
                <tr><td>置信度</td><td><span class="confidence-bar" style="width:${ev.confidence * 100}%"></span> ${Math.round(ev.confidence * 100)}%</td></tr>
                <tr><td>来源</td><td>${ev.source_step || '-'}</td></tr>
                <tr><td>内容</td><td><pre class="raw-output">${escapeHtml(JSON.stringify(ev.content, null, 2))}</pre></td></tr>
            </table>
        `;
        
        // Causal chain visualization
        if (chain.nodes && chain.nodes.length > 0) {
            html += `<h4>因果链</h4><div class="causal-chain">`;
            // Find the path from evidence to vulnerability
            let currentId = evidenceId;
            for (const edge of chain.edges) {
                if (edge.source === currentId) {
                    const target = chain.nodes.find(n => n.id === edge.target);
                    html += `
                        <div class="chain-node ${edge.label.toLowerCase()}">
                            <span class="chain-type">${edge.label}</span>
                            <span class="chain-content">${target ? target.node_type : edge.target}</span>
                            <span class="chain-arrow">→</span>
                        </div>`;
                    currentId = edge.target;
                }
            }
            html += `</div>`;
        }
        
        detailDiv.innerHTML = html;
    } catch (err) {
        detailDiv.innerHTML = `<p class="error">加载失败: ${err.message}</p>`;
    }
}
```

- [ ] **Step 3: Add evidence view CSS to index.html**

```css
/* P4: Evidence View */
#evidence-view {
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: #0d0d1a;
    z-index: 900;
    padding: 20px;
}
.ev-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
}
.ev-header h2 { margin: 0; color: #eee; font-size: 18px; }
.ev-header button {
    background: #2a2a3e;
    border: 1px solid #444;
    color: #bbb;
    padding: 6px 14px;
    border-radius: 4px;
    cursor: pointer;
}
.ev-layout { display: flex; gap: 16px; height: calc(100vh - 80px); }
.ev-filter {
    width: 200px;
    padding: 16px;
    background: #1a1a2e;
    border-radius: 6px;
}
.ev-filter h4 { margin: 0 0 12px 0; color: #999; font-size: 13px; }
.ev-filter label {
    display: block;
    color: #888;
    font-size: 12px;
    margin: 8px 0 4px;
}
.ev-filter select,
.ev-filter input[type="text"] {
    width: 100%;
    padding: 6px 8px;
    background: #0d0d1a;
    border: 1px solid #444;
    border-radius: 4px;
    color: #eee;
    font-size: 12px;
}
.ev-filter input[type="range"] { width: 100%; margin-top: 4px; }
.ev-list {
    flex: 1;
    padding: 16px;
    background: #1a1a2e;
    border-radius: 6px;
    overflow-y: auto;
}
.ev-list h4 { margin: 0 0 12px 0; color: #999; font-size: 13px; }
.ev-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 10px;
    background: #16162a;
    border-radius: 4px;
    margin-bottom: 4px;
    cursor: pointer;
    font-size: 12px;
}
.ev-item:hover { background: #1e1e36; }
.ev-cat-tag {
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 11px;
    white-space: nowrap;
}
.ev-cat-tag.open_port { background: #1a3a3a; color: #4cafaf; }
.ev-cat-tag.service { background: #1a2a3a; color: #4a9eff; }
.ev-cat-tag.subdomain { background: #2a1a3a; color: #9c4aff; }
.ev-cat-tag.vuln { background: #3a1a1a; color: #f44336; }
.ev-cat-tag.url { background: #2a3a1a; color: #8bc34a; }
.ev-cat-tag.http_header { background: #3a2a1a; color: #ff9800; }
.ev-cat-tag.raw_output { background: #2a2a2a; color: #999; }
.ev-preview { flex: 1; overflow: hidden; text-overflow: ellipsis; color: #aaa; white-space: nowrap; }
.ev-confidence { color: #999; min-width: 40px; text-align: right; }
.ev-detail {
    width: 350px;
    padding: 16px;
    background: #1a1a2e;
    border-radius: 6px;
    overflow-y: auto;
}
.ev-detail h4 { margin: 0 0 12px 0; color: #4a9eff; font-size: 14px; }
.placeholder { color: #666; }

/* Causal Chain Visualization */
.causal-chain {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-top: 12px;
}
.chain-node {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    background: #16162a;
    border-radius: 4px;
    border-left: 3px solid #4a9eff;
    font-size: 12px;
}
.chain-node.supports { border-left-color: #4caf50; }
.chain-node.reveals { border-left-color: #ff9800; }
.chain-node.exploits { border-left-color: #f44336; }
.chain-type { color: #999; min-width: 80px; }
.chain-content { color: #ddd; flex: 1; }
.chain-arrow { color: #666; }
```

- [ ] **Step 4: Commit**

```bash
git add web/server.py web/static/app.js web/templates/index.html
git commit -m "feat(P4): add evidence browser with causal chain visualization"
```

---

## Execution Handoff

Plan complete. Use TeamCreate to coordinate:
- 1 agent for P1 (data classes + executor)
- 1 agent for P2 (parsers + graph_manager)
- 1 agent for P3 + P4 (Web UI)

P1 → P2 have serial dependency. P3/P4 can be parallel with P2 if API contracts are respected.
