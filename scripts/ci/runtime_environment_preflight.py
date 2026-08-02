#!/usr/bin/env python3
"""Assess whether this checkout can execute SAHOOL PATH-3 live runtime probes.

The check is intentionally truth-preserving: missing infrastructure produces a
BLOCKED_ENVIRONMENT state, not a false failure of the static governance gates
and never a runtime-verification claim.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deterministic_time import generated_at_utc  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "runtime-verification" / "generated"
OUT_JSON = OUT_DIR / "runtime_environment_preflight.json"
OUT_MD = OUT_DIR / "RUNTIME_ENVIRONMENT_PREFLIGHT.md"

REQUIRED_TOOLS = ("docker",)
OPTIONAL_TOOLS = ("psql", "nats", "curl", "git")
COMPOSE_CANDIDATES = (
    "docker-compose.v9.yml",
    "docker-compose.unified.yml",
    "docker-compose.dev.yml",
    "docker-compose.test.yml",
)


def command_version(name: str) -> dict[str, Any]:
    path = shutil.which(name)
    if not path:
        # نفس شكل الفرع الناجح: `available` وحده. إبقاء `path`/`version` هنا كان يجعل
        # **عدد مفاتيح السجلّ** نفسه يتغيّر بتغيّر الآلة — بصمة آلة في الشكل لا في القيمة.
        return {"available": False}
    commands = {
        "docker": [name, "--version"],
        "psql": [name, "--version"],
        "nats": [name, "--version"],
        "curl": [name, "--version"],
        "git": [name, "--version"],
    }
    try:
        proc = subprocess.run(
            commands[name], text=True, capture_output=True, timeout=10, check=False
        )
        first = (proc.stdout or proc.stderr).splitlines()[0] if (proc.stdout or proc.stderr) else ""
    except Exception as exc:  # pragma: no cover - defensive environment boundary
        first = type(exc).__name__
    # `path` و`version` هويّة آلة: مسار مطلق ورقم إصدار يختلفان بين العدّاءات.
    # المطلوب من الأثر أن يقول **هل الأداة متاحة**، لا أين هي وأيّ نسخة.
    del first
    return {"available": True}


def _classify_daemon_error(text: str) -> str:
    """سبب مُصنَّف بدل نصّ العميل — قدرة لا هويّة آلة.

    `RUNTIME-ENV-PREFLIGHT-STAMPS-THE-MACHINE-01`: الأثر المُلتزَم كان يحمل نصّ خطأ
    عميل Docker حرفيّاً، وهو يختلف بين إصدارات العميل لنفس السبب («Cannot connect to
    the Docker daemon…» مقابل «failed to connect to the docker API…»). فكان `--check`
    يفشل على كلّ آلة غير المولِّدة — لا لانحراف بل لاختلاف صياغة.
    """
    low = (text or "").lower()
    if "permission denied" in low:
        return "daemon_permission_denied"
    if "no such file" in low or "cannot connect" in low or "failed to connect" in low:
        return "daemon_unreachable"
    if not low.strip():
        return "daemon_unreachable"
    return "daemon_error"


def docker_daemon_state() -> dict[str, Any]:
    if not shutil.which("docker"):
        return {"reachable": False, "reason": "docker_cli_missing"}
    try:
        proc = subprocess.run(
            ["docker", "info", "--format", "{{json .ServerVersion}}"],
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
    except Exception:  # noqa: BLE001 — الاستثناء لا يُلتقَط عمداً: نصّه هويّة آلة
        # لا `as exc`: التقاطه يُغري بنقل نصّه إلى الأثر، وهو ما جاءت هذه الشريحة
        # لإزالته. السبب يُصنَّف ولا يُنقَل — و`probe_failed` مستقلّ عن المُشغِّل.
        return {"reachable": False, "reason": "probe_failed"}
    if proc.returncode != 0:
        # نصّ خطأ عميل Docker يختلف حرفيّاً بين إصداراته لنفس السبب، فيصير الأثر
        # وصفاً لآلة لا للمنصّة. يُصنَّف السبب ولا يُنقَل نصّه.
        return {"reachable": False, "reason": _classify_daemon_error(proc.stderr or proc.stdout)}
    return {"reachable": True, "server_version": proc.stdout.strip().strip('"')}


def loopback_available() -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
        return True
    except OSError:
        return False


def build() -> tuple[dict[str, Any], str]:
    tools = {name: command_version(name) for name in (*REQUIRED_TOOLS, *OPTIONAL_TOOLS)}
    compose_files = [name for name in COMPOSE_CANDIDATES if (ROOT / name).exists()]
    daemon = docker_daemon_state()
    blockers: list[dict[str, str]] = []
    if not tools["docker"]["available"]:
        blockers.append(
            {"code": "DOCKER_CLI_MISSING", "detail": "docker executable is not installed"}
        )
    elif not daemon.get("reachable"):
        blockers.append(
            {"code": "DOCKER_DAEMON_UNREACHABLE", "detail": str(daemon.get("reason", "unknown"))}
        )
    if not compose_files:
        blockers.append(
            {"code": "COMPOSE_FILE_MISSING", "detail": "no supported compose candidate found"}
        )
    if not loopback_available():
        blockers.append(
            {"code": "LOOPBACK_BIND_UNAVAILABLE", "detail": "cannot bind a local TCP socket"}
        )

    runnable = not blockers
    state = "RUNNABLE" if runnable else "BLOCKED_ENVIRONMENT"
    payload = {
        "schema_version": "1.0",
        # حتميّ كبيان الإصدار. `normalized()` أدناه يُسقِط هذا الحقل قبل المقارنة،
        # فالانحراف لم يكن يُفشِل الفحص — لكنّه **كان** يُنتِج فرقاً سطريّاً في ملفّ
        # متعقَّب، وذلك وحده يكفي لصنع تعارض على كلّ فرع متوازٍ.
        "generated_at": generated_at_utc(cwd=ROOT),
        "state": state,
        "runnable": runnable,
        "runtime_verified": False,
        "production_certified": False,
        "platform": {
            "system": platform.system(),
            # لا `release` ولا `python`: يصفان **آلة المُشغِّل** لا قدرة المنصّة،
            # وتباينهما بين العدّاءات كان يُفشِل الفحص بلا انحراف حقيقيّ.
            "machine": platform.machine(),
        },
        "tools": tools,
        "docker_daemon": daemon,
        "compose_candidates": compose_files,
        "loopback_bind_available": loopback_available(),
        "blockers": blockers,
        "activation_command": "python scripts/ci/path3_runtime_activation.py --compose-file docker-compose.v9.yml --environment-id <id>",
    }
    lines = [
        "# SAHOOL PATH-3 Runtime Environment Preflight",
        "",
        f"**State:** `{state}`",
        "",
        "> This report does not count as live runtime evidence.",
        "",
        "## Environment",
        "",
        f"- Docker CLI: **{'available' if tools['docker']['available'] else 'missing'}**",
        f"- Docker daemon: **{'reachable' if daemon.get('reachable') else 'unreachable'}**",
        f"- Loopback bind: **{'available' if payload['loopback_bind_available'] else 'unavailable'}**",
        f"- Compose candidates: **{len(compose_files)}**",
        "",
        "## Blockers",
        "",
    ]
    if blockers:
        lines.extend(f"- `{item['code']}` — {item['detail']}" for item in blockers)
    else:
        lines.append("- None")
    lines += [
        "",
        "## Truth boundary",
        "",
        "- Runtime verified services: **0**",
        "- Production certified services: **0**",
        "- A RUNNABLE preflight only permits activation; it does not prove service health.",
    ]
    return payload, "\n".join(lines) + "\n"


def normalized(payload: dict[str, Any]) -> dict[str, Any]:
    copy = dict(payload)
    copy.pop("generated_at", None)
    return copy


def capability_scope(payload: dict[str, Any]) -> dict[str, Any]:
    """البيئة التي **يصفها** الأثر — لا هويّتها، بل قدراتها التي تُغيّر إجابته.

    الأثر يقيس «هذا الـcheckout» بنصّ docstring الملفّ. فمقارنته بآلة أخرى ليست كشف
    انحراف بل ادّعاءً بأنّ الآلات كلّها آلة واحدة: عدّاء GitHub يملك Docker فيولّد
    RUNNABLE، وصندوق بلا خفيّ يولّد BLOCKED_ENVIRONMENT — والاثنان صادقان.

    ولذلك يُعلَن النطاق في الأثر بدل أن يُفترَض. المساواة الكاملة تُفرَض حين يتطابق
    النطاق؛ وخارجه يُفحَص **الشكل والاتّساق** — وهو ما لا يعتمد على آلة أصلاً.
    """
    daemon = payload.get("docker_daemon", {}) or {}
    return {
        # Tool availability is capability, not machine identity.  Two hosts where one has
        # the Docker/psql CLI and the other does not are not the same preflight scope and
        # must not be compared byte-for-byte merely because both are currently blocked.
        "tools_available": {
            name: bool(record.get("available"))
            for name, record in sorted((payload.get("tools") or {}).items())
        },
        "docker_daemon_reachable": bool(daemon.get("reachable")),
        "docker_daemon_reason": daemon.get("reason"),
        "loopback_bind_available": bool(payload.get("loopback_bind_available")),
        "compose_candidates": sorted(payload.get("compose_candidates") or []),
    }


_REASON_VOCABULARY = {
    "docker_cli_missing",
    "daemon_unreachable",
    "daemon_permission_denied",
    "daemon_error",
    "probe_failed",
}


def shape_problems(payload: dict[str, Any]) -> list[str]:
    """ما يبقى صحيحاً على **أيّ** آلة — فيُفحَص في كلّ مكان لا حيث تتطابق البيئة فقط.

    هذه ليست تعويضاً عن المقارنة بل الطبقة التي لا تملك أيّ بيئة أن تُعفي منها: أثر
    يدّعي جاهزيّةً وهو يحمل حاجباً، أو يدّعي تحقّقاً تشغيليّاً، أو يحمل سبباً خارج
    المفردات المُصنَّفة — كلّها كذب مهما كانت الآلة.
    """
    problems: list[str] = []
    if payload.get("runtime_verified") or payload.get("production_certified"):
        problems.append("preflight must never assert runtime verification or certification")
    runnable = bool(payload.get("runnable"))
    blockers = payload.get("blockers") or []
    if runnable != (not blockers):
        problems.append("state/blockers disagree: RUNNABLE requires an empty blocker list")
    if payload.get("state") != ("RUNNABLE" if runnable else "BLOCKED_ENVIRONMENT"):
        problems.append("state does not follow from runnable")
    reason = payload.get("docker_daemon", {}).get("reason")
    if reason is not None and reason not in _REASON_VOCABULARY:
        problems.append(f"unclassified daemon reason (machine text leaks back in): {reason!r}")
    for name, tool in (payload.get("tools") or {}).items():
        if set(tool) - {"available"}:
            problems.append(f"tool record carries machine identity beyond availability: {name}")
    return problems


def write() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload, report = build()
    OUT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    OUT_MD.write_text(report, encoding="utf-8")


def check(require_runnable: bool) -> int:
    if not OUT_JSON.exists() or not OUT_MD.exists():
        print("runtime environment preflight artifacts missing")
        return 1
    current, report = build()
    stored = json.loads(OUT_JSON.read_text(encoding="utf-8"))

    problems = shape_problems(stored)
    if problems:
        print("runtime environment preflight is internally false:")
        for line in problems:
            print(f"  - {line}")
        return 1

    stored_scope = capability_scope(stored)
    if stored_scope == capability_scope(current):
        if normalized(stored) != normalized(current):
            print("runtime environment preflight drift")
            return 1
        # Generated time is intentionally excluded; report itself is deterministic.
        if OUT_MD.read_text(encoding="utf-8") != report:
            print("runtime environment preflight report drift")
            return 1
    else:
        # صدق: يُقال ما لم يُفحَص، ولا يُقرأ النجاح تغطيةً لا يملكها.
        print(
            "preflight scope differs from this machine "
            f"(stored docker_reachable={stored_scope['docker_daemon_reachable']}, "
            f"here={capability_scope(current)['docker_daemon_reachable']}) — "
            "shape and consistency verified, value comparison skipped"
        )
    if require_runnable and not current["runnable"]:
        print("PATH-3 environment BLOCKED: " + ", ".join(b["code"] for b in current["blockers"]))
        return 2
    print(f"runtime environment preflight PASS: {current['state']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--generate", action="store_true")
    group.add_argument("--check", action="store_true")
    parser.add_argument("--require-runnable", action="store_true")
    args = parser.parse_args()
    if args.generate:
        write()
        return 0
    return check(args.require_runnable)


if __name__ == "__main__":
    raise SystemExit(main())
