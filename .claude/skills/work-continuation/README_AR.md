# UWRP v3 — بروتوكول عام لاستمرار الأعمال واستئنافها

**مقصوده:** Skill خفيفة توحّد طريقة استعادة أعمال طويلة ومتعددة الوكلاء في مشاريع البرمجة والتحليل والتوثيق. لا تحتاج إلى قاعدة بيانات أو منصة جديدة؛ لكنها لا تعد بمنع جميع أخطاء التشغيل الموزع إذا لم تكن لدى المشروع آليات فعلية لهذه الضمانات.

## الاستخدام في أي محادثة

> تابع من آخر نقطة توقف المثبتة بالأدلة وطبّق Skill `work-continuation` (UWRP v3)، واحتفظ بملفات الحالة والبصمات والنسخة الدائمة المصرح بها، دون تكرار عملية مثبتة أو تجاوز صلاحيات المشروع.

للبدء الطويل `prompts/START_LONG_WORK_AR.md`، وللاستئناف `prompts/RESUME_AR.md`، لتسليم الوكيل `prompts/HANDOFF_TO_AGENT_AR.md`، ولأي فعل خارجي `prompts/EXTERNAL_ACTION_AR.md`.

## التثبيت

- **Claude Code (مشروع):** انسخ مجلد `work-continuation` إلى `.claude/skills/work-continuation/` في مستودع المشروع، عبر PR يخضع لبواباته. لا تنسخ `state.json` أو logs إلى مصدر المشروع.
- **Claude Code (شخصي):** ثبّت Skill في موقع skills الشخصي وفق دليل Claude Code لإصدارك؛ حاويات cloud المؤقتة قد لا تحتفظ بنسخها المحلية بعد إعادة التشغيل.
- **claude.ai Skills:** ارفع ملف ZIP المناسب من إعدادات Skills إذا كانت الميزة متاحة بحسابك، وتحقق من تفعيلها. لا يعني نقل الـZIP تلقائياً أنه وُثّق في GitHub.
- **أي وكيل آخر:** يمكنه قراءة `SKILL.md` والقوالب وفق طريقة تحميل المهارات في برنامجه. لا تفترض التشغيل التلقائي دون دعم Agent Skills.
- **قواعد المستودع:** حافظة المشروع مثل `CLAUDE.md` / `AGENTS.md` تظل مرجع طريقة العمل والبوابات. النص المقترح للإشارة في `examples/AGENT_GUIDANCE_SNIPPET.md`.

## ما الجديد عن v2.1؟

1. مستويات عبء L0/L1/L2، فلا تطبق الإجراءات الثقيلة على مهمة صغيرة.
2. فصل state كادعاءات عن real-time source truth.
3. صلاحية نتائج مبنية على dependencies وbase HEAD/merge-base وpolicy digest.
4. وصف صريح لتعذر exactly-once عبر الأنظمة الخارجية دون دعم المزوّد.
5. أقفال طبقية مع Fencing/CAS في النظام الهدف للأعمال الخطرة.
6. حدث completion ثم snapshot ذرية؛ واضح أن الحاوية المؤقتة ليست مستودعاً دائماً.
7. عزل النسخ الخاصة عن تاريخ المستودعات العامة/التي تمسح كل الفروع.
8. فصل Prompt قصير عن مراجع Skill، مع قوالب وفحص محلي قرائي.
9. نسخة v2.1 الأصلية محفوظة ضمن `references/PROTOCOL_v2_1_ORIGINAL.md` بنفس SHA-256.

## الملفات المهمة

| الملف | الوظيفة |
|---|---|
| `SKILL.md` | تعليمات مختصرة تنطبق على العمل طويل الأجل فقط |
| `references/RESEARCH_AND_DECISIONS.md` | المراجع الرسمية ومصفوفة التصميم |
| `references/EVALUATION_PLAN.md` | 14 سيناريو سلوك للوكيل معاييرها مقترحة ولم تُشغل |
| `references/VALIDITY_AND_TESTING.md` | صلاحية النتائج والاختبارات المجزأة |
| `references/EXTERNAL_ACTIONS_AND_LOCKS.md` | إجراءات side-effects والقفل |
| `references/SECURITY_STORAGE_AND_HANDOFF.md` | ثقة ملفات الحالة والنسخ والاحتفاظ |
| `templates/state.example.json` | شكل حالة صغيرة بصياغة اصطناعية لا أسرار فيها |
| `templates/HANDOFF.template.md` | تسليم قابل للفحص المستقل |
| `templates/shard-plan.example.json` و`templates/shard-receipt.example.json` | خطة اختبارات وإيصالات |
| `templates/external-action.example.json` | سجل إجراء خارجي مع حالة المصالحة |
| `templates/retention-policy.example.json` | سياسة مساحة/احتفاظ تُخصص |
| `scripts/validate_package.py` | فحص ملف skill وقوالب وchecksum بلا network أو git write |

## فحص الحزمة (محلي وقرائي)

```bash
python3 work-continuation/scripts/validate_package.py
python3 -m unittest discover -s work-continuation/tests -v
```

**لا تشمل الحزمة** أداة آلية لتشغيل `preflight.sh` على أي مستودع، ولا تنفيذ إنشاء GitHub repo، ولا قفلاً موزعاً جاهزاً للإنتاج. كلها تحتاج تكاملاً خاصاً بالمشروع وسياساته وتفويضاً مستقلاً.

## توصية التخزين

في المشاريع ذات استنسـاخات أو حاويات مؤقتة، احتفظ بملف الحالة وHANDOFF خارج شجرة المصدر، وانشر **عند التفويض فقط** نسخة منقحة صغيرة إلى مخزن GitHub خاص مستقل بعد التحقق البعيد. فشل النسخ = `BACKUP_PENDING`. لا تضف فروع backup بلا حدود إلى مستودع يفحص تاريخ كل الفروع.
