#!/usr/bin/env python3
"""مسارٌ يُنفّذه compose يجب أن تضعه صورةُ الخدمة فعلاً — «مُسجَّل» ليس «يعمل».

``CONTAINER-COMMAND-PATH-NOT-IN-IMAGE-01``. مقيس 2026-08-05:
``sahool-canonical-execution-learning-worker`` في ``docker-compose.v9.yml:2561`` يُشغّل
``python /app/scripts/workers/canonical_execution_learning_worker.py`` ويفحص صحّته بالمسار
نفسه — و``services/sahool-platform/Dockerfile`` ينسخ ``shared/`` و
``services/sahool-platform/`` **فقط**. والعامل يسكن ``scripts/workers/`` في جذر المستودع،
فلا أمر ``COPY`` واحد يمكن أن يضعه هناك. النتيجة في الإنتاج: الحاوية تموت فوراً و
``restart: unless-stopped`` يُعيدها إلى الأبد، والفحص الصحّيّ يسقط بالسبب نفسه.

**وهذا هو صنف واقعة WOFOST حرفيّاً** (``cb6598fe``): المحرّك كان خارج سياق Docker فعاد
الموجِّه ``available: False`` صامتاً. أُغلِقت تلك بعقدٍ خاصٍّ بها؛ وهذا يُغلق **الخاصّيّة
العامّة** التي كانت ستمنع الاثنتين.

والاختبار القائم ``test_worker_is_registered_in_compose`` **أخضر طوال الوقت** — يقرأ نصّ
compose ويؤكّد أنّ الاسم والمسار مذكوران. وهما مذكوران. «مُسجَّل» ليس «يعمل» (§٣.٢٧).

**دلالات ``COPY`` مُطبَّقة لا مُقرَّبة**، لأنّ التقريب أنتج إيجابيّات كاذبة عند القياس:
نسخة أولى عالجت نسخ الأدلّة وحدها فاتّهمت ثلاث خدمات سليمة تنسخ ملفّاً إلى ملفّ
(``COPY .../worker_health_probe.py /app/worker_health_probe.py``). القواعد المُطبَّقة:

* مصدرٌ دليل ⇒ تُنسَخ **محتوياته** لا هو (``COPY shared/ /app/shared/`` يضع
  ``shared/x.py`` في ``/app/shared/x.py``)؛
* وجهةٌ تنتهي بـ``/`` ⇒ دليل، وإلّا فمصدرٌ مفرد ملفٌّ ⇒ الوجهة اسم الملفّ؛
* ``.dockerignore`` يُحترم — ملفّ مُستبعَد لا يدخل الصورة مهما قال ``COPY``.

يفشل مُغلَقاً: Dockerfile غير مقروء أو compose غير قابل للتحليل خطأ، لا تخطٍّ صامت.
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]

# مسار تنفيذٍ داخل الحاوية: نُقيّده بـ.py لأنّ الأصداف والثنائيّات تأتي من الصورة
# الأساس لا من COPY، فادّعاء غيابها يكون كاذباً.
_CONTAINER_PATH = re.compile(r"/app/[\w./-]+\.py")

_COPY = re.compile(r"^\s*(?:COPY|ADD)\s+(.*)$", re.I)


def dockerignore_patterns(context: Path) -> list[str]:
    """‏``.dockerignore`` يسكن **جذر السياق** لا جذر المستودع، كما يقرؤه الباني."""
    path = context / ".dockerignore"
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith(("#", "!")):
            out.append(line.rstrip("/"))
    return out


def _ignored(rel: str, patterns: list[str]) -> bool:
    parts = Path(rel).parts
    for pattern in patterns:
        if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(Path(rel).name, pattern):
            return True
        if any(fnmatch.fnmatch(part, pattern) for part in parts):
            return True
    return False


def copy_instructions(dockerfile: Path) -> list[tuple[list[str], str]]:
    """أزواج (مصادر، وجهة) من كلّ COPY/ADD، متجاهلاً مراحل البناء (--from)."""
    out: list[tuple[list[str], str]] = []
    text = dockerfile.read_text(encoding="utf-8")
    text = re.sub(r"\\\n", " ", text)  # أسطر موصولة بشرطة عكسيّة
    for line in text.splitlines():
        match = _COPY.match(line)
        if not match:
            continue
        tokens = match.group(1).split()
        if any(token.startswith("--from=") for token in tokens):
            continue  # ينسخ من مرحلة بناء لا من سياق المستودع — خارج ما نقيسه
        parts = [token for token in tokens if not token.startswith("--")]
        if len(parts) >= 2:
            out.append((parts[:-1], parts[-1]))
    return out


def sources_for(dockerfile: Path, container_path: str, *, context: Path) -> str | None:
    """مسار المصدر الذي يضع ``container_path`` في الصورة، أو None.

    كلّ مسارات ``COPY`` نسبيّة إلى **سياق البناء** لا إلى جذر المستودع — و
    ``build.context`` كثيراً ما يكون دليلاً فرعيّاً (``./frontend``). خلطُ الاثنين
    أنتج خمس اتّهامات كاذبة عند أوّل تشغيل لهذا الحارس.
    """
    patterns = dockerignore_patterns(context)

    def present(rel: str) -> str | None:
        candidate = context / rel
        return rel if candidate.is_file() and not _ignored(rel, patterns) else None

    for sources, dest in copy_instructions(dockerfile):
        directory_dest = dest.endswith("/") or len(sources) > 1
        for source in sources:
            source_path = context / source.rstrip("/")
            if not directory_dest and source_path.is_file():
                if dest == container_path:  # ملفّ ⇒ ملفّ
                    return source.rstrip("/")
                continue
            base = dest if dest.endswith("/") else dest + "/"
            if not container_path.startswith(base):
                continue
            tail = container_path[len(base) :]
            if source_path.is_dir():
                # مصدرٌ دليل ⇒ تُنسَخ محتوياته، فالذيل نسبيّ إليه مباشرةً.
                hit = present(f"{source.rstrip('/')}/{tail}")
                if hit:
                    return hit
            elif source_path.is_file() and tail == source_path.name:
                hit = present(source.rstrip("/"))
                if hit:
                    return hit
    return None


def executed_paths(service: dict) -> set[str]:
    blobs: list[str] = []
    for key in ("command", "entrypoint"):
        value = service.get(key)
        blobs += value if isinstance(value, list) else ([value] if value else [])
    test = (service.get("healthcheck") or {}).get("test")
    blobs += test if isinstance(test, list) else ([test] if test else [])
    return set(_CONTAINER_PATH.findall(" ".join(str(item) for item in blobs)))


def audit(root: Path | None = None) -> tuple[list[str], int]:
    """(إخفاقات، عدد الأزواج المفحوصة). الثاني يمنع «أخضر لأنّه لم يفحص شيئاً».

    ``root`` يُربَط **متأخّراً**: ``def audit(root=ROOT)`` كان يُجمّد القيمة وقت تعريف
    الدالّة، فلا يستطيع أيّ مُستدعٍ إعادة تجذير الفحص — ولا يستطيع اختبارٌ أن يقيس فرع
    «صفر أزواج مفحوصة». حارسٌ لا يُمكن استجواب فشله المُغلَق ليس مُغلَقاً، وقد كشف هذا
    اختبارُ العقد نفسه لا القراءة.
    """
    root = ROOT if root is None else root
    problems: list[str] = []
    examined = 0
    for compose in sorted(root.glob("docker-compose*.yml")):
        try:
            document = yaml.safe_load(compose.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as error:
            raise SystemExit(f"✗ تعذّر تحليل {compose.name} — يفشل مُغلَقاً: {error}") from None
        for name, service in (document.get("services") or {}).items():
            if not isinstance(service, dict):
                continue
            build = service.get("build")
            if not isinstance(build, dict):
                continue  # `build: ./dir` المختصر أو `image:` — لا Dockerfile مُعلَن
            context = (root / build.get("context", ".")).resolve()
            dockerfile = build.get("dockerfile", "Dockerfile")
            path = context / dockerfile
            if not path.is_file():
                problems.append(
                    f"{compose.name} :: {name} — Dockerfile مُعلَن وغير موجود: "
                    f"{path.relative_to(root) if path.is_relative_to(root) else path}"
                )
                continue
            for container_path in sorted(executed_paths(service)):
                examined += 1
                if sources_for(path, container_path, context=context) is None:
                    problems.append(
                        f"{compose.name} :: {name}\n"
                        f"      يُنفّذ  : {container_path}\n"
                        f"      الصورة : {dockerfile}\n"
                        f"      لا أمر COPY في هذا الـDockerfile يضع هذا المسار — الحاوية\n"
                        f"      ستموت عند الإقلاع، و`restart` سيُعيدها إلى الأبد."
                    )
    return problems, examined


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="الافتراضيّ؛ الراية تُصرّح النيّة")
    parser.parse_args(argv)

    problems, examined = audit(ROOT)
    if not examined:
        print(
            "✗ لم يُفحَص أيّ زوج (خدمة، مسار) — حارسٌ بلا عين يفشل مُغلَقاً بدل أن يخضرّ",
            file=sys.stderr,
        )
        return 2
    print(f"container_command_path_guard: {examined} زوج (خدمة، مسار تنفيذ) مفحوصاً")
    if problems:
        print("\ncontainer_command_path_guard: FAIL", file=sys.stderr)
        for problem in problems:
            print(f"  ✗ {problem}", file=sys.stderr)
        print(
            "\n  «مُسجَّل في compose» ليس «موجود في الصورة». إمّا أن ينسخ الـDockerfile\n"
            "  المسار، أو ينتقل الملفّ إلى شجرةٍ ينسخها فعلاً.",
            file=sys.stderr,
        )
        return 1
    print("container_command_path_guard_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
