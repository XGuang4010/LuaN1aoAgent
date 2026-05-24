import json
from core.data_contracts import ToolFinding
from core.parsers import register_parser


@register_parser("httpx")
def parse_httpx_output(raw_output: str) -> list[ToolFinding]:
    findings: list[ToolFinding] = []
    for line in raw_output.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        url = data.get("url", data.get("input", ""))
        status_code = data.get("status_code")
        tech = data.get("tech", [])

        if status_code:
            findings.append(
                ToolFinding(
                    category="service",
                    key=url,
                    value={"url": url, "status_code": status_code},
                    confidence=1.0,
                )
            )

        if tech:
            findings.append(
                ToolFinding(
                    category="tech_stack",
                    key=url,
                    value={"url": url, "technologies": tech},
                    confidence=0.9,
                )
            )

    return findings
