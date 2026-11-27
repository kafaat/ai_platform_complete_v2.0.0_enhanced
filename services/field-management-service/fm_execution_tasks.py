"""Compatibility exports of the pure inspection contract used by the FM owner.

Coordination and outbound Decision HTTP live in sahool-platform. This module
contains no network client, service URL or persistence implementation.
"""

from shared.field_inspection_execution import (
    OPERATION as OPERATION,
)
from shared.field_inspection_execution import (
    PROVIDER as PROVIDER,
)
from shared.field_inspection_execution import (
    SCHEMA as SCHEMA,
)
from shared.field_inspection_execution import (
    TASK_NAMESPACE as TASK_NAMESPACE,
)
from shared.field_inspection_execution import (
    ExecutionBinding as ExecutionBinding,
)
from shared.field_inspection_execution import (
    ExecutionSettings as ExecutionSettings,
)
from shared.field_inspection_execution import (
    InspectionSpec as InspectionSpec,
)
from shared.field_inspection_execution import (
    binding_from_source as binding_from_source,
)
from shared.field_inspection_execution import (
    canonical as canonical,
)
from shared.field_inspection_execution import (
    digest as digest,
)
from shared.field_inspection_execution import (
    identifier as identifier,
)
from shared.field_inspection_execution import (
    iso as iso,
)
from shared.field_inspection_execution import (
    outcome_payload as outcome_payload,
)
from shared.field_inspection_execution import (
    refuse as refuse,
)
