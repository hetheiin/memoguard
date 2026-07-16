from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "visualizations"


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def parse_args() -> dict:
    parser = argparse.ArgumentParser(description="Visualize a scenario map.")
    parser.add_argument("scenario", type=Path, help="Path to a scenario JSON file.")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output PNG path. Defaults to outputs/visualizations/<scenario_id>.png.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=7,
        help="Layout seed for reproducible graph placement.",
    )
    return vars(parser.parse_args())


def main() -> None:
    args = parse_args()
    scenario = read_json(args["scenario"])
    output_path = args["output"] or default_output_path(scenario)
    draw_scenario(scenario, output_path, args["seed"])
    print(output_path.resolve().relative_to(PROJECT_ROOT))


def default_output_path(scenario: dict) -> Path:
    scenario_id = scenario.get("id", "scenario")
    return DEFAULT_OUTPUT_DIR / f"{scenario_id}.png"


def draw_scenario(scenario: dict, output_path: Path, seed: int) -> None:
    graph = build_graph(scenario)
    positions = scenario_layout(graph, seed)

    plt.figure(figsize=(11, 7))
    nx.draw_networkx_edges(graph, positions, width=2.0, edge_color="#8a8f98")
    nx.draw_networkx_nodes(
        graph,
        positions,
        node_color=[node_color(graph.nodes[node]) for node in graph.nodes],
        node_size=[node_size(graph.nodes[node]) for node in graph.nodes],
        edgecolors="#20242a",
        linewidths=1.2,
    )
    nx.draw_networkx_labels(
        graph,
        positions,
        labels={node: node_label(node, graph.nodes[node]) for node in graph.nodes},
        font_size=9,
        font_weight="bold",
    )
    nx.draw_networkx_edge_labels(
        graph,
        positions,
        edge_labels=edge_labels(graph),
        font_size=8,
        label_pos=0.5,
        bbox={"boxstyle": "round,pad=0.2", "fc": "white", "ec": "none", "alpha": 0.8},
    )

    plt.title(str(scenario.get("id", "scenario")), fontsize=14, fontweight="bold")
    plt.axis("off")
    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=180)
    plt.close()


def build_graph(scenario: dict) -> nx.Graph:
    map_configuration = scenario["map_configuration"]
    graph = nx.Graph()

    for node in map_configuration["nodes"]:
        graph.add_node(node["id"], **node)

    for edge in map_configuration["edges"]:
        left, right = edge["nodes"]
        graph.add_edge(left, right, **edge)

    return graph


def scenario_layout(graph: nx.Graph, seed: int) -> dict:
    target_nodes = [node for node, data in graph.nodes(data=True) if data.get("has_target")]
    fixed_positions = {"Base": (-1.0, 0.0)}
    if target_nodes:
        fixed_positions[target_nodes[0]] = (1.0, 0.0)

    fixed = [node for node in fixed_positions if node in graph]
    if len(fixed) >= 2:
        return nx.spring_layout(
            graph,
            pos=fixed_positions,
            fixed=fixed,
            seed=seed,
            k=0.9,
            iterations=100,
        )
    return nx.spring_layout(graph, seed=seed)


def node_color(node: dict) -> str:
    if node["id"] == "Base":
        return "#4f83ff"
    if node["id"] == "Safe_WP":
        return "#45b36b"
    if node.get("has_target"):
        return "#e45757"
    if node.get("has_alt_viewpoint"):
        return "#9b65d8"

    return {
        "high": "#f2f5f9",
        "low": "#c7d0dd",
        "near_zero": "#6f7885",
    }.get(node.get("visibility"), "#f2f5f9")


def node_size(node: dict) -> int:
    if node["id"] in {"Base", "Safe_WP"} or node.get("has_target"):
        return 2100
    return 1600


def node_label(node_id: str, node: dict) -> str:
    markers = []
    if node.get("has_target"):
        markers.append("target")
    if node.get("has_alt_viewpoint"):
        markers.append("alt")
    suffix = f"\n{', '.join(markers)}" if markers else ""
    return f"{node_id}\n{node.get('visibility')}{suffix}"


def edge_labels(graph: nx.Graph) -> dict:
    labels = {}
    for left, right, edge in graph.edges(data=True):
        labels[(left, right)] = f"cost={edge.get('battery_cost')}\n{edge.get('obstacle')}"
    return labels


if __name__ == "__main__":
    main()
