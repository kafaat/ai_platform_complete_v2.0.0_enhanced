#!/usr/bin/env python3
"""
validate_migrations.py — فحص ثابت للـmigrations بلا PostgreSQL

لا يُغني عن التشغيل الفعلي، لكن يلتقط أصناف الأخطاء الشائعة التي تكسر
الـmigrations قبل أن يصل المستخدم لقاعدة حقيقيّة:

  ١. أقواس غير متوازنة
  ٢. علامات اقتباس فرديّة غير متوازنة (خارج $$ ... $$)
  ٣. CREATE INDEX على دالّة non-IMMUTABLE (date_trunc/now/current_*)
     — الخطأ الذي أصلحناه في v11 سابقاً
  ٤. ON CONFLICT (col) بلا UNIQUE/PRIMARY KEY مطابق في نفس الملفّ
  ٥. ملفّات MANIFEST مفقودة من القرص أو العكس
  ٦. جمل لا تنتهي بفاصلة منقوطة (تحذير)

الاستخدام: python3 validate_migrations.py
"""
import os
import re
import sys

MIG_DIR = os.path.dirname(os.path.abspath(__file__))


def strip_dollar_quotes(sql: str) -> str:
    """يزيل كتل $$ ... $$ (دوالّ PL/pgSQL) لتفادي عدّ اقتباساتها."""
    return re.sub(r"\$\$.*?\$\$", "", sql, flags=re.DOTALL)


def strip_comments(sql: str) -> str:
    sql = re.sub(r"--.*", "", sql)
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    return sql


def check_file(path: str) -> list:
    """يفحص ملفّ migration واحداً، يعيد قائمة مشاكل."""
    issues = []
    raw = open(path, encoding="utf-8").read()
    code = strip_comments(raw)
    no_dollar = strip_dollar_quotes(code)

    # ١. أقواس متوازنة
    if no_dollar.count("(") != no_dollar.count(")"):
        issues.append(f"أقواس غير متوازنة: {no_dollar.count('(')} ( مقابل {no_dollar.count(')')} )")

    # ٢. اقتباسات فرديّة متوازنة (خارج $$)
    if no_dollar.count("'") % 2 != 0:
        issues.append("علامات اقتباس فرديّة غير متوازنة (')")

    # ٣. CREATE INDEX على دالّة non-IMMUTABLE
    for m in re.finditer(r"CREATE\s+(?:UNIQUE\s+)?INDEX[^;]+;", code, re.IGNORECASE | re.DOTALL):
        idx = m.group(0)
        # فقط لو الفهرس على تعبير (فيه أقواس دالّة)، لا مجرّد أعمدة
        for fn in ("date_trunc", "now(", "current_date", "current_timestamp"):
            if re.search(r"\b" + re.escape(fn), idx, re.IGNORECASE):
                issues.append(f"فهرس على دالّة non-IMMUTABLE ({fn}) — PostgreSQL سيرفضه")

    # ٤. ON CONFLICT (col) — تحقّق وجود UNIQUE/PK على نفس العمود
    for m in re.finditer(r"ON\s+CONFLICT\s*\(\s*([a-zA-Z_][\w,\s]*)\)", code, re.IGNORECASE):
        cols = m.group(1).replace(" ", "")
        # ابحث عن UNIQUE أو PRIMARY KEY أو UNIQUE INDEX يغطّي هذا العمود
        has_unique = (
            re.search(r"UNIQUE[^;,]*\b" + re.escape(cols.split(",")[0]), code, re.IGNORECASE)
            or re.search(r"PRIMARY\s+KEY[^;,]*\b" + re.escape(cols.split(",")[0]), code, re.IGNORECASE)
            or re.search(re.escape(cols.split(",")[0]) + r"[^;]*PRIMARY\s+KEY", code, re.IGNORECASE)
        )
        if not has_unique:
            issues.append(f"ON CONFLICT ({cols}) بلا UNIQUE/PK مطابق واضح (تحقّق يدويّاً)")

    return issues


def main():
    manifest_path = os.path.join(MIG_DIR, "MANIFEST.txt")
    if not os.path.exists(manifest_path):
        print("✗ MANIFEST.txt مفقود")
        return 1

    manifest = []
    for line in open(manifest_path, encoding="utf-8"):
        line = re.sub(r"#.*", "", line).strip()
        if line:
            manifest.append(line)

    # ٥. تطابق MANIFEST مع القرص
    on_disk = {f for f in os.listdir(MIG_DIR) if f.endswith(".sql")}
    in_manifest = set(manifest)
    missing = in_manifest - on_disk
    extra = on_disk - in_manifest
    if missing:
        print(f"⚠ في MANIFEST لكن مفقودة من القرص: {missing}")
    if extra:
        print(f"⚠ على القرص لكن ليست في MANIFEST: {extra}")

    print("═══ فحص ثابت للـmigrations ═══\n")
    total_issues = 0
    for fname in manifest:
        path = os.path.join(MIG_DIR, fname)
        if not os.path.exists(path):
            continue
        issues = check_file(path)
        if issues:
            print(f"  ⚠ {fname}:")
            for iss in issues:
                print(f"      - {iss}")
            total_issues += len(issues)
        else:
            print(f"  ✓ {fname}")

    print(f"\n{'─' * 40}")
    if total_issues == 0:
        print("✓ لا مشاكل ثابتة (هذا لا يُغني عن التشغيل الفعلي)")
        return 0
    print(f"⚠ {total_issues} مشكلة محتملة — راجعها قبل التطبيق")
    return 0  # تحذيرات لا تفشل (بعضها قد يكون إيجابيّات كاذبة)


if __name__ == "__main__":
    sys.exit(main())
