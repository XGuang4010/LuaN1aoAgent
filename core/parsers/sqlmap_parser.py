import re
from core.data_contracts import ToolFinding
from core.parsers import register_parser


@register_parser("sqlmap")
def parse_sqlmap_output(raw_output: str) -> list[ToolFinding]:
    findings: list[ToolFinding] = []
    pattern = re.compile(r"Parameter:\s+(.+?)\s+\((GET|POST)\)")
    for match in pattern.finditer(raw_output):
        param = match.group(1).strip()
        method = match.group(2)
        key = f"sqli_{param}"
        findings.append(
            ToolFinding(
                category="vuln",
                key=key,
                value={"parameter": param, "method": method},
                confidence=0.9,
            )
        )

    return findings
