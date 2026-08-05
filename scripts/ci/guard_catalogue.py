#!/usr/bin/env python3
"""What every guard enforces, what it catches, and where it runs — derived, never listed.

A developer meeting this repository asks three questions no document answered: *which
guards exist*, *what does each one refuse*, and *how do I satisfy it*. §1 of the runbook
lists CI **jobs**; §3 lists **failure classes**. Neither is a guard catalogue, and writing
one by hand would go stale on the first guard added — the drift this repository keeps
measuring.

So the catalogue is generated from three sources that are already authoritative:

* ``.github/workflows/*.yml`` — which job invokes which guard, i.e. **where it blocks**;
* ``docs/architecture/guard_mutation_registry.json`` — the defect each guard was built to
  catch, in the author's own words, plus the test that must go red when it is planted;
* the guard's own module docstring — its first line, which states what it enforces.

Nothing is transcribed. A guard that appears in a workflow but carries no mutation spec
shows up as such, because that is a true and useful thing to say about it.

    python scripts/ci/guard_catalogue.py            # regenerate the catalogue
    python scripts/ci/guard_catalogue.py --check    # fail if the committed copy drifted
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github/workflows"
REGISTRY = ROOT / "docs/architecture/guard_mutation_registry.json"
OUTPUT = ROOT / "docs/runbooks/GUARD_CATALOGUE.md"

_INVOCATION = re.compile(r"python3?\s+(scripts/ci/[\w./-]+\.py)([^\n|&;]*)")


def _first_docstring_line(path: Path) -> str:
    """The guard's own one-line statement of what it enforces."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return ""
    doc = ast.get_docstring(tree) or ""
    return doc.splitlines()[0].strip() if doc else ""


def discover_invocations() -> dict[str, set[tuple[str, str]]]:
    """guard path -> {(workflow, job)} — where each guard actually blocks."""
    found: dict[str, set[tuple[str, str]]] = {}
    for workflow in sorted(WORKFLOWS.glob("*.y*ml")):
        text = workflow.read_text(encoding="utf-8")
        # Job attribution without a YAML parser would be guesswork, so parse it.
        import yaml

        document = yaml.safe_load(text) or {}
        for job_name, job in (document.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            for step in job.get("steps") or []:
                run = step.get("run")
                if not isinstance(run, str):
                    continue
                for match in _INVOCATION.finditer(run):
                    found.setdefault(match.group(1), set()).add((workflow.name, job_name))
    return found


def load_registry() -> dict[str, dict]:
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    return data.get("mutated", {})


def render() -> str:
    invocations = discover_invocations()
    registry = load_registry()
    lines: list[str] = [
        "# كتالوج الحرّاس — ما يفرضه كلّ حارس وأين يحجب",
        "",
        "> **مصنوعة مولَّدة.** لا تُحرَّر يدويّاً: `python scripts/ci/guard_catalogue.py`.",
        "> مشتقّة من الـworkflows (أين يحجب) · `guard_mutation_registry.json` (ما يمسكه،",
        "> بكلمات كاتبه) · وسطر التوثيق الأوّل في الحارس نفسه (ما يفرضه).",
        "",
        "**كيف تقرأ هذا الجدول عند فشل بوّابة:** ابحث عن اسم السكربت في رسالة الفشل، ثمّ",
        "اقرأ عمود «ما يمسكه» — فهو يصف العطل الذي وُجِد الحارس لأجله، لا القاعدة مجرّدة.",
        "و«الاختبار الشاهد» هو ما يجب أن يحمرّ إن عُطِّل الحارس؛ شغّله لتفهم الخاصّيّة.",
        "",
    ]

    blocking = sorted(invocations)
    total_mutations = sum(len(s["mutations"]) for s in registry.values())
    spec_names = {Path(g).name for g in blocking} & set(registry)

    lines += [
        "## ما يقوله هذا الجرد قبل أيّ تفصيل",
        "",
        f"- حرّاس تحجب في CI: **{len(blocking)}**",
        f"- منها **مُثبَتة بالتكذيب** (لها مواصفة طفرة نُفِّذت): **{len(spec_names)}**",
        f"- إجماليّ الطفرات المُسجَّلة: **{total_mutations}**",
        "",
        f"أي أنّ **{len(blocking) - len(spec_names)}** حارساً يحجب الدمج ولم يُثبَت قطّ أنّه",
        "يفشل حين يوجد العطل. هذا ليس اتّهاماً لها بل **قياس لِما نعرفه عنها**: اختبار",
        "الحارس المعتاد يقيس أنّه يمرّ على شجرة سليمة، وهي خاصّيّة يُحقّقها حارسٌ لا يفعل",
        "شيئاً. ومواصفة الطفرة هي الفرق بين «يمرّ» و«يمسك».",
        "",
        "---",
        "",
        f"## الحرّاس المُثبَتة بالتكذيب ({len(spec_names)})",
        "",
        "لكلٍّ منها عطلٌ يُزرَع في مصدرها فعليّاً (`guard_mutation_guard --run`) واختبارٌ",
        "**مُسمّى** يجب أن يحمرّ عندها. حمرةٌ باختبار آخر ليست دليلاً.",
        "",
    ]
    for guard in blocking:
        name = Path(guard).name
        if name not in registry:
            continue
        spec = registry[name]
        lines.append(f"### `{name}`")
        lines.append("")
        statement = _first_docstring_line(ROOT / guard)
        if statement:
            lines.append(f"**يفرض:** {statement}")
            lines.append("")
        lines.append(
            "**يحجب في:** " + " · ".join(f"`{w}` → `{j}`" for w, j in sorted(invocations[guard]))
        )
        lines.append("")
        lines.append(f"**الاختبار الشاهد:** `{spec['test']}`")
        lines.append("")
        lines.append("**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:")
        lines.append("")
        for mutation in spec["mutations"]:
            lines.append(f"- {mutation['why']} — يُسقِط `{mutation['expect']}`")
        lines.append("")

    rest = [g for g in blocking if Path(g).name not in registry]
    lines += [
        "---",
        "",
        f"## حرّاس تحجب ولم تُثبَت بالتكذيب ({len(rest)})",
        "",
        "تعمل، وتُسقِط بناءً حين تُخالَف — لكنّ أحداً لم يقِس أنّها **تفشل حين يوجد**",
        "**العطل**. عند إضافة مواصفة لأيٍّ منها ينتقل صفّها إلى القسم أعلاه تلقائيّاً.",
        "",
        "| الحارس | يفرض | يحجب في |",
        "|---|---|---|",
    ]
    for guard in rest:
        name = Path(guard).name
        statement = _first_docstring_line(ROOT / guard).replace("|", "·") or "—"
        if len(statement) > 96:
            statement = statement[:93] + "…"
        where = " · ".join(f"`{j}`" for _, j in sorted(invocations[guard])[:2])
        lines.append(f"| `{name}` | {statement} | {where} |")
    lines.append("")

    unwired = sorted(name for name in registry if f"scripts/ci/{name}" not in invocations)
    lines += [
        "---",
        "",
        f"## مُواصَفة بطفرات ولا يستدعيها أيّ workflow ({len(unwired)})",
        "",
        "أداة غير موصولة لا تحرس شيئاً (§٣.٢). وجودها هنا سؤالٌ لا اتّهام.",
        "",
    ]
    lines += [f"- `{n}`" for n in unwired] or ["- (لا شيء)"]
    lines += [
        "",
        "---",
        "",
        "**حدّ الصدق:** هذا يجرد ما تستدعيه الـworkflows بنمط `python scripts/ci/<x>.py`.",
        "حارسٌ يُستدعى عبر `pytest` أو سكربت وسيط أو `bash` **لا يظهر هنا**، ولا يُدّعى غير",
        "ذلك — وعدد البوّابات في §١ أكبر لهذا السبب. ولا يقيس هذا الجرد **جودة** الحارس ولا",
        "تغطيته، بل وجوده وموضعه وهل أُثبِت بالتكذيب.",
        "",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="افشل إن انحرفت النسخة المُلتزَمة")
    args = parser.parse_args(argv)

    rendered = render()
    # `relative_to` raises when the target sits outside the repository — which happens the
    # moment a test points OUTPUT at a tmp_path. A crash while reporting drift would hide
    # the drift behind a traceback, so the display path degrades instead of raising.
    try:
        shown = OUTPUT.relative_to(ROOT)
    except ValueError:
        shown = OUTPUT

    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != rendered:
            print(
                f"✗ {shown} منحرفة عن مصادرها.\n"
                "  أعِد التوليد: python scripts/ci/guard_catalogue.py",
                file=sys.stderr,
            )
            return 1
        print("guard_catalogue_ok")
        return 0

    OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"guard_catalogue: كُتِبت {shown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
