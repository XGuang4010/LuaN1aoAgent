"""Tests for TestPolicy module."""
import pytest

from core.test_policy import TestPolicy, VULN_TYPE_KEYWORDS, HARD_DENYLIST


@pytest.fixture
def policy():
    return TestPolicy()


def test_classify_vuln_type_sql_injection(policy):
    assert policy.classify_vuln_type("test SQL injection on login") == "sql_injection"
    assert policy.classify_vuln_type("check for sqli vulnerability") == "sql_injection"
    assert policy.classify_vuln_type("尝试注入攻击") == "sql_injection"


def test_classify_vuln_type_ssrf(policy):
    assert policy.classify_vuln_type("check for SSRF vulnerability") == "ssrf"
    assert policy.classify_vuln_type("测试服务器请求伪造") == "ssrf"


def test_classify_vuln_type_command_execution(policy):
    assert policy.classify_vuln_type("test RCE on target") == "command_execution"
    assert policy.classify_vuln_type("检测命令执行漏洞") == "command_execution"
    assert policy.classify_vuln_type("remote code execution check") == "command_execution"


def test_classify_vuln_type_file_upload(policy):
    assert policy.classify_vuln_type("test file upload") == "file_upload"
    assert policy.classify_vuln_type("检测文件上传漏洞") == "file_upload"


def test_classify_vuln_type_xss(policy):
    assert policy.classify_vuln_type("test XSS vulnerability") == "xss"
    assert policy.classify_vuln_type("跨站脚本攻击检测") == "xss"


def test_classify_vuln_type_idor(policy):
    assert policy.classify_vuln_type("test IDOR on user endpoint") == "idor"
    assert policy.classify_vuln_type("检测越权访问") == "idor"
    assert policy.classify_vuln_type("horizontal privilege escalation") == "idor"


def test_classify_vuln_type_no_match(policy):
    assert policy.classify_vuln_type("enumerate user profiles") is None
    assert policy.classify_vuln_type("scan open ports") is None
    assert policy.classify_vuln_type("") is None


def test_parse_policy_mock_sql_and_ssrf(policy):
    raw = "SQL注入只允许sleep验证。SSRF使用 https://cb.net。"
    result = policy.parse_policy(raw)
    assert "sql_injection" in result
    assert "ssrf" in result
    assert result["sql_injection"]["allowed_verification"] == ["sleep"]
    assert result["ssrf"]["callback_url"] == "https://cb.net"
    assert policy.parse_status == "success"


def test_parse_policy_mock_partial(policy):
    raw = "SQL injection test only"
    result = policy.parse_policy(raw)
    assert "sql_injection" in result
    assert policy.parse_status == "success"


def test_parse_policy_empty(policy):
    raw = "nothing relevant"
    result = policy.parse_policy(raw)
    assert result == {}
    assert policy.parse_status == "partial"


def test_get_constraints_found(policy):
    policy.parse_policy("SQL注入只允许sleep验证")
    constraints = policy.get_constraints("sql_injection")
    assert constraints is not None
    assert constraints["allowed_verification"] == ["sleep"]


def test_get_constraints_not_found(policy):
    policy.parse_policy("SQL注入只允许sleep验证")
    assert policy.get_constraints("ssrf") is None


def test_get_constraints_without_parse(policy):
    fresh_policy = TestPolicy()
    assert fresh_policy.get_constraints("sql_injection") is None


def test_check_hard_denylist_blocked():
    policy = TestPolicy()
    assert policy.check_hard_denylist("rm -rf /") is False
    assert policy.check_hard_denylist("reboot now") is False
    assert policy.check_hard_denylist("mkfs.ext4 /dev/sda") is False
    assert policy.check_hard_denylist("dd if=/dev/zero of=/dev/sda") is False
    assert policy.check_hard_denylist("iptables -F INPUT") is False
    assert policy.check_hard_denylist("poweroff") is False


def test_check_hard_denylist_allowed():
    policy = TestPolicy()
    assert policy.check_hard_denylist("ls -la") is True
    assert policy.check_hard_denylist("cat /etc/passwd") is True
    assert policy.check_hard_denylist("nmap -sS target") is True
    assert policy.check_hard_denylist("") is True


def test_hard_denylist_constant():
    assert "rm -rf /" in HARD_DENYLIST
    assert "reboot" in HARD_DENYLIST
    assert "poweroff" in HARD_DENYLIST
    assert "mkfs" in HARD_DENYLIST
    assert "dd if=/dev/zero" in HARD_DENYLIST
    assert "iptables -F" in HARD_DENYLIST


def test_vuln_type_keywords_structure():
    assert "sql_injection" in VULN_TYPE_KEYWORDS
    assert "ssrf" in VULN_TYPE_KEYWORDS
    assert "command_execution" in VULN_TYPE_KEYWORDS
    assert "file_upload" in VULN_TYPE_KEYWORDS
    assert "xss" in VULN_TYPE_KEYWORDS
    assert "idor" in VULN_TYPE_KEYWORDS
    # Each entry should be a non-empty list
    for keywords in VULN_TYPE_KEYWORDS.values():
        assert isinstance(keywords, list)
        assert len(keywords) > 0
