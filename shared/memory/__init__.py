"""shared/memory — SAHOOL Farm Memory public API.

Re-exports all public symbols so callers can do:
    from shared.memory import FarmMemory, ConversationTurn, ...
"""

from __future__ import annotations

from .export_engine import (
    OptionalDependencyError,
    export_to_encrypted_tarball,
    export_to_json,
    export_to_parquet,
    export_to_qdrant_snapshot,
    generate_checksum,
)
from .farm_memory import FarmMemory
from .import_engine import (
    detect_format,
    import_from_encrypted_tarball,
    import_from_json,
    import_from_qdrant_snapshot,
    migrate_schema,
    resolve_conflicts,
    validate_checksum,
)
from .models import (
    SCHEMA_VERSION,
    ConversationTurn,
    MemoryItem,
    Recommendation,
    UsagePattern,
)
from .skills import list_skills, load_skill

__all__ = [
    # models
    "SCHEMA_VERSION",
    "ConversationTurn",
    "UsagePattern",
    "Recommendation",
    "MemoryItem",
    # core
    "FarmMemory",
    # export
    "OptionalDependencyError",
    "export_to_json",
    "export_to_parquet",
    "export_to_qdrant_snapshot",
    "export_to_encrypted_tarball",
    "generate_checksum",
    # import
    "validate_checksum",
    "detect_format",
    "import_from_json",
    "import_from_encrypted_tarball",
    "import_from_qdrant_snapshot",
    "resolve_conflicts",
    "migrate_schema",
    # skills
    "load_skill",
    "list_skills",
]
