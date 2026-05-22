"""
启动前环境校验模块 (Preflight Checks)

在 Agent 启动前运行非交互式环境检查，验证所有依赖项并给出清晰的修复指引。
"""

import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import httpx


@dataclass
class CheckResult:
    """单项环境检查结果."""

    passed: bool
    name: str
    message: str
    fix_hint: str = ""


def _resolve_tool_path(tool_name: str, env_var_name: str, tools_home_subpath: str) -> Optional[str]:
    """根据项目约定解析工具路径 (三层优先级)."""
    explicit = os.getenv(env_var_name, "").strip()
    if explicit and os.path.exists(explicit):
        return explicit

    tools_home = os.getenv("TOOLS_HOME", "").strip()
    if tools_home:
        candidate = os.path.join(tools_home, tools_home_subpath)
        if os.path.exists(candidate):
            return candidate

    return None


def _discover_external_tools() -> List[str]:
    """从 tools/mcp_service.py 中动态发现外部工具名称."""
    mcp_service_path = Path(__file__).parent.parent / "tools" / "mcp_service.py"
    if not mcp_service_path.exists():
        return []

    content = mcp_service_path.read_text(encoding="utf-8")
    tools = set()

    # Pattern 1: cmd = ["toolname", ...] or cmd = ['toolname', ...]
    for match in re.finditer(r'cmd\s*=\s*\[\s*["\']([^"\']+)["\']', content):
        tools.add(match.group(1))

    # Pattern 2: subprocess.run(["toolname", ...] or subprocess.run(['toolname', ...])
    for match in re.finditer(r'subprocess\.(?:run|Popen)\s*\(\s*\[\s*["\']([^"\']+)["\']', content):
        tools.add(match.group(1))

    # Pattern 3: cmd = f"toolname -u ..."
    for match in re.finditer(r'cmd\s*=\s*f["\']([^"\s\']+)', content):
        tools.add(match.group(1))

    # Exclude non-tool commands
    exclude = {"python", "python3", sys.executable.split(os.sep)[-1], "uvicorn", "{", ""}
    tools = {t for t in tools if t not in exclude and not t.startswith("{") and len(t) > 1}

    return sorted(tools)


async def check_llm_api() -> CheckResult:
    """检查 LLM API 连通性."""
    from conf.config import LLM_API_BASE_URL, LLM_API_KEY, LLM_PROVIDER, ANTHROPIC_API_BASE_URL, ANTHROPIC_API_KEY

    provider = LLM_PROVIDER
    api_key = LLM_API_KEY or ANTHROPIC_API_KEY
    base_url = LLM_API_BASE_URL if provider != "anthropic" else ANTHROPIC_API_BASE_URL

    if not api_key:
        return CheckResult(
            passed=False,
            name="LLM API",
            message="LLM API 密钥未配置",
            fix_hint="请在 .env 文件中设置 LLM_API_KEY",
        )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if provider == "anthropic":
                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                }
                payload = {
                    "model": "claude-3-haiku-20240307",
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "hi"}],
                }
                resp = await client.post(base_url, headers=headers, json=payload)
            else:
                headers = {"Authorization": f"Bearer {api_key}"}
                resp = await client.get(f"{base_url}/models", headers=headers)

            if resp.status_code in (401, 403):
                return CheckResult(
                    passed=True,
                    name="LLM API",
                    message=f"LLM API 服务可达，但认证失败 ({base_url}, 状态码: {resp.status_code})",
                )
            return CheckResult(
                passed=True,
                name="LLM API",
                message=f"LLM API 可连通 ({base_url}, 状态码: {resp.status_code})",
            )
    except httpx.RequestError as e:
        return CheckResult(
            passed=False,
            name="LLM API",
            message=f"LLM API 连接失败: {e}",
            fix_hint="请检查网络连接、LLM_API_BASE_URL 和 LLM_API_KEY 配置",
        )


def check_mcp_servers() -> CheckResult:
    """检查 MCP 服务器配置 (从 mcp.json 动态读取)."""
    mcp_json_path = Path(__file__).parent.parent / "mcp.json"
    if not mcp_json_path.exists():
        return CheckResult(
            passed=False,
            name="MCP Servers",
            message="mcp.json 配置文件不存在",
            fix_hint="请确认项目根目录存在 mcp.json",
        )

    try:
        with open(mcp_json_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        return CheckResult(
            passed=False,
            name="MCP Servers",
            message=f"mcp.json 解析失败: {e}",
            fix_hint="请检查 mcp.json 格式是否正确",
        )

    servers = config.get("mcpServers", {})
    if not servers:
        return CheckResult(
            passed=False,
            name="MCP Servers",
            message="mcp.json 中未配置任何 MCP 服务器",
            fix_hint="请在 mcp.json 的 mcpServers 中配置至少一个服务器",
        )

    issues = []
    for name, cfg in servers.items():
        cmd = cfg.get("command", "")
        args = cfg.get("args", [])

        # Only validate absolute paths; relative commands are executable names
        if os.path.isabs(cmd) and not os.path.exists(cmd):
            issues.append(f"服务器 '{name}' 的命令 '{cmd}' 不存在")
            continue

        for arg in args:
            if arg.startswith("-") or arg.startswith("--"):
                continue
            # Only check arguments that look like file paths
            if not (
                arg.startswith("/")
                or arg.startswith("./")
                or arg.startswith("../")
                or re.match(r"^[A-Za-z]:\\", arg)
            ):
                continue
            arg_path = Path(__file__).parent.parent / arg
            if not arg_path.exists() and not Path(arg).exists():
                issues.append(f"服务器 '{name}' 的参数文件 '{arg}' 不存在")
                break

    if issues:
        return CheckResult(
            passed=False,
            name="MCP Servers",
            message=f"{len(issues)} 个 MCP 服务器配置问题: {'; '.join(issues)}",
            fix_hint="请检查 mcp.json 中的命令路径和参数文件路径",
        )

    return CheckResult(
        passed=True,
        name="MCP Servers",
        message=f"{len(servers)} 个 MCP 服务器配置正常",
    )


def check_external_tools() -> List[CheckResult]:
    """检查外部渗透测试工具可执行性."""
    discovered = _discover_external_tools()

    # Merge with known project tools to ensure coverage
    known_tools = {"sqlmap", "dirsearch", "nuclei", "searchsploit", "httpx", "subfinder", "nmap"}
    tool_names = sorted(set(discovered) | known_tools)

    env_var_map = {
        "sqlmap": "SQLMAP_PATH",
        "dirsearch": "DIRSEARCH_PATH",
        "nuclei": "NUCLEI_PATH",
        "searchsploit": "SEARCHSPLOIT_PATH",
        "httpx": "PD_HTTPX_PATH",
        "subfinder": "SUBFINDER_PATH",
        "nmap": "NMAP_PATH",
    }

    results = []
    for tool in tool_names:
        env_var = env_var_map.get(tool, f"{tool.upper()}_PATH")
        subpath = os.path.join(tool, f"{tool}.exe")
        resolved = _resolve_tool_path(tool, env_var, subpath)

        if resolved:
            results.append(
                CheckResult(
                    passed=True,
                    name=f"Tool: {tool}",
                    message=f"已找到: {resolved}",
                )
            )
        else:
            fix = f"设置 {env_var} 或在 TOOLS_HOME 下安装 {tool}/{tool}.exe"
            if tool == "searchsploit":
                fix = "Download from GitHub and set SEARCHSPLOIT_PATH, or apt install exploitdb (Kali/Linux)"
            elif tool == "httpx":
                fix = "设置 PD_HTTPX_PATH 或在 TOOLS_HOME/httpx/ 下安装 httpx.exe"
            results.append(
                CheckResult(
                    passed=False,
                    name=f"Tool: {tool}",
                    message=f"未找到工具: {tool}",
                    fix_hint=fix,
                )
            )

    return results


async def check_rag_service() -> CheckResult:
    """检查 RAG 知识服务健康状态."""
    from conf.config import KNOWLEDGE_SERVICE_URL

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{KNOWLEDGE_SERVICE_URL}/health")
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "healthy":
                    return CheckResult(
                        passed=True,
                        name="RAG Knowledge Service",
                        message=f"知识服务运行正常 ({KNOWLEDGE_SERVICE_URL})",
                    )
                return CheckResult(
                    passed=False,
                    name="RAG Knowledge Service",
                    message=f"知识服务状态异常: {data}",
                    fix_hint="请检查知识服务日志或重启服务",
                )
            return CheckResult(
                passed=False,
                name="RAG Knowledge Service",
                message=f"知识服务返回状态码 {response.status_code}",
                fix_hint=f"请确保知识服务在 {KNOWLEDGE_SERVICE_URL} 运行",
            )
    except httpx.RequestError as e:
        return CheckResult(
            passed=False,
            name="RAG Knowledge Service",
            message=f"知识服务连接失败: {e}",
            fix_hint="请启动知识服务: python -m uvicorn rag.knowledge_service:app --host 0.0.0.0 --port 8081",
        )


async def check_database() -> CheckResult:
    """检查数据库可写性."""
    try:
        from core.database.utils import DB_URL
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy import text

        engine = create_async_engine(
            DB_URL, echo=False, connect_args={"timeout": 30}, pool_pre_ping=True
        )
        async with engine.begin() as conn:
            await conn.execute(text("CREATE TABLE IF NOT EXISTS _preflight_test (id INTEGER PRIMARY KEY)"))
            await conn.execute(text("INSERT INTO _preflight_test (id) VALUES (1) ON CONFLICT(id) DO UPDATE SET id=1"))
            await conn.execute(text("DELETE FROM _preflight_test WHERE id=1"))
        await engine.dispose()
        return CheckResult(
            passed=True,
            name="Database",
            message=f"数据库可写 ({DB_URL})",
        )
    except Exception as e:
        return CheckResult(
            passed=False,
            name="Database",
            message=f"数据库连接或写入失败: {e}",
            fix_hint="请检查数据库文件路径权限和磁盘空间",
        )


async def run_env_check() -> List[CheckResult]:
    """运行所有环境检查并返回结果列表."""
    checks: List[CheckResult] = []
    checks.append(await check_llm_api())
    checks.append(check_mcp_servers())
    checks.extend(check_external_tools())
    checks.append(await check_rag_service())
    checks.append(await check_database())
    return checks


def print_preflight_report(checks: List[CheckResult]) -> None:
    """打印环境检查结果及修复建议."""
    print("\n" + "=" * 60)
    print(" LuaN1ao Agent 启动前环境校验报告")
    print("=" * 60)

    passed = 0
    failed = 0

    for check in checks:
        status = "PASS" if check.passed else "FAIL"
        icon = "[OK]" if check.passed else "[FAIL]"
        print(f"\n{icon} [{status}] {check.name}")
        print(f"      {check.message}")
        if not check.passed and check.fix_hint:
            print(f"      Fix: {check.fix_hint}")
            failed += 1
        else:
            passed += 1

    print("\n" + "-" * 60)
    print(f" 总计: {passed} 项通过, {failed} 项失败")
    print("=" * 60 + "\n")
