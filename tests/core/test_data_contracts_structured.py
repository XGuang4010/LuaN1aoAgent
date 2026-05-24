"""Tests for P1 structured observation data contracts."""
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from core.data_contracts import ToolFinding, ToolError, StructuredObservation


def test_tool_finding_to_dict():
    f = ToolFinding(category="open_port", key="80/tcp", value="Apache httpd", confidence=0.9)
    d = f.to_dict()
    assert d["category"] == "open_port"
    assert d["key"] == "80/tcp"
    assert d["confidence"] == 0.9


def test_tool_error_from_json_response_syntax():
    data = {"success": False, "error_type": "SYNTAX", "message": "Bad arg", "fix_suggestion": "Fix args"}
    err = ToolError.from_json_response(data)
    assert err is not None
    assert err.error_type == "SYNTAX"
    assert err.is_correctable is True


def test_tool_error_from_json_response_success():
    data = {"success": True, "result": "ok"}
    err = ToolError.from_json_response(data)
    assert err is None


def test_tool_error_from_json_response_unknown():
    data = {"success": False, "error_type": "RUNTIME", "message": "Crash", "fix_suggestion": ""}
    err = ToolError.from_json_response(data)
    assert err is not None
    assert err.error_type == "RUNTIME"
    assert err.is_correctable is False


def test_structured_observation_to_dict():
    obs = StructuredObservation(
        step_id="step_1",
        tool="nmap",
        status="success",
        summary="Found 3 open ports",
        raw_output="PORT STATE SERVICE\n80/tcp open http\n",
        findings=[
            ToolFinding(category="open_port", key="80/tcp", value="http", confidence=0.9),
        ],
        errors=[],
        evidence_ids=[],
        truncated=False,
    )
    d = obs.to_dict()
    assert d["step_id"] == "step_1"
    assert d["status"] == "success"
    assert len(d["findings"]) == 1
    assert d["findings"][0]["category"] == "open_port"


def test_structured_observation_format_for_llm():
    obs = StructuredObservation(
        step_id="step_1",
        tool="nmap",
        status="success",
        summary="Found 3 open ports",
        raw_output="...",
        findings=[
            ToolFinding(category="open_port", key="80/tcp", value="http", confidence=0.9),
            ToolFinding(category="service", key="80/tcp", value="Apache", confidence=0.8),
        ],
        errors=[
            ToolError(error_type="NETWORK", message="timeout", fix_suggestion="retry", is_correctable=True),
        ],
        evidence_ids=[],
        truncated=True,
        truncation_info="raw_output truncated from 60000 chars",
    )
    result = obs.format_for_llm()
    assert "Found 3 open ports" in result
    assert "NETWORK" in result
    assert "截断" in result or "truncat" in result.lower()


def test_structured_observation_backward_compat():
    """Simulate reading old string data from DB fallback."""
    raw = "PORT STATE SERVICE\n80/tcp open http"
    obs = StructuredObservation(
        step_id="old_step",
        tool="unknown",
        status="partial",
        summary="Legacy observation (raw text)",
        raw_output=raw,
        findings=[],
        errors=[],
        evidence_ids=[],
    )
    assert obs.status == "partial"
    assert obs.raw_output == raw


def test_tool_error_from_json_response_timeout():
    data = {"success": False, "error_type": "TIMEOUT", "message": "Timed out after 30s", "fix_suggestion": "Increase timeout"}
    err = ToolError.from_json_response(data)
    assert err is not None
    assert err.error_type == "TIMEOUT"
    assert err.is_correctable is True


def test_tool_finding_with_evidence_ref():
    f = ToolFinding(category="vuln", key="CVE-2024-1234", value="SQL Injection", confidence=0.7, evidence_ref="line 42")
    d = f.to_dict()
    assert d["evidence_ref"] == "line 42"
