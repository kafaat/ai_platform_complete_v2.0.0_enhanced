"""واجهة عامّة لحزمة أبحاث SAHOOL الزراعيّة.

SAHOOL Agronomic Research Pipeline — public API re-exports.
"""

from __future__ import annotations

from sahool_ai.research.decomposer import decompose_query
from sahool_ai.research.extractor import (
    extract_causal_links,
    extract_numeric_values,
    extract_temporal_patterns,
)
from sahool_ai.research.models import (
    CausalLink,
    Factor,
    SubQuery,
    Synthesis,
)
from sahool_ai.research.pipeline import run_pipeline
from sahool_ai.research.reporter import (
    generate_json_report,
    generate_map_data,
    generate_markdown_report,
)
from sahool_ai.research.retriever import CONNECTORS, retrieve_all
from sahool_ai.research.synthesizer import synthesize_findings

__all__ = [
    # Models
    "SubQuery",
    "CausalLink",
    "Factor",
    "Synthesis",
    # Decomposer
    "decompose_query",
    # Retriever
    "retrieve_all",
    "CONNECTORS",
    # Extractor
    "extract_numeric_values",
    "extract_temporal_patterns",
    "extract_causal_links",
    # Synthesizer
    "synthesize_findings",
    # Reporter
    "generate_json_report",
    "generate_markdown_report",
    "generate_map_data",
    # Pipeline
    "run_pipeline",
]
