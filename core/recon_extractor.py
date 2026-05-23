"""ReconExtractor: ingest structured findings from tool output into ReconStore."""
import json
from typing import Any, Dict
from urllib.parse import urlparse

from core.recon_store import ReconStore


class ReconExtractor:
    """Extract recon information from tool results and persist to ReconStore."""

    def __init__(self, store: ReconStore = None):
        self.store = store or ReconStore()

    async def extract_from_tool_result(
        self,
        task_id: str,
        step_id: str,
        tool_name: str,
        tool_params: Dict,
        result_str: str,
    ) -> None:
        """Parse tool output and write recon records.

        Channel 1: structured_findings (deterministic, no LLM needed).
        Channel 2: LLM-based extraction for unstructured output (placeholder).
        """
        # Channel 1: structured_findings
        try:
            data = json.loads(result_str)
            if isinstance(data, dict) and "structured_findings" in data:
                await self._ingest_structured_findings(task_id, step_id, data["structured_findings"])
                return
        except (json.JSONDecodeError, TypeError):
            pass

        # Channel 2: LLM extraction (placeholder)
        # TODO: implement LLM-based extraction for unstructured outputs

    async def _ingest_structured_findings(
        self,
        task_id: str,
        step_id: str,
        findings: Dict[str, Any],
    ) -> None:
        """Ingest a structured_findings dict into ReconStore."""
        # nmap_scan findings
        if "hosts" in findings:
            for host in findings["hosts"]:
                target = host.get("ip") or host.get("hostname") or "unknown"
                if host.get("ip"):
                    await self.store.add_record(
                        task_id, "ip", target,
                        {"address": host["ip"], "type": "ipv4", "cdn": False},
                        step_id, 1.0,
                    )
                if host.get("hostname"):
                    await self.store.add_record(
                        task_id, "domain", target,
                        {"name": host["hostname"]},
                        step_id, 1.0,
                    )
                for port in host.get("ports", []):
                    await self.store.add_record(
                        task_id, "port", target,
                        {
                            "number": port["number"],
                            "protocol": port["protocol"],
                            "state": port["state"],
                            "service_hint": port.get("service", {}).get("name", ""),
                        },
                        step_id, 1.0,
                    )
                    service = port.get("service")
                    if service:
                        await self.store.add_record(
                            task_id, "service", target,
                            {
                                "name": service.get("name", ""),
                                "version": service.get("version", ""),
                                "banner": f"{service.get('product', '')} {service.get('version', '')}".strip(),
                            },
                            step_id, 1.0,
                        )

        # httpx_scan findings
        if "endpoints" in findings:
            for ep in findings["endpoints"]:
                url = ep.get("url", "")
                target = _extract_host_from_url(url) or "unknown"
                await self.store.add_record(
                    task_id, "endpoint", target,
                    {
                        "url": url,
                        "status_code": ep.get("status_code"),
                        "title": ep.get("title", ""),
                    },
                    step_id, 1.0,
                )


def _extract_host_from_url(url: str) -> str:
    """Extract hostname from a URL."""
    try:
        parsed = urlparse(url)
        return parsed.hostname or ""
    except Exception:
        return ""
