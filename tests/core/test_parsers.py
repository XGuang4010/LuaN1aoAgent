import pytest
from core.parsers import PARSER_REGISTRY, parse_tool_output, fallback_parser
from core.data_contracts import ToolFinding


def test_parser_registry_has_all_parsers():
    expected = {"nmap", "dirsearch", "httpx", "http", "subfinder", "nuclei", "sqlmap"}
    assert expected.issubset(PARSER_REGISTRY.keys()), f"Missing parsers: {expected - set(PARSER_REGISTRY.keys())}"


def test_fallback_parser():
    result = parse_tool_output("unknown_tool", "some raw output")
    assert len(result) == 1
    assert result[0].category == "raw_output"
    assert result[0].key == "full"
    assert result[0].confidence == 1.0


def test_fallback_parser_tool_truncation():
    long_output = "x" * 3000
    result = fallback_parser(long_output)
    assert len(result[0].value) == 2000


def test_nmap_open_port_parsing():
    nmap_output = """
Nmap scan report for example.com (93.184.216.34)
Host is up (0.0010s latency).

PORT    STATE    SERVICE    VERSION
80/tcp  open     http       Apache httpd 2.4.41
443/tcp open     https
"""
    findings = parse_tool_output("nmap", nmap_output)
    open_ports = [f for f in findings if f.category == "open_port"]
    services = [f for f in findings if f.category == "service"]

    assert len(open_ports) == 2
    assert open_ports[0].key == "80/tcp"
    assert open_ports[0].value["port"] == 80
    assert open_ports[0].value["service"] == "http"
    assert open_ports[1].key == "443/tcp"

    assert len(services) == 2


def test_dirsearch_url_parsing():
    dirsearch_output = """
[11:22:33] 200 -   123B - /admin
[11:22:34] 301 -   456B - /backup
"""
    findings = parse_tool_output("dirsearch", dirsearch_output)
    assert len(findings) == 2
    assert findings[0].category == "url"
    assert findings[0].value["path"] == "/admin"
    assert findings[0].value["status_code"] == 200
    assert findings[1].value["path"] == "/backup"
    assert findings[1].value["status_code"] == 301


def test_subfinder_subdomain_parsing():
    subfinder_output = """
api.example.com
admin.example.com
mail.example.com
"""
    findings = parse_tool_output("subfinder", subfinder_output)
    assert len(findings) == 3
    assert findings[0].category == "subdomain"
    assert findings[0].key == "api.example.com"
    assert findings[0].value == "api.example.com"


def test_http_header_parsing():
    http_output = """HTTP/1.1 200 OK
Server: nginx/1.18.0
X-Powered-By: Express
Content-Type: text/html

<html>...</html>"""
    findings = parse_tool_output("http", http_output)
    assert len(findings) == 4  # status_code + 3 headers

    status = next(f for f in findings if f.key == "status_code")
    assert status.value == 200

    server = next(f for f in findings if f.key == "server")
    assert server.value == "nginx/1.18.0"

    xpb = next(f for f in findings if f.key == "x-powered-by")
    assert xpb.value == "Express"


def test_httpx_json_parsing():
    httpx_output = """{"url":"http://example.com","status_code":200,"tech":["React","Nginx"]}
{"url":"http://example.org","status_code":301,"tech":[]}"""
    findings = parse_tool_output("httpx", httpx_output)
    services = [f for f in findings if f.category == "service"]
    tech_stacks = [f for f in findings if f.category == "tech_stack"]

    assert len(services) == 2
    assert len(tech_stacks) == 1
    assert services[0].value["status_code"] == 200
    assert tech_stacks[0].value["technologies"] == ["React", "Nginx"]


def test_nuclei_json_parsing():
    nuclei_output = """{"template-id":"cve-2024-1234","severity":"critical","matched-at":"http://target.com/admin"}
{"template-id":"tech-detect","severity":"info","matched-at":"http://target.com/"}"""
    findings = parse_tool_output("nuclei", nuclei_output)
    assert len(findings) == 2
    assert findings[0].category == "vuln"
    assert findings[0].value["severity"] == "critical"
    assert findings[0].value["template_id"] == "cve-2024-1234"
    assert findings[1].value["severity"] == "info"


def test_sqlmap_parameter_parsing():
    sqlmap_output = """
[11:22:33] [INFO] testing connection to the target URL
Parameter: id (GET)
    Type: boolean-based blind
    Title: AND boolean-based blind
Parameter: username (POST)
    Type: time-based blind
"""
    findings = parse_tool_output("sqlmap", sqlmap_output)
    assert len(findings) == 2
    assert findings[0].key == "sqli_id"
    assert findings[0].value["parameter"] == "id"
    assert findings[0].value["method"] == "GET"
    assert findings[1].key == "sqli_username"
    assert findings[1].value["parameter"] == "username"
    assert findings[1].value["method"] == "POST"


def test_nmap_empty_output():
    findings = parse_tool_output("nmap", "")
    assert len(findings) == 0


def test_dirsearch_no_matches():
    findings = parse_tool_output("dirsearch", "[11:22:33] Starting scan")
    assert len(findings) == 0


def test_httpx_empty_json():
    findings = parse_tool_output("httpx", "")
    assert len(findings) == 0
