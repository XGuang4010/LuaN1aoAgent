import re
from core.data_contracts import ToolFinding
from core.parsers import register_parser


@register_parser("dirsearch")
def parse_dirsearch_output(raw_output: str) -> list[ToolFinding]:
    findings: list[ToolFinding] = []
    pattern = re.compile(r"\]\s+(\d+)\s+-\s+\S+\s+-\s+(\/\S*)")
    for match in pattern.finditer(raw_output):
        status_code = int(match.group(1))
        path = match.group(2)
        findings.append(
            ToolFinding(
                category="url",
                key=path,
                value={"path": path, "status_code": status_code},
                confidence=0.95,
            )
        )

    return findings
