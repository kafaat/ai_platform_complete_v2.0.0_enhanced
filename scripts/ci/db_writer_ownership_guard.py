#!/usr/bin/env python3
"""`OWNERSHIP-CONTRACT-DECLARED-BUT-NEVER-MEASURED-01`: عقدٌ يُعلَن ولا يُقاس.

`docs/architecture/db_ownership.yml` يعلن لكلّ جدولٍ مالكاً وكُتّاباً وقُرّاءً —
**ولا شيء في الشجرة كان يقارن ما يُعلَن بما يقع**. فبقي العقدُ وثيقةَ نيّة، وانحرف
الكودُ عنه بصمت.

**العطلُ الذي وُجِد لأجله، مقيساً:** `db_ownership.yml:24` يعلن
``actuator_command_outbox`` مملوكاً لـ``actuator-service`` وكاتبُه هو وحده،
و``sahool-platform`` **قارئاً**. والمقيس أنّ ``sahool-platform`` يكتبه
(``phase_runtime_store.py``) وأنّ **لا قارئ له في كامل الشجرة**. والمثلُ في
``iot_command_dispatch`` — يكتبه ويقرؤه ويطالِبه ``sahool-platform`` وحده، بينما
العقدُ يعلنه قارئاً فقط. عطلان لم يكشفهما شيءٌ آليّ لأنّ **الفحص لم يكن موجوداً**.

**والقياسُ لا يُدين ما أذِن به العقدُ صراحةً:** الكتابةُ مشروعةٌ إن كانت الخدمةُ في
``writers``، **أو** كانت ``mirror`` الجدولِ — وهو جسرٌ انتقاليٌّ موثَّق
(``status: interim-bridge``) لا انحراف. فحارسٌ يخلط الاستثناءَ الموثَّقَ بالانحراف
يُنذِر كذباً، ويُدرَّب الناسُ على تجاهله، فيموت وهو أخضر.

**والكشفُ من شجرة البناء لا من النصّ** (درس
درسٌ مقيسٌ في #951): بحثٌ نصّيٌّ في
كامل الملفّ يتّهم التعليقَ الذي يشرح *لماذا* هُجِر مسارٌ، فيصير توثيقُ الإصلاح
مُبطِلاً له. هنا تُفحَص **سلاسلُ SQL الحرفيّة وحدَها**.

**وأساسٌ ينزل ولا يصعد** (درس ``AN-EXEMPTION-LIST-WITH-NO-DESCENDING-CEILING-01``):
الراتشِت يفشل في الاتّجاهين — مخالفةٌ جديدة **ومدخلٌ بائتٌ لم يعد منحرفاً**. إعفاءٌ
بلا سقفٍ نازل ليس ديناً مؤجَّلاً بل شطبٌ صامت.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs" / "architecture" / "db_ownership.yml"
BASELINE = ROOT / "docs" / "architecture" / "db_writer_ownership_baseline.json"

# `INSERT INTO` · `UPDATE` · `DELETE FROM` — و`ONLY` اختياريّة (PostgreSQL).
_WRITE = re.compile(
    r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+(?:ONLY\s+)?([a-z_][a-z0-9_]*)",
    re.IGNORECASE,
)
# أقصرُ من هذا لا يحمل عبارةَ SQL كاملة — يقلّل الضجيج بلا إسقاطِ حالةٍ حقيقيّة.
_MIN_SQL_LEN = 12

_SKIP_PARTS = ("/.git/", "/node_modules/", "/tests/", "/test_", "/.venv/", "/site-packages/")

_SERVICE_ROOTS = ("scripts", "migrations", "shared", "agents", "bots")


def _service_of(rel: Path) -> str:
    """الخدمةُ من المسار: ``services/<اسم>/…`` أو الجذرُ العلويّ."""
    parts = rel.parts
    if not parts:
        return "?"
    if parts[0] == "services" and len(parts) > 1:
        return parts[1]
    if parts[0] in _SERVICE_ROOTS:
        return parts[0]
    return parts[0]


def load_contract() -> dict[str, Any]:
    """العقدُ يُقرأ من مفتاح ``tables``، ويُتحقَّق أنّه غيرُ فارغ.

    **هذا الشرطُ ليس تجميلاً.** أوّلُ صياغةٍ لهذا الحارس قرأت جذرَ YAML بدل
    ``tables``، فصار كلُّ جدولٍ «غيرَ مُصرَّحٍ عنه» وأبلغ الحارسُ **صفرَ مخالفات**
    على شجرةٍ تحمل خمساً وسبعين. حارسٌ يمرّ صفراً كاذباً أسوأُ من غيابه: يُقرَأ
    ضماناً ويُسجَّل تغطية.
    """
    raw = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    tables = raw.get("tables") if isinstance(raw, dict) and "tables" in raw else raw
    if not isinstance(tables, dict) or len(tables) < 100:
        raise SystemExit(
            f"OWNERSHIP_CONTRACT_UNREADABLE: {CONTRACT} أعطى "
            f"{len(tables) if isinstance(tables, dict) else 'لا شيء'} جدولاً — "
            "الحارسُ كان سيمرّ صفراً كاذباً، فيفشل صراحةً بدلاً من ذلك"
        )
    return tables


def _write_allowed(table: str, service: str, contract: dict[str, Any]) -> bool:
    meta = contract.get(table)
    if not isinstance(meta, dict):
        return True  # جدولٌ خارج العقد — لا يُدان بما لم يُعلَن عنه
    if service in (meta.get("writers") or []):
        return True
    # جسرٌ انتقاليٌّ موثَّق: `mirror` + `status: interim-bridge` إذنٌ صريح لا انحراف.
    return meta.get("mirror") == service


def _sql_literals(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if len(node.value) >= _MIN_SQL_LEN:
                yield node.value


def survey() -> dict[str, list[str]]:
    """{"<جدول>::<خدمة>": [ملفّات]} لكلّ كتابةٍ لم يأذن بها العقد."""
    contract = load_contract()
    found: dict[str, set[str]] = {}
    for path in sorted(ROOT.rglob("*.py")):
        rel = path.relative_to(ROOT)
        posix = "/" + rel.as_posix()
        if any(part in posix for part in _SKIP_PARTS) or rel.parts[0] == "tests":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        service = _service_of(rel)
        for sql in _sql_literals(tree):
            for match in _WRITE.finditer(sql):
                table = match.group(1).lower()
                if not _write_allowed(table, service, contract):
                    found.setdefault(f"{table}::{service}", set()).add(rel.as_posix())
    return {key: sorted(files) for key, files in sorted(found.items())}


def _head_sha() -> str:
    """رأسُ الشجرة الذي قِيس عليه الأساس — أو ``unknown`` إن تعذّر (لا رمي، ولا اختلاق).

    قيمةٌ مختلقةٌ كانت ستُنتِج ختماً يبدو صادقاً ولا يُحيل إلى شيء؛ و``unknown``
    تُبقي الفجوةَ مرئيّةً لـ``claim_base_guard`` بدل أن تُخفيها.

    و``measured_on`` **إشارةُ إسناد** لا سلطةَ طزاجة: يقول أين قِيس الأساس، لا أنّ
    القياسَ ما زال صالحاً — السلطةُ للماسح حين يُعاد تشغيله.
    """
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    sha = (proc.stdout or "").strip()
    return sha if proc.returncode == 0 and len(sha) == 40 else "unknown"


def _baseline() -> dict[str, list[str]]:
    if not BASELINE.is_file():
        return {}
    return json.loads(BASELINE.read_text(encoding="utf-8")).get("violations", {})


def findings() -> list[str]:
    current, base = survey(), _baseline()
    out: list[str] = []
    for key in sorted(set(current) - set(base)):
        files = " · ".join(current[key])
        out.append(f"مخالفةٌ جديدة: {key} ⇒ {files}")
    # الراتشِت ينزل: مدخلٌ بائتٌ يُقرَأ ديناً قائماً وقد سُدِّد.
    for key in sorted(set(base) - set(current)):
        out.append(f"مدخلٌ بائتٌ في الأساس لم يعد منحرفاً — احذفه: {key}")
    return out


def generate() -> None:
    current = survey()
    BASELINE.write_text(
        json.dumps(
            {
                "$comment": (
                    "كتاباتٌ لم يأذن بها docs/architecture/db_ownership.yml — "
                    "مَعدودةٌ لا محكومٌ عليها. لم يُثبَت أنّ كلّاً منها خطأ؛ بعضُها قد "
                    "يكون العقدُ هو المخطئ فيه. الأساسُ راتشِتٌ ينزل ولا يصعد: "
                    "يُخفَّض بنقل الكتابة إلى مالكها أو بتصحيح العقد بأساسٍ مُعلَن."
                ),
                "contract": CONTRACT.relative_to(ROOT).as_posix(),
                "measured_on": _head_sha(),
                "violation_count": len(current),
                "violations": current,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"كُتِب {BASELINE.relative_to(ROOT)} — {len(current)} مخالفة")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="الوضعُ الحاجب (افتراضيّ)")
    parser.add_argument("--generate", action="store_true", help="إعادةُ توليد الأساس")
    args = parser.parse_args(argv)

    if args.generate:
        generate()
        return 0

    problems = findings()
    if problems:
        print("db_writer_ownership_guard: FAIL")
        for item in problems:
            print(f"  ✗ {item}")
        print(
            "\nالكتابةُ تنتمي إلى مالك الجدول. إن كان العقدُ هو المخطئ فصحّحه "
            "بأساسٍ مُعلَن، ثمّ:\n  python scripts/ci/db_writer_ownership_guard.py --generate"
        )
        return 1
    print(f"db_writer_ownership_guard_ok baseline={len(_baseline())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
