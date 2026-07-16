from __future__ import annotations

import heapq
import math
from typing import Any, Mapping


def shortest_path(
    graph: Mapping[str, list[dict[str, Any]]],
    current_node: str,
    goal_node: str,
) -> dict[str, Any]:
    queue = [(0.0, 0, current_node, [current_node])]
    best = {current_node: (0.0, 0)}

    while queue:
        cost, steps, node, path = heapq.heappop(queue)
        if (cost, steps) != best[node]:
            continue
        if node == goal_node:
            return {
                "path": path,
                "expected_cost": cost,
                "steps": steps,
                "reachable": True,
            }

        for edge in graph[node]:
            next_node = edge["node"]
            next_cost = cost + edge["expected_cost"]
            next_steps = steps + 1
            next_score = (next_cost, next_steps)
            if next_score >= best.get(next_node, (math.inf, math.inf)):
                continue

            best[next_node] = next_score
            heapq.heappush(queue, (next_cost, next_steps, next_node, path + [next_node]))

    return {
        "path": [],
        "expected_cost": math.inf,
        "steps": math.inf,
        "reachable": False,
    }
