from core.data_contracts import ToolFinding
from core.parsers import register_parser


@register_parser("subfinder")
def parse_subfinder_output(raw_output: str) -> list[ToolFinding]:
    findings: list[ToolFinding] = []
    for line in raw_output.strip().splitlines():
        subdomain = line.strip()
        if subdomain:
            findings.append(
                ToolFinding(
                    category="subdomain",
                    key=subdomain,
                    value=subdomain,
                    confidence=0.9,
                )
            )

    return findings
