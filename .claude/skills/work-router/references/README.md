# UWRP Professional v4.2 — حزمة مهارات موحّدة / unified skill pack

عشر مهارات مستقلّة؛ يُحمَّل منها ما تحتاجه المهمّة فقط. لا تحتاج المهمّة البسيطة أيّ مهارة.

| المهارة | الدور |
|---|---|
| `work-router` | يختار أقلّ عدد من المهارات ومستوى العمل؛ ويحمل جدول التوجيه والتحقّق والأبحاث |
| `intent-to-proof` | عقد عمل: مطالب ← مهام ← أدلّة قبول، مع فاحص يقيس نسبة الإغلاق |
| `evidence-research` | بحث بمصادر أصليّة ونسخ وتاريخ ودرجة ثقة |
| `failure-investigation` | سبب جذريّ بشاهد يفشل قبل الإصلاح وينجح بعده |
| `collaboration-coordination` | كاتب واحد لكلّ مورد، تسليم موثَّق، لا فكّ قفل بالعمر |
| `change-review` | مراجعة مستقلّة على الفرق الفعليّ والقاعدة والبوّابات |
| `safe-delivery` | الدفع والدمج والنشر والإرسال والحذف: إذن محدّد وفحص حيّ ولا إعادة عمياء |
| `skill-evaluator` | اختبار المهارة قبل تعميمها: تقييم استدعاء أعمى ومقارنة مع/بدون |
| `work-continuation` | UWRP Portable v3.1 — مجمَّدة بايتاً ببايت |
| `adaptive-test-accelerator` | Adaptive Test Accelerator v1.1 — مجمَّدة بايتاً ببايت |

## أين تعمل الحزمة — حقائق موثَّقة (تحقّق 2026-10-19)

| السطح | الطريقة | يصل إلى |
|---|---|---|
| مستودع واحد | ضع المجلّدات في `.claude/skills/` داخل المستودع | كلّ جلسة Claude Code لهذا المستودع، **بما فيها السحابيّة** (جزء من النسخة) |
| كلّ مشاريعك | ارفع كلّ مهارة zip مستقلاً في claude.ai: Customize › Skills › Upload | claude.ai، ويُزامَن إلى Claude Code (الإصدار 2.1.273 فأحدث، بالحساب نفسه) **وإلى الجلسات السحابيّة** |
| فريق/مؤسّسة | Team/Enterprise: نشر المهارة لمكتبة المؤسّسة أو توفيرها للجميع | كلّ الأعضاء |
| جهاز واحد | `~/.claude/skills/` | Claude Code المحلّيّ فقط؛ **لا ينتقل** إلى الجلسات السحابيّة |
| Codex · Kimi · OpenCode · GitLab Duo | مسار المهارات الذي توثّقه كلّ أداة؛ راجع [PROVIDER_DISCOVERY_AR.md](PROVIDER_DISCOVERY_AR.md) | تلك الأداة |
| أيّ محادثة بلا مهارات | الصق [UNIVERSAL_WORK_START_AR.md](UNIVERSAL_WORK_START_AR.md) ومعه نصّ مهارة واحدة | تلك المحادثة فقط |

شروط رفع claude.ai: مجلّد المهارة في جذر الـzip، واسمه هو اسم المهارة؛ الوصف ≤ 200 حرف؛ مفاتيح الواجهة المقبولة فقط `name` و`description` و`license` و`compatibility` و`metadata` و`allowed-tools`. الحزمة تفي بها، ويفحصها `scripts/verify_pack.py`. وصفا المهارتين المجمَّدتين أطول من 200 حرف (308)، فنسختا الرفع منهما تختلفان في سطر الوصف وحده، وتبقى الأصليّتان دون تغيير.

المصادر: https://code.claude.com/docs/en/skills · https://code.claude.com/docs/en/cloud-environments · https://code.claude.com/docs/en/plugins/org · https://support.claude.com/en/articles/12512180-using-skills-in-claude · https://support.claude.com/en/articles/12512198-how-to-create-custom-skills

**ملاحظة:** إضافة marketplace عبر `.claude/settings.json` في المستودع **لا** تصل إلى الجلسات السحابيّة. لذلك لا تعتمد هذه الحزمة عليه.

## التحقّق

```bash
python3 work-router/scripts/verify_pack.py <skills-root> [--require-baselines]
python3 work-router/tests/test_pack.py                   # من جذر المهارات
python3 intent-to-proof/scripts/check_contract.py <contract.json> --require-closure 1.0
python3 skill-evaluator/scripts/trigger_eval.py emit --skills-root <root> --scenarios skill-evaluator/assets/trigger_scenarios.json
```

ما قيس فعلاً وما لم يُقَس: [EVALUATION_RESULTS.md](EVALUATION_RESULTS.md). الحدود والصلاحيات: [SECURITY_AND_AUTHORITY.md](SECURITY_AND_AUTHORITY.md). بوّابة الاعتماد: [ADOPTION_GATE_AR.md](ADOPTION_GATE_AR.md). الدراسة: [COMPARATIVE_STUDY_AR.md](COMPARATIVE_STUDY_AR.md) · [RESEARCH_AR.md](RESEARCH_AR.md) · [SOURCE_REGISTER.json](SOURCE_REGISTER.json).

---

**English.** Ten independent skills. The eight v4.1 skills are improved and self-contained; the two baselines are byte-frozen. Install per repository in `.claude/skills/`, which reaches cloud sessions. To reach every project, upload each skill zip to claude.ai: enabled skills sync to Claude Code, including cloud sessions. `~/.claude/skills` is local only. Descriptions are ≤ 200 characters and frontmatter is upload-safe; `verify_pack.py` enforces both. Measured results and limits: [EVALUATION_RESULTS.md](EVALUATION_RESULTS.md). No skill grants permission to push, merge, deploy, delete or upload.
