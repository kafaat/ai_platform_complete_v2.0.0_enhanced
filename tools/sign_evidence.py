#!/usr/bin/env python3
"""
sign_evidence.py — توقيع evidence.json (Build Attestation — اختياري، إنتاجي).

المراجعة 15: دليل موقّع لا يُعدَّل صامتاً. يعيد استخدام مفتاح RS256 الخاصّ
(نفس بنية JWT_PRIVATE_KEY). اختياري — الـhash (sha256) يكفي للحماية الأساسيّة؛
التوقيع يُثبت المصدر (لـCI الإنتاجي). يحتاج cryptography + مفتاح خاصّ.
"""
import sys
from pathlib import Path

EV = Path("build/evidence.json")
KEY = Path("keys/ci_private.pem")  # أو JWT_PRIVATE_KEY


def main():
    if not EV.exists():
        print("✗ build/evidence.json غير موجود — شغّل make report أوّلاً")
        return 1
    if not KEY.exists():
        print(f"⚠ {KEY} غير موجود — التوقيع اختياري. الـhash (sha256) كافٍ "
              "للحماية الأساسيّة. لتوليد مفتاح: scripts_v9/generate_jwt_keys.sh")
        return 0
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
    except ImportError:
        print("✗ cryptography غير متاح — ثبّته للتوقيع (الـhash يعمل بدونه)")
        return 1
    data = EV.read_bytes()
    pk = serialization.load_pem_private_key(KEY.read_bytes(), password=None)
    sig = pk.sign(data, padding.PKCS1v15(), hashes.SHA256())
    Path("build/evidence.json.sig").write_bytes(sig)
    print("✓ وُقّع: build/evidence.json.sig")
    return 0


if __name__ == "__main__":
    sys.exit(main())
