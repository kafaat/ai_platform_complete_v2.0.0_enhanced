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

**وسكربتاتُ الهجرة سطحٌ ثانٍ** (`MIGRATOR-SCRIPT-DEFAULT-ROLE-PASSWORDS-01`): كان Compose
نظيفاً و`apply_in_compose.sh` — نقطةُ دخول صورة المُهاجر على Railway — يحمل
`${APP_DB_PASSWORD:-sahool_app_pw}` و`sahool_jobs_pw` و`odoo_app_pw`. فالسرُّ المنشور
انتقل من الملفّ المفحوص إلى الملفّ الذي يُنفَّذ. السطحُ مشتقٌّ من git
(`SHELL_UNIVERSE_SOURCE`) لا قائمةً، والافتراضيُّ المحسوب (`$(…)` أو `${…}` متداخل)
ليس قيمةً منشورة.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compose_surface import ROOT, compose_files, discovery_witness  # noqa: E402

EXCEPTIONS = ROOT / "docs" / "architecture" / "compose_secret_exceptions.json"

#: السطحُ الثاني: سكربتاتُ الهجرة التي تُنشئ أدوارَ القاعدة بكلمات مرورها.
SHELL_UNIVERSE_SOURCE = "git ls-files :(glob)migrations/*.sh"


def shell_files() -> list[Path]:
    """سكربتاتُ الهجرة المتعقَّبة. `ROOT` يُقرأ وقتَ الاستدعاء (الشواهد تُبدّله)."""
    out = subprocess.run(
        ["git", "ls-files", "--", "migrations/*.sh"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
    )
    if out.returncode != 0:
        return []
    return [ROOT / rel for rel in out.stdout.split()]


#: اسمُ متغيّرٍ يُعَدّ سرّاً. المطابقة على الاسم لا القيمة: القيمة قد تبدو بريئة
#: (`local`, `dev`) وتكون مفتاحاً يقبله خادمٌ حقيقيّ.
SECRET_NAME = re.compile(r"(PASSWORD|PASSWD|SECRET|_KEY|APIKEY|API_KEY|TOKEN|CREDENTIAL|_PW)\b")

#: أسماءٌ تحمل الكلمة ولا تحمل سرّاً — تُستثنى **بالبنية** لا بقائمةٍ في ملفّ.
NOT_SECRET = re.compile(r"(_KEY_ID|_KEY_FILE|_KEY_PATH|_TOKEN_URL|REQUIRE_AUTH_TOKEN)\b")

#: بدايةُ ``${NAME:-`` — والافتراضيُّ يُقرأ بأقواسٍ متوازنة لا بـ``[^}]*``: الصيغةُ القديمة
#: كانت تقطع ``${A_PASSWORD:-${LEGACY_PASSWORD:-سرّ}}`` عند أوّل ``}`` فتقرأ الافتراضيَّ
#: ``${LEGACY_PASSWORD:-سرّ`` ويُستثنى لأنّه يبدأ بـ``$`` — والسرُّ المنشور داخله لا يُرى
#: (مراجعةُ #1170 بعد دمجه، مُعادٌ إنتاجُها على 18b64ed0).
_DEFAULT_OPEN = re.compile(r"\$\{([A-Z0-9_]+)(?::?[-=])")
#: داخل الافتراضيّ: كلُّ عاملٍ يُنتج قيمةً حرفيّة يُقرأ — ``-``/``=`` (افتراضٌ وإسناد) و``+``
#: (بديلٌ حين يُضبط المتغيّر: ``${A:-${B:+سرّ}}`` يُسند السرَّ حين يغيب A ويُضبط B — مراجعةُ
#: Copilot على #1175)؛ و``?`` وحده لا يُنتج قيمة (يُفشل التوسيع).
_NESTED_OPEN = re.compile(r"\$\{([A-Za-z0-9_]+)(:?[-=+?])")
_SHELL_NAME = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*")
_LITERAL = re.compile(r"^\s*(?:-\s+)?([A-Z0-9_]+)\s*[:=]\s*(?!\$)(\S.*?)\s*$")


def _is_secret(name: str) -> bool:
    return bool(SECRET_NAME.search(name)) and not NOT_SECRET.search(name)


def _close(text: str, start: int, open_ch: str, close_ch: str) -> int | None:
    """موضعُ ما بعد إغلاقٍ متوازن لفتحةٍ سبقت ``start``، أو ``None`` إن لم يُغلَق."""
    depth = 1
    for i in range(start, len(text)):
        if text[i] == open_ch:
            depth += 1
        elif text[i] == close_ch:
            depth -= 1
            if depth == 0:
                return i + 1
    return None


def _defaulted(line: str) -> list[tuple[str, str]]:
    """``(اسم، افتراضيّ)`` لكلّ ``${NAME:-…}`` في السطر، والمتداخلُ منها أيضاً."""
    out = []
    for match in _DEFAULT_OPEN.finditer(line):
        end = _close(line, match.end(), "{", "}")
        if end is not None:
            out.append((match.group(1), line[match.end() : end - 1]))
    return out


def _literal_fallback(default: str) -> str:
    """النصُّ الذي يبلغ المتغيّرَ حين يغيب كلُّ متغيّرٍ متداخل.

    ``${X:-d}`` و``${X-d}`` و``${X:=d}`` و``${X=d}`` و``${X:+d}`` و``${X+d}`` تُسهم بحرفيِّ ``d``
    (تكراراً)، وأيُّ توسيعٍ آخر (``${X}`` · ``${X:?…}`` · ``$X`` · ``$(…)``) لا يُسهم بشيء:
    قيمتُه تُحسب وقتَ التشغيل لا تُكتب في المستودع.
    """
    out = []
    i = 0
    while i < len(default):
        if default.startswith("${", i):
            end = _close(default, i + 2, "{", "}")
            if end is None:
                return default[i:]
            inner = _NESTED_OPEN.match(default, i)
            if inner and not inner.group(2).endswith("?"):
                out.append(_literal_fallback(default[inner.end() : end - 1]))
            i = end
        elif default.startswith("$(", i):
            end = _close(default, i + 2, "(", ")")
            if end is None:
                return default[i:]
            i = end
        elif name := _SHELL_NAME.match(default, i):
            i = name.end()
        else:
            out.append(default[i])
            i += 1
    return "".join(out)


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
    for path in [*compose_files(), *shell_files()]:
        rel = str(path.relative_to(ROOT))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for name, default in _defaulted(line):
                # ما يُحسَب وقتَ التشغيل (`$(…)` · `$X` · `${X}`) ليس سرّاً مكتوباً؛ أمّا
                # الحرفيُّ — ولو داخل `${…:-…}` متداخل — فيبلغ المتغيّرَ حين يغيب الكلّ.
                if not _is_secret(name) or _literal_fallback(default) == "":
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
        f"{len(shell_files())} سكربتَ هجرة ({SHELL_UNIVERSE_SOURCE}) · "
        f"{len(_exceptions())} استثناءً مُسمّى · المصدر: {witness['universe_source']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
