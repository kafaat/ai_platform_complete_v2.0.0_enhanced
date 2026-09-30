# فرزُ دَين الفجوات — 2026-09-30

> **لقطةٌ لا مرجعٌ حيّ.** مُثبَّتةٌ على `main@a40f654b` (#1117)، قيست ~22:45Z في 2026-09-30.
> المرجعُ الحيّ لحالة كلّ صفّ هو [`sahool-brain/gaps/registry.md`](../../sahool-brain/gaps/registry.md)؛
> هذه الوثيقةُ تُسجّل **الأولويّة** التي قرّرها المالك، لا الحالة.
>
> **قرارُ المالك (2026-09-30):** قُبِل التصنيف كما هو، ومعه الستّةُ الأمنيّة بوصفها **مخاطرةً محصورة**
> (شبكةٌ داخليّة · محجوبةٌ على queue_v1 · على GATE-01) لا «مقبولة». الـ~٩٠ **دَينٌ مكتوب، لا مهامّ**.
> البندُ الوحيدُ الذي يُغيّر ما بعده: **بوّابةُ الإنتاج** (بيد المالك).

**الإطار:** `sahool-brain/gaps/registry.md` على main@`a40f654b` — ٥٦ صفّاً `open` (من ٤٣٦؛ ٢٣٣ fixed · ٣ verified) — **مضافاً إليها** ما لم يُدمَج بعد (شرائح · فروع `claude/wip-*` · مهامّ وكلاء · مهامّ الجلسة) ≈ ٣٤ ⇒ **~٩٠**.
**المعيار:** اليوم = تعرّضٌ حيّ + عملٌ مكتوب + سببُ فشله مقيس. الأسبوع = أمنٌ أو صحّةٌ بعملٍ مكتوبٍ يتعفّن إن تُرك، أو قرارُ مالكٍ اتُّخذ فعلاً. يُسجَّل ويُنسى = كلُّ ما عداه — دَينٌ مكتوبٌ بمصدره، لا يُتابَع.

---

## ١) اليوم — لا شيء

لا بندَ يستوفي الثلاثة. أقربُها شريحةُ التدقيق (§3.6 فحصُ ملكيّة المزرعة)، لكنّ:
- التعرّضُ غيرُ حيّ بالمعنى المقيس: RLS يعزل فعلاً، والمنصّةُ تُنشَر من `deploy/*` لا من main.
- الـpreflight على `e0207bbf` **فشل بسببين** (مقروءٌ من السجلّ): مراسي `platform_extraction_map.json` (٥ اختبارات + الشهادة) **و`test_router_size_ratchet`** (fields.py +18 سطراً — قرارُ تصميمٍ: أين يعيش `_stored_jsonb`).
⇒ تنتقل إلى الأسبوع. **اليومُ للتوقّف، كما قال المالك.** والشجرةُ عند `e0207bbf` محفوظةٌ على `claude/wip-audit-3-6-3-10-3-1`؛ الـpreflight الفاشل **قُرِئ** قبل هذا الفرز — `exit 0` لمُعيد التوجيه كاد يُقرأ «نجح».

## ٢) هذا الأسبوع — ١٢

| # | البند | لماذا الأسبوع | الحالة/الحاجب |
|---|---|---|---|
| 1 | شريحةُ التدقيق (§3.6 · §3.10 · §3.1) | عزلُ مستأجِرٍ + إسنادٌ كاذب للنموذج؛ مكتوبة ومُكذَّبة | فشلان مقيسان أعلاه؛ `claude/wip-audit-3-6-3-10-3-1`@e0207bbf |
| 2 | Slice C (حارسُ bidi · سطرُ SAHOOL_DEBUG · دليلُ Railway) | مكتوبة | `claude/wip-slice-c`@be317c60 |
| 3 | Slice E — F03 · F05 · F08 · F02-compose | حرّاسٌ **مقلوبة** (F05 أسوأ من الغياب) | ثلاثةُ فروع wip؛ Dockerfile الراستر آخِراً |
| 4 | Tiler — إزالةٌ من fixed/unified | قرارُ مالكٍ مُتَّخذ؛ يُغلق `TILER-…-01` | وكيلٌ لم يُطلَق |
| 5 | §3.4 erp-bridge: profile **و**readyz | قرارُ مالكٍ مُتَّخذ | وكيلٌ لم يُطلَق |
| 6 | SAM2_REF: commit + فحصٌ أسبوعيّ + SHA256 | قرارُ مالكٍ مُتَّخذ | وكيلٌ لم يُطلَق |
| 7 | §3.5 vllm-jais: اختبارُ الشروط الثلاثة | قرارُ مالكٍ مُتَّخذ | وكيلٌ لم يُطلَق |
| 8 | ثقةُ المستأجِر في الراستر وsentinel-hub-mcp | أمن: مستأجِرٌ يُمرِّره المُستدعي | `claude/wip-agent-raster-trust`@80d0b757 |
| 9 | — **مشروطٌ ببوّابة الإنتاج** — Postgres 15.8 → 15-3.5 (`POSTGRES-15-8-IS-STALE…`) | CVE؛ فحوصُ القراءة جاهزة وأُرسِلت للمالك | البوّابة |
| 10 | — بوّابة — queue_v1 للإشعارات (`NOTIFICATION-AGENT-LEGACY…`) | يمنع إعادةَ النشر بلا انقطاع | البوّابة + قيمةُ الوضع |
| 11 | — بوّابة — env_drift B (TileJSON) | مكتوب | `claude/wip-env-drift-b`@9f80a66b |
| 12 | — بوّابة — `SECURITY-DEFINER-…-PUBLIC-EXECUTE-01` + `NATS-ON-RAILWAY-STAGING-HAS-NO-AUTH…` | أمنٌ على Railway | موافقةُ مالك + خطّةُ تراجع |

إن لم تُفتَح البوّابةُ هذا الأسبوع ⇒ 9–12 تنتقل تلقائيّاً إلى «يُسجَّل» بلا نقاش.

## ٣) يُسجَّل ويُنسى — الباقي (~٧٥)

**قرارُ مالكٍ بلا موعد (يبقى صفُّه، لا يُتابَع):**
REPORT3-RAG-01…12 (١١) · REPORT3-U05 · U07 · U08 · REPORT2-C03 · C04 · B6-STRUCTURED-PROPOSAL · M4-BOOTSTRAP-JOURNAL · VEGETATION-ANALYZE-GATE · WEATHER-FORECAST-TOPIC · HEARTBEAT-LAST-SUCCESS · WEATHER-IDLE-WORKER · ROUTER-SIZE-UNGUARDED · COMPOSE-ALTERNATES · NO-SERVICE-…-OWNER · ROLE-DICTIONARY · TITILER-UPSTREAM-METRICS · CDSE-EMPTY-SCENE · PLATFORM-CONNECTOR-…-WIND

**غيرُ مقيس أو محجوبٌ بالبيئة:**
SAHOOL-AI-RAG-LIVE-001 · LOCAL-DEV-TENANT-POINTS · AUDIT-FINDINGS-NAMED-BUT-NOT-MEASURED · OWNER-AUDIT-20260920 · OUTBOX-BATCH-HOLDS-CONNECTION · OUTBOX-LEASE-SPENT-SERIALLY · RESTART-POLICY-BYPASSES-DEPENDS-ON · CONNECTIVITY-AUDIT-20260910 · PRODUCTION-CERTIFICATION-VERDICT · CORRELATION-ID-ABSENT · QDRANT-KEY-ROTATION (تشغيليّ لدى المشغّل)

**أدواتٌ وحوكمة (لا خطرَ تشغيليّ):**
C-LOCALE-GUARD-SWEEPS · TEXT-GUARD-ANCHORED-WRONG-FILE · FROZEN-PATH-LIST-NAMES-MISSING-FILE (ملفٌّ مجمَّد — لا أُعدّله) · OWNERSHIP-CONTRACT-NEVER-MEASURED · TENANT-GUC-NAME-DIVERGES (محروسٌ من يومه) · LOCAL-AUDIT-REPORT-PINNED-TO-SHAS (مع الشريحة 1)
ومهامُّ الجلسة: الموجةُ ٢ لزرع عطلٍ في ١١٣ حارساً (#29) · صفُّ صنف «الحارسُ يقيس الذِّكرَ» (#31) · تصحيحاتُ الدماغ (#28).

**⚠ أمنٌ يُقبَل دَيناً عن علم — أُسمّيه كي لا يُنسى أنّه نُسِي:**
| البند | لماذا يُقبَل |
|---|---|
| `SUP-08-DEVICE-COMMAND-SIGNATURE-UNBOUND-TO-DEVICE-01` | GATE-01 مجمَّد؛ patch جاهز في docs/audits/patches/ |
| `CP997-05-EDGE-IDEMPOTENCY-…` | GATE-01 + هجرة |
| `UNRECORDED-IRRIGATION-READ-AS-ZERO…` | GATE-01 (phase_runtime_workers.py مجمَّد) |
| `NATS-BROKER-HAS-NO-AUTHENTICATION…` (v9) + فرع `wip-agent-nats`@96f6a034 | v9 محلّيّ؛ Railway صفٌّ منفصل في الأسبوع/12 |
| `POSTGRES-V9-HAS-NO-TLS…` | v9 محلّيّ على شبكةٍ داخليّة |
| `JWT-DECODE-OUTSIDE-SHARED-SECURITY-01` + `wip-agent-ratchets-jwt-held` | يمسّ `shared/**` ⇒ محجوزٌ حتّى قرار queue_v1 |

## ما يُغلَق بهذا الفرز

- **مراقبُ الجلسة الساعيّ** (إعادات تشغيل الوكلاء): أُوقِف بإقرار المالك — شرطُه («كلُّ إعادة تشغيلٍ مدمجةٌ أو محجوزةٌ صراحةً») تحقّق بهذا الفرز: raster_trust في الأسبوع، nats وjwt محجوزان هنا.
- **فروع wip** تبقى نسخاً احتياطيّة؛ لا PR منها إلّا ما في الأسبوع.
- **بانتظار المالك (ليست بنوداً):** NOTIFICATION_CONSUMER_MODE (البيئتان) · SAHOOL_DEBUG · RAILWAY_DOCKERFILE_PATH على migrate-main · تشغيلُ فحوص Postgres للقراءة فقط (pg_proc · pg_authid · pg_prepared_xacts · replication slots) · موافقةُ مسبار HEALTHCHECK في staging.
