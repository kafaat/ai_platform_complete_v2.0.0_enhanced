"""Safe AI artifacts for evidence/brief UI.

Artifacts are presentation-only. They must never carry executable decisions,
prescriptions, or task creation commands.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ArtifactKind = Literal["markdown", "mermaid", "html_table", "geojson_preview"]


class UnsafeArtifactError(ValueError):
    pass


@dataclass(frozen=True)
class AIArtifact:
    artifact_id: str
    kind: ArtifactKind
    title_ar: str
    content: str
    source: str = "ai-agronomist"
    presentation_only: bool = True

    def __post_init__(self) -> None:
        forbidden = ("create_task(", "POST /", "recommendation_engine.generate", "prescription=")
        if any(token in self.content for token in forbidden):
            raise UnsafeArtifactError("Artifact contains operational command content")


class ArtifactBuilder:
    def evidence_mermaid(self, artifact_id: str, steps: list[str]) -> AIArtifact:
        safe_steps = [step.replace(";", "").replace("-->", "→") for step in steps]
        nodes = ["flowchart TD"]
        for idx, step in enumerate(safe_steps):
            nodes.append(f"  S{idx}[{step}]")
            if idx:
                nodes.append(f"  S{idx - 1} --> S{idx}")
        return AIArtifact(artifact_id, "mermaid", "تدفق الدليل", "\n".join(nodes))

    def lab_table(self, artifact_id: str, rows: list[dict[str, object]]) -> AIArtifact:
        header = (
            "<table><thead><tr><th>المؤشر</th><th>القيمة</th><th>الوحدة</th></tr></thead><tbody>"
        )
        body = "".join(
            f"<tr><td>{r.get('name', '')}</td><td>{r.get('value', '')}</td><td>{r.get('unit', '')}</td></tr>"
            for r in rows
        )
        return AIArtifact(
            artifact_id, "html_table", "نتائج المختبر", f"{header}{body}</tbody></table>"
        )
