# قفل تبعيّات Python (Dependency Locking)

معالجة فجوة سلسلة الإمداد التي رصدها تدقيق خارجيّ: ملفّات `requirements*.txt`
تستخدم نطاقات (`>=`/`<`) فيختلف الـbuild بين يومٍ وآخر. القفل يُثبّت النسخ
المُحلَّلة بالكامل (transitive + hashes) للمسار الحرج.

## لماذا الأداة لا الأقفال المُلتزَمة سلفاً

القفل حسّاس لإصدار Python والمنصّة. يجب توليده في **بيئة الهدف ذاتها**
(CI = `ubuntu-24.04` / Python 3.12)، لا في بيئة مطوّر مختلفة، وإلّا انجرفت
النسخ. لذا نشحن الأداة المُعاد-إنتاجها، وتُولَّد الأقفال وتُلتزَم من CI/حاوية مطابقة.

## الاستخدام

```bash
scripts/deps/lock.sh          # يولّد <req>.lock بجانب كلّ هدف
scripts/deps/lock.sh --check  # يفشل إن انجرف قفل عن مصدره (لبوّابة CI)
```

الأهداف (المسار الحرج الذي تحجبه بوّابة `pip-audit` — انظر `CLAUDE.md`):
`services/sahool-platform/api/requirements.txt` ·
`services/auth/requirements.txt` · `services/guardrails-engine/requirements.txt` ·
`requirements_real.txt`.

## خطوات الإكمال (لم تُنفَّذ بعد — تتطلّب بناءً فعليّاً)

1. توليد الأقفال في CI والتزامها (`*.lock`).
2. تعديل `Dockerfile` لكلّ خدمة ليُثبّت من `requirements.lock` (`uv pip install -r … --require-hashes`).
3. إضافة وظيفة CI تشغّل `scripts/deps/lock.sh --check` لمنع الانجراف.

حتى تكتمل هذه الخطوات لا تكون عمليّات البناء مقفولة فعليّاً — الأداة هي البداية
المُعاد-إنتاجها فقط.
