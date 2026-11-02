"""قارئُ سجلّ مصادر الحقيقة — البيانات في `docs/architecture/`، لا هنا.

**ولماذا البيانات خارج الكود:** السجلّ **قرارٌ محكَّم** لا اشتقاق، فموضعه
`docs/architecture/knowledge_source_registry.json` حيث يفرض `claim_base_guard`
أن يحمل كلُّ مصنوعةٍ إمّا ختمَ قياس أو تاريخَ حكم، و`manifest_registry_guard`
أن تكون محكومةً (schema+version+adjudicated_on). ولو كان قاموساً في `.py`
لأفلت من الاثنين — قرارُ ثقةٍ يتسلّل في مراجعة كود.

فحص صرف — ``pytest -m unit``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# G3: المسار نسبيٌّ إلى **الجذر الذي يحمل `shared/`** — جذرُ المستودع محلّيّاً و`/app`
# في الصورة (`COPY shared/ /app/shared/`). فالصورة يجب أن تنسخ الملفّ إلى
# `/app/docs/architecture/` (انظر `services/sahool-platform/Dockerfile` و`.dockerignore`)،
# ويقيس ذلك `tests_v9/test_image_data_file_contract.py` من هذه الدالّة نفسها.
# The path is relative to the root holding `shared/` (repo root, or /app in the image).
REGISTRY_RELATIVE_PATH = Path("docs") / "architecture" / "knowledge_source_registry.json"
REGISTRY_ENV = "SAHOOL_KNOWLEDGE_SOURCE_REGISTRY"
REGISTRY_SCHEMA = "sahool.knowledge_source_registry"


def default_registry_path(module_file: str | os.PathLike[str] | None = None) -> Path:
    """موضعُ السجلّ لوحدةٍ تسكن ``module_file`` (افتراضيّاً هذا الملفّ)."""
    anchor = Path(module_file) if module_file is not None else Path(__file__).resolve()
    return anchor.parents[2] / REGISTRY_RELATIVE_PATH


REGISTRY_PATH = default_registry_path()


def registry_path() -> Path:
    """المسار الفعّال: ``SAHOOL_KNOWLEDGE_SOURCE_REGISTRY`` إن ضُبط، وإلّا الافتراضيّ.

    تجاوزٌ مضبوطٌ إلى ملفٍّ غائب **يرفع** في `load_registry` — لا ارتداد صامت.
    """
    override = os.getenv(REGISTRY_ENV, "").strip()
    return Path(override) if override else REGISTRY_PATH


class RegistryError(RuntimeError):
    """سجلٌّ غائبٌ أو مشوَّه — يُرفَع ولا يُقرأ «صفر مفتاح»."""


@dataclass(frozen=True)
class KnowledgeSource:
    key: str
    source_of_truth: str
    producer_module: str
    producer_field: str
    forbidden_raw_inputs: tuple[str, ...]
    forbidden_reason_ar: str
    consumers: tuple[str, ...]


def _require_str(entry: dict, name: str, where: str) -> str:
    value = entry.get(name)
    if not isinstance(value, str) or not value:
        raise RegistryError(f"{where}: الحقل «{name}» مفقود أو ليس نصّاً")
    return value


def _require_str_list(entry: dict, name: str, where: str) -> tuple[str, ...]:
    value = entry.get(name)
    if not isinstance(value, list) or not value:
        raise RegistryError(f"{where}: الحقل «{name}» مفقود أو ليس قائمةً غير فارغة")
    if any(not isinstance(x, str) or not x for x in value):
        raise RegistryError(f"{where}: الحقل «{name}» يحمل عنصراً ليس نصّاً غير فارغ")
    if len(set(value)) != len(value):
        raise RegistryError(f"{where}: الحقل «{name}» يحمل تكراراً")
    return tuple(value)


def load_registry(path: Path | None = None) -> dict[str, KnowledgeSource]:
    """يقرأ السجلّ ويتحقّق من بنيته. **يرفع** بدل أن يُرجِع فارغاً.

    قاموسٌ فارغ يجعل كلّ فحصٍ فوقه يمرّ — «أخضرُ لأنّه لم ينظر»، وهو الصنف
    الذي يطارده هذا المستودع كلّه.
    """
    target = path or registry_path()
    if not target.is_file():
        raise RegistryError(
            f"سجلّ مصادر الحقيقة غير موجود: {target} — knowledge source registry missing; "
            f"the image must COPY {REGISTRY_RELATIVE_PATH.as_posix()} next to shared/ "
            f"(or set {REGISTRY_ENV})"
        )
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RegistryError(f"سجلٌّ غير قابل للتحليل: {target} — {exc}") from exc
    if not isinstance(raw, dict):
        raise RegistryError(f"سجلٌّ ليس كائناً: {target}")
    if raw.get("schema") != REGISTRY_SCHEMA:
        raise RegistryError(f"مخطَّطٌ غير متوقَّع في {target}: {raw.get('schema')!r}")
    entries = raw.get("keys")
    if not isinstance(entries, list) or not entries:
        raise RegistryError(f"سجلٌّ بلا مفاتيح: {target}")

    sources: dict[str, KnowledgeSource] = {}
    for index, entry in enumerate(entries):
        where = f"{target.name}[{index}]"
        if not isinstance(entry, dict):
            raise RegistryError(f"{where}: المدخل ليس كائناً")
        key = _require_str(entry, "key", where)
        if key in sources:
            # مفتاحٌ مكرَّر يعني مصدرَي حقيقةٍ لشيءٍ واحد — وهو نقيض غرض السجلّ.
            raise RegistryError(f"{where}: المفتاح «{key}» مكرَّر")
        sources[key] = KnowledgeSource(
            key=key,
            source_of_truth=_require_str(entry, "source_of_truth", where),
            producer_module=_require_str(entry, "producer_module", where),
            producer_field=_require_str(entry, "producer_field", where),
            forbidden_raw_inputs=_require_str_list(entry, "forbidden_raw_inputs", where),
            forbidden_reason_ar=_require_str(entry, "forbidden_reason_ar", where),
            consumers=_require_str_list(entry, "consumers", where),
        )
    return sources


@lru_cache(maxsize=1)
def registry() -> dict[str, KnowledgeSource]:
    return load_registry()


def readiness_check() -> dict[str, object]:
    """فحصُ جاهزيّةٍ للصورة المستهلكة: السجلّ يُقرأ مرّةً عند ``/readyz``.

    G3: غيابُه كان يحجب كلّ توصيةٍ بصمتٍ لكلّ طلب؛ هنا يصير «غير جاهز» بسببٍ يسمّي الملفّ.
    """
    try:
        return {"ok": True, "count": len(registry())}
    except RegistryError as exc:
        return {"ok": False, "error": str(exc)}


def source_of_truth_for(key: str) -> str:
    sources = registry()
    if key not in sources:
        raise RegistryError(f"المفتاح «{key}» غير مُسجَّل — لا مصدر حقيقةٍ له")
    return sources[key].source_of_truth
