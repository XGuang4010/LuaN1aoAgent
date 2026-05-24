"""Integration tests for TestPolicy injection into Planner and Executor."""
import pytest
import pytest_asyncio

from core.graph_manager import GraphManager
from core.test_policy import TestPolicy
from core.executor import _build_executor_prompt
from core.prompts import PromptManager


@pytest_asyncio.fixture
async def graph_manager():
    gm = GraphManager(task_id="test_task", goal="test goal", op_id="test_op", _skip_db_init=True)
    return gm


def test_add_subtask_node_accepts_extra_data(graph_manager):
    gm = graph_manager
    extra = {"policy_context": {"allowed": ["sleep"]}}
    gm.add_subtask_node(
        "subtask_1",
        description="test SQL injection",
        dependencies=[],
        extra_data=extra,
    )
    assert gm.graph.has_node("subtask_1")
    assert gm.graph.nodes["subtask_1"].get("extra_data") == extra


def test_add_subtask_node_without_extra_data(graph_manager):
    gm = graph_manager
    gm.add_subtask_node(
        "subtask_2",
        description="enumerate ports",
        dependencies=[],
    )
    assert gm.graph.has_node("subtask_2")
    assert gm.graph.nodes["subtask_2"].get("extra_data") is None


# We need to import process_graph_commands after modifying agent.py
# For now, test the classify + inject flow directly.


def test_classify_and_inject_sql_injection(graph_manager):
    gm = graph_manager
    policy = TestPolicy()
    policy.parse_policy("SQL注入只允许sleep验证")

    description = "test SQL injection on login form"
    vuln_type = policy.classify_vuln_type(description)
    assert vuln_type == "sql_injection"

    constraints = policy.get_constraints(vuln_type)
    assert constraints is not None

    gm.add_subtask_node(
        "subtask_sqli",
        description=description,
        dependencies=[],
        extra_data={"policy_context": constraints},
    )
    node_data = gm.graph.nodes["subtask_sqli"]
    assert node_data["extra_data"]["policy_context"]["allowed_verification"] == ["sleep"]


@pytest.mark.asyncio
async def test_executor_prompt_includes_policy_context(graph_manager):
    gm = graph_manager
    policy = TestPolicy()
    policy.parse_policy("SQL注入只允许sleep验证")

    gm.add_subtask_node(
        "subtask_sqli",
        description="test SQL injection",
        dependencies=[],
        extra_data={"policy_context": policy.get_constraints("sql_injection")},
    )

    messages = []
    system_prompt, messages = await _build_executor_prompt(
        gm, "subtask_sqli", "main goal", "briefing", messages
    )

    assert "【测试约束】" in system_prompt
    assert "sleep" in system_prompt


@pytest.mark.asyncio
async def test_executor_prompt_no_policy_context(graph_manager):
    gm = graph_manager
    gm.add_subtask_node(
        "subtask_recon",
        description="enumerate subdomains",
        dependencies=[],
    )

    messages = []
    system_prompt, messages = await _build_executor_prompt(
        gm, "subtask_recon", "main goal", "briefing", messages
    )

    assert "【测试约束】" not in system_prompt
