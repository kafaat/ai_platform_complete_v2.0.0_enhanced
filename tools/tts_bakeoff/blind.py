"""يخلط مقاطع التشغيلات الناجحة تحت معرّفاتٍ عشوائيّة لتقييمٍ أعمى.

    python3 blind.py runs/piper-… runs/silma-… --out review-001

يقبل التشغيلَ فقط إن كان ``harness_status == ok`` و``network_isolation == PROVEN`` (أو صرّحتَ
``--allow-unverified-network`` فيُوسَم الناتج بذلك)، ويقبل من كلِّ تشغيلٍ **المقاطعَ المُسجَّلة في
result.json وحدها** بعد مطابقة بصمتها. ملفٌّ في ``wav/`` لم يُسجَّل، أو تغيّرت بايتاته، يُرفض.

المُخرَج: ``audio/`` و``rating_sheet.csv`` للمراجعين، و``KEY_DO_NOT_SHARE.json`` للمنسّق وحده.

``--asr-hints DIR…`` (اختياريّ): يضيف عموداً بما رفعه فرزُ ASR لكلّ مقطع — الحالة، والمحتوى غير المغطّى، وأوّل
أسباب العلَم — **مطابَقاً ببصمة المقطع** (تلميحٌ لمقطعٍ آخر أو قديم يُرفض). مساعدٌ لا حكم: ``score.py`` لا يقرؤه،
وقد يُخطئ ASR أو يُحيّز المراجع (الانحياز إلى التلميح)؛ يُسجَّل في المفتاح أنّ التلميح عُرض.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import secrets
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

COLUMNS = [
    "reviewer_id",
    "blind_id",
    "sentence_id",
    "synthetic_example",
    "النص المكتوب",
    "الحقائق الحرجة (يجب أن تُسمع حرفيّاً)",
    "كلمات منطوقة خطأ (اكتبها)",
    "خطأ حرج؟ (نعم/لا) — رقم أو وحدة أو جرعة أو مدّة تغيّرت، أو نفيٌ سقط/التبس",
    "وصف الخطأ الحرج",
    "الوضوح (1-5)",
    "الطبيعيّة (1-5)",
    "ملاحظات",
]


def load_run(
    run: Path, allow_unverified: bool, corpus_sha: str
) -> tuple[dict, list[tuple[str, Path]]]:
    result = json.loads((run / "result.json").read_text(encoding="utf-8"))
    recorded_corpus = result.get("environment", {}).get("corpus_sha256")
    if recorded_corpus != corpus_sha:
        raise SystemExit(
            f"مرفوض {run}: قِيس على نصوصٍ بصمتُها {recorded_corpus} لا {corpus_sha} — "
            "الحقائقُ الحرجة في الورقة لن تطابق ما نُطق"
        )
    if result.get("harness_status") != "ok":
        raise SystemExit(
            f"مرفوض {run}: harness_status={result.get('harness_status')} stage={result.get('stage')}"
        )
    isolation = result.get("network_isolation")
    if isolation != "PROVEN" and not allow_unverified:
        raise SystemExit(
            f"مرفوض {run}: network_isolation={isolation} (استعمل --allow-unverified-network صراحةً)"
        )
    clips = []
    recorded = {r["id"]: r for r in result.get("sentences", []) if r.get("ok")}
    for sid, row in recorded.items():
        path = run / "wav" / f"{sid}.wav"
        if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise SystemExit(f"مرفوض {run}: بصمةُ {path.name} لا تطابق result.json")
        clips.append((sid, path))
    strays = {p.stem for p in (run / "wav").glob("*.wav")} - set(recorded)
    if strays:
        raise SystemExit(f"مرفوض {run}: مقاطع غير مُسجَّلة في result.json: {sorted(strays)}")
    return result, clips


HINT_COLUMN = "تنبيهٌ آليّ من ASR (مساعدٌ لا حكم — قد يُخطئ؛ احكم بأذنك)"


def load_hints(dirs: list[str]) -> dict:
    """(run_id, sentence_id) → (بصمةُ المقطع، نصُّ التلميح)."""
    hints = {}
    for d in dirs:
        doc = json.loads((Path(d) / "asr_screen.json").read_text(encoding="utf-8"))
        for c in doc["clips"]:
            parts = [c["screen"]]
            if c.get("uncovered_content"):
                parts.append("غيرُ مغطّى: " + "، ".join(c["uncovered_content"]))
            if c.get("flags"):
                parts.append("علَم: " + c["flags"][0][:120])
            hints[(doc["run_id"], c["sentence_id"])] = (c["clip_sha256"], " · ".join(parts))
    return hints


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--corpus", default=str(HERE / "corpus.tsv"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--allow-unverified-network", action="store_true")
    ap.add_argument(
        "--asr-hints", nargs="*", default=[], help="مجلّداتُ asr_screen — تلميحٌ مساعدٌ في عمودٍ منفصل"
    )
    args = ap.parse_args()

    out = Path(args.out)
    if out.exists():
        print(f"مرفوض: {out} موجود — كلُّ جولة تقييمٍ في مجلّدٍ جديد", file=sys.stderr)
        return 5
    corpus_bytes = Path(args.corpus).read_bytes()
    corpus_sha = hashlib.sha256(corpus_bytes).hexdigest()
    corpus = {
        row["id"]: row
        for row in csv.DictReader(corpus_bytes.decode("utf-8").splitlines(), delimiter="\t")
    }

    items, sources = [], []
    for run in map(Path, args.runs):
        result, clips = load_run(run, args.allow_unverified_network, corpus_sha)
        sources.append(
            {
                "run_id": result["run_id"],
                "engine": result["engine"],
                "network_isolation": result["network_isolation"],
                "clips": len(clips),
            }
        )
        items += [(result["engine"], result["run_id"], sid, path) for sid, path in clips]
    if len({s["engine"] for s in sources}) < 2:
        print("تنبيه: محرّكٌ واحد فقط — هذا فحصٌ للإجراء، لا مقارنة.", file=sys.stderr)
    hints = load_hints(args.asr_hints)
    random.SystemRandom().shuffle(items)

    (out / "audio").mkdir(parents=True)
    key, sheet = {}, []
    for engine, run_id, sid, path in items:
        blind = secrets.token_hex(5)
        shutil.copyfile(path, out / "audio" / f"{blind}.wav")
        key[blind] = {
            "engine": engine,
            "run_id": run_id,
            "sentence_id": sid,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        row = corpus[sid]
        entry = {
            "blind_id": blind,
            "sentence_id": sid,
            "synthetic_example": row["synthetic_example"],
            "النص المكتوب": row["text"],
            "الحقائق الحرجة (يجب أن تُسمع حرفيّاً)": row["critical_facts"],
        }
        if args.asr_hints:
            hint = hints.get((run_id, sid))
            if hint and hint[0] != key[blind]["sha256"]:
                raise SystemExit(
                    f"مرفوض: تلميحُ ASR لـ{run_id}/{sid} على مقطعٍ بصمتُه {hint[0][:12]}… لا {key[blind]['sha256'][:12]}…"
                )
            entry[HINT_COLUMN] = hint[1] if hint else "لم يُفرَز"
        sheet.append(entry)
    with (out / "rating_sheet.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS + ([HINT_COLUMN] if args.asr_hints else []))
        writer.writeheader()
        writer.writerows(sheet)
    (out / "KEY_DO_NOT_SHARE.json").write_text(
        json.dumps(
            {
                "corpus_sha256": corpus_sha,
                "sources": sources,
                "clips": key,
                "machine_hints": {
                    "shown_to_reviewers": bool(args.asr_hints),
                    "asr_dirs": args.asr_hints,
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"clips": len(sheet), "sources": sources}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
