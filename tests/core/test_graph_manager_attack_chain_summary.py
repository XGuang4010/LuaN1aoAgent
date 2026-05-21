from core.graph_manager import GraphManager


def _build_minimal_chain(graph: GraphManager):
    evidence_id = graph.add_causal_node(
        {
            "id": "ev_http_200",
            "node_type": "Evidence",
            "description": "login page leaks stack trace",
            "source_step_id": "step_1",
        }
    )
    hypothesis_id = graph.add_causal_node(
        {
            "id": "hyp_sqli",
            "node_type": "Hypothesis",
            "description": "username may be SQL injectable",
            "confidence": 0.9,
            "status": "SUPPORTED",
            "source_step_id": "step_2",
        }
    )
    vuln_id = graph.add_causal_node(
        {
            "id": "vuln_sqli",
            "node_type": "ConfirmedVulnerability",
            "description": "boolean based SQL injection",
            "cvss_score": 9.0,
            "source_step_id": "step_3",
        }
    )
    goal_id = graph.add_causal_node(
        {
            "id": "goal_admin",
            "node_type": "AttackGoal",
            "description": "obtain admin access",
            "goal_type": "privilege_escalation",
            "target_privilege_level": "admin",
        }
    )
    graph.add_causal_edge(evidence_id, hypothesis_id, "SUPPORTS")
    graph.add_causal_edge(hypothesis_id, vuln_id, "SUPPORTS")
    graph.add_causal_edge(vuln_id, goal_id, "ENABLES")
    return vuln_id


def test_summarize_high_value_chains_marks_missing_prerequisite_as_partial():
    graph = GraphManager("task-1", "reach admin goal")
    vuln_id = _build_minimal_chain(graph)
    prereq_id = graph.add_causal_node(
        {
            "id": "fact_authenticated",
            "node_type": "KeyFact",
            "description": "authenticated session available",
            "status": "pending",
        }
    )
    graph.add_causal_edge(vuln_id, prereq_id, "REQUIRES")

    summary = graph.summarize_high_value_chains(top_k=3)

    assert summary["chains"][0]["chain_type"] == "blocked_by_prerequisite"
    assert summary["chains"][0]["prerequisite_status"]["missing"] == [
        "fact_authenticated"
    ]
    assert summary["chains"][0]["execution_readiness"] == "partial"
    assert "前提" in summary["chains"][0]["next_best_action"]


def test_analyze_attack_paths_updates_joint_score_after_convergence():
    graph = GraphManager("task-2", "reach admin goal")
    _build_minimal_chain(graph)

    paths = graph.analyze_attack_paths(use_cache=False)

    goal_node = graph.causal_graph.nodes["goal_admin"]
    assert paths
    assert goal_node["joint_threat_score"] > 0.0
