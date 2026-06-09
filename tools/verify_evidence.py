#!/usr/bin/env python3
"""verify_evidence.py — تحقّق توقيع evidence.json (اختياري، إنتاجي)."""
import sys
from pathlib import Path


def main():
    ev = Path("build/evidence.json")
    sig = Path("build/evidence.json.sig")
    pub = Path("keys/ci_public.pem")
    # أوّلاً: تحقّق hash (دائماً متاح، رخيص)
    sha = Path("build/evidence.json.sha256")
    if ev.exists() and sha.exists():
        import hashlib
        actual = hashlib.sha256(ev.read_bytes()).hexdigest()
        if actual != sha.read_text().strip():
            print("✗ hash لا يطابق — evidence عُدّل!")
            return 1
        print("✓ hash مطابق (لم يُعدَّل)")
    # ثانياً: تحقّق التوقيع (إن توفّر)
    if not (sig.exists() and pub.exists()):
        print("⚠ لا توقيع/مفتاح عامّ — تحقّق الـhash كافٍ للحماية الأساسيّة")
        return 0
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        pk = serialization.load_pem_public_key(pub.read_bytes())
        pk.verify(sig.read_bytes(), ev.read_bytes(), padding.PKCS1v15(), hashes.SHA256())
        print("✓ EVIDENCE VERIFIED (توقيع صالح)")
        return 0
    except Exception as e:
        print(f"✗ توقيع غير صالح: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
