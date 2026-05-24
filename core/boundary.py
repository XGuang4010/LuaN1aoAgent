from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import ipaddress
import re
from urllib.parse import urlparse


@dataclass
class ScopeConfig:
    allowed_targets: List[str] = field(default_factory=lambda: ["*"])
    blocked_targets: List[str] = field(default_factory=lambda: [
        "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
        "127.0.0.0/8", "169.254.0.0/16", "0.0.0.0/8"
    ])
    allowed_ports: List[int] = field(default_factory=lambda: [80, 443, 8080, 8443])
    disabled_tools: List[str] = field(default_factory=list)
    tool_param_rules: Dict[str, Any] = field(default_factory=dict)
    disable_shell_exec: bool = False
    disable_python_exec: bool = False
    block_private_network: bool = True
    block_dns_rebinding: bool = True
    enforce_tls_verification: bool = True
    max_response_size: int = 50000
    rate_limit_requests_per_sec: float = 10.0
    max_concurrent_connections: int = 20
    blocked_scan_types: List[str] = field(default_factory=lambda: ["udp_full", "tcp_full"])

    @classmethod
    def from_global_config(cls, overrides: Optional[Dict] = None) -> 'ScopeConfig':
        from conf.config import SCOPE_DEFAULTS
        data = SCOPE_DEFAULTS.copy()
        if overrides:
            data.update(overrides)
        return cls(**data)

    def to_dict(self) -> Dict:
        return {
            "allowed_targets": self.allowed_targets,
            "blocked_targets": self.blocked_targets,
            "allowed_ports": self.allowed_ports,
            "disabled_tools": self.disabled_tools,
            "tool_param_rules": self.tool_param_rules,
            "disable_shell_exec": self.disable_shell_exec,
            "disable_python_exec": self.disable_python_exec,
            "block_private_network": self.block_private_network,
            "block_dns_rebinding": self.block_dns_rebinding,
            "enforce_tls_verification": self.enforce_tls_verification,
            "max_response_size": self.max_response_size,
            "rate_limit_requests_per_sec": self.rate_limit_requests_per_sec,
            "max_concurrent_connections": self.max_concurrent_connections,
            "blocked_scan_types": self.blocked_scan_types,
        }

    def to_prompt_context(self) -> str:
        lines = ["## 渗透测试边界约束"]
        lines.append(f"- 允许目标: {', '.join(self.allowed_targets)}")
        lines.append(f"- 禁止目标: {', '.join(self.blocked_targets)}")
        lines.append(f"- 允许端口: {', '.join(map(str, self.allowed_ports))}")
        if self.disabled_tools:
            lines.append(f"- 禁用工具: {', '.join(self.disabled_tools)}")
        if self.blocked_scan_types:
            lines.append(f"- 禁止扫描类型: {', '.join(self.blocked_scan_types)}")
        if self.disable_shell_exec:
            lines.append("- ⚠️ shell_exec 已禁用")
        if self.disable_python_exec:
            lines.append("- ⚠️ python_exec 已禁用")
        lines.append(f"- 最大响应大小: {self.max_response_size} 字节")
        return "\n".join(lines)


@dataclass
class BoundaryCheckResult:
    allowed: bool
    reason: str = ""
    rule_name: str = ""
    detail: Dict[str, Any] = field(default_factory=dict)


class BoundaryValidator:
    def __init__(self, scope: ScopeConfig):
        self.scope = scope
        self._rate_limit_tokens = 0.0
        self._last_check_time = 0.0

    def validate_tool_call(self, tool_name: str, params: Dict) -> BoundaryCheckResult:
        # 1. disabled_tools 检查（最高优先级）
        if tool_name in self.scope.disabled_tools:
            return BoundaryCheckResult(False, f"工具 '{tool_name}' 已被全局禁用", "disabled_tools", {"tool": tool_name})
        
        # 2. shell_exec / python_exec 单独开关
        if tool_name == "shell_exec" and self.scope.disable_shell_exec:
            return BoundaryCheckResult(False, "shell_exec 已被禁用", "disable_shell_exec")
        if tool_name == "python_exec" and self.scope.disable_python_exec:
            return BoundaryCheckResult(False, "python_exec 已被禁用", "disable_python_exec")
        
        # 3. 目标地址检查（从 params 中提取 url/host/target）
        target = self._extract_target(params)
        if target:
            # 从 URL 或 params 中提取端口
            port = self._extract_port(params)
            result = self.validate_target(target, port)
            if not result.allowed:
                return result
        
        # 4. 扫描类型限制（针对 nmap_scan）
        if tool_name == "nmap_scan" and self.scope.blocked_scan_types:
            result = self._check_blocked_scan_types(params)
            if not result.allowed:
                return result
        
        # 5. 速率限制检查
        result = self._check_rate_limit()
        if not result.allowed:
            return result
        
        return BoundaryCheckResult(True)

    def validate_target(self, host: str, port: int = None) -> BoundaryCheckResult:
        # 解析 IP / 域名
        ip = self._resolve_to_ip(host)
        
        # blocked_targets
        for blocked in self.scope.blocked_targets:
            try:
                if ipaddress.ip_address(ip) in ipaddress.ip_network(blocked, strict=False):
                    return BoundaryCheckResult(False, f"目标 {host} 命中禁止网段 {blocked}", "blocked_targets", {"host": host, "ip": ip, "blocked": blocked})
            except ValueError:
                continue
        
        # block_private_network
        if self.scope.block_private_network:
            try:
                addr = ipaddress.ip_address(ip)
                if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
                    return BoundaryCheckResult(False, f"目标 {host} ({ip}) 属于私有/保留地址", "block_private_network", {"host": host, "ip": ip})
            except ValueError:
                pass
        
        # allowed_ports
        if port is not None and self.scope.allowed_ports:
            if port not in self.scope.allowed_ports:
                return BoundaryCheckResult(False, f"端口 {port} 不在允许列表中", "allowed_ports", {"host": host, "port": port})
        
        # allowed_targets
        if self.scope.allowed_targets != ["*"]:
            allowed = False
            for allowed_target in self.scope.allowed_targets:
                if self._match_target(host, ip, allowed_target):
                    allowed = True
                    break
            if not allowed:
                return BoundaryCheckResult(False, f"目标 {host} 不在允许的目标列表中", "allowed_targets", {"host": host})
        
        return BoundaryCheckResult(True)

    def _extract_target(self, params: Dict) -> Optional[str]:
        for key in ["url", "host", "target", "domain", "ip"]:
            val = params.get(key)
            if val:
                raw = str(val)
                # 如果是完整 URL，解析出 hostname
                if key == "url" and ("://" in raw or raw.startswith("//")):
                    try:
                        parsed = urlparse(raw)
                        if parsed.hostname:
                            return parsed.hostname
                    except Exception:
                        pass
                return raw
        return None

    def _extract_port(self, params: Dict) -> Optional[int]:
        """从 params 中提取端口号，优先从 URL 解析，其次用显式 port 参数。"""
        # 优先用显式 port 参数
        port = params.get("port")
        if port is not None:
            try:
                return int(port)
            except (ValueError, TypeError):
                pass
        # 从 URL 解析
        url = params.get("url")
        if url:
            try:
                parsed = urlparse(str(url))
                if parsed.port:
                    return parsed.port
                # 默认端口映射
                if parsed.scheme == "https":
                    return 443
                if parsed.scheme == "http":
                    return 80
            except Exception:
                pass
        return None

    def _resolve_to_ip(self, host: str) -> str:
        # 简化实现：如果是 IP 直接返回，否则尝试解析
        try:
            ipaddress.ip_address(host)
            return host
        except ValueError:
            import socket
            try:
                return socket.getaddrinfo(host, None)[0][4][0]
            except Exception:
                return host

    def _match_target(self, host: str, ip: str, pattern: str) -> bool:
        if pattern == "*":
            return True
        if host == pattern or ip == pattern:
            return True
        try:
            return ipaddress.ip_address(ip) in ipaddress.ip_network(pattern, strict=False)
        except ValueError:
            pass
        # 支持通配符域名匹配（如 *.example.com）
        regex = pattern.replace(".", r"\.").replace("*", ".*")
        if re.match(f"^{regex}$", host):
            return True
        return False

    def _check_blocked_scan_types(self, params: Dict) -> BoundaryCheckResult:
        """检查 nmap_scan 参数是否包含被禁止的扫描类型。"""
        args = params.get("args", "")
        ports = params.get("ports", "")
        args_lower = str(args).lower()
        ports_str = str(ports)

        # udp_full: UDP 全端口扫描
        if "udp_full" in self.scope.blocked_scan_types:
            if "-su" in args_lower or "-sU" in str(args):
                if "1-65535" in ports_str or ports_str == "1-65535":
                    return BoundaryCheckResult(
                        False,
                        "UDP 全端口扫描 (-sU -p 1-65535) 已被禁止",
                        "blocked_scan_types",
                        {"blocked": "udp_full", "args": args, "ports": ports}
                    )

        # tcp_full: TCP 全端口扫描
        if "tcp_full" in self.scope.blocked_scan_types:
            if "1-65535" in ports_str or ports_str == "1-65535":
                return BoundaryCheckResult(
                    False,
                    "TCP 全端口扫描 (-p 1-65535) 已被禁止，请使用常用端口范围",
                    "blocked_scan_types",
                    {"blocked": "tcp_full", "ports": ports}
                )

        return BoundaryCheckResult(True)

    def _check_rate_limit(self) -> BoundaryCheckResult:
        import time
        now = time.time()
        elapsed = now - self._last_check_time
        self._rate_limit_tokens = min(self.scope.rate_limit_requests_per_sec, self._rate_limit_tokens + elapsed * self.scope.rate_limit_requests_per_sec)
        self._last_check_time = now
        if self._rate_limit_tokens < 1.0:
            return BoundaryCheckResult(False, "请求速率超过限制", "rate_limit", {"limit": self.scope.rate_limit_requests_per_sec})
        self._rate_limit_tokens -= 1.0
        return BoundaryCheckResult(True)

    def to_prompt_instruction(self) -> str:
        return self.scope.to_prompt_context()
