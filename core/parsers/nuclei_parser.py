import json
from core.data_contracts import ToolFinding
from core.parsers import register_parser


@register_parser("nuclei")
def parse_nuclei_output(raw_output: str) -> list[ToolFinding]:
    findings: list[ToolFinding] = []
    for line in raw_output.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        template_id = data.get("template-id", data.get("templateID", ""))
        severity = data.get("severity", "unknown")
        matched_at = data.get("matched-at", data.get("matched_at", ""))

        findings.append(
            ToolFinding(
                category="vuln",
                key=f"nuclei_{template_id}",
                value={
                    "template_id": template_id,
                    "severity": severity,
                    "matched_at": matched_at,
                },
                confidence=0.8,
            )
        )

    return findings
