# قرارات تنتظر المالك — حصيلة أسطول الإصلاح 2026-10-26

أسطولٌ من 26 وكيلاً عمل على الفجوات المفتوحة القابلة للإصلاح بالكود تحت التجميد (لا Railway ولا قاعدة بيانات ولا هجرات). ما يلي هو ما **لا يُغلَق بلا قرارك**؛ لكلّ بندٍ مصدرُه والخيار الذي توصي به وثائقُ المستودع. القرارات الزراعيّة وتفويضات GATE-01 لم يتّخذها الوكيل عنك.

| # | الفجوة | السؤال | توصية المستودع | المصدر |
|---|---|---|---|---|
| 1 | EFFECTIVE-RAIN-MONTHLY-FORMULA-ON-DAILY-RAIN-01 | أيّ قاعدةٍ للمطر الفعّال تحلّ محلّ USDA-SCS الشهريّة للنداءات الخمسة اليوميّة؟ | (ب) FAO-56 eq.85 مع عتبةٍ تُسمّيها ومصدرها | `owner_decisions_20261025.md:70-81` |
| 2 | DEPLETION-FRACTION-REGIONAL-CALIBRATION-NOT-RECONCILED-01 | متى يحلّ `raw_fraction` الإقليميّ محلّ `p` جدول FAO-56؟ وهل يبقى تعديل ETc والقصّ؟ ومعه تفويض GATE-01 لـ`run_water_ledger_once` | (ج) للمحاصيل الغائبة عن الجدول وحدها، `field_verified` | `owner_decisions_20261025.md:179-195` |
| 3 | PARALLEL-TAW-AND-KC-TABLES-DISAGREE-01 | هل يأخذ محرّك WOFOST الجداولَ القانونيّة؟ مقيسٌ دون اتّصال: الطمي 180⇒150 مم/م، المحصول البعليّ −17%…+38%، الريّ −17%…+23%؛ ومعه ربطُ أسماء المحاصيل (قمح صلب⇒`wheat.yaml`، خضروات⇒`GENERIC_STAGE_KC`…) | (ب) بعد جدولِ قبل/بعد | `owner_decisions_20261025.md:84-95` |
| 4 | FERTIGATION-EC-GUARD-HAS-NO-PRODUCER-01 | قبل مرحلة `FertigationState`: هل يظهر غيابُ EC نتيجةً غيرَ حاجبة `fertigation_ec_unmeasured`؟ | نعم (غير حاجبة) | `owner_decisions_20261025.md` ~97-109 |
| 5 | REPORT2-C04-QUEUED-PUSH-RECEIPTS-HAVE-NO-CONSUMER-01 | إعادةُ إرسال / إلغاء / انتهاء للإيصالات `queued`؟ وهل يُسجَّل الانتهاء `failed` برمزٍ مستقلّ (بلا هجرة)؟ | انظر الوثيقة | `docs/architecture/decisions_pending/REPORT2-C04-…md` |
| 6 | SUP-08-DEVICE-COMMAND-SIGNATURE-UNBOUND-TO-DEVICE-01 | تفويضُ GATE-01 لـ`send_mqtt_command` مربوطٌ ببايتات رقعة v2 مُعادٍ اشتقاقُها (sha256 الحاليّ `2cb2613b…`)، وقبولُ قطعٍ صلب مع البرنامج الثابت | تفويض + قطعٌ صلب بعد اختبار ESP32 | `docs/audits/patches/SUP-08-actuator-v2-PENDING-GATE-01.patch` |
| 7 | CATALOG-DECLARES-NO-SERVICE-CONSUMER-FOR-HTTP-OPERATIONS-01 | المستهلكون بين الخدمات: (أ) frontend وحده · (ب) ملفُّ تصريحٍ يحرّره المالك مع حارس وسقّاطة · (ج) ترقيةٌ آليّة (دائريّة) | (ب) | `owner_decisions_20261025.md:235-245` |
| 8 | ROUTER-SIZE-UNGUARDED-AFTER-MAIN-DECOMPOSITION-01 | هل تُقرّ خطّة تقطيع الموجّهات (4 شرائح تبدأ بـ`farm_operations_ledger`)؟ | — | `docs/architecture/router_extraction_plan_20261018.md` |
| 9 | REPORT3-RAG-02-01 | ملفُّ مصدرٍ للبذور وإعادةُ بذرٍ مقيسة إلى `__global__`، أم تبقى البذرة الداخليّة محجورة؟ | — | `services/qdrant-seed/seed.py:161-168` |
| 10 | UWRP-V43-LEARNING-SCRIPTS-UNSAFE-01 | إعادة تثبيت السكربتات المُصلَحة (أ–د)؟ ومشاركةُ إعادة إنتاج ثغرة `compare_trials`؟ وحدودٌ دنيا للسياسة؟ | — | `owner_decisions_20261025.md` |
| 11 | GAP-REGISTRY-DOES-NOT-REQUIRE-IDS-FOR-PR-FINDINGS-01 | التشغيل عند `pull_request_review`: (أ) الـworkflow كاملاً · (ب) workflow صغير منفصل · (ج) قبولُ الحكم عند الدفعة التالية | — | `.github/workflows/capability-governance.yml` |
| 12 | OWNERSHIP-CONTRACT-DECLARED-BUT-NEVER-MEASURED-01 | لكلّ صفٍّ معدود (67 كتابة + 46 قراءة غير مُعلَنة + 102 قارئٍ غير مرصود): الكود أم `db_ownership.yml`؟ | (ب) قبولُ التلميحات المشتقّة دفعةً | `owner_decisions_20261025.md` |
| 13 | WEB-ENDPOINT-CONSTANTS-WITHOUT-SERVER-HANDLER-01 | ~~دمجُ الإصلاح يُعيد نشر البوّابة~~ — **حسمه المالك:** «تنفيذ جميع الإصلاحات في pr واحد»، فضُمَّ إلى الـPR الموحَّد | — | — |
| 14 | RAILWAY-RESOURCEFUL-COMMITMENT-PROJECT-FAILS-EVERY-MAIN-COMMIT-01 | فكُّ ربط مشروع `resourceful-commitment` أم إصلاحُه؟ | — | `registry.md` (هذا الفرع) |
| 15 | REPORT3-RAG-12-01 | هل تكفي تجربة 2026-10-16 الحقيقيّة (24 استعلاماً، أحكامُ وكيل) للحكم بأنّ البادئة وحدها ليست السبب؟ | — | `certification/evidence/chatgpt_closure_nine_20261016/rag/` |
