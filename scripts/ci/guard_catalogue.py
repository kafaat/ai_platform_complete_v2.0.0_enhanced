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

# GUARD-DIES-PRINTING-ITS-OWN-SUCCESS-UNDER-C-LOCALE-01: مخرَجُ هذا السكربت عربيّ،
# و`print` يُرمّز بلغة الآلة. فتحت `LC_ALL=C` كان يحسب **صحيحاً** ثمّ يموت وهو يطبع
# نتيجته (UnicodeEncodeError) ⇒ خروجٌ بغير صفر يُقرَأ حجباً وهو قد مرّ.
# **عند التحميل لا داخل `main()`** — بعضُ المخرَج يُطبَع من جسد الوحدة قبل أيّ نداء.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

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


#: ``${{ matrix.<key> }}`` inside a job's display name. A matrix job reaches the Actions
#: API under its *expanded* name, so a consumer that matches API jobs by name has to
#: expand it — from ``strategy.matrix.include``, which is data, not a guess.
_MATRIX_REF = re.compile(r"\$\{\{\s*matrix\.([A-Za-z_][\w-]*)\s*\}\}")


def _job_display_names(job_key: str, job: dict) -> list[str]:
    """The names this job reports to the Actions API — one, or one per matrix leg.

    An unnamed job reports its key. A named job reports its name. A *matrix* job reports
    the name once per leg with ``${{ matrix.* }}`` substituted, so a single YAML job is
    several API jobs — and a consumer that expects one silently proves nothing about the
    other four. An expression this function cannot resolve yields **no** name rather than
    a guessed one: an unresolvable name is a measurement gap, and naming it wrongly would
    turn that gap into a false match.
    """
    declared = job.get("name")
    if not isinstance(declared, str) or not declared.strip():
        return [job_key]
    declared = declared.strip()
    if "${{" not in declared:
        return [declared]
    include = ((job.get("strategy") or {}).get("matrix") or {}).get("include")
    if not isinstance(include, list):
        return []
    names: list[str] = []
    for leg in include:
        if not isinstance(leg, dict):
            continue
        rendered = _MATRIX_REF.sub(
            lambda m, leg=leg: str(leg.get(m.group(1), m.group(0))), declared
        )
        if "${{" not in rendered:
            names.append(rendered)
    return names


def _run_steps() -> list[dict]:
    """Every ``run:`` step of every workflow job — the one walker both inventories share.

    ``discover_invocation_sites`` (guards named ``scripts/ci/<x>.py``) and
    ``discover_script_invocations`` (every Python file a step executes) are two views of
    the **same** walk, so they cannot disagree about which steps exist, which job they
    belong to, or whether a failure there is tolerated.
    """
    import yaml  # Job attribution without a YAML parser would be guesswork, so parse it.

    steps: list[dict] = []
    for workflow in sorted(WORKFLOWS.glob("*.y*ml")):
        document = yaml.safe_load(workflow.read_text(encoding="utf-8")) or {}
        workflow_dir = ((document.get("defaults") or {}).get("run") or {}).get("working-directory")
        for job_key, job in (document.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            job_names = _job_display_names(job_key, job)
            job_dir = ((job.get("defaults") or {}).get("run") or {}).get("working-directory")
            for index, step in enumerate(job.get("steps") or []):
                if not isinstance(step, dict):
                    continue
                run = step.get("run")
                if not isinstance(run, str):
                    continue
                name = step.get("name")
                directory = step.get("working-directory") or job_dir or workflow_dir or "."
                steps.append(
                    {
                        "workflow": workflow.name,
                        "job": job_key,
                        "job_names": job_names,
                        "step_index": index,
                        "step_name": name.strip() if isinstance(name, str) else None,
                        "step_if": step.get("if"),
                        # Only a literal true guarantees that failure is tolerated.
                        # Expressions may evaluate to false; do not assume an exemption.
                        "continue_on_error": step.get("continue-on-error") is True
                        or job.get("continue-on-error") is True,
                        "working_directory": str(directory),
                        "run": run,
                    }
                )
    return steps


def discover_invocation_sites() -> list[dict]:
    """Every place a guard is invoked, down to the step — the one parse, richest view.

    ``discover_invocations`` below is a projection of this, so the catalogue and any
    consumer that needs step-level detail (``collect_guard_surface_evidence``) read the
    **same** parse. Two parsers agreeing today is the drift class this repository keeps
    measuring; one parse with two views cannot drift.
    """
    sites: list[dict] = []
    for step in _run_steps():
        guards = sorted({match.group(1) for match in _INVOCATION.finditer(step["run"])})
        if not guards:
            continue
        site = {k: v for k, v in step.items() if k not in ("run", "working_directory")}
        site["guards"] = guards
        sites.append(site)
    return sites


#: Modules a step may run with ``python -m`` that are installed, not part of this tree.
#: An unknown module is **not** assumed external: it fails closed as unresolved, because
#: a guessed exemption is exactly how an inventory silently shrinks.
EXTERNAL_MODULES = frozenset(
    {"pip", "pytest", "pip_audit", "piptools", "compileall", "py_compile", "venv", "json"}
)

_PYTHON = re.compile(r"(?:^|(?<=[\s;&|(`]))python(?:3(?:\.\d+)?)?(?=\s)")
_SHELL_HOP = re.compile(r"(?:^|(?<=[;&|(])|(?<=\bbash\s)|(?<=\bsh\s))\s*([\w./-]+\.sh)\b")
_CD = re.compile(r"(?:^|(?<=[;&|(]))\s*cd\s+(\S+)")
#: ``NAME="$(cd "$(dirname "${BASH_SOURCE[0]}")/<rel>" && pwd)"`` (optionally inside
#: ``${NAME:-…}``) — the one idiom by which a script names its own root. Its value is
#: decidable from the script's path, so it is resolved rather than failed closed.
_SELF_ROOT = re.compile(
    r"^\s*(?:export\s+)?(\w+)=.*dirname\s+\"?\$\{?(?:BASH_SOURCE(?:\[0\])?|0)\}?\"?\)"
    r"(/[^\"\s)]*)?\"?\s*&&\s*pwd"
)
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][\w]*)\1")
_FLAGS_WITH_VALUE = frozenset({"-X", "-W", "-Q"})


def _shell_lines(text: str) -> list[str]:
    """Shell text as logical command lines: heredoc bodies and comment lines removed.

    A heredoc body is data fed to a command (inline Python, a JSON record), not a
    command — reading ``python foo`` inside it as an invocation would invent one.
    """
    lines: list[str] = []
    pending = ""
    terminator: str | None = None
    for raw in text.splitlines():
        if terminator is not None:
            if raw.strip() == terminator:
                terminator = None
            continue
        line = pending + raw
        if line.rstrip().endswith("\\"):
            pending = line.rstrip()[:-1] + " "
            continue
        pending = ""
        heredoc = _HEREDOC.search(line)
        if heredoc:
            terminator = heredoc.group(2)
        if line.lstrip().startswith("#"):
            continue
        lines.append(line)
    if pending:
        lines.append(pending)
    return lines


def _python_target(rest: str) -> tuple[str, str]:
    """``(kind, token)`` for one interpreter launch, read from the text after ``python``.

    ``kind`` is ``file`` (a script path), ``module`` (``-m``) or ``inline`` (``-c`` / ``-``:
    nothing on disk to inspect). Tokens are pulled lazily, so an inline program's own
    quoting never has to parse. A launch whose text cannot be tokenised is ``unresolved``.
    """
    import shlex

    lexer = shlex.shlex(rest, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        skip = False
        for token in lexer:
            if skip:
                skip = False
                continue
            if token == "-m":
                return "module", next(lexer, "")
            if token in ("-c", "-") or token.startswith("<"):
                return "inline", token
            if token in _FLAGS_WITH_VALUE:
                skip = True
                continue
            if token.startswith("-"):
                continue
            if token[:1] in ";&|()":
                break
            return "file", token
    except ValueError:
        return "unresolved", rest.strip()
    return "inline", ""


def _resolve(token: str, directory: Path | None, kind: str) -> tuple[str, str | None]:
    """``(status, repo-relative path)`` — status is ``file`` · ``external`` · ``unresolved``."""
    if kind == "module" and token.split(".")[0] in EXTERNAL_MODULES:
        return "external", None
    if directory is None or "$" in token or "`" in token or not token:
        return "unresolved", None
    if kind == "module":
        parts = token.split(".")
        candidates = [
            directory.joinpath(*parts).with_suffix(".py"),
            directory.joinpath(*parts, "__main__.py"),
        ]
    else:
        candidates = [directory / token]
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file() and resolved.suffix == ".py" and resolved.is_relative_to(ROOT):
            return "file", resolved.relative_to(ROOT).as_posix()
    return "unresolved", None


def _cd(target: str, directory: Path | None) -> Path | None:
    """The directory after ``cd <target>`` — ``None`` (unknown) when it is not literal."""
    target = target.strip("'\"")
    if directory is None or "$" in target or "`" in target or target in ("-", "~"):
        return None
    return (directory / target).resolve()


def _expand(text: str, variables: dict[str, Path]) -> str:
    for name, value in variables.items():
        text = re.sub(r"\$\{" + name + r"\}|\$" + name + r"\b", str(value), text)
    return text


def _scan_shell(
    text: str, directory: Path | None, script: Path | None = None
) -> tuple[list[dict], list[str]]:
    """Python launches and ``.sh`` hops in shell text, following literal ``cd``.

    ``script`` is the file's own path when the text is a ``.sh`` reached by a hop, so its
    self-root idiom (``_SELF_ROOT``) can be resolved instead of read as unknowable.
    """
    found: list[dict] = []
    hops: list[str] = []
    variables: dict[str, Path] = {}
    for line in _shell_lines(text):
        root = _SELF_ROOT.match(line) if script is not None else None
        if root:
            variables[root.group(1)] = (
                script.parent / (root.group(2) or "/").lstrip("/")
            ).resolve()
            continue
        line = _expand(line, variables)
        for segment in re.split(r"&&|\|\||;", line):
            cd = _CD.match(segment)
            if cd:
                directory = _cd(cd.group(1), directory)
                continue
            for match in _PYTHON.finditer(segment):
                kind, token = _python_target(segment[match.end() :])
                if kind == "inline":
                    continue
                status, path = (
                    ("unresolved", None)
                    if kind == "unresolved"
                    else _resolve(token, directory, kind)
                )
                found.append({"token": token, "status": status, "script": path})
            for hop in _SHELL_HOP.findall(segment):
                hops.append(hop if directory is None else str((directory / hop).resolve()))
    return found, hops


def discover_script_invocations() -> list[dict]:
    """Every Python file a **blocking** CI step executes — by class, not by name.

    The same walk as ``discover_invocation_sites`` (``_run_steps``), read differently: any
    directory (``tools/`` · ``services/`` · ``frontend/``), ``python -m <local module>``,
    the step's ``working-directory`` and literal ``cd``, and one hop into a ``.sh`` the
    step runs. A launch whose target is not readable off the text is returned with
    ``status: unresolved`` rather than dropped, so a consumer can fail closed instead of
    measuring less than it claims.
    """
    rows: list[dict] = []
    for step in _run_steps():
        if step["continue_on_error"]:
            continue
        directory = (ROOT / step["working_directory"]).resolve()
        where = {"workflow": step["workflow"], "job": step["job"], "via": None}
        found, hops = _scan_shell(step["run"], directory)
        rows += [{**where, **row} for row in found]
        for hop in hops:
            shell = Path(hop)
            if not shell.is_absolute() or not shell.is_file() or not shell.is_relative_to(ROOT):
                rows.append({**where, "token": hop, "status": "unresolved", "script": None})
                continue
            via = shell.relative_to(ROOT).as_posix()
            inner, _ = _scan_shell(shell.read_text(encoding="utf-8"), directory, shell)
            rows += [{**where, "via": via, **row} for row in inner]
    return rows


def discover_invocations() -> dict[str, set[tuple[str, str]]]:
    """guard path -> {(workflow, job)} — where each guard actually blocks."""
    found: dict[str, set[tuple[str, str]]] = {}
    for site in discover_invocation_sites():
        if site["continue_on_error"]:
            continue
        for guard in site["guards"]:
            found.setdefault(guard, set()).add((site["workflow"], site["job"]))
    return found


def load_registry() -> dict[str, dict]:
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    return data.get("mutated", {})


def load_behavioural() -> dict[str, dict]:
    """المواصفات السلوكيّة — مفاتيحها **مسارات مصادر إنتاج** لا أسماء حرّاس.

    تُعَدّ هنا لأنّ هذا الجرد يزعم أنّه يقول «ما نعرفه عن حرّاسنا»، وقسمٌ مقيس لا
    يظهر فيه يجعل الرقم أصغر من الواقع بصمت — وهو نفس عطل «سكوتٌ يُقرأ خضرةً».
    """
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    return {k: v for k, v in data.get("behavioural", {}).items() if not k.startswith("$")}


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
    behavioural = load_behavioural()
    behavioural_mutations = sum(len(s["mutations"]) for s in behavioural.values())

    lines += [
        "## ما يقوله هذا الجرد قبل أيّ تفصيل",
        "",
        f"- حرّاس تحجب في CI: **{len(blocking)}**",
        f"- منها **مُثبَتة بالتكذيب** (لها مواصفة طفرة نُفِّذت): **{len(spec_names)}**",
        f"- إجماليّ الطفرات المُسجَّلة: **{total_mutations}**",
        f"- وطفراتٌ **سلوكيّة** تُزرَع في منطق الإنتاج نفسه: **{behavioural_mutations}** "
        f"على {len(behavioural)} مصدراً",
        "",
        "والسلوكيّة محورٌ آخر لا زيادةٌ في العدد: الحارس الساكن يقيس **وقوع** الشيء —",
        "أنّ المسار يستشير مفتاح الطوارئ مثلاً — ويمرّ أخضر على مسارٍ يستشيره ثمّ يتجاهل",
        "نتيجته، أو يستشيره بنطاقٍ أضيق فلا يُطابِق. فتلك تُزرَع في المصدر الفيزيائيّ",
        "ويجب أن يحمرّ اختبارُ **أثرها**.",
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

    # Preserve advisory invocations in the inventory without calling them blockers
    # or falsely declaring them unwired. The detailed evidence consumer uses all sites.
    sites = discover_invocation_sites()
    all_invoked = {guard for site in sites for guard in site["guards"]}
    advisory = sorted(
        {
            (guard, site["workflow"], site["job"])
            for site in sites
            if site["continue_on_error"]
            for guard in site["guards"]
        }
    )
    if advisory:
        lines += [
            "---",
            "",
            f"## استدعاءات غير مانعة بحسب continue-on-error ({len(advisory)})",
            "",
            "يشمل التصريح على الخطوة أو الوظيفة؛ تبقى هذه الاستدعاءات ظاهرة ولا تُعدّ حجبًا.",
            "",
            "| الأداة | workflow | الوظيفة |",
            "|---|---|---|",
        ]
        lines += [f"| `{Path(g).name}` | `{w}` | `{j}` |" for g, w, j in advisory]
        lines.append("")

    unwired = sorted(name for name in registry if f"scripts/ci/{name}" not in all_invoked)
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
