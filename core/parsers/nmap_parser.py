import re
from core.data_contracts import ToolFinding
from core.parsers import register_parser


@register_parser("nmap")
def parse_nmap_output(raw_output: str) -> list[ToolFinding]:
    findings: list[ToolFinding] = []
    pattern = re.compile(r"(\d+)/(tcp|udp)\s+open\s+(\S+)(?:\s+(.*))?")
    for match in pattern.finditer(raw_output):
        port = match.group(1)
        protocol = match.group(2)
        service = match.group(3)
        service_version = match.group(4) or ""

        key = f"{port}/{protocol}"
        findings.append(
            ToolFinding(
                category="open_port",
                key=key,
                value={"port": int(port), "protocol": protocol, "service": service, "version": service_version},
                confidence=1.0,
            )
        )
        findings.append(
            ToolFinding(
                category="service",
                key=key,
                value=service_version if service_version else service,
                confidence=0.9,
            )
        )

    return findings
