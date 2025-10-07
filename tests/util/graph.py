import _canary.util.graph as graph


def test_find_reachable_nodes():
    G = {"A": ["B", "C"], "B": ["D"], "C": ["D", "E"], "D": [], "E": ["F"], "F": []}
    nodes = graph.find_reachable_nodes(G, "A")
    assert sorted(nodes) == ["A", "B", "C", "D", "E", "F"]
