#!/usr/bin/env python3
"""
runtime_truth_report.py — جامع الحقيقة التشغيليّة (يُشغَّل على جهازك بعد النشر).

المراجعة (خطّة ما بعد التشغيل): بعد make verify، لا نضيف ثقة — نقيسها. هذا
السكربت يجمع "ما حدث فعليّاً" في تقرير واحد (لا logs، لا CI output). يقارن
الواقع الحيّ بما يدّعيه evidence.json، ويبرز أخطر نوع: silent success.

⚠️ يُشغَّل على جهازك (يحتاج postgres حيّ + الخدمات قيد التشغيل). في بيئة
بلا بنية تحتيّة، يُبلّغ بصدق "غير متاح" بدل تخمين.

الاستخدام:
    python3 scripts_v9/runtime_truth_report.py > runtime_truth_report.md
"""

import json
import os
import subprocess
from datetime import UTC, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _section(title):
    return f"\n## {title}\n"


def _try(cmd, timeout=30):
    """يشغّل أمراً ويُرجع (نجح، المخرج). لا يرمي — يلتقط الفشل كحقيقة."""
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout, cwd=ROOT
        )
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except Exception as e:
        return False, str(e)


def collect():
    lines = []
    lines.append("# Runtime Truth Report — SAHOOL v9")
    lines.append(f"\nالوقت: {datetime.now(UTC).isoformat()}")
    lines.append("\n> القاعدة: نقيس الثقة لا نضيفها. هذا ما حدث فعليّاً، لا ما نأمله.")

    # ─── ١. حقيقة الخدمات (هل تعمل؟) ───
    lines.append(_section("١. حقيقة الخدمات (Service Health)"))
    has_docker, _ = _try("docker info", 10)
    if not has_docker:
        lines.append("- ⚠️ docker غير متاح هنا — شغّل على جهازك بعد `make up`.")
    else:
        ok, out = _try("docker compose -f docker-compose.v9.yml ps --format json", 20)
        lines.append(f"- docker compose ps: {'✓ نُفّذ' if ok else '✗ فشل'}")
        if out:
            lines.append(f"```\n{out[:1500]}\n```")

    # ─── ٢. حقيقة RLS (أخطر قياس — العزل الفعلي) ───
    lines.append(_section("٢. حقيقة عزل المستأجرين (RLS — الأهمّ)"))
    db_url = os.getenv("RLS_TEST_URL") or os.getenv("DATABASE_URL")
    if not db_url:
        lines.append("- ⚠️ DATABASE_URL/RLS_TEST_URL غير مضبوط. للقياس الحقيقي:")
        lines.append("  ```")
        lines.append("  export RLS_TEST_URL='postgresql://sahool_user@localhost/sahool'")
        lines.append('  psql "$RLS_TEST_URL" -f scripts_v9/test_tenant_isolation.sql')
        lines.append("  ```")
        lines.append(
            "- 🔑 كلمة المرور **لا تُكتب في سطر الأوامر**: `~/.pgpass` (صلاحية `0600`) "
            "أو `PGPASSWORD` من مخزن أسرار — سطرُ الأوامر يُقرأ من `ps` ويُحفظ في التاريخ."
        )
        lines.append(
            "- ⚠️ **حرج**: شغّل كـnon-superuser (sahool_user)، وإلّا RLS يُتجاوَز "
            "ويعطي نجاحاً زائفاً (silent success — أخطر فشل)."
        )
    else:
        ok, out = _try(
            f'psql "{db_url}" -v ON_ERROR_STOP=1 -f scripts_v9/test_tenant_isolation.sql', 60
        )
        verdict = "✅ عزل سليم (لا تسريب)" if ok else "🔴 فشل العزل — تسريب محتمل!"
        lines.append(f"- نتيجة اختبار العزل: {verdict}")
        # ابحث عن إشارات التسريب الصريحة
        if "تسريب" in out or "IDOR" in out or "EXCEPTION" in out:
            lines.append("- 🔴 **انتباه**: المخرج يذكر تسريباً/استثناءً:")
        lines.append(f"```\n{out[-2000:]}\n```")

    # ─── ٣. مقارنة الواقع بـevidence (كشف silent success) ───
    lines.append(_section("٣. الواقع مقابل evidence.json (كشف الانحراف)"))
    ev_path = os.path.join(ROOT, "build", "evidence.json")
    if os.path.exists(ev_path):
        ev = json.load(open(ev_path))
        lines.append(f"- evidence overall: **{ev.get('overall')}**")
        inv = ev.get("invariants", {})
        live_pending = [k for k, v in inv.items() if v == "requires_live"]
        lines.append(f"- invariants بنيويّة مُثبَتة: {sum(1 for v in inv.values() if v is True)}")
        if live_pending:
            lines.append(
                f"- ⏳ **لم تُقَس حيّاً بعد** (يجب تأكيدها من القسم ٢): {', '.join(live_pending)}"
            )
            lines.append("  - حتّى تُقاس، هذه ادّعاءات بنيويّة لا حقيقة تشغيليّة.")
    else:
        lines.append("- ⚠️ لا build/evidence.json — شغّل `make ci` أوّلاً.")

    # ─── ٤. القرار المعماري (الإطار — يملؤه الإنسان من القياس) ───
    lines.append(_section("٤. القرار المعماري (يُملأ من القياس أعلاه)"))
    lines.append("اختر **واحداً** بناءً على الأقسام ١-٣ (لا تخمين):")
    lines.append("")
    lines.append(
        "- 🟢 **APPROVED FOR SCALE**: العزل سليم + الخدمات صحّيّة + "
        "لا انحراف. → انتقل لـLevel 2 (PostGIS/NDVI)."
    )
    lines.append(
        "- 🟡 **STABLE BUT NOT CLOSED**: يعمل لكن فجوة 1-3. → إصلاح محدود فقط (لا إعادة تصميم)."
    )
    lines.append(
        "- 🔴 **ARCHITECTURE INVALID**: العزل غير مضمون. → جمّد الميزات + أعد تصميم طبقة واحدة."
    )
    lines.append("")
    lines.append(
        "> ملاحظة صدق: هذا التقرير **يجمع** الحقيقة. القرار قرارك أنت "
        "بناءً على ما قِيس فعليّاً — لا يدّعي السكربت حكماً لم يقِسه."
    )

    return "\n".join(lines)


if __name__ == "__main__":
    print(collect())
