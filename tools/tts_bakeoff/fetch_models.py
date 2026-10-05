"""تنزيلُ الأوزان — **منفصلٌ عن القياس**، ويُشغَّل حيث الشبكة مسموحة (جهازك أو بعد فتح النطاقات).

    python3 fetch_models.py --plan sources.json --dest models [--endpoint https://hf-mirror.com]

لكلّ ملفّ في ``sources.json``:
  • مستودع Hugging Face + **commit كامل** (لا فرع ولا وسم متحرّك) + اسم الملفّ، أو رابط GitHub Release.
  • ``trusted_sha256``: بصمةٌ تأتي من **المصدر الأصليّ** (صفحة الملفّ على huggingface.co أو صفحة
    الإصدار) — لا من المرآة. المرآةُ وسيلةُ نقلٍ فقط؛ لا تُغيّر الترخيص ولا تُثبت الأصالة.
  • ``published_git_blob_sha1``: لملفٍّ صغير بلا sha256 منشورة (ليس LFS، مثل ``vocab.txt`` و``config.yaml``):
    معرّفُ blob الذي ينشره المستودعُ عند **commit مثبّت** هويّةٌ منشورةٌ مُعنونةٌ بالمحتوى. تُحسب للملفّ
    المُنزَّل هويّتُه كما يحسبها ``git hash-object`` ويُرفض إن خالفت — **في كلّ تنزيل**، لا مرّةً واحدة
    بيد من نقلها. وإن وُجدت معها ``trusted_sha256`` وجب أن تطابق أيضاً. **حدٌّ معلن:** SHA-1 مكسورةٌ
    للتصادم المُختار، فالسلسلةُ تحمي من تبديلٍ لاحق لا من مستودعٍ زُرع فيه تصادمٌ عند ذلك الـcommit.

الضمانات: لا توكن يُرسَل (``token=False``)، والملفُّ الذي تخالف بصمتُه يُحذف ويُفشل التنزيل.
يكتب ``models/provenance.json`` (المصدر، commit، الخادم الفعليّ، البصمة، الترخيص المُعلن، الوقت)
**بعد كلّ ملفٍّ يجتاز التحقّق** لا في النهاية وحدها: انقطاعُ ملفٍّ كبير لا يُضيّع سجلَّ ما سبقه. والملفُّ
الموجودُ أصلاً بالبصمة نفسها لا يُنزَّل ثانيةً (``already_present``).
  • ``"extract": "zip"``: أرشيفٌ **اجتاز التحقّق** يُفكّ في مجلّده، وبصمةُ كلّ عضوٍ مستخرَج تُسجَّل
    ``derived_from`` بصمةِ الأرشيف — ثقةٌ مشتقّة لا منشورة. يُرفض العضوُ المطلق أو الذي فيه ``..`` أو
    الرابطُ الرمزيّ أو ما يقع خارج المجلّد بعد الحلّ (zip-slip)، **قبل** كتابة أيّ عضو.
لا يُدرِج شيئاً في أيّ صورة خدمة.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import stat
import urllib.request
import zipfile
from pathlib import Path

COMMIT = re.compile(r"^[0-9a-f]{40}$")
SHA1_HEX = re.compile(r"^[0-9a-f]{40}$")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_blob_sha1(path: Path) -> str:
    """هويّةُ git للمحتوى: SHA-1 لـ``blob <الطول>\\0`` ثمّ البايتات — ما يطبعه ``git hash-object``."""
    h = hashlib.sha1()  # noqa: S324 - هويّةُ git المنشورة نفسها؛ حدُّها مُعلنٌ في رأس الملفّ
    h.update(f"blob {path.stat().st_size}\0".encode())
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


def extract_zip(archive: Path, into: Path) -> dict[str, str]:
    """يفكّ أرشيفاً موثوقاً بعد فحص **كلّ** أعضائه أوّلاً؛ يُرجع ``{المسار النسبيّ: sha256}``."""
    root = into.resolve()
    with zipfile.ZipFile(archive) as zf:
        members = [m for m in zf.infolist() if not m.is_dir()]
        for m in members:
            name = m.filename
            if name.startswith(("/", "\\")) or ".." in Path(name).parts or ":" in name:
                raise SystemExit(f"{archive.name}: عضوٌ مرفوض (مسارٌ مطلق أو صاعد) {name!r}")
            if stat.S_ISLNK(m.external_attr >> 16):
                raise SystemExit(f"{archive.name}: رابطٌ رمزيّ داخل الأرشيف مرفوض {name!r}")
            if root not in (root / name).resolve().parents:
                raise SystemExit(f"{archive.name}: عضوٌ يقع خارج مجلّد الفكّ {name!r}")
        out = {}
        for m in members:
            target = root / m.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(m) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            out[m.filename] = sha256(target)
    return out


def _verified(path: Path, item: dict, blob: str | None) -> tuple[bool, str]:
    """``(مطابق، بصمة)`` — هويّةُ git أوّلاً إن أُعلنت، ثمّ sha256 الموثوقة إن أُعلنت."""
    if blob is not None and git_blob_sha1(path) != blob:
        return False, ""
    actual = sha256(path)
    return not (item.get("trusted_sha256") and actual != item["trusted_sha256"]), actual


def _write_provenance(dest: Path, records: dict) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    tmp = dest / "provenance.json.tmp"
    tmp.write_text(
        json.dumps(list(records.values()), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tmp.replace(dest / "provenance.json")


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
    previous = dest / "provenance.json"
    records = {
        f"{r.get('local_dir')}/{r.get('filename')}": r
        for r in (json.loads(previous.read_text(encoding="utf-8")) if previous.exists() else [])
    }
    for item in plan["files"]:
        blob = item.get("published_git_blob_sha1")
        if not item.get("trusted_sha256") and not blob:
            raise SystemExit(f"{item.get('filename')}: لا بصمةَ موثوقة من المصدر الأصليّ — لن يُنزَّل")
        if blob is not None:
            # الهويّةُ لا معنى لها إلّا داخل مستودعٍ عند commit مثبّت: رابطُ إصدارٍ أو فرعٌ متحرّك يُرفضان قبل التنزيل
            if not SHA1_HEX.match(str(blob)):
                raise SystemExit(
                    f"{item.get('filename')}: published_git_blob_sha1 غيرُ صالح {blob!r}"
                )
            if item.get("url") or not COMMIT.match(str(item.get("revision", ""))):
                raise SystemExit(
                    f"{item.get('filename')}: سلسلةُ git blob تتطلّب مستودعاً وcommit مثبّتاً (40 حرفاً)"
                )
        existing = dest / item["local_dir"] / item["filename"]
        already = (
            existing.is_file() and not existing.is_symlink() and _verified(existing, item, blob)[0]
        )
        path = (
            existing
            if already
            else (fetch_url(item, dest) if item.get("url") else fetch_hf(item, dest, args.endpoint))
        )
        if blob is not None:
            actual_blob = git_blob_sha1(path)
            if actual_blob != blob:
                path.unlink(missing_ok=True)
                raise SystemExit(
                    f"هويّةُ git مخالفة لـ{item['filename']}: المنشورة {blob} الفعليّة {actual_blob} — حُذف"
                )
        actual = sha256(path)
        if item.get("trusted_sha256") and actual != item["trusted_sha256"]:
            path.unlink(missing_ok=True)
            raise SystemExit(
                f"بصمةٌ مخالفة لـ{item['filename']}: الموثوقة {item['trusted_sha256']} الفعليّة {actual} — حُذف"
            )
        extracted = None
        if item.get("extract") is not None:
            if item["extract"] != "zip":
                raise SystemExit(
                    f"{item['filename']}: extract={item['extract']!r} غيرُ مدعوم (zip فقط)"
                )
            extracted = extract_zip(path, path.parent)
            for member, digest in extracted.items():
                print(f"  ↳ {member} {digest}  (مشتقّ من {actual[:16]})", flush=True)
        records[f"{item['local_dir']}/{item['filename']}"] = {
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
            "trust_basis": "git-blob-sha1@commit" if blob else "published-sha256",
            "git_blob_sha1": blob,
            "local_dir": item["local_dir"],
            "already_present": already,
            "extracted": extracted,
            "extracted_trust": "derived-from-verified-archive" if extracted else None,
            "fetched_at": dt.datetime.now(dt.UTC).isoformat(),
        }
        _write_provenance(dest, records)
        print(
            f"✓ {item['filename']} {actual[:16]}{' (موجودٌ مسبقاً)' if already else ''}", flush=True
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
