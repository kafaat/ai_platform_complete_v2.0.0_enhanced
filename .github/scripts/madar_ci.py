"""Read completed GitHub.com Actions attempts; write an Arabic job summary."""

import html
import http.client
import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_LOG = 4 * 1024 * 1024  # the tail of a job log kept for diagnosis
MAX_LOG_STREAM = 64 * 1024 * 1024  # stop downloading a job log beyond this
MAX_SUMMARY = 850_000
FAILED = {"failure", "timed_out", "action_required", "startup_failure", "stale"}
RESULTS = {
    "success": "نجحت",
    "failure": "فشلت",
    "skipped": "تُخطيت",
    "cancelled": "أُلغيت",
    "timed_out": "انتهت المهلة",
    "action_required": "تنتظر تدخلاً",
    "neutral": "محايدة",
    "stale": "انتهت صلاحيتها",
    "startup_failure": "تعذّر البدء",
}
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


class LogTooLarge(ValueError):
    """A job log longer than MAX_LOG_STREAM; nothing of it was diagnosed."""


class LogText(str):
    """Job log text; `truncated` says only its last MAX_LOG bytes were kept."""

    truncated = False


def display(value, width=120):
    # Render API metadata as inert Markdown text, including workflow job names.
    value = " ".join(str(value).split())[:width]
    return "".join(html.escape(c) if c.isalnum() or c in " -." else f"&#{ord(c)};" for c in value)


class LogRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urlsplit(newurl)
        if target.scheme != "https":
            raise ValueError("unsafe redirect")
        nxt = super().redirect_request(req, fp, code, msg, headers, newurl)
        if nxt and target.netloc != urlsplit(req.full_url).netloc:
            nxt.remove_header("Authorization")
        return nxt


class GitHub:
    def __init__(self, repo, token):
        self.base = f"https://api.github.com/repos/{repo}/actions/"
        self.token = token
        self.http = build_opener(LogRedirect())

    def open(self, path):
        req = Request(
            self.base + path,
            headers={
                "Authorization": "Bearer " + self.token,
                "User-Agent": "Madar-CI",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        return self.http.open(req, timeout=20)

    def read(self, path, limit):
        with self.open(path) as response:
            data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError("size limit")
        return data

    def metadata(self, path):
        return json.loads(self.read(path, 16 * 1024 * 1024))

    def log(self, job_id):
        with self.open(f"jobs/{job_id}/logs") as response:
            return read_log_tail(response)


GROUP_RUN = re.compile(rb"(?m)^\S+ ##\[group\]Run [^\n]*")


def read_log_tail(response, keep=MAX_LOG, ceiling=MAX_LOG_STREAM):
    """Stream a job log and keep its last `keep` bytes: a failing step's output is at the end.

    A long step's `##[group]Run` header can fall before the kept window (SAHOOL's unit job
    prints about 4.7 MB after it). The last header dropped is carried over and put back in
    front of the tail, closed at once, so the step's command still frames its output.
    """
    kept, total, header = bytearray(), 0, None
    while chunk := response.read(1024 * 1024):
        total += len(chunk)
        if total > ceiling:
            raise LogTooLarge(f"log over {ceiling} bytes")
        kept += chunk
        if len(kept) > keep:
            cut = len(kept) - keep
            dropped = None
            for found in GROUP_RUN.finditer(kept):
                if found.start() >= cut:
                    break
                dropped = found
            if dropped:
                header = bytes(dropped.group(0)).rstrip(b"\r")
            del kept[:cut]
    text = bytes(kept).decode("utf-8-sig" if total <= keep else "utf-8", errors="replace")
    if total > keep and header and not GROUP_RUN.match(bytes(kept)):
        lead = header.decode("utf-8", errors="replace")
        text = f"{lead}\n{lead.split(' ', 1)[0]} ##[endgroup]\n{text}"
    text = LogText(text)
    text.truncated = total > keep
    return text


# Who receives a failed job. Each specialist is a read-only Claude Code agent in
# .claude/agents/; it sends its recommendation to ci-fixer, the lab re-verifies the fix on
# its new commit, and the merge stays with the technical hospital
# (docs/runbooks/CI_FAILURE_HANDOFF_AR.md). Order matters: the most specific owner first.
SPECIALISTS = {
    "security": ("مراجع الأمن", "security-reviewer"),
    "migrations": ("مراجع الترحيلات وقاعدة البيانات", "migrations-reviewer"),
    "dependencies": ("مراجع الاعتماديات", "dependency-reviewer"),
    "frontend": ("مراجع الواجهة", "frontend-reviewer"),
    "ci-quality": ("وكيل جودة CI", "ci-quality-triage"),
}
FIXER = "ci-fixer"
ROUTES = (
    (
        "security",
        r"secur|bandit|gitleaks|secret|trivy|codeql",
        r"\bCVE-\d{4}-\d+|GHSA-[\w-]+|leaks? found|Severity: High",
    ),
    (
        "migrations",
        r"migrat|pg16|postgis|live pg|restricted role|alembic|database",
        r"SQLSTATE|psycopg|asyncpg\.exceptions|relation \"[^\"\n]+\" does not exist|run_migrations",
    ),
    (
        "dependencies",
        r"dependenc|drift|pip-audit|requirements|lockfile|constraints",
        r"has ==[\w.+-]+, constraints\.txt has|ResolutionImpossible|No matching distribution|ERESOLVE",
    ),
    (
        "frontend",
        r"frontend|playwright|typecheck|eslint|vitest|flutter|\be2e\b",
        r"error TS\d{4}|npm ERR!|\bvitest\b|\beslint\b",
    ),
)


def route(job_name, step_name, evidence_text=""):
    """The specialist for a failed job: by failing step name, then job name, then log."""
    for name in (step_name, job_name):
        for role, by_name, _ in ROUTES:
            if name and re.search(by_name, name, re.I):
                return role
    for role, _, by_log in ROUTES:
        if evidence_text and re.search(by_log, evidence_text):
            return role
    return "ci-quality"


def handoff_line(role, url, head):
    title, agent = SPECIALISTS[role]
    commit = f" · الالتزام `{head}`" if head else ""
    return (
        f"{title} (`.claude/agents/{agent}.md`) يراجع للقراءة فقط ويرسل توصيته إلى وكيل الإصلاح"
        f" (`{FIXER}`). الدليل: [سجل الخطوة]({url}){commit}."
    )


def failing_output(log):
    """The part of the log that says why it failed, for routing.

    Only the end of each failed command block: pytest's short summary when there is one,
    else its last 8 KiB. A whole unit-suite output (megabytes of passed test names) would
    route by words that have nothing to do with the failure.
    """
    parts = []
    for _, output in failed_commands(log):
        summary = output.rfind("short test summary info")
        parts.append(output[summary:] if summary >= 0 else output[-8192:])
    return "\n".join(parts) if parts else log[-8192:]


def failed_commands(log):
    """Only consider command blocks closed by an actual failing runner marker."""
    clean = ANSI.sub("", log)
    blocks = re.split(r"(?m)^\S+ ##\[group\]Run ", clean)[1:]
    for block in blocks:
        header, _, rest = block.partition("\n")
        _, sep, output = rest.partition("##[endgroup]")
        if not sep:
            continue
        output, marker, _ = output.partition("##[error]Process completed with exit code ")
        if marker:
            yield header.lower(), output


def diagnosis(steps, log):
    if len(steps) != 1:
        return (
            "تعذّر إسناد سبب واحد إلى خطوة بعينها.",
            "وكيل الجودة يراجع أدلة الخطوات كلًا على حدة.",
        )
    names = steps[0]["name"].lower()
    blocks = list(failed_commands(log))
    if "playwright" in names or "browser" in names:
        for cmd, output in blocks:
            if "playwright install" in cmd and re.search(
                r"Playwright does not support chromium on [a-zA-Z0-9_.-]+", output
            ):
                return (
                    "تعذّر تثبيت Chromium لأن إصدار Playwright المستخدم لا يدعم بيئة المشغّل.",
                    "وكيل بيئة CI يطابق إصدار المشغّل مع إصدارات Playwright المدعومة ثم يعيد التحقق.",
                )
    if "dependenc" in names or "drift" in names:
        for cmd, output in blocks:
            if ("drift" in cmd or "consisten" in cmd) and re.search(
                r"has ==[\w.+-]+, constraints\.txt has ==[\w.+-]+", output
            ):
                return (
                    "وجد فحص الاعتماديات تعارضاً بين إصدار خدمة وملف القيود.",
                    "وكيل الاعتماديات يقارن التعريفين ويعيد تشغيل فحص الاتساق.",
                )
    if "test" in names:
        for cmd, output in blocks:
            failed_case = re.search(r"(?m)^\S+ FAILED (\S+::\S+)", output)
            if re.search(r"\bpytest\b", cmd) and failed_case:
                return (
                    "سجّل pytest فشل حالة اختبار داخل خطوة الاختبارات. أول حالة فاشلة: "
                    + display(failed_case.group(1), 240)
                    + ".",
                    "وكيل الاختبارات يعيد تشغيل الحالة الفاشلة على الرأس نفسه.",
                )
    return (
        "أثبتت بيانات GitHub تعثّر الوظيفة. سبب التعثر يحتاج مراجعة يدوية.",
        "وكيل الجودة يفتح سجل الخطوة ويفحص أول تشخيص ذي صلة.",
    )


def card(repo, run_id, job, fetch, head=None):
    job_id = int(job["id"])
    head = job.get("head_sha") or head
    if head and not re.fullmatch(r"[a-fA-F0-9]{40}", str(head)):
        head = None
    state = job.get("conclusion")
    steps = job.get("steps") or []
    failed = [s for s in steps if s.get("conclusion") in FAILED]
    step = failed[0] if failed else None
    url = f"https://github.com/{repo}/actions/runs/{run_id}/job/{job_id}"
    if step:
        url += f"#step:{int(step['number'])}:1"
    title = f"### [{display(job.get('name') or job_id)}]({url})"
    status = RESULTS.get(state, "غير محسومة")
    if step:
        status += " · أول خطوة متعثّرة " + display(step["name"])
    if state in FAILED:
        routed = ""
        try:
            log = fetch(job_id)
            routed = failing_output(log)
            evidence, handoff = diagnosis(failed, log)
            if getattr(log, "truncated", False):
                evidence += f" فُحص آخر {MAX_LOG // (1024 * 1024)} MiB من السجل."
        except LogTooLarge:
            evidence = (
                f"السجل أطول من {MAX_LOG_STREAM // (1024 * 1024)} MiB فلم يُنزَّل. سبب التعثّر لم يُفحص."
            )
            handoff = "وكيل الجودة يفتح سجل الخطوة المتعثّرة من الرابط."
        except (OSError, ValueError, http.client.HTTPException) as exc:
            detail = f" (HTTP {exc.code})" if isinstance(exc, HTTPError) else ""
            evidence = f"تعذّر الوصول إلى سجل الوظيفة{detail}. سبب التعثّر لم يُفحص."
            handoff = "وكيل الجودة يتحقق من صلاحية السجل وإمكان قراءته."
        skipped_tests = [
            s
            for s in steps
            if s.get("conclusion") == "skipped"
            and re.search(r"^(run|execute)\b.*\btests?\b", s["name"], re.I)
        ]
        if skipped_tests:
            evidence += " تخطّى GitHub خطوة " + display(skipped_tests[0]["name"]) + "."
        role = route(job.get("name") or "", step["name"] if step else "", routed)
        evidence += "\n- الخطوة التالية — " + handoff
        handoff = handoff_line(role, url, head)
    elif state == "skipped":
        evidence, handoff = (
            "لم تُشغّل هذه الوظيفة.",
            "وكيل الجودة يراجع شرط التشغيل إذا كانت مطلوبة للقبول.",
        )
    elif state == "cancelled":
        evidence, handoff = (
            "أُلغي التشغيل قبل صدور نتيجة نهائية للوظيفة.",
            "منسّق الموجة يحدد الحاجة إلى إعادة التشغيل.",
        )
    elif state == "success":
        evidence, handoff = "أبلغ GitHub بنجاح الوظيفة.", "لا إحالة."
    else:
        evidence, handoff = "لم يُفحص سبب هذه الحالة.", "وكيل الجودة يراجع بيانات التشغيل."
    return (
        f"{title}\n\n- حالة الجلسة — {status}\n- نتيجة التحقق — {evidence}\n- الإحالة — {handoff}\n"
    )


def positive_id(value):
    if not re.fullmatch(r"[1-9][0-9]*", str(value)):
        raise ValueError("invalid identifier")
    return int(value)


def run_report(api, repo, run, emit):
    rid = positive_id(run["id"])
    attempt = positive_id(run["run_attempt"])
    head = str(run["head_sha"])
    if not re.fullmatch(r"[a-fA-F0-9]{40}", head):
        raise ValueError("invalid SHA")
    url = f"https://github.com/{repo}/actions/runs/{rid}/attempts/{attempt}"
    emit(
        f"## مدار · [{display(run['name'])}]({url})\n\nمحاولة {attempt} · الرأس `{head}` · {RESULTS.get(run.get('conclusion'), 'غير محسومة')}\n"
    )
    size, count, page = 0, 0, 1
    while True:
        group = api.metadata(f"runs/{rid}/attempts/{attempt}/jobs?per_page=100&page={page}")
        jobs = group["jobs"]
        for job in jobs:
            if int(job["run_id"]) != rid or (job.get("head_sha") and job["head_sha"] != head):
                raise ValueError("job identity mismatch")
            item = card(repo, rid, job, api.log, head)
            size += len(item.encode())
            if size > MAX_SUMMARY:
                emit("التقرير جزئي بسبب حدّ حجم الملخص. بقية الوظائف لم تُفحص.")
                return
            emit(item)
            count += 1
        if len(jobs) < 100:
            break
        page += 1
    if count == 0:
        emit("لم يُفحص التشغيل. لم ترجع GitHub أي وظيفة لهذه المحاولة.")


def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        raise ValueError("invalid repository")
    api = GitHub(repo, os.environ["GH_TOKEN"])
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as out:

        def emit(message):
            print(message, file=out)
            out.flush()

        try:
            if "workflow_run" in event:
                run = event["workflow_run"]
                if run["repository"]["full_name"].casefold() != repo.casefold():
                    raise ValueError("repository mismatch")
            else:
                run = api.metadata(f"runs/{positive_id(event['inputs']['run_id'])}")
            if run["status"] != "completed":
                emit("التشغيل قيد التنفيذ. أعد الفحص عند اكتماله.")
                return 0
            run_report(api, repo, run, emit)
        except (OSError, ValueError, KeyError, TypeError, http.client.HTTPException) as exc:
            code = f" (HTTP {exc.code})" if isinstance(exc, HTTPError) else ""
            emit(f"تعذّر إكمال جمع أدلة التشغيل{code}. الوظائف المتبقية لم تُفحص.")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
