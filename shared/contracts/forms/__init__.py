"""عقود النماذج الميدانيّة الديناميكية (GAP-FIELD-FORMS-01).

وحدات نقيّة (لا FastAPI/قاعدة/شبكة):
- condition_v1: DSL الظهور الشرطيّ SahoolFormConditionV1 (§10)
- schema_v1: عقد الـschema + تحقّق الإجابات خادميًّا (§8/§12)
- sync_token: توكن مزامنة HMAC ذاتيّ التحقّق بلا جدول خامس (§9)
"""

from shared.contracts.forms.condition_v1 import (
    ConditionError,
    ConditionTypeError,
    evaluate,
    validate_condition,
)
from shared.contracts.forms.schema_v1 import (
    NORMALIZER_VERSION,
    SchemaError,
    canonical_answers_hash,
    validate_answers,
    validate_form_schema,
    visible_fields,
)
from shared.contracts.forms.sync_token import (
    SyncTokenError,
    issue_token,
    verify_token,
)

__all__ = [
    "ConditionError",
    "ConditionTypeError",
    "NORMALIZER_VERSION",
    "SchemaError",
    "SyncTokenError",
    "canonical_answers_hash",
    "evaluate",
    "issue_token",
    "validate_answers",
    "validate_condition",
    "validate_form_schema",
    "verify_token",
    "visible_fields",
]
