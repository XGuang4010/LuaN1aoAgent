"""TestPolicy module for parsing and enforcing testing policies."""
from typing import Any, Dict, Optional

VULN_TYPE_KEYWORDS: Dict[str, list] = {
    "sql_injection": ["sql", "sqli", "注入", "injection"],
    "ssrf": ["ssrf", "服务器请求伪造", "server-side request forgery"],
    "command_execution": ["rce", "命令执行", "command execution", "cmd", "remote code"],
    "file_upload": ["upload", "文件上传", "file upload"],
    "xss": ["xss", "跨站", "cross-site scripting"],
    "idor": ["idor", "越权", "水平越权", "垂直越权", "unauthorized access", "privilege escalation"],
}

HARD_DENYLIST: list = [
    "rm -rf /",
    "reboot",
    "poweroff",
    "mkfs",
    "dd if=/dev/zero",
    "iptables -F",
]


class TestPolicy:
    """Parses natural-language policy docs and provides constraint lookups."""
    __test__ = False  # Prevent pytest from collecting this as a test class

    def __init__(self, raw_policy: str = ""):
        self.raw_policy = raw_policy
        self.parsed: Optional[Dict[str, Any]] = None
        self.parse_status = "pending"

    def classify_vuln_type(self, description: str) -> Optional[str]:
        """Match a subtask description against known vulnerability keywords."""
        desc_lower = description.lower()
        for vuln_type, keywords in VULN_TYPE_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in desc_lower:
                    return vuln_type
        return None

    def parse_policy(self, raw_text: str) -> Dict[str, Any]:
        """Parse raw policy text into structured constraints by vuln type.

        This is a lightweight mock implementation for unit-testability.
        Production usage should call an LLM to perform the parsing.
        """
        result: Dict[str, Any] = {}
        lower = raw_text.lower()

        if "sleep" in raw_text or "sql" in lower or "注入" in raw_text:
            result["sql_injection"] = {"allowed_verification": ["sleep"]}
        if "ssrf" in lower or "callback" in lower or "服务器请求伪造" in raw_text:
            result["ssrf"] = {"callback_url": "https://cb.net"}
        if "upload" in lower or "文件上传" in raw_text:
            result["file_upload"] = {"forbidden": ["webshell", "memory_shell"]}
        if "rce" in lower or "命令执行" in raw_text or "remote code" in lower:
            result["command_execution"] = {"allowed": ["cat", "ls", "id", "whoami"], "forbidden": ["nc", "bash -i"]}
        if "xss" in lower or "跨站" in raw_text:
            result["xss"] = {"allowed_verification": ["alert(1)"]}
        if "idor" in lower or "越权" in raw_text:
            result["idor"] = {"scope_limit": "specified_user_id_range"}

        self.parsed = result
        self.parse_status = "success" if result else "partial"
        return result

    def get_constraints(self, vuln_type: str) -> Optional[Dict[str, Any]]:
        """Return constraints for a given vulnerability type."""
        if not self.parsed:
            return None
        return self.parsed.get(vuln_type)

    def check_hard_denylist(self, command: str) -> bool:
        """Return False if *command* matches a hard-denied pattern, else True."""
        for pattern in HARD_DENYLIST:
            if pattern in command:
                return False
        return True
