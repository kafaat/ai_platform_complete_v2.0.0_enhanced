#!/usr/bin/env bash
# تفعيل `git rerere` لهذا المستودع — DETERMINISTIC-GENERATION-AND-MERGE-SAFETY-01 (L4)
#
# `rerere` (reuse recorded resolution) يحفظ **كيف** حُلّ تعارضٌ ما، ويُعيد تطبيق الحلّ
# نفسه تلقائيّاً حين يتكرّر التعارض عينه. وقيمته هنا محدّدة ومقيسة: ملفّات الدماغ
# الأربعة تتعارض على كلّ إعادة تأسيس، وحلّها واحدٌ دائماً (أبقِ الجانبين). فبلا rerere
# يُعاد الحلّ يدويّاً في كلّ مرّة، وهو بالضبط المسار الذي ضاعت فيه خمس قطع عمل سابقاً.
#
# **ثلاثة حدود تُقال قبل الاستعمال، لا بعده:**
#
# ① **إعداد محلّيّ لكلّ نسخة.** لا يمكن فرضه بالتزام: `.git/config` ليس متعقَّباً،
#    وسجلّ الحلول في `.git/rr-cache` لا يُدفَع. فهذا سكربت **يُشغَّل**، لا ملفّ يُقرأ.
#
# ② **لا يصلح بوّابةَ CI.** CI يبدأ من نسخة نظيفة بلا `rr-cache`، فـ«rerere معطَّل»
#    هناك حقيقةٌ بنيويّة لا عيب إنتاجيّ. حارسٌ يُفشِل CI على غيابه يُبلِّغ عن سؤال
#    لم يطرحه.
#
# ③ **حلٌّ خاطئ يُعاد تطبيقه بإخلاص.** إن حُلّ تعارضٌ خطأً ورُصِد، يجب مسح السجلّ
#    (`git rerere forget <path>` أو حذف `.git/rr-cache`) وإلّا عاد الخطأ في كلّ مرّة.
#
# `--local` لا `--global` عمداً: تفعيله عالميّاً يُغيّر سلوك كلّ مستودعات المستخدم
# بقرارٍ اتُّخذ في مستودعٍ واحد.
#
# idempotent: تشغيله مرّتين لا يُغيّر شيئاً ولا يفشل.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

git config --local rerere.enabled true
# `autoupdate` يُفهرِس الحلّ المُعاد تطبيقه بدل تركه في الشجرة غير مُفهرَس. بدونه
# يبدو التعارض «محلولاً» بينما `git status` ما زال يعدّه غير مُدرَج — وهو نفس فخّ
# ترتيب العمليّات الذي أضاع العمل في `MERGE-RESOLUTION-BY-HAND-LOSES-WORK-01`.
git config --local rerere.autoupdate true

# تحقّق بعد الكتابة لا قبلها: `git config` قد ينجح صامتاً على ملفّ للقراءة فقط.
test "$(git config --local --bool rerere.enabled)" = "true"
test "$(git config --local --bool rerere.autoupdate)" = "true"

echo "✓ rerere مُفعَّل لـ$(git rev-parse --show-toplevel)"
echo "  الحلول تُحفَظ في .git/rr-cache (محلّيّ، لا يُدفَع)."
echo "  إن أُعيد تطبيق حلّ خاطئ: git rerere forget <path>"
