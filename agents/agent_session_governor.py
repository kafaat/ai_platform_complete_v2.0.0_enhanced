#!/usr/bin/env python3
"""agents/agent_session_governor.py — مُحافظ جلسة الوكيل (Agent Session Governor).

الفكرة (مستلهمة من Ghostty Blackhole): الثقب الأسود يكبر مع السياق حتّى يبتلع
الشاشة — رسالته: "لا تنتظر حتّى ينهار السياق، بل تصرّف قبله". نطبّق المبدأ
تشغيليّاً لا بصريّاً: مُحافظ يراقب "صحّة السياق" ويُنشئ checkpoint تلقائيّاً
قبل الوصول للحدّ — يحفظ القرارات والفجوات والملفّات المعدّلة.

المخرجات عند --checkpoint (P1: قبل compact أو PR كبير):
  • agent-memory/JOURNAL.jsonl  ← يُضاف إدخال بما تمّ
  • agent-memory/OPEN_GAPS.md  ← يُحدَّث بالفجوات المفتوحة
  • agent-memory/CHECKPOINT_<ts>.md ← ملفّ لقطة الجلسة

الاستخدام:
  python3 agents/agent_session_governor.py --status      # عرض صحّة السياق
  python3 agents/agent_session_governor.py --checkpoint  # حفظ لقطة + تحديث OPEN_GAPS
  python3 agents/agent_session_governor.py --watch       # مراقبة مستمرّة (كلّ 30ث)

التكامل مع Claude Code (مثل claude-token.py في المقال):
  أضف في .claude/settings.json:
  {
    "statusLine": {"type":"command","command":"python3 agents/agent_session_governor.py --status-line"},
    "hooks": {
      "SessionStart": [{"hooks": [{"type":"command","command":"python3 agents/agent_session_governor.py --checkpoint"}]}],
      "SessionEnd":   [{"hooks": [{"type":"command","command":"python3 agents/agent_session_governor.py --checkpoint"}]}]
    }
  }
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

# ─── المسارات ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
MEM_DIR = ROOT / "agent-memory"
JOURNAL = MEM_DIR / "JOURNAL.jsonl"
OPEN_GAPS = MEM_DIR / "OPEN_GAPS.md"
FACTS = MEM_DIR / "FACTS.md"
MEMORY = MEM_DIR / "MEMORY.md"

# ─── عتبات صحّة السياق (تقديريّة — من خبرة عمل الجلسات الطويلة) ──────────
CONTEXT_WARN_PCT = 60  # تحذير: اقترب من compact
CONTEXT_CRIT_PCT = 80  # حرج: يجب checkpoint الآن
FILES_WARN = 15  # تحذير: ملفّات كثيرة مفتوحة
FILES_CRIT = 25  # حرج: تفتّت التركيز
GAPS_WARN = 5  # تحذير: فجوات معلّقة كثيرة

# ─── بنيانات ─────────────────────────────────────────────────────────────────


class ContextHealth:
    """صحّة سياق جلسة الوكيل — تُقاس من الملفّات الفعليّة."""

    def __init__(self) -> None:
        self.ts = datetime.now(UTC).isoformat()
        self.journal_entries = self._count_journal()
        self.open_gaps = self._count_open_gaps()
        self.files_touched = self._count_files_touched()
        self.memory_size_kb = self._memory_size()
        self.last_checkpoint = self._last_checkpoint()
        self.context_pct = self._estimate_context_pct()

    # ── قراءة الحالة الفعليّة ──────────────────────────────────────────────

    def _count_journal(self) -> int:
        if not JOURNAL.exists():
            return 0
        with JOURNAL.open(encoding="utf-8", errors="replace") as f:
            return sum(1 for line in f if line.strip())

    def _count_open_gaps(self) -> int:
        if not OPEN_GAPS.exists():
            return 0
        text = OPEN_GAPS.read_text(encoding="utf-8", errors="replace")
        return sum(
            1 for line in text.splitlines() if line.strip().startswith("-") and "✓" not in line
        )

    def _count_files_touched(self) -> int:
        """يعدّ الملفّات المذكورة في آخر 20 إدخال في JOURNAL."""
        if not JOURNAL.exists():
            return 0
        lines = [
            ln.strip()
            for ln in JOURNAL.read_text(encoding="utf-8", errors="replace").splitlines()
            if ln.strip()
        ]
        touched: set[str] = set()
        for line in lines[-20:]:
            try:
                entry = json.loads(line)
                for f in entry.get("files", []):
                    touched.add(f)
            except json.JSONDecodeError:
                pass
        return len(touched)

    def _memory_size(self) -> float:
        total = 0
        for p in MEM_DIR.glob("*.md"):
            total += p.stat().st_size
        if JOURNAL.exists():
            total += JOURNAL.stat().st_size
        return round(total / 1024, 1)

    def _last_checkpoint(self) -> str | None:
        checkpoints = sorted(MEM_DIR.glob("CHECKPOINT_*.md"), reverse=True)
        if not checkpoints:
            return None
        ts_str = checkpoints[0].stem.replace("CHECKPOINT_", "")
        return ts_str

    def _estimate_context_pct(self) -> int:
        """تقدير تقريبي لامتلاء السياق من حجم الذاكرة + الإدخالات.

        ⚠ تقديريّ: لا API لقياس tokens Claude في بيئتنا.
        الحدّ الأقصى التقريبي: ~200K token ≈ ~800KB نصّ.
        """
        # حجم النصّ في agent-memory + آخر entries ≈ مؤشّر جيّد
        approx_tokens = self.memory_size_kb * 1024 / 4  # ~4 chars/token
        approx_tokens += self.journal_entries * 200  # كلّ entry ~200 token
        max_tokens = 180_000  # تقديريّ (Claude context window ~ 200K)
        pct = int(min(99, approx_tokens / max_tokens * 100))
        return pct

    # ── المستوى والحكم ────────────────────────────────────────────────────────

    @property
    def level(self) -> str:  # green / yellow / red
        if (
            self.context_pct >= CONTEXT_CRIT_PCT
            or self.files_touched >= FILES_CRIT
            or self.open_gaps >= GAPS_WARN * 2
        ):
            return "red"
        if (
            self.context_pct >= CONTEXT_WARN_PCT
            or self.files_touched >= FILES_WARN
            or self.open_gaps >= GAPS_WARN
        ):
            return "yellow"
        return "green"

    @property
    def level_ar(self) -> str:
        return {"green": "آمن ✓", "yellow": "تحذير ⚠", "red": "حرج ✗"}[self.level]

    @property
    def recommendation_ar(self) -> str:
        if self.level == "red":
            return (
                "🔴 السياق حرج — checkpoint الآن:\n"
                "   • python3 agents/agent_session_governor.py --checkpoint\n"
                "   • اقترح /compact أو تقسيم PR\n"
                "   • أغلق الملفّات غير الضروريّة"
            )
        if self.level == "yellow":
            return (
                "🟡 اقترب من الحدّ — checkpoint قريباً:\n"
                "   • python3 agents/agent_session_governor.py --checkpoint\n"
                "   • راجع OPEN_GAPS.md وأغلق ما تمّ"
            )
        return "🟢 السياق آمن — استمرّ."

    def as_dict(self) -> dict:
        return {
            "ts": self.ts,
            "context_used_percent": self.context_pct,
            "level": self.level,
            "level_ar": self.level_ar,
            "journal_entries": self.journal_entries,
            "open_gaps": self.open_gaps,
            "files_touched_recent": self.files_touched,
            "memory_size_kb": self.memory_size_kb,
            "last_checkpoint": self.last_checkpoint,
            "thresholds": {
                "context_warn": CONTEXT_WARN_PCT,
                "context_crit": CONTEXT_CRIT_PCT,
                "thresholds_estimated": True,
            },
        }


# ─── Checkpoint ────────────────────────────────────────────────────────────


def _read_open_gaps_items() -> list[str]:
    if not OPEN_GAPS.exists():
        return []
    lines = OPEN_GAPS.read_text(encoding="utf-8", errors="replace").splitlines()
    return [ln.strip() for ln in lines if ln.strip().startswith("-") and "✓" not in ln]


def create_checkpoint(health: ContextHealth, reason: str = "manual") -> Path:
    """يحفظ لقطة الجلسة الحاليّة ويُحدِّث OPEN_GAPS.md."""
    MEM_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    cp_path = MEM_DIR / f"CHECKPOINT_{ts}.md"

    gaps = _read_open_gaps_items()
    recent_journal = []
    if JOURNAL.exists():
        lines = [
            ln
            for ln in JOURNAL.read_text(encoding="utf-8", errors="replace").splitlines()
            if ln.strip()
        ]
        for line in lines[-5:]:
            try:
                e = json.loads(line)
                recent_journal.append(f"- [{e.get('ts', '')}] {e.get('change', '')[:120]}")
            except json.JSONDecodeError:
                pass

    cp_content = f"""# Checkpoint — {ts}
**السبب**: {reason}
**مستوى السياق**: {health.level_ar} ({health.context_pct}% مقدَّر)
**ملفّات مسّتها الجلسة (آخر 20 entry)**: {health.files_touched}
**فجوات مفتوحة**: {len(gaps)}
**حجم ذاكرة الوكيل**: {health.memory_size_kb} KB

## آخر 5 تغييرات (من JOURNAL.jsonl)
{chr(10).join(recent_journal) or "_(لا إدخالات)_"}

## الفجوات المفتوحة (من OPEN_GAPS.md)
{chr(10).join(gaps) or "_(لا فجوات مفتوحة)_"}

## التوصية
{health.recommendation_ar}

## الخطوة التالية المقترَحة
- [ ] راجع الفجوات أعلاه وأغلق ما تمّ
- [ ] إن استمرّ السياق: `/compact` أو افتح جلسة جديدة
- [ ] قبل PR كبير: حدّث OPEN_GAPS.md يدويّاً بما تبقّى
"""
    cp_path.write_text(cp_content, encoding="utf-8")

    # إضافة إدخال JOURNAL
    entry = {
        "ts": ts[:10],
        "change": f"checkpoint({reason}): context={health.context_pct}% "
        f"gaps={len(gaps)} files={health.files_touched}",
        "files": [str(cp_path.relative_to(ROOT))],
    }
    with JOURNAL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return cp_path


# ─── واجهة المستخدم ──────────────────────────────────────────────────────────


def cmd_status(health: ContextHealth) -> None:
    """عرض بطاقة صحّة السياق."""
    colors = {"green": "\033[32m", "yellow": "\033[33m", "red": "\033[31m"}
    reset = "\033[0m"
    c = colors[health.level]

    bar_filled = int(health.context_pct / 5)
    bar = "█" * bar_filled + "░" * (20 - bar_filled)

    print(f"""
╔══════════════════════════════════════════╗
║   SAHOOL Agent Context Health            ║
╠══════════════════════════════════════════╣
║  السياق: {c}[{bar}] {health.context_pct:2d}%{reset}       ║
║  المستوى: {c}{health.level_ar:<30}{reset}  ║
╠══════════════════════════════════════════╣
║  journal_entries  : {health.journal_entries:<5}                  ║
║  open_gaps        : {health.open_gaps:<5}                  ║
║  files_touched    : {health.files_touched:<5} (آخر 20 entry)    ║
║  memory_size_kb   : {health.memory_size_kb:<7}                ║
║  last_checkpoint  : {str(health.last_checkpoint or "—"):<20}  ║
╠══════════════════════════════════════════╣
║  {health.recommendation_ar.splitlines()[0]:<40}  ║
╚══════════════════════════════════════════╝
""")
    if health.level != "green":
        for line in health.recommendation_ar.splitlines()[1:]:
            print(f"  {line}")


def cmd_status_line(health: ContextHealth) -> None:
    """سطر واحد لـClaude Code statusLine (مثل claude-token.py)."""
    symbols = {"green": "●", "yellow": "◐", "red": "○"}
    colors = {"green": "\033[32m", "yellow": "\033[33m", "red": "\033[31m"}
    r = "\033[0m"
    c = colors[health.level]
    s = symbols[health.level]
    print(
        f"{c}{s} ctx:{health.context_pct}% gaps:{health.open_gaps} files:{health.files_touched}{r}"
    )


def cmd_checkpoint(health: ContextHealth, reason: str) -> None:
    cp = create_checkpoint(health, reason)
    print(f"✓ Checkpoint → {cp.relative_to(ROOT)}")
    print(
        f"  السياق: {health.context_pct}% | فجوات: {health.open_gaps} | "
        f"ملفّات: {health.files_touched}"
    )
    if health.level == "red":
        print("  ⚠ السياق حرج — اقترح /compact أو تقسيم PR")


def cmd_watch(interval: int = 30) -> None:
    print(f"👁 مراقبة صحّة السياق (كلّ {interval}ث) — Ctrl+C للإيقاف")
    try:
        while True:
            h = ContextHealth()
            ts_now = datetime.now().strftime("%H:%M:%S")
            colors = {"green": "\033[32m", "yellow": "\033[33m", "red": "\033[31m"}
            r = "\033[0m"
            print(
                f"[{ts_now}] {colors[h.level]}{h.level_ar}{r} | "
                f"ctx:{h.context_pct}% gaps:{h.open_gaps} files:{h.files_touched}"
            )
            if h.level == "red":
                cp = create_checkpoint(h, "auto-watch-critical")
                print(f"  → Auto-checkpoint: {cp.name}")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n⏹ إيقاف المراقبة.")


def cmd_json(health: ContextHealth) -> None:
    print(json.dumps(health.as_dict(), ensure_ascii=False, indent=2))


# ─── نقطة الدخول ─────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SAHOOL Agent Session Governor — صحّة السياق وCheckpoint التلقائي"
    )
    parser.add_argument("--status", action="store_true", help="عرض بطاقة الصحّة")
    parser.add_argument("--status-line", action="store_true", help="سطر واحد (Claude statusLine)")
    parser.add_argument("--checkpoint", action="store_true", help="حفظ لقطة الجلسة")
    parser.add_argument("--watch", action="store_true", help="مراقبة مستمرّة")
    parser.add_argument("--json", action="store_true", help="إخراج JSON")
    parser.add_argument("--reason", default="manual", help="سبب الـcheckpoint")
    parser.add_argument("--interval", type=int, default=30, help="فترة المراقبة (ث)")
    args = parser.parse_args()

    if args.watch:
        cmd_watch(args.interval)
        return

    health = ContextHealth()

    if args.status_line:
        cmd_status_line(health)
    elif args.checkpoint:
        cmd_checkpoint(health, args.reason)
    elif args.json:
        cmd_json(health)
    else:
        cmd_status(health)


if __name__ == "__main__":
    main()
