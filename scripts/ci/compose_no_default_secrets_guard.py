#!/usr/bin/env python3
"""لا سرَّ افتراضيّ في Compose — `COMPOSE-DEFAULT-SECRET-IS-A-PUBLISHED-SECRET-01`.

`${APP_DB_PASSWORD:-sahool_app_pw}` ليست «قيمةً مريحة للتطوير». هي **كلمة مرور
منشورة** لدورٍ مقيّد يحمل RLS: كلّ من قرأ المستودع يعرفها، وكلّ بيئة أُقلعت بلا
ضبطٍ صريح تعمل بها. والمقيس على `258a5835`: أربعة أسرار افتراضيّة في خمسة ملفّات —
`APP_DB_PASSWORD` (١٩ خدمة) · `JOBS_DB_PASSWORD` · `ODOO_DB_PASSWORD` ·
`VLLM_API_KEY`.

**والعلاج ليس قاعدةً واحدة، وهذا مقيسٌ لا رأي:** `:?required` على خدمةٍ **خلف
profile** يكسر `docker compose config` للمكدّس الافتراضيّ — الاستيفاء يسبق ترشيح
الـprofiles (أُثبِت بمِسبار: `profiles: ["gpu"]` بمتغيّر `:?` ⇒ `rc=1` مع تفعيل
الـprofile وبدونه). فالمقبول شكلان:

  * ``${VAR:?…}`` — إلزامٌ صريح. مناسبٌ لمتغيّرٍ يستهلكه خدمةٌ دائمة.
  * ``${VAR:-}`` — افتراضيٌّ **فارغ**. يُزيل السرّ المنشور بلا كسر مكدّسٍ لا يستعمل
    الخدمة، والفشل يبقى مغلقاً عند الاستعمال الفعليّ.

والمرفوض واحد: ``${VAR:-<قيمة>}`` حيث `VAR` اسمُ سرّ. **وكذلك القيمة الحرفيّة بلا
استيفاء أصلاً** (`PASSWORD: abc`)، وإلّا كان الحارس يدفع الكاتب إلى صيغةٍ لا يراها.

النطاق من `compose_surface.py` — مصدرٌ واحد يستهلكه كلّ حارسٍ يمسّ Compose، فلا
يعود كلُّ حارسٍ يحمل قائمته وتنحرف الأربع عن بعضها.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compose_surface import ROOT, compose_files, discovery_witness  # noqa: E402

EXCEPTIONS = ROOT / "docs" / "architecture" / "compose_secret_exceptions.json"

#: اسمُ متغيّرٍ يُعَدّ سرّاً. المطابقة على الاسم لا القيمة: القيمة قد تبدو بريئة
#: (`local`, `dev`) وتكون مفتاحاً يقبله خادمٌ حقيقيّ.
SECRET_NAME = re.compile(r"(PASSWORD|PASSWD|SECRET|_KEY|APIKEY|API_KEY|TOKEN|CREDENTIAL|_PW)\b")

#: أسماءٌ تحمل الكلمة ولا تحمل سرّاً — تُستثنى **بالبنية** لا بقائمةٍ في ملفّ.
NOT_SECRET = re.compile(r"(_KEY_ID|_KEY_FILE|_KEY_PATH|_TOKEN_URL|REQUIRE_AUTH_TOKEN)\b")

_DEFAULTED = re.compile(r"\$\{([A-Z0-9_]+):-([^}]*)\}")
_LITERAL = re.compile(r"^\s*(?:-\s+)?([A-Z0-9_]+)\s*[:=]\s*(?!\$)(\S.*?)\s*$")


def _is_secret(name: str) -> bool:
    return bool(SECRET_NAME.search(name)) and not NOT_SECRET.search(name)


def _exceptions() -> dict[str, dict]:
    if not EXCEPTIONS.is_file():
        return {}
    return json.loads(EXCEPTIONS.read_text(encoding="utf-8")).get("exceptions", {})


def findings() -> list[tuple[str, str]]:
    """(مفتاح، رسالة) لكلّ انتهاك — **بلا** تطبيق الاستثناءات.

    الفصل مقصود: `violations()` تُرشّح، و`stale_exceptions()` تحتاج المجموعة
    **الخام**. وأوّل صياغةٍ عندي اشتقّت الحيّ من الافتراضيّات وحدها، فأعلنت
    إحدى عشرة استثناءً حرفيّاً بائتةً وهي حيّة — نفس صنف «قياسٌ يعدّ غير ما
    يدّعي» الذي يحرسه هذا الملفّ.
    """
    out: list[tuple[str, str]] = []
    for path in compose_files():
        rel = str(path.relative_to(ROOT))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for name, default in _DEFAULTED.findall(line):
                if not _is_secret(name) or default == "":
                    continue
                out.append(
                    (
                        f"{rel}::{name}",
                        f"{rel}:{number}: ${{{name}:-…}} افتراضيٌّ لسرّ — سرٌّ منشور. "
                        f"استعمل `${{{name}:?…}}` لخدمةٍ دائمة، أو `${{{name}:-}}` فارغاً "
                        "لخدمةٍ خلف profile",
                    )
                )
            match = _LITERAL.match(stripped)
            if match:
                name, value = match.group(1), match.group(2)
                # **تُنزَع علامات الاقتباس أوّلاً.** أوّل صياغةٍ عندي فحصت القيمة
                # كما وردت، فأدانت `JWT_SECRET: "${JWT_SECRET}"` — استيفاءٌ صحيح
                # تبدأ قيمتُه بعلامة اقتباس لا بـ`$`. ٤٥ من ٦٧ من أوّل تشغيلٍ كانت
                # من هذا الصنف: حارسٌ يُدين الصواب يُدرَّب مستعملُه على تجاهله.
                value = value.strip().strip('"').strip("'")
                if _is_secret(name) and value and not value.startswith(("$", "{")):
                    out.append(
                        (
                            f"{rel}::{name}",
                            f"{rel}:{number}: {name} قيمةٌ حرفيّة بلا استيفاء — "
                            "سرٌّ منشور لا يراه فحصُ الافتراضيّات",
                        )
                    )
    return out


def violations() -> list[str]:
    """الانتهاكات بعد ترشيح الاستثناءات المُسمّاة."""
    allowed = _exceptions()
    return [msg for key, msg in findings() if key not in allowed]


def stale_exceptions() -> list[str]:
    """استثناءٌ بلا انتهاكٍ يقابله إعفاءٌ دائم بلا صاحب — وهو كيف يصير المؤقّت أبديّاً.

    والمجموعة الحيّة تُشتقّ من `findings()` نفسها، لا من نصفها: أيّ اشتقاقٍ ثانٍ
    ينحرف عن الأوّل، وهو الصنف الذي يحرسه هذا الملفّ.
    """
    live = {key for key, _ in findings()}
    return sorted(set(_exceptions()) - live)


def main() -> int:
    witness = discovery_witness()
    problems = violations()
    for key, entry in sorted(_exceptions().items()):
        for field in ("reason", "owner", "expires_on"):
            if not str(entry.get(field, "")).strip():
                problems.append(f"استثناءٌ بلا {field}: {key}")
    for key in stale_exceptions():
        problems.append(f"استثناءٌ بائت (لا انتهاك يقابله): {key} — احذفه، القائمة تتقلّص")

    if problems:
        print("compose_no_default_secrets_guard: FAIL")
        for line in problems:
            print(f"  ✗ {line}")
        print(f"\n  السطح المفحوص ({len(witness['discovered_paths'])} ملفّاً):")
        for rel in witness["discovered_paths"]:
            print(f"    · {rel}")
        return 1

    print(
        f"compose_no_default_secrets_guard: PASS "
        f"({len(witness['discovered_paths'])} ملفّاً على السطح · "
        f"{len(_exceptions())} استثناءً مُسمّى · المصدر: {witness['universe_source']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
