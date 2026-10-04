"""تنزيلُ الأوزان — **منفصلٌ عن القياس**، ويُشغَّل حيث الشبكة مسموحة (جهازك أو بعد فتح النطاقات).

    python3 fetch_models.py --plan sources.json --dest models [--endpoint https://hf-mirror.com]

لكلّ ملفّ في ``sources.json``:
  • مستودع Hugging Face + **commit كامل** (لا فرع ولا وسم متحرّك) + اسم الملفّ، أو رابط GitHub Release.
  • ``trusted_sha256``: بصمةٌ تأتي من **المصدر الأصليّ** (صفحة الملفّ على huggingface.co أو صفحة
    الإصدار) — لا من المرآة. المرآةُ وسيلةُ نقلٍ فقط؛ لا تُغيّر الترخيص ولا تُثبت الأصالة.

الضمانات: لا توكن يُرسَل (``token=False``)، والملفُّ الذي تخالف بصمتُه يُحذف ويُفشل التنزيل.
يكتب ``models/provenance.json`` (المصدر، commit، الخادم الفعليّ، البصمة، الترخيص المُعلن، الوقت).
لا يُدرِج شيئاً في أيّ صورة خدمة.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import urllib.request
from pathlib import Path

COMMIT = re.compile(r"^[0-9a-f]{40}$")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_hf(item: dict, dest: Path, endpoint: str | None) -> Path:
    from huggingface_hub import hf_hub_download

    if not COMMIT.match(item["revision"]):
        raise SystemExit(
            f"{item['repo_id']}/{item['filename']}: revision يجب أن يكون commit كاملاً (40 حرفاً)"
        )
    return Path(
        hf_hub_download(
            repo_id=item["repo_id"],
            filename=item["filename"],
            revision=item["revision"],
            local_dir=dest / item["local_dir"],
            endpoint=endpoint,
            token=False,
        )
    )


def fetch_url(item: dict, dest: Path) -> Path:
    target = dest / item["local_dir"] / item["filename"]
    target.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(item["url"], target)  # noqa: S310 - رابطٌ مُعلن في الخطّة
    return target


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--dest", default="models")
    ap.add_argument(
        "--endpoint", default=None, help="خادم Hugging Face بديل (مثل مرآة) — وسيلة نقل فقط"
    )
    args = ap.parse_args()

    dest = Path(args.dest)
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    provenance = []
    for item in plan["files"]:
        if not item.get("trusted_sha256"):
            raise SystemExit(f"{item.get('filename')}: لا بصمةَ موثوقة من المصدر الأصليّ — لن يُنزَّل")
        path = fetch_url(item, dest) if item.get("url") else fetch_hf(item, dest, args.endpoint)
        actual = sha256(path)
        if actual != item["trusted_sha256"]:
            path.unlink(missing_ok=True)
            raise SystemExit(
                f"بصمةٌ مخالفة لـ{item['filename']}: الموثوقة {item['trusted_sha256']} الفعليّة {actual} — حُذف"
            )
        provenance.append(
            {
                **{
                    k: item.get(k)
                    for k in (
                        "repo_id",
                        "revision",
                        "filename",
                        "url",
                        "license",
                        "license_source",
                        "purpose",
                    )
                },
                "served_by": item.get("url") or args.endpoint or "https://huggingface.co",
                "path": str(path),
                "sha256": actual,
                "fetched_at": dt.datetime.now(dt.UTC).isoformat(),
            }
        )
        print(f"✓ {item['filename']} {actual[:16]}")
    (dest / "provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
