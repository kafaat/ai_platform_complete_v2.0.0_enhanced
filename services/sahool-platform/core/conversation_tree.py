"""Conversation tree for agronomist review and rollback.

This is intentionally metadata-only: branches compare drafts and assumptions but
cannot publish tasks or prescriptions directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import unified_diff


@dataclass(frozen=True)
class ConversationNode:
    node_id: str
    parent_id: str | None
    title: str
    body: str
    assumptions: dict[str, object] = field(default_factory=dict)


class ConversationTree:
    def __init__(self) -> None:
        self.nodes: dict[str, ConversationNode] = {}

    def add(self, node: ConversationNode) -> None:
        if node.parent_id and node.parent_id not in self.nodes:
            raise KeyError(f"Unknown parent node: {node.parent_id}")
        self.nodes[node.node_id] = node

    def branch(
        self, parent_id: str, node_id: str, title: str, body: str, assumptions: dict[str, object]
    ) -> ConversationNode:
        if parent_id not in self.nodes:
            raise KeyError(f"Unknown parent node: {parent_id}")
        node = ConversationNode(
            node_id=node_id, parent_id=parent_id, title=title, body=body, assumptions=assumptions
        )
        self.add(node)
        return node

    def diff(self, left_id: str, right_id: str) -> str:
        left = self.nodes[left_id]
        right = self.nodes[right_id]
        return "\n".join(
            unified_diff(
                left.body.splitlines(),
                right.body.splitlines(),
                fromfile=left_id,
                tofile=right_id,
                lineterm="",
            )
        )

    def path_to_root(self, node_id: str) -> list[ConversationNode]:
        out: list[ConversationNode] = []
        current = self.nodes[node_id]
        while current:
            out.append(current)
            if current.parent_id is None:
                break
            current = self.nodes[current.parent_id]
        return list(reversed(out))
