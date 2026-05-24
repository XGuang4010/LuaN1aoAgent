"""
渗透测试报告生成器

在任务正常完成后自动生成 Markdown 格式的渗透测试报告，
包含执行摘要、目标指纹、发现汇总、证据链和建议。
"""

import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from rich.panel import Panel


class PentestReportGenerator:
    """基于 GraphManager 数据自动生成渗透测试报告."""

    # 敏感信息正则匹配模式
    _SENSITIVE_PATTERNS = [
        (re.compile(r'(api[_-]?key\s*[:=]\s*)["\']?[\w\-]{8,}["\']?', re.IGNORECASE), r'\1***'),
        (re.compile(r'(token\s*[:=]\s*)["\']?[\w\-]{8,}["\']?', re.IGNORECASE), r'\1***'),
        (re.compile(r'(secret\s*[:=]\s*)["\']?[\w\-]{8,}["\']?', re.IGNORECASE), r'\1***'),
        (re.compile(r'(password\s*[:=]\s*)["\']?[\w\-]{4,}["\']?', re.IGNORECASE), r'\1***'),
        (re.compile(r'(authorization\s*[:=]\s*(?:[bB]earer\s+)?)["\']?[\w\-\.]{8,}["\']?', re.IGNORECASE), r'\1***'),
        (re.compile(r'(access[_-]?token\s*[:=]\s*)["\']?[\w\-]{8,}["\']?', re.IGNORECASE), r'\1***'),
        (re.compile(r'(session[_-]?id\s*[:=]\s*)["\']?[\w\-]{8,}["\']?', re.IGNORECASE), r'\1***'),
        (re.compile(r'(sk-[a-zA-Z0-9]{20,})', re.IGNORECASE), r'***'),
    ]

    def __init__(self, graph_manager: Any, task_id: str, task_name: str, log_dir: str):
        self.graph_manager = graph_manager
        self.task_id = task_id
        self.task_name = task_name
        self.log_dir = log_dir
        self.report_path = os.path.join(log_dir, "report.md")

    def _redact(self, text: str) -> str:
        """自动脱敏文本中的 API 密钥和令牌."""
        if not isinstance(text, str):
            text = str(text)
        for pattern, replacement in self._SENSITIVE_PATTERNS:
            text = pattern.sub(replacement, text)
        return text

    def _get_start_time(self) -> float:
        """从 graph_manager 推断任务开始时间."""
        root_data = self.graph_manager.graph.nodes.get(self.graph_manager.task_id, {})
        return root_data.get("start_time", time.time())

    def _build_executive_summary(self) -> str:
        """构建执行摘要部分."""
        root_data = self.graph_manager.graph.nodes.get(self.graph_manager.task_id, {})
        goal = root_data.get("goal", "N/A")
        status = root_data.get("status", "unknown")
        start_time = self._get_start_time()
        duration = time.time() - start_time

        lines = [
            "## 1. 执行摘要 (Executive Summary)",
            "",
            f"- **任务名称**: {self.task_name}",
            f"- **任务目标**: {goal}",
            f"- **任务状态**: {status}",
            f"- **执行时长**: {duration:.1f} 秒 ({duration/60:.1f} 分钟)",
            f"- **任务 ID**: {self.task_id}",
            f"- **报告生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
        ]
        return "\n".join(lines)

    def _build_target_fingerprint(self) -> str:
        """构建目标指纹部分，从证据节点提取技术栈、端口、服务信息."""
        fingerprints: Dict[str, List[str]] = {
            "open_port": [],
            "service": [],
            "tech_stack": [],
            "os": [],
            "subdomain": [],
            "url": [],
        }

        for node_id, data in self.graph_manager.causal_graph.nodes(data=True):
            node_type = data.get("node_type", data.get("type", ""))
            if node_type != "Evidence":
                continue
            findings = data.get("extracted_findings", {})
            if isinstance(findings, dict):
                for cat, vals in findings.items():
                    if cat in fingerprints and isinstance(vals, list):
                        fingerprints[cat].extend(str(v) for v in vals)

        lines = [
            "## 2. 目标指纹 (Target Fingerprint)",
            "",
        ]

        for category, label in [
            ("open_port", "开放端口"),
            ("service", "运行服务"),
            ("tech_stack", "技术栈"),
            ("os", "操作系统"),
            ("subdomain", "子域名"),
            ("url", "URL 路径"),
        ]:
            vals = fingerprints.get(category, [])
            if vals:
                unique_vals = sorted(set(vals))
                lines.append(f"- **{label}**: {', '.join(unique_vals[:20])}{' ...' if len(unique_vals) > 20 else ''}")
            else:
                lines.append(f"- **{label}**: 未发现")

        lines.append("")
        return "\n".join(lines)

    def _build_findings_table(self) -> str:
        """构建发现汇总表格."""
        findings: List[Dict[str, Any]] = []

        for node_id, data in self.graph_manager.causal_graph.nodes(data=True):
            node_type = data.get("node_type", data.get("type", ""))
            if node_type in {"Vulnerability", "ConfirmedVulnerability", "PossibleVulnerability"}:
                findings.append({
                    "category": "漏洞",
                    "key": node_id,
                    "value": data.get("description", "N/A"),
                    "confidence": data.get("confidence", data.get("cvss_score", "N/A")),
                })
            elif node_type == "Hypothesis":
                findings.append({
                    "category": "假设",
                    "key": node_id,
                    "value": data.get("description", "N/A"),
                    "confidence": data.get("confidence", "N/A"),
                })
            elif node_type == "Exploit":
                findings.append({
                    "category": "利用",
                    "key": node_id,
                    "value": data.get("description", "N/A"),
                    "confidence": data.get("expected_outcome", "N/A"),
                })

        # 从 shared_findings 补充
        for sf in getattr(self.graph_manager, "shared_findings", []):
            if isinstance(sf, dict):
                findings.append({
                    "category": sf.get("category", "发现"),
                    "key": sf.get("id", "shared"),
                    "value": sf.get("description", sf.get("finding", "N/A")),
                    "confidence": sf.get("confidence", "N/A"),
                })

        lines = [
            "## 3. 发现汇总 (Findings)",
            "",
            "| 类别 | 标识 | 描述 | 置信度/评分 |",
            "|------|------|------|-------------|",
        ]

        if findings:
            for f in findings:
                cat = f.get("category", "N/A")
                key = f.get("key", "N/A")
                val = str(f.get("value", "N/A")).replace("|", "\\|").replace("\n", " ")[:120]
                conf = f.get("confidence", "N/A")
                lines.append(f"| {cat} | `{key}` | {val} | {conf} |")
        else:
            lines.append("| - | - | 未发现显著发现 | - |")

        lines.append("")
        return "\n".join(lines)

    def _build_evidence_list(self) -> str:
        """构建证据列表及因果链链接."""
        evidence_nodes: List[Dict[str, Any]] = []

        for node_id, data in self.graph_manager.causal_graph.nodes(data=True):
            node_type = data.get("node_type", data.get("type", ""))
            if node_type == "Evidence":
                evidence_nodes.append({
                    "id": node_id,
                    "tool": data.get("tool_name", "N/A"),
                    "description": data.get("description", data.get("raw_output", "")[:200]),
                    "host": data.get("host", "N/A"),
                    "port": data.get("port", "N/A"),
                })

        lines = [
            "## 4. 证据列表 (Evidence)",
            "",
        ]

        if evidence_nodes:
            for ev in evidence_nodes:
                lines.append(f"- **{ev['id']}** (`{ev['tool']}`)")
                lines.append(f"  - 描述: {ev['description']}")
                lines.append(f"  - 目标: {ev['host']}:{ev['port']}")
                # 查找因果链上游/下游
                upstream = list(self.graph_manager.causal_graph.predecessors(ev["id"]))
                downstream = list(self.graph_manager.causal_graph.successors(ev["id"]))
                if upstream:
                    lines.append(f"  - 支持: {', '.join(upstream)}")
                if downstream:
                    lines.append(f"  - 推导: {', '.join(downstream)}")
                lines.append("")
        else:
            lines.append("未收集到证据节点。\n")

        return "\n".join(lines)

    def _build_recommendations(self) -> str:
        """构建建议部分，基于失败模式和漏洞生成."""
        recommendations: List[str] = []

        # 从漏洞节点生成修复建议
        for node_id, data in self.graph_manager.causal_graph.nodes(data=True):
            node_type = data.get("node_type", data.get("type", ""))
            if node_type in {"Vulnerability", "ConfirmedVulnerability"}:
                desc = data.get("description", "")
                if desc:
                    recommendations.append(f"- 修复漏洞 `{node_id}`: {desc}")

        # 从任务图中的失败子任务生成建议
        for node_id, data in self.graph_manager.graph.nodes(data=True):
            if data.get("type") == "subtask" and data.get("status") == "failed":
                summary = data.get("summary", "")
                if summary:
                    recommendations.append(f"- 回顾失败子任务 `{node_id}`: {summary}")

        lines = [
            "## 5. 建议 (Recommendations)",
            "",
        ]

        if recommendations:
            lines.extend(recommendations)
        else:
            lines.append("- 未发现明确的安全问题，建议保持常规安全监控。")

        lines.append("")
        return "\n".join(lines)

    def _build_causal_chain_summary(self) -> str:
        """构建因果链推理摘要."""
        edges = []
        for u, v, d in self.graph_manager.causal_graph.edges(data=True):
            label = d.get("label", "LINK")
            edges.append(f"- `{u}` --[{label}]--> `{v}`")

        lines = [
            "## 6. 因果推理链 (Causal Chain)",
            "",
        ]
        if edges:
            lines.extend(edges[:50])
            if len(edges) > 50:
                lines.append(f"\n... 共 {len(edges)} 条关系边，已截断显示。")
        else:
            lines.append("暂无因果推理链数据。")
        lines.append("")
        return "\n".join(lines)

    def generate(self) -> str:
        """生成 Markdown 报告并保存到 log_dir/report.md，返回文件路径."""
        sections = [
            f"# LuaN1ao 渗透测试报告: {self.task_name}",
            "",
            self._build_executive_summary(),
            self._build_target_fingerprint(),
            self._build_findings_table(),
            self._build_evidence_list(),
            self._build_recommendations(),
            self._build_causal_chain_summary(),
        ]

        raw_report = "\n".join(sections)
        report = self._redact(raw_report)

        with open(self.report_path, "w", encoding="utf-8") as f:
            f.write(report)

        return self.report_path
