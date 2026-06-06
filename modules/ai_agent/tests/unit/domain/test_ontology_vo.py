from ai_agent.domain.value_objects import OntologyNode, OntologySubgraph, PatternTemplate


def test_allowed_node_types_collects_all_nodes():
    sg = OntologySubgraph(
        seeds=("slack_send",),
        nodes=(
            OntologyNode(node_type="slack_send", category="messaging", risk_level="medium",
                         requires=("slack",)),
            OntologyNode(node_type="discord_send", category="messaging", risk_level=""),
        ),
        adjacency={"slack_send": ("discord_send",)},
    )
    assert sg.allowed_node_types() == frozenset({"slack_send", "discord_send"})


def test_empty_subgraph_allows_nothing():
    sg = OntologySubgraph(seeds=(), nodes=(), adjacency={})
    assert sg.allowed_node_types() == frozenset()


def test_vos_are_frozen():
    node = OntologyNode(node_type="x", category="c", risk_level="low")
    try:
        node.node_type = "y"  # type: ignore[misc]
    except AttributeError:
        pass
    else:
        raise AssertionError("OntologyNode는 frozen이어야 한다")


def test_pattern_template_defaults():
    p = PatternTemplate(name="quality_gate_loop", intent="검증/재생성")
    assert p.role_slots == {}
