"""طبقة المعرفة التشغيليّة — `KNOWLEDGE-CANONICAL-CONSUMPTION-01`."""

from .context_resolver import ContextResolver
from .contracts import (
    ContextResolutionError,
    KnowledgeRequirement,
    KnowledgeValue,
    ResolvedContext,
    TaskContextContract,
)
from .source_registry import KnowledgeSource, RegistryError, registry, source_of_truth_for

__all__ = [
    "ContextResolutionError",
    "ContextResolver",
    "KnowledgeRequirement",
    "KnowledgeSource",
    "KnowledgeValue",
    "RegistryError",
    "ResolvedContext",
    "TaskContextContract",
    "registry",
    "source_of_truth_for",
]
