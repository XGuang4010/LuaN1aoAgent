import re
from core.data_contracts import ToolFinding
from core.parsers import register_parser


@register_parser("http")
def parse_http_output(raw_output: str) -> list[ToolFinding]:
    findings: list[ToolFinding] = []
    lines = raw_output.splitlines()
    for i, line in enumerate(lines):
        # HTTP/1.1 status line
        status_match = re.match(r"HTTP/1\.\d\s+(\d{3})", line)
        if status_match:
            status_code = int(status_match.group(1))
            findings.append(
                ToolFinding(
                    category="service",
                    key="status_code",
                    value=status_code,
                    confidence=1.0,
                )
            )
            continue

        # Header lines
        header_match = re.match(r"^([\w-]+):\s*(.+)", line, re.IGNORECASE)
        if header_match:
            header_name = header_match.group(1).lower()
            header_value = header_match.group(2).strip()
            if header_name in ("server", "x-powered-by", "content-type"):
                findings.append(
                    ToolFinding(
                        category="http_header",
                        key=header_name,
                        value=header_value,
                        confidence=1.0,
                    )
                )

    return findings
