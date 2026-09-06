# 🚧 سجلّ الفجوات الحيّ (Gap Registry)

> سجلّ حيّ بالحالة. كلّ صفّ يحوي **مصدراً** (`file:line` أو `#PR`) و**حالة**
> (`open` / `fixed` / `verified`). المصدر الأساسيّ:
> [`../../SAHOOL_PRODUCTION_GAP_REPORT_v1.md`](../../SAHOOL_PRODUCTION_GAP_REPORT_v1.md) (تحليل ساكن
> READ-ONLY — «مؤشّر ≠ إثبات»: `fixed` = عُولِج في الكود؛ `verified` = أُكِّد حيّاً).
>
> **تنبيه دقّة:** تقرير الفجوات سجّل بعض البنود مُصلَحةً في الكود (#349–#363) لكنّها لم تُؤكَّد
> حيّاً بعد؛ نُبقيها `fixed` (لا `verified`) التزاماً بحدّ الصدق.

| ID | العنوان | المجال/الخدمة | المصدر | الحالة |
|---|---|---|---|---|
| BRAIN-DUP-GUARD-BLIND-TO-TABLE-ROWS-01 | حارسُ تكرار الهويّات يطابق عناوين `## ` وحدها، وسجلُّ الفجوات **جدول** — فتغطيتُه للموضع الذي تعيش فيه الهويّات أصلاً كانت **صفراً**. | brain · governance | [`brain_duplicate_gap_identity_guard.py`](../../scripts/ci/brain_duplicate_gap_identity_guard.py) (`HEADING_RE` · `ROW_RE`) · [`gaps/registry.md`](registry.md) | **fixed** — مرّ الحارسُ أخضرَ على صفّين متلاصقين لنفس المعرّف، **وأمسك التكرارَ مراجعٌ آليّ على #882 لا الحارسُ الموضوع لأجله بعينه**. أُضيفت `ROW_RE` بمرساة `|` تحفظ الصرامة نفسها. **والتكرارُ موروثٌ من `main` لا من هذه الشريحة**، وحُلَّ بالدمج لا بالحذف: السجلّ إلحاقيّ، و`brain_append_only_guard` حجب أوّلَ محاولةٍ حذفتُ فيها الصفّ (فُقِد ١٢٢٤ بايتاً) — والعلاجُ المكتوب في الحارس نفسه هو دمجُ المدخلين بحفظ نصّيهما. ومُكذَّبٌ من الطرفين. |
| MUT-REGISTRY-STRANDED-SPECS-01 | مواصفاتُ طفراتٍ تجلس مفاتيحَ أعلى الجذر، فتبدو مُسجَّلةً والمُشغِّل لا يقرؤها إطلاقاً. | ci · governance | [`guard_mutation_guard.py`](../../scripts/ci/guard_mutation_guard.py) (`check`) · [`guard_mutation_registry.json`](../../docs/architecture/guard_mutation_registry.json) | **fixed** — ثلاثُ مواصفات RAG حملت **٨ طفرات** بهذا الوصف، والبوّابةُ تمرّ خضراء وهي لا تعرفها: **تغطيةٌ مُعلَنةٌ غيرُ مملوكة**، وصمتُها أسوأ من حمرتها. نُقِلت إلى `behavioural` فصار الكونُ ٢٧٤ + ١١٠ = **٣٨٤** مطابقاً للمُعلَن. **و٨/٨ تُقتَل فعلاً عند التنفيذ** — فكانت تغطيةً حقيقيّةً معطَّلةً بخطأ تسجيل لا ادّعاءً فارغاً. والصنفُ مُغلَق: أيّ مفتاحٍ بشكل مواصفةٍ خارج القسمين يُخفِق صراحةً، مُكذَّباً بالزرع من الطرفين. |
| MUT-SWEEP-TIMEOUT-01 | مكنسةُ الطفرات نمت داخل *Unit Tests* حتّى صار الهامشُ فوق سقف المهلة **٥٨ ثانية**. | ci · governance | [`ci.yml`](../../.github/workflows/ci.yml) (`unit-tests.timeout-minutes`) · [`test_ci_pipeline_settings.py`](../../tests_v9/test_ci_pipeline_settings.py) · [`test_mutation_sweep_headroom.py`](../../tests_v9/test_mutation_sweep_headroom.py) | **fixed** — المقيس على #882: ٥٩:٠٢ مقابل سقف ٦٠، والأساسُ على `1cb3f278` ٤٦:٠٦. والسببُ مقيسٌ لا مفترَض: السجلّ ٣٨٤ ← ٤٠١ طفرةً مُعلَنة، و`MUT-PRE0` فوقها فعّلت ٨ مواصفاتٍ كانت محسوبةً في ٣٨٤ **ولا تُشغَّل قطّ** — ~٢٥ دورةَ زرعٍ↔pytest↔ردٍّ إضافيّة. رُفِع السقفُ إلى ٩٠ (هامشُ ~٣٤٪) وأُضيفت علامةُ ماءٍ على عدد الطفرات تُحمِّر **محلّيّاً في ثوانٍ** بدل أن يُكتشَف النموّ بعد حرقِ تسعين دقيقة. **والعلاجُ البنيويّ — نقلُ المكنسة إلى وظيفةٍ مستقلّة — مؤجَّلٌ بسببٍ مُعلَن:** يلزمه إضافةُ اسمِ الوظيفة إلى الفحوص المطلوبة في الـRuleset، و`branch_protection_contract_guard` يفرض حلَّ المحادثات وحده ولا يُعدّد الفحوصَ بالاسم — فالنقلُ قبل ضبط القفل يجعلها إرشاديّةً **صامتاً**. مُكذَّبٌ من الطرفين (٢/٢ مقتولة). **وحدُّ صدق:** `preflight.sh --fast` يتخطّى المكنسة، فخُضرتي المحلّيّة لم تكن تستطيع رؤية هذا — عُرِف من ساعة CI لا من قياسي. |
| RAG-PARITY-VOCABULARY-HALF-MIGRATED-01 | فصلُ الاسمين عولج في ثلاثة مستهلكين، وبقيت **المفردةُ المحفوظة** ومُنتِجٌ ثانٍ محجوزٌ في CI. | rag · governance | [`c8_rag_production_certification.py`](../../scripts/ci/c8_rag_production_certification.py) · [`rag_authority_convergence.json`](../../docs/architecture/rag_authority_convergence.json) · [`ci.yml`](../../.github/workflows/ci.yml) (السطر ٤٣٤) | **fixed** — وثيقةُ الحالة كانت تحمل `collection_schema_parity` و**لا تحمل `canonical_payload_parity` إطلاقاً**، فمُنتِجٌ يكتب الاسمَ الواسع `True` كان يُسقِط شرطَ الـpayload من الحساب رأساً لا يُخالِفه. والحسابُ قبل الإصلاح: `c8` بعد قلبِ `direct_qdrant_revocation_ready` ⇒ `blockers=[]` ⇒ `CERTIFIED_CUTOVER_CAPABLE` على إيصالٍ أثبت تكافؤَ المتّجه وحده — أي أنّ حارسَ الـpayload الوحيد كان **مصادفةً**. وبعده: يبقى `canonical_payload_parity` حاجزاً قائماً. هوجِرت المفردةُ ورُفِعت `version` إلى ٢ صراحةً (تُبطِل الأدلّة القديمة بدل أن يُقرَأ نقصُها قبولاً)، وزال المفتاحُ الشبح من حاجبات حارس القبول. **والسببُ الجذريّ أنّ التثبيت كان على نصّ الإسناد في ملفٍّ سُمّي بعينه لا على الخاصّيّة** — و`c8` يستعمل `effective[` فلم يطابق أيَّ نصّ. فصار الفحصُ خاصّيّةً على كلّ الشجرة بـ`ast` (لا نصّاً، تفادياً لـ`TEXT-GUARD-ANCHORED-IN-THE-WRONG-FILE-01`). مُكذَّبٌ من الطرفين، **والتكذيبُ أعاد إنتاج العطل الأصليّ بعينه فحمِرَ الاختبارُ الجديد وحده**. أمسكه مراجعٌ آليّ على #882. |
| RAG-CORPUS-AUDIT-RECEIPT-MISSING-01 | `canonical_payload_parity` كانت مثبَّتةً `False` بلا مسارٍ يرفعها بدليل — شرطٌ بلا آليّةِ وفاء. | rag · governance | [`rag_live_corpus_audit.py`](../../scripts/architecture/rag_live_corpus_audit.py) · [`rag_corpus_audit_receipt_guard.py`](../../scripts/architecture/rag_corpus_audit_receipt_guard.py) · [`rag_authority_convergence.json`](../../docs/architecture/rag_authority_convergence.json) (`corpus_audit_acceptance`) | **fixed** — D08: تكافؤُ الـpayload صار **مشتقّاً من إيصالِ جرد** لا مثبَّتاً في أيٍّ من الاتّجاهين، و`payload_parity_observed = False` هو الافتراضيّ فلا يرتفع إلّا بإيصالٍ مُتحقَّقٍ منه. والإيصالُ مقيَّدٌ بـ`--subject-sha` و`--subject-tree` معاً — فالـSHA وحده لا يمنع تقديمَ قياسٍ أُجرِي على محتوًى آخر. **ولا يشحن المستودعُ أيَّ إيصال**: لا Docker daemon ولا Qdrant هنا، فالإيصالُ الحيّ لم يُنتَج ولم يُلفَّق. ٦/٦ طفرة مقتولة بالزرع، والسلطةُ ما تزال `EVIDENCE_REQUIRED · capable=False`. |
| RAG-CORPUS-MEASUREMENT-INTEGRITY-01 | صدقُ القياس قبل إصلاحِ ما يُقاس: عددٌ دقيق، ورفضٌ مُصنَّف، وتكافؤٌ لا يُقرأ أوسع ممّا قاس. | rag · governance | [`production_qdrant.py`](../../services/sahool-platform/core/rag/production_qdrant.py) · [`rag_corpus_admissibility_probe.py`](../../scripts/architecture/rag_corpus_admissibility_probe.py) | **fixed** — العدُّ صار عبر Count API بـ`exact:true` **بلا ارتدادٍ** إلى التقريبيّ · و`skipped_by_reason` بتصنيفٍ ثابتٍ مُشتقٍّ من التحقّق لا من نصوص الاستثناءات، بعيّناتٍ محدودة وبلا نصّ مقطع · و`collection_schema_parity` انقسمت اسمين. ولا ترتيبَ تغيّر ولا بيانٌ هوجِر ولا سلطةٌ رُفِعت. |
| RAG-QDRANT-APPROXIMATE-COUNT-READINESS-01 | `points_count` من معلومات المجموعة **تقريبيّ بالعقد** وكان سلطةَ جاهزيّةٍ دقيقة. | rag · runtime | [`production_qdrant.py`](../../services/sahool-platform/core/rag/production_qdrant.py) (`collection_point_count`) · [`rag-retrieval/main.py`](../../services/rag-retrieval/main.py) (`_ensure_sparse_index`) | **fixed** — العطلُ كان مستقلّاً عن لغز الـ٥٤: يبقى قائماً بعد أن يصير `skipped = 0` وتُهاجَر كلّ نقطة، فينتج ٥٠٣ في مسارٍ حاجب **بلا فقد نقطةٍ واحدة**. وتعذُّرُ العدّ الدقيق يفشل مغلقاً بسببٍ مسمًّى. |
| RAG-LEGACY-DENSE-SPARSE-SCOPE-ASYMMETRY-01 | مستأجِرٌ في جذر الـpayload ⇒ يقبله المحلّل ويعميه مرشّحُ Qdrant: مرئيٌّ للمتناثر، غيرُ مرئيٍّ للكثيف. | rag · retrieval | [`production_qdrant.py`](../../services/sahool-platform/core/rag/production_qdrant.py) (`from_payload` · `search`) | **fixed** — مُعادُ إنتاجه بالزرع: `from_payload` = PASS · `chunk.tenant_id='tenant-a'` · `metadata['tenant_id']=None`. والقاعدةُ الناقصة: **قابليّةُ التحليل ليست أهليّةَ خدمة**. يكشفه `LEGACY_TENANT_ROOT_ONLY` ولا يُصلَح قبل جرد المجموعة الحيّة.  **✅ أُغلِقت (2026-08-27، فوق `ff4ab11f`):** العلاجُ **تطبيعٌ عند القراءة** في `from_payload` — المستأجِرُ المُحَلُّ من جذر الحمولة يُكتَب في `metadata.tenant_id` (`setdefault`، فلا يمسّ صفّاً يحمله سلفاً). فيتّفق ما يراه البحثُ المتناثر (`chunk.tenant_id`) وما يرشّح عليه الكثيف (`metadata.tenant_id`). **ويُشفى الصفُّ القديم لحظةَ تحليله** بلا انتظار إعادةِ فهرسةٍ كاملة للمخزَن. **والترتيبُ مقصود:** مِسبارُ `RAG-CORPUS-MEASUREMENT-INTEGRITY-01` يحمل القرارَ مكتوباً — «إصلاحُ الترتيب قبل معرفة المجموعة التي نقيسها يُصلِح رقماً لا يُعرَف مصدره» — فهذه الفجوةُ **شرطُ** إصلاح `RAG-BM25-CROSS-TENANT-CORPUS-STATS-01` لا عملٌ موازٍ له: ما دام المساران يريان مجموعتين مختلفتين فلا تُعرَّف المجموعةُ التي تُحسَب إحصاءاتُها. **والدَّينُ المقيس في المِسبار ٤/٤ ⇒ ٣/٤.** **ومرساةُ الاختبار قُلِبت لا حُذِفت:** كانت تؤكّد أنّ الكاشفَ **يُطلِق** (صوابٌ ما دام العطلُ قائماً)، وتركُها كذلك كان سيجعل **الإصلاحَ هو ما يكسر الجناح** — وهو بعينه ما حذّر منه متنُ المِسبار. فصارت تؤكّد الإصلاح، **والكاشفُ لم يمت بل صار كاشفَ انحدار**: نزعُ سطر التطبيع يُعيد `present=True` ويُحمِّرها (مقيسٌ بالزرع، واستعادتُه تُخضِرها). |
| RAG-BM25-CROSS-TENANT-CORPUS-STATS-01 | `score` يقرأ `n_docs` و`doc_freq` و`avg_len` العالميّة قبل أيّ عزل، و`search` يرشّح بعده. | rag · retrieval · tenancy | [`production_qdrant.py`](../../services/sahool-platform/core/rag/production_qdrant.py) (`BM25Index.score`) | **✅ أُغلِقت (2026-08-27، فوق `157a9cb4`):** كان مُعادَ إنتاجه: ٠٫٤١١ ← ٠٫٠١٢ بمستنداتِ مستأجِرٍ آخر تحمل المصطلح · ← ٧٫٢٨٩ بمستنداتٍ طويلة **لا تحمله** (عبر `avg_len`). **ولا إفشاءَ محتوًى** — تأثيرٌ في الترتيب وحده، ومُربِكٌ مباشر لأيّ قياس تكافؤ. **والعلاجُ `corpus_stats(tenant_id)` مقصورةٌ على `visible_scope`** = `{tenant_id, __global__}` — وهي بعينها ما يرشّح عليه البحثُ الكثيف، فالمجموعةُ التي تُحسَب إحصاءاتُها واحدةٌ للمسارين. **والمرشِّحاتُ لا تُضيِّق الإحصاء عمداً:** انتقاءٌ داخل المجموعة لا إعادةُ تعريفٍ لها، وإلّا صارت ندرةُ المصطلح دالّةً في مرشِّح الاستعلام نفسِه — أسوأُ من العطل المُغلَق. **والإحصاءُ يُمسَك مُبوَّباً والمجاميعُ تُشتقّ منه** لا تُمسَك بجانبه: نسختانِ بيدَين تنحرفان صامتتَين. **و`score` صار يطلب `tenant_id` صراحةً بلا افتراض** — «مستأجِرُ الوثيقة» كان سيبدو مقبولاً ويكون خاطئاً، لأنّ وثيقةَ المرجع العامّ تُقاس داخل مجموعة **السائل**. **والدَّينُ المقيس في المِسبار ٣/٤ ⇒ ٢/٤.** **والمرساةُ قُلِبت لا حُذِفت**، ومعها **شاهدٌ موجب**: «الدرجةُ لم تتحرّك» يبقى صادقاً لو صارت `score` تُعيد صفراً أبداً، فيُثبَت أنّ الإحصاءَين المُنطاق والعالميّ **يختلفان فعلاً على العيّنة** — وإلّا كان الأخضرُ بلا معلومة. وثلاثُ طفراتٍ مُسجَّلةٌ في القسم السلوكيّ، والرابعةُ **أُعيد توجيهُها لا تُسمِّيتُها**: `"present": False` صارت غيرَ قابلةٍ للقتل بعد الإغلاق (`present` صادقٌ بـ`False` على كلّ مجموعة)، فصارت تُصيب **الإنذارَ الكاذب** باستبدال درجةٍ مقيسة برقمٍ مُختلَق. |
| RAG-NEIGHBOR-FILTER-SCOPE-BYPASS-01 | `_expand_neighbors` يدخل بالمستند والترتيب بلا إعادة تطبيق `crop`/`field_id`/`region`/`source_type`. | rag · retrieval | [`production_qdrant.py`](../../services/sahool-platform/core/rag/production_qdrant.py) (`_expand_neighbors` · `matches_scope_filters`) · [`test_rag_neighbor_scope_filters.py`](../../tests_v9/test_rag_neighbor_scope_filters.py) | **✅ أُغلِقت (2026-08-29، فوق `08e92279`):** كان مُعادَ إنتاجه — استعلامُ `field_id=F1` أعاد جاراً من `F2`. **والعلاجُ تمريرُ `filters` إلى التوسيع وتطبيقُها بـ`matches_scope_filters`** — **تعريفٌ واحد** استُخرِج من `BM25Index.search` ويُشتقّ منه الموضعان. **ونسخةٌ ثانية للشرط كانت تُصلِح الحادثة وتُبقي الصنف:** شرطانِ متطابقانِ يُكتَبان مرّتين ينحرفان عند أوّل تعديلٍ لأحدهما بلا أن يحمرّ شيء — درسُ `RAG-BM25-CROSS-TENANT-CORPUS-STATS-01` مُطبَّقاً. **والحدُّ لم يتبدّل: عزلُ المستأجِر كان محفوظاً ولا يزال** (مفتاحُ `by_doc_idx` يحمل `tenant_id`) — عطلُ دقّةِ نطاقٍ لا خرقُ عزل، **وتأكيدُ ذلك مُثبَّتٌ في الجناح** كي لا تُقرأ الشريحةُ أوسعَ من دليلها. **والدَّينُ المقيس في المِسبار ٢/٤ ⇒ ١/٤.** **والمرساةُ قُلِبت لا حُذِفت — الثالثةُ في هذا العنقود** — والطفرةُ المُسجَّلة **وُجِّهت لا حُدِّث اسمُها**: `"present": False` صارت غيرَ قابلةٍ للقتل بعد الإغلاق. **⚠ وطفرةٌ نجت فكشفت عطلاً في شاهدي أنا:** كان التأكيدُ يقيس **وجودَ** الكلمة المفتاحيّة `filters` لا **قيمتَها**، و`filters=None` يُرضيه حرفيّاً — الاسمُ باقٍ والنطاقُ ذهب. صُحِّح الشاهدُ بـ`ast` ليقيس أنّ المُمرَّر اسمُ النطاق نفسُه. **النجاةُ تشخيصٌ لا حكم، وقد كان العطلُ في الاختبار.** |
| RAG-STORAGE-ID-AS-LOGICAL-IDENTITY-01 | التوثيق يقول إنّ الهويّة المنطقيّة دائماً `metadata.chunk_id`، والكود يُرقّي UUID التخزين عند غيابه. | rag · identity | [`production_qdrant.py`](../../services/sahool-platform/core/rag/production_qdrant.py) (`from_payload` · `payload`) · [`test_rag_storage_id_declaration.py`](../../tests_v9/test_rag_storage_id_declaration.py) | **✅ أُغلِقت (2026-08-29، فوق `08e92279`):** كان مُعادَ إنتاجه — `chunk_id = 'storage-uuid-42'`. **والعطلُ الصمتُ لا الاستعارة، والعلاجُ إعلانٌ لا نزع** — ثلاثةُ أسبابٍ مقيسة: ① `canonical_storage_shape` يستدعي المحلّلَ بـ`fallback_id=None` **فالخدمةُ القانونيّة ترفض المُستعارَ اليوم**، والسِّعةُ للهجرة والتدقيق ونزعُها يُعمي التدقيقَ عن الصفوف التي وُجِد لأجلها · ② مستهلِكٌ يقرأ `chunk_id` **لا يميّز مُعلَناً من مُستعار**، فيبني إحالاتٍ تنكسر عند أوّل إعادةِ كتابة · ③ وهو نمطُ `CAPABILITY-EVIDENCE-LISTS-TRUNCATE-SILENTLY-01` بعينه: **أُعلِن الاقتطاعُ ولم يُرفَع السقف**. فصارت `metadata['chunk_id_source']` تقول `declared` أو `storage_fallback`. **ولا تُكتَب في المخزَن:** `payload` تنزعها لأنّها خاصّيّةُ **هذا التحليل** لا خاصّيّةُ الصفّ — وإبقاؤها كان يكذب على صفٍّ أُعيدت كتابتُه بمفتاحٍ صحيح. **وأصلُ الفجوة متنٌ يَعِد بما لا يقع** («مُعرِّفُ التخزين لا يُسمَح أن يصير هويّةَ استرجاع») — **فصُحِّح المتنُ أيضاً**، وتركُه كان يُبقي نصفَ العطل: القارئُ يصدّق المنعَ فلا يبحث عن الراية. **والدَّينُ المقيس في المِسبار ١/٤ ⇒ ٠/٤ — العنقودُ أُغلِق.** والمرساةُ قُلِبت لا حُذِفت (الرابعةُ) والطفرةُ وُجِّهت لا حُدِّث اسمُها. |
| FROZEN-PATH-LIST-NAMES-A-FILE-THAT-DOES-NOT-EXIST-01 | قائمةُ التجميد تُطابَق **عضويّةَ سلسلةٍ حرفيّة**، ومدخلٌ منها يسمّي ملفّاً لا وجودَ له بينما الملفُّ الذي يؤدّي دورَه في الشجرة **خارجَ التجميد**. | governance · gates | [`gate01_frozen_path_guard.py`](../../scripts/ci/gate01_frozen_path_guard.py) (`:185` · `touched = {p for p in changed if p in frozen}`) · [`gate01_policy.json`](../../docs/architecture/gate01_policy.json) (`frozen_paths` · `not_yet_in_tree`) · قياسُ هذه الجلسة على `157a9cb4` · #954 | **open** — مقيسٌ لا مُستنتَج: من عشرة مُجمَّدين، **اثنان معدومان في `main` وفي فرع #954 معاً**. وأحدُهما `migrations/run_migrations.sql`، **والحقيقيُّ `scripts_v9/run_migrations.sql`** — موجودٌ، غيرُ مُجمَّد، **وعدّلته #954 وسكتت البوّابة عنه**. **والسياسةُ تستبق قراءةَ «انزياحِ تسمية» وترفضها** بحجّة أنّ المدخلين «من الشريحة المحجوبة لم يُدمَجا قطّ» — وهي صحيحةٌ للمسار الحرفيّ ولا تصمد لهذا: الدورُ **قائمٌ في الشجرة** عند مسارٍ آخر، فالتجميدُ يحرس اسماً **لم يُنشَأ قطّ**. **وتصحيحٌ لصياغتي الأولى: كتبتُ «اسماً لن يُمَسّ» وهو تنبّؤٌ، والمقيسُ أقوى منه وأبسط** — `git log --all -- migrations/run_migrations.sql` = **صفرُ التزام على كلّ المراجع**، بينما نظيرُه القائم `scripts_v9/run_migrations.sql` يحمل **٧٦**. فالمدخلُ لا يحرس مساراً «لم يُدمَج بعد» كما تقول السياسة، بل مساراً لا تاريخَ له البتّة. والمدخلُ الثاني (`v228_phase_runtime_claim_leases.sql`) **سليمُ الوصف على `main`** — لا يوجد ولا يؤدّي دورَه شيءٌ آخر هناك؛ لكنّ #954 أنشأت الهجرةَ نفسَها باسم `v228_worker_claim_lease.sql` فمرّت خارج التجميد. **وحدُّ صدقٍ لازم: لم يُفلِت شيء** — البوّابةُ حجبت #954 فعلاً عبر `MANIFEST.txt` و`phase_runtime_workers.py`. فهذا **ثقبٌ كامنٌ لا حادثة**: شريحةٌ تمسّ الهجرةَ والسجلَّ وحدَهما تمرّ خضراء. **ولم يُمَسّ `gate01_policy.json`:** تصحيحُ المسار يُجمِّد ملفّاً غيرَ مجمَّدٍ اليوم — تشديدٌ للبوّابة يقع على حكم المالك ويزيد #954 حجباً، فيُسجَّل ولا يُنفَّذ من طرفٍ واحد. **والعلاجُ المقترَح أن تُطابَق الملكيّةُ لا السلسلة**، وأدنى منه شرطٌ يُحمِّر حين يحمل مدخلُ `not_yet_in_tree` اسمَ ملفٍّ **قائمٍ في الشجرة عند مسارٍ آخر** — ادّعاءُ «غيرُ موجود» يصير حينها قابلاً للتكذيب. |
| TENANT-GUC-NAME-DIVERGES-ACROSS-POLICY-FAMILIES-01 | عزلُ المستأجِر يقوم على `current_setting('app.<اسم>')`، **والاسمُ ثلاثةٌ لا واحد** — ومَن يضبط أحدَها لا يُرى له الآخر. | rls · tenancy · governance | [`v9_rls_tenant_isolation.sql`](../../migrations/v9_rls_tenant_isolation.sql) (`_sahool_apply_tenant_rls` — يحكم `fields`) · [`v106_phase9_10_runtime_strengthening.sql`](../../migrations/v106_phase9_10_runtime_strengthening.sql) · [`v161_soil_p1_products.sql`](../../migrations/v161_soil_p1_products.sql) · [`phase_runtime_workers.py`](../../services/sahool-platform/api/phase_runtime_workers.py) (`_set_tenant:47`) · [`tenant_guc_name_convergence_guard.py`](../../scripts/ci/tenant_guc_name_convergence_guard.py) · قياسُ هذه الجلسة على `99000487` | **open — والصنفُ محروسٌ من اليوم** · المقيس: `app.current_tenant` **١٠٢ هجرة / ١٨٦ ضابط** · `app.tenant_id` **١٢ / ٧** · `app.current_tenant_id` **٣ / ٤**. **وشكلُ الفشل صامتٌ لا حاجب:** اسمٌ خاطئ ⇒ `current_setting(…, true) = NULL` ⇒ `USING (tenant_id::text = NULL)` ⇒ **صفرُ صفوف** بلا استثناءٍ ولا سجلٍّ ولا تغيُّرِ رمزِ خروج — **إجابةٌ ناقصةٌ تُقرَأ كاملة**، وهي أخطرُ من ٥٠٣ صريحة في مسار قراءة. **وأصلُ البلاغ جلسةٌ محلّيّة أطارت إطارَ تنفيذها** (بصمةٌ معدومة · `tests/operational/` غائب)، **والكشفُ صحيحٌ وأوسعُ ممّا وصفت**: ليس تبايناً بين اختبارٍ وإنتاج بل **ثلاثةَ أسماءٍ في سياسات الإنتاج نفسِها**. وادّعاؤها أنّ سياسةَ `fields` تستعمل `app.current_tenant` صحيح، وموضعُه غيرُ ما ظُنَّ: تأتي من دالّةٍ تُطبَّق بحلقة لا من عبارةٍ مكتوبة. **والثمنُ يُدفَع الآن بترقيعٍ صامت:** `_set_tenant` يضبط **اسمين معاً** في سطرين متتاليين بلا سطرٍ يقول لماذا — فالحلُّ قائمٌ في موضعٍ واحد ومفقودٌ في سواه. **والتوحيدُ لم يُنفَّذ عمداً:** هجرةٌ تمسّ ثلاثَ عائلاتِ سياسات وشكلُ خطئها **صامت** — قرارُ ترتيبٍ وقياسٍ للمالك لا خطوةٌ عابرة. **وما نُفِّذ هو ما يمنع الاتّساع:** حارسٌ يرفض اسماً رابعاً، ويرفض اسماً بلا ضابط، وسقفٌ ينزل ولا يصعد — بثلاث طفراتٍ مُسجَّلة مقتولةٍ بالزرع. **وحدُّ صدق:** الحارسُ يمنع اتّساعَ الانحراف **ولا يُصلِح القائم**؛ خضرتُه تعني «لم يتّسع» لا «وُحِّد». |
| WEATHER-IDLE-WORKER-READS-AS-DEAD-01 | في المسار **النشط** لـ`weather-polygon-worker` تُنعَش النبضة عند **وصول حدث** لا كلّ دورة ⇒ عاملٌ سليمٌ بلا أحداث يُقرأ ميّتاً. خلطُ «لا عمل» بـ«لا حياة». | weather · runtime | [`weather-polygon-worker/src/main.py:168`](../../services/weather-polygon-worker/src/main.py) · [`test_weather_worker_health_probe.py`](../../tests_v9/test_weather_worker_health_probe.py) | **open — مؤجَّل بقصد وبسبب**: المسار خلف `WEATHER_GRID_PIPELINE_ENABLED` **المُطفَأ افتراضيّاً**، ولا منتِج لـ`sahool.weather.forecast.updated` اليوم. فإصلاحه الآن يعالج مساراً لا يعمل، ويوسّع شريحةً حُدَّت عمداً بأصغر delta. يُفتَح مع تفعيل العلم. |
| HEARTBEAT-LAST-SUCCESS-UNREAD-01 | `last_success_at` يُكتَب في نبضة العامل ولا يقرؤه `evaluate_heartbeat` إطلاقاً — حقلٌ يُنتَج ولا يُستهلَك. | platform · runtime | [`api/worker_heartbeat.py:104`](../../services/sahool-platform/api/worker_heartbeat.py) (يُكتَب) · [`api/worker_heartbeat.py:37`](../../services/sahool-platform/api/worker_heartbeat.py) (`evaluate_heartbeat` لا يقرؤه) | **open — مؤجَّل**: قراءتُه تُغيّر دلالة الفحص (يصير «نجح مؤخّراً» لا «يتحرّك»)، وهو قرارٌ دلاليّ لا إصلاحٌ ميكانيكيّ. والحالةُ الراهنة ليست عمياء: `current_state == "failed"` يلتقط الفشل المُعلَن. |
| SAHOOL-AI-RAG-LIVE-001 | إثباتُ تكافؤ الاسترجاع الحيّ (hybrid parity) على مكدّس مُشغَّل — المرحلةُ التي تسبق أيّ ترقيةِ سلطة لـRAG. **الهويّة القانونيّة الوحيدة لهذه الفجوة.** | rag · runtime | [`rag_live_parity_probe.py`](../../scripts/architecture/rag_live_parity_probe.py) · [`ai_rag_live_certification.py`](../../scripts/ci/ai_rag_live_certification.py) · [`rag_cutover_admission_guard.py`](../../scripts/architecture/rag_cutover_admission_guard.py) | **BLOCKED_BY_ENVIRONMENT** — `docker info` يخرج بـ1، ولا GPU ولا Ollama/Qdrant في هذا الاستنساخ. سببٌ بيئيّ مشروع: **لا يُستبدَل باختبارٍ ساكن ولا يُلفَّق له دليلٌ حيّ**. والتنفيذ الحيّ جرى على مكدّس المالك لا هنا، ونتائجه مُسجَّلةٌ نقلاً في `DIRECT-VS-CANONICAL-DENSE-SEMANTICS-01`. سلطةُ RAG تبقى `NOT_YET_AUTHORITATIVE` و`cutover-admission` = FAILED. |
| RAG-LIVE-01 | **إحالةٌ تاريخيّة لا فجوة.** معرّفٌ استعملتُه في رسالة الالتزام `952e68c4` قبل أن تُثبَّت التسمية القانونيّة، فبقي لأنّ `brain_commit_claim_guard` يقرأ الرسائل المُلتزَمة ولا تُعاد كتابةُ التاريخ لإرضاء حارس. | rag · governance | [`sahool-brain/gaps/registry.md`](registry.md) (صفّ `SAHOOL-AI-RAG-LIVE-001`) · التزام `952e68c4` | **alias → `SAHOOL-AI-RAG-LIVE-001`** — لا حالةَ لها ولا تُتابَع ولا تُغلَق استقلالاً؛ حالتُها حالةُ الصفّ القانونيّ. وعدُّها فجوةً ثانيةً يُضاعِف الحقيقة بلا سبب. وغيابُ بدائيّة alias في الدماغ مُسجَّلٌ فجوةَ حوكمةٍ مستقلّة: `BRAIN-HISTORICAL-GAP-ID-ALIAS-01`. |
| BRAIN-HISTORICAL-GAP-ID-ALIAS-01 | لا بدائيّةَ alias في الدماغ: معرّفٌ ذُكِر في رسالة التزام ثمّ تغيّرت تسميتُه القانونيّة يُجبِر على أحد سيّئين — صفٌّ ثانٍ يُضاعِف الحقيقة، أو إعادةُ كتابة التاريخ لإرضاء حارس. | brain · governance | [`brain_commit_claim_guard.py`](../../scripts/ci/brain_commit_claim_guard.py) (يقرأ الرسائل المُلتزَمة) · [`brain_duplicate_gap_identity_guard.py`](../../scripts/ci/brain_duplicate_gap_identity_guard.py) (يقارن عناوين متلاصقة، لا التكافؤ الدلاليّ عبر اسمين) | **open** — مقيسٌ على حالةٍ واقعة: `RAG-LIVE-01` ⇄ `SAHOOL-AI-RAG-LIVE-001`. والعلاجُ حقلُ `alias_of` يقرؤه الحارسان معاً، فيُقبَل المعرّفُ التاريخيّ ادّعاءً ولا يُعَدّ فجوةً. **خارج نطاق G0 بالقصد** — بناءُ نظام aliases داخل شريحة إسنادٍ يوسّعها إلى ما لم يُقَس. |
| LOCAL-DEV-TENANT-POINTS-PROVENANCE-01 | سبعُ نقاط UUID بمستأجِر `sahool-local-dev` في مجموعة Qdrant الحيّة، بجانب ٦٤ نقطةً مُهاجَرة. **تصنيفٌ فقط، بلا حذف.** | rag · provenance | [`rag-retrieval/main.py:133`](../../services/rag-retrieval/main.py) (`/v1/ingest`) · [`local-ai-rag/main.py:250`](../../services/local-ai-rag/main.py) (الكاتب الثاني) · [`production_qdrant.py:200`](../../services/sahool-platform/core/rag/production_qdrant.py) (`payload()`) · [`ai_rag_live_certification.py:131`](../../scripts/ci/ai_rag_live_certification.py) | **open — غيرُ قابل للحسم في هذا الاستنساخ** · السلسلة `sahool-local-dev` **لا ترد في أيّ ملفّ متعقَّب** (`git grep` صفر)، فالسبعةُ حالةُ مخزنٍ حيّ لا مصنوعةُ شجرة، ولا Qdrant هنا. **والمحسوم ساكناً ثلاثة:** ① كلا الكاتبين المدعومين يمرّان بـ`KnowledgeChunk.payload()` التي تكتب `page_content`+`metadata` — فنقطةٌ بلا `page_content` **لم يكتبها أيٌّ منهما**، وهي إذن أثرُ شكلٍ سابق لا «بيانات محلّيّة مشروعة» من شيفرة اليوم ② العزلُ مفروض بمُرشِّح `metadata.tenant_id ∈ {tenant, __global__}` فلا تُرى من مستأجِرٍ آخر — إلّا لو حملت `__global__`، وهو ما يمنعه `/v1/ingest` بـ403 اليوم لكنّه لا يُبطِل ما كُتِب قبله ③ **تدخل مسار الشهادة**: `ai_rag_live_certification` و`rag_live_parity_probe` يأخذان `--tenant-id` معاملاً، فإن شُهِد بـ`sahool-local-dev` صارت السبعةُ **جزءاً من مادّة إيصال الإصدار** — ولذلك تُصنَّف `release-relevant provenance` حتّى يُثبَت خلافه، والحذفُ ممنوع. **والفحص الحاسم بيد المالك:** جرد payload السبعة — وجودُ `page_content` وقيمةُ `metadata.tenant_id` يفصلان `stale-shape` عن `legitimate local-only` قطعاً. |
| HYBRID-FUSION-SCORE-NORMALIZATION-01 (B1a) | تطبيعُ مقياس BM25 قبل الدمج — درجاتٌ غير مُطبَّعة تجعل الوزن `0.7·dense + 0.3·sparse` يعني شيئاً آخر عمليّاً. | rag · retrieval | [`production_qdrant.py:710`](../../services/sahool-platform/core/rag/production_qdrant.py) (`retrieve` · `_expand_neighbors:756` · `_rerank:772`) · [`rag_live_parity_probe.py:102`](../../scripts/architecture/rag_live_parity_probe.py) · قياسُ المالك على subject `4556dc4c4bae` (**غير قابل للحلّ في هذا الاستنساخ**) | **open** — `measured fix exists out-of-tree / NOT_LANDED_ON_MAIN` — أثرُه مُبلَّغ: `min_jaccard` ٠٫١١١←٠٫٢٥٠ · `mean_jaccard` ٠٫٣٧٢←٠٫٤٧١ · `sparse_vs_fused` ٠٫٧٥٢←٠٫٨٦٧. **وأغلق حجمَ الدمج وحده، لا التكافؤ.** والشيفرةُ الحاملة له ليست في هذا الاستنساخ (`_max_sparse` لا وجود له هنا)، فالحالةُ مُسجَّلةٌ نقلاً موثَّق المصدر لا تحقّقاً. **وكان الحقلُ يقول `fixed`** والتحفّظُ نثرٌ بعده — وحقلُ الحالة هو ما يُقرأ ويُجمَع، فصُحِّح. وأوّلُ تصحيحٍ أدخل حالةً حرّة (`FIXED_OUT_OF_TREE`) في سجلٍّ يضبط مفرداته، فرُدَّ إلى `open` والتفصيلُ نصّاً: **الإصلاحُ قد يكون مُثبَتاً في تجربةٍ أو فرع، وليس حالةَ شجرةِ الإصدار.** والقياسُ السابق يبقى مُسجَّلاً `historical/out-of-tree measurement` ولا يصير حالةً لهذه الشجرة. ومقيسٌ على `783a0eb3`: `production_qdrant.py:748` ما يزال `fused_score = 0.7*dense + 0.3*sparse` بلا تطبيع، و`_max_sparse` معدومٌ في الشجرة كلّها. وBM25 ليست على مجال `[0,1]` كجيب التمام، فوزنُ ٠٫٣ لا يعني ٣٠٪ عمليّاً. |
| DIRECT-VS-CANONICAL-DENSE-SEMANTICS-01 (B1b) | `direct_dense` ≠ `rag_dense` على نفس الاستعلام. الشاهدُ الحاسم Q4/NDVI: `dense_vs_sparse = 1.0` داخل المسار القانونيّ بينما `direct_vs_rag_dense = 0.25` ⇒ تطبيعُ BM25 **لا يمكن** أن يكون السبب الجذريّ. | rag · retrieval | [`production_qdrant.py:710`](../../services/sahool-platform/core/rag/production_qdrant.py) (`retrieve` · `_expand_neighbors:756` · `_rerank:772`) · [`rag_live_parity_probe.py:102`](../../scripts/architecture/rag_live_parity_probe.py) · قياسُ المالك على subject `4556dc4c4bae` (**غير قابل للحلّ في هذا الاستنساخ**) | **open — الحاجب الحاليّ** · ولا تُعاد معايرةُ عتبات Jaccard ولا أوزانِ الدمج قبل إغلاقه: خفضُ العتبة إلى مستوى النظام يُخضِر الإيصال بتغيير معيار القبول لا ببلوغه، وتكبيرُ الـcorpus يُخفي العطل إحصائيّاً. **تشخيصٌ ساكن مُشتقٌّ من الشيفرة هنا** يُضيّق المشتبَهين: ① `retrieve()` يُدخِل جيراناً (`role=neighbor`) لم يُرشِّحهم بحثٌ كثيف ولا متناثر ② عمقُ المرشّحين ١٢ مقابل `final_k` في المِسبار المباشر ③ `_rerank` يزيد ٠٫٠٥ لكلّ تطابقٍ معجميّ فيُعيد الترتيب ④ هويّةُ القطعة تسقط إلى مُعرّف Qdrant عند غياب `metadata.chunk_id` ⑤ المِسبار نفسه يُسقِط من الجانب المباشر كلّ نقطة بلا `page_content` بينما يقبلها القانونيّ بـ`text`. |
| MEASURED-ON-SQUASH-FRESHNESS-01 | `measured_on` في مصنوعات `docs/architecture/` يُقرأ شهادةَ «قِيس على الشجرة المنشورة» وهو **ليس كذلك**: مع الدمج بـsquash يستحيل أن يحمل الالتزامَ الناتج — الرقم يُقاس داخل الـPR والالتزام النهائيّ لا يوجد بعد. مقيس: `main` عند `57890905` و`tenant_guc_scope_baseline.json` يحمل `8655548f` والشجرة نظيفة و`verify_all_generated --check` يخرج بصفر | governance · provenance | [`scripts/ci/claim_base_guard.py`](../../scripts/ci/claim_base_guard.py) (`report_staleness` · `staleness_is_reported_not_blocked`) · [`scripts/ci/tenant_guc_scope_guard.py`](../../scripts/ci/tenant_guc_scope_guard.py) (`main()` يستدعي `scan()` قبل التفرّع) · [`tests_v9/test_claim_base_guard.py`](../../tests_v9/test_claim_base_guard.py) (`test_freshness_authority_is_re_derivation_not_the_stamp`) · جلسة `017Ee5NDNog8QCmQedcxMzW3` | **fixed (دلالةً لا سلوكاً)** — الفجوة **حقيقيّة وغير حاجبة تحت العقد الحاليّ**: `measured_on` **إشارةُ إسناد** لا سلطةَ طزاجة، والسلطة قائمةٌ فعلاً وأقوى — الحارس المالك **يُعيد الاشتقاق** من الشجرة الحاضرة ويقارن الناتج بالأساس. وثُبِّتت الدلالة بستّة تأكيدات، منها زوجٌ دلاليّ A/B مُسجَّلُ الطفرتين في [`guard_mutation_registry.json`](../../docs/architecture/guard_mutation_registry.json) تحت `tenant_guc_scope_guard.py[2..3]`: (أ) ختمٌ بائت + اشتقاقٌ مطابق ⇒ **يمرّ** — تقتلها ترقيةُ البيات إلى حجب · (ب) ختمٌ بائت + اشتقاقٌ مختلف ⇒ **يحجب** — تقتلها مقارنةُ الأساس بنفسه. وكلتاهما مقيسةٌ بالزرع الفعليّ لا بالقراءة. **والمرفوض ثلاثة:** اشتراطُ `measured_on == HEAD` (يُبيت كلّ قياسٍ عند أيّ التزام فيصير كلّ PR churn، وغيرُ قابل للتحقيق داخل PR مع squash) · تدويرُ SHA بعد كلّ دمج · وبصمةُ مدخلاتٍ **مستقلّة تُستخدَم سلطةَ طزاجةٍ موازيةً لإعادة الاشتقاق** (محرّكٌ ثانٍ للحقيقة، **وأضعف**: تلتقط تغيّر المدخلات ولا تلتقط تغيّر المولّد نفسه). والمرفوض هو **هذا الدور** لا الإسناد المُعنوَن بالمحتوى في ذاته: بصمةٌ تُسجَّل **إسناداً** بجانب إعادة اشتقاقٍ تبقى هي الحاكمة مقبولةٌ متى أفادت. **حدّ الصدق:** هذا يُثبِّت الدلالة ويمنع قراءتها شهادةً — ولا يجعل الختم صادقاً عن الشجرة المنشورة، لأنّه لا يمكن أن يكون كذلك بالبناء. **ونصُّ المدخل الأقدم محفوظاً بلا حذف** (كان صفّاً ثانياً بنفس الهويّة، موروثاً من قبل هذه الشريحة وموجوداً في `main`؛ دُمِج هنا بعلاج الحارس نفسه: «ادمج العنوانين في مدخل واحد يحفظ نصّيهما»): **fixed (دلالةً لا سلوكاً)** — الفجوة **حقيقيّة وغير حاجبة تحت العقد الحاليّ**: `measured_on` **إشارةُ إسناد** لا سلطةَ طزاجة، والسلطة قائمةٌ فعلاً وأقوى — الحارس المالك **يُعيد الاشتقاق** من الشجرة الحاضرة ويقارن الناتج بالأساس. وثُبِّتت الدلالة بأربعة تأكيدات مُكذَّبة بالزرع (نزعُ الاشتقاق ⇒ أحمر · ترقيةُ البيات إلى حكم ⇒ أحمر). **والمرفوض ثلاثة:** اشتراطُ `measured_on == HEAD` (يُبيت كلّ قياسٍ عند أيّ التزام فيصير كلّ PR churn، وغيرُ قابل للتحقيق داخل PR مع squash) · تدويرُ SHA بعد كلّ دمج · وبصمةُ مدخلاتٍ سلطةً موازية (محرّكٌ ثانٍ للحقيقة، **وأضعف**: تلتقط تغيّر المدخلات ولا تلتقط تغيّر المولّد نفسه). **حدّ الصدق:** هذا يُثبِّت الدلالة ويمنع قراءتها شهادةً — ولا يجعل الختم صادقاً عن الشجرة المنشورة، لأنّه لا يمكن أن يكون كذلك بالبناء. |
| CAPABILITY-EVIDENCE-LISTS-TRUNCATE-SILENTLY-01 | سقف الأدلّة ١٠٠ في خريطة القدرات كان يقتطع **بصمت**: إضافة اختبارٍ جديد تُخرِج شاهداً قائماً من القائمة بلا أيّ إعلان — والقارئ يعدّ القائمة جرداً وهي عيّنة (مقيس: `SEC-001.database` أسقط ٧٤٣ صفّاً صامتاً · `SAT-003` أسقط 25/36/69 عبر ثلاثة أبعاد) | capability-registry · governance | [`scripts/ci/capability_mapping_engine.py`](../../scripts/ci/capability_mapping_engine.py) (`cap_evidence_dimensions`) · [`tests/architecture/test_capability_mapping_engine.py`](../../tests/architecture/test_capability_mapping_engine.py) (`test_evidence_cap_truncation_is_declared_not_silent`) · قِيست أوّلاً في جلسة `017Ee5NDNog8QCmQedcxMzW3` (`deb4bab9`) | **fixed (TOOL_PROVEN)** — الاقتطاع صار **مُعلَناً**: حقل `evidence_truncated` لكلّ بُعدٍ يتجاوز السقف يحمل عدد المُسقَط، والترتيب حتميّ قبل القصّ، والسقف **لم يُرفَع** (رفعه يؤجّل الصنف لا يُغلقه). طفرة العودة إلى القصّ الصامت مُثبَتة بالتكذيب، وطبقة ثانية تقرأ الخريطة المشحونة نفسها (`SAT-003` يحمل الإعلان). **حدّ الصدق:** الإعلان يكشف الاقتطاع ولا يُعيد المُسقَط — القائمة تبقى عيّنة، لكنّها الآن عيّنة تقول إنّها عيّنة. |
| VISUAL-FIXME-DEBT-UNGUARDED-01 | `test.fixme` يجعل الاختبار **يُعَدّ ولا يُنفَّذ**، فيقول تقرير Playwright «0 failed» صادقاً حرفيّاً وكاذباً دلاليّاً — ولا شيء كان يمنع أن يصير الاثنان ثلاثةً ثمّ عشرة | frontend/e2e · governance | [`scripts/ci/visual_fixme_baseline_guard.py`](../../scripts/ci/visual_fixme_baseline_guard.py) · [`tests_v9/test_visual_fixme_baseline_guard.py`](../../tests_v9/test_visual_fixme_baseline_guard.py) · `.github/workflows/capability-governance.yml` (خطوة *Visual test debt must not accumulate*) | **fixed (TOOL_PROVEN)** — راتشِت يحجب الزيادة **والنقصان بلا خفض الأساس** (سقفٌ مُرتخٍ يبتلع عودة الدَّين صامتاً)، ويشترط لكلّ `fixme` سبباً ومرساة فجوة. ٥/٥ طفرات مُثبَتة بالتكذيب، ١٢ اختبار وحدة. **حدّ الصدق:** يحرس **تراكم** الدَّين لا يُغلِقه — الاختباران يبقيان `MAPHUB-WEBGL-VISUAL-DEBT-01`. |
| MAPHUB-WEBGL-VISUAL-DEBT-01 | اختبارا رسم المضلّع (`measure-area`) والخطّ (`measure-length`) عبر مؤشّر حقيقيّ مُعطَّلان: تهيئة Terra Draw لا تكتمل تحت SwiftShader headless (`data-draw-ready` لا يُرفَع) | frontend/e2e | [`frontend/e2e/maphub-webgl.spec.ts`](../../frontend/e2e/maphub-webgl.spec.ts) (سطرا `test.fixme`) · [`frontend/src/lib/measureDrawWiring.test.ts`](../../frontend/src/lib/measureDrawWiring.test.ts) · `scripts/ci/visual_fixme_baseline_guard.py` (خطّ الأساس ٢) | **open (دَينٌ مُعلَن ومحروس)** — مسار القيمة نفسه (هندسة ⇒ turf ⇒ مُنسِّق ⇒ قيمة معروضة) محروسٌ **حتميّاً** في `measureDrawWiring.test.ts`؛ الناقص هو الطبقة E2E الحقيقيّة (مؤشّر متصفّح ⇒ MapLibre ⇒ Terra Draw). لا يُنزَع `fixme` لإخضار CI — ذلك تزييفُ إغلاق يُنتِج اختباراً هشّاً. الإغلاق يحتاج تهيئةً مستقرّة headless (أو runner بـGPU): قياسٌ بيئيّ لا نصّيّ. |
| FRONTEND-LINT-DEBT-UNGUARDED-01 | `eslint` هنا يُبلِّغ **تحذيراً** لا خطأً على `no-explicit-any` و`no-unused-vars`، فوظيفة *Frontend Typecheck* تخرج خضراء ومعها ١٠٠ تحذير — وGitHub يقطع العرض عند **عشرة لكلّ وظيفة**، فيقرأ المالك عيّنةً بوصفها جرداً. عدّادٌ غير مرئيّ وغير محجوب معاً | frontend · governance | [`scripts/ci/frontend_lint_debt_guard.py`](../../scripts/ci/frontend_lint_debt_guard.py) · [`tests_v9/test_frontend_lint_debt_guard.py`](../../tests_v9/test_frontend_lint_debt_guard.py) · #824 (`fc88d494`) | **fixed (TOOL_PROVEN)** — راتشِت **لكلّ قاعدة** لا مجموعاً (المجموع وحده يسمح باستبدال عشرة `any` بعشرة `no-unsafe-assignment` بلا أثر)، يحجب الزيادة **والنقصان بلا خفض السقف**. ٥/٥ طفرات مُكذَّبة · ١١ اختبار وحدة. وبندُه الثاني **حجبَ صانعه** أوّل سدادٍ حقيقيّ (٨٢ ⇒ ٧٢ فاحمرّ حتى خُفِض إلى 41/31). **حدّ الصدق:** يحرس **تراكم** الدَّين لا يُصلحه — الـ٧٢ الباقية دَينٌ مفتوح، و«لم يُقَس» ليس «لم ينمُ» (تقريرٌ غائب يُفشِله بدل أن يُقرأ صفراً). |
| TEXT-GUARD-ANCHORED-IN-THE-WRONG-FILE-01 | حارسٌ نصّيّ يقرأ مرساةً في ملفٍّ **لا تعيش فيه الخاصّيّة** يمرّ لسببٍ غير سببه المُعلَن — فيُقرأ ضماناً وهو صدفة، ثمّ يُحمِرّ على أوّل من ينظّفها. وخطره أنّه يظهر عند **تحسّن** الكود لا عند انكساره، فيُقرأ الانحدارُ في التحسين لا في الحارس | ci/governance · frontend | حالتان مقيستان في #824 (`fc88d494`): [`services/sahool-platform/tests/test_ui14_field_workspace_route_shell_guard.py`](../../services/sahool-platform/tests/test_ui14_field_workspace_route_shell_guard.py) (مرساة `FieldWorkspaceMapCard` في `App.tsx` والخاصّيّة في `FieldWorkspaceRouteShell.tsx`؛ مرّت على `lazy(...)` ميّت) · [`frontend/src/components/maphub/DrawingTools.static.test.ts`](../../frontend/src/components/maphub/DrawingTools.static.test.ts) (شرطُ `(poly as any)` حرفيّاً، فعاقبَ تضييق النوع) | **open (الحالتان مُصلَحتان، والصنف بلا حارس)** — كلتاهما أُعيد توجيهها إلى موضع الخاصّيّة وصارت **أشدّ** لا أضعف، ومُكذَّبة بطفرات (نزعُ استيراد القشرة يُحمِر · إعادةُ ربطٍ في `App.tsx` تُحمِر · نزعُ حراسة `!isPivot` يُحمِر). لكنّ **لا شيء يمنع الصنف من العودة**: لا قياس يسأل «هل المرساة في الملفّ الذي تعيش فيه الخاصّيّة؟». وظهورُ حالتين مستقلّتين في شريحةٍ واحدة هو المؤشّر على أنّه صنفٌ لا صدفتان. الإغلاق يحتاج قياساً لا فقرة. |
| ACTION-PIN-HALF-UPGRADED-01 | ترقيةُ تثبيتٍ تُبدّل بعضَ مواضعه: كلّ موضعٍ يبقى مثبَّتاً ببصمةٍ كاملة، فيبقى `github_actions_policy_guard` أخضر — لأنّه يسأل «أمثبَّتٌ ببصمة؟» لا «أبصمةٌ واحدة؟». الصنف **خارج مدى البوّابة القائمة كلّيّاً** | ci/supply-chain · governance | [`scripts/ci/action_pin_agreement_guard.py`](../../scripts/ci/action_pin_agreement_guard.py) · [`tests_v9/test_action_pin_agreement_guard.py`](../../tests_v9/test_action_pin_agreement_guard.py) · `.github/workflows/sahool-production-gates.yml` (خطوة *Every pin of an action must agree*) | **fixed (TOOL_PROVEN)** — وقع الصنف **مرّتين مقيستين**: `#823` (سبع مراسٍ لا خمس، أمسكها فحصٌ خارجيّ لا بوّابة) · والحزمة المقترَحة في `#827` التي تُبدّل `ci.yml` وحده (**٣ من ٢٣**). بندان: **بصمةٌ واحدة لكلّ عمل** (بأساس تباعدٍ **بعدده** لا بوجوده، يمنع الزيادة والنقصان بلا خفض) · **وتعليقُ الوسم يوافق البصمة** (`@<بصمة v7> # v4` يُقرأ وسماً ويُبنى عليه). ٥/٥ طفرات مُكذَّبة — أُولاها تُعيد إنتاج سلوك الحزمة بالحرف — و١٢ اختبار وحدة. **حدّ الصدق:** يقيس **اتّساق** التثبيت لا **صحّته**؛ أنّ البصمة هي الوسم المكتوب بجانبها ادّعاءٌ عن مستودعٍ أعلى لا يُثبَت من هنا. |
| KNOWLEDGE-CANONICAL-CONSUMPTION-01 | سلسلة M2.2⇒M2.6 مقطوعة **باسمَي مفتاحين**: M2.6 يقرأ `status` وM2.2 يُصدِر `quality_status`؛ ويقرأ `maximum_safe_event_depth_mm` **ولا يكتبه أيّ ملفٍّ إنتاجيّ في الشجرة** (موضعه الوحيد تجهيزةُ اختبار M2.6 نفسه). فمُنتَجٌ صحيحٌ ومُتحقَّق يُرفَض | irrigation/canonical | [`api/canonical_root_zone_profile.py`](../../services/sahool-platform/api/canonical_root_zone_profile.py) · [`api/canonical_sprinkler_runoff_capability.py`](../../services/sahool-platform/api/canonical_sprinkler_runoff_capability.py) · [`tests_v9/test_canonical_root_zone_to_sprinkler_contract.py`](../../tests_v9/test_canonical_root_zone_to_sprinkler_contract.py) · [`tests_v9/test_canonical_knowledge_to_hourly_mpc_runtime.py`](../../tests_v9/test_canonical_knowledge_to_hourly_mpc_runtime.py) | **fixed (EXECUTION_PROVEN)** — العطل والإصلاح كلاهما مُثبَتٌ **بالتشغيل**: النداء نفسه أعاد `blocked` قبل و`verified · max_event=48.6` بعد. أُدخِل `root_zone_refill_cap_mm` حقلاً قانونيّاً في M2.2 (وسُمّي **سقفَ ملءٍ** لا حدَّ حدثٍ نهائيّاً — المعدّات والانجراف والميل والرياح قيودٌ downstream)، ويستهلكه M2.6 بلا اشتقاقٍ من `raw_mm`. واختبار السلسلة M2.2⇒M2.6⇒M2.8⇒M3 **مُكذَّب بطفرتين في الكود المنتَج**. **حدّ الصدق:** `build_canonical_sprinkler_runoff_capability` **لا مُستدعيَ له** في الشجرة؛ مُنتَجه يبلغ M3 عبر التخزين — فهو عقدٌ مقطوعٌ في مسارٍ غير مُستدعىً بعد، لا عطلٌ يقع اليوم على مستخدم. وحرّاسُه الثلاثة **غير مُواصَفين بطفرات** (لا اختبار يُشغّلها؛ تُستدعى مباشرةً في `ci.yml`). |
| RAG-ANSWERS-AN-OPERATIONAL-FACT-01 | جدولُ المصادر يقول إنّ الحقيقة التشغيليّة (ET0 الآن · السعة المتبقّية · الحدّ الآمن · هل القرار مُصرَّح) لا يجيب عنها الاسترجاع — **ولم يكن لذلك إنفاذٌ إطلاقاً**. ومُخرَجُ الاسترجاع نصٌّ معقولٌ دائماً، فإجابتُه عن حدٍّ آمنٍ تُنتِج رقماً يبدو صحيحاً ولم يمرّ بالميل ولا التسرّب ولا شهادة الحزمة | knowledge/rag | [`scripts/ci/rag_operational_boundary_guard.py`](../../scripts/ci/rag_operational_boundary_guard.py) · [`tests_v9/test_rag_operational_boundary_guard.py`](../../tests_v9/test_rag_operational_boundary_guard.py) | **guarded (٦/٦ طفرة)** — الحدّ مفروضٌ الآن على ٣ وحداتٍ تبلغ الاسترجاع فعلاً، و«الحقيقة التشغيليّة» مُعرَّفةٌ بالسجلّ لا بقائمةٍ ثانية. **حدّ صدق:** لا خرقَ قائماً اليوم — قِيس قبل كتابة الحارس، فهذا يمنع انحداراً ولا يُصلِح عطلاً حاضراً. |
| KNOWLEDGE-PROVENANCE-01 | مُنتِجاتٌ قانونيّة بلا مرساةٍ زمنيّة (`canonical_sprinkler_runoff_capability` و`canonical_irrigation_capability_graph`)، فبند الطزاجة في المُحلِّل **معطَّلٌ بصمت**: كلّ عقدٍ يُعلِن `max_age_seconds` يحجب دائماً بـ`FRESHNESS_UNMEASURABLE` ولا أحد يعرف لماذا | knowledge/canonical | [`scripts/ci/knowledge_provenance_guard.py`](../../scripts/ci/knowledge_provenance_guard.py) · [`tests_v9/test_knowledge_provenance_guard.py`](../../tests_v9/test_knowledge_provenance_guard.py) | **fixed (٦/٦ طفرة)** — أُضيف `generated_at`/`effective_at` للمُنتِجَين، ويفرض الحارس الحدّ الأدنى للنَّسَب على المُخرَج لا على الـdataclass. و`producer_digest_field` صار مُعلَناً إلزاماً بعد أن أطلق افتراضٌ صامت على مِلَفّ منطقة الجذر. |
| SHADOW-SOURCE-OF-TRUTH-01 | مفتاحٌ واحد بمُنتِجَين: `maximum_safe_depth_mm_event` كان اسماً واحداً لقيمتين مختلفتي المعنى — قيدُ الجريان عند قدرة الرشّ، و`min(machine_depth, safe_event_depth)` عند الرسم البيانيّ. فنَسَبُ إحداهما إلى الأخرى كذب | knowledge/canonical | [`scripts/ci/shadow_source_of_truth_guard.py`](../../scripts/ci/shadow_source_of_truth_guard.py) · [`tests_v9/test_shadow_source_of_truth_guard.py`](../../tests_v9/test_shadow_source_of_truth_guard.py) | **fixed (٦/٦ طفرة)** — انقسم المفتاح إلى `sprinkler.*` و`irrigation.*` ولكلٍّ مُنتِجُه. ولم يظهر العطل بالقراءة بل **ساعةَ ربط المُنسِّق**؛ والحارس يجعل ظهوره لا يعتمد على أن يربط أحدٌ شيئاً، ويسدّ أرخصَ طريقٍ إليه: عقدٌ يُسمّي مصدراً غير المُسجَّل. |
| UNDECLARED-CONTEXT-DEPENDENCY-01 | مَن يقرأ المعرفة **عبر المُحلِّل** خارج مدى حارس الالتفاف تماماً، فيستطيع طلبَ مفتاحٍ بـ`ctx.require(...)` بلا إعلانٍ في أيّ عقد — فتعود التبعيّة إلى رأس كاتبها، وهو ما بُنيت الطبقة لإخراجه منه | knowledge/contracts | [`scripts/ci/undeclared_context_dependency_guard.py`](../../scripts/ci/undeclared_context_dependency_guard.py) · [`tests_v9/test_undeclared_context_dependency_guard.py`](../../tests_v9/test_undeclared_context_dependency_guard.py) | **guarded (٦/٦ طفرة)** — وأوّل تشغيلٍ قاس **صفر طلب** لأنّ المُنسِّق كان يحلّ العقد ثمّ يُهمِل القيمة؛ فأُصلِح السبب لا الحارس: صار يستهلكها ويُصدِر `knowledge_context` بنَسَبها، ويحرس ذلك تأكيدٌ يشترط طلباً حقيقيّاً واحداً على الأقلّ. |
| KNOWLEDGE-RELATION-01 | العلاقات موزَّعة في النماذج والهجرات والعقود بلا سجلٍّ موحَّد؛ وثلاثيّةٌ تُكتَب مرّةً تَبيت بصمت لأنّ لا شيء يقول متى خالفتها الشيفرة | knowledge/relations | [`docs/architecture/knowledge_relation_registry.json`](../../docs/architecture/knowledge_relation_registry.json) · [`scripts/ci/knowledge_relation_registry_guard.py`](../../scripts/ci/knowledge_relation_registry_guard.py) | **guarded (٧/٧ طفرة)** — سُجِّلت علاقةٌ **قائمة** لا مُخترَعة: `REQUIRED_LINKS` تحكم فعلاً «أضعف حلقة» و`operational_eligible`. والسلسلة المُعلَنة تُقابَل بالثابت المقروء بـ`ast`، فانحرافُها يُحمِرّ — وهذا هو الفرق عن Ontology تقليديّة. **حدّ صدق:** علاقةٌ واحدة فقط؛ والتوسيع يشترط أن يكون لكلّ علاقةٍ ثابتٌ منفَّذ يُقابَل بها. |
| SOT-PROVENANCE-UNVERIFIED-01 | أدلّة Live-PG كانت **موقَّعة** ولم تكن **مُتحقَّقاً منها**: التوقيع يُنتَج في الوظيفة ولا شيء يُعيد التحقّق منه بأداةٍ رسميّة، ولا يربط مجموعةَ الملفّات المرفوعة بإعلانٍ مُغلَق — فملفٌّ زائد أو ناقص يمرّ | ci/provenance · security | [`scripts/ci/sot_provenance_guard.py`](../../scripts/ci/sot_provenance_guard.py) · [`scripts/ci/sot_evidence_manifest.py`](../../scripts/ci/sot_evidence_manifest.py) · [`tests_v9/test_sot_provenance_guard.py`](../../tests_v9/test_sot_provenance_guard.py) · `docs/architecture/sot_provenance_policy.json` · `.github/workflows/ci.yml` (وظيفة Live PG) | **fixed (TOOL_PROVEN)** — إغلاقٌ **تامّ**: manifest قانونيّ بايتاً ببايت، وبصمةُ كلّ موضوع، و«لا ملفّ خارج الإعلان»؛ ثمّ تحقّقٌ تشفيريّ بـ`gh attestation verify` بجذر ثقةٍ مُمرَّر صراحةً وworkflow/OIDC/‏source-digest مشروطة. السجلّ يبدأ `BLOCKED/L0` ولا يصير `VERIFIED` إلّا بإغلاقٍ كامل، والمستويات L0..L5 **مشتقّة**. **٨/٨ طفرات مُثبَتة بالتكذيب** (وهو نادر: الكتالوج يقيس ٢١٨ حاجباً و٨ مُثبَتة) · ٩ اختبارات وحدة. **حدّا صدق:** الأدلّة تحت `pull_request` مسقوفةٌ بـ**L3** لأنّها تُقاس على دمجٍ وهميّ لا على `main`؛ وبصمةُ `gh 2.93.0` لم تُتحقَّق من مصدرٍ أعلى — لكنّ الفحص يجري على البايتات المُنزَّلة، فبصمةٌ خاطئة **تُفشِل التثبيت** ولا تُمرِّر ثنائيّاً آخر. |
| DECISION-SOR-PRE-CUTOVER-ROLE-CERTIFICATION | تصديق فصل أدوار القاعدة (قراءة فقط) قبل أيّ REVOKE — مصفوفة حيّة: `current_user`/`session_user` عبر اتّصالَي المنصّة/الخدمة · مالك الجدول · grants (جداول+sequences+functions) · role memberships · `rolsuper`/`rolbypassrls` · توفّر `SET ROLE` | decision-service/deploy | [`decision_sor_role_certify.py`](../../services/decision-service/decision_sor_role_certify.py) · اختبار PG حقيقيّ `test_decision_sor_role_certify_pg.py` · [`DECISION_SOR_CUTOVER.md`](../../docs/runbooks/DECISION_SOR_CUTOVER.md) | **TOOL_PROVEN / LIVE_RUN_PENDING** — الأداة مُبرهَنة على PG في CI (دوران متمايزان ⇒ `role_separation_confirmed=true`؛ دور مشترك ⇒ `false` = «لا REVOKE»). المتبقّي **تشغيليّ**: تشغيلها على staging/prod بالاتّصالَين الفعليَّين. **precursor إلزاميّ** لـ`DECISION-SOR-CUTOVER-WIRING-01` و`DEPLOYED-DECISION-SOR-PROMOTION`. |
| PG-APP-ROLE-TRANSITIVE-PRIVILEGE-CLOSURE-01 | حارس أدلّة PG الحيّ كان يُثبِت **خصائص الصفّ المباشرة** على `sahool_app` وحدها؛ و`pg_auth_members` يمنح صلاحياتٍ موروثة أو `SET ROLE` عبر سلاسل عضويّة لا تظهر في تلك الخصائص — فحدُّ الصلاحية المقيس كان أضيق ممّا يُنفَّذ فعلاً | ci/live-pg · security | [`scripts/ci/live_pg_role_closure_guard.py`](../../scripts/ci/live_pg_role_closure_guard.py) · [`tests_v9/test_live_pg_role_closure_guard.py`](../../tests_v9/test_live_pg_role_closure_guard.py) · `.github/workflows/ci.yml` (وظيفة `live-pg-fake-connection-proofs`، خطوة *Prove the evidence role has no direct or transitive role memberships*) | **fixed (TOOL_PROVEN + LIVE_RUN_PROVEN)** — استعلامٌ تكراريّ على `pg_auth_members` يشترط أن يكون الإغلاق العبوريّ **فارغاً** لدور الأدلّة المخصَّص، ويحفظ `ADMIN`/`INHERIT`/`SET` لكلّ منحة. أشدّ عمداً من نموذج تفويضٍ إنتاجيّ: عضويّةٌ خاملة اليوم تصير نافذةً بتغيير خيارٍ لاحقاً بلا مسّ خصائص الدور. فشلٌ مغلق على غياب الدور/`psql`/جسمٍ مشوَّه، والمصنوعة المرفوعة تحمل **أسباباً ثابتة** لا تشخيصات libpq (مضيف/منفذ/كلمة مرور). ٤/٤ طفرات مُثبَتة بالتكذيب · ٩ اختبارات وحدة. **والحدّ سقط بقياسٍ لا بمرور الوقت:** أوّل تشغيل (وظيفة `Live PG Proofs` في `31424807525`، PR #821) خضراء على PostgreSQL 16 حيّة ⇒ `sahool_app` يحمل **صفر عضويّة عبوريّة** فعلاً. والمصنوعتان مفصولتان: `live-pg-evidence-…` (٤ ملفّات) و`live-pg-evidence-attestation-…` موقَّعة في Rekor (`logIndex=2412021383`). **وما يبقى غير مقيس:** هذا إعدادُ CI لا إعدادٌ إنتاجيّ — الدور المُشهَّد هو دور الأدلّة المخصَّص وحده. |
| MANIFEST-REGISTRY-01 | بيانات `docs/architecture/*.json` التحكيمية كانت تدخل بلا سجلّ مشتقّ ولا تصنيف governed/legacy | governance/docs-architecture | [`scripts/ci/manifest_registry_guard.py`](../../scripts/ci/manifest_registry_guard.py) · [`docs/architecture/manifest_registry.json`](../../docs/architecture/manifest_registry.json) · [`tests_v9/test_manifest_registry_guard.py`](../../tests_v9/test_manifest_registry_guard.py) | **fixed** — الجرد يُشتقّ من `git ls-files` لا من قائمة يدوية؛ الراتش يفرض `schema + version + adjudicated_on` على كلّ بيان جديد؛ والعقد يزرع بياناً غير مسجَّل فيثبت أنّ الفحص يقبضه ثم يعود أخضر بعد إزالته؛ صلاحيات الدفع بلا workflow scope فالفحص يسري في CI عبر الاختبار وباك-ستوب المكنسة لا بخطوة workflow. |
| CAP-INT-004-INTEGRATION | INT-004 «تكاملات آلات خارجيّة» — قُسِّم إلى: **INT-004A** محوِّل أثر ISOXML مُدام (أُغلِق) · **INT-004B** نقل الجهاز (CAN/ISOBUS) · **INT-004C** تأكيد استهلاك/تنفيذ الآلة (مفتوحان) | precision/platform | v216 [`migrations/v216_machinery_export.sql`](../../migrations/v216_machinery_export.sql) (machine_control_profiles SoR + machinery_export_artifacts append-only) · [`api/machinery_export.py`](../../services/sahool-platform/api/machinery_export.py) `generate_export_package`/`resolve_persisted_profile`/`package_taskdata` · [`routers/prescriptions.py`](../../services/sahool-platform/api/routers/prescriptions.py) `export`:337 مطويّ (`?format=isoxml&machine_profile_id=…` قانونيّ + `&artifact_id=…` تنزيل) · [`tests/test_machinery_export.py`](../../services/sahool-platform/tests/test_machinery_export.py) (15) · `precision.yaml::INT-004.scope` | **INT-004A CLOSED_IN_CODE + PG16_PROVEN / INT-004B+C OPEN** — المسار القانونيّ (مطويّ في `export` احتراماً لـRatchet، صافي مسارات=صفر) `GET .../export?format=isoxml&machine_profile_id=…` (EQUIPMENT_MANAGE) يحلّ ملفّ تحكّم مُدام (SoR معزول بالمستأجِر FORCE-RLS)، يتحقّق fail-closed عبر عقد ISOXMLTask، يولّد TaskData، **يغلّفه ZIP حتميّاً** (checksum قابل للتكرار)، **يُديم أثراً append-only غير قابل للتحوير مُتماثِلاً** (dedup على sha256) بلقطة ملفّ تعريف مجمّدة + package_bytes + sha256؛ و`&artifact_id=…` ينزّل أثراً مُداماً. مُثبَت حيّاً على PG16 (11 برهان جدول: RLS/WITH CHECK/append-only/CHECK/FK/updated_at + E2E إدراج/تنزيل مطابق بايتيّاً + عزل مستأجِر). المسار المضمّن (بلا profile/artifact) محجوب خلف PLATFORM_MANAGE (تطويريّ، لا يُدام). **حدّ الصدق:** إنتاج+إدامة الحزمة عند حافّة المنصّة فقط — `adapter_implemented`/`artifact_generation_verified`/`machine_upload_package_verified`=true؛ **لا** اتّصال بمُتحكّم/نقل CAN-ISOBUS/ادّعاء استهلاك ⇒ `device_delivery`/`machine_consumption`/`physical_execution`/`runtime`/`production`=false. **مفتوح:** INT-004B نقل الجهاز + INT-004C تأكيد التنفيذ. |
| DEPS-DEPENDABOT-4 | أربع ثغرات Dependabot على main (١ high postcss + ٣ moderate react-router): react-router الكاسر (v6→v7) كان مُؤجَّلاً في #628 | frontend/deps | Dependabot alerts؛ `frontend/package.json`؛ `npm audit` | **CLOSED** #633 (`63a70a7`) — postcss 8.5.15→8.5.23 · react-router 6.30.4→**8.3.0** (react-router-dom أُزيل، مُدمَج في v8؛ 21 ملفّاً `-dom`→`react-router` + node 20→22). v8.3.0 وحدها نظيفة من كلّ الاستشارات (v7.18 يقع في نطاق RSC-CSRF high). `npm audit`=0 · vitest 1291/1291. المالك اختار الترقية الكاملة (AskUserQuestion). صدق: RSC-CSRF/SSR-hydration لا تخصّان SPA عميل Vite. |
| GAP-B1-ALLFIELDS-SEQ | `all_fields` كان يستدعي raster-service تسلسليّاً لكلّ حقل (أسوأ حالة N×15s) | vegetation-analysis-service | بحث عميق 2026-07-25؛ [`routers/analysis.py`](../../services/vegetation-analysis-service/routers/analysis.py) `all_fields` | **CLOSED** #632 (`71ddbc8`) — `asyncio.gather` بتزامن محدود `Semaphore(8)` + `zip(strict=True)` (نفس النتائج، الترتيب محفوظ، زمن الجدار = أبطأ سلسلة). |
| GAP-B2-YIELD-MAX | غلّة الحصاد في التتبّعيّة كانت `MAX(actual_yield_t_ha)` — تتحيّز صعوديّاً مع حصاد جزئيّ/إعادة تسجيل | sahool-platform/الحقول | بحث عميق 2026-07-25؛ [`routers/fields.py`](../../services/sahool-platform/api/routers/fields.py) `field_input_traceability` | **CLOSED** #632 (`71ddbc8`) — `SELECT actual_yield_t_ha … ORDER BY outcome_recorded_at DESC NULLS LAST LIMIT 1` (أحدث نتيجة مُسجَّلة؛ العمود من v49). |
| GAP-B3-RECONCILE-DOUBLE | مصالحة النتائج كانت تعدّ قراراً موصوفاً في الجدولَين مرّتَين في `by_kind`/`success_rate` | decision-service | بحث عميق 2026-07-25؛ [`outcome_reconcile.py`](../../services/decision-service/outcome_reconcile.py) | **CLOSED** #632 (`71ddbc8`) — فكّ العدّ المزدوج بمفتاح `decision_id` (أولويّة outcome_record عبر setdefault؛ صفوف بلا مفتاح تُعدّ منفردةً) + اختبار `test_by_kind_dedups_shared_decision_id`. |
| GAP-F1-MAPHUB-PINS | دبابيس استكشاف MapHub كانت حالة جلسة محلّيّة تضيع عند التحديث (لا حفظ خادميّ) | frontend/MapHub | بحث عميق 2026-07-25؛ [`MapHub.tsx`](../../frontend/src/sections/MapHub.tsx) | **CLOSED** #632 (`71ddbc8`) — دائمة على الخادم (v94) عبر `useScoutingPins`/`useCreateScoutingPin` (إدراج تفاؤليّ+تراجُع، RLS)؛ حارس ساكن `MapHubScoutingPinsPersistence.static.test.ts`. الفراغ من القاعدة يبقى فراغاً (لا اختراع). |
| GAP-F2-STALE-COMMENTS | تعليقات scouting بائدة في MapHub.tsx/HubMap.tsx تصف الحالة المحلّيّة القديمة | frontend/MapHub | بحث عميق 2026-07-25 | **CLOSED** #632 (`71ddbc8`) — صُحِّحت لتعكس الحفظ الخادميّ الدائم. |
| GAP-F3-DEAD-IMPORTS | استيرادا `lazy()` ميّتان (FieldManagementPage/FieldMapCenter) في App.tsx | frontend | بحث عميق 2026-07-25؛ [`App.tsx`](../../frontend/src/App.tsx) | **CLOSED** #632 (`71ddbc8`) — حُذفا. |
| MIGRATE-ID-COLLISION | تصادم معرّفات هجرة بين نظامين: `migrations/vNNN_*.sql` و`alembic/versions/vNNN_*.sql` (v101 farm_budget_costing↔field_runtime_cohesion · v105 enterprise_imagery↔marketplace_ecosystem — نفس الرقم، ملفّان مختلفان لكلّ نظام). لا يكسر التنفيذ فوراً (لكلّ runner نطاقه) لكن قنبلة صامتة: غموض «vNNN applied»/rollback/التحقيقات/مطابقة البيئات | migrations/ + alembic/versions/ | تدقيق عميق مصحَّح 2026-07-20 (المالك) | **CLOSED 2026-07-20** — **الفضاءان مفصولان: alembic = `NNNN_*.py` حصراً · migrations = `vNNN_*.sql` حصراً.** الزومبيّان (`alembic/versions/v101_field_runtime_cohesion.sql` · `v105_marketplace_ecosystem.sql`) — بقايا ما قبل phase19 — أُثبِتت ميّتَين بثلاثة محاور (لا في MANIFEST · لا مُشغّل يطبّقهما · خارج سلسلة alembic 0001→0002 · صفر استعمال لجداولهما الثلاثة · shared/field_runtime_cohesion.py منطق صرف بلا DB I/O · marketplace canonical = migrations/v121) فأُزيلا. حارس منع انحدار + برهان سلبيّ في `tests/migrations/test_phase19_migration_manifest_unification.py` (`test_no_cross_system_migration_id_collision_between_alembic_and_migrations` + `..._negative_proof`). |
| BRANCH-RECONCILE-PENDING | فرعان متباعدان عند `84e14f0`: `main` (+7 hardening) و`claude/code-review-34hO3` (+25، فرع البناء). التوفيق مؤجَّل للخيار-3 (المالك) | git branches | decisions/ledger.md#BRANCH-RECONCILE 2026-07-20 | **CLOSED 2026-07-20** — التوفيق تمّ: `b01c75b` (merge `--no-ff`) وحّد الاتحاد في main + CI أخضر مؤكَّد (والفروع اللاحقة #585→#591 بُنِيت من main النظيف). المتبقّي الوحيد = **الحذف الفيزيائيّ** للفرع (شكليّ، محجوب بـ403 لبيئة الوكيل) — يُتابَع تحت BRANCH-GRAVEYARD-POLICY. |
| C1/C2 | التوصية تُولَّد + تُخزَّن وتُدقَّق وتُربَط بالشرح (جدول v77 + `RECOMMENDATION_CREATED` + `GET /{rec_id}`) | platform/التوصيات | `SAHOOL_PRODUCTION_GAP_REPORT_v1.md:19` (#350)؛ أصل: `:116-117` | fixed (يحتاج تأكيداً حيّاً) |
| C5 | NDVI الحقيقيّ معلوماتيّ لا يُغيّر صلاحيّة القرار — **سياسة دليل قرار** صريحة (`informational`/`supporting`/`decision_blocking`، الافتراضيّ `supporting`؛ الحجب فقط بمعايرة محليّة + سياق محصول + جودة مشهد) | platform/الحالة القانونيّة | #567 (`273ee34`)؛ [`api/evidence_policy.py`](../../services/sahool-platform/api/evidence_policy.py)؛ اختبار [`test_ndvi_evidence_policy.py`](../../tests_v9/test_ndvi_evidence_policy.py) | fixed (يحتاج معايرة ميدانيّة لعتبات NDVI) |
| H2 | **٧** اشتراكات NATS بلا ناشر (لا ٨) — تصنيفها «ناشر مفقود متوقَّع» لا «اشتراك ميّت»: تطابق `EVENT_EMOJI` وأنواع الأحداث (`api/main.py:1670`)، فالإصلاح = بناء ناشرين عبر outbox لا تقليم الاشتراكات (قرار معماريّ). الموضوعان `satellite.*.computed`/`sahool.events.>` لهما ناشرون (ليسا يتيمين). `weather.forecast.updated` مُعالَج خلف راية `WEATHER_GRID_PIPELINE_ENABLED` (OFF). | notification/الأحداث | عقد #568 (`008c330`)؛ [`event_publish_contracts.yaml`](../../event_publish_contracts.yaml)؛ حارس عكسيّ [`sahool_inspector.py`](../../tools/sahool_inspector.py) `check_nats_publisher_coverage` + اختبار [`test_nats_publisher_coverage.py`](../../tests_v9/test_nats_publisher_coverage.py) | fixed — كلّ مُستهلَك له منتِج موثَّق أو waiver؛ CI يحرس «مُستهلَك بلا منتِج» (لا تقليم اشتراكات، لا اختلاق ناشر) |
| H4 | ET0 Hargreaves مُكرَّر بقيم Ra متعارضة — وُحِّد في `core/engines/et0.py` | platform/الأغرونوميا الكمّيّة | `SAHOOL_PRODUCTION_GAP_REPORT_v1.md:23` (#351/#356)؛ تأكيد #457 | ✅ fixed + مؤكَّد باختبارات انحدار (#457؛ متبقٍّ موثَّق: إعادتان عبر-خدمات weather_server/wofost) |
| H5-EC-GATE-WIRING | ربط بوّابة EC القائمة fail-closed ببيانات مصدر الماء المقروءة خادميّاً (PR3 #641) — **ليس محرّك ملاءمة مياه ريّ**: النطاق المُعلَن = wiring لبوّابة EC موجودة. Ks + غسل مشروط؛ ٤ سياسات | platform/الريّ | #566 (`e6f98f5`) + #641؛ [`api/irrigation_recommendation_policy.py`](../../services/sahool-platform/api/irrigation_recommendation_policy.py) · [`canonical_well_capability.py`](../../services/sahool-platform/api/canonical_well_capability.py) `evaluate_water_salinity_gate` | **CLOSED_IN_CODE / PG_AND_ENDPOINT_BEHAVIORAL_VERIFICATION_PENDING** — لا تُسجَّل «ملاءمة/إدارة ملوحة مكتملة». يبقى: تحقّق سلوكيّ endpoint+PG (field↔water_source، منع bypass عند غياب المصدر للحقول المرويّة، رفض timestamp/ECw غير الصالح، عيّنة verified فقط، provenance كامل). |
| H5.1-BINDING-INTEGRITY | نزاهة الريّ: ربط الحقل بمصدر الماء **خادميّاً** (منع bypass العميل) + قبول عيّنة **قرار-درجة فقط** في البوّابة الحسّاسة | platform/الريّ | H5.1 (`3033765`)؛ `migrations/v214_field_irrigation_source_assignments.sql` · [`api/irrigation_source_binding.py`](../../services/sahool-platform/api/irrigation_source_binding.py) `resolve_active_bindings` · [`canonical_well_capability.py`](../../services/sahool-platform/api/canonical_well_capability.py) `DECISION_GRADE_SAMPLE_QUALITIES` · `tests_v9/test_h51_field_source_binding_pg.py` | **CLOSED_IN_CODE_AND_PG_PROVEN / LIVE_FIELD_BINDING_DATA_PENDING** — جدول وصل بـRLS صارم؛ المصدر مُشتَقّ من الخادم (mismatch/unresolved fail-closed)؛ estimated/measured مرفوضة (WATER_QUALITY_NOT_DECISION_GRADE)؛ خريطة enum DB↔canonical موثّقة كافتراض صريح. شهادة PG حقيقيّة بدور مقيَّد NOBYPASSRLS تُثبت الحلّ+فلتر الدرجة+النافذة/الحالة+عزل RLS (شُغّلت خضراء PG16 محلّيّ + خطوة CI مخصّصة `H51_CERTIFICATION_REQUIRED`). يبقى: تعبئة روابط حقول حيّة + برهان endpoint HTTP كامل عبر البوّابة. |
| IRRIGATION-WATER-SUITABILITY | محرّك ملاءمة مياه ريّ متعدّد الأخطار (ECw/SAR/Na/Ca/Mg/Cl/B/HCO3 + crop/stage + soil/drainage + طريقة ريّ + ECw→ECe) — **مؤجَّل بصدق** | platform/الريّ | مراجعة زراعيّة 2026-07-25 | **BLOCKED_DESIGN_DATA_AUTHORITY** — تقسيم آمن: H5.1 نزاهة (field↔source، منع bypass) · H5.2 ملفّ جودة ماء موحَّد (قرار informational/insufficient) · H5.3 سياسة متعدّدة الأخطار (تحتاج سلطة منتَج: جداول FAO/USDA، ECw→ECe، freshness) · H5.4 معايرة اليمن. لا محرّك ضخم دفعةً واحدة، لا «حقيقة محلّيّة» من مراجع دوليّة بلا معايرة. |
| H6 | عتبات الملوحة/pH/الحرارة مُكرَّرة — وُحِّدت في `core/thresholds.py` | platform/العتبات | `SAHOOL_PRODUCTION_GAP_REPORT_v1.md:21` (#352)؛ أصل: `:132` | fixed (يحتاج تأكيداً حيّاً) |
| C4/M1 | الموبايل: بنية push (FCM/APNs) + عميل WebSocket في Flutter | mobile | `SAHOOL_PRODUCTION_GAP_REPORT_v1.md:40,119,150` | deferred — يتطلّب بيئة Flutter (push/FCM/WebSocket) |
| SAM2 | خادم استدلال SAM2 يحتاج GPU (opt-in)؛ بدونه 503 صادق | field-segmentation/sam2 | `docker-compose.v9.yml:1351` (profile=gpu)؛ `services/sam2-inference/main.py:74`؛ [`docs/SAM2_DEPLOYMENT.md`](../../docs/SAM2_DEPLOYMENT.md) | by-design — opt-in خلف profile=gpu (503 صادق بدونه؛ ليس عيباً) |
| MAP-QA | بوّابة QA لـMapLibre/WebGL (إنشاء سياق WebGL + أسلاك الطبقات + التفاعل + القياس) | frontend/الخرائط | مهمّة CI **Frontend E2E (Playwright · MapLibre/WebGL QA)** تُشغّل `npx playwright test` على Chromium حقيقيّ (SwiftShader) كلّ دفعة ([`ci.yml:162`](../../.github/workflows/ci.yml)) | **verified** (تعمل حيّاً في CI وخضراء — CI run 28750924733 عند `781f7a4` — 11 مهمّة كلّها success؛ تشغيل محلّيّ 2026-07-05 أكّد 8/9 خطوات gating خضراء، وخطوة رسم Terra Draw حسّاسة لبناء Chromium تحت software-WebGL تمرّ على Chromium المُدار في CI؛ الخطوتان البصريّتان @visual يدويّتان بالتصميم) |
| TERRAIN | تضاريس الحقل: إحصاءات + سجل مصادر متعدّد الدقّة + عرض 3D | frontend/raster/platform | `services/raster-service/terrain_source_registry.py` (resolver+lineage+terrain-rgb) · `config/terrain_sources.yml` · `terrain_analysis.py::compute_field_terrain` · راستر `GET /v1/fields/{id}/terrain` (+`terrain_source` lineage+`resolution_policy`) · `GET /v1/terrain/status` · اختبار [`tests_v9/test_terrain_source_resolver.py`](../../tests_v9/test_terrain_source_resolver.py) 8/8 | **OPERATOR_BLOCKED · code_status=COMPLETE · product_decision=CLOSED** (PR TBD). قرار المالك: أساس عالميّ مجانيّ **Copernicus GLO-30 (30م)** + دعم 10م/5م موثّق عند التزويد؛ الأولويّة `validated_5m→validated_10m→glo30_30m` بحسب تغطية الحقل. سجل مصادر (لا ملفّ DEM واحد) + resolver + lineage صادق (`native`≠`storage`، `effective=max`، `is_upsampled`) يمنع الدقّة الوهميّة + مُرمِّز Terrain-RGB نقيّ (round-trip مُختبَر). **runtime OPERATOR_BLOCKED**: لا بيانات DEM مُزوَّدة ⇒ كلّ المصادر `provisioned=false` ⇒ `computed=false` صادق. **يبقى للمشغّل (بيانات لا كود):** `provision_baseline_dem` (GLO-30) · `deploy_terrain_rgb` بلاطات · `validate_runtime`. توافق للخلف: `FIELD_DEM_PATH` يُزوِّد الأساس. لا ادّعاء عالميّة/مجّانيّة للـ5م. |
| IND-SRC | مصدر مؤشّرات الموبايل الصحيح (`getFieldIndicators`) | mobile | #445 (`a7909e6`)؛ [`mobile/sahool_app/lib/services/api_service.dart`](../../mobile/sahool_app/lib/services/api_service.dart) | fixed |
| MERGE | دمج/انقسام الحقول ذرّيّاً (سدّ خطر البيانات الثلاثيّة) | platform/الحقول | #443 (`2456d2b`)؛ [`api/routers/fields.py`](../../services/sahool-platform/api/routers/fields.py)؛ اختبار [`tests_v9/test_fields_merge_split_atomic.py`](../../tests_v9/test_fields_merge_split_atomic.py) | fixed |
| NDVI-MOB | مسار سلسلة NDVI في الموبايل (404) | mobile | #444 (`9e00d0a`)؛ [`mobile/sahool_app/lib/screens/satellite_screen.dart`](../../mobile/sahool_app/lib/screens/satellite_screen.dart) | fixed |
| RASTER-STRIPE | شرائط داكنة فوق NDVI/NDMI/الملوحة — بكسلات `finite=0.0` خارج dataMask تُلوَّن معتمة | raster-service | إصلاح المصدر #550 (`2359cea`، قناع `cog_writer`)؛ [`cog_writer.py`](../../services/raster-service/cog_writer.py)؛ اختبار [`test_cog_writer_internal_mask.py`](../../services/raster-service/test_cog_writer_internal_mask.py) | fixed + مُختبَر |
| CDSE-SCL | قناع غيوم SCL **بكسليّ** في evalscript CDSE (لا `dataMask` فقط) | raster-service | #550 (`2359cea`)؛ [`cdse_client.py`](../../services/raster-service/cdse_client.py) | fixed (يحتاج تأكيداً حيّاً بتشغيل CDSE) |
| CDSE-CLIP | قصّ بلاطات CDSE على **مضلّع الحقل** لا الـbbox (إزالة الصحراء الحمراء) — تُمرَّر `geom`؛ وإن غابت تُجلَب الهندسة من DB كي يبقى القصّ دائماً | raster-service | #558 (`522a47e`) + احتياط الجلب الدائم #564؛ [`routers/cdse_tiles.py`](../../services/raster-service/routers/cdse_tiles.py) | fixed (يحتاج تأكيداً حيّاً بتشغيل CDSE) |
| CDSE-DATE | تطبيع `date` الفارغ (الواجهة ترسل `""`) ⇒ أحدث مشهد؛ وإسقاط `date` من رابط `cdse-tilejson` حين لا يُطلَب محدَّداً | raster-service | #559 (`1bef0cf`)؛ [`routers/cdse_tiles.py`](../../services/raster-service/routers/cdse_tiles.py)؛ اختبار [`test_cdse_date_normalization.py`](../../services/raster-service/test_cdse_date_normalization.py) | fixed + مُختبَر |
| CI-MIRROR | `ci.yml` فقد خطوة مرآة السجلّ `mirror.gcr.io` (ضاعت في إعادة كتابة `main` بدفع مباشر) ⇒ رفرفة Docker Hub تُعطّل *Integration Tests* | ci | إعادة #556 (`852fb5b`)؛ [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) | fixed (أُعيدت المرآة) |
| LOOP-LINEAGE | تحديثات التعلّم بلا رابط مصدر (learning update بلا evidence) — لا يُستعلَم «أيّ نتيجة أنتجت هذا التحديث» | platform/التعلّم | جسر #2 (`09fcc71`, v151)؛ [`core/learning_source_lineage.py`](../../services/sahool-platform/core/learning_source_lineage.py) + [`api/phase_runtime_store.py`](../../services/sahool-platform/api/phase_runtime_store.py)؛ التدقيق [`docs/audits/recommendation_loop_closure_20260708.md`](../../docs/audits/recommendation_loop_closure_20260708.md) | fixed — تحديث بلا مصدر ⇒ `rejected_untraceable` فلا يُطبَّق (يحتاج تأكيداً حيّاً على DB) |
| LOOP-OUTCOMES | نموذجا نتائج متوازيان (`outcome_record` بـdecision_id مقابل `recommendation_outcomes` بـrecommendation_id+season_id) يجب توفيقهما | platform/النتائج | جسر #3 (`3651764`)؛ [`core/outcome_reconciler.py`](../../services/sahool-platform/core/outcome_reconciler.py) | fixed — موحِّد قراءة واحد بوسم source_model/kind يربطهما عبر dispatch_decisions (متكاملان لا مكرّران) |
| LOOP-DEADFB | `recommendation_feedback` جدول مكرّر ميّت (بلا كاتب) | platform/التغذية الراجعة | جسر #4 (`16d8d8a`, v152)؛ حارس [`test_v152_recommendation_feedback_deprecation_static.py`](../../tests_v9/test_v152_recommendation_feedback_deprecation_static.py) | fixed — إيقاف موثَّق بتعليق + حارس ساكن يمنع إحياءه؛ الموطن الحيّ recommendation_outcomes/farm_operations_ledger/water_ledger (لا DROP) |
| LOOP-FK | لا مفاتيح أجنبيّة على جداول الحلقة ⇒ الأيتام ممكنة بنيويّاً | platform/سلامة مرجعيّة | جسر #5 (`69596a1`)؛ [`core/loop_referential_integrity.py`](../../services/sahool-platform/core/loop_referential_integrity.py) | by-design + fixed — غياب FK مقصود (نصّيّ vs UUID · ربط ليّن يحفظ RLS · كُتّاب متعدّدون)؛ الحماية = **كشف أيتام** دوريّ للمراجعة لا فرض FK (يكسر الإدراج) |
| RASTER-DECOMP | تفكيك `raster-service/main.py` (٤٥ مساراً → ١٠ `routers/`، محفوظ السلوك، CDSE محفوظة) | raster-service | #551 (`51d650c`)؛ [`router_registry.py`](../../services/raster-service/router_registry.py)؛ حارس [`test_raster_router_decomposition_guard.py`](../../services/raster-service/test_raster_router_decomposition_guard.py) | fixed (٤٩ مساراً ثابتة) |
| AUTH-DECOMP | تفكيك `auth/main.py` (٢٧ `@app` → ٩ `routers/`، محفوظ السلوك، حسّاس أمنيّاً) | auth | #557 (`f92c994`)؛ [`services/auth/router_registry.py`](../../services/auth/router_registry.py)؛ حارس [`test_router_decomposition_guard.py`](../../services/auth/tests/test_router_decomposition_guard.py) | fixed (العدد ثابت N=31) |
| SVC-DECOMP | تفكيك ٤ خدمات متجانسة: odoo-bridge (14) · video-processor (12) · vegetation-analysis (12) · supervisor-agent (14) — نفس نمط raster/auth، محفوظ السلوك، عدد المسارات ثابت | odoo/video/vegetation/supervisor | #560 (`77123b3`) · #561 (`d40f1a9`) · #562 (`0abe6de`) · #563 (`7a36511`)؛ حُرّاس تفكيك لكلٍّ + مساعِد [`tests_v9/supervisor_route_source.py`](../../tests_v9/supervisor_route_source.py) | fixed |
| SVC-DECOMP-2 | تفكيك ٤ خدمات أصغر (٦–٧ مسارات): soil-service (10) · tts-service (11) · actuator-service (10، حسّاس أمنيّاً) · guardrails-engine (11، حوكمة `/validate` حسّاسة) — نفس النمط، محفوظ السلوك، عدد المسارات ثابت. **soil احتاج إصلاح حُرّاس عزل المستأجرين** التي كسرها النقل: إعادة تصدير المعالجات من `main` + مساعِد مصدر مُجمِّع [`soil_route_source.py`](../../tests_v9/soil_route_source.py) + تحديث مفتاح allowlist في [`tenant_query_audit.py`](../../scripts/tenant_query_audit.py) + إصلاح تعفّن وحدة `main` عبر الاختبارات — **بلا إضعاف أيّ تأكيد** (IDOR/عبر-المستأجرين تمرّ) | soil/tts/actuator/guardrails | #570 (`d340e60`) · #571 (`7f642a2`) · #572 (`bcb6c15`) · #573 (`b4c0be6`) | fixed |
| SAT-DEFERRED | بنود «المؤجَّل» من تدقيقات سجلّ الأقمار v2/v3/v4 (كانت تحتاج عاملاً/معماريّة): F1 تواريخ متاحة مبتورة · F3 fetch غير واعٍ بالجودة · F4 خلط بيانات وصفيّة · v4 أعمدة v105 لا تُكتب · 007 auto-refresh · F6/7/8/9 CDSE cache/bbox/tid/S3 · 011 asset_status · 004 geometry_revision · 005 عامل الإبطال · 010 احتفاظ الكاش · 008/009 جسر registry+STAC | raster-service/platform/frontend/migrations | م1 `fe4426b` · م2 `8ed6272` · م3 `f440b3f`(v143) · م4 `bdf703a` · م5 `5f52b63`؛ ٥ حُرّاس unit جديدة | **fixed** (unit + **Integration Tests على Postgres+PostGIS حيّ في CI خضراء** — CI run 28750924733 عند `781f7a4` — 11 مهمّة كلّها success؛ يبقى تفعيل عامل الإبطال كخدمة compose في الإنتاج تحقّقاً تشغيليّاً/نشريّاً لا اختباريّاً) |
| MAPHUB-CDSE | MapHub `cdse-tiles` + bbox/geom/tenant + nginx `^~ /api/raster/` + `X-Tenant-Id` من `$arg_tenant_id` | frontend/nginx | **PR #564 مدموج** 2026-06-28 (`30102fe`→main) | **fixed** (مدموج؛ القيد «قيد المراجعة» كان بائتاً — التحقّق الميدانيّ لقصّ CDSE الحيّ يبقى نشريّاً) |
| NOTIF-WS | WebSocket الإشعارات: `websocket: WebSocket` + `python-jose` + `websockets<14` | notification | **PR #564 مدموج** 2026-06-28 | **fixed** (مدموج؛ القيد «قيد المراجعة» كان بائتاً) |
| AGENT-GOV | حوكمة أدوات الوكيل: مخازن موافقة/تدقيق قابلة للاستبدال (memory→redis) + `/approvals/resume` · تحقّق وسائط صارم + تعقيم نتائج (ضد tool-result injection) · «كلّ mutating ⇒ requires_approval» (ثابت وقت-البناء) · ميزانية run + dedupe + إيقاف عند بوّابة الموافقة | ai_agronomist/shared.ai | v58.2a `eb3cf89` · v58.2b `151851a` · v58.2c `0b5a13b`؛ [`agent_stores.py`](../../services/ai_agronomist/agent_stores.py) · [`tool_governance.py`](../../services/ai_agronomist/tool_governance.py) · [`tool_loop.py`](../../services/ai_agronomist/tool_loop.py) | fixed (unit + CI أخضر) |
| AIMEM-TENANT | ذاكرة AI للحقل: `_optional_events` صار tenant-scoped صريحاً (دفاع مضاعف مع RLS) + redaction قبل السياق + ميزانية حجم/عناصر + freshness/provenance؛ + ترحيل v127 (recommendation_outcomes RLS WITH CHECK) | platform/ai_agronomist | v49.5 `abe0c51`؛ [`field_ai_context.py`](../../services/sahool-platform/api/routers/field_ai_context.py) · [`migrations/v127_evidence_context_hardening.sql`](../../migrations/v127_evidence_context_hardening.sql) | fixed (Integration على Postgres) |
| MFA-HARDEN | تصلّب MFA الإنتاجيّ: تشفير السرّ عند الراحة (Fernet، لا default key) + recovery codes (hash-only، one-time) + قفل DB دائم + تدقيق append-only + RLS مُضيَّق (role='admin' لا tenant-null) + step-up محكوم + عدّاد فشل ذرّيّ + HMAC للـIP. مسار توافق لا يكسر مستخدماً قائماً (نصّ→مشفّر عند نجاح الدخول) | auth | v29.5 `8810321` (v128) · v29.6 `4a3f1a4` (v129)؛ [`mfa_crypto.py`](../../services/auth/mfa_crypto.py) · [`migrations/v128_mfa_hardening.sql`](../../migrations/v128_mfa_hardening.sql) · [`migrations/v129_mfa_hardening_followup.sql`](../../migrations/v129_mfa_hardening_followup.sql) | fixed (Integration يطبّق v128/v129 على Postgres حقيقيّ + يؤكّد سياق role=admin) |
| VEG-JWT | خدمة `sahool-vegetation-analysis` وحدها بلا `JWT_SECRET` في compose ⇒ 503 «JWT_SECRET غير مضبوط» على «تحليل الآن» | compose/vegetation | `62989c6`؛ [`services/vegetation-analysis-service/main.py:161`](../../services/vegetation-analysis-service/main.py) · docker-compose.v9.yml/fixed.yml | fixed (يلزم `--build`/إعادة تشغيل عند المشغّل) |
| DECISION-DEPLOY | 🔴 decision-service بلا Dockerfile/خدمة compose/env ⇒ مضيف المِرْآة `sahool-decision-service:8160` غير موجود ⇒ المِرْآة best-effort ميتة (P4.5–P4.7 غير صالحة إنتاجاً حتى تُنشَر) | decision-service/deploy | `services/decision-service/Dockerfile` (جديد، non-root 8160) · خدمة في `docker-compose.v9.yml`+`docker-compose.fixed.yml` · `DECISION_SERVICE_URL` على المنصّة + `.env.example` · حارس [`test_decision_service_deployment_contract.py`](../../tests_v9/test_decision_service_deployment_contract.py) | **fixed** (كود: Dockerfile+compose+env+حارس ٧ تأكيدات؛ لا فقدان بيانات أصلاً — المنصّة SoR بالجسر الانتقاليّ. **صدق:** لا DB env على الجذع كي لا يُوهِم استمراراً؛ يبقى **تحقّق نشريّ حيّ** (`docker compose up`/`-m integration`) وترقية SoR الحقيقيّ) |
| BACKFILL-422 | «تجهيز سنتين» يرسل `'truecolor'` ضمن `indices`، لكنّ `HistoricalBackfillRequest.indices: list[IndicatorKind]` لا يحوي truecolor ⇒ pydantic 422 | frontend/raster | `2e353af`؛ [`MapHub.tsx`](../../frontend/src/sections/MapHub.tsx) + حارس [`MapHubTwoYearBackfill.static.test.ts`](../../frontend/src/sections/MapHubTwoYearBackfill.static.test.ts) | fixed |
| SPATIAL-401 | «المؤشرات المكانية» كانت تُخرج المستخدم إلى الدخول (401 على `/v1/fields/{id}/indicator-grid` يُشغّل interceptor الخروج) | frontend/raster | [`SpatialIndicatorsPage.tsx`](../../frontend/src/sections/SpatialIndicatorsPage.tsx) · [`api.ts`](../../frontend/src/services/api.ts) | **fixed** (أفاد المستخدم 2026-07-05 بإصلاحه في بيئة التطوير؛ بانتظار تأكيد الـSHA/الدمج في هذا الفرع لتثبيت الحالة) |
| AUTO-SEG | «تحديد الحدود تلقائي» يُظهر «الخدمة غير متاحة» — `field-segmentation` يردّ 503/404 حتى تُنشَر خلفيّة SAM2 (الواجهة تسقط بصدق للرسم اليدويّ بلا تلفيق مضلّع) | field-segmentation | [`AddFieldWithMap.tsx:692`](../../frontend/src/components/AddFieldWithMap.tsx) · `docker-compose.fixed.yml:1076-1084` | by-design (تشغيليّ: `SEGMENTATION_BACKEND=sam2` + `SEGMENTATION_INFERENCE_URL` + حاوية استدلال) |
| v57.5-DB | تصلّب أساس القاعدة: v50 soil_lab analyte + chain-of-custody · v54 imagery quality metadata · v53 field_state recompute · v52 tenant AI policy DB-backed | platform/migrations | **مُغلَق downstream عبر ترقيات productionization:** `v130_soil_lab_evidence_hardening.sql` · `v131_imagery_quality_metadata.sql` · `v132_field_state_recompute_provenance.sql` · `v124_tenant_ai_policies.sql` — الأربعة موصولة في `migrations/MANIFEST.txt` **و** `scripts_v9/run_migrations.sql`؛ القرّاء/الكتّاب موجودون (`services/raster-service/db_persist.py` جودة الرستر · `services/ai_agronomist/` سياسة/عهدة) | **fixed** (أُعيد التحقّق 2026-07-05 عند رأس `781f7a4`؛ القيد `open` كان بائتاً) |
| THERMAL-COMPOUND | الإجهاد الحراريّ المركّب (حرّ نهار × برد ليل، DTR، ليالٍ باردة متتالية) مشروطاً بمحصول×مرحلة | weather-service/platform | `services/weather-service/thermal_stress.py` + `GET /v1/weather/thermal-stress` + façade `/api/v1/fields/{id}/weather/thermal-stress` + `test_thermal_stress.py` | **fixed** (منتِج حتميّ + مستهلك façade؛ دور supporting يحتاج معايرة عتبات ميدانيّة) |
| LODGING | ✅ خطر الرقود (رياح×طول×مرحلة×رطوبة تربة) | weather-service | لا مُنتِج بعد (0 ملفّات في المسح) | **fixed** (`lodging_risk.py` منتِج حتميّ + façade مُجمَّع crop-stress؛ supporting يحتاج معايرة) |
| POLLINATION-WX | خطر التلقيح الجوّيّ (حرّ/برد/رياح/مطر أثناء الإزهار) | weather-service | لا مُنتِج بعد (0 ملفّات) | **fixed** (`pollination_risk.py`؛ not_applicable خارج الإزهار — صدق) |
| CHILL-MODELS | نماذج ساعات البرودة المتقدّمة (Utah/Dynamic/Chill Portions) للأشجار المعمرة | weather-service | تغطية بسيطة فقط (5 ملفّات) | **fixed** (`chill_accumulation.py`: Chilling Hours + Utah؛ Dynamic معلَن not_implemented) |
| WAIVER-WX10.6-001 | إعفاء تغطية-واجهة لنقطة مرشّح القرار (machine-consumed) حتّى وصول شاشة المراجعة | platform/crop→decision | endpoint `POST /api/v1/crop-twin/decision-candidate` | **fixed (WX-10.6 PR4، #642 `012605a`)** — أُزيل الإعفاء (49 إعفاء) وصار المسار مُغطّى بتغطية-مصبّ في [`endpoint_ui_coverage.json`](../../config/endpoint_ui_coverage.json) (`downstream_surface`=`/api/v1/decisions/review-queue`، سطح ApprovalsConsole). أُصلح عمى البوّابة العكسيّة لتعرف تغطية-المصبّ. E2E مصبّ حقيقيّ [`test_wx10_6_crop_candidate_downstream_e2e.py`](../../services/decision-service/tests/test_wx10_6_crop_candidate_downstream_e2e.py) يُثبت أنّ المرشّح يُستهلَك في طابور المراجعة (Postgres حقيقيّ، خطوة CI). submit المنتِج يبقى خلف `CROP_TWIN_DIRECT_DECISION_ENABLED`. |
| WAIVER-EXPIRY-GUARD | حارس CI يرفض أيّ waiver منتهٍ (expiry < today) — وجود expiry في JSON لا يكفي دون إنفاذ | ci/governance | [`scripts/ci/waiver_expiry_guard.py`](../../scripts/ci/waiver_expiry_guard.py) (خطوة Structural Lint في [`ci.yml`](../../.github/workflows/ci.yml))؛ اختبار [`tests_v9/test_waiver_expiry_guard.py`](../../tests_v9/test_waiver_expiry_guard.py) | **fixed** — الحارس يفشل عند `expiry < today` أو waiver مؤقّت بلا expiry؛ يستخدم تاريخ CI الفعليّ ⇒ WAIVER-WX10.6-001 (2026-10-11) ذاتيّ-الانتهاء. اختبار حتميّ بتواريخ محقونة (لا يتعفّن). |
| DEPLOYED-DECISION-SOR-PROMOTION | تفعيل Decision-Service كـSoR للحلقة (قلب ملكيّة loop tables + `DATABASE_URL` في compose) — شرط تفعيل WX-10.7 authoritative | decision-service/deploy | [`db_ownership.yml`](../../docs/architecture/db_ownership.yml) (decision_record status=interim-bridge) · compose يمرّر `DATABASE_URL` opt-in (افتراض فارغ) لـdecision-service · كود SoR جاهز خلف `DECISION_SERVICE_SOR_ENABLED` | **open (cutover-prep مُنجَز @ `4a7488c`)** — أدوات الـcutover صارت WX-10.7-aware: `backfill.py --verify-review` (quarantine/parity لا يُخمّن)، `/readyz` يثبت db_reachable+migrations_current، rollback يصون `decision_reviews`، compose passthrough opt-in افتراض فارغ (mirror يبقى آمناً)، `scripts/deploy/decision_service_migrate.sh` خطوة قبل-نشر مرصودة، حارس `decision_sor_review_cutover_gate`. **المتبقّي (تشغيليّ للمشغّل، ليس كوداً):** apply على Postgres إنتاجيّ + backfill + حلّ أيّ quarantine + قلب الملكيّة + ضبط `DECISION_SERVICE_DATABASE_URL`/الراية. حتّى ذلك، endpoint المراجعة يفشل مغلقاً 503 بالتصميم. |
| WAIVER-WX10.7-001 | إعفاء تغطية-واجهة لنقطة مراجعة القرار (machine/BFF) حتّى reviewer/approvals UI | platform/decision-review | endpoint `POST /api/v1/decisions/{decision_id}/review` | **fixed (WX-10.8)** — أُزيل الإعفاء من [`endpoint_ui_coverage_waivers.json`](../../config/endpoint_ui_coverage_waivers.json) (30→29) وصار المسار مُغطّى واجهةً في [`endpoint_ui_coverage.json`](../../config/endpoint_ui_coverage.json) بوصول ApprovalsConsole (طابور المراجعة + approve/reject). reverse-gate أخضر (415 core + 29 إعفاء). |
| ACTIVATION-GATE-PROD-01 | آلة حالات التفعيل: ٥ حالات (disabled/evaluating/enabled/degraded/revoked)، الانتقالات القانونيّة مفروضة في خدمة التطبيق | decision-service/activation | [`activation_gate.py`](../../services/decision-service/activation_gate.py) · [`migrations/028_irr_f01_reservation_activation_gate.sql`](../../services/decision-service/migrations/028_irr_f01_reservation_activation_gate.sql)؛ حارس [`test_irr_f01_activation_gate_prod_guard.py`](../../tests/irrigation/test_irr_f01_activation_gate_prod_guard.py) | **locked (architectural)** — لا حذف/اختصار دون قرار معماريّ صريح |
| ACTIVATION-GATE-PROD-02 | CAS على `activation_generation` (رتيب +1، trigger حارس في DB يمنع القفز/إعادة ربط environment) | decision-service/activation | `activation_gate.py` · `028_*.sql` (`irr_f01_reservation_activation_guard`) | **locked** |
| ACTIVATION-GATE-PROD-03 | سجلّ أحداث/أدلّة append-only (immutable trigger) | decision-service/activation | `028_*.sql` (`irr_f01_reservation_activation_events_immutable`) | **locked** |
| ACTIVATION-GATE-PROD-04 | TTL للحالة (enabled/degraded تحملان أفقاً؛ الإنفاذ يقرأ طازجاً لا من الكاش) | decision-service/activation | `activation_gate.py` (`enforce_enabled`, `state_expires_at`) | **locked** |
| ACTIVATION-GATE-PROD-05 | `build_sha` غير قابل للانتحال من metadata النشر (`DEPLOY_BUILD_SHA`) + الأدلّة المقبولة، مُشتقّ خادميّاً | decision-service/activation | `activation_gate.py` (`build_sha`, `deploy_build_sha`) | **locked** |
| ACTIVATION-GATE-PROD-06 | لا جاهزيّة موازية: البوّابة تستهلك دليلاً يحمل producer/check_name/observed_at/valid_until/result/provenance/environment_id — لا تعيد تنفيذ فحوص مكوّن آخر | decision-service/activation | `activation_gate.py` (`_evidence_admissible`, `REQUIRED_CHECKS`)؛ خريطة [`docs/architecture/LIVE_ACTIVATION_ENVIRONMENTS.md`](../../docs/architecture/LIVE_ACTIVATION_ENVIRONMENTS.md) | **locked** |
| ACTIVATION-GATE-PROD-07 | Anti-premature abstraction: لا استخراج framework تفعيل عامّ قبل وجود بوّابتَي فئة-A مستقلّتَين **مُستخدَمتَين فعلاً**. تحقّق الشرط: بوّابتان (`irr_f01_reservation` + `satellite_cdse`) + مستهلك حيّ (raster-service). Phase 3 استخرج المُثبَّت-المشترك إلى `activation_gate_core.ActivationGateCore` (آلة الحالات/CAS/TTL/append-only/build_sha/probe/cache)؛ بقي خاصّاً بكلّ بوّابة: الهويّة/REQUIRED_CHECKS/المنتِجون + **معنى الإنفاذ** (رفض irr_f01 مقابل اختيار مصدر satellite) + أسماء الجداول | decision-service/activation | `activation_gate_core.py` · `activation_gate.py`/`satellite_cdse_activation_gate.py` (wrappers) · حارس PROD (`test_prod_07_shared_core_extracted_after_two_gates`) · القرار المعتمد (المستخدم 2026-07-18) | **locked (executed)** — الاستخراج تمّ بعد تحقّق الشرطَين (بوّابتان مستقلّتان + استهلاك حيّ)، لا قبله |
| ERR-BRIDGE-001 | `sahool-erp-bridge` كانت دائماً unhealthy (log فارغ) فتنهار 33+ خدمة تابعة. السبب: `_run_migrations()` تُصدر `CREATE TABLE odoo_sync_state` بدور `sahool_app` (بلا `CREATE` على `public` بعد REVOKE) ⇒ `InsufficientPrivilegeError` ⇒ lifespan ينهار قبل بدء uvicorn | services/odoo-bridge + migrations/ | `erp_runtime.py:_run_migrations()` (الأصل) · `migrations/v9_odoo_bridge.sql` (الإصلاح) · التزامات: `f1109df3` (DDL→migration) · `dd8e4653` (health 3-level) · `651b995c` (fail-closed sync) · `361c530d` (guards+checksums) | **CLOSED 2026-07-20** — (أ) DDL نُقل إلى `migrations/v9_odoo_bridge.sql` (sahool_user يُنشئ الجداول، sahool_app يملك أدنى الصلاحيات). (ب) ثلاثة مستويات صحّة مستقلّة: `/healthz` (حياة خالصة، لا I/O) · `/readyz` (DB فقط) · `/readyz/capabilities` (ERP كبيانات، HTTP 200 دائماً). (ج) fail-closed في POST /sync: 424 لمزوّد غير مُهيّأ · 503 (probe 5s) لمزوّد غير مستجيب — كلاهما قبل `add_task()`. حُرّاس: 4 + 6 = 10 اختبارات وحدة (مُعلَّمة unit). erp-bridge صار **healthy** على staging منذ 2026-07-20. |
| CONFLICTED-MANIFEST-DISABLES-THE-LAYER-IT-FEEDS-01 | بيانُ أهداف الكتابة الذي يقرؤه مُصنِّفُ التعارضات قد يكون **هو نفسُه متعارضاً**، فلا يُحلَّل، فتسقط طبقةُ البيان بأكملها ويتدهور المُصنِّف إلى «مصدر» للجميع — أي يقف حيث كان يحلّ آليّاً. | ci · governance | [`resolve_merge_conflicts.py`](../../scripts/ci/resolve_merge_conflicts.py) (`_measured_write_targets` · `WRITE_TARGETS`) · [`generated_write_targets.json`](../../docs/architecture/generated_write_targets.json) · #889 (دمجُ main في `sahool/crop-card-stage-nutrient-demand`) | **fixed** — **مقيسٌ على تعارضٍ حقيقيّ لا مِسبار:** دمجُ main في فرع #889 أنتج **١٣** تعارضاً، منها `generated_write_targets.json` نفسُه. فحمل الملفُّ مراسمَ تعارضٍ ⇒ فشل تحليلُ JSON ⇒ أرجعت `_measured_write_targets()` مجموعةً فارغة ⇒ صنّف المُصنِّفُ **ثلاثةَ** ملفّاتٍ «مصدراً» ووقف: البيانَ نفسَه، ووثيقةَ السياسة `guard_mutation_registry.json`، و`docs/runbooks/GUARD_CATALOGUE.md`. **والتكذيبُ بالتفريق:** حُلَّ البيانُ وحدَه (٣١ مدخلاً، يُحلَّل)، ثمّ أُعيد التصنيف بلا أيّ تغييرٍ آخر — فعاد `GUARD_CATALOGUE.md` **مصنوعةً** وانحصر الوقوفُ في وثيقة السياسة وحدها، وهو الوقوفُ الصحيح المقصود بـ`HAND_WRITTEN_POLICY`. فالفارقُ من البيان لا من المحتوى. **وحدُّ صدقٍ يُصغِّر العطل:** التدهورُ **آمنٌ بالتصميم** — `مصدر` تعني «قف واطلب إنساناً» لا «اكتب فوق عمل»، والفشلُ في الجهة الآمنة مقصودٌ ومُكذَّبٌ بـ`test_a_missing_manifest_degrades_to_source_not_to_chaos`. فهذا عطلُ **إبانةٍ لا صحّة**: الأداةُ تفقد قدرتَها صامتةً بلا أن تقول لماذا، فيظنّ القارئُ أنّ الملفّات مصادرُ حقّاً. **والعلاجُ المُقترَح رخيص:** أن يفحص المُصنِّفُ ما إذا كان **بيانُه** ضمن الملفّات المتعارضة فيقول ذلك صراحةً («حُلَّ بياني أوّلاً») بدل التدهور المجهول — تسميةُ السبب لا إصلاحُ السلوك. **ولا حارسَ له ولا طفرة:** حادثةٌ موثَّقةٌ بتفريقٍ مقيس، لا تغطيةٌ مفروضة. **العلاج كُتِب (2026-08-24):** لم يُغيَّر السلوك — القرارُ يبقى «قف» — بل أُضيفت **الإبانة**: `_manifest_is_conflicted()` يفحص ما إذا كان البيانُ نفسُه بين المتعارضات، فيطبع «حُلَّ هذا البيانَ أوّلاً ثمّ أعِد تشغيلي» بدل التدهور المجهول. **والمرساةُ مسارٌ مُطبَّع لا `substring`**: مطابقةٌ نصّيّة تُطابِق `vendor/docs/architecture/...` فتُنتِج رسالةً تكذب على قارئها — وذلك أسوأ من الصمت الذي جاءت تُصلحه. **وسقط «لا حارسَ له ولا طفرة»:** مُثبَّتٌ بـ`tests_v9/test_resolve_merge_conflicts.py` (`test_a_conflicted_manifest_is_named_not_left_to_guesswork`) وطفرتين مُكذَّبتين بالزرع — إسقاطُ الاكتشاف، وإرجاعُ المرساة نصّيّةً. **والشاهدُ الحيُّ وقع (2026-08-24):** دمجُ `main` (`46e1dbc`) في فرع الشريحة أنتج **٦** تعارضاتٍ منها البيانُ نفسُه، فطبعت الأداةُ الرسالةَ على تعارضٍ **حقيقيّ لا مزروع**؛ واتُّبِعت حرفيّاً — حُلَّ البيانُ أوّلاً (٣١ هدفاً) ثمّ أُعيد التشغيل — فحُلَّت **٦/٦ آليّاً بلا وقوفٍ واحد**، بعد أن كان الوقوفُ عند البيان وحدَه قبلها. فالرسالةُ قِيست تعمل، لا تُوصَف. |
| GATE-READS-A-FROZEN-EVENT-PAYLOAD-NOT-THE-LIVE-BODY-01 | بوّابةُ أثر القدرات تقرأ متنَ الطلب من **حمولة الحدث المُجمَّدة** لا من المتن الحيّ — فتصحيحُ المتن لا يُصلِح البوّابة، و«أعِد التشغيل» علاجٌ كاذبٌ لأنّه يُعيد الحمولةَ القديمة نفسها. | ci · governance | [`capability-governance.yml`](../../.github/workflows/capability-governance.yml) (السطر ١٢٤ `Enforce declared PR capability impact` · `PR_BODY: ${{ github.event.pull_request.body }}`) · [`pr_capability_impact_gate.py`](../../scripts/ci/pr_capability_impact_gate.py) (`--pr-body-file`) · #887 (المهمّة الفاشلة `97040471171` · الناجحة `97043697680`) | **closed (2026-08-23)** — **الحادثةُ مقيسةٌ بالتوقيت لا مستنتَجة:** انطلق التشغيل `13:50:12` وصُحِّح `Capability-Impact` في المتن `13:51:13`، فحجبت البوّابةُ بـ`missing_direct=[IRR-004]` و`unaffected_declared=[GIS-003, SEC-003]` **على متنٍ لم يعد قائماً**. والمُشتقُّ الصحيح على `7ba54bf1 → 46445690` بمحرّك البوّابة نفسه، بشجرةٍ نظيفةٍ وشرطِ `HEAD` متحقَّقٍ منه، كان **مطابقاً حرفيّاً** لِما في المتن وقتَ الفحص — فالعطلُ في **زمن القراءة** لا في الاشتقاق. **ولمَ «أعِد التشغيل» لا يُصلِحه:** إعادةُ التشغيل تُعيد تشغيلَ حمولة الحدث الأصليّة، و`on: pull_request` بلا `types` يعني الأنواعَ الافتراضيّة `opened · synchronize · reopened` — و`edited` **ليست منها**، فتحريرُ المتن لا يُطلِق حدثاً أصلاً. **والعلاجُ المُطبَّق التفافٌ لا إصلاح:** أُغلِق الطلبُ وأُعيد فتحه ليحمل `reopened` المتنَ الحاليّ، فمرّت البوّابة. **والإصلاحُ البنيويّ غيرُ مُنفَّذٍ بسببٍ مُعلَن:** إضافةُ `edited` إلى `types` تُعيد تشغيل **٥٨ فحصاً** عند كلّ تحرير متنٍ ولو كان مطبعيّاً — كلفةٌ لم تُقَس ولم تُوازَن؛ والبديلُ الأضيق أن تقرأ الخطوةُ المتنَ **حيّاً عبر الـAPI** بدل `github.event...body`، وهو ما يجعل القراءةَ في زمن التنفيذ لا في زمن الحدث. **وحدُّ صدق:** لم يُزرَع لهذا الصنف عطلٌ ولم يُكذَّب — لا حارسَ له بعد، فالمعرفةُ هنا حادثةٌ موثَّقةٌ لا تغطيةٌ مفروضة. **الإغلاق (2026-08-23):** نُفِّذ «البديلُ الأضيق» المذكورُ أعلاه بعينه — خطوةُ الإنفاذ تجلب المتنَ حيّاً من الـAPI وقتَ التنفيذ (بنمط قارئ قواعد الحماية المقيس في الملفّ نفسه) وتفشل مغلقةً عند تعذّر الجلب، وSHAs تبقى من الحدث بحقّ. وسقط «لا حارسَ له بعد»: مثبَّتٌ بـ`tests_v9/test_capability_gate_reads_live_body.py` وطفرتين مُكذَّبتين بالزرع (عودةُ الحمولة المجمَّدة، والسقوطُ الصامت عند فشل الجلب). **سِجِلُّ الدمج (2026-08-23):** ظهر هذا المدخلُ **مرّتين متلاصقتين** على فرع `sahool/crop-card-stage-nutrient-demand` بعد دمج `main` فيه — صفٌّ `open` من الفرع وصفٌّ `closed` من `main` (#907). ولم يُعلِن الدمجُ ذلك: `gaps/registry.md` **إلحاقيّ**، فضمّ git الجانبَين **بلا أيّ مِرقاب تعارض**، فلم يظهر في الثلاثةَ عشرَ تعارضاً التي حُلَّت يدويّاً. أمسكه `brain_duplicate_gap_identity_guard` وحدَه — وهو الصنفُ الذي وُضِع له: «بصمة دمج union على سطر واحد». **والمدخلان دُمِجا لا حُذِف أحدهما:** قِيس أنّ نصّ `closed` يحوي نصَّ `open` **حرفيّاً بكامله** — الافتراقُ عند المحرف ١٢٢٠ من ١٢٢١، أي الشرطة الفاصلة وحدها — فهذا السطرُ هو المدخلُ المدموج الذي يحفظ النصّين، لا انتقاءُ أحدهما. **ودرسٌ ثانٍ من العلاج نفسه:** أوّلُ محاولةٍ أسقطت الصفَّ المُضمَّن فحجبها `brain_append_only_guard` بـ`JOURNAL_SHRANK` (فُقِد ٢٬٧٩٤ بايتاً) — فالحارسان يشدّان في اتّجاهين: أحدهما يمنع التكرار والآخر يمنع التقلّص، والمخرجُ الوحيد الذي يُرضيهما هو ما يقوله نصُّ الأوّل حرفيّاً: **مدخلٌ واحد يحفظ النصّين** ويحمل سِجِلَّ ما جرى — لا حذفٌ ولا إبقاءُ تكرار. **وسِجِلُّ عودةٍ ثانية (2026-08-25):** الصفُّ الأصليّ عاد للظهور صفّاً مستقلّاً غيرَ متلاصقٍ (بينهما صفُّ #914) عبر دمج union لاحقٍ — وشبكةُ التلاصق لا تراه بالتصميم. قِيس أنّ نصَّه محتوًى **بكامله حرفيّاً** في هذا المدخل المدموج (2262 من 3300 بايتاً)، فأُزيلت البقايا بلا فقد نصٍّ واحد، ووُسِّع الحارسُ إلى تفرُّدٍ عالميٍّ لصفوف الجدول — `BRAIN-DUP-ROW-ESCAPES-THE-ADJACENCY-NET-01`. |
| GUARD-RUN-WITHOUT-THE-ARGUMENTS-CI-PASSES-01 | حارسٌ يُشغَّل محلّيّاً بلا الرايات التي تُمرِّرها CI يطبع `_ok` وهو **لم يقِس شيئاً** — خضرةٌ صادقةٌ حرفيّاً عن سؤالٍ لم يُطرَح. | ci · governance | [`brain_append_only_guard.py`](../../scripts/ci/brain_append_only_guard.py) (`--base` · `--head` · `commits_in_range`) · [`brain_state_transition_guard.py`](../../scripts/ci/brain_state_transition_guard.py) · [`brain-guards.yml`](../../.github/workflows/) | **open** — **مقيسٌ على حادثتين في جلسةٍ واحدة، لا على مِسبار.** `brain_append_only_guard` بلا رايات يفحص الشجرةَ الحاضرة فيطبع `brain_append_only_guard_ok`؛ وبـ`--base origin/main --head HEAD` يمشي على **كلّ زوج (التزام، والد)** — ٨٠ زوجاً في القياس الفعليّ — فيمسك تقلّصاً لا تراه الشجرةُ الحاضرة إطلاقاً. فمرّ عندي أخضرَ ثمّ حجب في CI بـ`JOURNAL_SHRANK` على الالتزام نفسِه. و`brain_state_transition_guard` من الصنف عينه: بلا `--base` يموت بـ`CalledProcessError` على `None...HEAD` — وهذا أصدقُ، لأنّه **يفشل بدل أن يخضرّ كاذباً**. **والفارقُ بين الحالتين هو العطل:** حارسٌ يقبل الغيابَ ويُكمِل يُنتِج خضرةً بلا معنى، وحارسٌ يرفضه يُنتِج رسالةَ خطأ — والثاني هو السلوكُ الصحيح. **وحدُّ صدقٍ يُصغِّره:** هذا عطلُ **إجراءٍ لا شيفرة** — الحارسُ في CI يعمل كما يجب، والخللُ في أنّ الاستدعاء المحلّيّ لا يُطابِق استدعاءَ البوّابة فيُوهِم المُشغِّلَ أنّه قاس. **والعلاجُ المُقترَح:** أن يرفض الحارسُ العملَ بلا `--base` صراحةً (كما يفعل `state_transition` عرَضاً) بدل أن يقبل الوضعَ المُصغَّر صامتاً — أو أن يطبع أنّه فحص **صفرَ أزواج** فلا يُقرأ سكوتُه قبولاً. **ولا حارسَ له ولا طفرة:** حادثتان موثَّقتان بأدلّتهما، لا تغطيةٌ مفروضة. |
| COVERAGE-MASKED-BY-A-NEIGHBOURING-GUARD-01 | اختبارٌ يعبث بمُدخَلٍ فيُمسَك العبثُ **بحارسٍ آخر** قبل بلوغ الحارس المقصود — فيمرّ الاختبارُ ويبقى المقصودُ بلا تكذيب. تغطيةٌ بالاسم لا بالأثر، والاسمُ نفسُه يُطمئِن القارئ. | ci · governance · testing | [`guard_mutation_guard.py`](../../scripts/ci/guard_mutation_guard.py) · [`test_irrigation_decision_evidence_chain.py`](../../services/sahool-platform/tests/test_irrigation_decision_evidence_chain.py) · [`test_crop_cards.py`](../../services/sahool-platform/tests/test_crop_cards.py) · #889 · رقعةُ IRR-CORR1 | **open** — **مقيسٌ مرّتين في جلسةٍ واحدة، بشيفرتين لا صلةَ بينهما.** **(١) مُتحقِّقُ سلسلة أدلّة الريّ:** `test_parent_tamper_is_rejected` يعبث بـ`parent_digest`، والعبثُ يُغيّر محتوى المرحلة فتختلف بصمتُها، فيُمسَك بحارس **E1** قبل أن يبلغ حارسَ E2 إطلاقاً. النتيجة: تعطيلُ فحصَي `parent_stage_id` و`parent_digest` يُبقي **٥/٥ خضراء**. **(٢) مُتحقِّقُ بطاقات المحاصيل (#889):** `True` ككسرٍ غذائيّ يُمسَك **بالمصادفة** عبر فحص مجموع الكسور (1.5 ≠ 1.0)؛ ورتّبتُ الزرعَ ليبلغ المجموعُ `1.0` بالضبط فنفذ صامتاً. **والعلاجُ المقيس في الحالتين واحد:** أعِد المُدخَلَ إلى حالةٍ يقبلها الحارسُ الجار (إعادةُ حساب البصمات · ضبطُ المجموع) كي يبقى الحارسُ المقصودُ وحدَه هو ما يُطلِق. **ولمَ لا يُمسَك في المراجعة:** المراجعُ يقرأ اسمَ الاختبار ونتيجتَه الخضراء، وكلاهما صادقٌ حرفيّاً؛ والفارقُ لا يظهر إلّا بتعطيل الحارس المقصود ورؤيةِ الاختبار **لا يحمرّ**. **وحدُّ صدقٍ يُصغِّره:** المِرقابُ القائم (`guard_mutation_guard --run`) **يكشفه** — فليست ثغرةَ أداةٍ بل ثغرةَ **إجراء**: الرقعُ الواردة تُتبنّى بادّعاء تغطيتها قبل تشغيل المِرقاب عليها. **والعلاجُ المُقترَح:** تشغيلُ الزرع على كلّ حارسٍ تدّعي رقعةٌ واردة تغطيتَه **قبل** التبنّي، لا بعد ظهور عطل. **ولا حارسَ لهذا الصنف بذاته:** حادثتان موثَّقتان بأدلّتهما، لا تغطيةٌ مفروضة. |
| ADMISSION-GROUND-STATED-IN-PROSE-ENFORCED-BY-NOTHING-01 | ملفُّ الأساس يشترط في نثره أرضيّةً واحدةً لقبول وحدةٍ جديدة في المنصّة — **مستهلكٌ إنتاجيّ يُبلَغ من مسارٍ مركَّب** — ولا يفرض هذه الأرضيّةَ **أيُّ حارسٍ حاجب**. الحاجبُ عدديٌّ وهُويّاتيٌّ فقط، وكلاهما يُرضى بتحرير ملفَّي JSON بلا دليل بلوغٍ واحد. | ci · governance · architecture | [`platform_python_module_baseline.json`](../../docs/architecture/platform_python_module_baseline.json) (`ci10_knowledge_layer_note` · `persisted_agronomic_sor_chain_note`) · [`platform_module_reachability_guard.py`](../../scripts/ci/platform_module_reachability_guard.py) · [`platform_shrink_ratchet_guard.py`](../../scripts/architecture/platform_shrink_ratchet_guard.py) · #916 | **open** — **مقيسٌ بالتعطيل لا بالافتراض.** `ci10_knowledge_layer_note` يقول حرفيّاً «admitted on ONE ground only - it has a production consumer»، و`persisted_agronomic_sor_chain_note` يقول «every one of the five is REACHABLE FROM A MOUNTED ROUTE, measured, in the same change that makes it so». **والحاجبُ الفعليّ اثنان لا ثالثَ لهما:** `test_platform_python_module_budget_does_not_grow` (عدديّ صرف: `len(current) <= baseline_python_module_count`) و`platform_shrink_ratchet` (هُويّاتيّ: `new_identity = BLOCK_UNLESS_EXPLICIT_EXCEPTION`). **وحارسُ البلوغ يُبلِّغ ولا يحجب:** شُغِّل قبل تسجيل `api/irrigation_decision_evidence_chain.py` وبعده فأعطى `rc=0` في الحالتين، والفرقُ الوحيد سطرٌ إخباريّ `inherited (reported, not blocking): 138 ⇐ 139`. **فالنتيجةُ المقيسة:** وحدةٌ مستورِدُها الوحيدُ ملفُّ اختبارها دخلت السطحَ بتحرير ملفَّي سياسة، ولم يُطلَب دليلُ بلوغٍ واحد ولم يحمرّ شيء. **ولا يُصغِّرها أنّ التسجيل كان صادقاً:** الصدقُ هنا اختياريّ — النثرُ يطلب والآليّةُ لا تسأل. **والعلاجُ المُقترَح بحدوده:** ليس رفعَ حارس البلوغ إلى حاجبٍ فوراً (١٣٩ وحدةً موروثة بلا جذرٍ تنفيذيّ ⇒ حجبٌ فوريّ للشجرة كلّها)، بل **راتشِتٌ على الموروث**: العددُ لا يصعد. فالوحدةُ الجديدة بلا جذرٍ تنفيذيّ تحمرّ، والموروثُ يبقى معدوداً ظاهراً. **ولا حارسَ لهذا الصنف بذاته:** حادثةٌ واحدة موثَّقة بدليلها، لا تغطيةٌ مفروضة. |
| RUNNER-CRASH-READS-AS-A-TEST-FAILURE-WHEN-ITS-MESSAGE-SAYS-FAILED-01 | `ran_at_all()` تفصل «سقطت اختبارات» عن «لم يُشغَّل شيء» بمطابقة **سلسلةٍ حرّة** `" failed"` في المخرَج — فرسالةُ انهيارٍ تحوي الكلمة تُقنِعها أنّ pytest عمل، وهو لم يجمع اختباراً واحداً. فيُحكَم على كلّ طفرةٍ بأنّها «حمرّت بغير الاختبار المُتوقَّع». | ci · governance · testing | [`guard_mutation_guard.py`](../../scripts/ci/guard_mutation_guard.py) (`ran_at_all` · `failing_tests` · `_FAILED_RE`) · #916 | **open** — **العطلُ داخل الآليّة التي وُضِعت لمنعه.** وثيقةُ `ran_at_all` تقول صراحةً إنّها بُنِيت بعد أن أبلغت `--run` عن «١٨ حمرّ بغير الاختبار المُتوقَّع» في وظيفةٍ بلا pytest، و«صحيحٌ حرفيّاً ويُرسِل قارئه إلى المكان الخطأ». **والمقيس أنّها لم تسدّه:** `pyo3_runtime.PanicException: Python API call failed` — الكلمةُ الأخيرة `failed` مسبوقةٌ بفراغ، فتُطابِق `" failed"` في `any(m in out for m in …)`. مِسبارٌ على المخرَج الحقيقيّ: `" passed"` غائبة · `" failed"` **حاضرة** · `" error"` غائبة · `"no tests ran"` غائبة · وعددُ الأسماء التي يلتقطها `_FAILED_RE` = **صفر**. **والحجمُ يقطع أنّها ليست خصوصيّةَ شيفرة:** ٢٩ طفرةً من ٢٩ في تشغيلٍ واحد أعطت العَرَض نفسه — بينها `bidi_control_char_guard` و`brain_*` و`branch_protection_contract_guard`، ولا صلةَ بينها. **والشجرةُ سليمة:** الملفُّ الذي اتُّهِم يمرّ `10 passed · rc=0` وحدَه، وCI أخضرُ على الشريحة نفسها. **ولمَ لا يُمسَك بالمراجعة:** الرسالةُ تُسمّي اختباراً حقيقيّاً وتقول إنّه لم يحمرّ، وكلاهما صادقٌ حرفيّاً؛ والفرقُ لا يظهر إلّا بسؤال «هل جمع pytest شيئاً أصلاً؟». **والعلاجُ المُقترَح:** ترسيةُ العلامات على **شكل سطر ملخّص pytest** لا على سلسلةٍ حرّة (`^=+.*\d+ (passed|failed|error)` أو `no tests ran`)، فرسالةُ استثناءٍ لا تُطابِقه. |
| SWEEP-SELF-CHECK-CANNOT-TELL-A-GUARD-WRITE-FROM-MY-OWN-COMMIT-01 | فحصُ المِكنسة لذاتها يقارن حالةَ الشجرة بين بدايته ونهايته ليكشف حارساً يكتب أثناء الفحص — ولا يملك ما يفصل كتابةَ حارسٍ عن **إيداعي أنا** في تلك النافذة. فالإيداعُ أثناء التشغيل يُنتِج إخفاقاً يصف حادثةً لم تقع. | ci · governance | [`verify_all_generated.py`](../../scripts/ci/verify_all_generated.py) · #916 | **open** — **مقيسٌ بحادثةٍ كاملة:** ٧٤ خطوةَ `--check` كلُّها ✓، ثمّ `rc=1` برسالة «حارس كتب أثناء الفحص — الشجرة تغيّرت بين بدايته ونهايته» تُسمّي `release/FILE_CHECKSUMS.sha256` و`release/SAHOOL_RELEASE_MANIFEST_20260626.json`. **ولم يكتبهما حارس:** كانا مُعدَّلَين غيرَ مُودَعَين عند بدء المِكنسة، وأودعتُهما أثناء تشغيلها، فرآهما الفحصُ نظيفَين عند النهاية — تغيُّرٌ حقيقيّ بسببٍ آخر. **والشاهدُ القاطع** إعادةُ التشغيل على شجرةٍ نظيفةٍ مُودَعة بلا لمسٍ أثناءها: `rc=0` و«كلّ المصنوعات المولَّدة المُكتشَفة متّسقة» — نقطةُ ثبات. **وحدُّ صدقٍ يُصغِّرها:** الفحصُ **مُحِقٌّ في حجبه** — الشجرةُ تغيّرت فعلاً، وحكمُه على ما قاس صحيح؛ الخللُ في **نسبة** التغيير إلى فاعلٍ بعينه. **والخطرُ أنّه يُدرِّب قارئه على تجاهله:** من رأى الإنذارَ كاذباً مرّةً يقرؤه ضجيجاً في المرّة التي يكون فيها حارسٌ يكتب حقّاً. **والعلاجُ المُقترَح:** التقاطُ `HEAD` مع حالة الشجرة عند الطرفين، فإن تحرّك `HEAD` تقول الرسالةُ «الشجرةُ تغيّرت **و**`HEAD` تحرّك — الأرجح إيداعُك أنت؛ أعِد التشغيل على شجرةٍ ساكنة» بدل اتّهام حارسٍ لم يفعل. تفريقٌ يُبقي الحجبَ ويُصلِح التشخيص. |
| WEATHER-CLIENT-ASKS-A-PATH-THE-SERVICE-NEVER-DECLARED-01 | عميلُ الطقس يطلب `/v1/weather/tile-cache/stats` والخدمةُ تُعلن `/v1/weather/cache-stats` — **404 حتميّ** لا احتماليّ. وطرفا العقد مختبَران كلٌّ وحدَه، فالقفزةُ بينهما لا يفحصها أحد. | weather · platform · contracts | [`weather_service_client.py`](../../services/sahool-platform/api/weather_service_client.py) (`get_tile_cache_stats`) · [`weather-service/main.py`](../../services/weather-service/main.py) · [`test_weather_client_paths_exist_on_the_service.py`](../../tests_v9/test_weather_client_paths_exist_on_the_service.py) | **fixed** — **مقيسٌ بجرد السطح كلِّه:** ٢٧ مساراً مُعلَناً في `weather-service`، **لا واحدَ منها** باسم `tile-cache/stats`. والدالّةُ الخلفيّةُ واحدةٌ للاسمين (`rt.tile_cache_stats`)، فالانحرافُ في السلسلة النصّيّة وحدَها. **ولمَ أفلت من الاختبارات:** اختبارُ العميل يزيّف الاستجابة، واختبارُ الخدمة ينادي مسارَها الصحيح — فيمرّ الطرفان خضراء والقفزةُ بينهما بلا شاهد. **والعلاجُ صُحِّح فيه العميلُ لا الخدمة:** تغييرُ مسار الخدمة كان سيكسر أيَّ مستهلكٍ آخر يناديه بالاسم القانونيّ، ومسارُ المنصّة العامّ `/api/v1/weather/tile-cache/stats` يبقى — القفزةُ المُصلَحة داخليّة. **والحارسُ مُكذَّب:** إعادةُ السلسلة القديمة تُحمِّر `test_no_client_path_is_absent_from_the_weather_service_surface` و`test_the_specific_regression_stays_closed`، ويُغلَق الفحصُ على نفسه بـ`test_the_reader_actually_found_both_sides` (١٨ مساراً مقروءاً من العميل · ٢٧ من الخدمة) لئلّا يمرّ أخضرَ وهو يقرأ صفراً. |
| DEGRADED-SAMPLE-CRASHES-THE-GUARD-THAT-SHOULD-REFUSE-IT-01 | `operation_suitability(None, …)` يرفع `AttributeError` غيرَ ملتقَط ⇒ **500** على `operation-tile-data` كلّما تدهور المزوّد — بينما آليّةُ الفشل المغلق قائمةٌ بعده بخطوةٍ ولا تُبلَغ. | weather · resilience | [`operations.py`](../../services/weather-service/operations.py) (`operation_suitability` · `_num`) · [`weather_runtime.py`](../../services/weather-service/weather_runtime.py) (`operation_tile_data`) · [`test_degraded_sample_is_not_a_crash.py`](../../services/weather-service/tests/test_degraded_sample_is_not_a_crash.py) | **fixed** — **والتشخيصُ الشائع لهذا العطل خاطئ، والفرقُ يُغيّر العلاج.** الظنُّ أنّ `payload["sample"]` يرفع `KeyError`؛ والقياس ينفيه: `tile_data` يعود بعبارةِ `return` **واحدة** فيها `"sample"` **دائماً**، وعند تدهور المزوّد لا يغيب المفتاح بل تصير قيمتُه `None`. فحراسةُ المفتاح في موضع النداء ما كانت لتُصلِح شيئاً. **والسببُ الحقيقيُّ مقيسٌ بالتنفيذ:** `_num` يحمي من **قيمةٍ** فاسدة (`except TypeError, ValueError`) لا من **عيّنةٍ** غائبة، فـ`sample.get(...)` على `None` يرفع `AttributeError` وهو غيرُ ملتقَط. **والعلاجُ سطرٌ واحد** (`sample = sample or {}`) في المدخل الواحد فيغطّي الأفعالَ الخمسة، ويبلغ الفشلَ المغلق القائم: `score=0.0 · status=insufficient_data · limiting_factors=[missing_wind, missing_precip]` — الجوابُ الصادق «مُدخَلُ سلامةٍ مفقود» بدل انهيار. **والخاصّيّةُ المحروسة ليست «لا ينهار»** بل أنّ الدرجةَ صفرٌ: حارسٌ يُرجِع درجةً صالحةً عن مُدخَلٍ غائب أخطرُ من الانهيار — نافذةُ رشٍّ زائفةٌ تُقرأ إذناً. |
| PLATFORM-ROUTES-BYPASS-THE-BREAKER-BY-IMPORTING-THE-PROVIDER-01 | مساران في مساحة الحقل يستوردان موصّلَ Open-Meteo **داخل الدالّة** فيخرجان مباشرةً إلى المزوّد، متخطّيَين قاطعَ الدارة والمخبّأ اللذين تمرّ بهما بقيّةُ مسارات الملفّ نفسِه. | weather · platform · resilience | [`field_workspace_weather.py`](../../services/sahool-platform/api/routers/field_workspace_weather.py) (`:229` · `:284` مقابل `:23`) | **fixed** — مقيسٌ بالسطر: الملفُّ يستورد `weather_service_client` في رأسه (`:23`) لبقيّة مساراته، ثمّ يستورد `api.connectors.openmeteo` **داخل** دالّتين (`:229` توصيةُ الريّ · `:284` مخاطرُ الأمراض). فالمساران يفقدان قاطعَ الدارة والمخبّأ والمهلةَ الموحّدة، وتدهورُ المزوّد يظهر فيهما بصورةٍ مختلفةٍ عن أخواتهما في الملفّ نفسه. **وحدُّ صدقٍ في اكتشافها:** أوّلُ بحثٍ لي عنها بـ`open_meteo`/`open-meteo` أعطى **صفراً** فظننتُها منقوضة — والاسمُ الحقيقيّ `openmeteo` بلا فاصل. فالنفيُ المبنيُّ على بحثٍ نصّيٍّ واحد ليس نفياً. **ولا حارسَ لها:** لا شيءَ يمنع استيراداً داخل دالّة، والعلاجُ المُقترَح حارسٌ يرفض استيرادَ الموصّلات في `api/routers/` — يلزمه جردُ الاستثناءات المشروعة أوّلاً.  **⚠ تصحيحُ آليّة (2026-08-27، مقيس):** «متخطّيَين قاطعَ الدارة» **خطأ** — `open_meteo._fetch_json:164` يفحص القاطعَ قبل كلّ طلبٍ للمزوّد و`:171` يُسجّل نجاحَه، و`fetch_current`/`fetch_daily_forecast` تمرّان به. **فالقاطعُ سليمٌ في المسارين.** والمتجاوَزُ فعلاً شيئان: **عقدُ الواجهة P3.4** (المنصّةُ تُلزَم بنداء `weather_service_client` لا باستيراد موصّلات Open-Meteo — نصُّ ترويسة العميل) **ومخبّأُ خدمة الطقس** (`cache_get`/`cache_set` في `weather_runtime`؛ و`open_meteo` بلا مخبّأ). والنتيجةُ قائمةٌ والآليّةُ صُحِّحت — وهو صنفُ «صحّت نتيجتُها وخانتها آليّتُها» الذي سمّاه متنُ #946 نفسُه، واقعاً فيه. **وعلاجُها ليس سطراً:** العميلُ يُعيد `dict` والمستدعي يقرأ سماتِ كائنات، والخدمةُ تُعيد مشاهدةً من `CanonicalWeatherState` بشكلٍ ثالث — فيلزم مُحوِّلٌ مُختبَر.  **✅ أُغلِقت (2026-08-27، #P6):** المساران يناديان الآن `get_current_weather`/`get_weather_forecast` من `weather_service_client`، ولا مُستوردَ للموصّل في الملفّ. **والمُحوِّلُ المُتوقَّع صار سطرين مُختبَرين** (`_forecast_days` · `_reading`): أيّامُ التوقّع تحت مفتاح `days` في غلافِ `forecast_view`، والقراءةُ الناقصة تصل `None` مُسمّاةً في `missing_fields` بـ`quality_status: degraded`. **وأُغلِق معها عطلان سابقان للموصّل** (`openmeteo.py:279-280`: `c.get("temperature_2m", 0)`): مفتاحٌ غائب ⇒ `0` فتُقرَأ `0°م` و`0٪` رطوبةً ⇒ خطرُ أمراضٍ `low` — **جوابٌ مطمئنٌّ من لا-بيانات**؛ ومفتاحٌ `null` ⇒ `float(None)` ⇒ ٥٠٠. كلاهما صار ٥٠٣ يُسمّي الناقص. **والحارسُ القائم هو الذي أقفل الحلقة:** `test_p3_5_weather_direct_wiring_final_sweep` كان يُدرِج الملفَّ «متبقّياً pending P4»، وحذفُ الاستيراد ألزم حذفَ مدخله (`test_allowlist_residuals_and_homes_are_not_stale` يُحمِّر المداخلَ البائتة). **وشاهدُ القفزة** `tests_v9/test_weather_views_survive_the_hop_to_the_platform.py` يُشغّل مُنتِجَ الخدمة الحقيقيّ في مُستهلِك المنصّة الحقيقيّ — لا تزييفَ لأيّ طرف. **وثقبان في الحارس نفسِه قِيسا وأُغلِقا:** كان الكشفُ نصّيّاً فيتّهم النثرَ (تعليقٌ يشرح هجرَ الموصّل كان يُبقي الملفَّ مخالفاً — أي أنّ توثيقَ الإصلاح يُبطِله) **ويُفلِت التهرّب** (`from api.connectors import openmeteo` لا يحوي السلسلة `connectors.openmeteo` إطلاقاً، و`fetch_bundle` كان خارج القائمة رأساً). صار الكشفُ بـ`ast`، والعلاماتُ سبعاً. |
| AN-ACCEPTED-HORIZON-IS-QUANTISED-TO-TWO-BUCKETS-01 | `horizon_hours` يُقبَل ويُتحقَّق منه (`ge=1, le=168`) ثمّ **يُهمَل** — لا يُستعمَل إلّا كقيمةٍ منطقيّة `> 48`. فـ`49` و`168` يُنتِجان الطلبَ نفسَه حرفيّاً. والمُعامل يَعِد بأفقٍ ويُسلّم إحدى دلوَين. | weather · platform · contracts | [`field_workspace_weather.py`](../../services/sahool-platform/api/routers/field_workspace_weather.py) (`:174` · `:190-192` · `:57`) | **fixed** — **والدعوى الأصليّة كانت معكوسة، والقياسُ صحّحها:** قيل «الخادم يسقط ما فوق ٤٨ صامتاً»، والشيفرةُ تُمدِّد صراحةً إلى `0,1,3,6,12,24,48,72,96,120,144,168`. فالعطلُ ليس إسقاطاً بل **تكميماً**: أفقٌ مطلوبٌ بين ٤٩ و١٦٨ يُخدَم بالقائمة الكاملة دائماً. **وفيها عطلٌ ثانٍ مستقلّ:** `"start_at": best.get("time") or best.get("weather_time")` — و`best["time"]` قيمةٌ **رمزيّة** (`time_key_from_hour` ⇒ `'now'` · `'+3h'` · `'+168h'`) تُضبَط بلا شرط، فتفوز دائماً على `weather_time` الذي يحمل الطابعَ الزمنيّ الحقيقيّ. فحقلٌ اسمُه `start_at` يُقرأ طابعاً زمنيّاً ويحمل `'+3h'`. **وعلاجُه قلبُ ترتيب `or`** — والأوّلُ يحتاج قراراً: أيُخدَم الأفقُ بدقّة أم يُعلَن التكميمُ في العقد. **أُغلِق شقُّ `start_at` 2026-08-27، ويبقى التكميمُ مفتوحاً.** قُلِب ترتيبُ `or` فصار الطابعُ الحقيقيّ (`weather_time`) أوّلاً والرمزُ احتياطاً، وأُضيف `start_at_is_relative_offset` كي يعرف المستهلكُ ما بين يديه بدل أن يخمّنه من شكل السلسلة. **ولم يُحذَف الرمز:** حين لا يُصرّح المزوّدُ بوقتٍ يبقى أنفعَ من `null` — بشرط أن يُعلَن. **مُكذَّبٌ بالزرع:** بالترتيب القديم يعود `'+3h'` بدل الطابع. **والتكميمُ (٤٩ و١٦٨ طلبٌ واحد) يبقى `open`** لأنّ علاجَه قرارُ عقدٍ لا إصلاحُ سطر: أيُخدَم الأفقُ بدقّةٍ أم يُعلَن التكميمُ في العقد. **تصحيحٌ 2026-08-27 — وصفي للآليّة كان خاطئاً، ودعوى المراجعة الأصليّة كانت صحيحة.** كتبتُ «يُمدِّد صراحةً فالعطلُ تكميمٌ لا إسقاط» بناءً على طرف المنصّة وحدَه، ولم أتبع السلسلةَ إلى الخدمة. و`parse_series_hours` في `services/weather-service/tiles.py` كان بقائمة سماحٍ **مغلقة** على `{0,1,3,6,12,24,48}` **ترمي** `72,96,120,144,168` صامتةً — فالمقيس: أُرسِلت ١٢ إزاحةً ووصلت ٧، و`horizon_hours=168` و`=48` يُنتِجان النتيجةَ نفسَها **حرفيّاً**. أي **إسقاطٌ صامتٌ كما قيل أوّلاً**، لا تكميم. **وعطلٌ ثانٍ معاكسٌ لم يُرصَد من قبل:** `horizon_hours=24` كان يُرسِل `48`، فتعود نافذةٌ تبدأ بعد **ضِعف** الأفق المطلوب. **ولمَ أفلت الطرفان:** كلٌّ سليمٌ بمعزل — المنصّةُ تُرسِل قائمةً معقولة، والخدمةُ تُصفّي مُدخَلاً غيرَ موثوق؛ والعطلُ في **القفزة** بينهما، ولا يظهر إلّا بقياس الطرفين معاً. وهو أخو `WEATHER-CLIENT-ASKS-A-PATH…-01` في السبب: عقدٌ طرفاه مختبَران كلٌّ وحدَه. **أُغلِق 2026-08-27:** مدًى محدود (`0..MAX_SERIES_HOUR=168`) بدل قائمة السماح · إزالةُ تكرارٍ بحفظ الترتيب · وسقفُ `MAX_SERIES_FRAMES=16` يحدّ الكلفة (كلُّ إطارٍ عيّنةُ مزوّدٍ تُضرَب في خمس عمليّات، فبلا سقفٍ يصير طلبٌ واحد مئاتِ النداءات). والمنصّةُ تشتقّ السلّمَ **مقصوراً على الأفق** بدل ثابتين، ويُعلَن `horizon_hours` و`sampled_offsets_h` في الجسم — فالمُعامِلُ يحكم **المدى** والسلّمُ يحكم **الكثافة** والمستهلكُ يرى الاثنين بدل أن يفترض ساعةً بساعة. **ولم يُقصَّ المُدخَل** (`min(max,h)` كما في `weather.py:_parse_series_hours`) لأنّ القصَّ يُنتِج قيمةً لم يطلبها أحدٌ ويُخفي أنّ الطلبَ كان خارج المدى — فيُبدِّل كذباً بكذب. **ومُكذَّبٌ من الطرفين منفردَين:** زرعُ قائمة السماح وحدَها ⇒ يُرمى `[72,96,120,144,168]`؛ وزرعُ الثابت في المنصّة وحدَه ⇒ أفقُ ٢٤ يُعاين ٤٨. فإصلاحُ طرفٍ واحدٍ **لا يُخضِر الحارس** — وذلك ما يجعله حارساً للقفزة لا لطرفٍ فيها. **تتمّةٌ مقيسة 2026-08-27 — الإصلاحُ في #948 كان طرفَ المنصّة وحدَه، وأثرُه مُبطَلٌ حيث يهمّ.** `_series_for_horizon` صار يشتقّ السلّمَ من `horizon_hours` (إصلاحٌ صحيح)، لكنّ `parse_series_hours` في `services/weather-service/tiles.py` بقي بقائمة سماحٍ **مغلقة** على `{0,1,3,6,12,24,48}` **ترمي** ما فوقها صامتاً. **والمقيس على رأس main بعد #948:** أفق 168 يُرسِل ١٢ إزاحةً ويصل ٧ (ضاع `[72,96,120,144,168]`)، و`parse_series_hours(_series_for_horizon(48)) == parse_series_hours(_series_for_horizon(168))` **⇒ True** — أي أنّ الأفقَين ظلّا يُنتِجان النتيجةَ نفسَها حرفيّاً **بعد الإصلاح كما قبله**. **ولمَ لم يكشفه اختبارُ #948:** يعيش في `services/sahool-platform/tests/` ويقرأ الراوترَ وحدَه — لا يستورد `tiles` ولا `parse_series_hours`. فيُثبِت أنّ المنصّة **تُرسِل** الصحيح لا أنّ الخدمة **تستقبله**. وهو الصنفُ نفسُه الذي أسقط `WEATHER-CLIENT-ASKS-A-PATH-THE-SERVICE-NEVER-DECLARED-01`: عقدٌ طرفاه في خدمتين، وكلٌّ مختبَرٌ وحدَه، والقفزةُ بلا شاهد — ووقع مرّتين في أسبوعٍ واحد. **أُغلِق الطرفُ الثاني:** مدًى محدود (`0..MAX_SERIES_HOUR=168`) بدل قائمة السماح · إزالةُ تكرارٍ بحفظ الترتيب · و`MAX_SERIES_FRAMES=16` يحدّ الكلفة (كلُّ إطارٍ عيّنةُ مزوّدٍ تُضرَب في خمس عمليّات). **ولم يُقصَّ المُدخَل** (`min(max,h)` كما في `weather.py:_parse_series_hours`) لأنّ القصَّ يُنتِج قيمةً لم يطلبها أحدٌ ويُخفي أنّ الطلبَ كان خارج المدى. **والشاهدُ الجديد يقيس الرحلة لا طرفاً:** `tests_v9/test_horizon_survives_the_hop_to_the_service.py` — ثمانيةُ آفاقٍ تصل كاملةً، و`48 ≠ 168`. |
| ONE-BAD-ROW-ABORTS-THE-WHOLE-SIGNAL-CYCLE-01 | `run_cycle` يمرّ على التراكبات بلا حراسةٍ لكلّ صفّ، فصفٌّ واحدٌ يرفع استثناءً يُسقِط **الدورة كلَّها** — وتبقى بقيّةُ الحقول بلا إشارات حتّى الدورة التالية، والسجلُّ لا يُسمّي الحقلَ الجاني. | weather · workers · resilience | [`weather-signal-engine/src/main.py`](../../services/weather-signal-engine/src/main.py) (`run_cycle` `:93-100` · الحلقةُ الخارجيّة `:112-119`) | **open** — مقيسٌ بالبنية: `for ov in overlays: total += await process_overlay(conn, ov)` بلا `try` داخليّ. والحلقةُ الخارجيّة تلتقط (`except Exception` ⇒ تحذير + نوم `INTERVAL_SEC`)، فالمحرّكُ لا يموت — **لكنّ الدورة تسقط كاملةً**، والتحذيرُ يقول «تعذّرت دورة توليد الإشارات» بلا اسمِ الحقل. فالعطلُ صامتٌ للمُشغِّل ومُكلِفٌ للحقول السليمة في الدورة نفسها. **ونصفُ الدعوى الأصليّة سقط:** «سباقُ نسختَي engine» لا شاهدَ له — مُحرِّكٌ واحدٌ يكتب `weather_signals`، وثلاثةُ ملفّاتٍ تمسّ `field_weather_overlay` اثنان منها عاملُ مضلّعاتٍ وخطُّ أنابيب. سُجِّل النصفُ المقيس وحدَه. |
| ABSENT-READING-COERCED-TO-ZERO-READS-AS-A-MEASUREMENT-01 | قراءاتٌ غائبة من المزوّد تُصفَّر بـ`or 0` — فالمطرُ المفقود يُقرأ «جافّ» والريحُ المفقودة «ساكنة». وهي أخطرُ صور الكذب الصامت: صفرٌ مُختلَقٌ يدخل قرارَ رشٍّ بوصفه قياساً. | weather · data-quality | [`open_meteo.py`](../../services/weather-service/open_meteo.py) (`:218` · `:231` · `:326` · `:427` · `:431-436` مقابل `:441`) | **fixed** — والصفُّ سقط صنفين، لا صنفاً: **كان نصفُه خطأً يومَ كُتِب**. دعواه أنّ `_at(..., idx, 0)` يُصفّر الحرارةَ والرطوبةَ والمطرَ والغيومَ في المسار الساعيّ كانت **كاذبةً وقتَ التسجيل**: المسارُ الساعيُّ صار صادقاً في `bba61eea` (#845) — وهو **سلفُ** `673bc161` (#946) الذي كتب الصفّ. ثمّ أُغلِق الباقي في `7508702a` (#948) وبقي الصفُّ `open` بعده. المقيسُ على `399614e4`: المسارُ الآنيُّ يُمرّر القراءةَ خاماً (`open_meteo.py:282` وأخواتُه ⇒ `None` عند الغياب) والرياحُ مشروطةٌ صراحةً (`... if wind_kmh is not None else None`)؛ والساعيُّ `_at(..., idx)` بلا افتراضٍ صفريّ (`:483-486`). ولم يبقَ من الصنف إلّا **موضعان يوميّان مقصودان** (`:359` · `:371`) أساسُهما مكتوبٌ لا مُفترَض. والحارسُ الذي اقترحه الصفُّ **وُضِع**: [`test_absent_reading_is_not_a_zero_measurement.py`](../../services/weather-service/tests/test_absent_reading_is_not_a_zero_measurement.py) براتشِتٍ على عدد المواضع. **ونقصٌ باقٍ أُغلِق في شريحة التصحيح نفسِها:** القيدُ يبلغ المستهلكَ في `limitations` (`canonical_weather_state.py:345-349`) لكنّ الطبقتين كانتا تُعلنان الحقيقةَ الواحدة مرّتين بلا رابط — **شرطان يتّفقان اليوم**، مُثبَّتٌ كلٌّ بحرفيّته في ملفٍّ لا يذكر الآخر. مُكذَّبٌ بالزرع لا بالقراءة: حقلٌ ثالثٌ مُصفَّرٌ ومُعلَنٌ عند الحافّة مرّ بـ**١٦٨ حالةً خضراء** والقيدُ المنشورُ يسمّي اثنين من ثلاثة — قاعدةٌ ضيّقةٌ تحت اسمٍ عريض. فصار التقابلُ تعريفاً واحداً (`_DAILY_ZERO_COERCED_FIELD_MAP`) يحرسه `test_the_published_caveat_names_every_field_the_edge_actually_coerces` **بالاحتواء لا التساوي** (اتّجاهُ الخداع وحدَه، فمُزوّدٌ ثانٍ يستطيع أن يُوسّع) — احمرَّ على الزرع نفسِه واخضرَّ برفعه. |
| A-SILENT-CLAMP-HIDES-AN-OUT-OF-RANGE-INPUT-01 | `rh = max(0.0, min(100.0, rh_pct))` يقصّ الرطوبةَ النسبيّة بلا أثر: مُدخَلٌ خارج المدى (خطأُ وحدةٍ أو حسّاسٌ معطوب) يُقصّ إلى حدٍّ صالحٍ ويدخل حسابَ ET0 كأنّه قياس. | weather · data-quality | [`vapor_pressure.py`](../../services/weather-service/vapor_pressure.py) (`:42`) | **fixed** — كان صادقاً يومَ كُتِب (#946) وسقط بعده: `7508702a` (#948) أصلح الكودَ **وكتب الإصلاحَ في نصّ التزامه** («`actual_vapor_pressure_from_rh_kpa` صار يرفع `ValueError` على مُدخَلٍ كان يمرّ») ثمّ مسّ `registry.md` لصفٍّ **واحدٍ فقط** — غيرِ هذا. فدليلُ الإغلاق عاش في رسالة التزام والسجلُّ يقول `open`. المقيسُ على `399614e4`: القصُّ غيرُ المحدود زال، و`vapor_pressure.py:57-63` يرفض ما خرج عن نطاق ضجيج المستشعر `[-5, 105]` بـ`ValueError` (`_RH_SENSOR_TOLERANCE_PCT = 5.0`) — فـ`120٪` لم تعد تصير `100٪`، و`350٪` تُفشِل الحسابَ حيث وقع العطلُ بدل أن تمضي إلى ET0 قياساً واثقاً. والقصُّ الباقي `[0, 100]` يقع **بعد** اجتياز البوّابة، أي على ضجيجٍ حول الحدّين لا على قراءةٍ مكسورة. وهو أوّلُ العلاجين اللذين اقترحهما الصفُّ: الرفضُ فاشلاً مغلقاً كأخواته. |
| READINESS-PROBES-THE-UPSTREAM-ON-EVERY-CALL-01 | `readyz` يضرب المزوّدَ الخارجيَّ حيّاً في كلّ نداء — فجاهزيّةُ الخدمة تصير دالّةً في صحّة طرفٍ ثالث، والمُنسِّقُ الذي يستطلعها كثيراً يُنتِج حِملاً على المزوّد ويعرّض الخدمةَ لإعادة تشغيلٍ بسببٍ خارجها. | weather · ops · resilience | [`weather_runtime.py`](../../services/weather-service/weather_runtime.py) (`readyz` `:75-87`) | **fixed** — صفٌّ بائتٌ أُغلِق كودُه ولم تُحرَّك حالتُه؛ **وهو ثالثُ صفٍّ من يد `7508702a` (#948) نفسِها** بعد `A-SILENT-CLAMP…` و`ABSENT-READING…` (أُغلِقا في #968). المقيسُ على `fe4c7744`: `weather_runtime.py` يحمل `_READYZ_OBSERVED_SUCCESS_TTL_S = 30.0` و`_upstream_readiness()` بجدولِ قرارٍ رباعيٍّ مكتوبٍ في موضعه (قاطعٌ مفتوح ⇒ `degraded` بلا نداء · إخفاقاتٌ > 0 ⇒ يُقاس الآن · نجاحٌ منبعيٌّ حديث ⇒ `ready` بلا نداء · باردةٌ ⇒ يُقاس)، و`readiness_source` مُعلَنٌ في الردّ فلا يُقرأ المُستنتَجُ قياساً جديداً. وله اختبارُه `test_readiness_does_not_probe_on_every_call.py`. **والعلاجُ ليس تخبئةَ نتيجة المِسبار** — جُرِّب فأحمرّ `test_readyz_reports_degraded_when_open_meteo_probe_fails` بحقّ، والتعليلُ مكتوبٌ في المصدر. |
| DEAD-FILES-TRACKED-AS-IF-THEY-WERE-SOURCE-01 | ملفّان باسم `main.before_p2` متعقَّبان في الشجرة — نسخٌ احتياطيّةٌ يدويّةٌ من قبل تعديل، تُقرأ مصدراً وتدخل المسح والجرد والبصمات. | repo-hygiene | `services/weather-service/main.before_p2` · `services/sam2-inference/main.before_p2` | **fixed** — **واثنان لا واحد**، وهذا فرقٌ يخصّ الصنف لا العدد: نسخةٌ يدويّةٌ واحدةٌ حادثة، واثنتان في خدمتين مختلفتين **نمط**. تدخلان جردَ الملفّات وبصماتِ الحزمة، ويقرؤهما مَن يبحث في الشجرة عن `main` فيجد نسخةً بائتة بلا علامةٍ تقول إنّها ميّتة. **ولا حارسَ للصنف:** لا شيءَ يمنع إيداعَ ملفٍّ بلاحقةٍ كهذه. **والعلاجُ المُقترَح** حذفُهما وحارسٌ يرفض اللواحقَ المعروفةَ للنسخ اليدويّة (`.before_*` · `.bak` · `.orig`) — والحذفُ وحدَه بلا حارسٍ يُغلِق الحادثة ولا يمنع تكرارها.  **✅ أُغلِقت (2026-08-27):** الملفّان حُذِفا في #948 (`7508702a`) — والحذفُ نصفُ العلاج بنصّ هذا الصفّ نفسِه. والنصفُ الثاني `scripts/ci/no_manual_backup_files_guard.py`: `git ls-files` + لواحقُ أدوات النسخ والدمج (`.bak` · `.orig` · `.rej` · `.save` · `~` · مقطعُ `.before_*`). حاجبٌ في `ci.yml` (وظيفة البنية) وفي `preflight.sh` (٢أ، دون ثانية). **والنطاقُ ضيّقٌ بقياس:** صفرُ مطابقات على ٥٧٠٨ ملفّاً متعقَّباً، و`.old`/`copy` مستبعدتان عمداً — حارسٌ يُنذِر كذباً يُدرَّب الناسُ على تجاهله فيموت وهو أخضر. و`.gitignore` لا يحمل سطراً واحداً لهذه اللواحق (مقيس). **ومُكذَّبٌ بخمس طفرات مُسجَّلة، الخمسُ زُرِعت وقُتِلت. وسادسةٌ نجت فأُسقِطت بدل أن تُسجَّل:** كان في الحارس عزلٌ لاسم الملفّ (`rsplit("/", 1)[-1]`) وطفرةٌ تُسقِطه — فنجت، لأنّ كلَّ بدائل النمط مرساةٌ بـ`$` ونهايةُ المسار هي نهايةُ الاسم. احتياطٌ لا يمنع شيئاً يُقرَأ ضماناً ويُسجَّل تغطية، فحُذِف الاحتياطُ والخاصّيّةُ باقيةٌ مفروضةً بآليّتها الحقيقيّة. |
| CALLER-KEPT-THE-OLD-SCALAR-CONTRACT-AFTER-THE-CALLEE-RETURNED-A-TUPLE-01 | `cache.get` تُعيد ثلاثيّة `(value, state, age)`، وأربعةُ مُعالِجات كُتبت بعدها بالاصطلاح القياسيّ القديم `series = cache_get(key)` / `if series is None:`. والثلاثيّةُ ليست `None` أبداً ⇒ الشرطُ لا يصدق ⇒ لا جلبَ ولا تخزين، ثمّ `series.get(...)` على `tuple` ⇒ `AttributeError` ⇒ **500 على كلّ نداء منذ يوم الكتابة**. | weather-service · runtime | [`weather_runtime.py`](../../services/weather-service/weather_runtime.py) (`:414` · `:482` · `:512` · `:539`) · [`cache.py:46`](../../services/weather-service/cache.py) · `017c035b` (الثلاثيّة) · `b614b3ee` و`ca91905f` (المُعالِجات، 2026-07-10) | **fixed** — أُصلِحت الأربعة بالاصطلاح نفسه القائم في موضعَين صحيحَين من الملفّ ذاته (`:153` · `:292`)، وأُضيف حارسٌ عبر `TestClient` بثلاثة فروع (بارد · طازج · بائت) × أربع نقاط. **مُكذَّبٌ ١٢/١٢ في الموضع:** عودةُ الاصطلاح القديم تقتل فرع «البارد» · إسقاطُ شرط المخبّأ يقتل «الطازج» · `if series is None` وحدها تقتل «البائت» — وهي الطفرةُ الوحيدة التي تنجو من الفرعَين الآخرَين (البائتُ ليس `None` فيُخدَم صامتاً). **وحدُّ صدق:** العطلُ لم يُكشَف بقراءةٍ بل **بتنفيذ** (`'tuple' object has no attribute 'get'`)، ولم يُحمِّره أيُّ حارسٍ قائم — الأربعةُ كانت خارج كلّ اختبارٍ يبني `TestClient`. **ولم يُعالَج البُعدُ البائت الأوسع:** لا تراجعَ إلى المُخبّأ البائت عند فشل الجلب (`_cached_sample` وحده يفعلها) — سلوكُ 503 باقٍ كما كان، عمداً، فتغييرُه قرارُ تصميمٍ لا إصلاحُ عطل. |
| SERVICE-ROUTES-WITNESSED-ONLY-AT-THE-PURE-CORE-01 | اختباراتُ خدمة الطقس تستورد `compute_*` مباشرةً فتقيس المنطقَ وتترك **مسار الطلب** بلا شاهد. وبين المُعالِج والنواة يعيش الربطُ كلُّه — المخبّأ، الجلب، تفكيك العقود — وهو حيث وقع العطلُ فعلاً. | weather-service · testing | [`tests/test_crop_stress_products.py`](../../services/weather-service/tests/test_crop_stress_products.py) · [`main.py`](../../services/weather-service/main.py) · وظيفة `Weather Service Unit Tests` | **open** — **مقيسٌ لا مُقدَّر:** ٢٧ مساراً في `main.py`، و**١٠ منها لم يُسمِّها أيُّ اختبارٍ في الجناح** قبل هذه الشريحة، و**٦ بعدها** (`/healthz` · `/health` · `agro/etc/hourly` · `agro/canonical-state` · `agro/state-report` · `cache-stats`). الأربعةُ التي أُغلِقت هي التي حملت العطل. **لماذا `open`:** لا حارسَ يفرض أن يُسمّى كلُّ مسارٍ مُسجَّل في اختبارٍ واحدٍ على الأقلّ، ولا راتشِتَ يمنع مساراً جديداً بلا شاهد — والستّةُ الباقية تبقى مكشوفةً للصنف نفسه بالضبط. **والعلاجُ المُتناسِب:** راتشِتٌ على «المسارات غير المسمّاة» لا يصعد (٦ سقفاً)، لا حجبٌ فوريّ يُوقِف الخدمة. |
| TYPED-CONTRACT-FORBIDS-ABSENCE-SO-THE-EDGE-INVENTS-ZERO-01 | موصِّل المنصّة يُعلن `temp_max_c: float` **غير اختياريّ**، فتختلق الحافّة `0.0°C` عند الغياب لتفي بالعقد (`_daily_at(..., i, 0)`). نفس كذبة `WEATHER-NORMALIZER-ZERO-COERCION` في مسارٍ منفصل — لكنّها هنا **مفروضةٌ بالنوع** لا سهواً، فالإصلاح يبدأ من `float \| None` لا من الحافّة. | platform · connectors | [`connectors/openmeteo.py`](../../services/sahool-platform/api/connectors/openmeteo.py) (`:168-169` · `:218-219`) · [`core/engines/fao56.py:55-56`](../../services/sahool-platform/core/engines/fao56.py) | **open** — **ونطاقُه ضاق بالقياس لا بالادّعاء.** أُغلِق منه **المطرُ وحدَه** في شريحة `IRRIGATION-READS-MISSING-RAIN-AS-NO-RAIN-01`: `precipitation_mm` صار `float \| None` في `CurrentWeather` و`DailyForecast`، وكفّت المواضعُ الثلاثة عن اختلاق الصفر. وأُخِذ المطرُ أوّلاً لأنّ انحيازَه في اتّجاه **الإذن** ويصل قراراً يُنفَّذ على أرض — مقيسٌ بالتنفيذ: أمرُ ريٍّ حيث القراءةُ تقول «لا حاجة». **والباقي مفتوحٌ ومُعلَنٌ في المصدر نفسِه** (تعليقٌ فوق `CurrentWeather` يسمّي هذه الفجوةَ باسمها): `temperature_c` · `humidity_pct` · `wind_speed_ms` · `cloud_cover_pct` · `weather_code` في الآنيّ، و`temp_max_c` · `temp_min_c` · `wind_max_ms` · `weather_code` في اليوميّ — كلُّها `.get(key, 0)` أو `_daily_at(..., i, 0)`. **ونطاقُ انفجار الحرارتين مقيسٌ سلفاً: ٥ مواضع**، ثلاثةٌ تُمرِّر إلى `fao56.WeatherDay` (`float` أيضاً) — فإغلاقُها يبدأ من عقدِ النواة لا من الحافّة. **والملفُّ يعرف النمطَ الصادق** ويطبّقه على `et0_mm` و`sunshine_hours` و`wind_gusts_ms` — فليس جهلاً بالنمط بل تفاوتاً فيه، وهو نفسُ ما قِيس في `open_meteo.py:441` حين سُجِّلت الفجوةُ الأمّ. |
| WORKFLOW-INJECTION-REGRESSION-HAS-NO-LOCAL-WITNESS-01 | الصنفُ الذي أغلقه #964 لا يحرسه شيءٌ **محلّيّاً**: الحارسُ المضاف فوقيٌّ لا يحلّل الحقن، والكشفُ مُفوَّضٌ كلُّه إلى ثنائيّةٍ تُنزَّل زمنَ التشغيل. | ci · supply-chain · governance | [`github_actions_security_guard.py`](../../scripts/ci/github_actions_security_guard.py) (`evaluate`) · [`github-actions-security.yml`](../../.github/workflows/github-actions-security.yml) (`zizmor --min-severity high --min-confidence high`) · [`test_workflow_run_body_interpolation.py`](../../tests_v9/test_workflow_run_body_interpolation.py) · قياسُ هذه الجلسة على `a0f20490` · #964 | **fixed** — العطلُ الأصليّ مقيسٌ لا مُستنتَج: على `5112a613` كانت **٢٣** قيمةً يملكها طرفٌ خارجَ الشيفرة تُستبدَل نصّاً داخل أجسام `run:`، وعلى `764713df` **صفر** — أي أنّ #964 أغلقه فعلاً، والشكرُ له. **والفجوةُ ليست العطلَ بل شاهدَه:** `github_actions_security_guard.py` **لا يحلّل الـworkflows بحثاً عن الحقن إطلاقاً** — يتحقّق أنّ مسارَ الفحص قائمٌ ومثبَّتُ البصمات وأنّ أوامرَه مذكورةٌ في `ci.yml`؛ حارسٌ **فوقيّ** لا موضوعيّ. فالكشفُ الفعليّ مُفوَّضٌ كلُّه إلى `zizmor --min-severity high --min-confidence high`، ثنائيّةٌ تُنزَّل زمنَ التشغيل **لم يكذّب أحدٌ عتبتَها في هذا المستودع**: فشلُ تنزيلٍ، أو تصنيفُ مُدخَلِ `workflow_dispatch` دون high/high، يُعيد الانحدارَ **صامتاً** — وهو نمطُ «أخضرُ لم يقِس» بعينه. **وثقلُه ليس هيّناً:** ثلاثٌ من الثلاثةَ عشرَ كانت في `runtime-image-provenance.yml`، وهي الوظيفةُ الوحيدةُ التي تحمل `id-token: write` و`attestations: write` و`packages: write` — فمن يملك write يحقن صدَفةً في **الوظيفة الموقِّعة** ويُخرِج برهاناً مزوَّراً، أي هدمُ الفصل الذي وُجِدت GATE-01 لحمايته من داخله. **وحدُّ صدقٍ لازم:** المهاجمُ ليس غريباً — الثلاثةُ `workflow_dispatch` فقط، ولا `pull_request_target` ولا `issue_comment` في المستودع كلّه؛ فالتصنيفُ **تصعيدُ صلاحيّةٍ داخل write** لا اختراقٌ من الخارج. **والعلاجُ شاهدٌ محلّيّ بلا أداةٍ ولا شبكة:** حالةٌ في `tests_v9` مُعلَّمةٌ `unit` تقيس ثلاثَ عائلاتٍ (`inputs.` · `github.event.` · `github.head_ref`) داخل أجسام `run:` وحدها، وتُسمّي الملفَّ والوظيفةَ والخطوةَ والتعبير. **ومُكذَّبةٌ على التاريخ الحقيقيّ لا بطفرةٍ مصطنعة:** إعادةُ workflows ما قبل #964 إلى الشجرة تُحمِّرها بـ**١١** مخالفةً مسمّاة، واستعادتُها تُخضِرها؛ وطفرةٌ مُسجَّلة في القسم السلوكيّ تُعيد الاستبدالَ إلى `runtime-image-provenance.yml` وتُقتَل بالاختبار المُسمَّى. **وتحمل شاهدَين للاتّجاهين**: أنّ القاعدةَ تلتقط الشكلَ الذي شُحِن، وأنّها **تمرّ على العلاج** (`env:` + `"$NAME"`) فلا تعاقب الإصلاح. **وحدود التغطية مُعلَنة:** لا تُقاس `steps.*.outputs.*` — تحتاج تحليلَ تدفّقٍ لا مطابقةَ نصّ، وقاعدةٌ تُعمَّم بلا ذلك تُنتِج ضجيجاً يُسقِط نفسَه — ولا دلالاتُ المنصّة؛ فهذه **مكمِّلةٌ** لـzizmor وactionlint لا بديلٌ عنهما. |

| CACHE-AGE-FABRICATED-AS-ZERO-AND-COMPARED-ACROSS-PROCESSES-01 | مسارُ Redis لم يكن يحسب عمراً **إطلاقاً**: `set` تكتب `"age_hint_s": 0` حرفيّاً و`get` تقرؤها عمراً ⇒ كلّ إصابةٍ طازجة تُبلِّغ `cache_age_s: 0` مهما بلغ عمرُها. وفرعُ البائت يطرح `monotonic()` بين **عمليّتين** — ونقطةُ مرجعيّتها غير معرَّفة بنصّ PEP 418 — ثمّ `max(age, TTL_S)` يرفع الناتجَ إلى حدٍّ معقول المظهر فيستر فسادَه. | weather-service · cache | [`cache.py`](../../services/weather-service/cache.py) (`:53` · `:57` · `:79`) · [`weather_runtime.py`](../../services/weather-service/weather_runtime.py) (`:157` · `:334` · `:918` · `:973`) | **fixed** — العمرُ صار `المدّة الكاملة − TTL(key)`، والعدُّ كلُّه داخل Redis فتسقط مسألةُ الساعات من أصلها. و**المجهولُ يُقال `None` لا `0`**: عدّادٌ عاطل أو حارسا `-1`/`-2` ⇒ لا عمر. وأُسقِط `max(age, TTL_S)` لأنّ العدَّ الصحيح لا يحتاج ستراً. **مُكذَّبٌ ٧/٧.** **وحدُّ صدق:** الشاهدُ Redis وهميٌّ يعرف `TTL`، لا خادمٌ حيّ — و`test_weather_cache_live_redis_roundtrip` يبقى مشروطاً بـ`WEATHER_REDIS_INTEGRATION_URL` فيُتخطّى في CI. **ولم يُقَس الأثرُ الزمنيّ:** نداءُ `TTL` إضافيٌّ لكلّ إصابة، ولم يُقَس تأخيرُه. |

| CONFIDENCE-FABRICATED-FROM-AN-INVENTED-DENOMINATOR-01 | ثقةُ إشارتَي الصقيع والحرارة نسبةٌ خام `hours / max(1, hours_evaluated)`. و**المقامُ نفسُه مُخترَع** في مسار الإنتاج: `build_signal_records` يشتقّه `max(1, heat, frost)` — أي يُساويه بالبسط — فتخرج النسبة 1.0 حتماً. وصفرُ ساعاتٍ مُقيَّمة يُطلِق `trafficability_poor` بثقة **1.0** من لا شيء. | platform · signals | [`core/weather_signals.py:38`](../../services/sahool-platform/core/weather_signals.py) · [`core/weather_overlay_pipeline.py:84`](../../services/sahool-platform/core/weather_overlay_pipeline.py) · مستهلِك: [`core/decision_playbook.py:117`](../../services/sahool-platform/core/decision_playbook.py) | **fixed** — أربعةُ أجزاء: لا إشارةَ بلا ساعاتٍ حاضرة · **مقامٌ مخصوصٌ لكلّ حدث** (`frost_evaluable_hours`/`heat_evaluable_hours` = الساعاتُ التي كان الحدثُ قابلاً للرصد فيها) · حدُّ Wilson الأدنى (z=1.645) فوق كسرٍ طرفاه من **فضاءِ ملاحظةٍ واحد** · والمقامات تُحمَل مقيسةً في سجلّ التراكب ولا تُشتقّ (بلا هجرة: الإدراج يقرأ بالاسم). **والقياسُ يقول حجمَ الخطأ:** ٦ ساعات صقيع من **٢٤** كانت تُبلِّغ `1.0` وتُبلِّغ الآن `0.135` — تضخيمٌ ٧٫٤ أضعاف **في المسار الطبيعيّ**. **ومدخلٌ متناقض** (`successes > trials`) يُرَدّ `None` ولا يُقَصّ إلى 1.0. **مُكذَّبٌ ١٨/١٨.** **وحدُّ صدق:** لم تُمَسّ ثقةُ `spray`/`disease`/`trafficability` — تستعمل الدرجةَ نفسَها ثقةً (خلطُ المقدار بالثقة)، وعدّاداتُها غيرُ قابلة للاسترداد من كسرٍ مُقرَّب. |

| GUARD-ALTER-ADD-SYNTAX-BLINDSPOT-01 | حارسُ فصل الأهليّة كان يرى صياغةً واحدة من صياغات `ALTER TABLE`، فتمرّ `ADD COLUMN IF NOT EXISTS` والمعرّفاتُ المُقتبَسة والبادئاتُ المشروعة الأخرى بلا رصد. | governance · migrations | [`snapshot_eligibility_separation_guard.py`](../../scripts/ci/snapshot_eligibility_separation_guard.py) · [`guard_mutation_registry.json`](../../docs/architecture/guard_mutation_registry.json) · وثيقةُ تحكيم Sigstore (2026-08-12) | **fixed** — **مُتحقَّقٌ منه على الشجرة لا من الوثيقة:** السجلُّ يحمل **٩ طفرات** لهذا الحارس، تُغطّي `ADD COLUMN IF NOT EXISTS` · كلَّ بادئة `ALTER` مشروعة · المعرّفَ المُقتبَس · العمودَ المُقتبَس داخل `CREATE TABLE` · وفقدانَ الموضوع. **والوثيقةُ قالت ٨؛ والمقيسُ ٩** — طفرةٌ أُضيفت بعد 2026-08-12. سُجِّل هنا لأنّ السجلَّ لم يكن يحمل المعرِّف **أصلاً**: لا فتحاً ولا إغلاقاً. |
| LIVE-PG-PSQL-ABSENCE-COLLECTION-ERROR-01 | غيابُ عميل `psql` كان يُسقِط **جمعَ** الاختبارات بخطأ استيراد بدل تخطٍّ مُعلَن — فيبدو انهيارُ المُشغِّل إخفاقَ اختبار. | ci · live-evidence | [`test_live_pg_fake_connection_debt.py:53,89`](../../tests_v9/test_live_pg_fake_connection_debt.py) · [`test_eligibility_assessment_live_pg.py:280`](../../services/decision-service/tests/test_eligibility_assessment_live_pg.py) | **fixed** — **مُتحقَّقٌ منه على الشجرة:** `shutil.which("psql")` يسبق أيّ استدعاء (سطرا 53 و89)، واختبارُ الانحدار المُسمّى `test_the_module_imports_even_without_a_psql_client` قائمٌ فعلاً. سُجِّل هنا لنفس السبب: المعرِّف لم يكن في السجلّ. |
| LESSON-CONCURRENT-PREFLIGHT-CONTAMINATION-01 | تشغيلتا `preflight` متزامنتان تُفسِدان قياسَ بعضهما: إحداهما داخل نافذة مِسبارٍ يكتب ملفّاً حقيقيّاً في `routers/`، والأخرى تعدّ بمسح القرص فترى ٥٧٤ بدل ٥٧٣. | ci · methodology | [`test_api_versioning_policy_guard.py:44-62`](../../tests_v9/test_api_versioning_policy_guard.py) · [`route_mount_contract_guard.py:107-121`](../../scripts/ci/route_mount_contract_guard.py) | **open** — **مقيسٌ بحادثةٍ كاملة:** أربعةُ إخفاقات نُسِبت إلى الشريحة وكانت كلُّها من تشغيلتَين متزامنتَين شغّلتُهما أنا. الشاهدُ ثلاثيّ: main منفرداً ٥٨١١/٠ · الفرع منفرداً ٥٨١١/٠ · `preflight` منفردة صفرُ إخفاقات — بينما المتزامنة أسقطت `route_mount`. **والآليّةُ مسمّاة:** المِسبارُ ملفٌّ `.py` حقيقيّ في `routers/`، وكلُّ حارسٍ يعدّ بمسح القرص يراه. **لماذا `open`:** لا قفلَ يمنع تشغيلتَين، ولا رسالةَ تُفرّق تلوّثَ التزامن عن عطلٍ حقيقيّ. |
| LESSON-READ-SUMMARY-NOT-TAIL-01 | قراءةُ `tail` من سجلّ بوّابات بدل سطر الخلاصة تُخفي إخفاقاتٍ مُبلَّغة صراحةً. | ci · methodology | `scripts/ci/preflight.sh` (سطر `═══ إخفاقات: N`) | **open** — **مقيس:** أبلغتُ المالكَ «إخفاقٌ واحد» بينما سطرُ الخلاصة يقول `إخفاقات: 2`، لأنّي قرأتُ `tail` وفلترتُ باسم الاختبار الذي أعرفه. والثاني (`checksum mismatch`) صنفٌ مختلف تماماً كان سيُكلّف جولةَ CI. **العلاج انضباطٌ لا أداة:** يُقرأ سطرُ الخلاصة أوّلاً، ثمّ يُبحَث عن كلّ `✗` بعدده. |
| LESSON-MERGED-GENERATED-ARTIFACTS-01 | المصنوعُ المولَّد لا يُدمَج يدويّاً عند التعارض: دمجُ بصمتَي `sha256` يُنتِج بصمةً ثالثة لا تصف أيّ شجرة. | governance · generated | [`verify_all_generated.py`](../../scripts/ci/verify_all_generated.py) · `release/FILE_CHECKSUMS.sha256` | **open** — **مقيسٌ على إعادة تأسيس H1 فوق P1:** ملفّاتُ الدماغ الأربعة اندمجت تلقائيّاً (الإلحاقيّةُ كفت)، و**١٤ مصنوعاً مولَّداً تعارضت**. حُسِمت بأخذ جانبٍ واحد ثمّ **إعادة التوليد آخِراً** على شجرةٍ ساكنة — فالمولِّد هو الحَكَم لا المُحرِّر. **لماذا `open`:** لا `.gitattributes` ولا آليّةَ تمنع دمجاً يدويّاً لمصنوعٍ مولَّد، والانضباطُ وحده يحرسه. |
| CONTRACT-WHOSE-TWO-ENDS-ARE-TESTED-APART-01 | عقدٌ طرفاه في خدمتين، كلٌّ منهما مختبَرٌ وحدَه فيمرّان خضراوين — **والقفزةُ بينهما لا يفحصها أحد**. | contracts · testing · governance | [`test_weather_client_paths_exist_on_the_service.py`](../../tests_v9/test_weather_client_paths_exist_on_the_service.py) · [`test_horizon_survives_the_hop_to_the_service.py`](../../tests_v9/test_horizon_survives_the_hop_to_the_service.py) · [`test_weather_views_survive_the_hop_to_the_platform.py`](../../tests_v9/test_weather_views_survive_the_hop_to_the_platform.py) | **fixed** — **الصنفُ يُسجَّل لأنّه أصابنا ثلاثَ مرّاتٍ في أسبوع، لا لأنّه مُتوقَّع.** ① `WEATHER-CLIENT-ASKS-A-PATH-THE-SERVICE-NEVER-DECLARED-01`: العميلُ يطلب `/v1/weather/tile-cache/stats` والخدمةُ تُعلن `cache-stats` — ٤٠٤ حتميّ؛ اختبارُ العميل يزيّف الاستجابة واختبارُ الخدمة ينادي مسارَها الصحيح. ② `AN-ACCEPTED-HORIZON-IS-QUANTISED-TO-TWO-BUCKETS-01`: أصلحت #948 طرفَ المنصّة وأبقت قائمةَ سماحٍ مغلقة في الخدمة، فبقي `168` و`48` يُنتِجان النتيجةَ نفسَها **حرفيّاً** بعد الإصلاح كما قبله. ③ P6 هنا: الموصّلُ يُعيد كائناتٍ والعميلُ قاموساً بغلافٍ ثالث. **والعَرَضُ المشترك أنّ كلا الطرفين سليمٌ بمعزل** — فالخُضرةُ صادقةٌ وناقصةٌ معاً، ولا رمزَ خروجٍ يقول ذلك. **وثلاثةُ شهودِ قفزةٍ كُتِبوا** (المصادر أعلاه) يُشغّلون المُنتِجَ الحقيقيَّ في المُستهلِك الحقيقيّ بلا تزييفِ طرف. **وتبقى `open` بصدق:** الحوادثُ الثلاثُ مُغلَقة، و**الصنفُ لا** — لا شيءَ في الشجرة يُلزِم عقداً جديداً عابراً للخدمات بشاهدِ قفزة. والعلاجُ يلزمه أوّلاً **جردُ العقود العابرة** (سطحُ `weather_service_client` وحدَه ١٨ مساراً)، وحارسٌ بلا جردٍ يُعلِن تغطيةً لا يملكها — وهو الصنفُ الذي سجّلناه في `MUT-REGISTRY-STRANDED-SPECS-01`.  **✅ أُغلِقت (2026-08-27، فوق `7c118b54`):** نُفِّذ العلاجُ الموصوفُ أعلاه بترتيبه — **الجردُ أوّلاً ثمّ الحارس** — و`scripts/ci/cross_service_path_contract_guard.py` حاجبٌ في `ci.yml` و`preflight.sh` (٢ز). **والنطاقُ مُشتقٌّ من الشجرة لا مكتوب:** العميلُ يُعرَّف بحمله عنوانَ خدمةٍ داخليّة (`http://sahool-<اسم>-service`) ومنه تُشتقّ الخدمةُ الهدف. **والاشتقاقُ نقض تقديري:** حسبتُ العملاءَ أربعةً (`*_client.py`) فوجد **ثمانية** — فقائمةٌ مكتوبةٌ كانت ستحرس النصفَ وتُعلِن الكلّ. **والمقيسُ اليوم صفرُ انحراف** في العقود الثمانية، فقيمتُه منعُ القادم لا إصلاحُ قائم — **وخضرتُه ليست إنجازاً**. **وثلاثةُ ثقوبٍ في مستخرِجه كُشِفت بمقابلة قارئَين لا بقراءةٍ واحدة:** `soil_hydraulic_client` أعطى **صفراً** بالنمطيّ (`httpx` بسلسلةٍ مُنسَّقة) · `irrigation_activation_gate` أعطى صفراً بـ`ast` (المسارُ في ثابتِ وحدةٍ يُبنى داخل دالّة) · و`raster_get_json_sync` أعطى **١٦ مقابل ١٤** (`endswith` أفلت لاحقةَ `_sync` فضاع مسارانِ). **قارئٌ واحدٌ لا يُكذِّب نفسَه**، والمقابلةُ مُثبَّتةٌ في الاختبار شاهداً سادساً. **وطفرةٌ نجت فكشفت اختباري لا الحارس:** شاهدُ العمى كان «القائمةُ فارغةٌ على شجرةٍ سليمة» وهي تبقى فارغةً لو عُطِّل الكشف — أُخرِج التصنيفُ دالّةً نقيّةً وصار له شاهدٌ **موجب**. مُكذَّبٌ بخمس طفرات، الخمسُ زُرِعت وقُتِلت. **وحدُّ صدق:** فحصٌ ساكن يقيس أنّ المسارَ **مُعلَنٌ** لا أنّ الخدمة تستجيب، ومُمرِّرٌ ديناميّ واحد خارج النطاق بسببٍ مكتوب وقائمتُه مغلقةٌ بالمساواة. |
| IRRIGATION-READS-MISSING-RAIN-AS-NO-RAIN-01 | `rain_recent_mm` المفقودُ يُقسَر إلى صفر، و«لا مطر» **يرفع** كمّيّةَ الريّ الموصى بها — فالغيابُ ينحاز إلى الإسراف لا إلى الحفظ. | weather · platform · agronomy | [`field_workspace_weather.py`](../../services/sahool-platform/api/routers/field_workspace_weather.py) (مسارُ `irrigation-advice`) · [`weather_advice.py`](../../services/sahool-platform/api/weather_advice.py) (`irrigation_advice:70`) | **fixed** — **وصفُّه كان صادقاً وناقصاً معاً:** الملفُّ الذي يسمّيه (`field_workspace_weather.py`) كان **قد أُصلِح** بالفعل — يفشل مغلقاً بـ`WEATHER_PRECIPITATION_INCOMPLETE`؛ بينما الصنفُ نفسُه حيٌّ في **ثلاثة أسطحٍ لا يذكرها الصفّ**: `fields.py` (توصيةُ الريّ ومخاطرُ الأمراض) · `main.py` (سياقُ التنبيهات) · `recommendations_hub.py` (العقدُ نفسُه `rain_recent_mm: float = 0.0`). أي **علاجٌ ضيّقٌ تحت اسمٍ عريض** — فالمزارعُ يُسقى أو لا يُسقى بحسب أيّ مسارٍ سأل. **والأثرُ مقيسٌ بالتنفيذ لا موصوف:** مطرٌ غائبٌ مُصفَّر ⇒ `recommended_mm=7.5` · `urgency=moderate` · «خلال ٢٤ ساعة» — أمرُ ريٍّ صريح؛ وبالقراءة الحقيقيّة (١٢مم) ⇒ `0.0` و«لا حاجة للريّ». فالانحيازُ في اتّجاه **الإذن** في منطقةٍ شحيحة الماء، و`rationale_ar` **لا يذكر المطرَ بحرفٍ** عند الصفر فيُقرأ حساباً لا جهلاً. **والعلاج تعريفٌ واحد لا ثلاثة:** `weather_advice.complete_rain_total` على `list[float \| None]` مُجرَّدةٍ من الشكل، ويُفوِّض إليها الموجِّهُ القديم بدل أن يحتفظ بحكمٍ ثانٍ؛ والحافّةُ كفّت عن اختلاق الصفر (`_build_daily` · `fetch_current` · `fetch_current_batch`)؛ وقرارُ الريّ/المرض يفشل مغلقاً في المسارات الطالبة ويصمت في مسار التنبيهات (حيث `FieldAlertContext` يُعلن الحقولَ `float \| None` سلفاً و`_heavy_rain` يفحص `is None` — فالعقدُ كان مبنيّاً لحمل الغياب والتصفيرُ هو ما يُتلفه). **والإعلانُ ضُمَّ إلى الإنفاذ في الشريحة نفسِها:** `required_inputs` صارت تسمّي حقولَ المطر، وإلّا كان العلاجُ يُنشئ عطلاً من صنفه — قاعدةٌ حقيقيّةٌ تحت وصفٍ يُطمئن. **و٧/٧ طفرات مُكذَّبة**، ومنها **اثنتان نجتا أوّلاً بخطأٍ في شهادتي لا في الشيفرة**: قِستُ `_daily_at` مُمرِّراً الافتراضَ بيدي بدل موضع البناء، وقِستُ العقدَ بتمرير `None` صراحةً وبايثون لا يفرض التصنيف وقتَ التشغيل — فأُعيد الإرساءُ على `_build_daily` وعلى **إغفال** الحقول. والصفرُ المرصود يبقى رصداً، محروساً في الاتّجاهين. ١١٢ فشلاً = الأساس بالحرف · ٣٥٢٦ ⇒ ٣٥٣٦ ناجحة. |
| OWNERSHIP-CONTRACT-DECLARED-BUT-NEVER-MEASURED-01 | `db_ownership.yml` يعلن مالكاً وكُتّاباً وقُرّاءً لـ**٣٨٣ جدولاً**، ولا شيء في الشجرة كان يقارن المُعلَنَ بالواقع — فبقي العقدُ وثيقةَ نيّة وانحرف الكودُ عنه صامتاً. | architecture · ci · governance | [`db_ownership.yml`](../../docs/architecture/db_ownership.yml) · [`db_writer_ownership_guard.py`](../../scripts/ci/db_writer_ownership_guard.py) · [`db_writer_ownership_baseline.json`](../../docs/architecture/db_writer_ownership_baseline.json) | **open** — **المقيس ٧٥ كتابةً لم يأذن بها العقد** موزّعةً على عشر خدمات (sahool-platform=54 · auth=5 · raster=4 · scripts=4 · odoo-bridge=2 · weather-polygon-worker=2 · agents · actuator-service · weather-signal-engine · mcp_servers). **ومنها عطلا M-03 اللذان كشفهما فحصٌ جنائيٌّ يدويّ** لأنّ الفحصَ الآليّ لم يكن موجوداً: `actuator_command_outbox` (كاتبٌ وحيد، صفر قارئ) و`iot_command_dispatch` (حيٌّ، يكتبه ويقرؤه ويطالِبه غيرُ مالكه المُعلَن) — والثاني **لم يُبلَّغ في أيّ تقريرٍ سابق**. أُنشئ الحارسُ بكشفٍ من شجرة البناء لا من النصّ، يحترم `writers` و`mirror`+`interim-bridge` كإذنٍ صريح، وراتشِتٍ يفشل في الاتّجاهين، ويفشل صراحةً على عقدٍ غيرِ مقروء. **وحدُّ صدق:** الحارسُ يُثبِّت العددَ ولا يحكم على أيٍّ منها: بعضُها قد يكون **العقدُ** هو المخطئ فيه لا الكود. والقرارُ في كلٍّ حوكمةٌ لا اشتقاق — بطاقةُ M-03 نموذجُه. |
| WORKER-CLAIM-NOT-PINNED-BY-A-TRANSACTION-01 | `FOR UPDATE SKIP LOCKED` في اتّصالٍ بوضع autocommit **لا يُثبِّت مطالبة**: القفلُ يُحرَّر فور انتهاء `SELECT`، فيلتقط عاملٌ ثانٍ الصفوفَ نفسَها. | platform · concurrency · safety | [`phase_runtime_workers.py`](../../services/sahool-platform/api/phase_runtime_workers.py) · [`v228_worker_claim_lease.sql`](../../migrations/v228_worker_claim_lease.sql) · [`test_worker_claim_lease_live.py`](../../tests_v9/test_worker_claim_lease_live.py) | **open** — **مُثبَتٌ حيّاً لا ساكناً:** عاملان متزامنان على PostgreSQL 16 حقيقيّ، أربعون صفّاً ⇒ **عشرون صفّاً مُطالَبٌ مرّتين** بالنمط القديم و**صفر** بالجديد. وكان الملفُّ يحمل ستّةَ مواضع `SKIP LOCKED` و**صفرَ** `conn.transaction()`. **وأخطرُها `run_actuator_once`:** يطالِب ثمّ ينشر `sahool.actuator.dispatch.requested` — فالعشرون تعني عشرين طلبَ إرسالٍ فيزيائيٍّ مكرَّر: حركةُ صمّامٍ أو مضخّةٍ تُطلَب مرّتين. والعلاجُ ليس إطالةَ المعاملة حتّى تشمل النشر (ذلك يُعيد نمطَ `event_bus.py` الذي يحبس الأقفالَ أثناء I/O) بل فصلٌ ثلاثيّ: TX-1 مطالبةٌ تُثبَّت بـcommit · الشبكةُ خارجها · TX-2 إنهاءٌ بـCAS على `claim_token`. **ولمَ رمزٌ ولا تكفي الحالة:** عند انتهاء الإجارة يُعيد عاملٌ ثانٍ المطالبة، فلو كان الشرطُ الحالةَ وحدَها لأنهى الأوّلُ مطالبةَ الثاني. **ولمَ `open`:** النمطُ مُطبَّقٌ على المواضع الستّة ومُكذَّبٌ بأربع طفراتٍ مزروعة، لكنّ `event_bus.py` (النمط الأوّل: معاملةٌ مفتوحةٌ أثناء I/O شبكيّ) **لم يُمَسّ بعد** — والصنفُ لا يُغلَق بنصفه. |
| AN-ISOLATION-TEST-ON-AN-EMPTY-TABLE-PROVES-NOTHING-01 | اختبارُ عزلٍ يؤكّد «صفرُ صفوفٍ من المستأجر الآخر» على جدولٍ **فارغ** يمرّ أخضرَ وRLS مُعطَّلةٌ كلّيّاً — فيقيس فراغَ الجدول لا عملَ السياسة، ويُقرَأ شهادةَ عزل. | security · testing | [`test_rls_tenant_isolation_live_pg.py`](../../tests_v9/test_rls_tenant_isolation_live_pg.py) · [`ci.yml`](../../.github/workflows/ci.yml) (`RLS tenant isolation certification`) | **fixed** — المقيس على PG16 بدورٍ مقيَّد (`rolsuper=f · rolbypassrls=f`): جدولٌ فارغ وRLS **مُفعَّلة** ⇒ ٠ صفّ ⇒ أخضر؛ جدولٌ فارغ وRLS **مُعطَّلة** ⇒ ٠ صفّ ⇒ **أخضر أيضاً**. أُضيف اختبارٌ بثلاثة شهود: سالبٌ (لا يرى صفَّي B) · موجبٌ (يرى صفَّه هو، وإلّا فالصفرُ عمًى لا عزل) · وإبطالُ فراغٍ (بتعطيل RLS يعودان صفّين). ويسبقها شاهدٌ رابع يتحقّق أنّ الدورَ **مقيَّدٌ فعلاً** — فالخارقُ يتجاوز RLS بحكم المحرّك فيقيس الملفُّ شيئاً آخر. أربعُ طفراتٍ زُرِعت وقُتِلت، منها `set_config(...,true)` خارج معاملة الذي يُعيد `GUC-SCOPE-GUARD-SEES-ONE-FILE-01`. **وحدُّ صدق:** الملفُّ يُنشئ جدولَه وسياستَه، فالمُثبَتُ أنّ المحرّكَ يعزل وأنّ المقياسَ غيرُ فارغ — **لا** أنّ سياسات RLS المُعلَنة في هجرات المنصّة صحيحة؛ تلك شهادةٌ أخرى لم تُدَّعَ. |
| AN-EXEMPTION-LIST-WITH-NO-DESCENDING-CEILING-01 | قائمةُ إعفاءٍ تمنع مخالفاً **جديداً** ولا تقيس شيئاً عن القائمين — فكلُّ مُعفًى موسومٌ «pending» يبقى إلى الأبد بلا سطرٍ واحدٍ يحمرّ. | governance · ci | [`weather_direct_wiring_allowlist.json`](../../docs/architecture/weather_direct_wiring_allowlist.json) (`composite_residuals_ceiling`) · [`test_p3_5_weather_direct_wiring_final_sweep.py`](../../services/sahool-platform/tests/test_p3_5_weather_direct_wiring_final_sweep.py) | **fixed** — المقيس: عشرةُ مداخلَ في `composite_residuals_pending_p4`، **كلُّها** موسومةٌ «pending P4» منذ الكنس الأوّل، ولا شيءَ في الشجرة يفشل إن بقيت عشراً بعد سنة. **وإعفاءٌ بلا سقفٍ نازل ليس ديناً مؤجَّلاً بل شطبٌ صامت** — يقرؤه المراجعُ خطّةً ويعمل عملَ الإلغاء. أُضيف `composite_residuals_ceiling` مفروضاً بـ`test_the_documented_residuals_only_ever_shrink`: يفشل إن **تجاوزت** المتبقّياتُ السقف، **وإن نقصت عنه** بلا خفضِه — فإغلاقُ متبقٍّ يُلزِم خفضَ السقف وإلّا عاد صامتاً. خُفِض ١٠ ⇒ ٩ بإغلاق P6، ومُكذَّبٌ بالطرفين (رفعُه إلى ١٠ بلا مُعفًى عاشرٍ يُحمِّره؛ مقيس). **وحدُّ صدق:** أُصلِحت **هذه** القائمةُ وحدَها. لم أجرد سائرَ قوائم الإعفاء في الشجرة، فلا أدّعي أنّ الصنفَ مُغلَق فيها — والادّعاءُ بلا جردٍ هو نفسُه العيبُ الموصوفُ هنا. |
| A-GUARD-NAMED-FOR-A-PROPERTY-THAT-PINS-AN-IMPLEMENTATION-01 | حارسٌ اسمُه يَعِد بخاصّيّة ويؤكّد **تنفيذاً** — فيحجب الإصلاحَ بدل الانحدار، ويتناقض مع حارسٍ آخرَ على السطر نفسِه. | testing · governance | [`test_ui27_backend_facades_guard.py`](../../services/sahool-platform/tests/test_ui27_backend_facades_guard.py) (`test_ui27_weather_facade_preserves_disease_and_irrigation_field_endpoints`) · [`test_p3_5_weather_direct_wiring_final_sweep.py`](../../services/sahool-platform/tests/test_p3_5_weather_direct_wiring_final_sweep.py) | **fixed** — **مقيسٌ بجولة CI حمراء على إصلاحٍ صحيح.** الاختبارُ اسمُه `preserves … endpoints`، وأوّلُ أربعةِ تأكيداتٍ فيه تقيس ذلك بالضبط (مُزخرِفا المسارين + `irrigation_advice` + `disease_risk`). ثمّ ثلاثةٌ تُثبِّت **أيَّ مزوّدٍ يناديانه** نصّاً (`fetch_daily_forecast` · `fetch_current` · `Open-Meteo`) — أُضيفت مع نقل UI-27 لتمنع ضياعَ المسارين، فثبّتت بلا قصدٍ تفصيلَ تنفيذ. **والنتيجةُ أنّ الشجرة حملت حارسَين يقولان عن السطر نفسِه قولين متناقضين:** هذا يُوجِب استيرادَ الموصّل، و`test_p3_5_…` يمنعه إلّا بإعفاءٍ مُعلَن. ولا يظهر التناقضُ ما دام أحدُهما مُعفًى — **فيبيت حتّى يُحاوِل أحدٌ الإصلاح**، وحينها يقرأ الفاعلُ الحمرةَ «تغييرُك خطأ» وهي تقول «تعريفانِ متزاحمان». **والعلاجُ ليس حذفَ التأكيدات:** استُبدِلت بالخاصّيّة المُسمّاة (قراءةُ طقسٍ خادميّة عبر `get_current_weather`/`get_weather_forecast`) **مع منعِ عودة الموصّل صراحةً** — فصار الفحصُ **أقوى** ممّا كان لا أضعف، وموضعُ سؤال «أيُّ مزوّد» حارسٌ واحدٌ بقائمةِ إعفاءٍ ذاتِ سقفٍ نازل. **ومُكذَّبٌ من ثلاث جهات** (مقيس): ضياعُ مسار ⇒ حمراء · عودةُ الموصّل ⇒ حمراء · فقدانُ قراءة الطقس ⇒ حمراء · والشجرةُ السليمة ⇒ خضراء. **وحدُّ صدقٍ يخصّني:** لم أُشغّل `services/sahool-platform/tests/` محليّاً قبل الدفع — شغّلتُ الاختباراتِ التي أعرفها لا التي قد تنكسر، والدليلُ على المتضرّرين يُشتقّ من المسار المُعدَّل لا من ذاكرتي. |
| A-STALENESS-ANCHOR-WITH-NO-DRIFT-BOUND-01 | مرساةُ قياسٍ (زمنٌ مقرونٌ بعددٍ) تُبيت **صامتةً**: لا يُحمِّرها إلّا سقفٌ بعيد، فتبقى تصف كوناً لم يعد قائماً وتُقرَأ عقداً حيّاً. | testing · governance | [`test_mutation_sweep_headroom.py`](../../tests_v9/test_mutation_sweep_headroom.py) (`MEASURED_SLOWEST_MINUTES` · `RE_MEASURE_DRIFT_CEILING`) · جولات CI ٣٣٢٥٩٦٥١٢٠٩→٣٣٢٦٩٠٤٦٤٣٧ | **fixed** — **مقيسٌ لا مُتوقَّع، ولم يحمرّ شيءٌ ليكشفه:** المرساةُ عند (٣٤٫٧ دقيقة، ٤٨١ طفرة) والسجلُّ بلغ ٥٠٩، والأبطأُ الحقيقيُّ ٣٧٫٢٣ (job 99138482939) — أي أنّ ثابتاً اسمُه «أبطأ قياس» لم يعد الأبطأ **منذ ثمانٍ وعشرين طفرة**، ولم يكشفه إلّا قارئٌ مصادفةً. **والعلامةُ وحدَها لا تكفي حارساً للبيات**: تنطق عند ٥٥٢ فقط، وعلاجُها الذي يُمليه العقدُ (أعِد القياس، أعِد الاشتقاق) **يُحرِّكها هي نفسَها** — فهي مِشعَلُ إعادةِ قياسٍ لا سقفٌ على النموّ؛ اليومَ صارت الجولةُ أبطأ وارتفعت ٥٥٢ ⇒ ٥٧٤ لأنّ النقطةَ المقيسة تحرّكت ٤٨١ ⇒ ٥٠٦. أُضيف حدُّ انجرافٍ **مشتقٌّ** (نصفُ الهامش ⇒ ٥٤٠) يُحمِّر قبل العلامة بعلاجٍ أرخص. **وشاهدٌ موجب لأنّ السقفين تأكيدانِ على الغياب:** إعادةُ تسمية قسمٍ في السجلّ أهبطت المقياسَ ٥٠٩ ⇒ ٣٣٨ **ومرّ السقفانِ أخضرين** — كُذِّب يدويّاً واحمرّ الشاهدُ وحدَه. **وحدُّ صدقٍ لازم: يُقاس بياتُ الاقتران لا بياتُ الزمن** — جولةٌ تبطؤ بلا نموِّ سجلٍّ (عدّاءٌ مختلف، ملفّاتُ اختبارٍ خارج المكنسة) تمرّ من هنا خضراء، والقياسُ الزمنيُّ يبقى فعلاً بشريّاً دوريّاً لا يفرضه ملفٌّ في الشجرة. **وستُّ جولاتٍ في يومٍ واحد أعطت حدّاً جديداً:** التشتُّتُ عند العدد الثابت نفسِه ٦٫٠٤ دقيقة — من رتبة الفرق بين الأعداد، **فلا كلفةَ حدّيّةً تُشتقّ منها**، والكلفةُ المتحفّظة (٠٫٧٧٥د) تبقى. |

## ملاحظات

- **إغلاق فعليّ 2026-06-28 (سياسات قابلة للضبط):** الفجوات `H5`/`C5`/`H2` نُقِلت من
  `deferred` إلى **`fixed`** بسياسات قرار قابلة للضبط والاختبار (لا «كود فقط»): H5 (#566) سياسة
  ريّ مشروطة بالملوحة · C5 (#567) سياسة دليل NDVI (داعم لا حاجب دون معايرة) · H2 (#568) عقد
  ناشري الأحداث + حارس CI عكسيّ. صدق: H5/C5 يبقيان بحاجة **معايرة ميدانيّة** (EC/عتبات NDVI) ⇒
  `fixed` لا `verified`؛ H2 بلا اختلاق ناشر ولا تقليم اشتراك.
- **إغلاق تتبُّعيّ 2026-06-28:** الفجوات `C4-M1`/`SAM2`/`TERRAIN` نُقِلت من `open` إلى
  **`deferred`/`by-design`** — لا واحدةَ منها قابلةٌ للإصلاح الآليّ الآمن: كلٌّ يحتاج بيئةً
  (GPU/Flutter) أو تحقّقاً ميدانيّاً أو قراراً زراعيّاً. (صدق: إغلاقُ تتبُّعٍ موثَّقٌ بالسبب، لا
  ادّعاءُ حلٍّ.) `SAM2` فعليّاً **بالتصميم** (opt-in خلف `profile=gpu` + 503 صادق) لا عيباً.
  `CI-MIRROR` صار `fixed` بإعادة #556.
- **مصادر [حيّ] تنتظر التشغيل:** R6 (البوّابيّ)، H1 (التفويض فاشل-مفتوح، قرار)، OFFLINE
  (مزامنة Flutter كاملة) — انظر ملحق التحقّق المعماريّ في
  [`../../SAHOOL_PRODUCTION_GAP_REPORT_v1.md`](../../SAHOOL_PRODUCTION_GAP_REPORT_v1.md):44-74.
- **الأداة القابلة للتشغيل:** [`../../tools/sahool_inspector.py`](../../tools/sahool_inspector.py)
  (RLS coverage / router wiring / NATS subjects / endpoint authz / migration manifest).

## WX-12-RUNTIME-SCHEDULERS — ✅ CLOSED @ `9e308d5` (2026-07-12) — كان OPEN (High) من التدقيق الجنائيّ
- **المصدر:** `services/model-registry-adapter/service.py` يعالج `monitoring_window` و`active_state_reconcile` لكنّ `persistence.list_runtime_work` لا يُنتج هذين النوعين ⇒ المراقبة والمصالحة الدوريّة كود خامل بلا مُطلِق.
- **لماذا مؤجَّل (لا نصف حلّ):** يلزم قرار بنية مجدول دائم (cron/NATS/جدول schedule دائم) + حالة جدولة + اختبارات إنشاء عمل دوريّ. نصف الحلّ (إنتاج نوع بلا جدولة حقيقيّة) يخالف "لا نصف حلّ".
- **التصميم المُوصى:** جدول `decision_model_monitoring_schedules` (نافذة + دوريّة + آخر تشغيل) يُنتج منه list_runtime_work عناصر `monitoring_window` مستحقّة؛ ومثله جدول reconcile دوريّ لكلّ (model, environment) نشط. كلاهما خلف راية تفعيل حتّى التحقّق التكامليّ.

- **الإغلاق (`9e308d5`):** نُفِّذ التصميم المُوصى حرفيّاً — migration 017: جدول `decision_model_runtime_schedules` (config دائم: period + anchor مقطوع-الثواني + enabled؛ إنشاء الصفّ هو راية التفعيل — لا صفوف = صفر انبعاث = صفر تغيير سلوك) + جدول `decision_model_reconcile_evidence` append-only (الانجراف/تغيير alias اليدويّ/split-brain صار أدلّة قابلة للتدقيق لا log — يغلق الشقّ القابل للتدقيق من High 4). التقدّم مُشتقّ من الأدلّة (snapshots/evidence) لا من حالة last-run متغيّرة. الـfeed يبثّ النافذة المكتملة الأخيرة بلا snapshot (ISO يدور بدقّة) وreconcile المستحقّ (period_index حتميّ)؛ الـclaims تغطّي النوعَين (صفّ واحد لكلّ جدولة). endpoints: runtime-schedules + reconcile-evidence (actor + idempotency + replay). الحارس `wx12_runtime_scheduler_gate` يمنع الانحدار لكود خامل. اختبارات pg حقيقيّة + contract.

## WORKER-IDENTITY-BINDING — CLOSED_FOR_SHARED_BEARER_IMPERSONATION_IN_PROD — من FORENSIC_AUDIT_SAHOOL_73666EE (F-03/F-04) 2026-07-12
> **تصنيف صدق (قرار المالك 2026-07-25):** التهديد المباشر أُغلِق في الإنتاج @ `9330407`: حامل الـbearer الواسع لم يعد يستطيع سحب قسمة عامل آخر — النقطتان تتطلّبان `X-Worker-Assertion` مربوطة بالطلب (subject=worker_id، fail-closed 403؛ prod-required 503 دون مفتاح؛ dev header-only موثَّق). أُغلِقت الحلقة عبر مفتاح assertion مشترك بين الـadapters + نطاق طلب + إعادة Redis. البقيّة نُقِلت إلى `WORKER-IDENTITY-HARDENING` أدناه (لا تُوسَّع في نفس الشريحة حفاظاً على Ratchet).

## WORKER-IDENTITY-HARDENING — PARTIALLY-CLOSED (المصفوفة السلبيّة على مستوى الـassertion + برهان endpoint-level PG مُغطّيان؛ يبقى PKI/SPIFFE لكلّ عامل — قرار بنية تحتيّة) — من قرار المالك 2026-07-25 (تجزئة WORKER-IDENTITY-BINDING)
> **تحديث 2026-07-26 (`ff3a11d`):** أُغلِق **برهان endpoint-level PG**: `test_worker_assertion_identity_binding_enforced_at_endpoint` (في `test_runtime_worker_tenants.py`، PG حقيقيّ + HTTP، assertion **مُفعَّلة**) يثبت على النقطتين الفعليّتين أنّ انتحال عامل مرفوض (تقديم worker_id=B بـassertion موقَّعة لـA ⇒ 403)، وغياب/تزوير الـassertion ⇒ 403، وتركيب الضابطين (هويّة صحيحة لـA لا تعبر لمستأجر غير مُفوَّض ⇒ 403)، والاكتشاف مربوط بالهويّة. مُثبَّت في wx12_gate، شُغِّل أخضر على PG16 محلّيّ (هجرات decision 001-030). يبقى فقط PKI/SPIFFE لكلّ عامل (بنية تحتيّة، لا نصف حلّ).
- **أُنجِز (شريحة الاختبارات، لا توسيع تصميم):** مصفوفة سلبيّة على مستوى `_verify_worker_identity` (بلا DB) في `test_worker_identity_binding.py` (14 حالة، مثبَّتة في wx12 gate): audience/service mismatch · method mismatch · **expired** · **not-yet-valid/future** (العقد يفرض iat+exp+skew فالمستقبل يُرفض) · **unknown kid** · wrong-key signature · **قبول المفتاح السابق بعد الدوران** (previous kid) · **Redis غير متاح في الإنتاج ⇒ fail-closed 503**. (`nbf` صريح ليس في العقد لكنّ فحص skew المستقبليّ يغطّي «قبل-الصلاحيّة».)
- **المتبقّي:** (١) برهان endpoint-level على PG حقيقيّ: عامل A لا يقرأ feed عامل B، اكتشاف عامل لمستأجر غير مُخوَّل (يتقاطع مع `worker_tenant_authorized` المُثبَت أصلاً؛ يبقى ربط الـassertion على المسار الكامل). (٢) هويّة workload لكلّ عامل (mTLS/SPIFFE/مفتاح لكلّ عامل) بدل المفتاح المشترك — **توسيع تصميم/بنية تحتيّة** يبقى governance-blocked.
- **المصدر:** `services/decision-service/main.py` — تسجيل worker→tenant يقبل `X-Registered-By` غير الفارغ كهويّة فاعل، ونقطة الاكتشاف `GET /v1/learning/runtime-workers/{id}/tenants` لا تُثبت أنّ المستدعي هو ذلك العامل. الحماية الحاليّة: توكن الخدمة المشترك `DECISION_SERVICE_AUTH_TOKEN` (opt-in، يقفل المنفذ الداخليّ كلّه) + strict mode يمنع عمّال مجهولين من الـfeed.
- **الإغلاق الجزئيّ (`9330407` 2026-07-25 — ربط هويّة العامل على النقطتَين المقودتَين-بالعامل):** النقطتان اللتان يقودهما العامل عن نفسه — `GET /v1/learning/runtime-work` و`GET /v1/learning/runtime-workers/{id}/tenants` — تتطلّبان الآن `X-Worker-Assertion` مربوطة بالطلب (`shared/security/service_tenant_assertion`، الموضوع=worker_id، تُقيّد service+method+path+request_id + دفاع إعادة عبر Redis) قبل الوثوق بـworker_id ⇒ الحامل لا يقدر أن ينتحل عاملاً آخر إلّا بحيازة مفتاح الـassertion (لا مجرّد الـbearer الواسع). مرحليّ: fail-open حين `DECISION_WORKER_ASSERTION_KEY` غير مضبوط (تطوير/تنصيبات قائمة)، **مطلوب في الإنتاج** (503). الـadapter (`worker_assertion.py` مُضمَّن، متوافق-بايتيّاً مع الـverifier المشترك عبر `tests_v9/test_worker_assertion_interop.py`) يوقّع الطلبَين. برهان سلوكيّ (other-worker/absent/path-mismatch→403؛ prod-no-key→503؛ dev-no-key→no-op) خطوة CI + wx12 gate مُوسَّع. **صدق:** المفتاح مشترك بين الـadapters (يضيّق مجموعة المُنتحِلين + يربط الطلب/الإعادة) لا هويّة PKI لكلّ عامل — التسجيل يبقى فعل مشغّل (X-Registered-By) خارج نطاق «هويّة العامل عن نفسه».
- **لماذا الباقي مؤجَّل بصدق (لا نصف حلّ):** الربط الأقوى = اعتماد لكلّ عامل (mTLS/SPIFFE/JWT claims) بمفتاح مُصدَر لكلّ عامل + صلاحيّة `runtime.worker_tenant.manage` للتسجيل — قرار بنية تحتيّة (PKI/إصدار هويّات) يخصّ نشر المشغّل.
- **الحالة:** PARTIALLY-CLOSED — هويّة العامل عن نفسه على النقطتَين مربوطة fixed (مفتاح assertion مشترك + نطاق طلب + إعادة)؛ **يبقى** governance-blocked: هويّة PKI/SPIFFE لكلّ عامل + authz تسجيل + تقاطع env صريح (F-05).

## WX-12-RUNTIME-MULTITENANCY — CLOSED (كان OPEN/High من التدقيق الجنائيّ 2026-07-12)
- **الإغلاق (التصميم المُوصى نفسه — feed مُخوَّل، لا header حرّ):** migration 024 `decision_runtime_worker_tenants` (سجلّ تفويض worker→tenant تشغيليّ، upsert idempotent مع replay/conflict، تعطيل بلا حذف) · الـfeed يرفض 403 `worker_tenant_unauthorized` أيّ مستأجر غير مُفوَّض لعامل مُسجَّل (العامل غير المُسجَّل يبقى على السلوك القديم — لا كسر للتنصيبات القائمة) · نقطة اكتشاف `GET /v1/learning/runtime-workers/{id}/tenants` يُعدّد منها العامل قسمته من الخادم · الـadapter يحلّ مستأجريه بأولويّة صريحة (RUNTIME_TENANT_IDS ← RUNTIME_TENANT_ID ← اكتشاف خادميّ) ويلفّ run_once عليهم؛ غياب أيّ تعيين = خطأ عقد صريح. برهان HTTP كامل على PG حقيقيّ (403/200/اكتشاف) + بوّابة wx12_runtime_multitenancy_gate. **تصلّب لاحق (تدقيق 73666ee):** migration 025 سجلّ أوامر append-only + إسقاط بمراجعة رتيبة (يقتل stale-replay)، راية strict fail-closed للعمّال المجهولين، قاعدة جاهزيّة F-09 للتوكن، بوّابة أعمق + 5 اختبارات سلوك PG/HTTP — انظر ledger 2026-07-12 (تصلّب multitenancy) وفجوة WORKER-IDENTITY-BINDING.

## WX-12-RUNTIME-MULTITENANCY (المدخل الأصليّ) — من التدقيق الجنائيّ 2026-07-12
- **المصدر:** `service.py` يعتمد `RUNTIME_TENANT_ID` واحداً لكلّ process؛ غير قابل للتوسّع لمنصّة SaaS متعدّدة المستأجرين (instance لكلّ tenant هشّ).
- **لماذا مؤجَّل:** قرار بنية (NATS partition by tenant أو worker مُخوَّل بتعداد مستأجرين من الخادم) + عدم السماح للـworker باختيار tenant من header بحرّية — يتقاطع مع مصادقة الخدمة (Critical 1 المُغلَق يمنع الانتحال؛ التقسيم المُخوَّل خطوة تالية).
- **التصميم المُوصى:** feed مُخوَّل يُرجِع عمل المستأجرين المسموح بهم للـworker المُصادَق فقط (لا header حرّ)، أو استهلاك NATS مُقسَّم.

## VEG-EVIDENCE-STORE — CLOSED @ `4b35809` (كان OPEN من تسوية `full_plan_closed`)
- **الإغلاق:** migration 019 أنزلت `decision_vegetation_snapshots` (content-addressed + CHECK availability>=acquisition + append-only + RLS) **مع كاتبها** `POST /v1/evidence/vegetation-snapshots` (canonical replay) وتحقّق الربط المُصنَّف + FK مركّبة بالمستأجر + الـtrigger الدلاليّ — بالضبط شرط الإغلاق المُدوَّن (المخزن مع كاتبه). المتبقّي منفصلاً: توصيل المنتِج (vegetation-service يدفع لقطاته) — ضمن Phase B/C.

## VEG-EVIDENCE-STORE (المدخل الأصليّ) — من تسوية `full_plan_closed` 2026-07-12
- **المصدر:** هجرة الحزمة المُسلَّمة أنشأت `decision_vegetation_snapshots` + `decision_field_history_snapshots` في decision-service **بلا أيّ كاتب/قارئ** — لم تُنزَل (`41211c6`؛ الملحق في `docs/audits/VEGETATION_AGRIAI_FULL_PLAN_CLOSURE_20260712.md`).
- **لماذا مؤجَّل:** مخزن أدلّة نباتيّ أوّل-الدرجة في decision-service يتطلّب كاتبه (ربط vegetation→decision عند الالتقاط) وقارئه (تحقّق الربط) — نصف حلّ يخالف الانضباط.
- **التصميم المُوصى:** ضمن Phase B/C من الخطّة الرئيسيّة — كاتب في مسار compose (السياق يحمل vegetation_snapshot_id مرجعاً لمخزن ثابت content-addressed بنمط 018_ac1: idempotency+request_hash+append-only+CHECK data_available_at>=acquisition_at) + تحقّق `_validate_decision_context` يقبل المرجع.

## RASTER-PROVENANCE-ENRICHMENT — CLOSED (كان OPEN من بوّابة سلطة NDVI 2026-07-12)
- **الإغلاق:** `ProvenanceRecord` أُثري بأربعة حقول أمينة: `acquisition_datetime` (نفس قيمة capture_datetime — تسمية بوّابة السلطة)، `algorithm_version` (ثابت `sahool.band_math/1` المُصدَّر من raster_quality حيث تعيش الصيَغ فعلاً)، `qa_mask_version` (هويّة استراتيجيّة القناع المُطبَّقة `<strategy>/1` **فقط عند تطبيق قناع سحابيّ فعليّاً** — المشهد غير المُقنَّع يبقى غير-سلطويّ بصدق)، `valid_pixel_pct` (توأم النسبة ×100). يُملأ في `build_validated_raster_product` و`layer_lookup`. برهان تقاطعيّ: بروفينانس مُثرى يجتاز `indicator_registry.validate_observation` بلا أخطاء (اختبار في raster يستورد بوّابة النبات).

## RASTER-PROVENANCE-ENRICHMENT (المدخل الأصليّ) — من بوّابة سلطة NDVI 2026-07-12
- **المصدر:** `raster_validated_product.ProvenanceRecord` يمدّ `capture_datetime`/`processing_version` **بلا** `qa_mask_version`، و`ValidatedIndicatorProduct` يمدّ `valid_pixel_ratio` (0..1) — بينما `indicator_registry.validate_observation` (سلطة NDVI الإنتاجيّة) يطلب `acquisition_datetime`/`algorithm_version`/`qa_mask_version`/`valid_pixel_pct` (`41211c6`).
- **الأثر الصادق:** في `VEGETATION_REAL_ONLY` الإنتاجيّ يفشل التحليل مُغلَقاً (424) حتى مع NDVI حقيقيّ — مقصود: لا تنفيذ بلا بروفينانس كامل. vegetation حوّل النسبة→نسبة مئويّة (وحدة فقط)؛ الأسماء الزمنيّة/الإصداريّة لم تُؤَلَّس.
- **التصميم المُوصى:** إثراء raster: ينشر `acquisition_datetime` (alias صادق لـcapture_datetime) + `algorithm_version` (من formula/processing) + `qa_mask_version` (من مسار SCL/cloud-mask الفعليّ) + `valid_pixel_pct` في provenance — ثمّ بوّابة السلطة تمرّ على بيانات حقيقيّة بلا تليين.

## FII-LIVE-RLS-GATE-ON-MAIN — LIVE-CERTIFIED FULLY (v192 + v194، الملاحظة أُغلِقت) — على `fdfc521` 2026-07-18
- **إغلاق ملاحظة المنهج (لاحقاً نفس اليوم):** طُبِّقت سلسلة الهجرات الكاملة **v1..v196 (202 خطوة) 0-error على PostGIS 16 حيّ** على قاعدة جديدة — أي أنّ v192 (الخطوة 198) و v194 (الخطوة 200) طُبِّقتا على **الجداول الإنتاجيّة الحقيقيّة بمخطّطها الكامل** (scouting_pins/prescriptions/recommendations/decision_record/work_orders/actuator_command_dedup/outcome_record/lineage_link التي تنشئها v75–v95) لا بجداول أدنى. الملاحظة المنهجيّة (أعمدة أدنى) **أُغلِقت** — التطبيق على المخطّط الكامل مُثبَت. البوّابة الآن **مُصادَقة حيّاً بالكامل**.
- **المصدر:** الـFF `9e38080..dae894b` أنزل عمل FII الأمنيّ إلى main: `migrations/v192_fii_rls_write_fail_closed.sql` + `migrations/v194_fii_chemical_chain_rls_fail_closed.sql` + حوكمة `chemical_lineage`. سجلّ الدفتر اشترط بوّابة PostgreSQL حيّة قبل الـFF، والـFF سبقها. **شُغِّلت البوّابة حيّاً بأثر رجعيّ على قمة main (`fdfc521`) — 2026-07-18.**
- **v192 — مُصادَق حيّاً بالكامل على PG 16:** (1) `tests_v9/test_fii_rls_write_fail_closed_postgres.py` **6/6 passed, 0 skipped** (رفض السياق المفقود/الفارغ/المشوَّه/مستأجر-خاطئ · كتابة المطابق فقط · لا تسرّب عبر-سياق). (2) **الهجرة المشحونة نفسها** طُبِّقت 0-error على `scouting_pins`/`prescriptions` الحقيقيَّين ⇒ سياق فارغ تحت دور `NOSUPERUSER NOBYPASSRLS` ⇒ `ERROR: new row violates row-level security policy` (تعضّ على مسار النشر). (3) بصمة السياسة المشحونة (FORCE + USING + WITH CHECK على `app.current_tenant`) طابقت المُختبَر حرفيّاً. (4) `fii_rls_write_policy_gate` PASSED.
- **v194 — مُصادَق حيّاً على PG 16 (المسارَان):** (أ) موجب: الهجرة المشحونة طُبِّقت 0-error على جداول السلسلة الستّة الحقيقيّة (`recommendations`/`decision_record`/`work_orders`/`actuator_command_dedup`/`outcome_record`/`lineage_link`) ⇒ سياق فارغ ⇒ `ERROR: new row violates row-level security policy for table "recommendations"`. (ب) سالب (forensic finding #12): بإسقاط `lineage_link` ترمي الهجرة `EXCEPTION: v194 FII fail-closed: required chain table public.lineage_link is absent; refusing to leave an FII chemical-lineage write path unprotected` — أي fail-closed-on-absence مُثبَت فعليّاً.
- **ملاحظة المنهج (صدق):** جداول الهدف/السلسلة أُنشئت **بأسمائها الحقيقيّة لكن بأعمدة أدنى (`id, tenant_id`)** لا بمخطّطها الإنتاجيّ الكامل — وهذا **برهان أمين للسياسة** (السياسة تقرأ `tenant_id` فقط)، نفس منهج v192 المُقيَّم «أقوى من اختبار تطبيقيّ». التطبيق على المخطّط الكامل عبر السلسلة v1..v194 يبقى تحسيناً (ترتيب الهجرات محروس أصلاً بـfinding #12 الذي بُرهِن أعلاه). الأدوار: البوستشر السلوكيّ (NOSUPERUSER/NOBYPASSRLS لا يتجاوز) مُثبَت؛ دور `sahool_app` الفعليّ محروس بتزويد الأدوار + `field_management_live_gate` (#584).
- **الأثر:** لم تعد على main أيّ آلية أمنيّة RLS في نطاق FII بلا برهان حيّ. الخلل الذي حذّر منه الدفتر (آلية أمنيّة مدموجة بلا برهان) **مُغلَق لـ v192 و v194**.

## ③ عزل مفتاح المنتِج (activation signing-key isolation) — CLOSED-IN-CODE 2026-07-18 (`e2f330e`)
- **الحقيقة عند الفحص:** العزل **قائم أصلاً** في الكود+compose (عمل Gate-Trust): `ACTIVATION_EVIDENCE_SIGNING_KEY` و`ACTIVATION_PROBE_SIGNING_KEY` متغيّران مخصّصان، كلٌّ من `${اسمه:-}` الخاصّ، **لا يُسنَد أيّهما لـ`${JWT_SECRET}`/`${SAHOOL_AGENT_TOKEN}`** (تحقّق grep = صفر). المفتاح ليس دفاعاً-في-العمق فوق مفتاح الخدمة بل جذر ثقة معزول بمتغيّره.
- **المُضاف (قفل + توثيق):** `tests_v9/test_activation_signing_key_isolation_guard.py` يفشل CI إن أسند تعديلٌ مستقبليّ أيّ مفتاح توقيع لسرّ الخدمة/JWT (برهان سالب) + ملاحظة `.env.example` صريحة: القيمة يجب أن تكون سرّاً متمايزاً عن JWT_SECRET/SAHOOL_AGENT_TOKEN/probe.
- **المتبقّي (مشغّل، بصدق):** تزويد **قيَم** سرّيّة متمايزة فعليّاً — واجب secret-manager لا يراه فحص ساكن. الجزء الكوديّ من ③ مُغلَق ومقفول ضدّ الانحدار.

## ⑥ db_ownership baseline + LOOP_TABLES⊆ownership — CLOSED 2026-07-18 (`773beb8`)
- **الإغلاق:** `db_ownership.yml` كان يسجّل 4 جداول decision فقط. مُلِئ الأساس: أُضيفت 38 جدولاً تنشئها هجرات decision-service ذاتها (owner=decision-service، sole writer، مصدر=الهجرة)؛ تُحقِّق أنّ **0 منها** تنشئه هجرة منصّة/عامّة (ملكيّة قاطعة). الخمسة interim-bridge (decision_record/dispatch_decisions/outcome_record/recommendation_outcomes/online_learning_updates) **لم تُقلَب** — تبقى platform-owned + mirror:decision-service حتّى قلب SoR (رنبوك ⑤).
- **الفحص المَوصول:** `test_every_loop_table_is_owned_by_decision_service` يؤكّد `LOOP_TABLES ⊆ {owner=decision-service} ∪ {mirror=decision-service}` (تحليل بلا تبعيّة YAML). بند mirror يغطّي الخمسة الآن ويصير redundant بعد قلب SoR بلا تعديل. برهان سالب مُضاف. 8/8 حُرّاس · كلّ مستهلكي db_ownership خضر (بوّابتا decision-SoR تؤكّدان `decision_record status=interim-bridge` محفوظ).

## FIELD-SVC-TENANT-HEADER-TRUST — CLOSED_IN_CODE / LIVE_CONFIG_AND_REPLAY_E2E_PENDING — من مراجعة cherry-pick 2026-07-18
> **مستوى الإثبات (تصويب المالك 2026-07-25):** مسار الإنتاج يتطلّب مطالبة مستأجر موقَّعة ويفشل مغلقاً عند غياب المفتاح أو مخزن الـreplay. **لا تُرفَع إلى VERIFIED** بعد: (١) fallback التطوير يعتمد الترويسة الحرّة عند غياب المفتاح (بالتصميم، APP_ENV=production ⇒ لا fallback)؛ (٢) تحقّق سلوكيّ مستقلّ لمسار replay/wrong-service/prod-503 مطلوب؛ (٣) لا رقم اجتياز (مثل «45/45») يُسجَّل بلا إخراج اختبار قابل للتتبّع على SHA محدَّد. مُوصى: guard في CI يثبت أنّ صورة الإنتاج تضبط strict mode صراحةً بدل الاعتماد على الافتراض.
- **المصدر:** `services/field-management-service/main.py` — `_require_service_token` (`:55-70`) يصادق `X-Agent-Token` فقط (hmac.compare_digest؛ JWT وحده مرفوض 401، لا قارئ JWT في الخدمة)، و`_require_tenant` (`:76-85`) يأخذ المستأجر **حصراً من ترويسة `X-Tenant-Id`** لا من claim موثوق. النتيجة: **أيّ خدمة تحمل `SAHOOL_AGENT_TOKEN` تقرأ حقول أيّ مستأجر بإرسال X-Tenant-Id عشوائيّ** — رباط المستأجر يقوم على ترويسة قابلة للضبط من أيّ حامل توكن-وكيل. RLS مفروض (`set_config`+`WHERE tenant_id=$2`) لكنّه يعزل بالقيمة المُرسَلة لا بقيمة موثوقة مصدريّاً.
- **الموقف:** هذا **عقد #201 الموثَّق عمداً** («service-token only · tenant from X-Tenant-Id header») — الثقة انتقلت من «claim JWT لا يُزوَّر» إلى «الخدمة المُنادية تُشتقّ X-Tenant-Id بأمانة من JWT المستخدم». ليس تراجعاً جديداً، لكنّه موقف يعتمد على سلامة كلّ مُنادٍ + سرّيّة `SAHOOL_AGENT_TOKEN`.
- **التصلّب المُوصى (لاحقاً، لا الآن):** بدل ترويسة X-Tenant-Id الحرّة، يمرّر المُنادي **مطالبة موقَّعة** (JWT المستخدم أو توكن خدميّ يحمل نطاق المستأجر) تتحقّق منها field-management-service وتشتقّ المستأجر منها — فيصبح الرباط غير قابل للتزوير حتّى بين حاملي توكن الوكيل. **اكتُشِف أثناء مراجعة البند (2) المُسقَط:** تغيير user_bearer المحليّ كان no-op (النقطة لا تقرأ JWT)، لكنّه كشف هذا الموقف.
- **التصميم مُجمَّد في ADR (بإذن المالك، تصميم فقط لا تنفيذ) 2026-07-18:** [`docs/adr/ADR-0033-field-management-tenant-claim-trust.md`](../../docs/adr/ADR-0033-field-management-tenant-claim-trust.md) — النموذج الحاليّ · لماذا مخاطرة مقبولة مؤقّتاً (محيط مصادَق، توكن واحد، نصف قطر = خدمة داخليّة لا عميل خارجيّ) · التصميم المستهدَف (**الخيار A**: توكن خدميّ قصير العمر يحمل `tid` موقَّعاً بمفتاح المُنادي/مفتاح mesh معزول؛ الخيار B تمرير JWT كامل = تسريب أوسع، احتياطيّ فقط) · الترحيل المرحليّ (قبول الترويسة+المطالبة ⇒ تحذير ⇒ رفض الترويسة) · **محفّز التنفيذ:** أوّل تعديل جوهريّ على field-management **أو** إضافة مستهلك جديد لـ`/internal/fields`.
  - **فُحص في الشريحة 3 (SEASON-RECORD-ENTRY UI) 2026-07-19: المحفّز غير مشتعل** — صفحة إدخال الموسم تعيد استخدام مكوّن رسم الحقل الذي يستهلك **API المنصّة العامّ JWT-محميّ** (`kongApi`: `POST /api/v1/fields` · `/api/v1/drawing-features`)، **لا `/internal/fields`** (يظهر فقط خادميّاً: منصّة→field-management بتوكن خدمة). لا مستهلك جديد للمسار الداخليّ ⇒ لا لمس، ADR-0033 يبقى OPEN بلا تنفيذ. يبقى OPEN حتّى المحفّز؛ عندها ترجمة وثيقة لا إعادة اكتشاف.
  - **تصويب صدق للحالة (2026-07-25 — مطابقة السجلّ للشجرة):** المصدر أعلاه (`:76-85` ترويسة X-Tenant-Id حصراً، «بلا فرض») **بائت** — الكود الحيّ في `services/field-management-service/main.py` يُنفِّذ الآن **الخيار A من ADR-0033**: `_require_tenant` (`:90-130`) يتحقّق من `X-Tenant-Assertion` موقَّعة (`verify_tenant_assertion`، نطاق service+tenant+method+path+request_id)، **يُلزمها في الإنتاج** (503 حين غياب `FIELD_SERVICE_TENANT_ASSERTION_KEY`)، ويستهلك nonce مرّةً عبر Redis (`_claim_assertion_once :133-152`، الإنتاج لا يعود لذاكرة العمليّة). دوران المفاتيح (current+previous kid) مضبوط. تغطية عقديّة في `test_field_management_service_contract.py`. ⇒ الحالة الحقيقيّة **CODE-CLOSED** لا OPEN. **الباقي بصدق:** (1) وضع dev بترويسة فقط (غياب المفتاح ⇒ توافق خلفيّ — بالتصميم)، (2) **برهان مُنادٍ حيّ** أنّ المنصّة تُوقّع الـassertion فعلاً على نداءات `/internal/fields` في الإنتاج (تشغيليّ لا كوديّ). لا نصف حلّ: الفرض موجود ومقفول-عند-الفشل في الكود؛ ما يبقى إثبات تشغيليّ لا بناء.

## AUTH-E2E-UNDER-RESTRICTED-ROLE — LIVE-CERTIFIED (CLOSED) 2026-07-18 (`9a3ce99`)
- **الإغلاق (رنبوك حيّ):** رُفِعت طبقة البيانات **أصلاً** في حاوية الجلسة (Docker Hub محجوب بسياسة الشبكة — 403 على registry — فاستُعمِل PostgreSQL 16 + PostGIS 3.4 **الأصليّ** لا حاوية): **202 هجرة 0-خطأ على المخطّط الإنتاجيّ الكامل (304 جدول)** + نموذج الأدوار (`sahool_app` NOSUPERUSER/NOBYPASSRLS/NOINHERIT + `sahool_jobs` BYPASSRLS، مُتحقَّق حيّاً). برهان FII RLS fail-closed حيّ (سياق فارغ ⇒ `RLS ERROR` على `recommendations`). ثمّ `test_auth_e2e` تحت `sahool_app`: **10/10 نجاح** (كان 1/10). حارس الأدوار الذي حجب تحت superuser لم يعد يحجب.
- **علّتان لم تكونا خطأ دور/RLS:** (1) **مصفّي الوحدة (harness):** الاختبار يحمّل main كـ`auth_main` لكن الراوترات `import main` ⇒ نسخة ثانية `_pool=None` ⇒ 500؛ أُصلِح بـ`sys.modules["main"]=m` قبل exec. (2) **تأكيد بائت:** توقّع خفض التسجيل الذاتيّ لـ`farmer`؛ العقد المشحون يجعل المُسجِّل **مالك مؤسّسته الجديدة** (tenant_id افتراضه gen_random_uuid) لا تصعيداً — ومنع التصعيد **بنيويّ** (لا حقل role في RegisterRequest). مطابق لـ`test_auth_signup_owner.py` (register يجب ألّا يُثبّت farmer — Bootstrap Deadlock). صُحِّح التأكيد لـ`owner`. الاختبار يتخطّى نظيفاً بلا DB (integration) ⇒ CI الوحدة سليم.
- **~~التكليف~~ (السابق):** OPEN (Low) — من قبول ⑥ 2026-07-18
- **المصدر:** `pytest -m integration` على المخطّط الكامل (v1..v196) أعطى 123 passed · صفر خلل مخطّط/DB، لكن `test_auth_e2e` سقط لأنّ الاتّصال كان بدور superuser فرفضه حارس الأدوار `assert_db_role_rls_safe` (`shared/db_role_guard.py:97`) — **الحارس يعمل، ليس خللاً** (superuser يتجاوز RLS).
- **التكليف (رفعه المستخدم من توصية إلى مهمّة):** إعادة تشغيل الجناح التكامليّ الحيّ متّصلاً بدور `sahool_app` المقيَّد (NOSUPERUSER/NOBYPASSRLS) بدل superuser — عندها يتحوّل `test_auth_e2e` من «فشل مفسَّر» إلى «اجتياز/تخطٍّ نظيف». السبب: الفشل المفسَّر خطر توثيقيّ — قارئ مستقبليّ يمرّره دون قراءة تفسيره.
- **الشرط البيئيّ:** يحتاج DATABASE_URL موجَّهاً لـsahool_app + طبقة الخدمة (نفس شرط بنود الرنبوك ③④⑤⑦). يُنفَّذ في بيئة المالك ضمن جولة الرنبوك الحيّة القادمة.

## BRANCH-GRAVEYARD-POLICY — OPEN (رُفِعت إلى Medium 2026-07-28 — الجرد كشف فقدان قرار) · تحديث 2026-07-28: قياس فعليّ + قرار مفقود كاد يُمحى — كشفه فشل حذف 2026-07-18

> **أثر دمج، مُصلَح 2026-08-02:** كان هذان سطرين متلاصقين، كلٌّ عنوان `## ` لنفس
> المعرّف بلا متن بينهما — بصمة ضمّ `union` لنسختَي سطر واحد. أوّل إصابة حقيقيّة
> لـ`brain_duplicate_gap_identity_guard`، وُجِدت في الشجرة **قبل** وصل الحارس. دُمِج
> النصّان في عنوان واحد بلا حذف كلمة، لأنّ الجانبين جاءا من جلستين.

- **الطلب:** «احذف ما لا عمل فريد فيه». **لم يُنفَّذ — الحذف محجوب بيئيّاً:** `git push --delete` يُجاب بـ**HTTP 403**، ولا أداة حذف فرع في مجموعة GitHub MCP المتاحة (`create_branch` موجودة، لا نظير لها للحذف). الحذف من واجهة GitHub أو جهاز المالك.
- **القياس (٤٢٣ فرعاً):** اختبار الأسلاف يُثبت فرعين فقط — عديم الجدوى لأنّ المستودع يدمج **بالضغط** فتبقى بصمات الفرع خارج main. اختبار `merge-tree` (هل يُغيّر دمج الفرع شجرة main؟) صحيح مفهوميّاً لكنّه يتعارض على **٤١٩** فرعاً، والتعارض كلّه في الآثار المولَّدة التي تُعيد كلّ شريحة توليدها — نفس العلّة البنيويّة المسجَّلة في `decisions/ledger.md`.
- **المُثبَت (مقارنة محتوى المصدر، تستثني المولَّدات وتتحفّظ عند أيّ اختلاف):** **٤ فروع** لا تحمل شيئاً يفتقده main — `claude/build-id-no-fake-identity` (#684) · `claude/decision-center-unify-sidedoors` · `claude/guard-fp-and-fastapi-pin` (#686) · `claude/wire-canonical-field-state` (#682). و`develop` خالٍ محتوىً أيضاً لكنّه **فرع تكامل قائم لا شريحة** ⇒ استُثني من الترشيح صراحةً.
- **الباقي (~٤١٦) لم يُثبَت خلوّه.** الاختبار يتحفّظ عمداً: أيّ ملفّ تقدّم فيه main يُصنَّف «يحتاج حكماً» لا «فارغ». إثباتها يحتاج ربط كلّ فرع بـPR مدموج — ممكن عبر GitHub لا محلّيّاً.
- **الاكتشاف الذي غيّر الجواب:** الجرد **ليس نظافةً فقط**. `claude/brain-session-close` يحمل **٨ أسطر في `decisions/ledger.md` غائبة عن main**، منها **قراران كاملان**: ربط النواة الرابعة بأمر المالك بعد اعتراض الوكيل المُسجَّل (#682)، وتقسيم شريحة الإيقاظ بدل وسم ١١ اختباراً بـ`xfail` (#681⇒#683). حذف الفرع كان سيمحو قراراً حقيقيّاً بسببه — مخالفة مباشرة لقاعدة CLAUDE.md «لا قرار بلا سبب + PR/SHA». **استُنقِذا حرفيّاً إلى `ledger.md`** في هذه الشريحة.
- **القاعدة المستخلَصة:** لا يُحذَف فرع قبل مقارنة **سطريّة** لملفّات الدماغ عليه بـmain. الفرع المدموج شيفرةً قد يبقى حاملاً وحيداً لتوثيق لم يُدمَج — لأنّ الدمج بالضغط ينقل ما في الـPR، لا ما كُتب على الفرع بعده أو خارجه.
- **الحالة:** `claude/brain-session-close` و`claude/code-review-34hO3` و`claude/wake-dormant-unit-tests` **ليست مرشَّحة للحذف الآن**: الأوّل كان يحمل المفقود (يصير مرشَّحاً بعد دمج هذه الشريحة)، والثاني يحمل ٦ أسطر سجلّ + ٣ في `SERVICE_REGISTRY.md` غير مُتحقَّق من اندماجها، والثالث يحمل `test_unit_environment_completeness.py` المنقول إلى هذه الشريحة (يصير مرشَّحاً بعد دمجها).

### الأصل (2026-07-18)
- **المصدر:** محاولة حذف `claude/code-review-34hO3` كشفت **~400 فرعاً بعيداً مهجوراً** (claude/·fix/·refactor/·copilot/·feat/…)، معظمها ميت منذ أشهر. بيئة بهذا الكمّ تجعل «القمة القانونيّة» مفهوماً هشّاً وتُسهم في فوضى تصادم الجلسات.
- **المُقترَح (لاحقاً، لا الآن):** سكربت «جنازة فروع» يقترح حذف فرع **مُدموج في main** أو **خامد >60 يوماً**، دفعة أسبوعيّة **بمراجعة بشريّة**، مع قائمة استثناء للفروع الموثّقة كمرجع (main·develop·الموثّقة). لا يُطبَّق تلقائيّاً بلا مراجعة.
- **قيد بيئيّ مكتشَف:** حذف الفروع من هذه الجلسة محجوب (`git push --delete` → 403؛ لا أداة MCP لحذف ref) — الجنازة تُنفَّذ في بيئة المالك.
- **دفعة إضافيّة مدموجة تنتظر الحذف الفيزيائيّ (جلسة 2026-07-21، كلّها ⊆ main، أُكِّدت خضرة CI قبل الدمج):** `claude/code-review-34hO3` · `claude/field-forms-01` (#585) · `claude/erp-bridge-fix-01` (#587) · `claude/adr-physics-ai-calibration-01` (#588) · `claude/axios-security-1.18` (#589) · `claude/field-forms-api-integration-tests` (#590) · `claude/adr-0035-relocation` (#591). النسخ المحلّية حُذِفت؛ الريموت محجوب بـ403 (مهمّة المالك عبر UI/جهازه).

## BRANCH-FUNERAL — القاعدة المُثبَّتة + دفعة الحذف الأولى (بأمر المالك 2026-07-18)
- **القاعدة:** فرع **مدموج أو 0-ahead** ⇒ حذف فوريّ · فرع **خامد >30 يوماً** ⇒ أرشفة SHA في الدماغ ثمّ حذف على دفعات (~30/أسبوع، استرجاع بالـSHA ممكن — الحذف لا يمحو الـobjects) · فرع **نشط <7 أيّام** ⇒ لا يُمسّ · **`code-review-34hO3` مُصفّى** (رُوجِعت دلتاه كاملةً، لا قيمة محتجزة).
- **الدفعة الأولى — آمنة للحذف الآن (المالك ينفّذها؛ الجلسة محجوبة 403):**
  - `certification/final-readiness-evidence` · `claude/unify-main-and-certification` · `copilot/29041154936` (مدموجة، محتواها ⊆ main) · `claude/code-review-34hO3` (مُصفّى بالمراجعة).
  - **`develop` — لا يُحذَف** (فرع قانونيّ ثانٍ).
- **الأمر:** `for b in certification/final-readiness-evidence claude/unify-main-and-certification copilot/29041154936 claude/code-review-34hO3; do gh api -X DELETE repos/kafaat/ai_platform_complete_v2.0.0_enhanced/git/refs/heads/$b; done` (أو حذف من واجهة GitHub). التقرير الكامل: `docs/audits/BRANCH_TRIAGE_REVIEW_20260718.md`.

- **الأداة مبنيّة (`cf9f6b0`+):** [`scripts/ops/branch_funeral.py`](../../scripts/ops/branch_funeral.py) — تصنيف + حذف محروس (DRY-RUN افتراضيّ · fail-safe بلا بيانات PR · أرشفة SHA قبل الحذف · دفعات `--limit` · `--apply` بتأكيد). dry-run حيّ 2026-07-18: 384 فرعاً ⇒ zero-ahead=3 (آمن) · stale-unmerged=255 (أرشفة+حذف) · review-manual=122 · recent-keep=4. التنفيذ في بيئة المالك (gh + حذف). تقرير: `docs/audits/BRANCH_TRIAGE_REVIEW_20260718.md`.

- **مراجعة 2026-07-20 (بأمر المالك «راجع جميع الفروع الفاشلة») — النشطة فقط، والمقبرة مؤجَّلة بقرار:**
  - **الفروع النشطة الثلاثة كلّها خضراء على `ci.yml`:** `main` (139eb0d ✅) · `develop` (84e14f0 ✅) · `claude/code-review-34hO3` (fa6a128 ✅ — أُصلِح ودُمِج اليوم). **صفر فرع فاشل نشط.**
  - **المقبرة:** 386 فرعاً بعيداً؛ ~380 بلا CI حديث (خامدة). **لم يُجرَ مسح CI شامل عمداً** (قرار المالك): (١) الحذف نفسه محجوب بيئيّاً (403 على ref-deletion يحجب الـ380 كما حجب 34hO3) ⇒ قائمة فرز الآن غير قابلة للتصرّف؛ (٢) الفروع تشيخ ⇒ الفرز الصحيح لحظة جلسة الحذف لا قبلها. **البروتوكول:** يُستدعى `branch_funeral.py --dry-run` في **جلسة حذف المالك نفسها** (تصنيف بحالة PR-merged عبر GitHub API لا بنسب SHA؛ squash يكسر النسب) — لا منهج جديد، لا إنفاق نداءات استباقيّ.
  - **🪦 جاهز للحذف الفوريّ (بند مؤكَّد):** `claude/code-review-34hO3` — محتواه مُدمَج بالكامل في `b01c75b` (main، 0/34 غير مُدمَجة) ومؤرشَف في سجلّ الجنازة (`139eb0d`). الأمر: `gh api -X DELETE repos/kafaat/ai_platform_complete_v2.0.0_enhanced/git/refs/heads/claude/code-review-34hO3` (أو واجهة GitHub). لا يحتاج فرزاً — جاهز.

## SIM-PATHS-DUAL — OPEN (يُحسم عند مواصفة SIM-GOLDEN-01) — سُجِّل مع SEASON-RECORD-01 (v201)
- **الملاحظة:** مساران للمحاكاة الموسميّة يتعايشان: (١) `season_simulation.py` على المنصّة (RUE/FAO-56 نقيّ، نطاق±ثقة) و(٢) `wofost_adapter.py` في agriai-engine (PCSE/WOFOST أو بديل Liebig حتميّ، عقد قدرة). كلاهما صادق (غير مُعايَر، مُعلَّم). عند بناء SIM-GOLDEN-01 يجب **حسم أيّهما نقطة المعايرة ضدّ `season_harvest.yield_kg_ha`** (المُشتقّ عبر `season_calibration_eligibility` من v201) لتفادي مصدرَي حقيقة للتنبّؤ.
- **المصدر:** `services/sahool-platform/api/season_simulation.py` · `services/agriai-engine/wofost_adapter.py` · `migrations/v201_season_records.sql` (season_calibration_eligibility). **الحالة:** OPEN — لا فعل الآن (SEASON-RECORD يجمع البيانات؛ SIM-GOLDEN يستهلكها لاحقاً بعد توفّر مواسم مؤهَّلة).
  - **اتّجاه الحسم (من مسح المحاكاة المفتوح 2026-07-20، `sahool-brain/research/open_season_simulation_models_survey_20260720.md`):** قاعدة توجيه واحدة معلَنة لا منطق ضمنيّ — **مدخل ملوحة (ECe/ECsw) ⇒ AquaCrop؛ بلا ملوحة ⇒ PCSE**؛ و`season_simulation` يبقى النموذج الخفيف للمنصّة. مسار المعايرة الواقعيّ: **SEASON-RECORD-01 → QUEFTS+WOFOST → SIM-GOLDEN** (QUEFTS توصية WOFOST الرسميّة عند قلّة البيانات: حصاد + تحليل تربة = وصف SEASON-RECORD حرفيّاً). AquaCrop = المحرّك الثالث المُقترَح في مواصفة WATER-SALT-02 (محجوبة على إقفال v201 + اعتماد). Gym/RL أرشيف فقط.
  - **حُسِم جزئيّاً (WATER-SALT-02، 2026-07-20):** المسار الملحيّ محسوم بقاعدة توجيه صريحة — `aquacrop_adapter.salt_engine_applies`: `ec_e >= AQUACROP_ECE_THRESHOLD` (2.0 dS/m) ⇒ المحرّك الملحيّ (Maas-Hoffman الداخليّ، `aquacrop_uncalibrated`)؛ وإلّا PCSE (مصدر حقيقة واحد). يبقى `season_simulation` (المنصّة، خفيف) مقابل PCSE (agriai) للمسار غير-الملحيّ — يُحسَم عند SIM-GOLDEN-01. عقد قدرة `AQUACROP_SALT_CAPABILITY` + حارس `test_aquacrop_salt_capability_contract.py` (7). **صدق:** «لا نقل ملح زمنيّ» بقي في limits (Maas-Hoffman ثابت؛ لم يُنقَل لcovers خلافاً لـ§Q2 لأنّ حزمة aquacrop الديناميكيّة مؤجَّلة).
  - **اتّجاه الحسم المعتمد مسبقاً (2026-07-20، اقترحه المراجع الرئيسيّ في تحليل الازدواج «أميل لـ(ب)»، اعتمده المالك — يُصدَّق رسميّاً في مواصفة SIM-GOLDEN-01 لا يُبنى الآن):** **تسلسل هرميّ مُعلَن (الخيار ب)** لا دمج ولا منصّة-أوّلاً:
    | المسار | الدور الرسميّ | القاعدة |
    |---|---|---|
    | **PCSE/WOFOST** (`services/agriai-engine/wofost_adapter.py`) | **المرجعيّ — نقطة المعايرة الوحيدة** | كلّ غلّة «رسميّة» تُعرَض للمستخدم أو تدخل معايرة تصدر منه (عند توفّر pcse + كفاية المدخلات) |
    | **season_simulation** (`services/sahool-platform/api/season_simulation.py`) | **استكشافيّ فقط (screening)** | يُوسَم `screening_only` صراحةً؛ يُمنَع ظهوره حيث يتوفّر PCSE لنفس الحقل/الموسم — لا رقمان جنباً إلى جنب أبداً |
    | **AquaCrop** (Maas-Hoffman، `aquacrop_adapter.py`) | **المسار الملحيّ — محسوم** | `ec_e >= 2.0` ⇒ هو، وإلّا PCSE |
  - **لماذا (ب) لا (أ)/(ج):** الدمج (ج) يخلط RUE ثابت المعاملات بفيزيولوجيا يوميّة في جلد واحد (أسوأ من الازدواج) · المنصّة-أوّلاً (أ) تُورِث قيد النموذج الأخفّ (نطاق ±20٪ ثابت، `season_simulation.py:21,113`) للمرجعيّ · الهرميّ (ب) يُبقي قيمة `season_simulation` الحقيقيّة (إجابة خفيفة سريعة في «ماذا لو»/crop_twin) دون أن ينازع PCSE، والمعايرة ضدّ `season_harvest.yield_kg_ha` تذهب لمحلّها العلميّ: محرّك يوميّ الخطوة **قابل للمعايرة فعلاً**، لا نموذج موسميّ ساكن.
  - **الشرطان التنفيذيّان عند المصادقة (في مواصفة SIM-GOLDEN-01):** ① `screening_only` **حارس لا تعليق:** عقد `services/agriai-engine/simulation_capability.py` (SIM-PCSE-01) يُعدَّل ليُعلِن الهرميّة بمرجع `file:line`، وحارس سلبيّ (نمط `tests_v9/test_simulation_capability_contract.py`) يرفض ظهور غلّة `season_simulation` في مسار يتوفّر فيه PCSE · ② **QUEFTS يتبع PCSE** في الهرم (لا يُعايَر مستقلّاً؛ مسار التسميد يقرأ مخرجات WOFOST — توصية الأدبيّات، `sahool-brain/research/open_season_simulation_models_survey_20260720.md`).
  - **الحالة:** الاتّجاه **معتمد مسبقاً وموثَّق**؛ يبقى القيد OPEN حتى **المصادقة الرسميّة + البراهين** في مواصفة SIM-GOLDEN-01 (تصبح: مصادقة + براهين، لا نقاش من الصفر). المحفّز: أوّل موسم مؤهَّل للمعايرة (SEASON-ENTRY-EVENTS-UI فتح المسار).

## MINIO-PER-SERVICE-CREDENTIALS — ACCEPTED_RISK (2026-07-23، تصويب تصنيف المالك) — كان OPEN (Low/follow-up)، سُجِّل مع SEASON-RECORD-ENTRY-01 (شريحة 2)
- **الملاحظة (رفعها المراجع الرئيسيّ أثناء مراجعة تصميم الشريحة 2 / `blob_store`):** MinIO مشترك بمفتاح `sahool-admin` واحد عبر المنصّة (raster/decision/scout-ingest…). أيّ خدمة تحمل المفتاح تقرأ بادئات الآخرين، بما فيها `season-logbooks/` (دفاتر المواسم). عزل المفاتيح على مستوى الخدمة غير موجود بعد.
- **لماذا مقبول الآن:** نموذج تهديد داخليّ + شبكة docker معزولة + `season-logbooks/<tenant>/<season_id>/` مُشتقّ خادميّاً (لا يختار العميل المسار) + المرجع الداخليّ لا يُسرَّب (presigned ≤300ث). المخاطرة = خدمة داخليّة مُخترَقة تقرأ بادئة أخرى، لا عميل خارجيّ.
- **القالب عند التصليب:** سابقة B1.2 (per-source credentials عبر `resolve_ingest_source`، لا توكن مشترك) هي القالب — مفاتيح/سياسات MinIO لكلّ خدمة (bucket-policy أو IAM users مُنفصلة) بدل `sahool-admin` الواحد. **المحفّز:** أوّل بيانات حسّاسة تتطلّب عزلاً تنظيميّاً، أو تصلّب أمنيّ مُخطَّط.
- **المصدر:** `shared/storage/blob_store.py` (يقرأ `S3_*` المشترك) · `docker-compose.v9.yml` (`S3_ACCESS_KEY:-sahool-admin`) · سابقة `migrations/bootstrap_postgres.sh` §٥.٢ (per-source). **الحالة:** **ACCEPTED_RISK** — لا فعل حتى المحفّز.
- **حوكمة القبول (منعاً لإغلاق دائم غير مراقب):** مالك المخاطرة = **المالك (kafaat)** · تاريخ الاعتماد = **2026-07-23** · محفّز إعادة الفتح = **أوّل بيانات حسّاسة تتطلّب عزلاً تنظيميّاً، أو تبنّي secret-manager/IAM per-service، أو أيّ اختراق خدمة داخليّة يقرأ بادئة غيرها** · تاريخ المراجعة = **2026-10-23** (ربع سنويّ؛ يُعاد تقييم القبول أو يُرفَع للتصليب).

## HISTORICAL-SEASON-BRIDGE-01 (v207) — ✅ DELIVERED / CONFIG-COMPLETE (live-proof pending) — #605 (`bbfbf95`) 2026-07-23
- **ما سُلِّم:** جسر حوكميّ رقيق SEASON-RECORD→الموسم القانونيّ + سجلّ محاكاة قابل لإعادة الإنتاج. `migrations/v207_historical_season_simulation_bridge.sql`: `season_record_links` (immutable، trigger يفرض `season_records.trust_status='accepted'`+تطابق tenant/field) + `season_simulation_runs` (append-only). يُعلن RLS ذاتيّاً (ENABLE+FORCE+`tenant_isolation` عبر `public.sahool_effective_tenant_id()`)؛ **مُدرَج قبل v206** في MANIFEST+run_migrations كي يبقى v206 آخِراً ويُعيد تغطية catalog RLS. `core/historical_season_context.py` (جديد) + تعديلات season_simulation/season_models/agronomic_replay/seasons/decision_service_client/api.ts + 3 اختبارات. `HISTORICAL_SEASON_DECISION_CONTEXT_ENABLED=false` (default-off؛ مرآة decision-service مغلقة).
- **التسجيل (الحُرّاس التي تعيش في `tests/test_p0_*` / وظيفة Platform Unit Tests لا `-m unit`):** جدولا v207 في `db_ownership.yml` (sahool-platform) · ميزانيّة وحدات المنصّة 653→654 + `modules[]`+`historical_season_context_note` · توسيع `sahool_inspector.check_rls_coverage` ليقبل المساعد القانونيّ (غير مُضعِف؛ v206 نفسه يستعمله). **CI:** 65/65 success/skipped على `428e508` (production-validation-gate · Repo Structural Lint · Platform Unit Tests · Structure Inspector · drift/contract).
- **المصدر:** `migrations/v207_historical_season_simulation_bridge.sql` · `services/sahool-platform/core/historical_season_context.py` · `docs/architecture/db_ownership.yml` · `docs/architecture/platform_python_module_baseline.json`. **الحالة:** DELIVERED/CONFIG-COMPLETE. **معلّق بصدق (تشغيليّ لا اختباريّ):** تطبيق PG16 + برهان RLS بجلستَين على جدولَي v207 · مرآة SoR تبقى default-off حتى الشهادة. لا SoR موازٍ للموسم/المحاكاة (يتقاطع مع SIM-PATHS-DUAL — لا يُحسم إلّا في مواصفة SIM-GOLDEN-01).

## DECISION-CENTER-UNIFY-01 — تقدّم: المُحلِّل الطيفيّ الخادميّ (شريحة Composer، 2026-07-23)
- **الشريحة المُنفَّذة (CLOSED-IN-CODE):** بُعد «سلطة المدخلات» — `_compose_state` (crop_twin router) يجلب الطيف
  الحاكم (NDVI/الطيف) من raster-service خادميّاً (tenant-scoped، الواجهة القانونيّة raster_service_client)
  ويتجاوز مدخلات العميل عند تفعيل الراية `COMPOSE_SERVER_AUTHORITATIVE_SPECTRAL_ENABLED` (**default-off**، نمط سهول).
  fail-soft: فشل الجلب ⇒ طيف العميل مع علم `spectral_unverified=true` (شفافيّة، لا اختلاق سلطة). NDVI السيّد؛
  غيابه ⇒ لا سلطة خادميّة (لا خلط مصادر). 4 اختبارات وحدة + بوّابة decision-candidate 403 سليمة.
- **المتبقّي (BLOCKED-DESIGN+RUNTIME كما هو):** توسيع السلطة للطقس/التربة · **إلزام AgronomicContext الذرّيّ**
  عند التسجيل · **إثبات SoR حيّ** (يتقاطع مع PG16). submit يبقى 403 حتى اكتمال هذه الأبعاد.

## DECISION-CENTER-UNIFY-01 — الأبواب الجانبيّة مُغلقة (#610، `8243e7a`)؛ الباقي معماريّ مؤجَّل — من تحقّق مراجعة REQUEST CHANGES 2026-07-23
- **المسار 3/4/5 مُنجَز (#610، fail-closed افتراضيّاً):** (3) `/crop-twin/decision-candidate` يرفض `submit=true` (403) ما لم يُفعَّل `CROP_TWIN_DIRECT_DECISION_ENABLED` — مرشّح مبنيّ على مدخلات العميل لا يُدفَع للمركز. (4) `/crop-twin/decision`+`/profit-aware` preview/scenario فقط افتراضيّاً (الحفظ خلف نفس العلم؛ `persisted=false`+`preview_only=true`). (5) `field_intelligence.executable` لم يعد يُفتَح بـguardrails وحده — يتطلّب `FIELD_INTELLIGENCE_DIRECT_EXECUTABLE_ENABLED`، وإلّا `dispatch_block_reason=requires_decision_center` (عرضيّ فقط؛ لا تنفيذ عليه). خرّطتُ الاستخدام بوكيلَين قبل التنفيذ (لا واجهة تقرأ persisted/submit/executable). علمان موثَّقان في `.env.example`. 64/64 CI أخضر على `969dfc9`. **⇒ المسارات المتوازية مُغلقة؛ المركز هو المالك الوحيد افتراضيّاً.**
- **المتبقّي — التصنيف: BLOCKED-DESIGN+RUNTIME (تصويب المالك 2026-07-23).** ليس محجوباً على PG16 وحده: **Composer خادميّ** يجلب `Canonical*State`/`SoilProfileSnapshot`/طيف موثَّق (لا مدخلات عميل في المسار الحاكم) + **إلزام AgronomicContext/History/FeatureManifest ذرّياً** عند تسجيل المرشّح = **عمل معماريّ غير منفَّذ** (تصميم+كود جديد، لا مجرد بنية حيّة). ثمّ **إثبات SoR حيّ** = الجزء الوحيد المتقاطع مع PG16/DECISION-SOR-CUTOVER. أي: تصميم+تنفيذ معماريّ أوّلاً، ثمّ إثبات تشغيليّ — لا يُغلَق بـPG16 فقط.

## DECISION-CENTER-UNIFY-01 (المدخل الأصليّ) — من تحقّق مراجعة REQUEST CHANGES 2026-07-23
- **الملاحظة (مراجعة توصيل المحرّكات↔مركز القرار عند `9a218c7`، تحقّقتُ منها بأربعة وكلاء عدائيّين — الادّعاءات 11 كلّها CONFIRMED بأدلّة `file:line`):** المركز قويّ كبنية وبوّاباته fail-closed سليمة، لكنّ **مسارات قرار متوازية تلتفّ حول البوّابة القانونيّة للمرشّح**: (١) `/crop-twin/decision` و(٢) `/profit-aware` يبنيان `unified_decision` ويكتبانه في `decision_record` المنصّة بـ`"authoritative_store":"sahool-platform"` (استشاريّ لا قابل للتنفيذ)، (٣) `run_field_intelligence.executable` يُفتح بـ`actionable AND guardrails∈approved` وحده (`coordinator.py:330-331`) دون سجلّ موافقة/مراجِع/خطّة تنفيذ. كذلك المرشّح مبنيّ على **مدخلات العميل** (ET0/NDVI/تربة/طيف عبر `CropTwinComposeRequest` `routers/crop_twin.py:70-85`)؛ الجلب الخادميّ الوحيد `get_gdd_product` (`:136`)؛ `_compose_state` لا يمرّر `weather_state` ⇒ heat/frost ميّتان + `crop_water=unavailable`؛ لا SoilProfileSnapshot/CanonicalWaterState/طيف موثَّق؛ field/season بلا تحقّق دلاليّ (`crop_decision_bridge.py:79-82`)؛ ازدواج `CanonicalFieldState` (3 تعريفات صنف + ≥6 مسارات تركيب، فقط `FieldTwin` مُعلَّم DERIVED_VIEW).
- **الفعل المقترَح (قابل للتنفيذ الآن بلا migration — المسار 3/4/5 من ترتيب المراجعة):** منع `submit=true` على `/compose` (مدخلات عميل ⇒ preview فقط) · تحويل `/crop-twin/decision` و`/profit-aware` إلى preview/scenario · منع `field_intelligence.executable` من تجاوز مركز القرار. ثمّ (معماريّ أكبر) Composer خادميّ يجلب `Canonical*State`/`SoilProfileSnapshot`/طيف موثَّق + جعل AgronomicContext/History/FeatureManifest شرطاً ذرّياً + إثبات SoR حيّ.
- **المصدر:** `services/sahool-platform/api/routers/crop_twin.py` · `api/crop_decision_bridge.py` · `api/unified_decision.py` · `core/field_intelligence_coordinator.py` · `core/field_intelligence_adapters.py` · `services/decision-service/{main,persistence}.py`. **الحالة:** PROPOSED (High) — **لا لمس حتى قرار المالك الصريح على هذا البند** (احترام منع التجريد المبكّر؛ الحكم: أؤيّد حجب الاعتماد الإنتاجيّ على المركز حتى الإغلاق).

## DECISION-SOR-CUTOVER-WIRING-01 — OPEN_P0 / BLOCKED_ON_DB_ROLE_TOPOLOGY_VERIFICATION — من تحقّق مراجعة تحويل SoR القرار 2026-07-23
> **تصويب صدق حاسم (المالك 2026-07-25):** أداة الـREVOKE (`platform_sor_revoke.py` @ `3ebd618`) **تفترض** فصل الأدوار لكنّها **لا تُثبته**. تحقّقٌ مباشر: المنصّة تتّصل بدور `sahool_app` (compose افتراض `DATABASE_URL`)، لكنّ `DECISION_SERVICE_DATABASE_URL` **فارغ افتراضاً** ودور decision-service **يورَّده المشغّل عند التحويل — غير معرَّف في المستودع** (`.env.example:322-325`). ⇒ **فصل الاتّصال المنطقيّ: مؤكَّد · فصل دور القاعدة: غير مُثبَت.** لو كان الدوران نفسه، الـREVOKE يحجب الخدمتَين. **precursor إلزاميّ قبل أيّ REVOKE:** `DECISION-SOR-PRE-CUTOVER-ROLE-CERTIFICATION` — مصفوفة حيّة (`current_user`/`session_user` عبر اتّصالَي المنصّة/الخدمة · مالك الجدول · grants الجداول+sequences+functions من `information_schema.role_table_grants` · role memberships · `rolsuper`/`rolbypassrls` · توفّر `SET ROLE`). **تحذير ملكيّة:** مالك الجدول في PostgreSQL يحتفظ بسلطة قويّة حتى بعد REVOKE — الأصلب: `table owner = decision_schema_owner` (NOLOGIN) · `sahool_app`=SELECT فقط · `decision_service_app`=DML، لا أن يبقى `sahool_app` مالكاً مع REVOKE. الاختبار الحاليّ (دور probe واحد) **ضعيف**: يجب دورَين متمايزَين (platform_test + decision_service_test، كلاهما NOSUPERUSER/NOBYPASSRLS) + فحص catalog (لا سلوك فقط) + sequences + functions (SECURITY DEFINER) + ownership + `SET ROLE` غير متاح للمنصّة + فشل المنصّة = `InsufficientPrivilegeError` لا Python guard.
- **الشريحة 1 (#607، `d0dc527`):** فُكّ يُتم العقد. `api/decision_sor_mode.py`: `DECISION_SOR_TABLES` (متطابق مع `cutover._REQUIRED_TABLES`) + `PlatformDecisionWriteForbidden` + `assert_platform_may_write_decision_sor(table)` (no-op في `platform_sor`/`shadow`؛ يرفع بعد التحويل). وُصِّل قبل كتابة صفوف SoR في مسارات HTTP: `decision_record`(×2)+`outcome_record` · `weather` · `decision_dispatch`(INSERT) · `recommendations`. 64/64 CI أخضر على `d4cc79b`.
- **الشريحة 2 (#608، `55ff805`):** اكتمال طبقة التطبيق — تحديثا حالة `dispatch_decisions` (مستهلك الطابور + نتيجة التنفيذ) + كتابة العامل `online_learning_updates` (phase_runtime_store). `decision_outbox_events` **ليست مكتوبة من المنصّة** (decision-service يملك outbox الخاصّ) ⇒ لا شيء يُحرَس. الحارس الساكن الآن يؤكّد **كلّ** كتابة SoR في المنصّة مسبوقة بالحارس. 64/64 CI أخضر على `4a5b91b`. **⇒ كلّ كتّاب SoR على مستوى التطبيق محروسون fail-closed الآن.**
- **أداة الـREVOKE أُنجِزت + بُرهِنت على PG حقيقيّ (`3ebd618` 2026-07-25):** `services/decision-service/platform_sor_revoke.py` (+ غلاف `scripts/deploy/decision_sor_platform_revoke.sh`) — REVOKE/GRANT عكسيّ لـINSERT/UPDATE/DELETE (يُبقي SELECT) على الجداول الخمسة platform-owned فقط (يستثني `decision_outbox_events` المملوك لـdecision-service). fail-closed: `--revoke` يتطلّب `DECISION_SERVICE_PRODUCTION_CUTOVER_APPROVED=true`+`DECISION_SOR_ALLOW_PLATFORM_REVOKE=true`؛ `--grant` (تراجُع، خطوة `rollback.py` الجديدة 3) يتطلّب `DECISION_SERVICE_ROLLBACK_APPROVED`. **ليست migration** (خارج `migrations/` كي لا تُطبَّق قبل التحويل). same-DB فقط (no-op في split-DB). برهان سلوكيّ على PG حقيقيّ في وظيفة Decision Service Tests (المنصّة تُمنَع الكتابة وتحتفظ بـSELECT بعد الـrevoke، تُستعاد بالـgrant) + حارس ساكن `tests_v9/test_decision_sor_platform_revoke_static.py` (unit). الرنبوك اكتسب قسم الـREVOKE.
- **المتبقّي (محجوب على بنية حيّة — تشغيليّ لا كوديّ):** **تطبيق** الـREVOKE أثناء التحويل الفعليّ على PG16 حيّ (خطوة المالك 5؛ الأداة جاهزة لكنّ الـcutover نفسه لم يقع) · إلزام السياق الزراعيّ للقرار القابل للتنفيذ · إغلاق المنطقة الميّتة قبل التحويل. `phase_runtime_store` (~40 جدول ML/marketplace) تُرِك سليماً — ليست SoR قرار.

## DECISION-SOR-CUTOVER-WIRING-01 (المدخل الأصليّ) — PROPOSED، من تحقّق مراجعة تحويل SoR القرار 2026-07-23
- **الملاحظة (تحقّقتُ منها مباشرةً على `9a218c7`+فرع #606):** العقد المركزيّ `services/sahool-platform/api/decision_sor_mode.py::get_platform_decision_sor_mode()` (3 أوضاع `platform_sor`/`shadow`/`decision_service_sor` + 6 بوّابات fail-closed + `platform_writes_required`) **يتيم**: مُستدعِيه الوحيد اختبار `tests/test_p0_3_decision_sor_shadow_promotion_guard.py` — **صفر كتّاب إنتاجيّين** يستشيرونه (grep مؤكَّد). الكتّاب الخمسة يكتبون مباشرةً بلا فحص الوضع: `routers/decision_record.py` (3 INSERT/UPDATE) · `routers/weather.py` (4) · `routers/decision_dispatch.py` (6) · `routers/recommendations.py` (2) · `phase_runtime_store.py` (48). ⇒ في وضع `decision_service_sor` ستستمرّ المنصّة بالكتابة المباشرة ⇒ **ازدواج/اختلاف SoR**. والأخطر: الحارس `test_p0_3...:122-125` يؤكّد `"INSERT INTO decision_record" in text` صراحةً — الاختبارات **تُثبِّت** الكتابة المباشرة، فالأخضر يوثّق الوضع الانتقاليّ لا سلامة التحويل.
- **فجوات مرافقة مؤكَّدة:** (P0-B منطقة ميّتة) `DECISION_SERVICE_SOR_ENABLED=false` افتراضاً + طابور المراجعة/الاعتماد في decision-service فقط (`decision_review` يردّ 503 خارج SoR) ⇒ مرشّح مخزَّن بالمنصّة بلا مسار اعتماد كامل قبل التحويل؛ الجسور (`crop_decision_bridge`/`water_decision_bridge`) تتطلّب `persisted&&authoritative` فتفشل افتراضاً (water bridge default-off ⇒ الخطر مضبوط الآن). (P1) `DECISION_REQUIRE_AGRONOMIC_CONTEXT=false` (`decision-service/main.py:541`) ⇒ السياق الزراعيّ اختياريّ حتى للقرارات القابلة للتنفيذ. (P1) **لا حارس DB يسحب صلاحيّة الكتابة من دور المنصّة بعد التحويل** — علم البيئة وحده (grep لم يجد REVOKE على جداول القرار).
- **الخطّة (خطوات المالك العشر، مُختصَرة):** توصيل `get_platform_decision_sor_mode()` بالكتّاب الخمسة (fail-closed: يرفض الكتابة حين `platform_writes_required=False`؛ **محايد في الوضع الافتراضيّ platform_sor**) · حارس DB يُسقِط صلاحيّة كتابة المنصّة بعد التحويل · منع تفعيل مرشّحين بينما المراجعة غير authoritative · إلزام السياق الزراعيّ للقرار القابل للتنفيذ · اختبارات PG حيّة للتحويل/العودة (لا static فقط).
- **تصويب صدق على المراجعة:** ادّعاؤها «المؤشرات تقرأ من raster_assets بدل الجدول القديم» **غير صحيح بعد** — sim/replay ما زالا يقرآن `ndvi_timeseries` (المنصّة، بلا بروفيننس)؛ إعادة التوجيه لا تزال شريحة معلّقة (#1). كذلك `sim_run_id`+`rue-fao56` على فرع #606 لا على `main` بعد.
- **المصدر:** `services/sahool-platform/api/decision_sor_mode.py` · `routers/{decision_record,weather,decision_dispatch,recommendations}.py` · `phase_runtime_store.py` · `tests/test_p0_3_decision_sor_shadow_promotion_guard.py` · `services/decision-service/main.py:541`. **الحالة:** OPEN (P0) — **لا لمس حتى قرار المالك على السلسلة** (كبيرة/مرحليّة، تحقّق كامل يحتاج PG حيّاً). الوضع الافتراضيّ الحاليّ (`platform_sor` fail-closed) آمن؛ **أؤيّد توصية المالك: لا تفعيل decision-service كـSoR إنتاجيّ قبل توصيل الحارس بكلّ الكتّاب + إسقاط صلاحيّات المنصّة.**

## RUFF-FORMAT-DRIFT-SHARED — ✅ FIXED (2026-07-23) — كان OPEN (Low/housekeeping) من فحص نطاق-CI الموسّع 2026-07-19
- **الإغلاق (2026-07-23، التزام تنسيق جماعيّ مستقلّ كما نصّت القاعدة):** `ruff format shared/` (35 ملفًّا) + `ruff check shared/ --fix` (95/103 آليًّا: I001/UP017/F401/UP035) + إصلاح الثمانية المتبقّية يدويًّا (E402 ⇒ `# noqa`، B007 `idx`⇒`_idx`، B905 `zip(...,strict=False)` محافِظ على السلوك). **شُدِّدت البوّابة:** `ci.yml` وسّع **كلا** خطوتَي `ruff check` و`ruff format --check` لتشمل `shared/` (منع تكرار الانجراف — سقّاطة ذاتيّة). أمان إعادة التصدير: `ruff.toml` يحمل `"**/__init__.py" = ["F401"]` ⇒ لم تُمسّ أيّ إعادة تصدير (الـ`__init__` diffs سطر-فارغ فقط، الوحدات الأربع تستورد بـ`__all__` سليم 5/5/6/76). التحقّق: `-m unit` 3400 · اختبارات shared 229 · bundle 4795.
- **الملاحظة:** `ruff format --check` على النطاق الموسّع (`shared/` مضمَّناً) يُبلِّغ ~36 ملفًّا «would reformat» (مثل `shared/test_marketplace_ecosystem_phase12.py`) — **انجراف تنسيق قديم على main** (غالباً اختلاف نسخة ruff بين بيئات)، سابق لهذه الجلسة ولا علاقة له بأيّ شريحة.
- **لا يحجب:** بوّابة CI للتنسيق مقصورة على `services/ bots/ agents/ tests_v9/` (أخضر: 2203 ملفّ مُنسَّق) — `shared/` خارج النطاق المحجوب. ملفّات الشرائح (`shared/storage/*`, `season_api.py`, tests) نظيفة.
- **القاعدة المُطبَّقة (منعاً للتكرار):** لا يُدخَل إصلاح 36 ملفًّا غريباً في التزام شريحة (تضخيم نطاق). يُعالَج في **التزام تنسيق جماعيّ مستقلّ** بعنوان صريح لاحقاً.
- **المصدر:** `ruff format --check services/ bots/ agents/ tests_v9/ shared/` (2026-07-19). **الحالة:** OPEN — housekeeping، لا فعل الآن.

## SHARED-PACKAGE-NAME-COLLISION — ACCEPTED_RISK / WONTFIX (2026-07-23، تصويب تصنيف المالك) — كان OPEN (Low/refactor) من فشل CI الترتيبيّ 2026-07-19
- **الملاحظة:** حزمتان بالاسم `shared` في المستودع: **جذر المستودع** `shared/` (الكاملة، فيها security/storage/…) و**`services/mcp_servers/shared/`** (جزئيّة: oauth_middleware/streamable_http فقط، **بلا storage**). في عامل pytest واحد متقاسم sys.path (وxdist يوازي عمّالاً)، اختبار MCP يحقن مسار mcp_servers ويربط `shared` على النسخة الجزئيّة ⇒ اختبار لاحق يستورد `shared.storage` يفشل **حسب ترتيب التشغيل** (لاحتمائيّ = أخطر: إعادة التشغيل قد تخفيه).
- **الإصلاح المُطبَّق (شريحة 2):** الحُرّاس التي تستورد `shared.*` عالية-الاصطدام تُحمَّل عبر **المسار المطلق** (`importlib.util.spec_from_file_location`، نمط aquacrop/rs-anomaly) — مناعة تامّة ضدّ التظليل بصرف النظر عن ترتيب xdist. + `pythonpath = .` في pytest.ini + برهان ترتيبيّ (`test_blob_store_immune_to_shared_package_shadow`). **تحقّق:** كامل `-m unit` مع fastapi محجوبة ⇒ صفر فشل مواسم (كان 6).
- **الحلّ النهائيّ (مؤجَّل، refactor أوسع):** إعادة تسمية `services/mcp_servers/shared` → `mcp_shared` (أو حزمة namespace مؤهَّلة) ليزول التصادم من جذوره. **المحفّز:** أوّل عمل جوهريّ على mcp_servers. حتّى ذلك: أيّ حارس جديد يستورد `shared.*` يُحمَّل عبر المسار المطلق (قاعدة مراجعة).
- **المصدر:** `services/mcp_servers/shared/` · `tests_v9/test_mcp_functional.py:78-102,148-167` (يُنظّف ذاتيّاً) · `tests_v9/test_season_api_static.py` (نمط المناعة). **الحالة:** **ACCEPTED_RISK / WONTFIX** (بأمر المالك 2026-07-23) — **ليس بنداً ينتظر التنفيذ.** الحماية القائمة كافية ونهائيّة كموقف: (١) كلّ حارس يستورد `shared.*` يُحمَّل عبر المسار المطلق (`spec_from_file_location`) فيُمنَّع من التظليل بصرف النظر عن ترتيب xdist · (٢) `pythonpath = .` في pytest.ini · (٣) برهان مناعة ترتيبيّ `test_blob_store_immune_to_shared_package_shadow`. إعادة التسمية (`mcp_shared`) **gold-plating**: تلمس مسارات استيراد عبر الشجرة (خطر انحدار حقيقيّ) مقابل قيمة صفريّة فوق المناعة القائمة — يخالف «لا نصف حلّ/لا تذهيب». **قاعدة مُبقاة:** أيّ حارس جديد يستورد `shared.*` يُحمَّل بالمسار المطلق. لا يُعاد فتحه إلّا إن كسرت المناعة فعلاً.
- **حوكمة القبول (منعاً لإغلاق دائم غير مراقب):** مالك المخاطرة = **المالك (kafaat)** · تاريخ الاعتماد = **2026-07-23** · محفّز إعادة الفتح = **أوّل عمل جوهريّ على `services/mcp_servers/` (يبرّر إعادة التسمية `mcp_shared`)، أو أيّ كسر فعليّ للمناعة (فشل `test_blob_store_immune_to_shared_package_shadow` أو تظليل `shared.storage` في تشغيل xdist)** · تاريخ المراجعة = **2026-10-23** (ربع سنويّ؛ يُعاد تقييم القبول).

## SEASON-REVIEWER-GRANT-MODEL — OPEN (Medium/deferred) — قرار الشريحة 3b 2026-07-19
- **الوضع الحاليّ (الشريحة 3b):** سلطة `season-reviewer` **مُشتقّة** من دور auth المفرد (RBAC): `season_reviewer_roles_for` يمنحها لـ**{owner, expert} فقط** — القبول فعل زراعيّ لا تشغيليّ. **admin مستثنى عمداً** (تشغيليّ: مستخدمون/إعدادات؛ إدخاله = مدير نظام بلا خلفية زراعية يصدّق غلالاً تدخل معايرة علمية). farmer/viewer خارج. الاشتقاق مُعلَن في `shared/security/trusted_tenant.py:SEASON_REVIEWER_SOURCE_ROLES` بتوثيق الاستثناء بجانبه (الاستثناء المدوَّن أهمّ من الاشتقاق — هو ما يسأل عنه قارئ مستقبليّ). برهان لكلّ دور (`test_reviewer_authority_owner_and_expert_only`): owner/expert يمرّان · admin/farmer/viewer ⇒ 403.
- **النموذج النهائيّ (مؤجَّل، شريحة قائمة بذاتها):** مطالبة `roles` متعدّدة قابلة للمنح لكلّ مستأجِر (هجرة role-grants + claim في JWT + مسار/واجهة منح من مدير المستأجِر، §5-2 حرفيّاً) — يزيل الاشتقاق من الدور المفرد.
- **المحفّز الصريح:** **أوّل حاجة لمُراجِع ليس مالكًا ولا خبيرًا** — مثلاً مُدقّق خارجيّ لموسم تصدير، أو مُراجِع مفوَّض من تعاونيّة. عندها يُبنى نموذج المنح الكامل بدل توسيع قائمة الاشتقاق (الذي يُبقي «الصلاحية التشغيلية = السلطة الزراعية» خلطاً مرفوضاً).
- **المصدر:** `shared/security/trusted_tenant.py:SEASON_REVIEWER_SOURCE_ROLES` · `services/auth/main.py` (single-role RBAC: owner/admin/expert/farmer/viewer، X-User-Role مفرد). **الحالة:** OPEN — الاشتقاق الضيّق يكفي المرحلة.

## SEASON-EDGE-LIVE-PROOF — ✅ CLOSED (مرصود حيّاً على staging) — 2026-07-20
- **الإقفال:** البراهين الثلاثة رُصِدت **خضراء على staging** عبر `scripts/e2e/season_gateway_live_gate.py` (المالك، فرع البناء `claude/code-review-34hO3`): (أ) ترويسات مزوَّرة بلا جلسة ⇒ deny · (ب) مُراجِع شرعيّ ⇒ 200 · (ج) إعادة قبول ⇒ 409. «ALL PROOFS PASSED ✅». المهمّة #225 مُغلَقة. حدّ الثقة الإنتاجيّ (تجريد nginx + تصديق مقيَّد الوجهة) مُثبَت حيّاً لا تصميميّاً فقط.

- **الملاحظة:** البرهان السلبيّ الثالث لبوّابة القبول (شرط المالك ③) — **ترويسة `X-Canonical-Path` مزوَّرة من عميل لا تصل auth** — لا يمكن إثباته بوحدة؛ يتطلّب nginx حيًّا يعمل (تجريد الترويسة سلوك تشغيليّ لا نصّيّ). أُثبِت **تصميميّاً** بحارس ساكن (`test_season_gateway_nginx_static.py`: البوّابة تكتب X-Canonical-* بنفسها فتَطمِس المزوَّرة) لكن **السلوك الحيّ مؤجَّل**.
- **الإثبات المؤجَّل (عند أوّل إقلاع stack كامل، بجانب irr_f01 PROD-01→07):** (أ) قبول بترويسة X-Canonical/هويّة/تصديق مزوَّرة من عميل ⇒ **401/deny** (المزوَّرة جُرِّدت) · (ب) مُراجِع owner/expert يقبل موسمه ⇒ 200 · (ج) إعادة القبول ⇒ 409. البرهان المكمّل: تصديق مسار عامّ لا يُقبَل على القبول (تقيّد الطرفين بالداخليّ).
- **الرَّنبوك القابل للنسخ:** [`sahool-brain/runbooks/season-record-entry.md`](../runbooks/season-record-entry.md) §3 (أوامر curl جاهزة). المهمّة المرقّمة: #225.
- **المصدر:** `nginx/nginx.v9.conf` (مواقع المواسم) · `services/auth/routers/season_edge_sign.py` · `services/scout-ingest-service/season_api.py:accept_season`. **الحالة:** OPEN — يُقفَل فور رصد (أ/ب/ج) على staging أخضر.

## SEASON-ENTRY-EVENTS-UI — CLOSED (`7419b13`) — بُنِيت 2026-07-20
- **الملاحظة (الأصل):** واجهة 3c رقّمت الموسم عبر الستّ النقاط فقط؛ جداول `season_events`/`season_harvest`/`season_cost_items` (v201) كانت **بلا API** — فلم تُبنَ نماذجها (لا نصف حلّ).
- **الإغلاق (`7419b13`):** أربع نقاط أبناء على scout-ingest (POST events/harvest/costs + GET detail، الستّ ⇒ عشر) — untrusted فقط (409 بعد القبول، trigger + نقطة) · low_confidence تلقائيّ للنوع الكمّيّ بلا شاهد (قاعدة ٤) · قيود energy/machinery/currency/harvest>sowing مفروضة (⇒ 400) · `detail` يقرأ `calibration_eligible` من الـVIEW المُشتقّ (مصدر قاعدة واحد). ثلاث خطوات واجهة (أحداث/حصاد/تكاليف اختياريّة) + تلميح «مؤهَّل للمعايرة» في المراجعة. **برهان حيّ PG16:** calibration_eligible يقلب FALSE→TRUE عند القبول (SIM-GOLDEN مفتوح).
- **درس (برهان حيّ يمسك ما لا تمسكه الوحدة):** `sahool_ingest` كان يفتقر SELECT على الـVIEW ⇒ `detail` 503 — **فجوة منح إنتاجيّة حقيقيّة** لا يكشفها اختبار وحدة؛ أُصلِحت `GRANT SELECT ON season_calibration_eligibility` في المُشغّلَين (bootstrap + apply).
- **المصدر:** `services/scout-ingest-service/season_api.py` (10 نقاط) · `SeasonRecordEntryPage.tsx` · `services/api/season.ts` · `test_season_live.py` (البرهان). **الأثر على SIM-GOLDEN:** الجسر مكتمل — SEASON-RECORD يجمع الحصاد المؤهَّل؛ SIM-PATHS-DUAL يبقى OPEN (أيّ محرّك يُعايَر ضدّه يُحسَم عند SIM-GOLDEN-01).

## SEASON-CONFORMANCE-AUDIT — تدقيق مطابقة SEASON-RECORD-01 (spec↔مبنى) 2026-07-20
تدقيق المالك للمواصفة المعتمدة ↔ المبنيّ (v201، أخضر) وجد **فجوة صلابة واحدة** في مخطّط بهذا الحجم:
- **① قيد النزاهة 2 (بذار ضمن نطاق المشاهدة) كان تطبيقيّاً فقط — أُغلِق DB-level (`v203`):** المواصفة §قيود-النزاهة صرّحت «DB-level، لا تطبيقيّة فقط»؛ v201 فرضته في الواجهة فقط (`SeasonRecordEntryPage:270`) — الواجهة عميل مؤدّب لا حارس، فمستدعٍ مباشر يتجاوزها. **`v203`** يفرضه بـtrigger `season_crop_sowing_in_observed_range` (يعبر جدولين، نمط `season_harvest_after_sowing`)؛ الرسالة تذكر النطاق الفعليّ (حارس لا عائق). برهان حيّ PG16 (بذار خارج النطاق ⇒ 400، لا موسم يُنشأ) + حارس ساكن. **الحالة: CLOSED.**

## SEASON-QUARANTINE-FLOW — انحراف مقبول موثَّق (لا فجوة) — قرار المالك 2026-07-20
- **قيمة `quarantined` محجوزة للمصادر الخارجيّة غير المتزامنة مستقبلاً؛ الترقيم الورقيّ يرفض مبكّراً (400) + `low_confidence` — انحراف عن §3 الأصليّ، مقبول 2026-07-20 بمبرّر التزامن.**
- **قواعد 4ب/4ج (طاقة/معدّات ناقصة) تبقى سارية كرفض مبكّر — لم تُفقَد، تغيّرت آليتها فقط** (CHECK ⇒ 400 بدل quarantine).
- **القاعدة العامّة المُعلَنة:** الرفض المبكّر للمصدر **المتزامن** (مُدخِل بشريّ حاضر يقدر على الإصلاح فوراً)، الحجر (`quarantined`) للمصدر **غير المتزامن** (B1: ODK/Kobo — البيانات تصل من جهة لا تُردّ لحظيّاً). quarantine في جلسة متزامنة كان سينتج كومة بيانات سيّئة مخزَّنة تنتظر مراجعة قد لا تأتي.
- **المصدر:** `services/scout-ingest-service/season_api.py` (رفض مبكّر) · `migrations/v201_season_records.sql` (enum يبقي `quarantined` للمستقبل غير المتزامن). **الحالة:** انحراف مقبول موثَّق — لا فعل.

## CODE-CLOSABLE-DEFERRED-SWEEP — تسوية تصنيفات (بأمر المالك 2026-07-23) — بعد دمج #616 (`main`=38ed755)
- **الحكم (جرد عدائيّ + تحقّق المالك):** **صفر بنود قابلة للإغلاق من الكود وحده الآن** دون خرق «لا نصف حلّ» أو الصدق. آخر بند كوديّ نظيف (RUFF-FORMAT-DRIFT-SHARED) أُغلق فعلاً (#603). **العمل الكوديّ العامّ مُجمَّد بقرار المالك؛** لا يُصنَّع بند ولا يُنصَّف إغلاق. **لا يُعلَن السجلّ «خاليًا من الفجوات الكوديّة» — بل مُصنَّفاً بوضوح.**
- **تصنيف المُحجِّبات (دقيق، لا خلط):**
  - **BLOCKED-OPERATIONAL (PG16 حيّ + قرار تحويل):** `DECISION-SOR-CUTOVER-WIRING-01` (**OPEN_P0 / BLOCKED_ON_DB_ROLE_TOPOLOGY_VERIFICATION — أداة REVOKE @ `3ebd618` موجودة لكنّ فصل دور القاعدة غير مُثبَت؛ precursor: `DECISION-SOR-PRE-CUTOVER-ROLE-CERTIFICATION`**) · `DEPLOYED-DECISION-SOR-PROMOTION` (تطبيق+backfill+قلب ملكيّة) · `SEASON-EDGE-LIVE-PROOF` (برهان nginx حيّ) · `BRANCH-GRAVEYARD-POLICY` (حذف ref، 403 مشغّل).
  - **DECISION-SOR-PRE-CUTOVER-ROLE-CERTIFICATION — TOOL_PROVEN / LIVE_RUN_PENDING (precursor لـcutover):** أداة قراءة-فقط تُنتج المصفوفة الحيّة (اتّصال/current_user/session_user/مالك الجدول/grants الجداول+sequences+functions/role memberships/rolsuper/rolbypassrls/SET ROLE) قبل أيّ REVOKE. **verdict الأداة مُبرهَن على PG حقيقيّ في CI** (`test_decision_sor_role_certify_pg.py`: دورَان متمايزان ⇒ `role_separation_confirmed=true` + current_users صحيحة + مالك الجدول + attributes؛ دور مشترك ⇒ `false` = «لا REVOKE»). **المتبقّي تشغيليّ:** تشغيلها على staging/prod الحيّ بالاتّصالَين الفعليَّين. دوران مستقلّان ⇒ promotion/rollback مباشرة؛ دوران مشتركان ⇒ إنشاء `decision_service_app` + نقل اتّصال decision-service + إثبات + ثمّ REVOKE.
  - **BLOCKED-GOVERNANCE/TRIGGER (قرار هويّة/حوكمة أو محفّز لم يقع):** `WORKER-IDENTITY-BINDING` (**OPEN_HIGH / TARGET_DESIGN_SIGNED_WORKER_ASSERTION — الحلقة المشتركة (bearer) أُغلقت في الإنتاج @ `9330407`؛ يبقى مفتاح/هويّة لكلّ عامل — قرار بنية تحتيّة**) · `FIELD-SVC-TENANT-HEADER-TRUST`/ADR-0033 (**CLOSED_IN_CODE / LIVE_CONFIG_AND_REPLAY_E2E_PENDING — الخيار A مفروض ومقفول-عند-الفشل بـ`main.py:90-152`؛ لا يُرفَع إلى VERIFIED بلا تحقّق سلوكيّ+config حيّ**) · `SEASON-REVIEWER-GRANT-MODEL` (محفّز أوّل مراجِع غير owner/expert).
  - **BLOCKED-SPEC+DATA:** `SIM-PATHS-DUAL` (مواصفة SIM-GOLDEN-01 + بيانات مواسم مؤهَّلة حقيقيّة؛ الاتّجاه معتمد مسبقاً، الحسم مصادقة لا نقاش).
  - **BLOCKED-DESIGN+RUNTIME (عمل معماريّ غير منفَّذ، ليس PG16 وحده):** `DECISION-CENTER-UNIFY-01` المتبقّي (Composer خادميّ + إلزام AgronomicContext ذرّيّ = تصميم+كود جديد؛ إثبات SoR حيّ = الجزء الوحيد المتقاطع مع PG16).
  - **ACCEPTED_RISK / WONTFIX:** `SHARED-PACKAGE-NAME-COLLISION` (المناعة القائمة كافية ونهائيّة؛ إعادة التسمية تذهيب بخطر انحدار) · `MINIO-PER-SERVICE-CREDENTIALS` (اصطلاح مشترك مقبول؛ يحتاج IAM/سياسة-دلو لكلّ خدمة = مشغّل).
- **تصنيف نتيجة جرد المستهلكين (بلا اختراع مستهلك — أدلّة `file:line`):**
  - **agriai-engine** — UNCONSUMED-INTENTIONAL (internal, route-ready). خدمة حقيقيّة مصلَّبة (17 py، evidence bundle/PCSE/profit-planner). مسار بوّابة داخليّ `nginx/nginx.v9.conf:452 location /api/agriai/` (`deny all` عامّ، شبكات خاصّة فقط) + خدمة compose (`docker-compose.v9.yml:147`)، **لكن صفر مُنادٍ فعليّ** في `services/`/`frontend/` (grep لـ`/api/agriai/`+`agriai_backend` = فارغ). ⇒ جاهزة للتوصيل داخليّاً، بلا مستهلك مُؤكَّد بعد. **لا مستهلك مُختلَق.**
  - **remote-sensing-workspace-bff** — UNCONSUMED-INTENTIONAL (future BFF). `services/remote-sensing-workspace-bff/main.py:1` docstring «RS-9 single aggregation point for the remote-sensing field workspace»؛ خدمة compose (`:1017`)، **بلا مسار nginx ولا مستهلك frontend/كود**. ⇒ نقطة تجميع BFF تنتظر واجهتها + مسار البوّابة.
  - **gis-workflow-service** — INTERNAL/FUTURE (undeployed). موجودة (20 py) بـبوّابة CI مخصّصة (`.github/workflows/gis-workflow-service-gates.yml`) + اختبارات (print-map · v200 admin boundaries) + `db_ownership.yml` + مُحمِّل لمرّة-واحدة `load_admin_boundaries.py`؛ **غير موجودة في `docker-compose.v9.yml` (0) ولا في nginx**. ⇒ أداة داخليّة/مستقبليّة (حدود إداريّة + خرائط طباعة) بلا نشر runtime ولا مستهلك مُؤكَّد.
- **المسار المُوصى المفتوح أوّلاً (المالك): PG16 staging** — يفتح بندَي P0 ويولّد أقوى برهان تشغيليّ. التسلسل: (1) تطبيق الهجرات + تحقّق RLS بالدور المقيَّد · (2) backfill + فحوص اكتمال/مقارنة · (3) canary/read-side comparison · (4) قرار تحويل بشريّ · (5) قلب الملكيّة ثمّ REVOKE كتابة المنصّة · (6) إثبات rollback + health/audit على SHA نفسه. **السرّ (DSN/كلمة المرور) لا يُرسَل في المحادثة — متغيّر بيئة/سرّ في بيئة التنفيذ.**
- **موقف توقيع commit:** `%G? = N` = غياب توقيع تشفيريّ (لا مفتاح توقيع في البيئة)، **ليس سبباً مشروعاً لـforce-push** على تاريخ main المدموج. لا يُعاد كتابة `38ed755` (دمج GitHub، `noreply@github.com`) ولا `69cd496` (بريدي الصحيح، غير موقَّع فقط).
- **المصدر:** جرد وكيل + تحقّق `nginx/nginx.v9.conf:452` · `services/remote-sensing-workspace-bff/main.py:1` · `services/gis-workflow-service/` (لا في compose) · `config/service_feature_ui_contracts.json`. **الحالة:** تصنيفات مُسوّاة — لا فعل كوديّ حتى فتح المالك لمسار (PG16 staging / تأكيد محفّز / قرار PKI).

## GIS-AI-INSPIRATION-TRACKS — سجلّ صادق (2026-07-23) — من مراجعة 5 مشاريع GIS+AI مفتوحة
مصدر: مراجعة Geeflow/TESSERA/AiTLAS/SemanticSeg4EO/GeoOSAM ورأي مستقلّ.
- **Track 1 (MCP فوق CDSE، إلهام Geeflow) — ✅ CLOSED-IN-CODE @ `762dd61`:** أداة MCP قراءة-فقط
  `analyze_field_change` فوق `services/mcp_servers/sentinel_hub_server.py` + منطق نقيّ
  `shared/field_change_summary.py`، تقرأ النقطة القانونيّة `GET /v1/fields/{id}/timeseries`،
  fail-closed 424، بلا حساب طيفيّ/تفسير زراعيّ. اختبار وحدة 6/6. الإثبات الحيّ (MCP+raster مرفوعان) معلّق.
- **Track 2 (TESSERA embeddings خلف v60) — BLOCKED-SPEC+DATA (مقعد موجود):** مقعد الاستبدال
  **موجود أصلاً** — `services/ai_agronomist/productivity_zones_clustering.py::kmeans_nd` يقبل متّجهات
  N-بُعد لكلّ خليّة (`_feature_vectors`/`_aligned_aux`)؛ تضمينات TESSERA 128-بُعد تُدخَل مباشرةً.
  الناقص الوحيد = **مصدر التضمين (النموذج)**: أوزان TESSERA v1.1 + بيانات pilot حيّة + عامل offline —
  غير متوفّرة داخل الحاوية؛ لا يُبنى مصدرٌ فارغ (سقالة). محفّز إعادة الفتح: توفّر أوزان v1.1 + مستأجِر pilot.
- **Track 3 (TinyCD كشف تغيير) — BLOCKED-SPEC+DATA (منطق موجود):** الشذوذ/الاتّجاه **موجود أصلاً** —
  `services/raster-service/time_series.py::build_time_series` (linear_trend + z_score). TinyCD ترقية
  تحتاج **بيانات تغيير موسومة (ground truth) + أوزان + تصدير ONNX** — غير متوفّرة/موسومة؛ لا يُبنى نموذج مُختلَق.
  محفّز: بيانات تغيير موسومة أو نموذج CD مُدرَّب مسبقاً + قناة model-registry.
- **مرفوض بدليل:** Geeflow (GEE تجاريّاً مقيَّد) · SemanticSeg4EO/GeoOSAM (إضافات QGIS، GPL — لا يُلمَس الكود، تُقتبَس الأفكار فقط) · SAM3 (رخصة غير مؤكَّدة — يُفترَض غير-Apache حتى يثبت العكس).
- **رخص مؤكَّدة:** TESSERA كود MIT/أوزان CC0 · AiTLAS Apache 2.0 · SAM/SAM2 Apache 2.0.

## RUNTIME-FUNCTIONAL-LIVE-PROOF — OPEN (blocked on blessed environment) — الطريق الوحيد لقلب runtime_verified صدقاً
- **المصدر:** `runtime-verification/service_identity_map.json` (3 خدمات/5 قدرات) · `scripts/ci/runtime_identity_bridge.py` (`--check`/`--dry-run`) · `scripts/ci/functional_probe_runner.py` (`--run`) · خطط `runtime-verification/functional_probes/{weather-service,soil-service,sahool-platform}.json`.
- **الحالة:** الجسر جاهز وخامل (#666 `479c09d` · #667 `4ac10bf` · #668 `b8ddc5f`). التغطية الوظيفيّة معلَنة: WX-004/WX-006 (weather) · SOIL-001 (soil) · IRR-009/IRR-010 (platform). **runtime_verified=0 · production_certified=0** — لا دليل وظيفيّ مُودَع (الأدلّة تحت `runtime-verification/functional_evidence/` **gitignored**، تُنتَج حيّاً).
- **تحديث 2026-07-27 (#670 `0dad1a1`) — المسار صار مُقنَّناً وأصرم بكثير:** لم يعد Step 3 «شغّل `--run` في بيئة ما»، بل **ورشة محكومة**. `runtime-verification/trusted_environments.json` يَسِم `local` و`sandbox` صراحةً `eligible_for_runtime_verified: false` (فاستحالة الترقية من sandbox صارت قاعدة في الكود لا اجتهاداً)، والبيئة المؤهّلة الوحيدة `staging-pg16`.
- **المطلوب (Step 3 — بنية تحتيّة/مشغّل، لا كود):** (١) تشغيل ورشة `.github/workflows/runtime-image-provenance.yml` لبناء/دفع صور OCI موثَّقة (GitHub Artifact Attestation لكلّ digest) وأخذ `run_id` الناجح. (٢) توفير **runner ذاتيّ الاستضافة** بالوسوم `[self-hosted, linux, docker, sahool-path3-trusted]` + **بيئتَي GitHub محميّتين**: `staging-pg16` (المنتِج) و`staging-pg16-attestation` (الموقِّع المعزول). (٣) ضبط مفتاح `SAHOOL_RUNTIME_EVIDENCE_HMAC_KEY` (مُصدِر `sahool-staging-hmac`) — **ملاحظة صدق:** مُصدِر `github-actions-oidc` يتطلّب مُتحقِّق provenance خارجيّاً و«الجسر المحلّيّ يرفضه حتى يُهيَّأ مُتحقِّق»، فالمسار العامل اليوم هو HMAC. (٤) تشغيل `.github/workflows/path3-runtime-verification.yml` (`workflow_dispatch`) بمدخلاته الأربعة الإلزاميّة: `environment_id=staging-pg16` · `image_build_run_id=<run الناجح>` · `allow_partial` · `keep_stack`. (٥) أسرار الـprobes: soil يحتاج `SAHOOL_AGENT_TOKEN`، platform يحتاج `SAHOOL_PLATFORM_PROBE_JWT`.
- **ثمّ Step 4 (لا يزال بلا كاتب — يُبنى وقتها بمراجعة):** قلب `runtime_verified` فقط للقدرات التي تجتاز أدلّتها عبر الجسر. السياسة الآن: functional فقط · رفض liveness · مطابقة SHA · بيئة **مسجَّلة وموثوقة** · إيصال provenance + الحزمة الأصليّة (يُعاد حساب digest) · ورشة الموقِّع المُعلَنة · رفض digest مستهلَك سلفاً (حارس الإعادة) · `max_age 30 يوماً` + سقف انحراف ساعة 300ث. `production_certified` أخيراً بعد بوّابات الإنتاج.
- **لماذا مؤجَّل بصدق:** الدليل الوظيفيّ الحقيقيّ لا يُنتَج من sandbox — وهذا الآن **مفروض بالكود** (`eligible_for_runtime_verified: false`) لا بالانضباط وحده؛ وقلب القيمة دون دليل مطابق = تليين التعريف (مرفوض بقرار المالك، الخيار A). المرشّحون الأنقى الباقون خارج الخدمات المسجَّلة (`agriai`/`guardrails` ليسا `services` لأيّ قدرة) ⇒ خدمة رابعة على الجسر ذات عائد متناقص دون بحث.
- **ملاحظة نطاق — مُحدَّثة 2026-07-27 (#672 `cae51f7`، ناسخة لِما قبلها):** المنصّة **تعرض** `GET /runtime-identity` مجدّداً. المالك نقض إسقاط #670 واختار «Exclude infra from budget»: المسار مصنَّف بنية/provenance ومستثنى من ميزانية النطاق عبر allowlist مركزيّة صريحة (خام 630 · بنية 4 · نطاق 626 ≤ 629، والسقف لم يُرفَع). موضعه القانونيّ مثبَّت بعقد: `services/sahool-platform/api/routers/platform_health.py:23` عبر `docs/architecture/platform_route_placement_contract.json`. ⇒ **لم يعد Step 3 بحاجة إلى قرار ميزانيّة جديد** للتدقيق الذاتيّ على المنصّة؛ الحاجز الوحيد الباقي هو البيئة/المشغّل في البنود (١)–(٥) أعلاه.

## ROUTE-ARCHIVE-BINDING-CLI-TAUTOLOGY — ✅ FIXED_IN_CODE (2026-07-28) — التحقّق صار بلا أثر جانبي
- **المصدر:** `scripts/release/platform_route_release_binding.py::main` · `tests/release/test_platform_route_release_binding.py`.
- **الإصلاح:** وضع `--check-archive-binding` يُنفَّذ قبل الكتابة وبفرع `elif` مستقل؛ لذلك لا يعيد توليد الـsidecar التي يفحصها. وضع check أصبح side-effect-free، بينما الكتابة تبقى عملية مستقلة عبر `--archive [--output]`.
- **البرهان:** اختبار يعبث بـ`domain_budget_routes` ثم يشغّل CLI الطبيعي ويثبت `AssertionError` مع بقاء محتوى الملف المعبوث كما هو؛ واختبار write ثم check مستقل يثبت النجاح وعدم إعادة الكتابة. مجموعة الربط: **7 passed**.
- **حدّ الصدق:** إصلاح أداة الإثبات فقط؛ لا يغيّر route budget/placement/attestation ولا يعيد فتحها.

## WEATHER-NORMALIZER-ZERO-COERCION — OPEN (صدق بيانات؛ يحتاج قرار مالك لأنّه يغيّر شكل ردّ عامّ) — رُصِد أثناء WX-10.4
- **المصدر (مُوسَّع في WX-10.5 — العيب عائليّ لا موضعيّ):** `open_meteo.py:218,229` في `normalize_current` (`... or 0.0` / `... or 0`) **و**`open_meteo.py:313-320` في `normalize_daily` (`_at(..., idx, 0)`) لـ`temp_max_c`/`temp_min_c`/`precipitation_mm`/`wind_max_kmh`. أي أنّ المسارات الثلاثة (الآن/التوقّع/الأرشيف) تشترك في العيب نفسه.
- **الأثر:** رياح غائبة تُصبح **0.0 م/ث** ومطر غائب يُصبح **0 مم** — لا يُميَّز المرصود عن المفقود. هذا يناقض عقد **WS-D** المفروض في المستودع نفسه (`scripts/ci/consumer_contract_gate.py:179-185`: «depletion must route through the canonical water-stress guard; **missing != zero**») — القاعدة مطبَّقة على الريّ وغير مطبَّقة على مصدر المشاهدة الذي يغذّيه.
- **خطر عمليّ:** «صفر مطر» يقود توصية ريّ؛ «صفر رياح» يفتح نافذة رشّ؛ و**في السلسلة اليوميّة أخطر**: `temp_max_c` مفقودة تصير **0°م** فتنهار GDD/ET0 المشتقّة منها وتبدو الأيّام باردة كذباً. كلّها قرارات تشغيليّة على قيم **مُختلقة** لا مرصودة.
- **ما فُعِل في WX-10.4/10.5 (تخفيف لا إصلاح):** الخانات الثلاث تُعلن القيد صراحةً في `limitations`.
- **تفصيل الآن:** خانة `current` في CanonicalWeatherState **تُعلن القيد صراحةً** بدل ابتلاعه: `current: upstream normalization coerces a missing value to zero for ['precipitation_mm', 'wind_speed_ms'] — an observed zero is indistinguishable from an absent reading`. المعلومة أُتلِفت أعلى المجرى فلا يستطيع المنتَج النقيّ استعادتها.
- **لم يُصلَح لأنّه قرار مالك:** الإصلاح (إبقاء `None` بدل `or 0`) يغيّر **شكل ردّ نقطة عامّة** (`/v1/weather/current` و`/api/v1/weather/current`). المستهلك الداخليّ `services/weather-service/operations.py:41,57` يتعامل مع `None` سليماً سلفاً (`_num(sample, ..., None)`)، لكنّ الواجهة/الموبايل خارج نطاق فحصي.
- **الحلّ المقترح (WX-10.5):** إسقاط `or 0`/`or 0.0` وإبقاء `None`؛ ثمّ ترقية خانة `current` كي تُصنّف الغياب الحقيقيّ `missing_fields` بدل التصريح بالقيد؛ مع مراجعة مستهلكي الواجهة.

### تحديث WEATHER-NORMALIZER-ZERO-COERCION (2026-08-25): النصف الحراريّ أُغلِق — والقرار المُعلَّق منذ WX-10.5 صدر (H1)

- **القرار الذي كان ينقصها:** السجلّ يقول منذ WX-10.5 «لم يُصلَح لأنّه قرار مالك». صدر القرار: الإزالة الكاملة في `normalize_daily`، **بنطاقٍ مضبوط** — `temp_max_c`/`temp_min_c` وحدهما. المطر والرياح يبقيان مُصفَّرَين («لا مطر» قراءةٌ معقولة للصفر) بقيدٍ مُعلَن، و`normalize_current` خارج النطاق.
- **المُنجَز:** `open_meteo.py:313-314` تُسقِط الافتراضيّ `0` ⇒ الغياب يبقى `None`. و`_DAILY_ZERO_COERCED_FIELDS` ضاقت إلى `("precipitation_mm", "wind_max_ms")` — لأنّ إبقاء الحرارتين كان سينشر **قيداً كاذباً** يصف تصفيراً لم يعد يقع، والقيد الكاذب يُقرأ عذراً.
- **وأخطرُ ممّا سجّله الرصد الأوّل، باتّجاهين لا واحد:** السجلّ قال «تبدو الأيّام باردة» — والقياس يضيف أنّ `_finite(0.0)` صادقة في `gdd.py:49-57`، فاليوم المُصفَّر **يُحتسَب في `counted`** وفي `coverage_ratio`. أي التراكم يُبخَس **والتغطية تُضخَّم** بنفس اليوم المفقود: نافذةٌ حرجة تُسقَط أبعدَ ممّا هي، بثقةٍ أعلى ممّا تستحقّ.
- **تدقيق المستهلكين (شرط المالك أ) — والنتيجة تقلب التبرير الأصليّ:** ثمانية مستهلكين للحرارة اليوميّة، **كلّهم يتعاملون مع `None` سلفاً**: `phase_runtime_workers.py:430` (`if t_max is None … continue`) · `weather_analytics.py:97-100` (`float(None)` ⇒ `TypeError` ملتقَط ⇒ تخطٍّ) · `field_intelligence_card.py:276` (`_num` ⇒ حذف المفتاح والعلَم) · `weather_overlay.py:86-87` · `field_ai_context.py:624-626` · `canonical_water_state.py:154-155` (⇐ `accumulate_gdd`) · `field_state_projection.py:286` · `irrigation_recommendation.py:100-101`. **فالتصفير لم يكن يحمي أحداً — كان يُعطِّل حرّاساً مكتوبين**: شرطُ `if t_max is None: continue` في `phase_runtime_workers` **لا يمكن أن يُطلِق** ما دام المُطبِّع يضمن `float`.
- **التكذيب: ٦/٦ مقتولة** — عودةُ تصفير Tmax · عودةُ تصفير Tmin · قراءةُ الصفر المرصود غياباً (الوجه المعاكس) · كفُّ الغلاف عن رصد الغياب · عودةُ القيد الكاذب · احتسابُ النواة اليومَ المفقود صفراً.
- **وحدُّ صدقٍ مقيس:** أوّل صياغةٍ للاختبار كانت تمرّ بلا أن تقيس — حمولةٌ ناقصة في `et0_mm`/`weather_code` تجعل الجواب `degraded` **دائماً**. مسكه اختبارُ الضبط (`…_stays_validated`) لا المراجعة، فأُصلِحت الحمولة.
- **الحالة:** **PARTIAL** لا `fixed`. الباقي مفتوحٌ بنصّه: `normalize_current` (`or 0.0`/`or 0`) · `precipitation_mm`/`wind_max_ms` في اليوميّ · وقرار «شكل ردّ نقطة عامّة» الذي بُنِي عليه التأجيل الأصليّ لم يُمَسّ لأنّ النطاق لم يبلغه.

## CAPABILITY-CORES-NOT-WIRED — OPEN (groundwork لا integration lifecycle) — رُصِد عند دمج حزمة «القدرات العشر»
- **المصدر (تحقّق مباشر بالبحث عن مستهلكين غير اختباريّين):** `services/sahool-platform/core/canonical_field_state.py` · `core/yield_intelligence.py` · `core/equipment_intelligence.py` · `core/economic_scenarios.py` — **صفر مستهلك غير اختباريّ** لكلٍّ منها (المستهلك الوحيد `tests/test_capability_plan_closures.py`).
- **المقابل الموصول فعلاً:** `core/crop_intelligence/canonical_inputs.py` (CI-7) **موصول** في `core/crop_intelligence/engine.py:48-56` ويمرّر النَّسَب (`evidence_ids`) ويُعلن `canonical_input_sources.weather` ⇒ هذا وحده مستهلك إنتاجيّ حقيقيّ لـCanonicalWeatherState من جهة المحاصيل.
- **لماذا يُسجَّل:** الأربعة نوى نقيّة صحيحة ومُختبَرة، لكن **بلا مسار ولا إدامة ولا مُستدعٍ إنتاجيّ** — أي *groundwork* لا *integration lifecycle*، وهو نفس التمييز الذي أرساه المالك في **INT-004** («مسلسلات تصدير ساكنة بلا adapter/consumer حيّ ⇒ groundwork لا دورة تكامل»). وثيقة الحزمة `docs/implementation/TEN_CAPABILITY_PLAN_CLOSABLE_EXECUTION_20260728.md` **صادقة** (تذكر لكلّ بند ما تبقّى، وتفصل *added* عن *existing re-verified*)، لكنّ كلمة «CORE CLOSED» يجب ألّا تُقرأ «تعمل في الإنتاج».
- **الحالة:** لا يُطلَب إصلاح — التسجيل يمنع أن يتحوّل «CLOSED» إلى ادّعاء تغطية لاحقاً. الإغلاق الحقيقيّ لكلٍّ منها = مسار/إدامة/مستهلك + دليل، تماماً كـINT-004A.

### تحديث CAPABILITY-CORES-NOT-WIRED (2026-07-28): الحارس أثبت الفجوة عمليّاً
- **CI أثبت ما سجّلتُه:** `test_p0_platform_module_growth_guard` أسقط الـPR — «sahool-platform Python module count grew from 666 to 671». الحارس مصمَّم ليقول: **أضِف الكود الجديد إلى خدمته المالكة، أو ارفع الأساس عمداً**. أي أنّ المستودع نفسه يقاوم تركيز الكود في منصّة موسومة سلفاً `critical-core-concentration`.
- **ما فُعِل:** رُفِع الأساس **666 ⇒ 672** (ستّة، شاملاً `policy_engine` من CI-9) مع مذكّرة `capability_plan_ci7_ci9_note` **تفصل صراحةً**: اثنان (`canonical_inputs`/`policy_engine`) موصولان في `engine.py` ويستحقّان الملكيّة بنفس شروط المداخل السابقة؛ **أربعة مسجَّلة كغير موصولة** ولم تُبرَّر كإنتاج — «admitted so the increment can land intact, NOT because they have earned platform concentration».
- **البديل الأصدق المطروح على المالك:** نقل الأربعة إلى خدماتها المالكة، أو إبقاؤها حتى يكتسب كلٌّ منها مستهلكاً حقيقيّاً ثمّ تثبيت ملكيّتها. رفع الأساس هنا **قرار قابل للنقض** لا إغلاق.

### تحديث CAPABILITY-CORES-NOT-WIRED (2026-07-28): قاعدة قبول جديدة وحاجبة — «لا اسم في الأساس بلا مستهلك إنتاجيّ»
- **قرار المالك (مُلزِم، صدر بعد مراجعة الفرع):** *«وجود ملفّات أو وحدات مع حرّاس ratchet لا يثبت أنّ القدرة دخلت المسار التشغيليّ»* ⇒ **لا يُرفَع أساس الوحدات لقدرة بلا مستهلك غير اختباريّ**، وإلّا تحوّل «وجود بنية» إلى «قدرة محكومة ومعتمدة» بينما الدليل التنفيذيّ صفر.
- **ما طُبِّق فوراً على #676 (إعادة تشكيل، لا تبرير):** أُبقي **`knowledge_layer` وحده** (موصول في `canonical_inputs.py`) والأساس **672 ⇒ 673**؛ **أُسقِط من الشريحة** `learning_engine` و`agricultural_operating_system` — الوحدتان + اختباراهما + وثيقتاهما + إعادة التصدير في `__init__.py` — حتى يظهر لكلٍّ مستهلك إنتاجيّ.
- **قاعدة دائمة للشرائح القادمة:** اسم الوحدة يدخل الأساس **في نفس الـPR** الذي يضيف مستهلكها الإنتاجيّ **وحارساً يثبت ذلك**. لا قبول مسبق ولا «يهبط الآن ويُوصَل لاحقاً».
- **خطأ منهجيّ منّي يُسجَّل:** قبلتُ في #675 و#676 صياغة «يُقبَل ليهبط الإنكرمنت سليماً، لا لأنّه استحقّ التركيز» — وهي **صادقة في الوصف لكنّها خاطئة في الأثر**: الراتشِت لا يقرأ المذكّرات، يقرأ الأرقام. المذكّرة الأمينة لا تُصلِح رقماً يشهد زوراً.
- **الحالة:** ستّ نوى غير موصولة، **لا واحدة منها في الأساس** بعد إعادة التشكيل (الأربع الأصليّة دخلت في #675 قبل صدور القاعدة — تُعالَج في شرائح الربط، لا بنقض دمج قائم).

### تحديث CAPABILITY-CORES-NOT-WIRED (2026-07-28): النواة الأولى — `equipment_intelligence` — أُصلِحت ثمّ رُبِطت
- **عيب اختلاق رُصِد قبل الربط (لا بعده):** النواة كانت تُسقِط الغياب إلى أرقام — `service_interval_hours` غائبة ⇒ **250 مُخترَعة**، و`last_service_hours` غائبة ⇒ **0.0**. وجدول `equipment` (`migrations/v23_equipment.sql`) **لا يحمل أيّ من العمودين**، فحمولة `list_equipment` الحقيقيّة كانت تُخرِج جرّاراً بـ300 ساعة وبلا سجلّ صيانة كـ«مستحقّ» (`300−0 ≥ 250`) **وبلا قيد واحد يُعلن ذلك**. نفس عائلة `WEATHER-NORMALIZER-ZERO-COERCION` ومخالفة لقاعدة WS-D `missing ≠ zero`.
- **لماذا لم أربط قبل الإصلاح:** الربط كان سيحقّق شرط «مستهلك إنتاجيّ» **وينقض شرط «fail-closed»**، ويجعل الراتشِت يشهد على قدرة تُفبرِك — أسوأ من نواة يتيمة.
- **العقد بعد الإصلاح (`equipment_intelligence.v2`):** حالة صريحة لكلّ أصل — `due` · `not_due` · `not_evaluated` — وقيود مُسمّاة: `maintenance_policy_missing` · `service_meter_baseline_missing` · `current_meter_reading_missing`. لا مدخل ناقص يُنتِج `due` ولا `overdue_hours` موجباً. **الصفر الحقيقيّ يبقى قراءة** (`0.0` ⇒ يُقيَّم؛ الغياب ⇒ لا يُقيَّم)، و`bool` مرفوض كقراءة عدّاد. و`readiness` لا يقول `ready` لأسطول لم يُقيَّم منه شيء.
- **المستهلك الإنتاجيّ:** `api/routers/equipment.py::list_equipment` عبر `?summary=true` — **بلا مسار جديد** (سابقة INT-004A)، والردّ الافتراضيّ **بلا تغيير**. الواقع الذي يُبلِغه اليوم: كلّ الأصول `not_evaluated` لأنّ سياسة الصيانة غير مسجَّلة — وهي **الحقيقة** لا عيب.
- **حارس الملكيّة مُثبَت بالتكذيب:** اختبار يمنع تكرار قاعدة الاستحقاق خارج النواة. سقط أوّلاً على **docstring** الراوتر (إيجابيّة كاذبة)، فصُحّح ليجرّد الـdocstrings بـAST (نمط `consumer_contract_gate`) — ثمّ أُثبِت أنّه يلتقط منطقاً حقيقيّاً مزروعاً ويعود أخضر بعد إزالته.
- **مؤجَّل صراحةً (خارج النطاق بقرار المالك):** هجرة `equipment.service_interval_hours` و`equipment_maintenance.hours_at_service`. وجود `performed_date` **لا يكفي** لاشتقاق `last_service_hours`، ولا يجوز تقريب الساعات من الزمن أو من عمر الأصل.

### الحارس الحقيقيّ: `capability_core_consumption_guard` (2026-07-28)
- **السجلّ الواحد:** `docs/architecture/capability_core_consumption_registry.json` — النوى الأربع فقط، لكلٍّ `status` و`consumer` و`consumed_symbol`. **الحالة اليوم: 1/4 موصولة** (`equipment_intelligence`)، وثلاث `pending_wiring` بأسبابها المسجَّلة (تعارض التوأم · تداخل الغلّة · قرار مسار الاقتصاديّات).
- **ما يفرضه:** `wired` ⇒ المستهلك المُعلَن موجود **ويستورد الرمز فعلاً بفحص AST**؛ `pending_wiring` ⇒ لا يجوز أن يُعلن مستهلكاً. الترقية تحدث **في نفس التغيير الذي يضيف المستهلك** — لا قبول مسبق.
- **مُثبَت بالتكذيب على أربع طرق انحدار:** فقدان الاستيراد ⇒ FAIL · تنزيل نواة موصولة إلى pending ⇒ FAIL · ادّعاء `wired` بلا مستهلك ⇒ FAIL · **ذكر الرمز في docstring فقط ⇒ FAIL** (الأخيرة هي المصيدة التي وقعتُ فيها مرّتين اليوم).
- **حدّ نطاق مفروض باختبار:** السجلّ يتتبّع النوى الأربع **حصراً**، واختبار يمنع تسرّب `pest_detector`/`yield_estimator`/`field_boundary_backends`/`aquacrop` إليه — أي يمنع بنيويّاً تكرار الخلط التسمويّ الذي كاد يُغلق الفجوة زوراً.
- **خطأ منهجيّ تكرّر منّي مرّتين:** فحص نصّيّ يلتقط الـdocstring/النثر التوضيحيّ ويُنتِج إيجابيّة كاذبة — مرّة في حارس الملكيّة (docstring الراوتر) ومرّة في اختبار النطاق (حقل `not_this` في السجلّ). العلاج في الحالتين: **افحص المنفَّذ لا النصّ** (تجريد docstrings بـAST · قصر الفحص على `cores`).

### تقارب مستقلّ على `equipment_intelligence` — وفرق سلوكيّ حاسم (2026-07-28)
- **حزمة المالك `…equipment_intelligence_fail_closed_wired…` وصلت بعد #677 وتحمل التشخيص نفسه:** الحالات الثلاث نفسها، أسماء القيود الثلاثة نفسها، المستهلك نفسه (`list_equipment`)، صفر مسار جديد، وحتّى الحارس بالاسم نفسه. تقارب مستقلّ يؤكّد صحّة التشخيص.
- **الفرق الوحيد الجوهريّ — لصالح #677:** في نسخة الحزمة، وجود `next_service_date` **يُنهي التقييم فوراً** ويُرجِع `not_due` إن كان التاريخ مستقبليّاً. **برهان سلوكيّ:** أصل بـ600 ساعة وفاصل 250 وآخر صيانة 0 (⇒ **متأخّر 350 ساعة**) وموعد مجدول `2026-12-31` ⇒ نسختهم: `service_due=0` و`readiness=ready`؛ #677: `due` و`overdue_hours=350.0`.
- **لماذا يهمّ:** هذا **العيب الأصليّ مقلوباً** — الأوّل يخترع استحقاقاً من العدم، وهذا **يُخفي استحقاقاً مُثبَتاً بالعدّاد** ويُصدر `ready` عن أسطول متأخّر. القاعدة تعمل في الاتّجاهين: التاريخ المسجَّل يُثبِت الاستحقاق عند حلوله، ولا يُلغيه قبله.
- **ثُبِّت باختبارَي انحدار** في `test_equipment_intelligence_wiring.py`: تاريخ مستقبليّ لا يحجب استحقاق العدّاد · وتاريخ مستقبليّ وحده (بلا مدخلات عدّاد) ⇒ `not_evaluated` لا `not_due`.
- **فرق ثانٍ = تفضيل لا عيب:** أسطول تعذّر تقييمه كلّه — نسختهم `degraded`، #677 `unknown`. الأدقّ `unknown` (العجز عن التقييم ليس تدهوراً)، و`degraded` دفاع تحفّظيّ مشروع. مطروح على المالك.

### عقد `equipment_intelligence` النهائيّ بقرار المالك (2026-07-28) — أسبقيّة الأدلّة ومفردات الجاهزيّة
- **القاعدة التي حسمها المالك:** `next_service_date` مستقبليّ **لا يُثبِت `not_due` وحده**، بل يُثبِت فقط أنّ **مسار التاريخ** لم يستحقّ بعد؛ ثمّ يُفحَص العدّاد إن اكتملت بياناته. الإرجاع المبكر عند رؤية تاريخ مستقبليّ خطأ لأنّه **يمنع جمع الأدلّة المستقلّة ويُخفي استحقاقاً مُثبَتاً**.
- **العقد المُنفَّذ (كلّ حالة مُختبَرة):** تاريخ حلّ ⇒ `due` بـ`basis=next_service_date` · تاريخ مستقبليّ + عدّاد مكتمل ⇒ يُقيَّم العدّاد (`basis=service_meter`) · تاريخ مستقبليّ + عدّاد ناقص ⇒ **`not_due` بالتاريخ** مع قيد `service_meter_not_evaluable` · بلا تاريخ + عدّاد ناقص ⇒ `not_evaluated`.
- **حقل `basis` أُضيف لسبب صدق:** يميّز `not_due` المُسنَد إلى موعد مجدول عن `not_due` الذي **أيّده العدّاد** — قوّتاهما مختلفتان ولا يجوز خلطهما. اختبار يثبّت التمييز.
- **مفردات الجاهزيّة (كلّ حالة تعني شيئاً واحداً):** `unknown` = لا أدلّة كافية · `attention_required` = أصل مستحقّ على الأقلّ · `degraded` = **تدهور مُثبَت بالأدلّة** (أصول غير متاحة) · `ready` = القابل للتقييم سليم. **الأسبقيّة:** الاستحقاق يتقدّم على التدهور — لئلّا يُخفى بند قابل للتنفيذ خلف `degraded`.
- **إشارة التحفّظ بلا تزوير الحالة:** `assessment_coverage` (0.0 حين لا يُقيَّم شيء) + قيد `all_assets_not_evaluated` — التحفّظ يُسجَّل ولا يُحوّل `unknown` إلى `degraded`.
- **حمولة الإنتاج اليوم:** `readiness=unknown` · `coverage=0.0` · صفر استحقاق — لأنّ سياسة الصيانة غير مسجَّلة. هذه هي الحقيقة، لا عيب.

### CAPABILITY-CORES-NOT-WIRED: النواة الثانية — `economic_scenarios` (2026-07-28)
- **لا إصلاح مطلوب في الأساس:** `api/economic_state.py` صادق سلفاً («مُدخَل غائب ⇒ مكوّنه None ولا يُحتسب صفراً» + `status`/`missing_inputs`/`calibrated`). بخلاف `equipment_intelligence` لم يكن هناك اختلاق يُصلَح — العقبة كانت **المستهلك** لا الصدق.
- **العقد v2 (رفع من v1):** سيناريو ناقص ⇒ `not_evaluated` **بأسماء مدخلاته الغائبة**، و**لا يُصنَّف** مقابل مكتمل. الخطر هنا ليس رقماً خاطئاً بل رقماً **مُجامِلاً**: لو عُومل غياب بند تكلفة كصفر، لفاز السيناريو الذي **لم يُصرِّح** بتكلفته. `assessment_coverage` + `incomplete_assessment_coverage` يكشفان النقص دون إلغاء الإجابة المفيدة.
- **الصفر مقابل الغياب:** `water_price_per_m3=0` يُقيَّم عاديّاً؛ وتكلفة كلّيّة صفر ⇒ `roi_pct=None` + `roi_undefined_zero_total_cost` بدل نسبة لانهائيّة أو مُختلقة. والقيمة المشوّهة (`nan`/سالب/`bool`/نصّ) **تُرمى** لا تُهمَل — إسقاطها صامتاً كان سيجعل خطأ المستدعي يبدو كإغفال.
- **المستهلك — بمسار جديد بقرار المالك:** `POST /api/v1/scenario/economics` على راوتر السيناريو. **أُنفِق مسار واحد من ثلاثة عمداً**: نقطة `feasibility` تأخذ نموذج مدخلات مختلفاً كلّيّاً (`area_ha`/`price_per_t`) فطيّها فيه كان سيكون قسراً. **الميزانية 626 ⇒ 627 ≤ 629، والهامش 3 ⇒ 2.**
- **ضريبة تسجيل مسار جديد (تُذكَر للمرّات القادمة):** المسار الجديد لا يكفيه الكود — يجب تسجيله في `platform_extraction_map.json` بمالك وتصنيف، **وإدراجه أزاح أرقام أسطر أربعة مسارات تحته** فأسقط `platform_route_ownership_guard`. صُحّحت الأرقام **باشتقاقها من AST** لا يدويّاً. وظهر مولِّد سادس وأربعون لا ينكشف إلّا بإضافة مسار: `route_mount_contract_guard`.
- **الحارس:** `capability_core_consumption_guard` انتقل **1/4 ⇒ 2/4** عند هذه الشريحة، ثمّ **3/4** (`yield_intelligence`، `4eded7a`) ثمّ **4/4** (`canonical_field_state`، `247c69c`). تصحيح لِما كُتب هنا: حاجز التوأم كان **تشخيصاً خاطئاً** — `core/field_twin.py:30` يُعلن نفسه `DERIVED_VIEW` وCanonicalFieldState مرجعاً؛ والحاجز الحقيقيّ غياب مُنتِجَي التربة والطقس (`FIELD-STATE-PRODUCERS-MISSING-01`). وتداخل الغلّة فُحِص ووجد نظيفاً: `calibration_factor` له مالك واحد. **المرجع هو الحارس لا هذا النصّ** — وقد تأخّر تحديثه، وهو ما يُصلحه `BRAIN-CLAIM-UNVERIFIED-01` أدناه.

### عيبان كشفهما إيقاظ الاختبارات الخامدة (2026-07-28) — لم يُحدِثهما الفرع

إيقاظ ~479 اختباراً أخرج عيبين **قائمين سلفاً** كان الخمود يُخفيهما. وُسِما `xfail` بسبب
مُعلَّل ومُتتبَّع — لا `skip` صامتاً — فيبقيان مرئيَّين في تقرير CI.

- **دور superuser في CI ⇒ لا معرّف جديد.** المفهوم مسجَّل سلفاً باسم **`AUTH-E2E-UNDER-RESTRICTED-ROLE`**
  (`registry.md:166` — LIVE-CERTIFIED/CLOSED @ `9a3ce99`). سككتُ له معرّفاً جديداً (محذوف الآن) دون البحث في
  السجلّ — خطأ تكرّر ثالث مرّة في الجلسة. **الفرع المفتوح تحت المعرّف القائم:** الإغلاق أثبت
  عمل التطبيق تحت `sahool_app`، لكنّه **لم يُغيّر وظيفة CI** — `ci.yml:626` ما زال يتّصل
  بـ`sahool_test` superuser، فسقطت ثلاثة اختبارات 2026-07-28 بنفس الحارس
  (`shared/db_role_guard.py:97`). الإصلاح دور مقيَّد، **لا** `SAHOOL_ALLOW_RLS_BYPASS_ROLE=1`.
- **تصحيح على قياس «صفر إصلاح»:** القياس كان مقصوراً على `-m unit`. تعديل
  `requirements-test.txt` يُصيب كلّ وظيفة تُثبّته ومنها `-m integration` (`ci.yml:624`)،
  وهناك ظهر الفشلان أعلاه وثالثٌ أُصلِح (تصادم `routers` في `test_services_functional`).

## APP-ROUTES-EMPTY-01 — CLOSED_IN_CODE (2026-07-28) — السبب مُبرهَن، ليس عيب تسجيل

- **الأثر (كان):** ١١ اختباراً في `tests_v9` تفحص `app.routes` ترى
  `{'/docs', '/docs/oauth2-redirect', '/openapi.json', '/redoc', None}` فقط.
- **السبب المُبرهَن (قياس المالك في بيئة مطابقة لـCI):**

  | fastapi | `app.routes` | التركيب | `-m unit` |
  |---|---|---|---|
  | 0.140.13 (بلا تثبيت) | 175 | 4 Route + 171 `_IncludedRouter` | **11 failed** · 3467 passed |
  | 0.136.3 (الإنتاج) | 639 | 4 Route + 634 APIRoute + 1 WS | **0 failed** · 3478 passed |

  في fastapi ≥ 0.140 لم يعد `include_router` يُسطِّح المسارات في `app.routes`؛ يُدرِج
  غلافاً واحداً `_IncludedRouter` لكلّ راوتر، **والغلاف لا يُصدِّر `.path`**.
- **التطبيق لم يكن فارغاً قطّ:** المسارات مُسجَّلة ويخدمها التطبيق (٦٣٤ APIRoute تحت
  التثبيت). المتغيّر **سطح الاستبطان لا التسجيل** — وهو ما يؤكّد التضييق السابق
  (`api/router_registry.py:39-47` لا يبتلع استثناءً) ويكمله بالسبب.
- **المصدر:** `tests_v9/requirements-field-forms.txt` كان يحمل `fastapi>=0.115.0` **بلا
  سقف** ⇒ يحلّ إلى 0.140.13، أي أنّ خطوة field-forms كانت تختبر على إصدار **غير إصدار
  الإنتاج** (`api/requirements.txt:6` = `0.136.3`).
- **الإغلاق:** التثبيت على `fastapi==0.136.3`. وهذا يفسّر تباين القياسين: محاولة الإيقاظ
  ثبّتت بلا سقف ⇒ ١١ إخفاقاً؛ وقياس المالك بـ0.136.3 ⇒ صفر. **كلاهما صحيح، والفارق
  التثبيت.**
- **ما أعقبه:** إغلاق هذه رفع الحاجب عن `UNIT-TEST-DORMANCY-01`، فأُغلِقت في اليوم
  نفسه بإيقاظ ٤٧٩ اختباراً. إخفاقات التكامل مستقلّة عن الاثنتين ولم تُغلَق —
  `AUTH-E2E-UNDER-RESTRICTED-ROLE` (فرع CI) و`MCP-PREAUTH-STATUS-01`.
- **دَين متبقٍّ (`APP-ROUTES-INTROSPECTION-COUPLING-01`):** الأحد عشر يؤكّدون على تمثيل
  FastAPI الداخليّ. تحويلهم إلى `app.openapi()["paths"]` يجعل الترقية ممكنة بدل تجميد
  الإصدار أبداً.

## APP-ROUTES-INTROSPECTION-COUPLING-01 — CLOSED (2026-07-30)

- **الأثر (كان):** ١٢ ملفّاً (لا ١١ — العدّ الأصليّ كان تقريبيّاً) يقرأ `app.routes` —
  تمثيل FastAPI **الداخليّ** — فينكسر عند أيّ تغيير في بنيته، كما حدث في 0.140
  (`_IncludedRouter`، `APP-ROUTES-EMPTY-01`).
- **الإصلاح:** مساعِدان في `tests_v9/conftest.py` — `registered_paths(app)` و
  `registered_methods(app, path)` — يقرآن `app.openapi()["paths"]` بدل `app.routes`؛
  سطح **عامّ ومستقرّ بالعقد** لا داخليّ. كلّ الاثني عشر ملفّاً حُوِّلت:
  `test_alerts_derived_from_state.py` · `test_alerts_field_state_route.py` ·
  `test_calendars_today.py` · `test_disease_field_state_feed.py` ·
  `test_field_state_gateway.py` · `test_internal_field_read_channel.py` (موضعان) ·
  `test_internal_field_state_channel.py` · `test_recommendations_field_state_gate.py` ·
  `test_soil_lab_field_state_emit.py` · `test_tasks_endpoints.py` (موضعان) ·
  `test_tts_providers_20260702.py` (موضعان) · `test_yield_field_state_feed.py`.
- **مُثبَت:** ٨٤ اختباراً عبر الملفّات الأربعة عشر (بما فيها `test_unit_environment_completeness.py`
  الذي كان يذكر «١٢ ملفّاً تفحص `app.routes`» في تبريره — حُدِّث ليصف `registered_paths`)
  تمرّ كاملةً؛ `-m unit` الكامل 3750 نجح بلا انحدار؛ `ruff check`/`format --check` نظيفان.
- **لماذا لم يُترَك تعليق `app.routes` وحيداً في `test_tts_providers_20260702.py:190`:**
  ذلك تعليق يشرح آليّة `include_router` الداخليّة لـFastAPI (لماذا `dependency_overrides`
  لا يُستشار) لا كيف يقرأ الاختبار المسارات — يبقى صادقاً بعد الإصلاح ولا علاقة له
  بالاقتران المُغلَق هنا.
## UNIT-TEST-DORMANCY-01 — FIXED_IN_CODE (2026-07-28) — كان OPEN (P1) في اليوم نفسه

- **الأثر:** ~479 اختبار وحدة لا يُنفَّذ في بوّابة الدمج لاستبعاد `fastapi` من `requirements-test.txt`؛ منها ١٢ ملفّاً في `tests_v9` تفحص `app.routes`.
- **القرار الأصليّ ومبرّره البائت:** `hot.md` (#590) + `tests_v9/requirements-field-forms.txt:2-3`. الشرط «يفشل في البيئة الدنيا» **تآكل**: لم يبقَ ناقصاً إلّا `scipy` و`pillow`، و`scipy` مثبَّتة أصلاً في `api/requirements.txt:20`.
- **قياس المالك:** 3478 نجح · 26 تخطٍّ · صفر فشل — **على `-m unit` وحدها**. CI أظهر ١١ فشلاً في الوحدة و٣ في التكامل.
- **كان محجوباً بـ:** `APP-ROUTES-EMPTY-01` (أُغلِقت `29809dc` بتثبيت fastapi على إصدار الإنتاج) — وهو ما رفع الحاجب.
- **القياس التفاضليّ الذي أوجب الإغلاق** (نفس أمر CI، بيئة نظيفة من `requirements-test.txt`):

  | البيئة | نجح | تخطٍّ | فشل |
  | --- | --- | --- | --- |
  | قبل (بلا fastapi/scipy/pillow) | 2999 | 369 | 0 |
  | بعد | **3478** | 26 | **0** |

  الفارق **٤٧٩ اختباراً** — مطابق للتقدير المسجَّل، ومطابق لقياس المالك رقماً برقم.
- **الإصلاح:** الثلاث أُضيفت إلى `tests_v9/requirements-test.txt` **مثبَّتة على إصدار الإنتاج** (`fastapi==0.136.3` · `scipy==1.13.1` · `pillow>=10.0.0`) لا على نطاق مفتوح — درس `APP-ROUTES-EMPTY-01`. كلّ تبعيّة أُثبتت لزومها بالقياس لا بالتقدير: إسقاط `scipy` وحدها يُوقِف الجمع (`api/trial_engine.py:28`)، وإسقاط `pillow` وحدها يُفشِل `test_segmentation_frontend_contract_20260702::test_segment_request_accepts_frontend_field_names`.
- **أثر التغطية:** `--cov=services` صار 46٪ (كان 44.55٪)، والأرضيّة تصعد 40→42 بقاعدة `floor(المقيس)-~4` المُعلَنة في `docs/testing/coverage_ratchet.md`. **الرقم الكلّيّ يُقرأ بحذر:** المقام تضاعف ثلاثاً (20655 ← 60870 عبارة). المكسب الحقيقيّ في الأصفار التي زالت: `services/auth/main.py` 3٪←50٪ · `auth/routers/*` 0٪←14–62٪ · `api/field_state_gateway.py` 29٪←100٪ · `api/field_state_projection.py` 44٪←85٪ · `supervisor-agent/main.py` 0٪←37٪.
- **`requirements-field-forms.txt` حُذِف:** سبب وجوده كان عزل fastapi عن البيئة المشتركة؛ زال السبب فزال الملفّ. خطوة CI باقية لأنّ ثلاثة من ملفّاتها الأربعة **بلا `pytestmark = unit`** ⇒ يستبعدها `-m unit`؛ تُشغَّل صراحةً بالمسار (40 نجحت).
- **حارس ضدّ عودة الخمود الصامت:** `tests_v9/test_unit_environment_completeness.py` يفحص **الشرط** الذي يجعل الاختبارات تعمل (استيراد `fastapi`/`scipy`/`PIL`) لا الاختبارات الموقَظة واحداً واحداً. بلا هذا، حذف تبعيّة يُعيد المئات إلى `skip` **والبوّابة تبقى خضراء** بعدد أصغر لا يقرأه أحد — وهو بالضبط ما حدث المرّة الأولى. مُثبَت بالتكذيب: إسقاط `pillow` يُفشِله برسالته.
- **أثر على اختبارات التكامل — لم يُخفَ:** وظيفة *Integration Tests* تُثبّت الملفّ نفسه (`ci.yml:611`) وتشغّل `-m integration`، فالإيقاظ يمسّها أيضاً. الاختباران اللذان يستيقظان بفشل معروف وُسِما `xfail(strict=False)` **بسببه المُسمّى ومعرّف فجوته**، لا `skip`: `test_mfa_hardening_integration_v29_5::test_mfa_end_to_end_via_app` (`AUTH-E2E-UNDER-RESTRICTED-ROLE`) و`test_mcp_functional::test_shared_helpers_servers_import_or_skip` (`MCP-PREAUTH-STATUS-01`). `strict=False` عمداً: حين يُصلَح السبب يمرّ الاختبار ولا يُحمِّر البناء بـ`XPASS`.
- **CI قال ما لم أستطع قوله — والحالة الثالثة ظهرت:** أعلنتُ أنّي لا أستطيع تشغيل `-m integration` محلّيّاً وأنّ الحكم لـCI. وقع الفشل فعلاً في **اختبار ثالث لم أُعلّمه**: `test_services_functional::test_services_functional` — ولم يكن عيباً جديداً بل **الحالة الثالثة لـ`AUTH-E2E-UNDER-RESTRICTED-ROLE`**، هذه المرّة في `soil-service` لا `auth`. الوسمان اللذان وضعتُهما مسبقاً عملا (`2 xfailed`)، ومجموع الفشل التكامليّ كان **اختباراً واحداً** لا انهياراً. وُسِم بالمعرّف نفسه؛ الإصلاح الجذريّ يبقى دوراً مقيَّداً للتشغيلة المشتركة.
- **سلسلة إعادة التوليد المُوثَّقة كانت ناقصة مولِّداً:** `capability_mapping_engine` ليس في السلسلة المعتادة، وأيّ **ملفّ جديد** يُدرِجه في `unmapped_artifacts` ⇒ `capability-registry` تسقط. علاجه لم يكن مطاردة المولِّد الذي سقط، بل **مسح الثمانية والثلاثين مولِّداً كلّها بوضع `--check`** — نفس درس «الكنس يغطّي ٤٦ من ٢١١». المسح كشف أربعة انحرافات، ثلاثة منها **قائمة على `main` سلفاً** ولا تخصّني (`compose_runtime_target_resolver` · `path3_runtime_readiness_closure` · `runtime_environment_preflight`) — تُثبَّت على **بيئة التوليد نفسها**، فإعادة توليدها تبصم بيئة الوكيل على المستودع. تُركت لـ`ARCH-TESTS-UNLISTED-IN-CI-01`، وهي دليل إضافيّ عليها: ثلاثة آثار منحرفة تجلس على main بلا حارس.
  - **خطأ قياس صحّحتُه في حينه:** فحصتُ «هل تنحرف على main النظيفة؟» بـ`git stash` — و`stash` لا يُلغي الالتزامات، فكنتُ أفحص فرعي لا `main`. أُعيد الفحص على worktree منفصلة على `origin/main`، وعندها فقط انفصل الأربعة إلى واحد لي وثلاثة قائمة.
- **حدّ الصدق:** هذا يُنهي سُبات **اختبارات الوحدة**. إخفاقا التكامل المتبقّيان مستقلّان ولا يُغلقهما هذا: `AUTH-E2E-UNDER-RESTRICTED-ROLE` (فرع CI) و`MCP-PREAUTH-STATUS-01`. ولا يُلغي `APP-ROUTES-INTROSPECTION-COUPLING-01`: التثبيت رفع الحاجب ولم يفكّ الاقتران بـ`app.routes`.

## IMAGERY-BLANK-THUMBNAIL-01 — OPEN (P1) 2026-07-28

- **الأثر:** بطاقات السجلّ الزمنيّ التاريخيّة تعرض مصغّرات فارغة.
- **كان يتيماً:** أُجِّل في `hot.md` (#660) بعبارة «blank-thumbnail بند مستقل» ثمّ لم يدخل السجلّ قطّ، و`git grep blank-thumbnail` صفر في الكود — مخالفة مباشرة لقاعدة CLAUDE.md «لا فجوة بلا مصدر + حالة».
- **تشخيص مُتحقَّق منه:** نافذة CDSE تنهار إلى ٢٤ ساعة للتواريخ التاريخيّة (`raster_cdse_tile_runtime.py:75-77`) ودورة Sentinel-2 ~٥ أيّام · `nginx.v9.conf:261` مهلة 60s مقابل `cdse_client.py:468` 120s · `MapHub.tsx:2484` يُخفي الفشل بـ`display:none`.
- **تصحيحان على تقرير المالك:** الفشل **لا يُخزَّن** في الكاش (`return None` قبل سطر التخزين 201) — العيب أنّ نتيجة **ناجحة لكن فارغة** تُخزَّن ساعة، فيتغيّر الإصلاح إلى فحص فراغ قبل التخزين. وسابقة `CDSE_CLIENT_ID:?` في BUG-7 **غير موجودة**؛ `docker-compose.v9.yml:745` يخصّ `SH_CLIENT_ID`.
- **حدّ نطاق:** إصلاح الكاتب لا يُصلح COGs المعطوبة القائمة؛ يلزم إعادة معالجة.

### تقدّم (2026-07-28): حارس الراستر الفارغ — الشقّ الأوّل مُغلَق في الكود

- **المُنجَز:** `tile_render.raster_has_observable_content` (نقيّة، fail-closed) تُستدعى في `raster_cdse_tile_runtime.ensure_field_cog` **قبل** سطر الكاش: بلا مشاهدة ⇒ لا كاش ولا ملفّ مؤقّت. يُنهي تجميد الفراغ ساعةً الذي كان يمنع ظهور أثر أيّ إصلاح لاحق.
- **البرهان:** ١٤ اختباراً (`test_raster_observable_content.py` ١٠ حالات على ملفّات راستر ناتجة فعليّاً + `test_cdse_empty_raster_not_cached.py` ٤ تقود المسار الحقيقيّ). **مُثبَت بالتكذيب:** تعطيل الفحص يُسقِط اختبارَين فوراً (الكاش يمتلئ + تسريب ملفّ مؤقّت).
- **حدّ الصدق:** يُغلق **آليّة تثبيت الفراغ فقط**. **مفتوح:** نافذة الـ٢٤ ساعة (المولِّد الجذريّ) · تصنيف وإعادة اشتقاق الأصول القديمة · تطبيع TIFF الخام من CDSE في المسار الحيّ (لا يمرّ بـ`cog_writer` المُصلَح في #660) · الحالات المرئيّة بدل `display:none`.
- **تصحيح تشخيصيّ مُثبَت:** إصلاح `photometric=RGB` المقترَح **مُنفَّذ سلفاً** (`cog_writer.py:161-170`, #660)، و`write_rgba_cog` **لا يُستدعى** في المسار الحيّ (`raster_pixel_processing.py:319,417` فقط) — فالعيب بيانات + مسار، لا كاتب.
- **انقسام رسميّ لـBUG-1 (قرار المالك):** **BUG-1A** أصول قديمة فاسدة (تصنيف + إعادة اشتقاق؛ لا يُصلحها كود) · **BUG-1B** المسار الحيّ يكتب TIFF خام من CDSE ويتجاوز الكاتب المُطبَّع. **لا يُفتَح PR لإعادة تنفيذ إصلاح #660.**

### تصحيحان بالقياس على بندَين مفتوحَين (2026-08-16، `main` عند `21179b7f`)

أُعيد قياس البندين المتبقّيين في «حدّ الصدق» أعلاه قبل الشروع فيهما، فسقط كلاهما كما كُتِب:

- **«الحالات المرئيّة بدل `display:none`» — مُغلَق سلفاً، والمرساة بائتة.** `MapHub.tsx:2484` لم يعد موضع الإخفاء (`display: 'none'` الوحيد اليوم في `frontend/src/sections/MapHub.tsx:1712` ويخصّ مُدخَل ملفّ لا مصغّرة). البديل المُنفَّذ: `frontend/src/components/maphub/ImageryTimelineThumb.tsx` يُستدعى في `MapHub.tsx:2558` بـ`src={null}` حين `has_cog=false` فيعرض «قيد المعالجة»، ويحرسه `ImageryTimelineThumb.test.tsx` (١٠ حالات).
- **«نافذة الـ٢٤ ساعة (المولِّد الجذريّ)» — مُكذَّب للتواريخ التاريخيّة.** تواريخ الشريط تأتي من `/api/v1/fields/{id}/available-dates` (`services/raster-service/routers/fields.py:1350`) وهي **تواريخ اكتساب حقيقيّة** (COGs مُدامة + تواريخ STAC حين `include_provider`). فنافذة اليوم الواحد عليها صحيحة؛ وتوسيعُها كان **يُدخِل عطلاً**: مشهد يومٍ آخر يُعرَض تحت التاريخ المختار. المرساة المسجَّلة `:75-77` بائتة أيضاً — الموضع الفعليّ `raster_cdse_tile_runtime.py:97-104`.
- **وما بقي فعلاً ليس هذا:** قياس الموضع نفسه كشف عطلاً مختلفاً في **الفرع المقابل** (`is_latest`) — سُجِّل مستقلّاً في `IMAGERY-LATEST-UNBOUND-TO-A-SCENE-DAY-01`.

## IMAGERY-LATEST-CANONICAL-SCENE-BINDING-01 — FIXED_IN_CODE (P1) 2026-08-16

> **تصحيح اسمٍ وادّعاء (مراجعة المالك، 2026-08-16).** سُمّيت أوّلاً
> `IMAGERY-LATEST-UNBOUND-TO-A-SCENE-DAY-01` ووُصِفت بأنّها تُصلح دلالة «الأحدث».
>
> والصفّ أدناه **خارج الاقتباس عمداً**: حارس ادّعاءات الالتزام يقرأ الأسطر التي
> تبدأ بـ`|` أو `## ` وحدها، والالتزام `426ea0f9` يذكر المعرّف المهجور. حذفُ المعرّف
> كان يُحوّل رسالةً مدفوعة إلى ادّعاءٍ بلا سجلّ؛ فيُقاد إلى خلَفه ولا يُمحى.

| المعرّف المهجور | خلَفه | لمَ هُجِر |
|---|---|---|
| IMAGERY-LATEST-UNBOUND-TO-A-SCENE-DAY-01 | `IMAGERY-LATEST-CANONICAL-SCENE-BINDING-01` | الاسم ادّعى دلالة الحداثة، والشريحة تربط يوماً قانونيّاً فقط |

> **وهذا أوسع ممّا قاست.** ما تُغلقه هذه الشريحة هو **ربطُ الناتج بيوم مشهدٍ قانونيّ
> واحد** بدل مزيجٍ ممتدّ بلا هويّة — وهو تصحيح تكافؤ بين المسارين، لا تنفيذٌ لدلالة
> الحداثة. الدلالة نفسها ما زالت مكسورة وسببُها في `search_scenes` لا في النافذة؛
> تفصيلها في `IMAGERY-LATEST-SELECTION-SEMANTICS-02`. الاسم الجديد يقول ما فُعِل.

- **العلّة:** «latest» في الخريطة الحيّة لم تكن مربوطةً بمشهدٍ بعينه. `raster_cdse_tile_runtime.py:101` يبني نافذة `LATEST_WINDOW_DAYS` (٣٦٥ افتراضاً) ويُسلّمها إلى `process_index`، وهو يُرسِل `mosaickingOrder=leastCC` (`cdse_client.py:550`) — فالمعروض **أقلّ المشاهد غيوماً في سنة**، ويُخزَّن ساعةً تحت مفتاح كاش مبنيّ على `today` (تاريخ الطلب، `:153`) بلا شاهد على تاريخ البكسلات.
- **ولمَ هو عطل لا خيار — المسار النظير حلّه سلفاً:** `raster_cdse_processing.py:61-95` يبحث الكتالوج ثمّ `scene_policy.rank_scenes` ثمّ يضيّق إلى يوم المشهد، وتعليل كاتبه بلفظه: *"Process API may return a least-cloud mosaic from the lookback window while we persist acquisition_date=time_to (today), making available-dates and selected tile dates point at the wrong COG."* والشريط الزمنيّ يُغذّى من هذا المسار المُصلَح — فالخريطة الحيّة والشريط قد يعرضان **بكسلات يومَين مختلفين** تحت الاسم نفسه.
- **الإصلاح:** `window_spans_multiple_days` + `bind_scene_day_window` (نقيّتان) في `raster_cdse_tile_runtime.py`، موصولتان في `ensure_field_cog` **بعد فحص الكاش** وحده (فلا نداء شبكيّ على إصابة كاش). ورُفِعت `day_window` من مُغلَق داخل `raster_cdse_processing` إلى `raster_date_geo.day_window` ليستهلكها المساران من سلطة واحدة بدل نسخةٍ تنحرف. و`MAX_CLOUD_PCT` ثابتٌ واحد للبحث والمعالجة — سقفان مختلفان كانا سيربطان بيوم مشهدٍ ترفضه المعالجة.
- **يفشل مفتوحاً عمداً:** انقطاع الكتالوج أو غياب تاريخ صالح ⇒ النافذة كما جاءت (سلوك ما قبل الشريحة بالضبط). الربط تحسينُ صدقٍ لا شرطُ صلاحيّة؛ وإغلاقه كان سيُحوّل عطلاً في التسمية إلى بلاطة مفقودة.
- **البرهان:** `tests_v9/test_cdse_latest_scene_day_binding.py` (١٢ حالة، مُعلَّمة `unit` وفي `testpaths` فتعمل في البوّابة فعلاً). **مُثبَت بالتكذيب في ثلاثة اتّجاهات:** استبدال `rank_scenes` بـ`scenes[0]` يُسقِط حالتين · جعل `window_spans_multiple_days` تُعيد `True` دائماً يُسقِط حالتين (وهو الاتّجاه الذي يمنع إعادة تفسير تاريخ صريح) · إعادة `best.get("properties", {})` تُسقِط حالة.
- **عطبٌ في اختباري كشفه التكذيب لا القراءة:** أوّل صياغة لحالة `properties: None` وضعت `datetime` عُلويّاً أيضاً — و`or` تقصر الدارة فلا تُقرأ `properties` إطلاقاً. فالحالة كانت **خضراء عن سؤال لم يُطرَح**، ولم تحمرّ عند زرع العطب. صُحّحت بإسقاط التاريخ العُلويّ.
- **حدّ صدق مقيس:** التاريخ المربوط يُسجَّل في السجلّ ولا يُخرَج في عقد استجابة البلاطة (النقطة تُعيد بايتات صورة). فالشاهد اليوم تشغيليّ لا تعاقديّ.
- **دَينُ انتقال مُعلَن (لا سلوكٌ نهائيّ):** `fail-open` هنا يُبقي التوافريّة على حساب الدلالة — انقطاع الكتالوج ⇒ نافذة ٣٦٥ يوماً بـ`leastCC` تُقدَّم **باسم latest**. أي أنّه يُلفِّق دلالةً عند العطل. أُبقِي في هذه الشريحة عمداً لتضييق نصف قطر الأثر، ويُغلَق في `IMAGERY-LATEST-SELECTION-SEMANTICS-02` بـ«تدهور توافريّة مقبول، تلفيقٌ دلاليّ غير مقبول».
- **المصدر:** قياس مباشر على `main` عند `21179b7f`؛ وتصحيح النطاق من مراجعة المالك 2026-08-16.

## IMAGERY-LATEST-SELECTION-SEMANTICS-02 — FIXED_IN_CODE (P1) 2026-08-16

سلطتان مختلفتان كان النظام يخلطهما في واحدة: **«أحدث اكتساب مقبول»** و**«أعلى جودة»**. الخلط هو الجذر، وتضييق النافذة (`…-BINDING-01`) لا يمسّه.

- **١) `search_scenes` يدّعي ترتيباً لا يفعله — تعليقان لا واحد.** `cdse_client.py:696-697` («Client-side date sorting is applied below after features are received») و`:713-715` («Client-side cloud/date sorting still happens below»). والمقيس: `return filtered` بلا أيّ `sort` في الدالّة. فالتعليق يصف سلوكاً غير موجود — وهو صنف «ادّعاء بلا شاهد» نفسه، وقد بُنِيت `bind_scene_day_window` فوقه.
- **٢) لا ترقيم صفحات.** `data.get("features")` فقط؛ `context.next` **صفر إشارة** في الملفّ، وكتالوج Sentinel Hub مُرقَّم رسميّاً. مع `limit=10` على نافذة ٣٦٥ يوماً يصير الناتج «أفضل مشهد من صفحةٍ جزئيّة صادف أن أعادها المزوّد» — لا الأحدث ولا الأفضل في السنة.
- **٣) `rank_scenes` ليست سياسة حداثة.** الأوزان المقيسة (`scene_policy.py:142-148`): `0.50` سحاب · `0.20` حداثة · `0.20` تغطية · `0.10` جودة مزوّد − عقوبة زاوية. فمشهدٌ **أقدم وأنظف يهزم الأحدث** بالتصميم — سلوكٌ صحيح لـ«أفضل جودة»، وخاطئ لـ«الأحدث».
- **٤) `mosaickingOrder=leastCC` ليست دلالة الحداثة.** هي ترتيب فسيفساء بأقلّ غيوم على بيانات وصفيّة لبلاطةٍ تقارب ١٢٬٠٠٠ كم²؛ ودلالة الحداثة الرسميّة `mostRecent`. (مصدر: وثائق Copernicus/Sentinel Hub — مراجعة المالك 2026-08-16؛ **لم أتحقّق منها بنداء حيّ**، فهي مصدر خارجيّ لا قياس عندي.)
- **٥) المسار النظير يحمل العطل نفسه.** `raster_cdse_processing.py:81-86` يربط تاريخ الاكتساب بـ`rank_scenes(...)[0]`. فتوحيدُ المسارين في `…-BINDING-01` تكافؤٌ صحيح على **دلالةٍ خاطئة**؛ وإصلاح المسار الحيّ وحده يُعيد التناقض من الجهة الأخرى.
- **العقد المقصود:** `LATEST_ACCEPTABLE` = أحدث اكتساب زمنيّاً **من** المشاهد المجتازة لشروط أهليّة صريحة · `BEST_QUALITY` = أعلى `scene_quality_score`. منتقٍ واحد مركزيّ `select_scene(policy=…)` يستهلكه المساران، ولا تُستعمَل `rank_scenes` لتنفيذ الأوّل.
- **الإصلاح:** `scene_policy.select_scene(policy=…)` منتقٍ مركزيّ وحيد يُعيد `SelectedScene` (هويّة + تاريخ اكتساب + غيوم + مصدرها + السياسة ونسختها) لا `tuple` تفقد المنشأ · `SceneSelectionPolicy.LATEST_ACCEPTABLE` ترتيب زمنيّ تنازليّ بعد سقف الغيوم مع كسر تعادل حتميّ (الأنظف ثمّ المعرّف) · `BEST_QUALITY` تبقى على `rank_scenes` · ترقيم صفحات `context.next` في `search_scenes` بسقف `_CATALOG_MAX_PAGES=10` **يُعلَن اقتطاعُه** · `process_index` صار يقبل `mosaicking_order` مُتحقَّقاً منه (`mostRecent` لمسار الحداثة) ويرفض المجهول بدل تمريره · والمساران — الحيّ والمُدام — يستهلكان المنتقي نفسه.
- **والاستجواب صار من الأحدث إلى الأقدم** (`backward_probe_windows`، خطوة ٣٠ يوماً افتراضاً): ليس توفيراً في الكلفة بل **شرطُ إثبات**. مع سقف الصفحات وترتيبِ مزوّدٍ غير موثَّق، قد يُسقِط الاقتطاع أحدثَ مشهدٍ نفسه؛ أمّا حين تُستجوَب أحدثُ نافذة أوّلاً فأيّ مشهد مؤهَّل فيها **أحدث بالضرورة** ممّا في الأقدم. هذه النقطة لم تكن في تصميمي الأوّل — أضفتُها بعد أن كشف القياسُ أنّ الترقيم وحده لا يجعل الادّعاء قابلاً للإثبات.
- **البرهان:** `tests_v9/test_cdse_latest_selection_semantics.py` (٢٠ حالة) + تحديث `…_scene_day_binding.py` (١٢). **مُكذَّبة في خمسة اتّجاهات:** تنفيذ `LATEST` بـ`rank_scenes()[0]` · تجاهل الصفحة الثانية · إبقاء `leastCC` بعد الربط · إلغاء تقسيم النوافذ · عدم التوقّف عند أوّل نافذة مُثمِرة.
- **وعطبان في اختباراتي كشفهما الزرع لا القراءة:** حارس «المسار المُدام لا ينتقي بالجودة» طابق **تعليقي أنا** لا الكود (يقرأ الكود بلا تعليقات الآن) · وحالة تقسيم النوافذ كانت تمرّ على تنفيذٍ يُعيد نافذةً واحدة (أُضيف `len(windows) > 1`).
- **ما لم يُغلَق بعد (مُعلَن لا مسكوت عنه):** الإيصال يُسجَّل ولا يُنشَر في ترويسات الاستجابة (`X-SAHOOL-Acquisition-Date` وأخواتها) · هويّة الكاش ما زالت `today` لا `scene_id` فتُنتَج نسختان لنفس المشهد · و`fail-open` ما زال يُقدّم نافذةً واسعة باسم latest عند العطل. الثلاثة أثرُها **عرض/كلفة/توافريّة** لا اختيارٌ خاطئ، فبقيت خارج هذه الشريحة عمداً.
- **المصدر:** مراجعة المالك 2026-08-16 على `426ea0f9`، ونقاطها ١–٣ و٥ **مُعاد قياسها في الشجرة** قبل القبول؛ والنقطة ٤ (`leastCC` مقابل `mostRecent`) مصدرٌ خارجيّ (وثائق Copernicus) **لم أتحقّق منه بنداء حيّ**.

## REGENERATION-ORCHESTRATOR-CLAIMED-COVERAGE-IT-LACKED-01 — FIXED_IN_CODE (P2) 2026-08-16

> **أُغلِقت على main في #860 بنسخةٍ أشمل من نسختي، فأُخِذت نسختُهم.** تُنفِذ `git add` داخل المكنسة بدل التوصية به، وتفصل الفحص النهائيّ في **عمليّة نظيفة بعد آخر بناءٍ للحزمة** — فتُمسَك حالة «الحزمة تغيّرت ولم تُعَد الخريطة بعدها» بالبناء لا بالانضباط. وقياسهم يسمّي ٧١ خطوة تكتشفها المكنسة مقابل الثلاث التي كان يغطّيها.

- **العلّة:** `scripts/ci/regenerate_all_generated.sh` أعلن في ترويسته أنّه يُعيد توليد «**every** committed generated artifact … so you don't chase CI drift one gate at a time»، وختم بـ«verify: everything is now self-consistent». **والمقيس: ثلاثة مولّدات من نحو تسعة وثلاثين** (`generate_service_inventory` · `route_mount_contract_guard` · حزمة الإصدار).
- **وقاعدةٌ مكتوبة تُحيل إليه:** `sahool-brain/log.md` يقول «أيّ تغيير يمسّ المسارات/الخدمات/التبعيّات ⇒ شغّل هذا قبل الدفع». فمن اتّبعها نال خضرةً صادقة عن ثلاث بوّابات ثمّ أسقطته CI على البقيّة **واحدةً تلو الأخرى** — وهو عين ما وُعِد بتفاديه.
- **الأثر المقيس في هذه الجلسة:** أربع جولات CI حمراء متتالية على مولّدات مختلفة (الحزمة · الخريطة · الرابط/التتبّع · تدقيق التنفيذ · عقود التشغيل · سلالة القرار · مِرقاب التحقّق). ولمّا شُغّلت المكنسة الحقيقيّة `verify_all_generated.py --fix` أصلحت **ستّ مصنوعات إضافيّة لم أبلغها يدويّاً** (منها `fake_connection_debt.json` و`source_text_assertion_inventory.json` و`compose_runtime_targets.json` و`runtime_evidence_ledger.json`).
- **صنفه:** «ادّعاءٌ أوسع ممّا قِيس» — نظير تعليق الترتيب في `cdse_client` الذي أُصلح في الشريحة نفسها. والأخطر أنّه هنا **في الأداة المُوكَل إليها منع هذا الصنف**.
- **الإصلاح:** السكربت صار **مُحوِّلاً** إلى `verify_all_generated.py` (يكتشف القائمة من الـworkflows، يرتّب بالتبعيّة، يُكرّر حتّى الثبات، ويُعلن غير المُولَّد آليّاً بدل تخطّيه). الاسم يبقى مدخلاً لأنّ العادات والسجلّ يُحيلان إليه — لكنّ السلطة واحدة لا اثنتان تنحرفان.
- **حدّ صدق:** لا يُغلق هذا سبب الفشل الحقيقيّ عندي — وهو أنّي شغّلتُ `preflight.sh --fast` وقرأتُ خضرتَه أوسع ممّا قاست، والسكربت نفسه يطبع تحتها «الجناحان والمكنسة **لم يُشغَّلا**. لا تدفع على هذا وحده».
- **المصدر:** مراجعة المالك 2026-08-16 (سمّت الفجوة)، وقياسٌ مباشر للتغطية: عدّ المولّدات المُعلِنة `--generate/--apply` مقابل المذكورة في السكربت.

## DECISION-LINEAGE-LEXICAL-CROSS-DOMAIN-FALSE-POSITIVE-01 — OPEN (P2) 2026-08-16

- **العلّة:** `scripts/ci/decision_lineage_graph.py:29` يُصنّف مراحل سلالة القرار بتعبير نمطيّ عامّ يُطبَّق على **نصّ الملفّ كاملاً** تحت `services/` — لا على رموز ولا على عقود نطاق. فورودُ الكلمة **مرّةً واحدة في أيّ سياق** يجعل الملفّ **كلّه** شاهداً على تلك المرحلة.
- **الدليل المقيس (وقع فعلاً في هذه الشريحة):** متغيّر محلّيّ في `scene_policy.select_scene` حمل اسم مرحلة الترشيح، فدخل `services/raster-service/scene_policy.py` في `decision_lineage_graph.json` تحت `nodes[1].repository_evidence[102]` — أي أنّ **اختيار مشهد Sentinel صار دليلاً على محرّك القرار** بتطابقٍ نصّيّ بحت.
- **وبصمة الانحراف تُميّزه عن تغيّر مشروع:** انحرفت `graph.json` و`nodes.csv` و`REPORT.md` بينما **لم تنحرف** `edges.csv` ولا `summary.json` — أي تغيّر عددِ شواهد عقدة بلا أيّ علاقة قرار جديدة. هذه بصمة تلوّثٍ معجميّ لا سلالة جديدة.
- **الإصلاح هنا ضيّق عمداً:** أُعيدت تسمية المتغيّر إلى `ranked_scene`، ثمّ أُعيد توليد السلالة **لإزالة** الشاهد الكاذب لا لتثبيته (الفرق مهمّ: المصنوعة كانت مُلوَّثة سلفاً في الشجرة، فإعادةُ التوليد بعد التسمية تحذف السطر ولا تُرسّخه). الفرق سطرٌ واحد محذوف.
- **ودرسٌ من المحاولة الأولى:** أوّل تعليق كتبتُه لشرح العطل **حمل الكلمة المُطلِقة نفسها**، فبقي الملفّ مُصنَّفاً وبقي الحارس أخضر كاذباً — الماسح لا يُميّز التعليق من الكود. فأُعيدت صياغة الشرح بلا الكلمة.
- **لمَ تبقى مفتوحة:** الإصلاح عالج **حالةً واحدة**. الماسح ما زال يقبل أيّ ورود لكلمات المراحل في أيّ ملفّ تحت `services/`، فالعطل يتكرّر مع أسماء مشروعة تماماً في نطاقات أخرى. العقد الأقوى (مطابقة رموز/سياق أو إشارات واعية بالنطاق بدل `search` على النصّ) قرارُ مالك المولِّد.
- **المصدر:** مراجعة المالك 2026-08-16، **وأُعيد قياسها في الشجرة**: العقدة `nodes[1].stage == "candidate"`، وحذفُ الاسم وحده أسقط الشاهد.

## CAPABILITY-EVIDENCE-LISTS-TRUNCATE-SILENTLY-01 — FIXED_IN_CODE (P2) 2026-08-16

> **أُغلِقت على main في #860 لا هنا.** جلسةٌ أخرى أخذت هذا المعرّف وأصلحت السقف بإعلانٍ صريح: `cap_evidence_dimensions` تُبقي السقف مئةً وتكتب `evidence_truncated` بعدد المحذوف لكلّ بُعدٍ قُصّ، بترتيب حتميّ فيستقرّ الباقي. **وقياسُهم تجاوز قياسي**: بعد الإعلان ظهر أنّ `SEC-001.database` كان يُسقط **٧٤٣** شاهداً صامتاً — لا شاهدَين. يبقى هذا السجلّ لأنّه يحمل القياس الأصليّ وسببَ الاكتشاف؛ والسقف نفسه لم يُرفَع (قرار أساس مستقلّ).
>
> **وشقُّ سجلّ الحقيقة أُغلِق بعده (2026-08-16، هذه الشريحة):** `capability_linker` صار يكتب `evidence_truncated` باسم البُعد وعدد المحذوف، والحقل **مُصرَّح به في المخطَّط** (`capabilities/schema/capability-registry.schema.json`، و`additionalProperties: false` كان سيرفضه بلا تصريح). ويُحذَف الحقل عند زوال القصّ — فحقلٌ باقٍ بقيمة قديمة أسوأ من غيابه.
>
> **والمقيس بعد الإعلان أكبر ممّا قدّرتُ بمرّات: ٤٩٤ شاهداً** كانت تُحذَف صامتاً عبر ثمانِ قدرات — `FM-003` وحدها **٢٠٠ واجهة و٩٦ اختباراً**، و`SAT-009` **٥٧ و٩٤**. وقياسي الأصليّ كان شاهدَين. والأبعاد المقصوصة **خمسة** (`services` ٨ · `apis` ٤٠ · `tests` ٢٥ · `ui_consumers` ٢٠ · `mobile_consumers` ٢٠) لا واحداً كما ظننت.
>
> **السقوف لم تُرفَع** (قرار أساس مستقلّ): المطلوب أن يُعلن السجلّ نقصانَه لا أن يُخفيه بسقفٍ أوسع. والقصّ ما زال **أبجديّاً** — أي أنّ *أيّ* شاهدٍ يبقى تقرّره صدفةُ الاسم؛ ما تغيّر أنّ ذلك صار **مرئيّاً**. ترتيبٌ دلاليّ (بالحداثة أو الصلة) شريحةٌ تالية.
>
> **البرهان:** `tests/architecture/test_capability_linker.py` — حالتان مُكذَّبتان بالزرع: إسقاط الإعلان يُحمِّر «بُعدٌ بلغ سقفه بلا إعلان»، وحذف التصريح من المخطَّط يُحمِّر حارس العقد.

- **العلّة:** `scripts/ci/capability_mapping_engine.py:549` يقصّ كلّ قائمة شواهد إلى **مئة عنصر** (`dedup(rec[k], "value")[:100]`) **بلا أيّ إعلان للاقتطاع**. فالقائمة المُولَّدة تُقرأ «كلّ الشواهد» وهي في الحقيقة «أوّل مئة».
- **كيف انكشفت (لا بقراءة بل بأثر):** إضافة ملفَّي اختبار في هذه الشريحة أدخلتهما ضمن شواهد **SAT-003 (NDVI)** — وهي عند السقف تماماً (`tests: 100`) — فخرج `tests_v9/test_field_state_unification.py` من `capability_evidence_matrix.json` بصمت. أي أنّ **إضافة اختبار أسقطت شاهدَ اختبارٍ قائم** من مصنوعة حوكمة.
- **لمَ تهمّ:** ثلاث قوائم عند السقف في SAT-003 وحدها (`backend` · `events` · `tests`). ومصنوعات القدرات تُستعمَل في التتبّع والاعتماد، فاقتطاعٌ صامت يجعل «لا شاهد» و«شاهدٌ خارج المئة» متطابقَين في القراءة.
- **لم تُصلَح هنا عمداً:** الملفّ داخل مسار سجلّ القدرات الذي تملكه جلسة أخرى (`scripts/ci/capability_*.py`)، وإصلاحه قرار مالكه: إمّا رفع السقف، أو إعلان `truncated: true` وعدد المحذوف، أو ترتيب حتميّ يُبقي الأقدم. تعديلُه من هنا كان سيصطدم بعملٍ جارٍ.
- **والحالة الأشدّ — الاقتطاع يبلغ سجلّ الحقيقة نفسه لا المصنوعات فقط:** `scripts/ci/capability_linker.py:500-506` يكتب `cap["tests"] = uniq(tests, 25)` و`uniq` هي `sorted(dict.fromkeys(values))[:limit]` — أي **اقتطاعٌ أبجديّ**. فبقاء الشاهد في `capabilities/registry/capabilities.json` تقرّره **صدفةُ اسم الملفّ** لا صلتُه ولا حداثتُه.
- **بالأسماء لا بالعدد:** ملفّاي `test_cdse_latest_*` يسبقان أبجديّاً، فدخلا شواهد SAT-001 وأخرجا اثنين قائمَين من **السجلّ**: `tests_v9/test_normalized_scene_wiring_v63_2.py` و`tests_v9/test_raster_scene_model_v63.py`. وكلاهما اختبار حيّ يمرّ اليوم.
- **ولمَ طُبِّق رغم ذلك:** `capability_compatibility_roundtrip_guard` يحجب الدمج ما لم يتقارب الرابط، والتقارب **يستلزم** هذه الكتابة. فالخيار كان بين بوّابة حمراء وسجلٍّ يفقد شاهدَين — وطُبِّق التقارب **مع تسمية الفقد هنا** بدل ابتلاعه. القرار في السقف لمالك المسار: رفعُه، أو ترتيبٌ يُبقي الأقدم، أو إعلان `truncated` وعدد المحذوف.
- **السقفان مقيسان:** ٢٥ في السجلّ (`capability_linker.py:506`) · ١٠٠ في الخريطة (`capability_mapping_engine.py:549`).
- **المصدر:** قياس مباشر 2026-08-16 على `0560c74d` — `capability_mapping.json` يُظهر `len(tests) == 100` لـSAT-003، والفرق المولَّد يُظهر دخول ملفَّين وخروج واحد.

## DECLARATION-DERIVED-BEFORE-COMMIT-01 — FIXED_IN_CODE (P2) 2026-08-16

- **العلّة:** `pr_capability_impact_gate` يشتقّ الأثر من `git diff base..head` — مراجعُ **ملتزَمة** حصراً. فاشتقاقُ سطر `Capability-Impact` بينما في الشجرة تعديلٌ غير ملتزَم يُنتج جواباً عن شجرةٍ أخرى غير التي تقيسها CI، **بلا أيّ إشارة**.
- **وقع فعليّاً في #859:** اشتُقّ السطر بعد `git add -A` وقبل الالتزام، فلم تدخل المصنوعات التي أعادت المكنسةُ توليدها في الفرق، فسقطت `FM-001` و`OPS-003` وحجبت البوّابة. والتصحيح كلّف جولة CI كاملة.
- **صنفه:** نظير `REGENERATED-FROM-AN-UNRESOLVED-INDEX-01` **معكوساً** — هناك يُولَّد من فهرس ناقص، وهنا **يُشتقّ ادّعاءٌ من فهرسٍ يسبق الالتزام**. والجامع بينهما: فعلٌ يقرأ حالةً غير التي يظنّها فاعلُه.
- **الإصلاح:** `worktree_deviation()` (نقيّة، تقرأ `git status --porcelain`) + رفضٌ **مغلَق** برمز `2` حين يكون `--head` نسخةَ العمل وفيها انحراف، مع رسالةٍ تسمّي المنحرف وتقول لماذا. و`--allow-dirty-tree` رخصةٌ صريحة للاستكشاف — **لا يُبنى عليها إعلان**. ولا أثر على CI: شجرتها نظيفة بحكم الـcheckout.
- **حدّ مقصود:** المرجع التاريخيّ الصريح (SHA لا `HEAD`) لا يُبلَّغ عنه انحراف — السؤال حينها تاريخيّ لا حاليّ، ومقارنةُ الشجرة به بلا معنى.
- **البرهان:** `tests/architecture/test_pr_capability_impact_gate.py` على **مستودع git حقيقيّ مؤقّت** لا محاكاة: نظيف ⇒ `[]` · مُدرَجٌ غير ملتزَم ⇒ يُسمّى · غير مُدرَج ⇒ يُسمّى · مرجع تاريخيّ ⇒ `[]`. **مُكذَّب بالزرع:** تعطيل مقارنة الرأس يُحمِّره.
- **المصدر:** مراجعة المالك 2026-08-16 (بندٌ سابع خارج ترتيب الإغلاق)، وقياسٌ مباشر لسبب حجب #859.

## RASTER-SERVICE-TESTS-UNWIRED-TO-CI-01 — CLOSED (2026-08-19) — كان OPEN (P2) منذ 2026-08-16

- **ما أغلقها:** وظيفة `raster-service-tests` في [`ci.yml`](../../.github/workflows/ci.yml) تُشغّل `pytest -q -p no:cacheprovider test_*.py` بـ`working-directory: services/raster-service` — نمطٌ **شامل** يجمع الملفّات الإحدى والسبعين كلّها، ومنها الثلاثة التي سُمّيت أدناه دليلاً على السبات: `test_cdse_empty_raster_not_cached.py` و`test_persisted_thumbnail_path.py` و`test_cdse_poly_contract.py`. أي أنّ **مسار الجمع** — وهو علّة الفجوة بعينها — صار يبلغها.
- **والشرط الذي أخّر الإغلاق استُوفي:** الوظيفة تُثبّت تبعيّاتها بنفسها (`pip install -r services/raster-service/requirements.txt pytest pytest-asyncio Pillow`)، فلم يعد الوصل مشروطاً بإدخال `rasterio` إلى وظيفة الوحدة.
- **دليلٌ حيّ لا قراءةُ YAML:** الوظيفة خضراء بالاسم في جولة `32311551455` على الرأس `733d4c04`.
- **حدُّ صدق:** الفجوة كانت مُصلَحةً في الشجرة منذ شريحة 2026-08-18 (د) وبقي صفُّها هنا `OPEN` — أي أنّ الجرد نفسه كان يكذب ثلاثة أيّام. صُحِّح عند قياسه لا عند كتابته، وهذا هو الفرق.

<details><summary>النصّ الأصليّ للفجوة (محفوظ)</summary>

- **العلّة:** ملفّات `services/raster-service/test_*.py` **لا يجمعها** `pytest.ini` (`testpaths = tests_v9`)، ولا يُشغّلها إلّا `.github/workflows/raster-validated-product.yml` بقائمة **مسارات صريحة** من أربعة ملفّات. فكلّ ملفّ اختبار خارج تلك القائمة ميّتٌ في البوّابة.
- **الدليل المقيس:** `grep` على `.github/workflows/` و`scripts/` لأسماء `test_cdse_empty_raster_not_cached` · `test_persisted_thumbnail_path` · `test_cdse_poly_contract` ⇒ **صفر مطابقة**. والأوّل منها هو «برهان الوصل» المُعلَن لـ`IMAGERY-BLANK-THUMBNAIL-01` أعلاه — أي أنّ برهان إغلاق فجوة لم يُنفَّذ في CI مرّةً.
- **صنفه:** نظير `UNIT-TEST-DORMANCY-01` و`TESTS-UNMARKED-DESELECTED-01` بآليّة ثالثة: لا العلامة ولا التبعيّة، بل **مسار الجمع**.
- **لمَ لم يُغلَق هنا:** وصلُ الجناح يتطلّب `rasterio`/`rioxarray` في الوظيفة (غير مثبَّتة في *Unit Tests*)، فهو شريحة بذاتها لا ذيلٌ لشريحة ربط النافذة. وتفادياً للسبات وُضِع برهان `IMAGERY-LATEST-UNBOUND-TO-A-SCENE-DAY-01` في `tests_v9/` بلا اعتماد على `rasterio`.
- **المصدر:** قياس مباشر 2026-08-16 على `main` عند `21179b7f`.

</details>

#### BUG-1B: صياغتي «عيب photometric» **مُكذَّبة** بإعادة الإنتاج (2026-07-28)

- **ما جرى:** شرعتُ في تنفيذ BUG-1B على فرض أنّ الكتابة الخام تُنتج وسوم تفسير لون متناقضة، وبنيتُ مُطبِّعاً يمرّر الملفّ عبر `write_rgba_cog`. **إعادة الإنتاج أسقطت الفرض:** GDAL يكتب `PHOTOMETRIC=RGB` (وسم TIFF 262 = 2) **تلقائيّاً** لأيّ ملفّ ٣-٤ نطاقات uint8 حتّى بلا تمرير `photometric`. فالكتابة الخام وحدها **لا تُنتج** العيب.
- **ما كان عيب #660 فعلاً:** التفاعل المحدَّد «`RGBA_COG_PROFILE` بلا مفتاح `photometric` **مع** ضبط `dst.colorinterp` بعد الإنشاء» ⇒ GDAL يكتب MINISBLACK. ليس مجرّد غياب الكاتب.
- **الفرق الحقيقيّ المقيس بين المسارين:** ليس تفسير اللون بل **البنية** — المسار الحيّ يُنتج ملفّاً بلا أهرامات وبلا ضغط (`overviews=[]`, `compression=none`)، مقابل `[2,4,8,16]` + DEFLATE من الكاتب. خاصّيّة أداء (كلّ تصيير يقرأ الدقّة الكاملة)، **لا** سبب المصغّرات الفارغة.
- **القرار:** لم يُشحَن شيء. مُطبِّع لعيب لا يمكن إظهاره هو كود ميت يحمل ادّعاءً. **تُعاد صياغة BUG-1B إلى: «المسار الحيّ لا يُنتج بنية COG (أهرامات/ضغط)»** — بند أداء يُقيَّم على حدة، لا استمرار لـBUG-1.

#### تقاطع تنفيذين مستقلّين للفحص نفسه (2026-07-28) — الفارق تغطية لا سلوك

- **المصدر:** لقطة `sahool_imagery_empty_raster_cache_guard_delta_20260728.zip` (أساسها `121ab09`) تحمل تنفيذاً مستقلّاً لـ`raster_has_observable_content` بتوقيع مختلف: `(raster_path, index)` يقرّر مسار الألفا **باسم المؤشّر**، مقابل تنفيذنا `(cog_path)` الذي يقرّره **بالبنية** (‏`count >= 4` و`dtype == uint8`).
- **قياس مباشر لا مقارنة نصّيّة:** شُغّل التنفيذان على **٧ حالات** بُنيت كملفّات راستر حقيقيّة (RGB صالح · RGB بقناع كلّه صفر · مؤشّر محدود خلف قناع باطل · RGBA بألفا صفر · RGBA ببكسل معتم واحد · كلّه NaN · nodata كامل). **النتيجة متطابقة في السبع** ⇒ لا تصحيح سلوكيّ يُستورَد.
- **ولمَ لا يُستورَد التوقيع:** وسيط `index` يُكرّر سلطة `cdse_client.is_truecolor` بقائمة مكتوبة `{truecolor, true_color, rgb, rgba}` تختلف عنها في الاتّجاهين (تقبل `rgb`/`rgba` وترفض `true-color` لأنّها لا تطبّع الشرطات). سلطة مُكرَّرة تنحرف؛ والبنية تُغني عنها هنا فعلاً.
- **ما استُخرِج (وهو الفارق الحقيقيّ): ٤ حالات كانت بلا حارس عندنا.** ثلاثة على القناع الداخليّ وRGB بلا ألفا (‏`write_mask` سلطة صلاحيّة ثالثة لا تكتبها أيّ حالة سابقة عندنا، ومسار ٣ نطاقات لم يكن مقيساً إطلاقاً) وواحدة على المسار الموصول ببايتات تالفة.
- **لمَ تهمّ:** تنفيذنا **صحيح في الثلاث بالتبعيّة** — من دلالة `read(1, masked=True)` التي تطبّق قناع المجموعة — لا بفرع مكتوب لها. **مُثبَت بالتكذيب:** استبدالها بـ`src.read(1)` («تبسيط» معقول) يُسقط الحالتين الجديدتين ويُبقي الإحدى عشرة القديمة **خضراء**.
- **حدّ مقيس على الحالة الرابعة:** اختبار البايتات التالفة **لا** يحرس مظروف `try/except` حول فحص المحتوى — إزالته تُبقيه أخضر لأنّ `except` الخارجيّ لـ`ensure_field_cog` يبتلع الاستثناء. سُجِّل الحدّ في docstring الاختبار بدل تركه يوحي بضمانة لا يملكها.
- **ما يبقى مطلوباً لأيّ ادّعاء عن تفسير اللون:** أصل CDSE حقيقيّ + `gdalinfo` عليه. تحذير `TIFFReadDirectory` الذي رآه المالك حقيقيّ، لكنّ مصدره لم يُعزَل بعد — وهو ما جعل BUG-1 «تحقيقاً لا إصلاحاً معروفاً» منذ البداية.
- **درس:** أوّل فحص كتبتُه استعمل `colorinterp` — وGDAL **يستنتجه** فيمرّ على ملفّ خام. الفحص الصادق يقرأ وسم 262 من البايتات، وهو ما يفعله `test_rgba_cog_photometric.py` سلفاً. فحص مبنيّ على قيمة مُستنتَجة يُخفي بالضبط ما جاء يكشفه.

### تقدّم (2026-07-28): فصل بطاقة السجلّ الزمنيّ عن الاكتشاف الحيّ

- **الجذر:** بطاقة تُعلن `has_cog=true` (مُشتَقّ في SQL من وجود `cog_uri` غير فارغ، `db_persist.py:932`) كان رابطها يبني نقطةً **تُعيد تنفيذ اكتشاف حيّ** عبر `ensure_field_cog` — فلا تُقرأ من الأصل الذي ادّعت البطاقة وجوده. وهذا ما جعل توسيع النافذة (`±3 أيّام`) خطراً: مشهد تاريخ آخر يُعرَض تحت التاريخ المطلوب = خرق نَسَب لا يُصلحه امتلاء الصورة.
- **المُنجَز:** `?source=persisted` على النقطة القائمة (**بلا مسار جديد** — الميزانية ثابتة عند 627/629) يحلّ `raster_assets` عبر `fetch_latest_asset` (`asset_status='ready'`، مقيَّد بالمستأجِر، تاريخ مطابق **بالضبط**) ويصيّر من `cog_uri`. **صفر نداء CDSE في كلّ الفروع**؛ الغياب/غياب الملفّ/التلف كلّها `X-Imagery-State: unavailable` — لا استبدال بمشهد قريب ولا اشتقاق حيّ. النجاح يحمل `X-Acquisition-Date` (نَسَب قابل للفحص من العميل). المنصّة تُلحق `&source=persisted` عند `has_cog`.
- **البرهان:** ٦ اختبارات قبول تقود المعالِج الحقيقيّ وتقطع كلّ منافذ CDSE (أيّ نداء ⇒ `AssertionError`). **مُثبَت بالتكذيب:** إعادة الفرع إلى المسار الحيّ تُسقِط ٥ من ٦ فوراً.
- **حدّ الصدق:** يُغلق **مسار العرض** فقط. `X-Imagery-State` مُعلَنة وغير مُستهلَكة بعد — حالات UI الصريحة شريحة مستقلّة، و`display:none` ما زال قائماً في `MapHub.tsx`. وBUG-1A/1B ونافذة الاكتشاف تبقى مفتوحة.

### تقدّم (2026-07-28): الحالة صارت مرئيّة — الفشل لم يعد فراغاً

- **الجذر (BUG-4/BUG-5):** `onError` كان يضبط `style.display = 'none'` فيتحوّل كلّ فشل إلى مربّع فارغ، وتاريخ المزوّد المعلّق (`has_cog=false`) لم يكن يعرض عنصراً أصلاً. الحالتان تبدوان متطابقتين للمستخدم وهما مختلفتان تماماً: واحدة تُعالَج الآن، والأخرى أصل مُعلَن تعذّر تقديمه.
- **قيد تقنيّ حاسم اكتُشِف:** عنصر `<img>` **لا يقرأ ترويسات الاستجابة**. فـ`X-Imagery-State` فوق 200 + PNG شفّاف كانت تُنتج بالضبط ما جئنا نُنهيه. لذلك `unavailable` صار **404** في المسار المُدَام — الإشارة الوحيدة التي تصل الواجهة عبر `onError`، وهي صادقة (المورد المُعلَن غير قابل للتقديم). الترويسة تبقى للفاحص البرمجيّ. المسار الحيّ (`auto`) بلا تغيير عقد.
- **المُنجَز:** `frontend/src/components/maphub/ImageryTimelineThumb.tsx` — ثلاث حالات مُعلَنة: `pending` («قيد المعالجة») · `ready` · `failed` («تعذّر العرض»). تبدّل الرابط يُعيد الحالة فلا تُورَّث حالة فشل لصورة أخرى.
- **البرهان:** ٧ اختبارات مكوّن + تثبيت رمز الحالة في ٦ اختبارات الخلفيّة. **مُثبَت بالتكذيب من الطرفين:** إعادة الخلفيّة إلى 200 تُسقِط ٣ اختبارات، وإعادة `display:none` تُسقِط ٣ أخرى. حزمة الواجهة **1300/1300**.
- **الحرّاس الساكنة تبعت الاستخراج ولم تضعف:** `MapHubHistoricalTimeline` و`MapHubTwoYearBackfill` كانا يؤكّدان نصّ `alt` داخل `MapHub.tsx`؛ صارا يؤكّدان تصيير `<ImageryTimelineThumb` في البطاقة **و**وجود `alt` في المكوّن.
- **حدّ الصدق:** يُغلق **BUG-4 وBUG-5**. لا يزال مفتوحاً: BUG-1A · BUG-1B · نافذة الاكتشاف بـ`acquisition_date` صريح · `SatellitePage.tsx:331` (truecolor مُثبَّت نصّيّاً).

## FIELD-STATE-PRODUCERS-MISSING-01 — PARTIALLY_CLOSED (soil + spectral) / OPEN (weather) 2026-08-01

**تحديث الطيف (2026-08-01) — الغياب كان مُصطنَعاً لا مقيساً.** كان `_compose_canonical` يُمرّر
`spectral=None` **حرفيّاً**، بينما المُنتِج والمُحلِّل قائمان في الشجرة:

- المُنتِج: `core/crop_intelligence/spectral.py` ⇒ `canonical_spectral_state.v1` (والنواة تقبل بادئته: `core/canonical_field_state.py:78`).
- المُحلِّل الخادميّ: كان يعيش داخل `routers/crop_twin.py` وحده، فلا يبلغه هذا المُركِّب.

فالحالة الكنسيّة كانت تُعلن `spectral_missing` لحقولٍ **تُقرأ مؤشّراتها فعلاً**. هذا الصنف
أخطر من «لم يُختبَر حيّاً»: تشغيل اختبار حيّ عليه كان سيُثبِت الغياب ويُسمّيه بيئةً.

- **المُنجَز:** `api/canonical_spectral_state.py` — نظير `canonical_soil_state.py`/`canonical_water_state.py`. المُحلِّل **نُقِل** بلا تغيير سلوك (لا نسخة ثانية)، و`crop_twin` يستورده بالاسم فبقيت اختباراته العاملة بالترقيع خضراء. NDVI سيّد: غيابه ⇒ `None` لا منتَج بمؤشّرات كلّها `None` (ذاك يرفع `availability.spectral` بلا معرفة — التلفيق نفسه بمخطّط صحيح).
- **قفل صدق:** الطيف **ليس** من `required=(weather, water, soil)`، فوصله **لا يرفع** `operational_eligible` — مُقفَل بـ`test_wiring_spectral_cannot_raise_eligibility_on_its_own`. لولاه لقُرِئ الوصل تقدّماً نحو أهليّة لم تتغيّر.
- **التكذيب:** إعادة `spectral=None` ⇒ حارس AST يسقط؛ إرجاع منتَج فارغ بدل `None` ⇒ **٣** اختبارات تسقط. استُعيد الأصل ⇒ **١٨** نجحت.
- **`temporal_compatible=None` عمداً:** التوافق الزمنيّ بين NDMI وMSI ادّعاء لا يملكه هذا المسار؛ تمريره `True` كان سيرفع `water_stress.confirmation_available` بلا دليل ويحوّل قراءتين من مشهدين إلى «تأكيد إجهاد».
- **الراتشِت:** وحدات المنصّة 674 ⇒ 675 بمذكّرة مُعلَّلة على نمط سابقة التربة حرفيّاً.
- **حدّ الصدق:** مُثبَت على مستوى الوحدة بمحاكاة `get_indicator_grid`؛ **لا** برهان تشغيليّ حيّ بأنّ الحقول الحقيقيّة تُرجِع منتَجاً. ⇒ `WIRED_AND_UNIT_PROVEN`، لا `runtime_verified`.

**تصحيح مقيس لسبب بقاء الطقس** (كان الوصف هنا وفي الكود ناقصاً): `POST /v1/weather/agro/canonical-state`
**يُرجِع الغلاف فعلاً** — لكنّه **حاسبة على مدخلات المُستدعي** (`CanonicalWeatherStateRequest`:
`t_max_c`/`rh_mean_pct`/…) لا تجلب شيئاً. والمسارات الجالبة (`current`/`forecast`/`historical`)
تُرجِع **مشاهدات** بلا غلاف. فلا واجهة تُجيب «ما الحالة الكنسيّة لطقس هذا الحقل؟»، وتغذية
الحاسبة من المنصّة كانت ستجعل **المنصّة** هي مَن يؤكّد وقائع الطقس. فالفجوة **`implementation
missing` في خدمة الطقس** لا نقصُ وصلٍ هنا — و`weather=None` محروسة بـAST كي لا تُدسّ حمولة.


- **الأثر الأصليّ:** `canonical_field_state` موصولة (`247c69c`) وكانت تُعيد `operational_eligible=false` **دائماً**.
- **السبب الأصليّ:** من `required=(weather, water, soil)` مُنتِج واحد فقط — الماء (`api/canonical_water_state.py:21`). لا مُنتِج لـ`canonical_soil_state.`/`soil-profile.` (البادئة ترد في قائمة قبول النواة نفسها: `core/canonical_field_state.py:77`) ولا لـ`wx10/canonical-weather-state/`.
- **لماذا مُسجَّل رغم إغلاق الفجوة الأمّ:** الراتشِت يقول 4/4 بصدق (مستهلكون يستوردون الرموز بفحص AST) لكنّه **لا يقول** إنّ الأربع تُنتِج قيمة. فجوة مُغلقة بتحفّظ غير مكتوب هي أوّل خطوة نحو سجلّ يكذب.
- **مُنجَز التربة (2026-07-30):** `api/canonical_soil_state.py` (جديد) — عميل HTTP بنفس نمط `soil_hydraulic_client.py` (ترويستَي `X-Agent-Token`/`X-Tenant-Id`، `SOIL_SERVICE_URL`، لا اختلاق عند أيّ فشل/404/رمز مفقود). يقرأ `GET /v1/fields/{field_id}/soil/profile` من `soil-service` (`services/soil-service/routers/canonical.py:72` ← `profile_composer.compose_snapshot`)، الذي يُصدِر `contract_version: "soil-profile.v1"` أعلى المستوى — مفتاح لا تعرفه `core.canonical_field_state._schema_of()` (تقرأ `schema_version`/`schema` فقط). العميل يُطبِّع بإضافة `schema_version` من `contract_version` **دون حذف الأصل** وإن لم يوجد مفتاح مخطّط أصلاً؛ يُبقي الحمولة كما هي إن وُجد `schema_version`/`schema` مسبقاً.
  - **الوصل:** `api/routers/internal_service.py:_compose_canonical` يستدعي `resolve_canonical_soil_state` بدل `soil=None` الثابتة. الطقس (`weather`) يبقى `None` صراحةً — **قرار معماريّ مؤجَّل عمداً**، لا نسيان: `weather-service/canonical_weather_state.py` (674 سطراً) مُنتِج كامل وموصول فعلاً عبر `POST /v1/weather/agro/canonical-state`، لكنّ نقطتَي `GET /v1/weather/current`/`forecast` الأبسط تُعيدان "views" جزئيّة بلا غلاف `schema_version` — كشف/تعديل عقد HTTP جديد لخدمة الطقس قرار لا يُتّخذ من هذه الجلسة.
  - **البرهان بالتكذيب:** `tests/test_canonical_field_state_wiring.py::test_consumer_sources_soil_from_a_resolver_call_not_a_literal` — حقن `soil={"schema_version": ..., "fake": True}` مكان `soil_payload` ⇒ فشل فوريّ («soil يجب أن يأتي من نتيجة الحلّ»)؛ استعادة الوصل الحقيقيّ ⇒ نجاح. + ٩ اختبارات وحدة جديدة على العميل نفسه (`tests/test_canonical_soil_state.py`، عبر `respx` بلا شبكة): نجاح مع تطبيع المفتاح، إبقاء `schema_version` الموجود دون تكرار، رمز مفقود ⇒ `None` بلا طلب شبكة، 404/500/خطأ اتصال/حمولة غير `dict`/JSON تالف/بلا أيّ مفتاح مخطّط ⇒ `None` في كلّ حالة.
  - **الأثر المتبقّي:** `operational_eligible` لا يزال `false` حتى يُحسَم الطقس (يشترط الثلاثة معاً — `core/canonical_field_state.py`)؛ لكن `limitations` الآن تسمّي `weather_missing` فقط بدل `weather_missing`+`soil_missing`.

## GENERATED-ARTIFACT-SWEEP-01 — FIXED_IN_CODE (2026-07-28)

- **الأثر:** «ضريبة التسجيل» موصوفة في `hot.md` بثلاث قفزات (جرد ⇒ كتالوج ⇒ حزمة)، ومداها الحقيقيّ **٤٧ خطوة `--check` موزّعة على ١٨ workflow**. الفارق كلّف جولة CI كاملة في #688 وأخرى في #689: الفحص المحلّيّ كان انتقائيّاً، فيُصلَح ما يسمّيه CI ويظهر التالي في الجولة التي بعدها.
- **المُنجَز:** `scripts/ci/verify_all_generated.py` — أمر واحد يشغّل الكلّ بترتيب التبعيّة (مولّدات ⇒ `static_governance_closure` الذي يبصمها ⇒ حزمة الإصدار آخِراً)، و`--fix` يُكرّر حتّى الثبات (حدّ ٣ دورات؛ الحاجة إلى دورة ثانية مرصودة فعليّاً على `execution_dependency_audit`).
- **القائمة تُكتشَف من الـworkflows لا تُكتب:** قائمة يدويّة تبيت عند إضافة مولّد جديد فتُعيد إنتاج العيب داخل الأداة التي تعالجه. المصدر الوحيد للحقيقة هو ما ينفّذه CI.
- **البرهان بالتكذيب:** حقن انحرافٍ في مصنوع محروس ⇒ `✗ generate_service_inventory --check` وخروج غير صفريّ؛ و`--fix` يُعيده إلى الاتّساق في دورة واحدة.
- **صدق:** الأداة تُبلِّغ الخطوات التي **لا تعرف** إعادة توليدها كـ«يدويّة» بدل تخطّيها صامتةً — فلا يُقرأ نجاحها كتغطية لا تملكها. و`--fix` لا يُعيد بناء حزمة الإصدار إلّا عند فشل التحقّق، لأنّ البناء يكتب `generated_at` جديداً فيُوسّخ الشجرة بفرق لا يقابله محتوى.
- **درسان من التنفيذ:** أوّل نسخة من التعبير النمطيّ عبرت الأسطر فابتلعت كتلة YAML وأنتجت «خطوة» وهميّة تمرّ خضراء بلا تنفيذ شيء — رُصِدت بقراءة المخرَج لا بالثقة في العدّ. وأوّل تكذيب اخترتُ فيه ملفّاً **غير محروس أصلاً**، فبدا أنّ الأداة عمياء بينما كانت صادقة؛ البرهان الرديء أخطر من غيابه.
- **الزاوية العمياء المُغلقة (2026-07-28، مُستخرَجة من `claude/verify-all-generated`):** «الاكتشاف من الـworkflows» يترك ثقباً **بحدّ تعريفه** — مولّد يدعم `--check` ولا يذكره أيّ workflow لا يراه CI ولا تراه المكنسة. الفرع الآخر بنى نسخة bash موازية تحت `GENERATED-CHAIN-UNDOCUMENTED-01`؛ المُستخرَج هو **الزاوية** لا الشيفرة، وأُعيد قياسها على `780d0544` بدل نقل نتائجها.
  - **القياس:** ٦١ سكربتاً في `scripts/{ci,architecture,release}` يُعلن علم `--check` نصّاً في مصدره؛ **٦** لا يذكرها أيّ workflow — خمسة منحرفة وواحد سليم.
  - **الأساس:** `docs/architecture/generated_chain_known_drift.json` — لكلّ مدخل حارسه و**سبب صمته** ودليله وشرط إغلاقه. التصنيف افتراضيّ و**لا ينفّذ** (خمسة من الستّة تكتب ملفّات متعقَّبة أثناء `--check` — `CHECK-STEPS-MUTATE-THE-TREE-01`)؛ التنفيذ صريح بـ`--uncovered`.
  - **الأسباب ثلاثة لا واحد:** ثلاثة حرّاسها في `tests/architecture/` خارج `testpaths` (`ARCH-TESTS-UNLISTED-IN-CI-01`) · واحد حارسه في `tests_v9` لكنّه **بلا علامة** فتستبعده كلّ وظائف CI (`TESTS-UNMARKED-DESELECTED-01` أدناه) · وواحد (`capability_linker`) **بلا حارس البتّة**.
  - **تصحيح قياس داخل الجلسة:** عددتُ `api_versioning_policy_guard` سليماً أوّلاً؛ كان خطأ أداة لا حكم — قرأتُ `$?` بعد أنبوب `| tail` فعاد رمز `tail`. القياس الصحيح: ٥ منحرفة من ٦، والأساس بُني على الرقم الصحيح.
  - **مُكذَّب في أربعة اتّجاهات:** مولّد جديد بلا تصنيف ⇒ فشل · مدخل بائت في الأساس ⇒ فشل · «الأساس يقول سليم وقد انحرف» ⇒ فشل · «الأساس يقول منحرف وقد سلُم» ⇒ فشل (يطالب بحذف المدخل، فالقائمة تتقلّص).

## CHECK-STEPS-MUTATE-THE-TREE-01 — FIXED_IN_CODE (2026-07-30)

- **العلّة:** ستّة حرّاس كانت تولّد ملفاتها داخل المستودع أثناء `--check` ثم تقارن، فتغيّر المحتوى أو `mtime` وقد تمحو الانحراف قبل أن يراه المراجع.
- **الإصلاح:** فصل مسار الفحص عن الكتابة. تُبنى النتائج المرشحة في الذاكرة أو في مجلد مؤقت خارج الشجرة، ثم تُقارن byte-for-byte بالمصنوعات الملتزمة. أوامر التوليد الصريحة وحدها تكتب.
- **الحرّاس المغلقة:** `generate_service_inventory` · `execution_dependency_audit` · `capability_runtime_evidence` · `service_dependency_conflict_guard` · `route_mount_contract_guard` · `raw_data_processing_contract_guard`.
- **تصحيح workflow:** مسار raw-data أصبح يستدعي `--check` صراحةً بدل وضع الكتابة الافتراضي.
- **البرهان بالتكذيب:** `tests/architecture/test_check_steps_are_read_only.py` يشغّل الستّة كعمليات مستقلة ويقارن hash و`mtime` وmode لكل الملفات العشرين المملوكة قبل/بعد؛ 6/6 تمرّ بلا أي تغير. وتبقى مقارنة `git status` في المكنسة دفاعاً ثانياً لأي حارس جديد.
- **حدّ الصدق:** إغلاق ساكن لعقد `--check` فقط؛ لا يرفع `runtime_verified` أو `production_certified`.
- **مُدقَّق لا مُنقَل — والحارس أمسك مؤلّفه سابعاً:** الشريحة وصلت كحزمة خارجيّة (بيئة بلا `git`)، على أساس مطابق تماماً لـ`main` الحاليّ (`dfc0be4e`) فسمح بمقارنة مباشرة بلا ضجيج نسخة. كذّبتُ كلّ حارس ستّة على حدة (حقن انحراف حقيقيّ ⇒ `rc=1` باسمه، إصلاح ⇒ `rc=0`) — الستّة صمدت. لكنّ `tests/architecture/test_check_steps_are_read_only.py` **الجديد نفسه لم يكن مُدرَجاً في أيّ workflow** (`arch_test_ci_coverage_guard` ⇒ `FAIL`، `57/58`) — العلّة ذاتها التي أغلقتها `ARCH-TESTS-UNLISTED-IN-CI-01`، تتكرّر على اختبار وُلِد لإثبات إغلاق فجوة أخرى. أُضيف إلى `capability-governance.yml` ⇒ `58/58`.
- **نقطة ضعف موروثة لا مُدخَلة، مُسجَّلة لا مُصلَحة:** فحص `execution_dependency_audit --check` يقارن **بصمة SHA-256 لمخرَجه المُعاد توليده** بقيمة بصمة مخزَّنة (`.audit.sha256`) لا **محتوى الملفّ الملتزَم نفسه** بايتاً ببايت (خلافاً للخمسة الأخرى، ومنها `generate_service_inventory` في الشريحة نفسها، اللواتي يقارنّ `committed.read_bytes() != candidate.read_bytes()`). أثبتُّه بالتكذيب: تحرير `route_handlers.csv` الملتزَم يدويّاً (لا تغيير مصدر) لا يُكتشَف — لأنّ `generate()` يُعيد كتابته من الصفر داخل المجلّد المؤقّت قبل حساب البصمة، فمحتواه الملتزَم المُتلاعَب به لا يُقارَن أبداً. **هذا موروث من التصميم قبل هذه الشريحة** (تحقّقتُ من النسخة الأصليّة: نفس منطق «قارن بصمة القديم ببصمة الجديد» كان قائماً قبل الفصل عن الشجرة، فالشريحة نقلت مكان الكتابة فقط ولم تُغيّر قوّة الاكتشاف) — لا تراجع، ولا يُحلّ هنا.
## BRAIN-DEFERRAL-LEAK-01 — FIXED_IN_CODE (2026-07-28)

- **العلّة الجذريّة:** `hot.md` يمتصّ التأجيلات ولا شيء يجبرها على الهجرة إلى هذا السجلّ. حارس `tests/architecture/test_brain_state_consistency.py` يفرض **الادّعاءات العدديّة فقط**، فالتسرّب مسموح تصميميّاً.
- **الدليل:** ثلاثة مفاهيم أُجِّلت في `hot.md` ولم تصل السجلّ؛ اثنان بقيا يتيمَين حتّى 2026-07-28 (`IMAGERY-BLANK-THUMBNAIL-01` منذ #660، و`UNIT-TEST-DORMANCY-01` منذ #590 ومبرّره سقط دون أن يوقظه شيء).
- **الإصلاح:** `scripts/ci/brain_deferral_registry_guard.py` — كلّ سطر تأجيل في `hot.md` يجب أن يحمل معرّف فجوة **موجوداً فعلاً** في هذا السجلّ. الأسطر القائمة في أساس مُجمَّد يتقلّص ولا ينمو: تأجيل **جديد** بلا معرّف يُسقِط CI.

## BRAIN-CLAIM-UNVERIFIED-01 — FIXED_IN_CODE (2026-07-28)

- **العلّة:** رسالة الالتزام تحمل ادّعاءً **لا يفرضه أيّ حارس**. المستودع يفرض تطابق الأرقام (`test_brain_state_consistency`)، وموضع المسارات (عقد JSON)، واستهلاك النوى (`capability_core_consumption_guard`) — ولا شيء يتحقّق من أنّ **فجوة أُعلِن تسجيلها قد سُجِّلت فعلاً**.
- **الدليل (مرّتان):** رسالة #683 أعلنت تسجيل أربع فجوات؛ اثنتان فقط وصلتا الشجرة. و`APP-ROUTES-EMPTY-*` — وهي **حاجب الشرائح الثلاث الباقية** — كانت إحدى الغائبتين. السبب الميكانيكيّ: سكربت إعادة البناء طبع `-1` (لم يُعثَر) وتُجوهِل.
- **الإصلاح:** `scripts/ci/brain_commit_claim_guard.py` — يستخرج معرّفات الفجوات من رسائل الالتزام في نطاق الـPR ويطالب كلّاً منها بعنوان `## ` في `gaps/registry.md`، بنفس آليّة `pr_capability_impact_gate` مع سطر `Capability-Impact:`.
- **تضييق ثانٍ (2026-07-28، `UNIT-TEST-DORMANCY-01`): معرّفات الاستشارات الأمنيّة ليست ادّعاءات فجوات.** رسالة تلك الشريحة تذكر `PYSEC-2026-1325` توثيقاً لنتيجة `pip-audit` قبل/بعد ⇒ أسقطها الحارس، لأنّ الشكل مُطابِق (ثلاثة مقاطع كبيرة بشرطات) والصنف مختلف: تُصدرها جهة خارجيّة ولا تُسجَّل هنا قطّ. لو بقي، لدفع الحارسُ كلَّ رسالة إلى **كتمان** رقم الاستشارة — عكس غرضه.
  - **الاستثناء على الشكل الكامل لا على البادئة:** نسختي الأولى استعملت `startswith("CVE-")` وكانت ستبتلع معرّف فجوة اسمه `CVE-LIKE-BUT-NOT`. **التقطه اختبار التكذيب قبل الدفع** — وهو الدرس المعاكس لعطبَي هذه الجلسة (`registry_ids()` على نصف الملفّ): الاختبار فحص الاتّجاه الذي **لم** أتوقّع فشله. المعتمَد: `^(CVE|PYSEC|OSV)-\d{4}-\d+$` أو `^GHSA-…{4}-…{4}-…{4}$`.
  - **مُثبَت بالاتّجاهين:** الفشل التاريخيّ `4eded7a..121ab09` ما زال يُلتقَط بعد التعديل (rc=1)، و`37c3b56` ما زال يمرّ.
- **تضييق ثالث (2026-07-28): حدّ المعرّف لم يكن `\b`.** رسالة تذكر `لـAUTH-E2E-UNDER-RESTRICTED-ROLE` — والمعرّف ملتصق بحرف عربيّ. الحرف العربيّ **حرف كلمة**، فلا حدّ قبل `AUTH`، فيبدأ التطابق بعد أوّل شرطة. النتيجة **عطبان في اتّجاهين متعاكسين معاً**: يُطالِب بتسجيل `E2E-UNDER-RESTRICTED-ROLE` وهو لا وجود له، و**يفوته** `AUTH-E2E-UNDER-RESTRICTED-ROLE` وهو الادّعاء الحقيقيّ الذي بُني الحارس ليفحصه. أي أنّ الحارس كان يُفوّت كلّ معرّف مذكور بالصيغة العربيّة الطبيعيّة — وهي الغالبة في هذا المستودع.
  - **الحدّ المعتمَد:** `(?<![-A-Za-z0-9_])…(?![-A-Za-z0-9_])` — تُقبل العربيّة حدّاً وتُرفض الشرطة. طُبِّق على **الحارسَين** لأنّ النمط كان مكرّراً فيهما.
  - **خطأ توقّع مسجَّل:** كتبتُ في اختبار التكذيب أنّ `XAPP-ROUTES-EMPTY-01` و`APP-ROUTES-EMPTY-01X` يجب أن تُرفَض — **مرّتين متتاليتين، وكان خاطئاً**. كلاهما رمز صالح الشكل بذاته؛ الضمانة المقصودة **قراءة كاملة لا رفض**. الاختبار الآن يُعبّر عن الضمانة الحقيقيّة: لا تطابق يبدأ بعد شرطة.
- **المصدر:** مراجعة المالك 2026-07-28 (تحقّق مزدوج: `git grep` على `origin/main` + grep على الأرشيف المفكوك).

## MCP-PREAUTH-STATUS-01 — STALE / MISDIAGNOSED (أُغلِقت بالقياس 2026-08-01)

- **الادّعاء المُسجَّل:** «طلب بلا توكن على `POST /mcp/v1/tools/call` يُجاب بـ**400** بدل 401 — عيب ترتيب ورمز حالة».
- **لم يتكرّر.** شُغِّل `require_scope` الحقيقيّ على نفس شكل النقطة (‏`dependencies=[Depends(...)]` مع جسم `dict`):

  | الحالة | الفعليّ |
  |---|---|
  | بلا توكن + جسم صالح | **401** |
  | بلا توكن + بلا جسم | **401** |
  | توكن فاسد | **401** |
  | JSON مشوَّه | 422 |

- **والمسار المذكور غير موجود:** `/mcp/v1/tools/call` صفر مطابقة في المستودع؛ كلّ الخوادم تُعلن `/v1/mcp/tools/call`. و`/mcp/v1` موجود **حصراً** كمسار بثّ (`streamable_http.py:26` ⇒ `/mcp/v1/stream`).
- **ولا يُصنَّف الـ422 عيباً pre-auth:** FastAPI يفشل في تحليل الجسم قبل استدعاء الـdependency. **إن** اشترطت السياسة auth قبل تحليل الجسم فتلك **فجوة ترتيب middleware مستقلّة** — تُسجَّل عند اتّخاذ تلك السياسة، ولا تُدمَج في هذه.
- **أصل الخطأ مُرجَّح ومقيس:** `supervisor-agent` يبني عميله بـ`base_url` منتهياً بـ`/mcp/v1`، فمن قرأ الإعداد استنتج المسار — انظر `MCP-SUPERVISOR-CLIENT-PATH-DOUBLED-01` أدناه.
- **الأثر الجانبيّ:** سبب `xfail` في `tests_v9/test_mcp_functional.py` كان يحمل التشخيص الخاطئ؛ صُحِّح. ويبقى الوسم غير صارم لأنّ ذلك الاختبار **يتخطّى** في هذا التخطيط (‏`shared.helpers` مدموجة داخل الحاوية فقط) — فالسلوك داخل الحاوية **غير مقيس**، لا مُثبَت سليماً.

## MCP-GENERIC-CONTEXT-AUTH-MISSING-01 — FIXED_IN_CODE (أمنيّة/P1، 2026-08-01)

- **العلّة:** `services/mcp_servers/generic_context_server.py` كان **الوحيد** بين خوادم MCP بلا أيّ مصادقة — لا `require_scope` ولا `Depends` ولا middleware — على `GET /v1/mcp/tools` و`POST /v1/mcp/tools/call`. بقيّة الخوادم محروسة بأسلوبين (‏`dependencies=[...]` في weather/sentinel/wofost، و`Depends` في التوقيع في market)، وكلاهما يحرس.
- **المدى: ستّ خدمات منشورة لا أربع** (تصحيح لتقديري الأوّل): `field` · `lab` · `satellite` · `iot` · `rag` · `knowledge-graph` — كلّها `MCP_SERVER_MODULE: generic_context_server` في `docker-compose.rag-kg-mcp.yml`.
- **حدّ الأثر بأمانة:** الشبكة `sahool-internal` بلا `ports:` ⇒ لا انكشاف خارجيّ مباشر، والخادم يفرض عقد مخرَج (`observation`/`signal`/`annotation`، ويرفض `recommendation`/`prescription` بـ500، و`decision_authority: "none"`). **لكنّ «داخليّ» ليس «مُصادَق»**: أيّ حِمل داخل الشبكة الموثوقة كان يقرأ سياق مستأجِرين بلا هويّة. ليس تجاوزاً لحدّ الأثر الفيزيائيّ، وهو حدّ أمنيّ حقيقيّ رغم ذلك.
- **جرد المستهلكين (إلزاميّ قبل التغيير السلوكيّ، بتوجيه المالك) ⇒ صفر مستهلك مُهيّأ:**
  - أسماء الخدمات الستّ: لا تظهر إلّا في `docker-compose.rag-kg-mcp.yml` ومصفوفة CSV مولَّدة.
  - لا متغيّر بيئة يشير إليها؛ متغيّرات `MCP_*_URL` كلّها تشير إلى الخوادم المحروسة.
  - العميل الوحيد (`services/supervisor-agent/mcp_client.py`) يستهدف أربعةً محروسة (`sentinel-hub` · `weather` · `wofost` · `market`) **ويرسل** `Authorization: Bearer` دائماً.
  - **حدّ الجرد صريح:** «لا مستهلك في المستودع» ≠ «لا مستهلك في نشر المُشغّل».
- **النطاق موحَّد لا مجاليّ:** `mcp:context:read`. وحدة واحدة تخدم ستّة مجالات، فنطاق مجاليّ واحد يكذب على خمسة، وستّة نطاقات تجعل الحارس يعتمد على `MCP_SERVICE` — وهو **مُدخَل بيئة لا هويّة**.
- **بلا bypass ولا علم انتقال:** الجرد أثبت غياب المستهلك، فلا فترة سماح. والافتراضيّ الآمن أصدق من علم مؤقّت يصير دائماً بالصمت.
- **`/healthz`/`/readyz` تبقى مفتوحة عمداً:** مُنسّق الحاويات لا يحمل توكناً، وحراستها تُنتج إعادة تشغيل لا نهائيّة — ولا تكشف سياق مستأجِر.
- **مصفوفة الحالات المُثبَتة:** بلا اعتماد ⇒ 401 · توكن فاسد ⇒ 401 · نطاق خاطئ ⇒ 403 · نطاق صحيح ⇒ 2xx.
- **الحارس على الوراثة لا على الأصل:** «المشتقّ» هنا ليس صنفاً وارثاً بل **نفس الوحدة بقيمة `MCP_SERVICE` مختلفة**، فاختبار تطبيق واحد يترك خمسةً بلا برهان. تُبنى الستّة بإعادة تحميل الوحدة. وقائمة الخدمات **تُشتقّ من compose** لا من تعداد في الاختبار: خدمة سابعة تظهر هناك تُسقِط الفحص بدل أن تمرّ صامتة.
- **التكذيب — ثلاثة أقفال:** حذف الحارس من `tools/call` ⇒ **١٣** تسقط · استبداله بـdependency غير حارسة ⇒ **١٣** تسقط (فالفحص ليس «أيّ dependency» بل `require_scope` بعينها) · إضافة خدمة سابعة إلى compose ⇒ يسقط فحص المطابقة. استُعيد ⇒ **١٥ نجحت**.

## MCP-TEST-STUB-NEUTERS-AUTH-01 — مفتوحة (أمنيّة في حزمة الاختبارات، 2026-08-01)

- **العلّة:** `tests_v9/test_mcp_weather_et0_engine_delegation.py:50-53` يحقن كعباً لـ`shared.oauth_middleware` في `sys.modules` **وقت استيراد الملفّ** — أي أثناء جمع pytest، قبل تشغيل أيّ اختبار — و`require_scope` فيه `lambda *a, **k: lambda: None`. فأيّ خادم MCP يُستورَد بعده يُبنى **بلا حراسة**.
- **الخطر ليس في ذلك الملفّ بل في جيرانه:** اختبار أمن يبني تطبيقاً بعد الكعب يصير أخضر على تطبيق **غير محروس** — «حارس لا يحرس» على مستوى حزمة الاختبارات.
- **مقيس لا مُفترَض:** تشغيل `test_mcp_weather_et0_engine_delegation.py` **قبل** `test_mcp_functional.py` يُسقِط **ثلاثة** من تأكيدات الأمن القائمة (منها `test_wofost_mcp_call_rejects_missing_token` و`..._rejects_wrong_scope`). وتحت الترتيب الأبجديّ اليوم يسبق `functional` ملفّ الكعب، فالخضرة الحاليّة **مصادفة ترتيب** لا خاصّيّة.
- **كيف انكشف:** اختباراتي الجديدة تؤكّد **سلوكاً** (401/403) لا بنيةً، فظهر أنّ الـdependency المرتبطة بالمسار `<lambda>` من ذلك الملفّ. ولو اكتفيتُ بفحص «هل توجد dependency؟» لمرّ الاختبار على حارس مُبطَل — وهو ما جعلني أضيف فحصاً على **وحدة** الدالّة لا وجودها.
- **الحلّ في شريحتي (احتواء لا إصلاح):** `_install_real_oauth_middleware()` يُحمّل الملفّ الحقيقيّ بمساره ويُثبّته قبل بناء التطبيق، فلا تعتمد نتيجتي على ترتيب الجمع.
- **لم يُصلَح المصدر عمداً:** تغيير تصميم اختبار آخر (يحتاج الكعب لأنّ `shared.helpers` مدموجة داخل الحاوية فقط) قرارٌ يخصّه، وقد يُبطِل غرضه. والأصحّ إصلاحه بعزل (‏`monkeypatch` بنطاق دالّة، أو `importlib` محلّيّ) لا بحقن دائم في `sys.modules`.
- **شرط الإغلاق:** لا يبقى في `tests_v9` حقنٌ دائم في `sys.modules` لوحدة أمنيّة؛ + حارس يمنع عودته؛ + إثبات أنّ تأكيدات أمن MCP تبقى صادقة تحت **أيّ** ترتيب (‏`-p no:randomly` وعكسه).

## MCP-SUPERVISOR-CLIENT-PATH-DOUBLED-01 — مفتوحة (عالية، 2026-08-01)

- **العلّة:** `services/supervisor-agent/main.py:69-78` يبني `MCPClient` بـ`base_url` منتهياً بـ`/mcp/v1`، و`mcp_client.py:97` يطلب `/v1/mcp/tools/call`. ودمج httpx **يُضيف لا يستبدل**:

  ```
  base_url     : http://sahool-weather-mcp:8000/mcp/v1/
  request path : /mcp/v1/v1/mcp/tools/call      ← لا يوجد على أيّ خادم
  ```

- **مقيس لا مُستنتَج:** بُني الطلب بـ`httpx.build_request` وقُرئ `url.path`.
- **في كلّ بيئة لا واحدة:** `docker-compose.v9.yml:678` · `.fixed.yml:354` · `.light.yml:87` · `.unified.yml:123` — كلّها تضبط `MCP_*_URL` باللاحقة `/mcp/v1` نفسها، فالافتراضيّ والمضبوط سواء.
- **الأثر:** نداءات المشرف إلى أدوات MCP تصطدم بـ404 دائماً. صنف «موصول ولا يعمل» — نفس عائلة `SPECTRAL-COLLECTOR-ASYNC-RACE-01`.
- **لم تُصلَح هنا عمداً:** تمسّ عميلاً حيّاً وأربع خدمات محروسة، والإصلاح (حذف اللاحقة من الإعداد أم من المسار؟) قرار عقد لا تصليب أداة. وخارج نطاق شريحة أمنيّة.
- **شرط الإغلاق:** توحيد المصدر (لاحقة في الإعداد **أو** في المسار، لا الاثنان) + اختبار يبني الطلب فعليّاً ويؤكّد المسار الناتج — لا فحص نصّيّ على الإعداد.

## MCP-PREAUTH-STATUS-01 — OPEN (P2) 2026-07-28

<!-- الوصف الأصليّ أدناه، أُبقي للمصدر -->

- **الأثر:** طلب بلا توكن على `POST /mcp/v1/tools/call` يُجاب بـ**400** بدل 401.
- **ليس غياب حماية — مُثبَت:** `services/mcp_servers/weather_server.py:147` يُعلن
  `dependencies=[Depends(require_scope("weather:read"))]`، و
  `services/mcp_servers/shared/oauth_middleware.py:43-44` يرفع `401 Missing token` عند
  غياب الاعتماد. إذن **طبقة سابقة للحارس تُجيب أوّلاً**. العيب في الترتيب ورمز الحالة.
- **لماذا يهمّ رغم ذلك:** استجابة غير المُخوَّل تتغيّر بتغيّر جسم الطلب.
- **تصحيح على تقديري الأوّل:** وصفتُه «ثغرة تخويل محتملة» قبل الفحص — كان أشدّ ممّا تحتمله
  الأدلّة. المصدر: `tests_v9/test_mcp_functional.py:317`.


## ARCH-TESTS-UNLISTED-IN-CI-01 — FIXED_IN_CODE (2026-07-28) — كان OPEN (P1) في اليوم نفسه

- **الإصلاح:** `scripts/ci/arch_test_ci_coverage_guard.py` يقارن `tests/architecture/` بـ**محتوى المجلّد** لا بذاكرة كاتب القائمة. ملفّ غير مُدرَج في أيّ workflow يُسقِط CI.
- **النقلة المقيسة: 37/54 ⇒ 52/55 موصول.** أُدرِج **١٤** اختباراً كانت تُجمَع ولا تُشغَّل قطّ (٩٤ اختباراً تمرّ في بيئة مطابقة لوظيفة CI)، وأُعفيت **٣** لأنّها **تفشل لسبب مُسجَّل** لا لأنّ إدراجها نُسي.
- **الأساس يتقلّص ولا ينمو**، ويفرض ذلك اختبار: حقن مدخل رابع يُسقِط `test_the_baseline_never_silently_grows`. وكلّ مدخل يحمل `gap` و`failing` و`evidence` و`to_close` — «معفى» بلا شرط إغلاق إعفاءٌ صامت لا تسجيل.
- **الثلاثة المُعفاة ليست صنفاً واحداً:** اثنان محجوبان بقرار المالك في `PATH3-READINESS-CLAIM-UNBACKED-01` (الاختبار يفشل **لأنّه صادق**: الأثر المُلتزَم يدّعي جاهزيّةً لا تسندها الشجرة)، والثالث `runtime_environment_preflight` يؤكّد على **بيئة المُشغِّل** فيفشل على أيّ آلة غير المولِّدة.
- **كشف الأسماء البائتة:** workflow يذكر ملفّاً غير موجود يمرّ أخضر بلا تنفيذ شيء. ليس افتراضيّاً — **أدرجتُ اسم اختبار الحارس في الـworkflow قبل كتابته، فالتقطني الحارس** قبل أوّل تشغيل.
- **والحارس موصول بنفسه:** `test_this_guard_is_itself_wired`. مكنسة #691 واختبارها وقعا خارج CI بعد بنائهما — حارس اكتمالٍ خارج الاكتمال لا يحرس شيئاً.

### الأدلّة الثلاثة التي أوجبته، كلّها من 2026-07-28

1. **١٧ من ٥٤** اختباراً خارج القائمة — منها حرّاس بُنيت في الجلسة نفسها.
2. **ادّعاء إنفاذ غير صحيح:** `hot.md:1` كان يقول إنّ ثلاثيّة عدّ المسارات «**يفرضها**» `test_brain_state_consistency.py` — وهو خارج القائمة. صُحِّح النصّ، والاختبار **صار مُدرَجاً الآن** فالادّعاء يصير صحيحاً بعد هذه الشريحة.
3. **مكنسة المصنوعات (#691)** — سكربتها واختبارها — لم تكن موصولة بأيّ workflow.

### دليل رابع مُسجَّل ولم يُصلَح — `workflow` يفشل عند الإقلاع بلا ظهور

- `path3-runtime-verification.yml` و`runtime-verification-promotion.yml` كلاهما `on: workflow_dispatch:` فقط، ومع ذلك يُنشئ GitHub لهما تشغيلات `event: push` تنتهي بـ**failure** على كلّ فرع بما فيه `main` (١١٣ تشغيلة على الأوّل وحده).
- **لا تظهر في فحوص أيّ PR** — ولذلك كانت #687 «٦٣/٦٣ خضراء» وهما حمراوان في الخلفيّة.
- **خارج نطاق هذا الحارس عمداً:** هو يفحص *اختبارات* لا *workflows*. مُسجَّل هنا كي لا يبقى ملاحظةً في محادثة؛ علاجه إمّا إصلاح سبب فشل الإقلاع أو حذف التشغيل غير المقصود.

- **الأثر:** ١٧ من أصل ٥٣ اختباراً في `tests/architecture/` **لا تعمل في بوّابة الدمج
  إطلاقاً** — منها حُرّاس بُنيت هذه الجلسة نفسها.
- **الآليّة:** `pytest.ini` يحصر `testpaths` في `tests_v9`، وكلّ ما تحت `tests/` يُشغَّل
  في CI **بقائمة مسارات صريحة**: `capability-governance.yml:105-140` تسمّي ٣٦ ملفّاً
  اسماً اسماً. أيّ ملفّ جديد في المجلّد يقع خارج القائمة **صامتاً** — لا شيء يقارن
  محتوى المجلّد بالقائمة.
- **الكشف:** أثناء `UNIT-TEST-DORMANCY-01`، إذ فشل
  `test_compose_runtime_target_resolver::test_generated_artifacts_match` محلّيّاً
  **على شجرة `origin/main` النظيفة** (مُثبَت بـ`git stash`) — أي أنّ أثراً مولَّداً
  منحرفاً يجلس على main بلا حارس.
- **ادّعاء إنفاذ غير صحيح:** `sahool-brain/hot.md:1` يقول إنّ ثلاثيّة عدّ المسارات
  «يفرضه `tests/architecture/test_brain_state_consistency.py`». ذلك الاختبار **ليس
  على قائمة CI** — يُشغَّل يدويّاً فقط. الادّعاء صحيح عن وجود الاختبار، خاطئ عن إنفاذه.
- **القياس (كلّ الـ١٧ محلّيّاً):** 81 نجح · **4 فشل** — واحد انحراف أثر حقيقيّ
  (`compose_runtime_target_resolver`)، واثنان يؤكّدان على **بيئة التوليد نفسها**
  (إصدار بايثون، نصّ خطأ Docker) فيفشلان على أيّ آلة غير المولِّدة، وواحد
  `path3_runtime_readiness_closure`. أي أنّ ١٣ منها صالحة للإدراج فوراً وأربعة تحتاج
  حكماً — الإدراج الأعمى للـ١٧ يُحمِّر CI.
- **العلاج المقترح (شريحة مستقلّة):** حارس يقارن `tests/architecture/test_*.py` بقائمة
  workflows ويفشل على أيّ غير مُدرَج، بأساس مُجمَّد يتقلّص ولا ينمو — نفس نمط
  `brain_deferral_registry_guard`. ثمّ إدراج الـ١٣، ومعالجة الأربعة كلٌّ بسببه.

### مُنفَّذ (2026-07-28) — وشكلٌ **مخالف** لِما اقترحتُه أعلاه، عن قصد

- **النطاق الحقيقيّ أكبر ممّا قِسْتُ أوّلاً:** القياس السابق شمل `tests/architecture/` وحدها
  (‏١٧ من ٥٣). المسح الكامل لشجرة `tests/` على `bb53981e`: **١١٢ ملفّاً مُتعقَّباً، ٦٦ منها
  لا يذكره أيّ workflow** — بينها **الخمسة عشر في جذر `tests/` كلّها**، وهي غائبة عن
  قياسي الأوّل لأنّ نمط البحث كان `tests/**/` فأسقط الجذر.
- **العلاج المُنفَّذ ليس «حارس قائمة» بل إلغاء القائمة:** اقتراحي أعلاه كان حارساً يقارن
  الشجرة بالقائمة اليدويّة ثمّ يُطيلها. ذلك يُبقي العلّة — **قائمة سماح يدويّة** — ويجعل
  الحارس صيانةً دائمة لها. المعتمَد: وظيفة `Repository Tests (tests/)` تشغّل
  `pytest tests` **كاملةً** ناقص أساس مُبرَّر، والاستثناءات **تُشتقّ** من
  `docs/testing/tests_tree_baseline.json` عبر `--pytest-ignores` بدل أن تُكتب في الـYAML.
  فالملفّ الجديد مُغطّى **تلقائيّاً** بلا أن يتذكّره أحد.
- **القياس:** الشجرة كاملةً في venv نظيفة (‏`requirements-test.txt` وحدها) ⇒ **٥٥٦ نجح ·
  ١٣ فشل · ٨ تخطٍّ**. الأساس **عشرة ملفّات** تحمل الثلاثة عشر، لكلّ مدخل سببه ودليله وشرط
  إغلاقه. الوظيفة الخضراء تشغّل **١٠٣** ملفّاً.
- **مُكذَّب في ثلاثة اتّجاهات، وأهمّها الأوّل:** ملفّ اختبار جديد في **دليل جديد** لا يسمّيه
  أيّ workflow ⇒ **نُفِّذ وأسقط الوظيفة**. هذا هو الفرق بين «مُغطّى» و«مُغطّى لأنّ أحدهم
  تذكّر». والثاني: `--ignore=tests/` مكتوباً في YAML ⇒ فشل (التفاف على الأساس). والثالث:
  مدخل أساس لملفّ غير موجود ⇒ فشل.
- **برهان ذاتيّ مضمَّن:** `tests/architecture/test_tests_tree_coverage_guard.py` **لا يذكره
  أيّ workflow** ويعمل مع ذلك — ويؤكّد ذلك عن نفسه (`test_this_very_file_is_covered_without_being_listed_anywhere`).
  تحت الشكل القديم كان سيولد خامداً كما ولد سبعة عشر حارساً قبله.
- **الثلاثة الباقية من الأربعة الأصليّة** (‏`compose_runtime_target_resolver` ·
  `path3_runtime_readiness_closure` · `runtime_environment_preflight`) في الأساس بأسبابها
  نفسها المُسجَّلة في `docs/architecture/generated_chain_known_drift.json` — الاختبارات
  صادقة والآثار بائتة، ورفعُ الاستثناء مشروط بإعادة التوليد لا بمرور الوقت.
- **نمط مُتكرِّر بعيّنة ثانية مستقلّة:** خمسة من العشرة تؤكّد **نصّاً حرفيّاً** في مصدر
  تغيّرت صياغته **بينما المقصد قائم** — `test_riv_p0_consumer_truth_guard` يطلب
  `LEGACY_DIRECT_SENTINEL_ENABLED = False` والمصدر يُعلن `"direct_provider_fetch": False`
  و`runtime_role: compatibility-only`. أي أنّ الحارس يفشل والحقيقة التي يحرسها **صادقة**.
  هذا تأكيد مستقلّ لِما رُصِد في `TESTS-UNMARKED-DESELECTED-01`: التأكيد على النصّ يبيت،
  والتأكيد على السلوك لا يبيت.
- **أثر جانبيّ يُسجَّل:** القائمة الصريحة في `capability-governance.yml` (‏٣٥ ملفّاً) صارت
  **زائدة** — الوظيفة الجديدة تشغّلها كلّها. لم تُحذَف هنا: حذف ٣٥ سطراً من بوّابة حوكمة
  قرار مراجعة مستقلّ، لا أثر جانبيّ لشريحة.
- **العائلة:** هذا `UNIT-TEST-DORMANCY-01` بوجه ثانٍ — اختبار موجود لا يُنفَّذ. الفارق
  أنّ الأوّل سببه تبعيّة ناقصة والثاني سببه **قائمة سماح يدويّة**، وكلاهما يُنتِج
  «أخضر يعني أقلّ ممّا يبدو».

## TESTS-UNMARKED-DESELECTED-01 — OPEN (P1) 2026-07-28 — الأساس ١٤ ⇒ **٩** (2026-07-29)

### مُنفَّذ (2026-07-29): خمسة مداخل أُغلِقت بتحويل التأكيد لا بحذف الاختبار

- **الفرضيّة التي سجّلتُها أمس تحقّقت بالمعالجة:** الخمسة كلّها **قواعد قائمة انتقل موضعها**،
  لا انحدار واحد بينها. الأسطر المُؤكَّدة موجودة حرفيّاً — في ملفّ آخر بعد تفكيك P1/P2.
- **المرساة الجديدة لكلّ حالة تُختار بحسب ما تحرسه، لا بقاعدة واحدة:**
  - `test_p3_legacy_routes_and_indicator_ui` — المسارات الستّة انتقلت من `api/main.py`
    (خالٍ من المسارات **بالعقد**) إلى `api/routers/compat_gateway.py`. المرساة الآن
    **كائن الراوتر**: تُستورَد كلّ وحدات `api/routers/` ويُقرأ `router.routes`، فينجو
    التأكيد من النقلة التالية أيضاً — وبلا اعتماد على `app.routes`
    (`APP-ROUTES-INTROSPECTION-COUPLING-01`).
  - `test_qdrant_snapshot_manager` — كان يؤكّد سطر `if target.startswith(DRILL_PREFIX)`؛
    صار في المصدر `if not target.startswith(...)` حارساً fail-closed، فسقط التأكيد
    **والحماية أقوى**. المرساة الآن **سلوكيّة**: تُقاد `restore_drill` بعميل مسجِّل
    ويُتحقَّق أنّ كلّ `DELETE` يقع داخل البادئة المحجوزة وأنّ مجموعة المصدر لا تُحذف.
  - `test_fields_put_and_mfa_api_contract_20260626` — كان يقصّ `raster-service/main.py`
    بين مرساتين نصّيّتين؛ التفكيك نقل الدالّة و**فرّق المرساتين على وحدتين**، فصار الفشل
    `ValueError: substring not found` — فشل في **إعداد** التأكيد لا في التأكيد. المرساة
    الآن **دالّة بالاسم عبر AST**، وتتبع التفويض: الغلاف يجب أن يستدعي المُنفِّذ،
    والقاعدة تُقاس في `raster_security_context.require_layer_tenant_authorized`.
  - `test_real_findings_closure_20260702` و`test_v9_gpu_enablement_20260702` — الأسطر
    انتقلت إلى `ai_evidence_runtime.py` و`sam2_runtime.py`. المرساة الآن **وحدات الخدمة
    مضمومة** بدل ملفّ مُسمّى. **حدّ مُعلَن:** هذا يبقى تأكيداً نصّيّاً؛ تحرّر من الموضع
    لا من النصّ.
- **مُكذَّبة أربعتها بإسقاط ما تحرسه فعلاً:** إزالة البادئة من هدف الحذف · تعطيل مسار
  احتياطيّ · تغيير رمز سبب في SAM2 · إسقاط علم توكن الخدمة في خدمة الذكاء ⇒ كلّها تُسقِط
  اختبارها.
- **تكذيب أوّل فشل، والفارق يستحقّ التسجيل:** أوّل محاولة على مسار الراستر استبدلت
  `raise` واحداً بـ`pass`، فبقي الاختبار أخضر — لأنّ العبارة نفسها ترد **ثلاث مرّات** في
  الوحدة، وواحدة منها داخل الدالّة المقيسة. التكذيب الصحيح كان إسقاط الفرع كاملاً.
  **الحدّ المقيس:** التأكيد النصّيّ يمسك **حذف** القاعدة ولا يمسك إعادة صياغة تُبقي
  الكلمات — وهذا مكتوب هنا بدل أن يُقرأ ضماناً أوسع.
- **البوّابة:** 3723 ⇒ **3750 نجح · صفر فشل**؛ التغطية 47.39٪ بلا تغيير (الاختبارات
  الخمسة تحرس نصّاً ومسارات لا كوداً تنفيذيّاً جديداً)، والسقف ١٤ ⇒ ٩.
- **الباقي تسعة، وكلّها بأسباب لا تُحلّ بإعادة توجيه:** أربعة تُشغَّل بمسار صريح · اثنان
  لا يجمع منهما pytest شيئاً · و**ثلاثة تحتاج حكماً**: `test_tool_contracts` (أيّ اسم
  أداة هو العقد) · `test_sahool_brain_forensic` (ادّعاء سلوكيّ يحتاج تشخيصاً) ·
  `test_roadmap_phase23` (واجهات تغيّرت جذريّاً). لا يُوسَم أيّ منها بحاله.


- **الأثر:** اختبار في `tests_v9/` **بلا علامة** لا يعمل في أيّ وظيفة CI. كلّ الوظائف
  تنتقي بـ`-m` (‏`unit` · `integration` · `security`)، وpytest يستبعد ما لا علامة له من
  **كلّ** واحدة منها. الملفّ داخل `testpaths` ويُجمَع محلّيّاً، فيبدو حيّاً وهو ميت في
  البوّابة — وهذا أخبث من `ARCH-TESTS-UNLISTED-IN-CI-01` حيث الاستبعاد ظاهر في المسار.
- **القياس:** **٦٩ ملفّاً من ٥٩٢** في `tests_v9/` بلا `pytestmark` ولا `pytest.mark.<علامة
  مسجَّلة>`. لا شيء في `tests_v9/conftest.py` يَسِم تلقائيّاً (‏`pytest_collection_modifyitems`
  غير موجود) — أي أنّ الغياب غياب فعليّ لا يعوّضه شيء.
- **الدليل الملموس (كيف اكتُشف):** `tests_v9/test_api_versioning_policy_guard.py` يشغّل
  `scripts/ci/api_versioning_policy_guard.py --check` بـ`check=True`. الحارس **منحرف الآن**
  على `main` (‏exit=1، أرقام أسطر انزاحت في الجرد: `agriai-engine/main.py` ‏`/metrics`
  ‏٨٥→٩٠). الاختبار موجود، ويفشل عند تشغيله، ولا يعمل في أيّ وظيفة — فالانحراف جالس على
  main بحارس تامّ الصحّة وصامت.
- **لماذا P1:** الحارس الصحيح الصامت أسوأ من غياب الحارس، لأنّه يُنفِق ميزانية الثقة بلا
  مقابل: وجودُه في الشجرة يُقرأ تغطيةً.
- **العلاج المقترح (شريحة مستقلّة):** حارس يفشل على أيّ ملفّ `tests_v9/test_*.py` بلا علامة،
  بأساس مُجمَّد للـ٦٩ يتقلّص ولا ينمو (نمط `brain_deferral_registry_guard`) — ثمّ وسم الـ٦٩
  دفعةً دفعةً، إذ **وسمها كلّها بـ`unit` دفعةً واحدة يُحمِّر CI**: منها ما يحتاج خدمات
  (`test_db_integration` · `test_field_forms_api_integration`) ومنها ما ينحرف فعلاً
  (`test_api_versioning_policy_guard`).

### مُنفَّذ (2026-07-28): ٢٤١ اختباراً أُيقِظ، وأساس مُجمَّد للأربعة عشر الباقية

- **القياس قبل أيّ تغيير — في venv نظيفة مطابقة لوظيفة *Unit Tests*** (‏`requirements-test.txt`
  وحدها، بلا أيّ حزمة أخرى من بيئتي): الـ٦٥ الخامدة ⇒ **٤١٥ نجح · ١٣ فشل · صفر تخطٍّ**.
  «صفر تخطٍّ» هي النتيجة المهمّة: كلّ اختبار نجح **نُفِّذ فعلاً** بلا خدمات، فوسمُه `unit`
  صادق بتعريف `pytest.ini` («fast unit tests (no services)») لا تجاوزاً.
- **المُنجَز:** وُسِم **٥٥ ملفّاً** (‏٢٤١ اختباراً) بـ`unit`. البوّابة: **3482 ⇒ 3722 نجح ·
  صفر فشل** بنفس أمر CI، والتغطية **46٪ ⇒ 47٪** فترتفع الأرضيّة 42→43 بقاعدة «~٤ نقاط دون
  المقيس» المُعلَنة في `docs/testing/coverage_ratchet.md`.
- **لماذا شُغِّلت المجموعة كاملةً قبل الالتزام:** «ناجح منفصلاً ≠ ناجح مُجمَّعاً» (#590، والدرس
  مكتوب في `ci.yml` نفسه عند الأربعة المُشغَّلة معاً). إضافة ٢٤١ اختباراً إلى تشغيل واحد قد
  تُظهِر تفاعل ترتيب — لم تُظهِر: صفر فشل.
- **الحارس:** `scripts/ci/test_marker_coverage_guard.py --check` خطوةً في وظيفة *Unit Tests*
  (قبل `pytest`)، بأساس `docs/testing/unmarked_tests_baseline.json` لكلّ مدخل سببه ودليله
  وشرط إغلاقه. **مُكذَّب في اتّجاهين:** ملفّ اختبار جديد بلا علامة ⇒ فشل · مدخل وُسِم ولم
  يُحذَف من الأساس ⇒ فشل.
- **الباقي ١٤ بثلاثة أصناف مقيسة:** ٤ تُشغَّل بمسار صريح في `ci.yml` (لا تحتاج علامة) · ٢
  لا يجمع منهما pytest أيّ اختبار (سكربتان لا وحدتا اختبار) · ٨ تفشل فعلاً.
- **النمط في الثمانية — أهمّ ما كشفته الشريحة:** سبعة منها تؤكّد **نصّاً حرفيّاً في ملفّ
  مصدر** انتقل بتفكيك لاحق (‏`api/main.py` صار خالياً من المسارات **بالعقد** · تفكيك P2
  لخدمة SAM2 · سطر انتقل في `qdrant_snapshot_manager`). أي أنّها لا تكشف انحداراً بل
  **بايتت هي نفسها**، وبيّتَها الخمول ذاته. الكلفة الثانية للاختبار الخامد إذن ليست تفويت
  الانحدار فحسب: يتعفّن إلى إنذار كاذب، فيبدو إيقاظه لاحقاً كسراً — وهذا ما يجعل الخمول
  يُبرِّر استمراره.
- **أُغلِق واحد بدليله:** `test_api_versioning_policy_guard` — أُعيد توليد جرده البائت
  (‏`--check` ⇒ exit=0) ثمّ وُسِم، فالأساس ١٥ ⇒ **١٤** والسقف تبعه.
- **الفرق عن `UNIT-TEST-DORMANCY-01`:** ذاك سببه تبعيّة ناقصة تُسقِط الجمع (خطأ استيراد
  مرئيّ)، وهذا سببه **انتقاء بعلامة** — لا خطأ ولا تحذير، فقط عدد مجموع أصغر لا يقارنه شيء.
- **المصدر:** `pytest.ini:7-14` (‏`testpaths` + العلامات) · قياس على `780d0544` ·
  `docs/architecture/generated_chain_known_drift.json` (‏`api_versioning_policy_guard`).

### مُنفَّذ (2026-08-07): الحارس نفسه كان أعمى عن دليل فرعيّ — وثمانية اختبارات ميّتة خارج أساسه

- **الحادثة:** الحارس المبنيّ لالتقاط «اختبار خامد» كان يعدّ بـ‏`git ls-files 'tests_v9/test_*.py'`
  — نمطٌ **مسطّح** لا يرى `tests_v9/<دليل>/`. فملفّا `tests_v9/runtime_activation/` — ثمانية
  اختبارات تؤكّد التركيبة القانونيّة ومسارات البوّابة — كانا ميّتين في **كلّ** وظيفة CI، ولم
  يكونا **قابلَين للظهور في الأساس أصلاً**. أي أنّ الحارس لم يفوّتهما: لم يكن يستطيع تسميتهما.
- **وثقبٌ ثانٍ من الصنف ذاته:** القياس كان **نصّيّاً**. `_MARKED` يطابق `pytestmark` مجرّداً،
  فـ`pytestmark = pytest.mark.asyncio` يُقرأ «موسوماً» بينما `asyncio` ليست علامة انتقاء
  فيُستبعَد الملفّ من كلّ وظيفة — موسومٌ ظاهراً، ميّتٌ فعلاً؛ ويطابق داخل تعليق أو نصّ.
  **والأدهى:** `registered_markers()` موصوفةٌ في الحارس بأنّها «مصدر الحقيقة الوحيد لأسماء
  العلامات» وهي **زينة** — تُستعمل في سطر النجاح وحده والأسماء مُصلَّبة في التعبير النمطيّ.
- **واختباران كانا يحرسان الوهم:** `test_the_marker_names_come_from_pytest_ini_not_a_hardcoded_list`
  أكّد **قيمة** الدالّة فمرّ طوال الوقت الذي كانت فيه زينة؛ و`test_detection_agrees_with_what_pytest_would_select`
  يُسمّي pytest في عنوانه ولا يستدعيه — يقارن بالأساس ثمّ `len(marked) > 500`. الاسم يدّعي
  المُصدِّق والجسد يؤكّد الأساس.
- **المقيس:** بالبنية والنطاق الكامل ⇒ **١١** بدل ٩ على الشجرة ذاتها؛ الفارق هو الملفّان
  المحجوبان. و**لم يُوسَّع الأساس بهما:** وُسِما `unit` فمرّت الثمانية — الراتشِت يتقلّص
  والتصحيح لا يُموَّل بتوسيعه. الأساس **٩** كما هو.
- **وواحدٌ منها كان قد تعفّن كما تنبّأ هذا السجلّ:** `test_phase2` يؤكّد
  `/internal/fields/{field_id}/state` في `services/ai_agronomist/main.py`، والقدرة **سليمة**
  في `ai_evidence_runtime.py:61` بعد تفكيك. أُعيدت المرساة إلى وحدات الخدمة مضمومة + تأكيدٍ
  صريح على التفويض (`from .ai_evidence_runtime import` في `main.py`) — **مُكذَّبة بشطريها.**
- **المُصدِّق صار اختباراً:** `test_the_guard_agrees_with_pytests_own_selection` يقارن جواب
  الحارس الرخيص بجمع pytest الحقيقيّ تحت `-m`، بعلاقة دقيقة: المُستبعَد = «بلا علامة» ∪ «لا
  يجمع منه شيء». وهو ما أمسك خطأً حقيقيّاً عندي: إغفال مُزخرِفات **الأصناف** أعطى ١٩ بدل ١١
  (ثمانية ملفّات في هذه الشجرة تَسِم على مستوى الصنف وحده). صياغتي الأولى للعلاقة بالطرح
  كانت خاطئة أيضاً، وأسقطها التأكيد نفسه.
- **الدَّين غير المُطفَّر:** ١١٦ ⇒ **١١٥** (مواصفتا طفرة: النمط المسطّح · نزع التحقّق من
  التسجيل)، كلتاهما مزروعة ومُشغَّلة بـ`--run` وأسقطت اختبارها المُسمّى.
- **خطأ إجرائيّ يستحقّ التسجيل:** استعدتُ الحارس بعد الطفرة الأولى بـ`git checkout --` وهو
  **غير مُودَع**، فمحوتُ إعادة كتابته كاملةً؛ ونتائج الطفرتين التاليتين كانت على النسخة
  القديمة — لولا رسالة «PLANT DID NOT MATCH» لَمرّت خضرةً كاذبة. الاستعادة في دورة الزرع
  تكون من **نسخة محفوظة** لا من HEAD.
- **المصدر:** `scripts/ci/test_marker_coverage_guard.py` · `tests/architecture/test_marker_coverage_guard.py`
  · `docs/testing/unmarked_tests_baseline.json` (‏`correction_2026_08_07`) · قياس على `9c0647a3`.

## API-VERSIONING-GUARD-IS-A-MIRROR-01 — مُغلقة بشطريها (2026-07-29)

- **الشطر الثاني (التصنيف) أُغلِق:** `_classify` كان يعرف `/v1/` وحده بينما عرف المنصّة الفعليّ `/api/v1/`. لم يكن خطأ بيانات بل **خطأ تعريف** — قاعدة كُتبت من عرف مُتخيَّل لا من الشجرة.
- **الإصلاح:** `^(?:/api)?/v[0-9]+(?:/|$)` — مقطع الإصدار أينما وقع في البادئة، ويشمل `/api/v2/` مستقبلاً. مُثبَت على ثمانِ حالات: `/api/v1/fields` و`/v1/x` و`/api/v2/y` و`/api/v1` ⇒ `versioned`؛ و`/apiv1/z` و`/api/fields` ⇒ `legacy` (لا يبتلع المتشابه).
- **الأثر المقيس:** قائمة السماح **٧٤٩ ⇒ ٢٣٢**، و`versioned` **١٨٠ ⇒ ٦٩٧**. التقلّص **٥١٧** مطابق للتقدير المُسجَّل رقماً برقم، و`ما زال يبدأ بـ/api/v1/` صار **صفراً**.
- **السقف نزل بالكسب لا بالتمرير:** ٧٤٩ ⇒ ٢٣٢ في `api_versioning_legacy_baseline.json`، و`known_misclassified_count` صار **صفراً** بعد أن كان ٥١٧ مُعلَناً. الراتشِت ما زال يعمل عند السقف الجديد — مُكذَّب: سقف ٢٣١ يُعطي `rc=1`.
- **الترتيب كان مقصوداً:** جُمِّدت القائمة أوّلاً (#697) ثمّ صُحِّح المُصنِّف. لو عُكس، لابتلعت إعادةُ الحساب أثرَ التصحيح بصمت ولما ظهر التقلّص لأحد.
- **يبقى مفتوحاً بصدق:** ٢٣٢ مساراً **غير مُصدَّر حقيقةً**. إصدارها تحت `/api/v1/` عمل منتَج لا تصنيف — كلّ واحد شريحته، والراتشِت يمنع نموّها في الأثناء. — النصف البنيويّ مُغلَق (2026-07-29) · التصنيف باقٍ

- **الشريحة الأولى (2026-07-30):** sam2-inference `POST /predict` ⇒ `POST /v1/predict` (٢٣٢ ⇒ ٢٣١). استدعاء واحد متتبَّع (`SEGMENTATION_INFERENCE_URL`)، مُحدَّث في `docker-compose.v9.yml`/`v9.gpu.yml`/`fixed.yml` + `scripts/ci/v9_gpu_contract_gate.py` + اختبارَي `tests_v9`.
- **تصحيح مصدر الجرد ذاته (2026-07-30):** `collect()` في `scripts/ci/api_versioning_policy_guard.py` كانت تمسح `services/**/*.py` بلا استبعاد بنيويّ لملفّات الاختبار، فصنّفت `GET /probe` داخل `services/sahool-platform/tests/test_correlation_middleware.py:18` كمسار عمل غير مُصدَّر حقيقيّ — **false positive وحيد في الجرد كلّه** (تحقّق شامل عبر التصنيفات الأربعة الأخرى أيضاً، لا نظير له). اكتُشف أثناء تدقيق مستقلّ لتقرير خارجيّ ادّعى ٢٥٠/٢٣٠/٥٥ ثمّ تبيّن أنّه استبعد `/probe` يدويّاً من الناتج بدل إصلاح المصدر.
  - **الإصلاح:** استبعاد بنيويّ (`_is_test_file`: `/tests/` في المسار، أو البادئة `tests/`، أو اسم الملفّ يبدأ بـ`test_`) — لا حذف يدويّ لسطر من الناتج المولَّد. الأساس ٢٥٠/٢٣٠/٥٥ يُعاد توليده الآن من الصفر بلا تدخّل تشغيليّ.
  - **الأثر:** ٢٣١ ⇒ **٢٣٠** في `api_versioning_legacy_baseline.json` (`ceiling`). `legacy_unversioned_business` في الجرد الخام: ٢٥١ ⇒ **٢٥٠** موضعاً، ٢٣١ ⇒ **٢٣٠** عقداً فريداً، ٥٦ ⇒ **٥٥** ملفاً.
  - **البرهان بالتكذيب:** `tests_v9/test_api_versioning_policy_guard.py::test_collect_excludes_test_file_routes_structurally` — إزالة الاستبعاد يُسقِط الاختبار فوراً باسم `/probe` صراحةً؛ استعادته يُعيده أخضر. اختباران إضافيّان يثبّتان `_is_test_file` على حالات دليل/بادئة/اسم ملفّ.
  - **حدّ صدق:** إصلاح مصدر بيانات ساكن فقط. لا يمسّ الـ٢٣٠ مساراً غير المُصدَّر حقيقةً المتبقّية — تلك تبقى شرائح منتَج مستقلّة، كلّ واحدة تستحقّ قياس أثرها قبل التنفيذ (انظر تصنيف الأولويّة P0/P1/P2 في تقرير 2026-07-30 المصحَّح).

- **تصحيح تصنيف ثانٍ (2026-07-30):** `GET /runtime-identity` (ثلاث خدمات: sahool-platform·soil-service·weather-service) كان يُصنَّف `legacy_unversioned_business` رغم أنّ CLAUDE.md يجمعه صراحةً مع `/healthz`/`/readyz`/`/metrics` كمسار بنية/provenance، وأنّ حارساً مستقلّاً (`platform_route_ownership_guard`) يصنّفه بنية تحتيّة فعلاً — **تناقض بين حارسين على نفس المسار**. اكتُشف أثناء تحضير خطة توزيع عمل على أربعة وكلاء مستقلّين: المسار محكوم بعقد مُجمَّد (`docs/architecture/platform_route_placement_contract.json`)، ومُستهلَك حرفيّاً في `functional_probe_runner.py`'s `identity_path` عبر ثلاثة ملفّات probe (`runtime-verification/functional_probes/{sahool-platform,soil-service,weather-service}.json`)، ومُختبَر بحضوره الحرفيّ في اختبارَي الشهادة (`test_runtime_build_identity_attestation.py`، `test_platform_route_placement_guard.py`) — **نقل المسار فعليّاً (لا تصنيفه) كان سيمسّ سلسلة التحقّق الحيّ/الشهادة المحظور لمسها صراحةً في قواعد الجلسة**.
  - **الإصلاح تصنيفيّ بحت:** أُضيف `/runtime-identity` إلى قائمة `infra` في `_classify()` — لا تغيير مسار، لا تغيير ملفّ، لا تغيير سلوك.
  - **الأثر:** ٢٣٠ ⇒ **٢٢٩** في `api_versioning_legacy_baseline.json` (`ceiling`). الجرد: ٢٥٠ ⇒ **٢٤٧** موضعاً، ٢٣٠ ⇒ **٢٢٩** عقداً فريداً، ٥٥ ⇒ **٥٢** ملفاً، ١٩ ⇒ **١٨** خدمة (weather-service خرجت كليّاً من القائمة — كان `/runtime-identity` مسارها الوحيد فيها).
  - **البرهان بالتكذيب:** `test_runtime_identity_is_infra_not_legacy_business` — حذف `/runtime-identity` من قائمة `infra` يُسقِط الاختبار فوراً (`assert 'legacy_unversioned_business' == 'infra'`)؛ استعادته يُعيده أخضر.
  - **الدرس العامّ:** خطّة توزيع عمل على أربعة وكلاء مستقلّين كشفت مشكلة لم يكشفها التدقيق الفرديّ للمسارات — تجميع المسارات المتكرّرة عبر الخدمات (العقود الذرّية) وفحص كلّ واحد منها بحثاً عن مسوّغ استثناء أظهر أنّ أحدها ليس ديناً إصداريّاً أصلاً بل مسار بنية مصنَّف خطأً.

- **شريحة الوكيل A الأولى (2026-07-30) — عقد MCP الذرّي (mcp_servers، ٥ ملفّات):** ٢٢٩ ⇒ **٢٢٦** (٣ عقود فريدة). فُرِّع من `7563239b` (origin/main، رأس #710) على `agent-a-mcp-protocol-v1`.
  - **ما انتقل:**
    - `GET /mcp/v1/tools` ⇒ `GET /v1/mcp/tools` — أربعة ملفّات: `services/mcp_servers/generic_context_server.py:133`، `services/mcp_servers/sentinel_hub_server.py:198`، `services/mcp_servers/weather_server.py:84`، `services/mcp_servers/wofost_server.py:50`.
    - `POST /mcp/v1/tools/call` ⇒ `POST /v1/mcp/tools/call` — الأربعة أعلاه + `services/mcp_servers/market_server.py:577`.
    - `GET /mcp/v1/tools/list` ⇒ `GET /v1/mcp/tools/list` — `services/mcp_servers/market_server.py:545` فقط (لا نظير لها في الملفّات الأربعة الأخرى).
    - الثلاثة هُوجِرت معاً في شريحة/PR واحدة لأنّها عقد MCP ذرّي واحد فعليّاً — لا معنى لهجرة نصفه.
  - **لماذا `/v1/mcp/...` لا `/mcp/v1/...`:** مصنِّف `scripts/ci/api_versioning_policy_guard.py:_VERSIONED` (`^(?:/api)?/v[0-9]+(?:/|$)`) يتطلّب مقطع الإصدار **في البادئة** — المسار القديم يحمل `v1` لكن بعد `/mcp/`، فلا يُقبَل. السابقة القائمة لخدمات مستقلّة في هذا المستودع: `services/sam2-inference/main.py:23` (`/v1/predict`) و`services/soil-service/routers/p1_products.py` وأخواتها (`/v1/soil/...`) — بادئة `/v1/` عارية لا `/api/v1/` (تلك الأخيرة بادئة `sahool-platform` كبوّابة). فحُوفِظ على البنية الدلاليّة للمسار (`mcp/tools[...]`) مع نقل مقطع الإصدار إلى الصدارة.
  - **كل مستدعٍ حرفيّ بُحث عنه (`grep -rn "mcp/v1/tools"`) وحُدِّث:**
    - `services/supervisor-agent/mcp_client.py:65` (`GET`)، `:97` (`POST`).
    - `services/mcp_servers/shared/streamable_http.py:101` (`GET`)، `:103` (`POST`).
    - `services/sahool-platform/core/mcp/independent_servers.py:4` (docstring توضيحيّ).
    - `docs/MARKET_SYSTEM.md` (رسم ASCII للبنية + مثال `curl`).
    - `docs/api/BACKEND_FRONTEND_COVERAGE.md` (ثلاثة صفوف جدول).
    - `sahool-brain/runbooks/full-stack-activation.md` (تعليق + مثال `curl` حيّ).
    - `tests_v9/test_mcp_functional.py` (docstrings + نداءات `TestClient` في الاختبارات نفسها).
    - `tests_v9/test_mcp_servers.py`، `tests_v9/test_end_to_end.py` (عناوين `http://localhost:809x/...`).
  - **لم يُمسّ عمداً (سجلّ تاريخيّ، لا مرجع API حيّ):** `docs/audits/NATIVE_LIVE_VERIFICATION.md`، `docs/audits/CRITICAL_REVIEW_RESPONSE.md`، `docs/audits/CODE_REVIEW_REPORT.md`، `docs/CRITICAL_REVIEW_ROUND3_2026-06.md` — تقارير تدقيق مؤرَّخة تصف حالة كود عند لحظة ماضية؛ تعديلها يُزيّف ما وُصِف وقتها، كما `sahool-brain/log.md`/`gaps/registry.md` نفسيهما.
  - **مُلاحَظ خارج النطاق — لم يُصلَح (عِلّة سابقة الوجود غير مرتبطة):** `MCP_SENTINEL_HUB_URL`/`MCP_WEATHER_URL`/`MCP_WOFOST_URL`/`MCP_MARKET_URL` (`docker-compose.fixed.yml:353-356`، `docker-compose.unified.yml:122-125`، `docker-compose.light.yml:86-89`، `docker-compose.v9.yml:677-680`، مُستهلَكة في `services/supervisor-agent/main.py:72-76`) تحمل بادئة `base_url` بقيمة `.../mcp/v1`، بينما `mcp_client.py` يستدعي بمسار مطلق `/v1/mcp/tools...`. `httpx.Client._merge_url` **يُلحِق** مسار الطلب المطلق بمسار `base_url` (لا يستبدله — مُتحقَّق حيّاً: `client.build_request('GET','/mcp/v1/tools').url` على `base_url='http://host:8000/mcp/v1'` يُنتِج `http://host:8000/mcp/v1/mcp/v1/tools`، ازدواج قائم أصلاً قبل هذه الشريحة). هذا خلل تشغيليّ سابق الوجود في مسارات supervisor-agent الصادرة الحقيقيّة، غير ناتج عن نقل المسار ولا يزداد سوءاً به (المُتغيّر الوحيد هو الجزء الأخير من السلسلة المضاعَفة). خارج نطاق الوكيل A بالكامل — يستحقّ فجوة مستقلّة يفتحها المالك أو وكيل مستقبليّ (`services/supervisor-agent/mcp_client.py:46,81`، `main.py:72-76`).
  - **إعادة توليد السلسلة:** `api_versioning_policy_guard.py --generate` (247→237 موضعاً، 229→226 عقداً) · `route_conflict_guard.py --generate` (PASS، 1089 مساراً، صفر تعارض حادّ) · `duplicate_definition_guard.py --generate` (PASS) · `execution_dependency_audit.py --generate` · `static_governance_closure.py --generate` (20/20) · `integration_runtime_governance_closure.py --generate` (21/21) · `generate_service_inventory.py --write-registry` (لازم إضافيّ اكتشفه `verify_all_generated.py`، لم يكن في القائمة المُقترَحة) · `capability_mapping_engine.py --generate` (لازم إضافيّ مماثل) · `pr_capability_impact_gate.py --generate-index` (لازم إضافيّ مماثل) · `build_platform_catalog.py` (لازم إضافيّ مماثل) · `platform_route_release_binding.py --write-source` + `build_release_bundle.py` + `validate_release_package.py` (أُعيدت **بعد** كلّ التوليدات الإضافيّة، إذ تشغيلها الأوّل قبل اكتشاف اللوازم الإضافيّة أنتج بصمات checksum بائتة اكتشفها `verify_all_generated.py` لاحقاً — درس تشغيليّ: شغّل حزمة الإصدار **آخراً** بعد استقرار كلّ مولّد آخر، لا حسب ترتيب القائمة المقترحة وحدها).
  - **البرهان بالتكذيب:** `tests_v9/test_api_versioning_policy_guard.py::test_mcp_protocol_atomic_contract_migrated_to_versioned_prefix` — كسر مقصود (إعادة `@app.get("/mcp/v1/tools")` في `generic_context_server.py`) أسقط الاختبار فوراً باسم المسار المتسرِّب حرفيّاً (`{'service': 'mcp_servers', ..., 'path': '/mcp/v1/tools', 'classification': 'legacy_unversioned_business'}`)؛ استعادة `/v1/mcp/tools` أعادته أخضر.
  - **التحقّق:** `verify_all_generated.py` ⇒ `✅ كلّ المصنوعات المولَّدة المُكتشَفة متّسقة` (rc=0) · `pytest -m unit` (باستثناء `test_geo_import.py` المُعفى مُسبَقاً): **3753 نجح**، تعطُّل واحد **مُشخَّص لا مُتجاهَل**: `test_dockerfile_pip_mirror_guard.py::test_pip_dockerfiles_default_to_pypi_...` يفشل لأنّ هذا الوكيل يعمل داخل `.claude/worktrees/agent-a065bac9508997bd9/` — استبعاد الحارس لأيّ مسار يحوي `.claude` في `df.parts` يُسقِط **كلّ** ملفّات Dockerfile لأنّ جذر الشجرة نفسه متداخل تحت `.claude/worktrees/`؛ لا يتكرّر على checkout عاديّ في CI (تحقّق: `services/mcp_servers/Dockerfile` موجود وبه `pip install`، والدالّة المعزولة تعيد صفراً فقط بسبب هذا الاستبعاد). غير مرتبط بهذه الشريحة إطلاقاً، ونظير لاستثناء `test_geo_import.py` المُوثَّق مسبقاً في هذه الجلسات. `ruff check .` و`ruff format --check .` نظيفان.
  - **PR:** انظر السجلّ التشغيليّ في `log.md` لرقم PR ورابط الدمج.

- **شريحة الوكيل A الثانية (2026-07-30) — عقد `/products` العابر للخدمات:** ٢٢٦ ⇒ **٢٢٥** (عقد فريد واحد رغم موضعين). فُرِّع من `origin/main` بعد دمج شريحة الوكيل A الأولى، على فرع `agent-a-products-v1`.
  - **لماذا عقد واحد رغم خدمتين مختلفتين تماماً:** الحارس يُوحِّد بنصّ `method + path` لا بالخدمة — فـ`GET /products` في `services/mcp_servers/market_server.py:631` (منتجات السوق الزراعيّ عبر MCP، منفذ 8094) و`services/odoo-bridge/routers/catalog.py:70` (منتجات ERP عبر Odoo، منفذ 8126) كانا يُحسَبان **عقداً فريداً واحداً** في `api_versioning_legacy_allowlist.generated.json` رغم اختلاف الدلالة الكامل. الخطّة المُعلَنة صراحةً فوّضت الوكيل A بلمس هذا السطر الواحد في ملفّ `odoo-bridge` (نطاق الوكيل C عادةً) لهذه الشريحة تحديداً، بلا لمس أيّ شيء آخر في الخدمة.
  - **ما انتقل:** كلاهما ⇒ `GET /v1/products` — `services/mcp_servers/market_server.py:631`، `services/odoo-bridge/routers/catalog.py:70`.
  - **كل مستدعٍ حرفيّ بُحث عنه (`grep -rn '"/products"'` + بحث عريض لصيغ الاقتباس المختلفة) وحُدِّث:**
    - `tests_v9/test_mcp_functional.py:232` (نداء `TestClient`) + سطرا التوثيق المحيطان بنصّ `/products` الحرفيّ.
    - `docs/MARKET_SYSTEM.md` (رسم ASCII للبنية سطر ٢٧ + مثال `curl` لمنفذ 8094 سطر ١١٣ + مقتطف Dart توضيحيّ سطر ١٩٦).
    - `docs/ODOO_INTEGRATION.md:207` (مثال `curl` لمنفذ 8126).
    - `docs/api/BACKEND_FRONTEND_COVERAGE.md:582` (صفّ جدول).
    - `docs/capability-registry/domains/farm_management.yaml:793` (مرجع قدرة — ملفّ يدويّ الصيانة، لا مولَّد؛ تحقّق: لا سكربت في `scripts/` يكتب هذا المسار).
    - `docs/openapi/ROUTE_INVENTORY.json:84` (لقطة مسارات ثابتة قديمة، غير موصولة بسلسلة التوليد الحيّة؛ حُدِّثت لتبقى مرجعاً صادقاً لا مُضلِّلاً).
    - `config/platform_catalog_overrides.yml` — **قرار حوكمة يدويّ** (`duplicate_route_classifications`) يُصنِّف تكرار `/products` عبر خدمتين `service_scoped_semantics` بحكم "منتجات ERP ومنتجات MCP دلالتان مختلفتان". أُعيد ربط مفتاح القرار بالمسار الجديد `/v1/products` **مع الإبقاء على نصّ الحكم ذاته** (الفرق الدلاليّ بين الخدمتين لم يتغيّر، فقط المسار) — هذا اكتشاف مهمّ: `build_platform_catalog.py` فشل حوكميّاً (`GET /products: stale decision` + `GET /v1/products: measured duplicate group has no decision`) حتى حُدِّث الملفّ اليدويّ، فلولا هذا الفشل الصريح لبقي قرار الحوكمة يتيماً بصمت.
  - **مُلاحَظ:** بحث شامل في `nginx/*.conf`، `frontend/nginx.conf`، وكلّ `docker-compose*.yml` عن توجيه خاصّ بـ`/products` — صفر نتائج، لا شيء يوجّه به كمسار خاصّ خارج الخدمتين أنفسهما.
  - **إعادة توليد السلسلة:** نفس ترتيب الشريحة الأولى + ثلاثة لوازم إضافيّة اكتشفها `verify_all_generated.py` لم تظهر في الشريحة الأولى: `capability_linker.py --apply` (لا `--generate`، الاسم مختلف)، `capability_registry_v1.py --generate`، `capability_parity_investment_engine.py --generate`، `capability_roadmap_linker.py --generate` — تسلسل تبعيّات متتالٍ: كلّ مولّد يُغيّر مُدخَل التالي، فتكرّر تشغيل `verify_all_generated.py` ثلاث مرّات قبل الاستقرار. **حزمة الإصدار (`build_release_bundle.py`/`validate_release_package.py`) أُعيدت آخراً بعد كلّ التوليدات**، بنفس درس الشريحة الأولى.
  - **البرهان بالتكذيب:** `tests_v9/test_api_versioning_policy_guard.py::test_products_cross_service_contract_migrated_to_versioned_prefix` — كسر مقصود (إعادة `@router.get("/products")` في `services/odoo-bridge/routers/catalog.py`) أسقط الاختبار فوراً باسم الخدمة والملفّ والسطر المتسرِّب حرفيّاً (`{'service': 'odoo-bridge', 'file': 'services/odoo-bridge/routers/catalog.py', 'line': 71, ...}`)؛ استعادة `/v1/products` أعادته أخضر، وكلّ الاختبارات الستّة في الملفّ (شريحتا الوكيل A معاً) خضراء.
  - **التحقّق:** `verify_all_generated.py` ⇒ `✅ كلّ المصنوعات المولَّدة المُكتشَفة متّسقة` (rc=0) · `pytest -m unit` (باستثناء `test_geo_import.py` المُعفى): **3754 نجح** (+1 عن الشريحة الأولى)، نفس التعطُّل البيئيّ الوحيد `test_dockerfile_pip_mirror_guard.py` (مُشخَّص سابقاً، غير مرتبط) · `ruff check .` و`ruff format --check .` نظيفان.
  - **PR:** انظر السجلّ التشغيليّ في `log.md` لرقم PR ورابط الدمج.

- **شريحة الوكيل A الثالثة (2026-07-30) — أوامر actuator-service (نطاق حذر مرتفع صراحةً):** ٢٢٥ ⇒ **٢٢٢** (3 عقود فريدة). فُرِّع من `origin/main` بعد دمج شريحة الوكيل A الثانية، على فرع `agent-a-actuator-v1`.
  - **لماذا حذر مرتفع:** actuator-service يُشغِّل أجهزة فيزيائيّة (مضخّات/صمّامات) — أعلى الخدمات حساسيّة في نطاق الوكيل A. قبل أيّ نقل، بُحث الشجرة كاملةً (`frontend/src`، `mobile/sahool_app/lib`، `nginx/*.conf`، `frontend/nginx.conf`، كلّ `docker-compose*.yml`، كلّ خدمة أخرى بحثاً عن `ACTUATOR_URL` أو نداءً حرفيّاً) — **صفر مستدعٍ خارجيّ** لأيّ من الثلاثة عدا اختبارات الخدمة نفسها. المسار محميّ أصلاً خلف `FEATURE_MANUAL_ACTUATOR_COMMANDS` (معطَّل افتراضيّاً) + `Depends(main._verify_token)` + `main._authorize_device_control` (`services/actuator-service/routers/commands.py:7-9` توثّق ذلك صراحةً).
  - **ما انتقل:** `POST /command` ⇒ `POST /v1/command` (`services/actuator-service/routers/commands.py:24`) · `GET /commands` ⇒ `GET /v1/commands` (`:69`) · `GET /idempotency/metrics` ⇒ `GET /v1/idempotency/metrics` (`services/actuator-service/routers/metrics.py:17`).
  - **كل مستدعٍ حرفيّ حُدِّث:**
    - `services/actuator-service/test_actuator_safety.py:163` (نداء `TestClient.post`).
    - `services/actuator-service/test_actuator_router_decomposition_guard.py:36-37` (`_CRITICAL_ROUTES`، أرضيّة الانحدار الحرجة).
    - `docs/capability-registry/domains/irrigation.yaml:420,423,431` (مرجع يدويّ الصيانة — لا سكربت يكتبه، تحقّق مماثل لشريحة `/products`).
  - **تصويب عمليّاتيّ اكتُشف أثناء هذه الشريحة (يخصّ الشريحتين السابقتين أيضاً):** `docs/api/BACKEND_FRONTEND_COVERAGE.md` يُعلِن في رأسه صراحةً «تُولَّد بـ`python3 scripts/ci/endpoint_ui_coverage_gate.py --report` — لا تُحرَّر يدويّاً»، لكنّ شريحتَي الوكيل A الأولى (تحديث ثلاثة صفوف `/mcp/v1/tools*`) والثانية (صفّ `/products`) عدَّلتا هذا الملفّ **يدويّاً بدل تشغيل المولِّد** — مخالفة صريحة لقاعدة «لا تُحرَّر يدويّاً» رغم أنّ القيم المُدخَلة كانت صحيحة. **لماذا لم يُكتشَف فوراً:** خطوة CI (`endpoint-ui-coverage-gate` في `ci.yml:17`) تُشغِّل السكربت **بلا** `--check`، فتفحص عقد التغطية الملزِم (`config/endpoint_ui_coverage.json`) لا تطابق الملفّ المولَّد حرفيّاً — فلم تفشل رغم التحرير اليدويّ. وهذا السكربت أيضاً **خارج مدى `verify_all_generated.py`** (يكتشف فقط سكربتات بعلم `--check` مذكورة صراحةً في workflow؛ هذا مذكور بلا العلم). **الإصلاح:** شُغِّل المولِّد الفعليّ (`--report`) في هذه الشريحة — أنتج **262 سطراً تغيّرت**، أكبر بكثير من تعديلاتي اليدويّة الثلاثة مجتمعة، ما يُثبت أنّ الملفّ كان بائتاً أصلاً (منحرفاً عن الشجرة) **قبل** لمس الوكيل A له، لا بسببه فقط — لكنّ التحرير اليدويّ كان لا يزال خطأً إجرائيّاً يستحقّ التسجيل بصراحة لا التعتيم عليه.
  - **ملاحظة تحقّق إضافيّة أثناء المراجعة:** الملفّ المولَّد أظهر ✅ (مغطّى نصّيّاً) لـ`/v1/command`/`/v1/commands` رغم تأكيد عدم وجود مستدعٍ حقيقيّ — تحقّق: خوارزميّة `has_frontend_evidence`/تقرير `--report` تبحث عن **جذع المسار كسلسلة فرعيّة** (`stem in corpus`) لا كمسار كامل مُحدَّد الحدود؛ `/v1/command` سلسلة فرعيّة حرفيّة داخل مسار آخر غير مرتبط تماماً (`/api/v1/commands/{command_id}` في `sahool-platform`، خدمة قرار مختلفة) — إيجابيّة كاذبة معروفة في أداة التغطية نفسها، ليست دليل استدعاء حقيقيّاً لـactuator-service. خارج نطاق هذه الشريحة (عِلّة في أداة تغطية موجودة مسبقاً)، لكن يستحقّ تسجيله لئلّا يُقرأ ✅ لاحقاً كدليل تغطية زائف.
  - **إعادة توليد السلسلة — أطول من الشريحتين السابقتين (خمس دورات تصحيح متتالية):** بعد السلسلة القياسية + إعادة توليد `endpoint_ui_coverage_gate.py --report`، اكتشف `verify_all_generated.py` تدريجيّاً: `runtime_contract_generator.py --generate` ⇒ `runtime_verification_harness.py --generate` ⇒ (دورة ثالثة) `compose_runtime_target_resolver.py --generate` + `integration_runtime_governance_closure.py --generate` + `path3_runtime_readiness_closure.py --generate` + `runtime_evidence_ingestion.py --generate` ⇒ (دورة رابعة) إعادة `integration_runtime_governance_closure.py --generate` مرّة أخرى لأنّ مُدخَله تغيّر بعد الجولة السابقة ⇒ (دورة خامسة) rc=0. حزمة الإصدار (`build_release_bundle.py`/`validate_release_package.py`) أُعيد بناؤها بعد **كلّ** دورة تصحيح، لا مرّة واحدة فقط في النهاية، لأنّ كلّ دورة غيّرت مصنوعات جديدة.
  - **البرهان بالتكذيب:** `tests_v9/test_api_versioning_policy_guard.py::test_actuator_commands_migrated_to_versioned_prefix` — كسر مقصود (إعادة `@router.post("/command")` في `commands.py`) أسقط الاختبار فوراً باسم الملفّ والسطر المتسرِّب حرفيّاً (`{'service': 'actuator-service', 'file': 'services/actuator-service/routers/commands.py', 'line': 25, ...}`)؛ استعادة `/v1/command` أعادته أخضر، وكلّ الاختبارات السبعة في الملفّ (شرائح الوكيل A الثلاث معاً) خضراء.
  - **التحقّق:** `verify_all_generated.py` ⇒ `✅ كلّ المصنوعات المولَّدة المُكتشَفة متّسقة` (rc=0) · `pytest -m unit` (باستثناء `test_geo_import.py` المُعفى): **3755 نجح** (+1 عن الشريحة الثانية)، نفس التعطُّل البيئيّ الوحيد `test_dockerfile_pip_mirror_guard.py` (مُشخَّص سابقاً، غير مرتبط) · `ruff check .` و`ruff format --check .` نظيفان.
  - **PR:** انظر السجلّ التشغيليّ في `log.md` لرقم PR ورابط الدمج.
  - **قرار نطاق مُسجَّل — Auth (session/registration group) لم يُبدأ في هذه الجلسة:** بُحث الشجرة عن مستدعي `/auth/login`·`/auth/refresh`·`/auth/logout`·`/auth/me`·`/auth/register`·`/auth/change-password` تحضيراً للشريحة التالية، فوُجِد سطح استدعاء أوسع بكثير من MCP/`/products`/actuator: `frontend/src/services/api/auth.ts`، `mobile/sahool_app/lib/services/api_service.dart`، **و`nginx/nginx.v9.conf`+`nginx/nginx.fixed.conf`+`frontend/nginx.conf` (توجيه بوّابة حيّ، بتعليقات موثَّقة عن مطبّ إعادة كتابة مزدوج `/auth/auth/login`)**، و`docs/NGINX_ROUTING.md`، وثلاثة سكربتات e2e (`scripts/smoke_e2e.py`, `scripts/e2e/spatial_flows.py`, `scripts/e2e/live_full_e2e.py`)، و`tests_v9/test_auth_e2e.py` وأخواتها. توسّع النطاق ليشمل **إعادة كتابة nginx** (بنية توجيه إنتاجيّة حيّة) هو الفارق النوعيّ عن الشرائح الثلاث المُغلَقة: خطأ في تعديل location block واحد يُعطِّل مصادقة كلّ عميل، لا مجرّد تصنيف مسار في جرد. حُكم صريح لا تخمين: هذه الشريحة تستحقّ جلسة مخصّصة بميزانية تحقّق كاملة (كلّ location block مُختبَر يدويّاً + مسار nginx مُحاكى) بدل إنهائها ضمن ما تبقّى من هذه الجلسة. **لا تخمين ولا نقل بلا تحقّق** — هذا حكم نطاق موثَّق بسببه الدقيق، لا فجوة اكتشاف. — OPEN، السبب: تعقيد إعادة كتابة nginx يتجاوز ميزانية التحقّق الآمنة المتبقّية في هذه الجلسة، ليس غياب المستدعين (وُجِدوا جميعاً ويمكن تحديثهم، لكن التحقّق من صحّة كلّ location block يستحقّ جلسة مخصّصة). التالي: Auth password-recovery/MFA/tenant-users groups (سطح استدعاء أبسط، بلا مسارات nginx خاصّة موثَّقة بنفس القدر) قد تكون نقطة بداية أنسب من session/registration. الحارس **يكشف** الانحراف فعلاً — يقارن القائمة المُلتزَمة بالمُعاد حسابها. العيب أنّ **علاجه المُوثَّق «أعِد التوليد»**: فمسار عمل جديد بلا إصدار يُقبَل بمجرّد الالتزام بالقائمة الجديدة. **كاشف انحراف لا بوّابة سياسة** — والفرق أنّ الأوّل يُبلِّغ والثاني يمنع.
- **شريحة الوكيل D الأولى (2026-07-30) — field-segmentation، `POST /segment` ⇒ `POST /v1/segment`:** ٢٢٢ ⇒ **٢٢١** (عقد فريد واحد). خدمة أحادية الملفّ (`services/field-segmentation/main.py:390`) بمسار عمل وحيد، مستهلَكة عبر بروكسي `service_proxy.py` الشفّاف (`@router.api_route("/api/segmentation/{path:path}")`) لا عميل بمسار ثابت. كلّ مستدعٍ حُدِّث: `services/field-segmentation/test_segmentation.py` (22 موضع + اختبار تزييف جديد `test_segment_route_is_versioned_not_legacy`)، `frontend/src/services/api.ts`+`api.test.ts`، `scripts/e2e/segmentation_platform_live_gate.py`، `tests_v9/test_segmentation_remaining_ui_live_gate_20260703.py`، `docs/SAM2_DEPLOYMENT.md`.
  - **أُعيد بناء الفرع ثلاث مرّات — أوضح مثال في هذه الجلسة على مخاطر الدمج المتوازي على جرد مشترك:** فُتِح PR #711 أصلاً على `7563239b` (٢٢٩⇒٢٢٨). اندمج #712 (شريحة الوكيل A الأولى، ٢٢٩⇒٢٢٦) ⇒ `mergeable_state: dirty` (مؤكَّد بـ`git merge-tree`) ⇒ إعادة بناء من `69572be7` (٢٢٦⇒٢٢٥). قبل الدفع اندمج #715 (شريحة الوكيل A الثانية، ٢٢٦⇒٢٢٥) ⇒ إعادة بناء ثانية من `160b0798` (٢٢٥⇒٢٢٤). قبل الدفع أيضاً اندمج #716 (شريحة الوكيل A الثالثة، ٢٢٥⇒٢٢٢) ⇒ إعادة بناء ثالثة من `4d4f2d90` (٢٢٢⇒**٢٢١** الصحيح النهائيّ) — نفس الرقعة المصدريّة الثابتة في كلّ مرّة، إعادة توليد كاملة من الصفر في كلّ مرّة.
  - **فجوة ثانية أُغلِقت ضمن هذه الشريحة — `CAPABILITY-LINKER-SCANS-AGENT-WORKTREES-01`:** أثناء إعادة البناء الثانية، `capability_linker.py --apply` كشف مسحاً خاماً لنظام الملفّات (`discover_files()`: `ROOT.rglob("*")` مباشرةً، لا `git ls-files`) لا يستبعد `.claude` ضمن `EXCLUDED_DIRS` (يستبعد `.git`/`node_modules`/`.venv`/`venv`/`dist`/`build`/`coverage`/`.next`/`__pycache__` فقط). في بيئة هذه الجلسة (أربعة وكلاء متوازين عبر `Agent({isolation:"worktree"})`)، كلّ وكيل يعمل في نسخة كاملة من المستودع تحت `.claude/worktrees/agent-<id>/` — دليل حقيقيّ على القرص، مُستبعَد من git لكن مرئيّ تماماً لمسح خام. النتيجة: قفز عدد المرشّحين المكتشَفين من ~1827 الطبيعيّ إلى 5171 (أربعة أضعاف تقريباً)، وكُتِبت مسارات `.claude/worktrees/agent-.../...` في حقول `tests`/`mobile_consumers` لعدّة قدرات (SEC-004 إلى SEC-008، INT-002، INT-003، FM-001 وغيرها) داخل `capabilities/registry/capabilities.json` **المُلتزَم فعليّاً**، مُسقِطاً `capability-registry` و`tests/architecture/test_capability_traceability.py` على GitHub Actions الحقيقيّ (حيث هذه المسارات غير موجودة). **الإصلاح:** أُضيف `.claude` إلى `EXCLUDED_DIRS` (نفس نمط `_is_test_file` المعتمَد سابقاً، PR #709). إعادة تشغيل `--apply` نظَّفت كلّ الإدخالات الفاسدة تلقائيّاً (الحقول تُعاد كتابتها كاملةً من الصفر في كلّ تشغيل، لا إلحاق). **البرهان بالتكذيب:** `tests/architecture/test_capability_linker.py::test_discover_files_excludes_claude_worktree_directories` — يزرع ملفّاً داخل `.claude/worktrees/agent-fake123/tests/` في مستودع اصطناعيّ ويؤكّد عدم تسرّبه؛ إزالة `.claude` من `EXCLUDED_DIRS` تُسقِطه فوراً باسم المسار المتسرِّب حرفيّاً؛ استعادته يُعيده أخضر.
  - **درس صدق تشغيليّ من الإعادة الثالثة:** في الإعادة الثانية إلى الفرع الجديد، طُبِّقت الرقعة عبر `git apply --check` فقط (اختبار جفاف) دون تشغيل `git apply` الفعليّ بعده — فاستمرّت خطوات التوليد على ملفّات لم تتغيّر فعليّاً، واكتُشف الخطأ فقط حين ظهر السقف الخاطئ لاحقاً. الدرس: `--check` يثبت أنّ الرقعة **تنطبق**، لا أنّها **انطبقت** — يجب التحقّق من محتوى الملفّ الفعليّ بعد أيّ `git apply`، لا الاكتفاء بنجاح الأمر.
  - **الدرس العامّ لبقيّة الوكلاء:** حين يعمل أكثر من وكيل بالتوازي على جرد مولَّد مشترك، الدمج يجب أن يكون **متسلسلاً واحداً تلو الآخر** — فرع جديد + إعادة توليد كاملة قبل **كلّ** دفعة نهائيّة، لا افتراض أنّ الأساس المحسوب وقت الفتح يبقى صالحاً وقت الدمج؛ وقد يتكرّر هذا أكثر من مرّة لنفس الـPR الواحد إن تأخّر دمجه بينما تندمج شرائح إخوة متتالية.
  - **التحقّق:** `verify_all_generated.py` ⇒ `✅ كلّ المصنوعات المولَّدة المُكتشَفة متّسقة` (rc=0، ٥٦ خطوة + ٥٢٣٠ بصمة إصدار) · `pytest -m unit`: 3753 نجح، 26 تخطّي، تعطُّلان بيئيّان معروفان غير مرتبطين (`test_dockerfile_pip_mirror_guard.py`، `test_scout_ingest_service_ownership.py::test_no_other_source_inserts_into_external_submissions` — كلاهما آثار بيئة `.claude/worktrees` الموازية) · `ruff check .`/`ruff format --check .` نظيفان.
  - **PR:** #711 (أُعيد بناؤه ثلاث مرّات على نفس رقم الفرع/الـPR؛ انظر `log.md` لرابط الدمج النهائيّ).

- **Option B (2026-07-30) — نفس عطل التركيب في المولِّد الشقيق `generate_service_inventory.py`، أُصلِح أخيراً:** بعد اكتمال شرائح الوكيل D الخمس (PR #711/#718/#719/#720/#721، السقف ٢٢٩⇒٨٩)، طلب المستخدم صراحةً إصلاح هذا العطل **قبل** أيّ هجرة واسعة جديدة (raster-service)، بحجّة أنّ أيّ قياس على جرد بائت قد يُنتج تكرارات وهميّة — وهو ما تحقّق فعلاً (انظر أدناه).
  - **العطل:** `routes_for_file()` في `scripts/ci/generate_service_inventory.py` كانت تقرأ نصّ المُزخرِف الحرفيّ فقط (`@router.get("/plan")`) دون تركيبه مع `APIRouter(prefix="/v1/phase9/autonomy")` المُعلَن في الملفّ نفسه — **نفس** العطل المُصلَح في `api_versioning_policy_guard.py` (PR #717)، لكنّه ظلّ قائماً بصمت في هذا المولِّد الشقيق (المُستخدَم في كشف التكرار النصّيّ عبر `build_platform_catalog.py`، لا في راتشِت الإصدار).
  - **التحقّق قبل الإصلاح (بدل الافتراض):** بحث حرفيّ (`grep -rn "include_router(" services/ bots/`) لم يجد استخدام `prefix=` في `include_router` إطلاقاً، ومسح AST مستقلّ طابق كائن كلّ مُزخرِف مسار حقيقيّ بتعريفه المحليّ — صفر نتيجة عبر-ملفّات. الإصلاح اقتُصر إذن على تركيب **نفس-الملفّ فقط** (يطابق نطاق PR #717 حرفاً بحرف)، مع اختبار حارس تكذيبيّ (`test_no_include_router_with_prefix_or_cross_file_route_decorators_exist`) يُسقِط الافتراض فوراً لو ظهر نمط عبر-ملفّات مستقبلاً.
  - **الإصلاح:** إضافة `router_prefixes(tree)` (عامّة، بلا شرطة سفليّة — خلافاً لـPR #717 عمداً كي يستدعيها ملفّ الاختبار مباشرةً) + `_decorator_object_name(dec)` + `_compose(prefixes, object_name, path)` في `scripts/ci/generate_service_inventory.py`، وربطها بحلقتَي `routes_for_file()` (المُزخرِف والتسجيل الصريح `include_router`/`app.get` معاً).
  - **الأثر المقيس — ٩٩ صفّاً في ستّة ملفّات سحول-بلاتفورم مُطابقة تماماً لِـPR #717** (`phase9_autonomous_farm_os.py`, `phase10_continuous_learning.py`, `phase11_federated_agents.py`, `phase12_marketplace_ecosystem.py`, `routers/gis_cloud_native.py`, `routers/irrigation_engineering.py`)، بلا تغيّر في إجماليّ المسارات (١١٠٥) ولا في عدد الخدمات (٣٢).
  - **تركيبات Method/Path الفريدة عبر الكتالوج ٩٩٢ ⇒ ٩٩٨ (+٦) — تفصيل كامل في `tests_v9/test_platform_catalog_gate.py:36`:** +٢ من انفصال `GET /stac`/`GET /stac/collections` عن نصّ raster-service الحقيقيّ الخام إلى نصّ سحول-بلاتفورم المركَّب الجديد (`/api/v1/gis/cloud-native/stac[/collections]`)؛ +٤ من نصوص خام كانت **مشتركة داخل الملفّات الستّة نفسها قبل الإصلاح** — `POST /cycle` (أربعة صفوف في phase9/phase10/phase11/phase12 انهارت إلى نصّ فريد واحد قبل الإصلاح، صارت أربعة نصوص مُركَّبة مميَّزة بعده) و`POST /models/register` (صفّان في phase9/phase10 انهارا إلى نصّ واحد، صارا اثنين). بقيّة الـ٩٩ صفّاً تبادلت نصّاً خاماً بنصّ مركَّب دون أثر على العدّ الإجماليّ (إضافة صفّ = حذف مقابله).
  - **أثر جانبيّ حوكميّ لم يكن متوقَّعاً عند البدء — تكرار وهميّ ثانٍ من نفس العطل:** بعد الإصلاح، فشل `build_platform_catalog.py --generate` بـ`GET /stac: stale decision` و`GET /stac/collections: stale decision` — **نفس نمط `/plan` الوهميّ** المُكتشَف في شريحة الوكيل D الخامسة (2026-07-30، مذكور أعلاه): سحول-بلاتفورم كانت تُقرَأ زوراً بنصّ خام يطابق نصّ raster-service الحقيقيّ (`gis_cloud_native.py`)، فصنعت مجموعة تكرار وهميّة معه. بعد الإصلاح، عضو raster-service الحقيقيّ الوحيد يبقى وحده — لم يعد عقداً مُكرَّراً. **حُذف القراران المقابلان نهائيّاً** من `config/platform_catalog_overrides.yml` (لا إعادة ربط بمسار جديد، خلافاً لِـ`/products` سابقاً، إذ لم يبقَ عضوان يتشاركان النصّ نفسه). مجموعات التكرار المُصنَّفة ١٤ ⇒ **١٢** (`tests_v9/test_platform_catalog_gate.py:142`).
  - **الثمانية المسارات المتبقّية في سحول-بلاتفورم كـ`legacy_unversioned_business` (مطلوبة صراحةً من المستخدم للتوثيق) — مقيسة من `api_versioning_inventory.generated.json` بعد الإصلاح:** `POST /api/chat` (`chat_proxy_reference.py:110`) + سبعة في `routers/compat_gateway.py`: `GET /api/indicators/readyz:31`، `GET /api/weather/readyz:37`، `GET /api/vegetation/readyz:43`، `GET /api/agent/health:48`، `GET /api/vegetation/v1/all_fields:53`، `GET /api/vegetation/v1/analyze:80`، `GET /api/raster/{path:path}:114`. هذه ديون توافقيّة مؤجَّلة عمداً (بوّابة توافق قديمة صريحة)، لا فجوة اكتشاف جديدة — الإصلاح لم يغيّرها إطلاقاً (خارج مدى `APIRouter(prefix=...)`، مسارات `@app.` مباشرة بلا بادئة).
  - **معزول تماماً عن راتشِت الإصدار:** `git status --short` على `api_versioning_inventory.generated.json`/`.csv`، `api_versioning_legacy_allowlist.generated.json`، و`docs/architecture/api_versioning_legacy_baseline.json` عاد فارغاً — السقف ما زال **٨٩** بلا أثر، مطابقاً لشرط النطاق الصريح من المستخدم («إصلاح مُصنِّف فقط، لا هجرة مسارات في نفس الالتزام»).
  - **اختبار جديد:** `tests/architecture/test_generate_service_inventory.py` (خمسة اختبارات) — يشمل برهان تكذيب مباشر لـ`router_prefixes()` نفسها، إثبات تركيب على الملفّات الستّة الحقيقيّة، حارس نطاق عبر-ملفّات/`include_router(prefix=...)`، وتحقّق تكامليّ يُشغِّل `check_drift()` الحقيقيّ على الشجرة الملتزَمة.
  - **التحقّق:** `verify_all_generated.py` ⇒ `✅ كلّ المصنوعات المولَّدة المُكتشَفة متّسقة` (rc=0، ٥٦ خطوة) بعد ثلاث دورات تصحيح متتالية (`capability_linker.py --apply` تغيّر أوّلاً بإضافة ملفّ الاختبار الجديد كدليل لِـFM-007، ثمّ `static_governance_closure.py --generate` تبع تغيّره) · `pytest -m unit`: **3761 نجح**، 26 تخطّي، صفر فشل (بعد تحديث ثابتَي `tests_v9/test_platform_catalog_gate.py` — `PINNED_UNIQUE_METHOD_PATH` و`duplicate_groups_classified` — ليطابقا القياس الصحيح الجديد بدل البائت) · `ruff check .`/`ruff format --check .` نظيفان.
  - **القرار التالي (مُقرَّر مسبقاً من المستخدم):** raster-service على الأساس المُعاد قياسه الآن — **لا افتراض أنّ عدده يبقى ٣٠** قبل قياس مباشر على هذا الجرد المُصحَّح. يُقسَّم إلى خمس PRs بالملكيّة لا الحجم (جرد/تصنيف، مسارات داخليّة/تشغيليّة، صور/كتالوج/معالجة، بلاط/عرض، توافق+حذف) — مع حذر خاصّ على مسارات البلاط (nginx/بروكسي، عناوين واجهة، انتشار مستأجر، مفاتيح تخزين مؤقّت، تفويض بتوقيع/استعلام). بعده: soil-service ⇐ mcp_servers ⇐ erp-bridge (وodoo-bridge اسم مستعار تاريخيّ لـerp-bridge، لا خدمة مستقلّة). Auth يبقى مؤجَّلاً حتى إثبات مستهلكين حيّين.
  - **PR:** #722 (فرع `fix-route-inventory-classifier-prefix`؛ التزامان: `e87bba05` الإصلاح الأصليّ + `a42dc1d7`/`e94d538a` تسجيل الاختبار في `capability-governance.yml` وإصلاح `Capability-Impact: ALL`) — اندمج `aeb9b1a7`.

- **raster-service PR-R1 — جرد/تصنيف الملكيّة (2026-07-30):** أُعيد قياس raster-service على الأساس المُصحَّح (بعد Option B) بدل افتراض الرقم القديم كما حذّر المستخدم صراحةً — **٣٠ لا تزال ٣٠** (٤٨ `versioned`، ٣ `infra`، ٣٠ `legacy_unversioned_business`)، لم يتأثّر raster-service بعطل Option B إطلاقاً (العطل كان محصوراً بستّة ملفّات سحول-بلاتفورم). قياس مستقلّ حقيقيّ، لا نقل افتراض.
  - **التصنيف الكامل بمصادر path:line في `docs/architecture/raster_service_route_migration_plan.md`، مُثبَّت آليّاً في `tests/architecture/test_raster_service_route_migration_plan.py` (أربعة اختبارات، مُثبَتة بالتكذيب — إزالة `/gis/admin-boundaries` من التصنيف أسقطت اختبارين باسم المسار المتسرِّب حرفيّاً، استعادته أعادهما أخضر):**
    - **PR-R2 (٨) — داخليّة وتشغيليّة:** حالة/نتيجة المهامّ (`jobs.py`) + تخزين/رفع/حزم offline (`storage.py`). كلّها `require_service_token`.
    - **PR-R3 (٢٠) — صور/كتالوج/معالجة:** تحاليل (`analysis.py` ٨) + معالجة غير متزامنة (`processing.py` ٣) + واجهة STAC داخليّة (`stac.py` ٣) + مراقبة (`observability.py` ٢) + سلسلة زمنيّة (`timeseries_routes.py` ٣) + حدود GIS (`fields.py` ١). ثلاثة مسارات STAC + `GET /imagery/timeseries` الخام `public_catalog` (لا بيانات مستأجر)، الباقي `service_only`.
    - **PR-R4 (٢) — بلاط وعرض:** `tiles.py` فقط (`GET /tiles/{layer_id}/{z}/{x}/{y}.png` و`GET /layers/{layer_id}/tilejson`) — `layer_scoped`، منفصلة معماريّاً تماماً عن عائلة `/v1/fields/{field_id}/tiles/...` المُصدَّرة فعلاً (`routers/fields.py`) التي تستدعيها الواجهة حقيقةً (`frontend/src/services/api.ts:3150`).
    - **PR-R5:** ليست مجموعة مسارات — تحقّق تتبّعي بعد اندماج R2-R4: كلّ مستهلك حقيقيّ حُدِّث بلا تأجيل، لا حاجة لاسم مستعار توافقيّ (صفر مستهلك واجهة/موبايل حيّ عبر الثلاثين)، وفحص تكرار عابر-خدمات جديد (نفس نمط `/stac` الوهميّ في Option B) قبل كلّ دمج.
  - **مستهلكون حقيقيّون يستوجبون تحديثاً متزامناً (لا تأجيلاً لـR5) — عُثر عليهم عبر `raster_service_client.py`، لا تخمين:** `GET /jobs/{job_id}/result` (`raster_service_client.py:466`، `get_job_result`) · `GET /indices` (`raster_service_client.py:182`، `get_indices_sync`) · `POST /process/batch` (`raster_service_client.py:448`، `process_indicator_batch` يقود تجميع مؤشّرات `imagery_automation.py`). هذه الثلاثة تختلف عن روتيرات سحول-بلاتفورم في Option B (صفر مستدعٍ حقيقيّ) — نقلها يتطلّب تحديث العميل في **نفس** الـPR.
  - **تحقّق حذر خاصّ لمسارات البلاط (المطلوب صراحةً من المستخدم) — أُجري فعليّاً لا افتراضاً:**
    - **nginx** (`nginx/nginx.v9.conf:252`، `nginx/nginx.fixed.conf:65`، `frontend/nginx.conf:75`): بروكسي شفّاف يُجرِّد `/api/raster/` ويُمرِّر أيّ مسار كما هو — لا يحتاج تعديلاً لأيّ نقل مسار.
    - **واجهة/موبايل:** صفر مرجع حرفيّ لـ`/tiles/{layer_id}` أو `/layers/{layer_id}/tilejson` في `frontend/src/` أو `mobile/sahool_app/lib/` — الواجهة تستدعي عائلة `/v1/fields/{field_id}/tiles/...` المنفصلة فعليّاً.
    - **بناء URL ديناميكيّ (الاكتشاف غير المتوقَّع):** `raster_job_orchestration.py:230` يُضمِّن `tile_url_template: /tiles/{layer_id}/...` في نتيجة `/process` — تُبِع كلّ قارئ لـ`get_job_result()`؛ `imagery_automation.py`'s `_fetch_index_mean` يقرأ `stats.mean`/`stats.valid_pixels` فقط. **لا قارئ لحقل `tile_url_template` في كامل الشجرة** — بيانات ميّتة، لا تكامل حيّ، لكن يستحقّ تحديثه في PR-R4 نفسها لسلامة الحمولة (لا تُصدَّر رابط بادئة بائتة حتى لو غير مُستهلَكة اليوم).
    - **الخلاصة:** رغم الحذر العامّ المُبرَّر لمسارات البلاط، هذا الزوج تحديداً **بلا مستدعٍ خارجيّ حيّ** — R4 يهاجر مباشرة بلا حاجة فترة اسم مستعار توافقيّ.
  - **معزول تماماً عن مضيّ Option B:** لم يُلمَس أيّ ملفّ سحول-بلاتفورم أو مولَّد؛ إضافة اختبار وثائقيّ جديد فقط + وثيقة تخطيط.
  - **التالي:** PR-R2 (الأبسط، بلا مستهلك واجهة/موبايل حيّ) أوّلاً.

- **raster-service PR-R2 — داخليّة وتشغيليّة (2026-07-31):** ٨ مسارات هاجرت فعليّاً ⇐ `/v1/*` — `GET /jobs/{job_id}`، `GET /jobs/{job_id}/result`، `POST /upload/raster`، `POST /upload/drone`، `GET /storage/stats`، `POST /storage/cleanup`، `GET /offline/packs`، `GET /offline/packs/{pack_name}` (`services/raster-service/routers/jobs.py:18,36` + `routers/storage.py:25,42,64,73,86,114`). السقف ٨٩ ⇒ **٨١** في `api_versioning_legacy_baseline.json`.
  - **مستهلك حقيقيّ واحد حُدِّث في نفس الالتزام (لا تأجيل):** `services/sahool-platform/api/raster_service_client.py:466`'s `get_job_result` — `f"/jobs/{job_id}/result"` ⇐ `f"/v1/jobs/{job_id}/result"`. اختبار الواجهة `test_p2_1_imagery_automation_raster_facade_guard.py`'s `test_raster_facade_exposes_automation_primitives` حُدِّث معه (يفرض حرفيّاً وجود مسار العميل الجديد).
  - **كلّ مرجع حرفيّ آخر عبر المستودع حُدِّث (بحث شامل قبل الالتزام، لا تخمين):**
    - `tests_v9/test_raster_endpoint_auth_coverage.py`'s `SERVICE_ONLY` — ثمانية إدخالات حُدِّثت لتطابق المسارات الجديدة (الحارس يصنِّف بمطابقة نصّيّة حرفيّة على `SERVICE_ONLY`/`PUBLIC_CATALOG`، لا بادئة عامّة، فتحديث النصّ إلزاميّ لا اختياريّ).
    - `tests_v9/test_fields_put_and_mfa_api_contract_20260626.py` — أربعة تأكيدات substring حرفيّة على قسم `SERVICE_ONLY` في الملفّ أعلاه.
    - `services/raster-service/test_stac_vrt.py:68` — **النداء الوظيفيّ الحقيقيّ الوحيد** داخل الخدمة نفسها يستدعي `/jobs/{job}` مباشرةً عبر `TestClient` (سكربت مستقلّ لا مُكتشَف تلقائيّاً بـpytest، لكن يُشغَّل يدويّاً/بخطوة CI منفصلة — حُدِّث احتياطاً).
    - **حقلان ديناميكيّان مُضمَّنان في استجابات — نفس درس `tile_url_template` من بحث PR-R1:** `download_url` في استجابة `/offline/packs` (`storage.py:104`) و`note` الاستشاريّ في استجابتَي `/process/batch` (`processing.py:162`) و`/process-cdse` (`routers/fields.py:839`) — كلّها تُضمِّن `/jobs/{job_id}`/`/offline/packs/{name}` الخام حرفيّاً في الحمولة المُعادة للعميل؛ حُدِّثت جميعاً لتفادي تصدير رابط بادئة بائتة حتى لو بلا مستهلك مؤكَّد اليوم (نفس انضباط «لا نصّ شبح» من الجلسة).
    - `docs/openapi/API_MAP.md` — ثمانية أسطر (مُعلَن «مُولَّد آليّاً» لكن بلا مولِّد حيّ في `scripts/`؛ نفس القرار المُتَّخَذ لملفّات مماثلة في شرائح سابقة: يُصحَّح يدويّاً ليبقى مرجعاً صادقاً).
    - `docs/api/BACKEND_FRONTEND_COVERAGE.md` — أُعيد توليده فعليّاً عبر `scripts/ci/endpoint_ui_coverage_gate.py --report` (٨ أسطر تغيّرت بالضبط)، لا تحريراً يدويّاً.
  - **تُركت عمداً بعد تحقّق مباشر لا افتراض:**
    - `tests_v9/test_mobile_backend_contract.py` — اختبار غير مُؤكِّد أصلاً (`test_every_mobile_call_has_backend` تُعيد قائمة نتائج بـ`return` لا `assert` — لا تفشل أبداً بصرف النظر عن المحتوى)، ويمسح `sahool-raster-service/app/api/endpoints.py` — مسار مجلّد **غير موجود** في هذا المستودع (بنية مشروع سابقة). بائت سابق الوجود، خارج نطاق هذه الشريحة.
    - `tests_v9/test_roadmap_phase23.py`'s فحصان ناعمان (`test_geospatial_deep_gaps` وما قبلها) يمسحان `services/raster-service/main.py` بحثاً عن `/offline/packs`/`/storage/stats`/`/storage/cleanup` — لكنّ هذه المسارات انتقلت إلى `routers/storage.py` منذ تفكيك سابق (Phase 13)، فلم تكن موجودة في `main.py` أصلاً حتى قبل هذه الشريحة (تحقّق مباشر بـ`grep` أكّد الغياب المسبق) — بائتان سابقا الوجود، لا انحداراً مُستحدَثاً.
    - تقريران تاريخيّان مؤرَّخان (`FIX_ALL_REPORTED_ISSUES_20260626.md`، `docs/history/PROVIDERS_GAPS_IMPLEMENTATION.md`) — نفس سابقة الشرائح الأخرى في هذه الجلسة.
  - **اختبارا تكذيب جديدان، كلاهما مُثبَت بكسره فعليّاً ثمّ استعادته:** `tests_v9/test_api_versioning_policy_guard.py::test_raster_service_pr_r2_routes_are_versioned` (يفرض غياب المسارات الخام + وجود الجديدة + تحديث العميل)، و`tests/architecture/test_raster_service_route_migration_plan.py`'s `test_pr_r2_routes_stay_versioned_not_legacy` (حارس انحدار: عودة أيّ مسار إلى خام يُسقِطه باسمه). وثيقة الخطّة `docs/architecture/raster_service_route_migration_plan.md` حُدِّثت (قسم PR-R2 وُسِم "MIGRATED").
  - **التحقّق:** `verify_all_generated.py` ⇒ صفر انحراف (rc=0) · `pytest -m unit`: **3762 نجح** (+١) · `ruff check .`/`ruff format --check .` نظيفان.
  - **التالي:** PR-R3 (٢٠ مساراً — صور/كتالوج/معالجة؛ مستهلكان حقيقيّان يحتاجان تحديثاً متزامناً: `/indices`، `/process/batch`).

- **raster-service PR-R3 — صور/كتالوج/معالجة (2026-07-31):** ٢٠ مساراً هاجرت فعليّاً ⇐ `/v1/*` — تحاليل (`analysis.py`: `/zones/classify`، `/change/detect`، `/fvc/compute`، `/sar/rvi`، `/terrain/slope`، `/cog/validate`، `/salinity/classify`، `/salinity/calibrate`) + معالجة (`processing.py`: `/process`، `/raw/process`، `/process/batch`) + STAC (`stac.py`: `/stac`، `/stac/collections`، `/stac/mosaicjson`) + مراقبة (`observability.py`: `/info/{layer_id}`، `/indices`) + سلسلة زمنيّة (`timeseries_routes.py`: الثلاثة) + حدود GIS (`fields.py`: `/gis/admin-boundaries`). السقف ٨١ ⇒ **٦١** في `api_versioning_legacy_baseline.json`.
  - **مستهلكان حقيقيّان حُدِّثا في نفس الالتزام (لا تأجيل) — يختلفان جوهريّاً عن PR-R2 (صفر مستهلك خارجيّ):** `services/sahool-platform/api/raster_service_client.py:191`'s `get_indices_sync` (`/indices` ⇐ `/v1/indices`) و`:448`'s `process_indicator_batch` (`/process/batch` ⇐ `/v1/process/batch`، يقود تجميع مؤشّرات `imagery_automation.py`). `test_p2_1_imagery_automation_raster_facade_guard.py` وdocstrings `imagery_automation.py` حُدِّثا معه.
  - **كلّ مرجع حرفيّ آخر عبر المستودع حُدِّث (بحث شامل لكلّ من الـ٢٠ مساراً قبل الالتزام):**
    - `tests_v9/test_raster_endpoint_auth_coverage.py`'s `SERVICE_ONLY`/`PUBLIC_CATALOG` — سبعة عشر إدخالاً حُدِّثت.
    - ثلاثة ملفّات اختبار وظيفيّة حقيقيّة تؤكّد وجود الديكوريتر الفعليّ: `test_change_detection.py:109`، `test_fvc.py:80`، `test_sar_rvi.py:58`، وأيضاً `test_field_intelligence_cloud.py`'s `test_indices_endpoint_wired_and_guarded`.
    - `scripts/ci/raw_data_processing_contract_guard.py` — **حارس CI حقيقيّ لا اختبار**، يفحص وجود `@router.post("/v1/raw/process")` حرفيّاً في `processing.py` + غياب المسار الخام من `main.py`؛ مصنوعه المولَّد `raw_data_processing_contract.generated.json` أُعيد توليده.
    - وصف نصّيّ في مهارة LLM غير مُتّصلة فعليّاً (لا نداء `httpx`) لكن حُدِّث للدقّة: `services/supervisor-agent/skills/remote_sensing_skill.py` ونسختها المكرَّرة `services/supervisor-agent/remote_sensing_skill.py` (كلتاهما — تكرار ملفّ سابق الوجود، خارج نطاق هذه الشريحة).
    - روابط STAC ذاتيّة الإشارة (self/search/data) في `cloud_native_catalog.py:37-45` — نفس درس `tile_url_template` من بحث PR-R1: تُضمَّن في استجابة `/v1/stac` الحيّة، فحُدِّثت رغم عدم استهلاكها خارجيّاً اليوم.
    - حقلا `note` استشاريّان في `timeseries_routes.py` يُرشِدان العميل لاستدعاء `/process` ثمّ `/imagery/timeseries/analyze` — حُدِّثا للمسارين الجديدين.
    - `docs/openapi/API_MAP.md` — أحد عشر سطراً (من أصل ٢٠؛ تسعة مسارات كانت غائبة أصلاً عن الوثيقة قبل هذه الشريحة — نقص سابق الوجود، لم يُملأ، خارج النطاق).
    - `docs/api/BACKEND_FRONTEND_COVERAGE.md` — أُعيد توليده فعليّاً عبر المولِّد، لا تحريراً يدويّاً.
  - **تُركت عمداً بعد تحقّق مباشر:** فحوص `test_roadmap_phase23.py`'s الناعمة (تمسح `main.py` الذي لم يحمل هذه المسارات قطّ بعد التفكيك — بائتة سابقة الوجود، `grep` أكّد الغياب المسبق) وفحصا مطابقة `"/process" in url` على عنوان مُموَّه (يبقيان صحيحَين حتماً كسلسلة جزئيّة بصرف النظر عن بادئة `/v1/`). `services/sahool-platform/api/routers/gis_cloud_native.py`'s `@router.get("/stac")`/`"/stac/collections")` — خدمة مختلفة تماماً (سحول-بلاتفورم، عقودها منذ Option B)، تطابق نصّيّ عرضيّ على مستوى الديكوريتر قبل تركيب بادئة راوترها الخاصّ، غير مرتبط.
  - **تحقّق حوكميّ إضافيّ (نفس درس `/stac` الوهميّ من Option B):** `build_platform_catalog.py --generate` بعد الهجرة ⇒ نظيف بلا `stale decision` — لا تكرار نصّيّ وهميّ جديد نتج عن نقل `/stac`/`/stac/collections`/`/stac/mosaicjson` (كانت raster-service المالك الحقيقيّ الوحيد المتبقّي لهذه النصوص أصلاً بعد إغلاق شبح سحول-بلاتفورم في Option B).
  - **اختبارا تكذيب جديدان مُثبتان بكسرهما فعليّاً ثمّ استعادتهما:** `tests_v9/test_api_versioning_policy_guard.py::test_raster_service_pr_r3_routes_are_versioned` و`tests/architecture/test_raster_service_route_migration_plan.py`'s `test_pr_r2_and_pr_r3_routes_stay_versioned_not_legacy`. وثيقة الخطّة وُسِمت "MIGRATED" لِـPR-R3 أيضاً، وباقي المسارات المُتتبَّعة (`ALL_BUCKETED`) صارت ٢ فقط (PR-R4).
  - **التحقّق:** `verify_all_generated.py` ⇒ صفر انحراف بعد دورتَي تصحيح (تجديد `capability_evidence_maturity_engine.py --generate` ثمّ إعادة بناء حزمة الإصدار) · `pytest -m unit`: **3763 نجح** (+١) · `ruff check .`/`ruff format --check .` نظيفان.
  - **التالي:** PR-R4 (٢ مساراً فقط — `tiles.py`، بلاط/عرض؛ صفر مستهلك خارجيّ حيّ مؤكَّد بالبحث الشامل في بحث PR-R1، يهاجر مباشرة بلا اسم مستعار توافقيّ).

- **raster-service PR-R4 — بلاط وعرض (2026-07-31)، آخر شريحة — يُغلَق نطاق raster-service الأصليّ بالكامل:** مساران هاجرا فعليّاً ⇐ `/v1/*` — `GET /tiles/{layer_id}/{z}/{x}/{y}.png`، `GET /layers/{layer_id}/tilejson` (`services/raster-service/routers/tiles.py:22,36`). السقف ٦١ ⇒ **٥٩** في `api_versioning_legacy_baseline.json`.
  - **صفر مستهلك خارجيّ حيّ — نفس نتيجة بحث PR-R1، مؤكَّدة مجدَّداً لا مفترَضة:** بحث شامل في `frontend/src/`، `mobile/sahool_app/lib/`، كلّ `nginx/*.conf`، كلّ `docker-compose*.yml`، وكلّ خدمة أخرى عن نداء حرفيّ أو متغيّر بيئة يحمل جزء المسار — صفر نتائج. الواجهة تستدعي عائلة `/v1/fields/{field_id}/tiles/...` المنفصلة تماماً (`routers/fields.py`، مُصدَّرة فعلاً). الهجرة إذن مقصورة على المراجع الداخليّة/الوثائقيّة، لا تحديث عميل متزامن.
  - **رابط ذاتيّ-الإشارة مُحدَّث رغم غياب المستهلك — نفس درس `tile_url_template`/STAC من PR-R1/PR-R3:** `tiles.py:63`'s حقل `tiles` في استجابة `"static-pregenerated"` (fallback عند عدم ضبط TiTiler) و`raster_job_orchestration.py:230`'s حقل `tile_url_template` (ميداني ميّت وفق بحث PR-R1، حُدِّث للاتّساق الداخليّ فقط) — كلاهما `f"/tiles/{layer_id}/..."` ⇐ `f"/v1/tiles/{layer_id}/..."`.
  - **فجوة تصنيف مصاحبة أُصلِحت استباقيّاً (لا بعد فشل CI):** `tests_v9/test_raster_endpoint_auth_coverage.py`'s `_is_layer_scoped(path)` كانت تطابق البادئة الخام `/tiles/{layer_id}`/`/layers/{layer_id}/` — لو تُركت، كان المساران سيصيران «غير مُصنَّفين» فور الهجرة (لا حارس ملكيّة/خدمة، وليسا في `PUBLIC_CATALOG`/`SERVICE_ONLY`). حُدِّثت لتطابق `/v1/tiles/{layer_id}`/`/v1/layers/{layer_id}/` **قبل** تشغيل السويت، وبُرهِنت بالتكذيب: عكس ديكوريتر واحد مؤقّتاً عبر `sed` أنتج رسالة الفشل المتوقَّعة حرفيّاً؛ استعادة الإصلاح أعادته أخضر.
  - **تنظيف تراكميّ اكتُشف بالمسح الشامل لهذه الشريحة — بقايا من PR-R2/PR-R3 لم تُصلَح وقتها:** `docs/openapi/API_MAP.md`/`ROUTE_INVENTORY.json` (إدخالا `tiles.py` الأخيران)، `skills/sahool-gis/RASTER_LAYER.md` (`/info/{layer_id}` أيضاً، فاتت PR-R3)، `skills/sahool-gis/TERRAIN_DEM.md` (`/terrain/slope`، فاتت PR-R3)، `docs/architecture/GIS_CLOUD_NATIVE_BEST_PRACTICES_PHASE4.md` (ثلاثة مسارات STAC، فاتت PR-R3)، `docs/architecture/db_ownership.yml` (تعليق `/gis/admin-boundaries`، فاتت PR-R3)، وأربعة ملفّات `docs/capability-registry/domains/*.yaml` (gis.yaml ٤ أسطر، satellite.yaml ١٨ سطراً، irrigation.yaml ٣ أسطر، operations.yaml سطران [`/offline/packs`+`/offline/packs/{pack_name}`، فاتا PR-R2]) — سكربت مسح نهائيّ أكّد صفر مرجع raster-service خام متبقٍّ في أيّ ملفّ `capability-registry/domains/*.yaml`.
  - **تُركت عمداً بعد فحص مباشر لا افتراض:** `docs/specs/A7_admin_boundaries_spec.md` (رأسه يُعلِن صراحةً «⏳ مسودّة للمراجعة» وملكيّة TBD — منفصل عن التنفيذ الحقيقيّ)، `docs/history/RASTER_SERVICE_REVIEW.md` و`docs/audits/RIV_DURABLE_PRODUCT_IDENTITY_AND_LEASES_REPORT_20260712.md` (سجلّ تاريخيّ مؤرَّخ)، `shared/enterprise_gis/phase8_global_scale.py:124` (قالب اختبار حمل عامّ يذكر `/stac` بلا صلة بـraster-service).
  - **اختبارا تكذيب جديدان، كلاهما مُثبَتان بكسرهما فعليّاً ثمّ استعادتهما:** `tests_v9/test_api_versioning_policy_guard.py::test_raster_service_pr_r4_routes_are_versioned` و`tests/architecture/test_raster_service_route_migration_plan.py`'s `test_pr_r2_pr_r3_pr_r4_routes_stay_versioned_not_legacy` (الملفّ أُعيد هيكلته: `ALL_BUCKETED` صار مجموعة فارغة، `test_measured_baseline_matches_the_bucketed_classification` يفرض صراحةً أنّ `legacy_unversioned_business` لِـraster-service أصبح فارغاً). وثيقة الخطّة `docs/architecture/raster_service_route_migration_plan.md` وُسِمت "MIGRATED" لِـPR-R4، مع بيان إغلاق كامل: كلّ الثلاثين مساراً الأصليّة مُصدَّرة الآن.
  - **التحقّق:** `guard.collect()` الحيّ يُظهِر raster-service الآن `Counter({'versioned': 78, 'infra': 3})` — صفر `legacy_unversioned_business` متبقٍّ لهذه الخدمة · `verify_all_generated.py` ⇒ صفر انحراف من أوّل تشغيل (بلا دورات تصحيح، خلافاً لـPR-R2/PR-R3) · `pytest -m unit`: **3764 نجح** (+١)، صفر انحدار · `ruff check .`/`ruff format --check .` نظيفان.
  - **بهذه الشريحة يُغلَق نطاق raster-service الأصليّ بالكامل** (٣٠ مساراً عبر أربع شرائح: PR-R1 تصنيف بلا هجرة، PR-R2 ٨ مسارات داخليّة/تشغيليّة، PR-R3 ٢٠ مساراً صور/كتالوج/معالجة، PR-R4 ٢ مساراً بلاط/عرض). التالي وفق الترتيب المُعلَن مسبقاً من المستخدم: soil-service ⇐ mcp_servers ⇐ erp-bridge (وodoo-bridge اسم مستعار تاريخيّ لـerp-bridge، لا خدمة مستقلّة). Auth (٢٤ مساراً) يبقى مؤجَّلاً حتى إثبات مستهلكين حيّين.
  - **PR:** انظر السجلّ التشغيليّ في `log.md` لرقم PR ورابط الدمج.

- **soil-service (2026-07-31، خامس خدمة بعد اكتمال raster-service بالكامل):** ٥ مسارات غير مُصدَّرة، كلّها `service_only` (بلا اختلاف ملكيّة يستحقّ تقسيمها كما في raster-service). السقف ٥٩ ⇒ **٥٤**.
  - **ما انتقل ⇐ `/v1/soil/*`:** `POST /soil/decode/modbus` (`services/soil-service/routers/modbus.py:35`)، `GET /soil/readings/{field_id}` و`POST /soil/ingest` (`routers/readings.py:22,37`)، `POST /soil/suitability` و`GET /soil/soilgrids` (`routers/soil_profile.py:46,57`). هجرة واحدة، PR واحد — لا تقسيم بالملكيّة كـraster-service إذ الخمسة `require_service_token` بلا تمايز.
  - **مستهلك حقيقيّ واحد وُجِد بالبحث الشامل عبر المستودع كلّه (لا افتراض)، حُدِّث في نفس الالتزام:** `services/sahool-platform/core/field_intelligence_adapters.py:105`'s `fetch_soil_baseline()` يستدعي `/soil/soilgrids` مباشرةً ⇐ `/v1/soil/soilgrids`؛ docstring الدالّة نفسها وثلاثة تعليقات وصفيّة في `field_intelligence_card.py`/`soil_climate_sources.py`/`api/routers/field_intelligence.py` حُدِّثت للدقّة.
  - **الأربعة الباقية بلا مستهلك خارجيّ حقيقيّ** — بحث شامل عبر frontend/mobile/nginx/docker-compose صفر نتائج؛ frontend's `soilApi` يستدعي مسارات مختلفة تماماً (`/soil/wofost_params/{id}`، `/soil/nitrogen/recommendation`، إلخ — راوترات أخرى في نفس الخدمة). بوّابة nginx's `/api/soil/` تمرّ عبر `service_proxy.py`'s `proxy_soil` (نمط field-segmentation/edge-inference — بروكسي شفّاف، العميل يحدّد المسار النهائيّ).
  - **مرجع حيّ غير-اختباريّ اكتُشف لم يكن ليظهر ببحث سطحيّ:** `runtime-verification/functional_probes/soil-service.json` — خطّة probe فعليّة تُشغَّل حيّاً عبر `functional_probe_runner.py` (لا pytest) تحمل `path: "/soil/suitability"` مرّتين + جملة في `note` — حُدِّثا كلاهما؛ `functional_probe_runner.py --check` أعاد التحقّق (`plans=3 probes=6`).
  - **كلّ مرجع حرفيّ آخر حُدِّث:** أربعة ملفّات اختبار وظيفيّة حقيقيّة (`test_modbus_decoder_20260703.py`، `test_soil_science_20260703.py`، `test_services_functional.py` — مُعلَّم `integration` لا يعمل في `-m unit` لكن حُدِّث لنفس الانضباط)، `_CRITICAL_ROUTES` في `test_soil_router_decomposition_guard.py`، docstring افتتاحيّ في `test_soil_field_tenant_authz.py` (سرد ثغرة IDOR سابقة، لكن يسمّي المسار الحيّ)، `docs/openapi/API_MAP.md`+`ROUTE_INVENTORY.json` (سطرا readings/ingest فقط — الثلاثة الأخرى غائبة أصلاً عن الوثيقتين، نقص سابق الوجود)، `docs/capability-registry/domains/soil.yaml` (SOIL-001's apis)، و`docs/NGINX_ROUTING.md` (صفّ `/api/soil/*` اليدويّ، وصف upstream فيه بائت أصلاً قبل هذه الشريحة لكن نصّ المسار حُدِّث).
  - **تُركت عمداً:** `sahool-brain/hot.md`/`log.md`'s سرد تاريخيّ لبناء هذه المسارات أصلاً (وصف جلسة ماضية)، و`docs/api/BACKEND_FRONTEND_COVERAGE.md` (مُولَّد فعليّاً، أُعيد توليده لا حُرِّر يدويّاً).
  - **عثرة اختبار غير مرتبطة اكتُشفت أثناء البحث، مُوثَّقة لا مُصلَحة:** `test_soil_router_decomposition_guard.py::test_no_app_route_decorators_in_main` يفشل سابقاً على `main` نفسه (قبل أيّ لمس لهذه الشريحة) — `main.py:197`'s `@app.get("/runtime-identity")` مسار بنية تحتيّة مُعلَن مباشرةً بلا راوتر؛ مُتحقَّق بـ`git stash` على الشجرة النظيفة فأكّد أنّه فشل قائم سلفاً غير ناتج عن هذه الهجرة، خارج نطاقها.
  - **اختبار تكذيب جديد، مُثبَت بكسرين منفصلين ثمّ استعادتهما:** `tests_v9/test_api_versioning_policy_guard.py::test_soil_service_routes_are_versioned` — كسر أوّل (إعادة `@router.get("/soil/soilgrids")`) أسقطه باسم المسار المتسرِّب؛ كسر ثانٍ (إعادة رابط adapters.py الخام) أسقطه باسم السطر المتسرِّب؛ استعادة كليهما أعادته أخضر.
  - **التحقّق:** `guard.collect()` الحيّ يُظهِر صفر `legacy_unversioned_business` لـsoil-service (٥٠ `versioned`، ٥ `infra`) · `verify_all_generated.py` ⇒ صفر انحراف من أوّل تشغيل · `pytest -m unit`: **3765 نجح** (+١)، صفر انحدار · `ruff check .`/`ruff format --check .` نظيفان.
  - **التالي وفق الترتيب المُعلَن مسبقاً:** mcp_servers، ثمّ erp-bridge (وodoo-bridge اسمه التاريخيّ لا خدمة مستقلّة). Auth (٢٤ مساراً) يبقى مؤجَّلاً حتى يثبت مستهلك حيّ.
  - **PR:** انظر السجلّ التشغيليّ في `log.md` لرقم PR ورابط الدمج.

- **mcp_servers (2026-07-31، سادس خدمة بعد soil-service):** ٧ مسارات REST سوق غير مُصدَّرة، كلّها Bearer/JWT عبر `Depends(_get_current_user)` (مُصادَقة مستخدم متصفّح لا توكن خدمة، بخلاف soil-service/raster-service). السقف ٥٤ ⇒ **٤٧**.
  - **ما انتقل ⇐ `/v1/*`:** `GET /suppliers/{supplier_id}`، `POST /procurement`، `GET /procurement/{order_id}`، `POST /sales`، `GET /sales`، `GET /price-history/{category}`، `GET /analytics/{tenant_id}` — كلّها `services/mcp_servers/market_server.py:643-691`. الملفّ يستعمل `@app.<method>` مباشرةً بلا `APIRouter`/`routers/` (بخلاف soil-service/raster-service المُفكَّكين) — نفس نمط تسجيل `GET /v1/products` المُصدَّر مسبقاً في الملفّ نفسه (شريحة الوكيل A الأولى، عقد MCP الذرّي)، فالهجرة تعديل حرفيّ مباشر بلا اعتبارات تركيب راوتر.
  - **صفر مستهلك خارجيّ حيّ عبر كامل المستودع (بحث شامل، لا افتراض):** frontend/mobile/nginx.v9.conf (لا بوّابة market فيه إطلاقاً)/supervisor-agent (يستدعي فقط عقد بروتوكول MCP `/v1/mcp/tools*` المُهاجَر سابقاً، لا نقاط REST هذه)/odoo-bridge (صفر نداء HTTP فعليّ، مجرّد ذكر عابر في تعليق) — صفر نتائج للسبعة كلّها. `nginx.fixed.conf`/`nginx.unified.conf`'s `/api/market/` (غائبة كليّاً من `nginx.v9.conf` الأساسيّ) بروكسي شفّاف بلا rewrite — لا حاجة لتعديل نغينكس.
  - **مرجع توضيحيّ اكتُشف ولم يُخلَط بمستهلك حقيقيّ:** `docs/MARKET_SYSTEM.md`'s مثال Dart (`lib/services/market_service.dart`) — تحقّق مباشر أكّد أنّ هذا الملفّ **غير موجود** في `mobile/sahool_app/lib/services/` فعليّاً (توضيحيّ في الوثيقة فقط) — حُدِّث للدقّة رغم كونه غير وظيفيّ.
  - **اكتشاف جانبيّ في capability-registry:** `docs/capability-registry/domains/farm_management.yaml`'s قدرتان تحملان أدلّة conservative-linked لـ`GET /analytics/{tenant_id}` و`POST`/`GET /procurement*` — تحقّق مباشر أنّ `mobile_consumers: inventory_screen.dart` المُدرَج في نفس القدرة **لا يستدعي** هذين المسارين فعليّاً (ربط `capability_linker.py` تحفّظيّ heuristic لا دليل نداء حقيقيّ) — حُدِّثت الأسطر الثلاثة للدقّة النصّيّة فقط، بلا تعديل `mobile_consumers`/`ui_consumers`.
  - **مرجعان حيّان غير-كوديَّين حُدِّثا:** `docs/MARKET_SYSTEM.md` (رسم ASCII للبنية + خمسة أمثلة `curl` + مثال Dart) و`docs/UNIFIED_SETUP.md`'s مثال `curl` حيّ لسير عمل التشغيل السريع (`/api/market/procurement` ⇐ `/api/market/v1/procurement`، عبر بروكسي شفّاف).
  - **اختبار تكذيب جديد، مُثبَت بكسره فعليّاً ثمّ استعادته:** `tests_v9/test_api_versioning_policy_guard.py::test_mcp_servers_market_rest_routes_are_versioned` — كسر مقصود (إعادة `@app.post("/sales")`) أسقط الاختبار فوراً باسم المسار المتسرِّب حرفيّاً؛ استعادة الإصلاح أعادته أخضر.
  - **دورة تصحيح واحدة في `verify_all_generated.py`:** `capability_management_engine.py --check` اكتشف انحرافاً (`capability_management_matrix.json`) لم تلتقطه الدورة الأولى — أُصلِح بـ`--generate` ثمّ إعادة بناء حزمة الإصدار.
  - **التحقّق:** `guard.collect()` الحيّ يُظهِر صفر `legacy_unversioned_business` لـmcp_servers (١١ `versioned`، ١٤ `infra`) · `verify_all_generated.py` ⇒ صفر انحراف بعد دورة تصحيح واحدة · `pytest -m unit`: **3766 نجح** (+١)، صفر انحدار · `ruff check .`/`ruff format --check .` نظيفان.
  - **التالي وفق الترتيب المُعلَن مسبقاً:** erp-bridge (وodoo-bridge اسمه التاريخيّ لا خدمة مستقلّة). Auth (٢٤ مساراً) يبقى مؤجَّلاً حتى يثبت مستهلك حيّ.
  - **PR:** انظر السجلّ التشغيليّ في `log.md` لرقم PR ورابط الدمج.

- **odoo-bridge/erp-bridge (2026-07-31، سابعة وآخر شريحة هجرة نشطة قبل Auth المؤجَّل):** ٧ مسارات، معظمها Bearer/JWT عبر `main.require_auth` باستثناء الويبهوك. السقف ٤٧ ⇒ **٤٠**.
  - **ما انتقل ⇐ `/v1/*`:** `GET /erp/provider`·`GET /config`·`GET /logs`·`GET /suppliers` (`routers/catalog.py`، أربعتها `require_auth`)، `GET /readyz/capabilities` (`routers/health.py`، بلا مصادقة)، `POST /sync` (`routers/sync.py`، `require_auth`)، `POST /webhook/odoo` (`routers/webhooks.py`، سرّ `X-Webhook-Secret` مشترك لا JWT — يُستدعى من Odoo خارجيّاً).
  - **قرار تصنيف `/readyz/capabilities`:** رغم موقعه بجوار `/healthz`/`/readyz` (المُصنَّفان `infra`) وتصميمه المُوثَّق كمستوى ثالث مستقلّ، الحارس صنّفه `legacy_unversioned_business` — بفحص المحتوى فعليّاً يُعيد بيانات قدرة ERP التشغيليّة لا حكماً على صحة الحاوية، فالتصنيف التجاريّ محقّ دلاليّاً أيضاً. لم يُطلَب استثناء تصنيفيّ جديد (بخلاف `/runtime-identity` المدعوم بعقد مُجمَّد صريح في CLAUDE.md).
  - **صفر مستهلك خارجيّ حيّ عبر كامل المستودع للستّة الأولى:** frontend/mobile/nginx.v9.conf (لا بوّابة odoo/erp فيه)؛ `nginx.unified.conf`'s `/api/odoo/`+`/api/erp/` بروكسيان شفّافان بلا rewrite؛ `market_server.py`'s `ERP_BRIDGE_URL` مُعرَّف كثابت لكن غير مُستهلَك (بيانات ميّتة، لا مقطع مسار مُلحَق أصلاً).
  - **`POST /webhook/odoo` خاصّ:** مُستدعًى من نظام Odoo خارجيّ عبر Automation Rule يُهيَّئه مسؤول بشريّ يدويّاً في واجهة Odoo — لا كود داخل هذا المستودع يستدعيه، فتحديثه اقتصر على مثال التوثيق الإرشاديّ (`docs/ODOO_INTEGRATION.md`) لضمان صحّة الإعداد المستقبليّ — حدّ صدق: لا سبيل للتحقّق من نداءات Odoo الحيّة الفعليّة من داخل المستودع.
  - **مرجع مُضمَّن حيّ في استجابات API — نفس درس `tile_url_template`:** `routers/sync.py`'s ثلاث رسائل خطأ استشاريّة (424/503) تُضمِّن نصّاً حرفيّاً "Check /readyz/capabilities for ..." يصل للعميل مباشرةً في جسم الاستجابة — حُدِّثت الثلاثة.
  - **مستندان في `docs/audits/` فُحِصا وتبيَّن أنّهما ليسا تقارير تدقيق مؤرَّخة (بخلاف نظرائهما الآخرين تحت نفس المجلّد) فحُدِّثا:** `ERPNEXT_SETUP_GUIDE.md` (دليل إعداد حاليّ الصيغة، لا تاريخ في الترويسة) و`ERP_PROVIDER_SWITCH.md` (وصف بناء ميزة، لا طابع تاريخيّ).
  - **`docs/ODOO_INTEGRATION.md` (مؤرَّخ 2026-05-19 لكن بصيغة دليل حيّ لا تقرير — نفس معاملة `MARKET_SYSTEM.md`) و`docs/UNIFIED_SETUP.md`** حُدِّثا (ثمانية أمثلة `curl`+Python في الأوّل، مثال واحد في الثاني).
  - **تصحيح ترافقيّ اكتُشف في `docs/openapi/API_MAP.md`:** `GET /products` بائت سابق الوجود (المسار الحقيقيّ `/v1/products` مُصدَّر منذ شريحة الوكيل A الأولى، لم تُصحَّح الوثيقة يومها) — صُحِّح ضمن نفس تعديل قسم odoo-bridge لتفادي ترك سطر متناقض بجوار الأسطر المُهاجَرة حديثاً.
  - **اختبار تكذيب جديد، مُثبَت بكسره فعليّاً ثمّ استعادته:** `tests_v9/test_api_versioning_policy_guard.py::test_odoo_bridge_erp_routes_are_versioned` — كسر مقصود (إعادة `@router.get("/erp/provider")`) أسقط الاختبار فوراً باسم المسار المتسرِّب حرفيّاً؛ استعادة الإصلاح أعادته أخضر.
  - **خمس دورات تصحيح متتالية في `verify_all_generated.py` — أطول سلسلة في هذه الجلسة:** `runtime_contract_generator.py` ⇒ `runtime_verification_harness.py` ⇒ `runtime_evidence_ingestion.py` ⇒ (`compose_runtime_target_resolver.py` + `integration_runtime_governance_closure.py` + `path3_runtime_readiness_closure.py` معاً في الدورة الأخيرة) — كلّ دورة أُعيد بعدها بناء حزمة الإصدار.
  - **التحقّق:** `guard.collect()` الحيّ يُظهِر صفر `legacy_unversioned_business` لـodoo-bridge · `verify_all_generated.py` ⇒ صفر انحراف بعد خمس دورات تصحيح · `pytest -m unit`: **3767 نجح** (+١)، صفر انحدار · `ruff check .`/`ruff format --check .` نظيفان.
  - **بهذه الشريحة تُغلَق كلّ سلاسل الهجرة المُعلَنة صراحةً من المستخدم.** الجرد الخام المتبقّي `legacy_unversioned_business` ٤٠ مساراً مُوزَّعة على ثلاث خدمات فقط:
    - **auth (٢٤):** مؤجَّل صراحةً حتى إثبات مستهلك حيّ (قرار مُسجَّل مسبقاً في هذه الجلسة).
    - **sahool-platform (٨):** ديون توافقيّة `compat_gateway.py`/`chat_proxy_reference.py` مؤجَّلة عمداً — مُوثَّقة مسبقاً في شريحة Option B (بوّابة توافق قديمة صريحة، خارج نطاق الهجرة).
    - **video-processor (٨، `routers/streams.py`) — اكتشاف جديد أثناء قياس ما بعد erp-bridge، لم يُذكَر في التسلسل المُعلَن مسبقاً (raster⇐soil⇐mcp_servers⇐erp-bridge):** `POST /streams`·`DELETE /streams/{id}`·`GET /streams/{id}`·`GET /streams`·`POST /streams/{id}/snapshot`·`GET /streams/{id}/snapshot`·`POST /streams/{id}/record/start`·`POST /streams/{id}/record/stop`. **لم يُبدَأ بحث استهلاك ولا هجرة — يحتاج قرار نطاق مستخدم صريح («ابدأ بـ...») قبل أيّ لمس، بنفس انضباط كلّ شريحة سابقة في هذه الجلسة.** — **أُغلِقت لاحقاً (2026-07-31) — انظر القسم أدناه.**
  - **PR:** انظر السجلّ التشغيليّ في `log.md` لرقم PR ورابط الدمج.

- **video-processor (2026-07-31، اكتشاف جديد، نُفِّذ بأمر مستخدم صريح بعد اكتشافه في قياس erp-bridge النهائيّ):** ٨ مسارات، كلّها Bearer/JWT عبر `main._get_current_user`. السقف ٤٠ ⇒ **٣٢**.
  - **ما انتقل ⇐ `/v1/streams*`:** `POST /streams`·`DELETE /streams/{stream_id}`·`GET /streams/{stream_id}`·`GET /streams`·`POST /streams/{stream_id}/snapshot`·`GET /streams/{stream_id}/snapshot`·`POST /streams/{stream_id}/record/start`·`POST /streams/{stream_id}/record/stop` — كلّها `services/video-processor/routers/streams.py:46-238`. نمط تسجيل مطابق تماماً لكلّ الشرائح السابقة (`register_routers(app)` بلا prefix).
  - **صفر مستهلك خارجيّ حيّ عبر كامل المستودع:** frontend/mobile صفر مرجع حرفيّ؛ لا خدمة أخرى تُعرِّف ثابت URL يُشير لـvideo-processor (بخلاف mcp_servers's `ERP_BRIDGE_URL` الميّت — هنا لا يوجد الثابت أصلاً).
  - **فارق مهمّ عن mcp_servers/erp-bridge:** `nginx/nginx.v9.conf` (الأساسيّة الحيّة) **تملك فعلاً** `location /api/video/` — لكنّها مُقيَّدة صراحةً بنطاقات شبكة داخليّة فقط (`allow 127.0.0.1; allow 10.0.0.0/8; allow 172.16.0.0/12; allow 192.168.0.0/16; deny all;`) مع تعليق صريح يصف video-processor كـ«سطح داخليّ/خدمة-لخدمة» لا واجهة متصفّح. البروكسي شفّاف بلا rewrite فلا حاجة لتعديله.
  - **capability-registry: صفر ربط أصلاً** — video-processor غائب كليّاً من `capabilities/registry/capabilities.json` ومن كلّ ملفّات `docs/capability-registry/domains/*.yaml` (فجوة تغطية قدرات موجودة سابقاً، خارج نطاق هذه الهجرة، لم تُملأ).
  - **تُركت عمداً بعد فحص مباشر:** ثلاثة ملفّات (`docs/audits/PONYTAIL_MCP_STREAMING_KG_EXECUTION_20260625.md`، `MCP_STREAMING_KG_COMPLETION_20260625.md`، `docs/architecture/agentic_rag_mcp_streaming_plan.md`) طابقت بحث "stream" نصّيّاً لكن تحقّق مباشر أكّد أنّها تخصّ مفهوماً مختلفاً تماماً (بثّ استجابات MCP/RAG، لا بثّ فيديو) — صفر مرجع حقيقيّ لـvideo-processor أو `/streams`.
  - **اختبار تكذيب جديد، مُثبَت بكسره فعليّاً ثمّ استعادته:** `tests_v9/test_api_versioning_policy_guard.py::test_video_processor_stream_routes_are_versioned` — كسر مقصود (إعادة `@router.delete("/streams/{stream_id}")` الخام) أسقط الاختبار فوراً باسم المسار المتسرِّب حرفيّاً؛ استعادة الإصلاح أعادته أخضر.
  - **التحقّق:** `guard.collect()` الحيّ يُظهِر صفر `legacy_unversioned_business` لـvideo-processor · `verify_all_generated.py` ⇒ صفر انحراف من أوّل تشغيل (كلّ مولّدات سلسلة runtime المُكتشَفة في erp-bridge شُغِّلت استباقيّاً هذه المرّة) · `pytest -m unit`: **3768 نجح** (+١)، صفر انحدار · `ruff check .`/`ruff format --check .` نظيفان.
  - **بهذه الشريحة لا يبقى شيء من `legacy_unversioned_business` إلّا خدمتان مؤجَّلتان بقرار صريح:** auth (٢٤) وsahool-platform (٨، ديون توافقيّة موثَّقة). **لا شريحة هجرة نشطة متبقّية** إلّا بأمر مستخدم صريح جديد.
  - **PR:** انظر السجلّ التشغيليّ في `log.md` لرقم PR ورابط الدمج.

- **auth (2026-07-31، الشريحة الأخطر والأخيرة المُعلَنة صراحةً — تسجيل دخول/جلسة/تفويض على مستوى المنصّة كلّها):** ٢٤ مساراً عبر تسعة ملفّات راوتر. السقف ٣٢ ⇒ **٨**.
  - **ما انتقل ⇐ `/v1/auth/*`:** `email_verify.py` (٤: `GET /verify`·`GET /verify/status`·`POST /verify/confirm`·`POST /verify/request`) · `invitations.py` (٤: `POST`/`GET /invitations`·`POST /invitations/accept`·`DELETE /invitations/{invitation_id}`) · `mfa.py` (٣: `/mfa/setup`·`/mfa/activate`·`/mfa/disable`) · `password_reset.py` (٢: `/password-reset/request`·`/password-reset/confirm`) · `registration.py` (٢: `/register`·`/change-password`) · `season_edge_sign.py` (١: `/edge-sign`) · `session.py` (٤: `/login`·`/refresh`·`/logout`·`/me`) · `tenants.py` (١: `/tenants`) · `users.py` (٣: `GET /users`·`/users/{user_id}/role`·`/users/{user_id}/deactivate`). نفس نمط التسجيل المسطّح (`register_routers(app)` بلا prefix) المُتّبَع في كلّ شرائح هذه الجلسة.
  - **طبقة أولى لم تظهر بأيّ شريحة سابقة — بوّابتا nginx داخليّتان حرجتان:** `location = /_auth_verify` (يستهدفها `auth_request` من ٧ مواقع في `nginx.v9.conf` وحده — vegetation/raster/remote-sensing-workspace ×2 + seasons ×2 — زائداً موقع مستقلّ ثانٍ في `frontend/nginx.conf` بهدف مختلف `sahool-auth:8000` لا `auth_backend`) و`location = /_auth_edge_sign` (يستهدفها `auth_request` من مسار قبول الموسم `POST /api/v1/seasons/{id}/accept`، `SEASON-RECORD-ENTRY-01` شريحة 3b). كانت `proxy_pass http://auth_backend/auth/verify;`/`.../auth/edge-sign;` حرفيّاً؛ عدم تحديثهما كان سيُسقِط JWT verification صامتاً (فشل مغلق 401 لا اختراق، لكن انقطاع كامل) خلف كلّ سطح محكوم بـ`auth_request`. حُدِّثت الثلاث (اثنان في `nginx.v9.conf`، واحد في `frontend/nginx.conf`) إلى `/v1/auth/verify`/`/v1/auth/edge-sign`.
  - **طبقة ثانية — موقع `/auth/` العميل المُواجِه في خمسة ملفّات nginx، اصطلاحان متضاربان قبل التعديل:** الواجهة (`authApi` قاعدتها `/auth`، تستدعي `.post('/auth/login')` ⇒ مزدوج `/auth/auth/login` على السلك) وعميل مباشر (`/auth/login` مفرد، مستخدَم في تطبيق الجوّال Flutter). `nginx.v9.conf`/`nginx.fixed.conf`/`frontend/nginx.conf` استخدمت `rewrite ^/auth/auth/(.*)$ /auth/$1 break;` (يُطبِّع المزدوج فقط، يُمرِّر الـURI كما هو لكلا الشكلين)؛ `nginx.unified.conf`/`nginx.light.conf` استخدمتا `proxy_pass http://auth_backend/;` (تجريد شرطة لاحقة يدعم المزدوج بالمصادفة فقط — تحقّق بجدول حقيقة يدويّ أنّه **لم يدعم قطّ** الاصطلاح المفرد، ثغرة سلوك سابقة الوجود لا شيء أُدخِلَته هذه الشريحة). الإصلاح المُوحَّد في الخمسة: قاعدتا `rewrite` (الأولى تُطبِّع المزدوج، الثانية المفرد، كلتاهما ⇐ `/v1/auth/$1`) — مُتحقَّق بجدول حقيقة يدويّ لكلا المدخلين، ومُتحقَّق أنّه يُبقي `tests_v9/test_auth_rls_and_routing.py::test_nginx_auth_routing_preserves_prefix` أخضر بلا تعديل جوهر التأكيدات. **لا مُصدِّق nginx محليّاً** (لا ثنائيّ nginx في هذا الصندوق) — التحقّق اعتمد كليّاً على المراجعة النصّيّة اليدويّة الشاملة بعد كلّ تعديل + حزمة اختبارات التأكيد الساكنة الموجودة.
  - **فجوة CI ثالثة اكتُشفت بالقراءة الذاتيّة لا بالافتراض:** `scripts/ci/endpoint_ui_coverage_gate.py`'s `has_frontend_evidence()` طبَّعت تاريخيّاً `/api/v1/auth/*` فقط (اصطلاح sahool-platform المنفصل الخاصّ به) ⇄ `/auth/*`. بعد ترقية auth، وإعادة تسمية قاعدة التصنيف `/auth/` ⇒ `/v1/auth/` في `config/endpoint_ui_coverage.json` (لازمة كي تبقى الـ٢٢ مساراً غير المُعفاة مُصنَّفة `farmer`/`admin` مواجِهاً للمستخدم بدل الانحدار الصامت إلى `internal` المُعفى من البوّابة العكسيّة)، كانت ستُنتِج ٢١ «مساراً هارباً» مُزيَّفاً. الإصلاح: `_AUTH_BACKEND_PREFIX_RE = re.compile(r'^/(?:api/v1|v1)/auth')` تطبّع كلا الاصطلاحين إلى `/auth`. **مُكذَّب فعليّاً:** إعادة المنطق القديم أنتجت فشلاً حرفيّاً بـ٢١ مساراً مُسمّاة (`endpoint-ui-coverage-reverse-gate: FAIL`)؛ استعادة الإصلاح أعادت `PASS — 425 core + 52 إعفاء`. حُدِّثت أيضاً ٢٠ إدخال `core_endpoints` (`endpoint` فقط؛ `evidence` بقي كما هو — نصّ استدعاء العميل الحرفيّ `/auth/x` لم يتغيّر) وإدخالا إعفاء (`/auth/edge-sign`، `/auth/me`) إلى `/v1/auth/*`.
  - **اكتشاف رابع بالقراءة الذاتيّة، لم يُذكَر في تقرير الوكيل الخلفيّ:** `frontend/src/config/endpoints.ts`'s `VITE_API_MODE=dev` (منافذ localhost مباشرة بلا بوّابة) كان افتراض قاعدة auth `http://localhost:8120` بلا `/v1` — استدعاء `authApi.post('/auth/login')` غير المُعدَّل كان سيصل حرفيّاً `http://localhost:8120/auth/login`، مساراً لم يعد قائماً على الخدمة بعد الترقية. أُصلِح بتضمين `/v1` في `devDefault` نفسه (`${localHttp(8120)}/v1`) — القاعدة فقط، لا نصّ استدعاء العميل — فتبقى `authApi.post('/auth/login')` بلا تغيير وتُنتِج المسار الصحيح.
  - **مستهلكون حقيقيّون فُحِصوا بالكامل ولم يُعدَّلا عمداً (بحث شامل لا افتراض):** `frontend/src/services/api/auth.ts` (٢٣ استدعاءً مُؤكَّداً) و`mobile/sahool_app/lib/services/api_service.dart` (٨ استدعاءات) — كلاهما يستدعي `/auth/*` الحرفيّ عبر nginx الذي يترجمه الآن؛ تعديلهما كان سيُغيّر عقداً عميلاً بلا حاجة. `bots/telegram/main.py:350` استدعاء مباشر لـ`AUTH_SERVICE_URL` (افتراضه `http://sahool-auth:8000` — **بلا** nginx بينهما) **عُدِّل** حرفيّاً `/auth/login` ⇐ `/v1/auth/login`.
  - **اختبار تكذيب جديد، مُثبَت بكسره فعليّاً ثمّ استعادته:** `tests_v9/test_api_versioning_policy_guard.py::test_auth_service_routes_are_versioned` — كسر مقصود (إعادة `@router.post("/auth/login")` الخام في `session.py`) أسقط الاختبار فوراً باسم المسار المتسرِّب حرفيّاً؛ استعادة الإصلاح أعادته أخضر.
  - **ملفّات اختبار مُحدَّثة** (استدعاءات `TestClient`/HTTP مباشرة بلا nginx بينها، فتتطلّب المسار الجديد حرفيّاً): `test_auth_e2e.py`، `test_auth_service.py`، `test_security.py`، `test_mfa_hardening_integration_v29_5.py` — زائداً تحديثات نصّيّة/توثيقيّة (لا تأكيدات تنفيذيّة، الاصطلاح الحرفيّ يبقى صحيحاً كسلسلة substring) في `test_auth_rls_and_routing.py`، `test_dev_gateway_raster_tile_auth_guard.py`، `test_season_gateway_nginx_static.py`، `test_season_edge_sign_endpoint_static.py`، `test_nginx_tenant_injection_guard.py`. سكربتات E2E (`scripts/smoke_e2e.py`، `scripts/e2e/live_full_e2e.py`، `scripts/e2e/spatial_flows.py`، `tests_v9/smoke_frontend_activation.sh`، `tests_v9/test_smoke_e2e.py`) تعمل عبر البوّابة فعبرت بلا تعديل — قاعدتها الافتراضيّة `http://localhost[:8080]` تمرّ عبر nginx الذي يترجم.
  - **وثائق مُحدَّثة:** `docs/openapi/API_MAP.md`/`ROUTE_INVENTORY.json` (١٢ من ٢٤ المُدرَجة سلفاً — نقص جزئيّ سابق الوجود، لم يُملأ)، `docs/capability-registry/domains/farm_management.yaml` (٢٥ سطراً بما فيها تكرار `edge-sign` في قدرة الموسم)، `satellite.yaml` (٢)، `security.yaml` (٣)، `docs/security/SEC-3.1_approvals_user_role.md`، `docs/runbooks/REAL_ENV_VERIFICATION_RUNBOOK.md`، `docs/api/UI_DEBT_MAP.md` (٦ إشارات). `docs/NGINX_ROUTING.md` أعيدت كتابة قسم `/auth/*` بالكامل — كانت تصف تقنيّة القطع بشرطة لاحقة وهي أصلاً **لا تطابق** ما في `nginx.v9.conf` الفعليّ (كان يستخدم `rewrite` سلفاً قبل هذه الشريحة)، تصحيح استباقيّ لتوثيق كان زائفاً من قبل هذه الهجرة لا فقط تحديث مسار.
  - **تُركت عمداً بعد فحص مباشر (سجلّ تاريخيّ، لا يُزيَّف بأثر رجعيّ):** `docs/audits/CODE_REVIEW_REPORT.md`، `CRITICAL_REVIEW_RESPONSE.md`، `NEW_TESTS_AND_FIXES.md` (روايات جولات مراجعة ماضية)، `docs/history/*`، و`docs/architecture/brain_deferral_baseline.json` (لقطة مجمَّدة لحارس انحراف مؤجَّل — تعديلها يُزيّف الأساس لا يُصحِّحه).
  - **التحقّق:** `guard.collect()` الحيّ يُظهِر صفر `legacy_unversioned_business` لـauth (٢٤/٢٤ `versioned`) · `endpoint-ui-coverage-reverse-gate` ⇒ PASS (425 core + 52 إعفاء) · `verify_all_generated.py` ⇒ صفر انحراف من أوّل تمريرة (نفس تحسين video-processor: تشغيل كلّ المولِّدات المكتشَفة استباقيّاً) · `pytest -m unit`: **3771 نجح**، صفر فشل، 26 تخطٍّ، بلا انحدار.
  - **بهذه الشريحة يُغلَق `legacy_unversioned_business` عند ٨ مساراً — كلّها sahool-platform (ديون توافقيّة `compat_gateway.py`/`chat_proxy_reference.py` موثَّقة منذ Option B، مؤجَّلة عمداً).** **auth كانت آخر شريحة هجرة نشطة مُعلَنة في هذه الجلسة — لا شريحة متبقّية إلّا بأمر مستخدم صريح جديد.**
  - **PR:** انظر السجلّ التشغيليّ في `log.md` لرقم PR ورابط الدمج.

- **إحكام حوكميّ للحارس نفسه (2026-07-31، لا هجرة مسار جديدة — طلب مستخدم مباشر بعد تدقيق مستقلّ لنتائج شريحة auth):** `api_versioning_policy_guard.py`'s `--check` كان يفرض شرطاً واحداً فقط — `len(current) <= ceiling` (عدّ صرف) — لا مطابقة هويّة. هذا يسمح نظريّاً باستبدال دَين قديم مُقفَل بدَين جديد مختلف كلّياً طالما العدد الكلّي لا يتجاوز السقف: إغلاق مسارَين ثمّ اكتشاف/فتح مسارَين آخرَين مختلفَين كان سيمرّ الحارس صامتاً طالما العدد لا يتجاوز السقف — لم يكن يُثبَت أنّ **نفس** المجموعة تتقلّص، فقط أنّ **حجمها** لا ينمو.
  - **الإصلاح:** أُضيف حقل `routes` إلى `api_versioning_legacy_baseline.json` — مجموعة مُجمَّدة صريحة للثمانية مسارات المتبقّية (كلّها sahool-platform: `compat_gateway.py`×7 + `chat_proxy_reference.py`×1) — وشرط ثانٍ مستقلّ في `--check`: `current_legacy_set ⊆ frozen_routes_set`. أيّ مسار في القائمة الحيّة غير موجود في `routes` المُجمَّدة يُسقِط CI فوراً بالاسم الصريح، بصرف النظر عن العدد الكلّي. الحقل `ceiling` (عدد صرف) يبقى للتوافق الرجعيّ والعرض السريع، لكنّ الإنفاذ الفعليّ الآن على المجموعة لا العدد.
  - **مُكذَّب فعليّاً بطريقتين:** اختبار pytest جديد `tests_v9/test_api_versioning_policy_guard.py::test_baseline_check_rejects_legacy_route_swap_not_just_count` — يُسقِط مساراً واحداً من `routes` مؤقّتاً (داخل `try/finally` يضمن الاستعادة)، يشغّل `--check` عبر subprocess حقيقيّ، يؤكِّد الفشل الحرفيّ باسم المسار الهارب صراحةً، ثمّ يستعيد الأصل ويؤكِّد `--check` أخضر. ومحاكاة يدويّة منفصلة أُجريت أوّلاً (قبل كتابة الاختبار): استبدال `POST /api/chat` بمسار وهميّ `GET /api/fake-new-legacy-route` بنفس العدد الإجماليّ (٨) عبر تلاعب مباشر بـ`api_versioning_legacy_allowlist.generated.json` — اصطدم أوّلاً بحارس الانحراف **الموجود مسبقاً** (`api versioning inventory drift`، لأنّ `write()` يعيد توليد الملفّ من الحساب الحيّ فيكتشف تلاعبي) قبل الوصول لمنطقي الجديد؛ الطريقة الصحيحة لاختبار المنطق الجديد فعليّاً هي تعديل `routes` في الأساس **لا** الملفّ المولَّد نفسه — درسٌ مُسجَّل في الاختبار.
  - **التحقّق:** `pytest -m unit`: **3772 نجح** (+١)، صفر فشل. `verify_all_generated.py` ⇒ صفر انحراف بعد دورتَي تصحيح (`capability_mapping_engine.py --generate` ثمّ `pr_capability_impact_gate.py --generate-index` ثمّ إعادة بناء حزمة الإصدار — نفس نمط التصحيحات التسلسليّة في شرائح سابقة، سببها الفعليّ حساسيّة `capability_mapping_engine`/الحزمة لأيّ تعديل في `api_versioning_legacy_baseline.json`، لا خطأ منطقيّ في الإصلاح نفسه). لا هجرة مسار في هذه الشريحة — تحصين حارس فقط، سقف `legacy_unversioned_business` يبقى ٨.
  - **PR:** انظر السجلّ التشغيليّ في `log.md` لرقم PR ورابط الدمج.

- **إغلاق موضوعيّ (2026-07-31، إيجابيّة كاذبة + إعادة توصيف الباقي — لا هجرة مسار):** بعد إحكام الحارس، فُحِصت الثمانية المتبقّية بالقراءة المباشرة للمصدر لا بالافتراض. النتيجة: **لا واحد منها قابل للهجرة**، وواحد منها ليس مساراً أصلاً. السقف ٨ ⇒ **٧**.
  - **الإيجابيّة الكاذبة — `POST /api/chat` (`services/sahool-platform/api/chat_proxy_reference.py:109`):** الجرد ادّعى مساراً **لا يخدمه التطبيق العامل**. أربعة أقفال بنيويّة مستقلّة: (١) الملفّ في `api/` لا `api/routers/`؛ (٢) `register_routers()` يُسجّل تلقائيّاً وحدات `api/routers/` وحدها عبر `pkgutil.iter_modules(_routers_pkg.__path__)` (`api/router_registry.py:41`)؛ (٣) صفر استيراد إنتاجيّ في المستودع كلّه — المطابقتان الوحيدتان تعليق عربيّ في `ai_provider_config.py:4` ونصّ docstring داخل الملفّ نفسه، لا `import` واحد؛ (٤) لا يُصدِّر `router` إطلاقاً بل `app = FastAPI(...)` داخل `try/except ImportError` كمثال مستقلّ (`uvicorn api.chat_proxy_reference:app`)، وdocstring صريح: «هذا ملف مرجعي يوضّح النمط… النواة الحالية لا تتضمّن خادماً». **سابقة مستقلّة تؤكّد الحكم:** `tests_v9/test_endpoint_auth_coverage.py:60` يستثنيه **بالاسم** منذ قبل هذه الشريحة. نفس صنف `GET /probe` المُصلَح 2026-07-30.
  - **الاستبعاد مسنود ببرهان لا بادّعاء:** `_UNMOUNTED_REFERENCE_FILES` في `api_versioning_policy_guard.py` + اختبار `test_chat_proxy_reference_is_structurally_unmounted` **يُثبِت الحقائق الأربع** بدل تأكيدها. **مُكذَّب بكسر الأربعة فعليّاً واحداً واحداً:** نسخة داخل `api/routers/` ⇒ فشل · تغيير آليّة المسح ⇒ فشل مُسمّى · `import` إنتاجيّ ⇒ فشل يسمّي الملفّ المستورِد · `router = …` ⇒ فشل مُسمّى؛ والاستعادة خضراء في الأربع. فلو رُكِّب الملفّ يوماً يسقط CI بدل بقاء الاستثناء صامتاً.
  - **إعادة توصيف السبعة الباقية — عقود توافق دائمة لا ديون مؤجَّلة:** كلّها `api/routers/compat_gateway.py`. أربعة أسماء بديلة صحّيّة (`/api/indicators/readyz`·`/api/weather/readyz`·`/api/vegetation/readyz`·`/api/agent/health`) تُعيد حمولة صحّيّة خالصة `{"status": "ready", "service": …, "mode": "alias"}` بصفر بيانات عمل (`:26-49`)؛ وثلاثة تمرير ضيّق (`/api/vegetation/v1/all_fields`·`/api/vegetation/v1/analyze`·`/api/raster/{path:path}`) موثَّق بالمصدر بأنّه «fallback ضيق وآمن… حين تُمرّر بيئات nginx/compose **قديمة** مساراتها إلى المنصّة» (`:105-109`). **نقل أيٍّ منها إلى `/v1/` يُلغي الغرض الذي وُجِدت له** — العميل القديم الذي يستدعي `/api/indicators/readyz` يتلقّى 404، وهو عين الانقطاع الذي أُنشِئ الاسم البديل لمنعه. فالحملة **مكتملة موضوعيّاً**: كلّ ما كان قابلاً للهجرة هوجِر (٧٤٩ ⇒ ٧ عبر الجلسة)، والباقي عقد دائم يُوثَّق ولا يُهاجَر.
  - **مؤجَّل عمداً بحدّ صدق صريح (API-VERSIONING-GUARD-IS-A-MIRROR-01):** الأربعة الصحّيّة تفوتها بوّابة `infra` لسبب تقنيّ بحت — `_classify()` يطابق `/health` بادئةً أو عضويّة مضبوطة في `{"/readyz", …}`، و`/api/…/readyz` **لاحقة لا بادئة**. إعادة تصنيفها (٧ ⇒ ٣) دفاعها الدلاليّ قويّ ونظيرها `/runtime-identity` أُعيد تصنيفه سابقاً — **لكنّها لم تُنفَّذ**: ذاك كان مسنوداً بعقد مُجمَّد صريح في CLAUDE.md (`platform_route_placement_contract.json`) وهذه بلا نظير، وخفض العدد بإعادة تصنيف بلا عقد يُقرأ تحسينَ رقم لا تصحيحاً. تُترَك لقرار مالك صريح.
  - **التحقّق:** `pytest -m unit`: **3773 نجح** (+١)، صفر فشل · `verify_all_generated.py` ⇒ صفر انحراف · `--check` أخضر على السقف ٧ والمجموعة المُجمَّدة السبعة.
  - **PR:** انظر السجلّ التشغيليّ في `log.md` لرقم PR ورابط الدمج.

- **عقد التوافق الدائم (2026-07-31، بمراجعة المالك على #734 — `legacy_unversioned_business` ⇐ ٠):** المراجعة أقرّت نطاق #734 وحكمه (false positive مُزال · ٧ عقود مقصودة · دَين قابل للهجرة = ٠)، ورصدت أنّ شرطاً واحداً من شروط القبول الثمانية غير مستوفٍ: التقارير ما زالت تعرض السبعة تحت لافتة `legacy_unversioned_business` أي «سبعة ديون»، بينما الحقيقة «صفر ديون + سبعة عقود». هذه الشريحة تُصلح التوصيف نفسه — لا هجرة مسار ولا إخفاء.
  - **العقد المركزيّ:** `docs/architecture/permanent_compatibility_contract.json`، مفتاح كلّ إدخال **method + مسار مُطبَّع**. التطبيع يستبدل كلّ معامل بـ`{}` فيُعرَّف **شكل** المسار لا تسمية معاملاته (`/api/raster/{path:path}` ⇒ `/api/raster/{}`): إعادة تسمية معامل لا تُسقِط المطابقة (لا إنذار كاذب) ولا تفتح ثغرة (لا هروب بإعادة تسمية).
  - **الفئتان المُسمّاتان:** `permanent_health_compat_alias` (٤: `/api/indicators/readyz`·`/api/weather/readyz`·`/api/vegetation/readyz`·`/api/agent/health`) و`permanent_compatibility_gateway` (٣: `/api/vegetation/v1/all_fields`·`/api/vegetation/v1/analyze`·`/api/raster/{path:path}`).
  - **ليست `infra` — وهذا جوهر الفرق عن إعادة التصنيف المرفوضة سابقاً:** الفئتان تظهران في الجرد وCSV وفي حقل `permanent_compatibility_routes` الجديد بقائمة السماح المولَّدة. تُسمّى ولا تُخفى. العقد يوثّق ذلك صراحةً في حقل `not_infra`، ويسجّل أنّ إعادة تصنيف الأربعة الصحّيّة إلى `infra` تبقى **قراراً معماريّاً مستقلّاً لم يُتَّخذ**.
  - **إنفاذ ثلاثيّ، كلّه مُكذَّب فعليّاً:** (١) **السقف ٠** ⇒ أيّ مسار غير مُصدَّر جديد لا يطابق العقد يُسقِط CI — والاختبار يذهب أبعد: يطبّق العلاج المُوثَّق («أعِد التوليد») ثمّ يؤكّد الفشل المستمرّ على `0 ⇒ 1`، فيُثبِت أنّ إعادة التوليد **لا تُبيّض** مساراً جديداً. (٢) **adjudication إلزاميّ:** إضافة اسم بديل دائم تتطلّب تعديل ملفّ العقد صراحةً — مُثبَت بمِسبار على شكل alias صحّيّ (`/api/probe-newservice/readyz`) رُفِض لأنّه ليس في العقد. (٣) **إنفاذ عكسيّ:** إدخال عقد بلا مسار حيّ مطابق يُسقِط CI — الاتّجاه الأمامي مضمون بنيويّاً (التصنيف يأتي **من** العقد فلا مسار دائم خارجه) لكنّ العكس ليس كذلك، وإدخال ميّت يبقى صامتاً ويُغطّي سلفاً مساراً يُعاد إدخاله بنفس التوقيع بلا adjudication جديد.
  - **إعادة صياغة اختبار المجموعة من #733 (فشل حقيقيّ كشفه التشغيل، لا تعديل تجميليّ):** بعد أن صارت مجموعة legacy فارغة (السقف ٠)، صار شرط `current_set ⊆ frozen_set` غير قابل الوصول عبر بيانات حقيقيّة — المجموعة الفارغة جزء من كلّ شيء، وأيّ مسار legacy حيّ يسقط على السقف أوّلاً. فبدل حذف الاختبار أو تركه يفشل، أُعيد بناؤه ليصنع الحالة صناعيّاً: سقف **يقبل** العدد (١≤١) ومجموعة مُجمَّدة **لا تحوي** المسار الحيّ ⇒ لا شيء يرفضه إلّا شرط المجموعة. ويؤكّد الاختبار ذلك صراحةً بـ`assert "نمت" not in output` (أي لم يسقط على العدد). الثابت يبقى محروساً ليوم يعود فيه دَين.
  - **التحقّق:** `pytest -m unit`: **3776 نجح** (+٣)، صفر فشل · `verify_all_generated.py` ⇒ صفر انحراف · العدّاد الحيّ: `{versioned: 937, infra: 101, internal_s2s: 24, graphql_facade: 1, permanent_health_compat_alias: 4, permanent_compatibility_gateway: 3}` — `legacy_unversioned_business` **غائب تماماً**.
  - **PR:** انظر السجلّ التشغيليّ في `log.md` لرقم PR ورابط الدمج.

## WORKFLOW-TEMPLATE-COMPLETES-AS-SUCCESS-01 — مُغلقة (2026-07-31)

- **العلّة (مُبرهَنة بالقياس لا بالقراءة):** `services/sahool-platform/core/workflow_engine.py` يخزّن نتيجة المعالِج ويُعلّم الخطوة مكتملة **بلا فحص محتوى إطلاقاً** — مسح الملفّ كلّه أعطى **صفر** `result.get(...)`/`result[...]`. فالاكتمال دالّة في «هل رمى المعالِج؟» وحدها (`:713` متزامن، `:844` async).
- **الأثر:** قوالب الريّ الأربعة (`api/workflow_definitions.py:184/190/196/202`) تُعيد `{"…": True, "_template": True}` ولا تفعل شيئاً، فتبلغ `COMPLETED` بمسار **مطابق بايتاً** لمعالِج حقيقيّ. والوسم `_template` **لا يقرؤه شيء في الإنتاج**: قراءاته الخمس كلّها في `tests/test_irrigation_workflow_handlers.py`. فكان إشارة **ميتة** لا ضعيفة، وهذا المسار الوحيد القادر على تسجيل **نجاح غير حقيقيّ** في المحرّك.
- **الإصلاح:** `_reject_template_result(step_id, result)` يُستدعى **داخل** كتلة `try` في كلا مساري التشغيل، فيرث مسار الفشل القائم بالكامل (`FAILED` + تعويض Saga إن طُلِب + قابليّة الاستئناف) بلا حالة جديدة ولا مسار موازٍ. الوسم صار مقروءاً حيث يُهمّ.
- **مُكذَّب فعليّاً:** إزالة الحارس تُسقِط **٤ من ٥** اختبارات جديدة، والخامس (`test_real_result_still_completes`) يبقى **أخضر** — فيُثبِت أنّ الحارس يميّز لا يُفشِل الجميع. ومخرَج الفشل يعرض العلّة حيّة: `status=COMPLETED` لسير عمل قالبيّ بالكامل.
- **اكتشاف مصاحب — اختبار كان يحرس الكذبة:** `tests/test_workflow_definitions.py::test_end_to_end_built_steps_run_to_completion` كان يؤكّد أنّ `irrigation_cycle` (بالعلم المُطفأ ⇒ أربعة قوالب) يبلغ `COMPLETED` بخطواته الأربع — أي يُرمِّز النجاح غير الحقيقيّ ويحرسه ضدّ الإصلاح. أُعيد بناؤه ليؤكّد **عدم** الاكتمال وتسمية السبب، مع إحالة صريحة إلى `test_irrigation_workflow_handlers.py::test_real_workflow_suspends_then_resumes_with_approval` الذي يغطّي اكتمال المسار الحقيقيّ.
- **نطاق الأثر مقيس لا مفترَض:** **صفر** مستهلك حيّ لسير الريّ خارج ملفّ تعريفه (بحث شامل في `services/` باستثناء الاختبارات والتعريف)، ولا اختبار آخر كان يؤكّد اكتمال القالب عبر المحرّك. فالتغيير لا يمسّ سلوكاً إنتاجيّاً قائماً.
- **حدّ صدق:** العلم `FEATURE_IRRIGATION_WORKFLOW_REAL` مُطفأ افتراضاً وتوثيقه يَعِد «صفر كسر على السلوك القائم». هذا الحارس **يغيّر** ذلك عمداً: السلوك القائم كان نجاحاً زائفاً، وضمانه ضمانٌ للكذبة. الآن المسار الافتراضيّ يفشل بوضوح ويسمّي العلاج (فعّل المعالِج الحقيقيّ أو أزِل القالب) بدل أن يبلغ اكتمالاً كاذباً.
- **التحقّق:** `pytest -m unit`: 3776 · مجموعة المنصّة (`Platform Unit Tests`): **4014 نجحت**، صفر فشل · `ruff` نظيف.
- **PR:** انظر السجلّ التشغيليّ في `log.md`.

## VERIFY-ALL-GENERATED-WRITER-FLAG-MISMATCH-01 — مُغلقة جزئيّاً (2026-07-31)

- **العلّة عطلان لا عطل:** (١) ثلاثة كتّاب انحرفوا فعليّاً وكانوا **غائبين عن `_GENERATE_FLAG`** فلم يُستدعوا إطلاقاً، فمرّت الدورات الثلاث بلا تغيير وأُبلِغ «لم تثبت المصنوعات». (٢) طباعة الصدق الموجودة أصلاً — «فُحِصت ولا تُولَّد آليّاً» — كانت **غير قابلة للوصول على مسار الفشل**: موضعها بعد الحلقة، والفشل يعود `return 1` قبلها. فالمعلومة تُحسَب ثمّ تُرمى في اللحظة التي تُحتاج فيها.
- **تصحيح لتشخيصي الأوّل:** قلتُ إنّ المكنسة «تفترض `--generate`». **خطأ.** `_GENERATE_FLAG` خريطة صريحة لكلّ سكربت تحمل أصلاً `--apply` و`--write-registry`، و`regenerate()` تضع غير المُدرَج في `manual` ولا تُخمّن له علماً. فالعيب صفوف ناقصة + رسالة محجوبة، لا عدم تطابق واجهات — والتوحيد القسريّ للأعلام كان سيغيّر ثلاث واجهات عموميّة بلا داعٍ.
- **القياس:** ٣٨ سكربتاً في قائمة «لا يُولَّد آليّاً»، منها **٢٣ تُعلن علم كتابة في مصدرها** (قابلة للإضافة ميكانيكيّاً) و١٥ فحوص بلا مولّد (يدويّة بالتصميم). أي أنّ الخريطة كانت تغطّي أقلّ من نصف ما تستطيع.
- **العلاج في هذه الشريحة:** أُضيف الثلاثة **المُثبَتون بالانحراف** بعلمهم المُعلَن في مصدرهم؛ وفُصِلت رسالة الفشل إلى ثلاثة أسباب مميَّزة (كاتب لم يُستدعَ · فحص بلا مولّد · دورة/لاحتميّة حقيقيّة) وطُبِعت **قبل** `return 1`.
- **مُكذَّب:** إسقاط إدخال ⇒ فشل يسمّي السكربت وعلمه · ربط `capability_linker` بـ`--generate` (وهو لا يُعلنه) ⇒ فشل يسمّي عدم المطابقة. الثاني يحرس تحديداً ضدّ «توحيد الأعلام» بلا دعم في المصدر.
- **حدّ صدق:** لم أُضِف العشرين الباقية. استدعاء علم كتابة آليّاً يفترض أنّه **إعادة توليد نقيّة**، و`--apply` في `capability_linker` يطبّق مرشّحات فوق عتبة — دلالة قد تختلف. إضافتها تحتاج مراجعة دلاليّة لكلّ سكربت، وهي قرار مستقلّ مُسجَّل هنا لا مُنفَّذ صامتاً.
- **الخطر البنيويّ الباقي:** الخريطة قائمة يدويّة تتخلّف صامتة — الصنف نفسه الذي بُني له `arch_test_ci_coverage_guard.py`. الاكتشاف من argparse لكلّ سكربت هو الحلّ المتوسّط المدى.
- **الجولة الثانية (2026-08-01، ‏٩ ⇒ ٣):** أُغلِقت الستّة التي كان **شرط إغلاقها نفسه غير قابل للتحقّق**. الشرط يبدأ بـ«أفسِد مصنوعة ⇒ يجب أن يرصد `--check`»، وهي كانت عمياء عن ١٣ من ١٦ مصنوعة تملكها (`GENERATED-CHECK-IGNORES-ITS-OWN-COMPANION-ARTIFACTS-01`)؛ فوصلها قبل إصلاح العمى كان سيُصلح انحرافاً لا يستطيع أحد رصده. بعد توحيدها على `scripts/ci/generated_artifact_contract.py` مرّ الشرط كاملاً على كلٍّ منها: خمول على شجرة نظيفة · رصد الإفساد **مع تسمية الملفّ** · استعادة بايتاً بايت · ولا يمسّ العلم ملفّاً غير الذي سمّاه الانحراف.
- **الباقي ثلاثة، وسببها واحد لا صلة له بالعمى:** `capability_management_engine` · `capability_registry_guard` · `runtime_environment_preflight` — **غير خاملة**: تشغيل العلم على شجرة نظيفة يُغيّر ملفّاً في كلّ مرّة، فوصلها يجعل كلّ مكنسة تُوسِّخ الشجرة بفرق لا يقابله تغيير مصدر.


## DEFERRED-IMPORT-UNDECLARED-01 — النموّ مُغلَق / الدَّين مفتوح (baseline 3، 2026-07-31)

- **العلّة (نقطة عمياء في حارس قائم، لا غياب حارس):** `tests_v9/test_requirements_completeness.py` كان يرصد بتعبير نمطيّ **مرتكز على العمود صفر** (`^(?:from|import)`)، وعلّق ذلك صراحةً بأنّ المهمّ هو الإقلاع. فالاستيراد **المؤجَّل** داخل دالّة لم يكن يُرى أصلاً. وثانياً: `redis` لم تكن في خريطة الحزم `CHECK` **رغم إعلانها في ثمان خدمات**. النقطتان معاً أخفتا الصنف كلّه.
- **لماذا التأجيل لا يُلغي العطل:** الحزمة الناقصة لا تُسقِط الإقلاع بل **تؤجّل الانهيار إلى أوّل استعمال**، وغالباً يبتلعه `except Exception` عريض فيظهر «الخدمة غير متاحة» — فيُرسَل المشغّل إلى خادم سليم بينما العطل نقصٌ في الصورة. أسوأ تشخيصاً من الفشل المبكر، لا أخفّ.
- **القياس بعد إصلاح الحارس:** **ثمانية** مواضع في **خمس** خدمات، لم يكن أيّ منها مرئيّاً. صُنِّفت بقراءة كلّ موضع لا بالاسم: أربعة `optional_by_design` (بديل صادق موثَّق) وثلاثة `undeclared_debt` وواحد أُصلِح.
- **`undeclared_debt` (مُجمَّد، ثلاثة):** `raster-service:yaml` (المعالِج يلتقط `(FileNotFoundError, OSError)` فقط ⇒ ImportError ينتشر) · `sahool-platform:sklearn` (**استيراد مؤجَّل عارٍ بلا try/except إطلاقاً** — أخطرها) · `ai_agronomist:redis` (الإنتاج يرفع RuntimeError بدل السقوط ⇒ مطلوب إنتاجاً وغير مُعلَن).
- **لماذا لم تُعلَن الثلاث في هذه الشريحة:** `CLAUDE.md` يوجب `pip-audit` **قبل** أيّ إضافة تبعيّة، وpip-audit غير متاح في هذه الحاوية. وscikit-learn/pyyaml قرار وزن صورة لا سطر نصّ. الإعلان بلا فحص يخالف قاعدة المستودع؛ فجُمِّدت بشرط إغلاق مكتوب لكلّ واحدة.
- **الحالة الوحيدة المُصلَحة:** `decision-service:redis` — انظر الفجوة أدناه.
- **الإنفاذ:** فئتان في `docs/architecture/deferred_import_declaration_contract.json`، وإنفاذ عكسيّ (إدخال بائت يُسقِط CI، كعقد #735).
- **مُكذَّب ثلاثاً:** إسقاط إدخال ⇒ فشل يسمّي `raster-service:yaml` ومواضعه · إدخال بائت ⇒ فشل يسمّيه · استيراد مؤجَّل جديد في `services/auth` ⇒ فشل يسمّي `auth:numpy` والسطر. والاستعادة تُعيد الأخضر.
- **حدّ صدق:** الحارس **يمنع النموّ ولا يُصلِح الثلاثة**. التسمية تفصل الحالتين عمداً (درس #737: «مرصودة ومُجمَّدة» ليست «مُعالَجة»).

## DECISION-SERVICE-REDIS-DEPENDENCY-GAP-01 — مُغلقة (2026-07-31)

- **الاتّجاه مقيس لا مُخمَّن:** **مُستعمَلة وغير مُعلَنة**. `main.py:225` يستورد redis كسولاً، و`requirements.txt` كان خمسة أسطر بلا redis، وDockerfile:15 يثبّت ذلك الملفّ وحده — ولا شيء من fastapi/uvicorn/httpx/pydantic/asyncpg يجرّها عبَراً.
- **لماذا بقيت كامنة:** المسار مسوَّر بمتغيّرين فارغين افتراضاً (`DECISION_WORKER_ASSERTION_KEY` و`..._REDIS_URL`)، فالنشر الافتراضيّ لا يبلغه. **والإقلاع لا يفشل** — صياغة «قد يفشل إقلاعاً» في تسجيلي الأوّل كانت غير دقيقة: الاستيراد كسول، فالفشل عند الطلب لا عند الإقلاع.
- **الأثر الحقيقيّ — سوء تشخيص لا انقطاع:** بتفعيل ربط هويّة العامل (الإنتاج الموصوف في `docker-compose.v9.yml:1374-1375`)، كلّ طلب يعود `503 "worker assertion replay store unavailable"` بينما Redis سليم؛ السبب الحقيقيّ `ModuleNotFoundError` يبتلعه `except Exception` العريض.
- **العلاج شقّان:** (١) إعلان `redis>=5.0.0` — القيد نفسه المُعلَن في خمس خدمات شقيقة. (٢) **فصل العطلين في الرسالة**: `except ModuleNotFoundError` منفصل يعيد `replay store misconfigured: redis not installed` بدل دمجه مع تعذّر الاتّصال.
- **حدّ صدق:** `pip-audit` **لم يُشغَّل** (غير متاح في الحاوية) خلافاً لقاعدة `CLAUDE.md`؛ المخفّف أنّ القيد مطابق لخمس خدمات قائمة يفحصها CI. يلزم تأكيده في CI.
- **مُثبَت بالكاشف نفسه:** بعد الإعلان اختفى `decision-service:redis` من مجموعة `_undeclared_deferred()` الحيّة (٨ ⇒ ٧) — لا بادّعاء بل بقياس.
- **ملاحظة تغطية:** `tests/test_worker_identity_binding.py:185-195` كان يمرّ **سواء أُثبِّتت redis أم لا** (كلا العطلين ⇒ 503 نفسه)، فلم يوفّر تغطية للتبعيّة إطلاقاً.

## BRAIN-ACTUATOR-BYPASS-UNGUARDED-01 — مُغلقة (2026-07-31)

- **العلّة:** المبدأ «الدماغ لا يصل فيزيائيّاً إلّا عبر Decision-Service» كان **مُعلَناً** في `shared/contracts/intelligence_governance.json` وفي تعليق خطوة CI، لكنّه مفروضٌ **جزئيّاً فقط**: ثلاث كلمات مفتاحيّة داخل `intelligence_governance_gate.py:24-32` (`actuator_service_url` · `sahool-actuator` · `mqtt.publish(`) تغطّي المسار الأصرح وحده، على ثلاث مناطق دماغ من خمس.
- **الثغرات الأربع المقيسة:** (١) نقطة نهاية HTTP للمُشغِّل جزئيّة · (٢) **موضوع أمر على وسيط غير مغطّى إطلاقاً** — `sahool.actuator.dispatch.requested` موجود حيّاً في الشجرة · (٣) استيراد عميل المُشغِّل مباشرةً · (٤) غلاف/مُرحِّل يُخفي النداء خلف وحدة أخرى. ومنطقتان كاملتان خارج النطاق: `services/mcp_servers` (أدوات مكشوفة لمزوّد LLM — أخطر شكل تجاوز) و`agents/` (وكلاء يملكون عميل NATS).
- **العلاج:** `scripts/ci/physical_effect_boundary_guard.py` + عقد `docs/architecture/physical_effect_boundary_contract.json`. قاعدتان مختلفتان عمداً: **إطلاق الأثر** مقيَّد عالميّاً بقائمة سماح مُعلَّلة سطراً سطراً، بينما **البلوغ بالاستيراد** مقيَّد داخل مناطق الدماغ وحدها (استيراد وحدات التوزيع داخل المنصّة سلوك طبيعيّ؛ فرضه عالميّاً ضجيج بلا خطر مقابل).
- **إنفاذ عكسيّ مزدوج:** إدخال سماح بلا مسار حيّ مطابق يُسقِط CI (كعقد #735)، **وإدخال سماح داخل منطقة دماغ يُسقِط CI** — فلا يُعالَج خرقٌ مستقبليّ بترخيصه.
- **الفحص على الكود المُنفَّذ وحده:** تُجرَّد docstrings والتعليقات بالـAST (نمط `decision_candidate_boundary_gate.py`) — لأنّ التوثيق يسمّي الممنوع بالنفي مشروعاً. الأثر المقيس: `core/actuator_command.py` **سقط من القائمة** لأنّ الموضوع في docstring فقط.
- **قائمة السماح بُنيت بالقياس لا بالتوقّع — إدخالان لا أربعة:** `actuator-service/actuator_runtime.py` (المُشغِّل نفسه) و`sahool-platform/api/phase_runtime_workers.py` (عامل الترحيل المعتمَد). ثلاثة مواضع بدت مرشَّحة وسقطت: باني الأمر نقيّ · `dispatch_executor` يُدرِج ولا يُطلِق · منفذ طلبات التنفيذ في `decision-service` **للقراءة فقط**.
- **مُكذَّب على الشجرة الحيّة بالمسارات الأربعة** (لا بمقتطفات صناعيّة وحدها): ملفّ HTTP في `mcp_servers` · موضوع NATS في `agents/` · استيراد عميل في `supervisor-agent` · غلاف `from api import phase_runtime_workers` في `ai_agronomist` — كلٌّ أسقط الفحص برسالة تسمّي الملفّ والمنطقة والفئة، والحذف أعاده أخضر.
- **ثغرة حقيقيّة كشفها التكذيب في الحارس نفسه:** التعبير النمطيّ الأوّل فحص ما بعد `from` وحده، فمرّر `from api import phase_runtime_workers` — الاسم المستهدَف يقع **بعد** `import`. أُصلِح جذريّاً بتحليل الاستيرادات بالـAST بدل الترقيع.
- **حدّ صدق:** الخرق الحاليّ **صفر** — الحدّ سليم اليوم بالقياس. فهذا الحارس **يُجمّد حالة صحيحة قائمة ولا يُصلِح عطلاً**؛ قيمته في الانحدار لا في الإصلاح، والتمييز مُسجَّل في `state_at_adjudication` داخل العقد.
- **مصدر حقيقة واحد:** حُذِفت القاعدة الجزئيّة من `intelligence_governance_gate.py` بعد أن غطّاها الحارس الجديد بالكامل — نسختان لقاعدة واحدة مصدرا انحراف.


## SUPERVISOR-ROOT-SKILLS-DEAD-CODE-01 — مُغلقة (2026-07-31)

- **العلّة:** `services/supervisor-agent` حمل **نسختين** من كلّ مهارة — واحدة في جذره وأخرى في `skills/`. والنسخ الجذريّة كانت **ميتة ومتباعدة معاً**، وهو أسوأ من التكرار الصرف: `advisory_skill` ١٣٧ سطراً مقابل ٢٤٨ (**١٢٣ سطراً مختلفاً** — فرق قدرة لا أسلوب) · `crop_model_skill` ١٦٠/١٦٥ (٩) · `market_skill` ١١١/٩٦ (١٧) · `remote_sensing_skill` ١٧٦/١٧٦ (٢).
- **إثبات reachability كامل قبل الحذف (لا `main.py` وحده):** صفر استيراد جذريّ (`from X`/`import X`) في الشجرة كلّها · صفر استيراد ديناميكيّ يمسّ الجذر (`router_registry.py:30` يمسح `routers/` فقط) · صفر `__main__` في الأربعة · entrypoint الحاوية `uvicorn main:app` و`main.py` يستورد `skills.*` حصراً · `test_advisor_source_tagging.py` يحمّل بـ`spec_from_file_location` لكن على `skills/` صراحةً.
- **ثلاثة مستهلكين كانوا يقرؤون الملفّ الجذريّ نصّاً — الحذف كان سيُسقِطهم بـ`FileNotFoundError`:** `scripts/ci/intelligence_governance_gate.py:11-21` (حارس CI) · `tests/test_intelligence_governance_contract.py:14-21` · `tests_v9/test_change_detection.py:98-104`. الثلاثة يفرضون العقد نفسه على النسختين (لا `compute_ndvi`، وجود `read_indicator_observation`، تسييج الجلب المباشر) — قُلِّمت قوائمهم إلى `skills/` وحدها **قبل** الحذف.
- **ورابع:** `architecture/legacy_quarantine_allowlist.json:16` كان يحجر `advisory_skill.py:mvp_in_memory` **الجذريّ** — سطر أُزيل، وهو بذاته دليل أنّ الجذر كان معروفاً كـlegacy.
- **العلاج: حذف مباشر (٥٨٤ سطراً) — بلا wrappers وبلا نقل الفروق.** الكود الميت لا يصير قدرة مطلوبة لمجرّد أنّه أطول؛ أيّ فرق ذي قيمة يحتاج إثبات مستهلك أو عقد أو اختبار مستقلّ — ولم يُقدَّم.
- **حارس منع العودة:** `tests_v9/test_supervisor_skill_canonical_location_guard.py` — أربعة تأكيدات: لا `*_skill.py` في جذر الخدمة · الأربع الحيّة سليمة في `skills/` · `main.py` يستورد `skills.*` ولا يستورد جذريّاً · صفر استيراد جذريّ عبر الشجرة.
- **مُكذَّب بثلاثة مسارات:** إعادة ملفّ إلى الجذر ⇒ فشل مُسمّى · استيراد جذريّ عارٍ ⇒ فشل يسمّي الملفّ والسطر · حذف مهارة حيّة ⇒ فشل مُسمّى. والاستعادة خضراء في الثلاثة.
- **التحقّق:** `intelligence_governance_gate` ⇒ `ok` · `tests/` **611 نجحت صفر فشل** · `pytest -m unit` **3780** · `verify_all_generated` ⇒ صفر انحراف بعد **سبع دورات توليد** (أطول سلسلة في الجلسة: الحذف حرّك الجرد والنَّسَب وعقود التشغيل والإغلاق الساكن معاً).

## PYTEST-NONASSERTING-GROWTH-01 — مُغلقة (2026-07-31)

- **ما أُغلِق بالضبط:** **النموّ** لا الدَّين. لا يمكن بعد اليوم إدخال دالّة `test_*` بلا `assert`/`raises` وتُرجِع قيمة: `scripts/ci/assertion_presence_guard.py --check` يُسقِط CI **بالاسم**، مربوطاً بـ`capability-governance.yml`. المجموعة مُجمَّدة (٢٠٧) وتتقلّص ولا تنمو — فلا يُستبدَل دَين بدَين حتى لو ثبت العدد (درس #733).
- **مُكذَّب:** إسقاط إدخال من الأساس يُسقِط الفحص مسمّياً الدالّة؛ الاستعادة تُعيده أخضر.
- **حدود القاعدة عمداً:** «بلا تأكيد ولا إرجاع» (٧٤ دالّة) لا تُرصَد — قد تكون دخاناً مشروعاً. صفر إيجابيّة كاذبة أهمّ من الشمول في بوّابة تحجب الدمج. و`pytest.raises` تأكيد صحيح.

## PYTEST-NONASSERTING-EXISTING-DEBT-01 — مفتوحة (baseline 207، 2026-07-31)

- **الدَّين القائم:** ٢٠٧ دالّة `test_*` لا يمكن أن تفشل، مُجمَّدة في `docs/architecture/assertion_presence_baseline.json`. **لم يُصلَح منها شيء.** إصلاح الدالّة = تحويل الإرجاع إلى `assert` حقيقيّ ثمّ حذف سطرها من الأساس.
- **التركّز:** أكثر من نصفها في ملفّ واحد — `tests_v9/test_roadmap_phase23.py` (١٤٢ من ١٤٣ دالّة فيه). و`test_roadmap_phase1.py` ١٧/١٧.
- **الأثر المُثبَت لا المُرجَّح:** تشغيل دوالّ `phase23` وقراءة ٦٨٣ علامة كشف إخفاقين حقيقيّين تحت خضرة تامّة — سُجِّلا فجوتين مستقلّتين أدناه (لا يُدفَنان في دليل الحارس).
- **شرط الإغلاق:** الأساس ⇐ صفر. التقلّص الجزئيّ يُحدَّث في الأساس ويُسجَّل هنا.
- **ملاحظة نطاق:** `test_roadmap_phase23.py` **مُستبعَد من `-m unit`** (`143 deselected`) — فأرقام الجلسة غير ملوّثة به؛ لكنّ الدرس عامّ: «نجح» لا يعني «أُكِّد».

## SPECTRAL-CONSUMER-PARTIAL — مقيسة (2026-08-01)

- **السؤال:** هل يُستهلَك ناتج منتِج الطيف فعلاً في مسار إنتاجيّ يُغيّر قراراً أو حالة مخزَّنة أو توصية؟ **وجود endpoint ليس دليل استهلاك** (شرط المالك).
- **السلسلة المطلوبة:** منتِج ⇒ منتَج كنسيّ مُعاد/مُخزَّن ⇒ مستهلك إنتاجيّ **مُسمّى** ⇒ أثر سلوكيّ. تُقتفى لكلّ مؤشّر على حدة لا بالتعميم.
- **النتيجة: سلسلتان لا واحدة، ونتيجتاهما متعاكستان.**
  - **(أ) حيّة ومكتملة الوصل:** `raster-service` ⇒ bundle عبر HTTP ⇒ `vegetation-analysis-service`. NDVI يُفرَّع عليه (`vegetation_runtime.py:777` ⇒ 424؛ `:472-481` تصنيف). NDMI+MSI يدخلان `_derive_water_stress_from_observed` (`:459-468`) وحدهما، ثمّ `:497` يُغيّر **توصية**. والأصالة تُفرَّع عليها بإخفاق مُغلَق (`indicator_registry.py:37-39,54` ⇒ `:834`) و`VEGETATION_REAL_ONLY=1` مضبوط في compose الإنتاج.
  - **(ب) مظلمة:** `imagery_automation` ⇒ أعمدة `last_ndmi_mean/last_msi_mean` ⇒ `canonical_water_stress` ⇒ تصعيد يُحوّل `execution_mode` إلى `human_review`. **لا تعمل** — سببان مستقلّان أدناه.
- **حدّ صدق:** الحكم **ليس إغلاقاً**. الاستهلاك الحقيقيّ يُنتِج **توصية** (`advisory_role: hypothesis`) لا صفّاً مخزَّناً؛ والمسار الوحيد الذي يمسّ صفّاً مخزَّناً هو (ب) وهو معطَّل.

## SPECTRAL-COLLECTOR-ASYNC-RACE-01 — مُصلَحة في الكود (2026-08-01)

- **الإصلاح:** انتظار حالة نهائيّة للدفعة **قبل** قراءة نتائج مهامّها الفرعيّة — `imagery_automation._await_batch_terminal`، يُستدعى مرّةً واحدة في `_trigger_indicators` (لا مرّةً لكلّ مؤشّر). و`raster_service_client.get_job_status` جديد لأنّ `/v1/jobs/{id}/result` **لا يصلح** للانتظار: يردّ 409 حتّى الاكتمال فلا يميّز «لم تنتهِ» من «انتهت فارغة»، بينما `/v1/jobs/{id}` يردّ الحالة الجارية.
- **ثلاث نهايات مفصولة لأنّها ثلاثة أعطال مختلفة العلاج** — وخلطها كان سيُخفي أحدها خلف تفسير الآخر:
  - **نهائيّة** ⇒ تُقرأ النتائج. حتّى `failed` تُقرأ: قد ينجح مؤشّر ويفشل آخر.
  - **نفاد الميزانيّة** ⇒ لا قراءة، `warning`، وعدّاد `timed_out`. القيمة تبقى `NULL` ولا تُختلَق، والدورة التالية تُعيد المحاولة.
  - **مهمّة مجهولة (404)** ⇒ توقّف **فوريّ** بلا استهلاك ميزانيّة، وعدّاد `unknown` مستقلّ. الانتظار عبث هنا: الحالة بالذاكرة قد تكون على نسخة أخرى من raster-service، والزمن لا يُصلح عطل نشر.
- **`processed_unpublished` حالة نهائيّة** (`raster_persistence_policy.terminal_status`): إغفالها كان سيُنتِج مهلةً في **كلّ** دورة تعمل بوضع الإدامة «أفضل-جهد» — أي إصلاحاً يفشل حيث يعمل النظام فعليّاً.
- **عيب ثانٍ في المسار نفسه، ظهر أثناء التنفيذ:** `_fetch_index_mean` كان يترك 409 ينتشر، و`_collect_spectral_values` يقرأ NDMI ثمّ MSI **بالتتابع** — فمؤشّر واحد فاشل كان يُسقِط الناجح بعده. صار 409 ⇒ `None` (غياب قيمة، لا عطل قراءة).
- **قابليّة القراءة شرط في الإصلاح لا زينة:** العدّادات الثلاثة منشورة في `ImageryAutomation.status()` ⇒ `routers/automation.py:152`. بدونها يعود «لم تُكتَب القيم» غير مرئيّ من الخارج تماماً كما كان.
- **بوّابة تراجع:** `IMAGERY_BATCH_WAIT_BUDGET_S=0` تُعطّل الانتظار وتُعيد السلوك السابق حرفيّاً — وهي أيضاً ما يجعل التكذيب ممكناً في اختبار.
- **التكذيب (لا ادّعاء):** حذف نداء الانتظار من `_trigger_indicators` ⇒ **٨ من ٩** تسقط، والوحيدة الناجية هي اختبار ميزانيّة الصفر الذي يصف العطل نفسه. وتعطيل فرع 409 ⇒ يسقط اختبار «مؤشّر فاشل لا يُضيع الناجح بعده» وحده.
- **المصدر:** `tests_v9/test_imagery_batch_wait_before_read.py` (٩ اختبارات) · `services/sahool-platform/api/imagery_automation.py` · `services/sahool-platform/api/raster_service_client.py`.
- **حدّ الصدق — ما لم يُثبَت:** هذا إصلاح مُثبَت بالاختبار على مستوى الوحدة، **لا** برهان تشغيليّ حيّ بأنّ الأعمدة الثلاثة صارت تُكتَب في بيئة حقيقيّة. التحقّق الحيّ يبقى مطلوباً، ولذلك تُسجَّل «مُصلَحة في الكود» لا «مؤكَّدة».

## SPECTRAL-COLLECTOR-ASYNC-RACE-01 — مفتوحة (عالية، 2026-08-01)

- **العطل:** `POST /v1/process/batch` **غير متزامن** — `routers/processing.py:154` يضيف `background_tasks.add_task(...)` ثمّ يُرجِع `status: pending` فوراً، والمهامّ الفرعيّة تُنشَأ **داخل** المهمّة الخلفيّة (`raster_job_orchestration.py:442-451`).
- **بينما** `imagery_automation.py:618-620` يقرأ النتيجة **فور عودة الطلب، بلا استطلاع ولا إعادة** (`_fetch_index_mean` نداء واحد). فالقراءة تصطدم بـ404 (`routers/jobs.py:41-44`) ⇒ `get_job_result` يُرجِع `None` ⇒ `_persist_spectral` **لا يُستدعى**؛ أو 409 يبتلعه `except Exception` عريض في `:689-690`.
- **الأثر:** `last_ndvi_mean` · `last_ndmi_mean` · `last_msi_mean` **لا تُكتَب أبداً**. وهذان الأخيران لا كاتب إنتاجيّ آخر لهما — لا مسح تسوية ولا مسار بديل.
- **تحقّقتُ منه بنفسي** لا بنقل: قرأتُ `processing.py:154-162` و`imagery_automation.py:610-625`.
- **يمسّ صحّة المنتج اليوم** — ولذلك سُجِّل مستقلّاً عن حكم `SPECTRAL-CONSUMER-PARTIAL`.
- **شرط الإغلاق:** استطلاع/إعادة حتّى اكتمال المهمّة قبل القراءة، أو مسح تسوية لاحق. **تغيير سلوكيّ يمسّ توقيت كتابة صفوف ⇒ شريحة مستقلّة بقرار المالك، لا تُدسّ في تنظيف.**

## SPECTRAL-ESCALATION-FLAG-DARK-01 — مفتوحة (قرار تفعيل، 2026-08-01)

- **العلّة:** `field_state_projection.py:754-756` يسوّر التصعيد بـ`FEATURE_WATER_STRESS_ESCALATION`، والافتراض **مُطفأ** (`feature_registry.py:47`).
- **بالقياس:** العلم **لا يظهر في أيّ ملفّ نشر** — لا `docker-compose*.yml` ولا `helm/` ولا `k8s/`. مواضعه: كودان، ثلاث وثائق، واختبار واحد.
- **الأثر:** حتّى لو أُصلِح السباق أعلاه، `escalation_triggered` يبقى `False` دائماً.
- **ليس عطلاً بل قرار غير مُتَّخذ** — ولذلك فُصِل عن الفجوة السابقة: إصلاح أحدهما لا يُغني عن الآخر.

## SPECTRAL-MSI-ABSENT-FROM-DEFAULT-PRODUCTS-01 — مفتوحة (2026-08-01)

- **العلّة:** MSI مُنفَّذ صحيحاً (`band_math.py:80-87`) ويُفرَّع عليه في السلسلة الحيّة، لكنّه **غائب عن كلّ قوائم الإنتاج الافتراضيّة**: `scene_policy.py:50` (`CORE_TIMELINE_INDICES`) و`raster_api_models.py:225` (`default_indices`).
- **الأثر:** يُحَلّ عادةً إلى `product_unavailable`، فيتدهور `water_stress` إلى فرع NDMI وحده — **بلا تحذير**: `vegetation_runtime.py:650-655` يُخفِق مُغلَقاً على `mixed_scene`/`bundle_consistency` لا على النقص.
- **شرط الإغلاق:** إضافة MSI للقوائم، أو تحذير صريح عند غيابه بدل التدهور الصامت.

## SPECTRAL-STALE-DECISION-LINKED-CLAIMS-01 — أُعيد القياس: الادّعاء لم يعد **كاذباً** بل **غير مُبرهَن حيّاً** (2026-08-01)

- **لماذا أُعيد القياس:** الحكم الأصليّ («صحيح بنيويّاً كاذب تشغيليّاً») كان مبنيّاً على أنّ **الكاتب لا يعمل**: `imagery_automation` يقرأ نتيجة الدفعة قبل اكتمالها فلا يُكتَب `last_ndmi_mean`/`last_msi_mean` أبداً. **وقد أُصلِح ذلك في #749.** إبقاء الوصف كما هو كان سيُنتج انحرافاً معاكساً: سجلّ يقول «كاذب» عن ادّعاء لم يعد كذلك.
- **السلسلة كما قِستُها على `e73944e7`:** `imagery_automation._trigger_indicators` (ينتظر حالةً نهائيّة ثمّ يكتب) ⇒ `field_state_projection.py:145` يختار العمودين وتاريخيهما ⇒ `canonical_water_stress.py:142` يدمجهما بـ`fuse_water_stress` ⇒ `spectral_confirmation_available`/`spectral_stress_detected` في الحالة القانونيّة.
- **والاستهلاك لا يتوقّف على علم التصعيد:** `FEATURE_WATER_STRESS_ESCALATION` يحكم **التصعيد** لا **التأكيد**. فالمؤشّران يُغيّران مخرَج `canonical_water_stress` حتّى والعلم مُطفَأ — أي أنّ `decision_linked` صادق بمعناه الأضيق، و`SPECTRAL-ESCALATION-FLAG-DARK-01` تبقى مستقلّة.
- **الحالة الدقيقة:** لا «كاذب» ولا «مُغلَق». **الوصل قائم ومشروط ومحروس؛ والملء الحيّ غير مُبرهَن.** لم يُرفَع `runtime_verified`.
- **الحارس الجديد:** `tests_v9/test_spectral_decision_link_is_bound_to_the_chain.py` (١١ اختباراً) يربط الوسم بالمسار بدل أن يفحص إعلاناً بإعلانه.
- **العيب في الحارس القائم:** `tests/test_spectral_stress_bridge.py:84-85` يؤكّد أنّ `ndmi`/`msi` **موجودان في القاموس الذي تكتبه الوحدة نفسها** — حلقة مغلقة تبقى خضراء لو انقطعت السلسلة كلّها. لم يُحذَف (يحرس شكل التقرير) لكنّه لم يعد وحده.
- **وخطأ وقعتُ فيه ثمّ كشفه التكذيب:** أوّل صيغة للحارس كانت **نصّيّة** (`"last_ndmi_mean" in source`)، فمرّت خضراء رغم كسري لجملة `SELECT` — لأنّ الاسم يظهر في مكان آخر من الملفّ. استُبدِلت بفحص **سلوكيّ**: conn وهميّ يُجيب ذلك الاستعلام وحده، فانقطاع الاختيار يُسقِط التأكيد. **الحارس النصّيّ يقيّد الإملاء لا العقد** — الدرس نفسه، ولم يظهر إلّا بالتكذيب.
- **التكذيب — أربعة أقفال، كلٌّ على حدة:** إيقاف اختيار العمودين ⇒ يسقط اختبار السلسلة · جعل مؤشّر واحد كافياً ⇒ يسقط اثنان · تجاوز الجسر بقيمة محليّة ⇒ يسقط اختبار الجسر · حذف انتظار الدفعة من `_trigger_indicators` ⇒ يسقط اختبار الكاتب. استُعيد الأصل ⇒ **١١ نجحت**.

## SPECTRAL-STALE-DECISION-LINKED-CLAIMS-01 — الحكم الأصليّ (2026-08-01، أُبقي للمصدر)

- **ثلاثة ادّعاءات في الشجرة تناقض القياس:** `band_math.py:83` يقول إنّ MSI «يُستهلَك في تأكيد الإجهاد الطيفيّ (canonical_water_stress عبر spectral_stress_bridge)» · `spectral_stress_bridge.py:175-176` يَسِم NDMI/MSI بـ`decision_linked ✓` · و`sahool-brain/log.md:2598` يسجّل أنّ فحصاً سابقاً خلص إلى أنّ السلسلة **ليست مكسورة**.
- **كلّها صحيحة بنيويّاً وكاذبة تشغيليّاً**: المسار موجود ولا يعمل.
- **لماذا أخطأ الفحص السابق:** قاس «هل يُحسَب MSI؟» لا «هل نتيجة المهمّة قابلة للقراءة **لحظةَ تُقرأ**؟» — وهو الفرق نفسه بين وجود endpoint وإثبات استهلاك.
- **الصنف نفسه** الذي عالجه `WEATHER-SERVICE-STUB-DOCSTRING-DRIFT`: ادّعاء صحّ يوماً ثمّ بطل وبقي مكتوباً.

## ACTIONS-NODE20-DEPRECATION-01 — نُفِّذت بإعادة فتحٍ من المالك (2026-08-11)

- **العلّة:** `actions/upload-artifact` مثبَّت بـSHA على v4 الذي يُعلن Node 20؛ وGitHub أهملت Node 20 فيُجبِر المُشغِّل Node 24 ويُصدِر تحذيراً.
- **المدى المقيس (تصحيح):** **٢٣ موضعاً في ١٣ ملفّ workflow** ببصمةٍ واحدة متمايزة. والعدّان السابقان كلاهما خطأ: «٢٠+ عبر ١٥» (2026-08-01) و«٢٣ في ١٦» الذي كتبتُه في أوّل صياغة لهذا البند — والثاني خطئي أنا، صحّحه العدّ الآليّ (`grep -rln` ⇒ 13). **ولا مرساة خارج `.github/workflows/`**: لا حارس ولا اختبار ولا allowlist يحمل البصمة — بخلاف ترقية `actions/attest` في #823 التي حملت **سبع مراسٍ** منها حارسٌ واختبار، فأخضرّت البوّابات على نصف ترقية.
- **قرار المالك الأوّل (2026-08-01):** مؤجَّلة — «دين بنية CI مهمّ لكنّه لا يغيّر صحّة المنتج اليوم».
- **وإعادة الفتح (2026-08-11):** بأمرٍ صريح من المالك («قوم بتنفيذ») **قبل** وقوع مُحفِّز إعادة الفتح المكتوب (فشلٌ حقيقيّ بدل تحذير). أي أنّ التنفيذ **قرارُ مالكٍ ينسخ قرارَ مالك**، لا مبادرةَ وكيل — وهذا هو سببُه المُسجَّل.
- **ما نُفِّذ:** ٢٣/٢٣ موضعاً ⇒ `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1`، **مع تعليق الوسم** لا البصمة وحدها (تركُ `# v4` بجانب بصمة v7 يجعل التعليق يكذب على قارئه، وهو أسوأ من غيابه).
- **حدُّ صدقٍ باقٍ بعد التنفيذ:** ربطُ البصمة بالوسم **لم يُتحقَّق منه داخل هذه الشجرة**. مصدرُه حزمةُ المالك، ونطاق GitHub في جلسة الوكيل محصورٌ بهذا المستودع فلا يُقرأ `actions/upload-artifact`. فما هو مُثبَتٌ هنا **اتّساقُ** التثبيت لا **صحّتُه**، ولا يدّعي أيّ حارس غير ذلك.
- **وما وُلِد من الشريحة:** [`ACTION-PIN-HALF-UPGRADED-01`](#) — الحزمة المقترَحة كانت تُبدّل `ci.yml` وحده (**٣ من ٢٣**)، فتترك عشرين موضعاً على البصمة القديمة وكلُّ البوّابات خضراء، لأنّ `github_actions_policy_guard` يسأل «أمثبَّتٌ ببصمة؟» لا «أبصمةٌ واحدة؟». وصار الصنف محروساً.


## LOCAL-RASTER-UNKNOWN-WORKTREE — محجورة بقرار المالك (2026-08-01)

- **ما هي:** أربعة عشر ملفّاً مُعدَّلاً وُجِدت في شجرة عمل الحاوية **عند بدء الجلسة**، غير مُودَعة، من نقطة **سابقة لـ#724**. ليست من إنتاج هذه الجلسة، وكاتبها ونيّتها **مجهولان لي**.
- **الموضع الدائم:** فرع `wip/raster-quarantine-20260801` عند `bba6081a` — أساسه `b3af02a7` (دمج #724) وهو الالتزام الذي كُتِبت عليه فعلاً، **لا `main` الحاليّ**. عليه تُطبَّق نظيفةً؛ على `main` تتعارض في أربعة ملفّات. حلّ ذلك التعارض كان سيعني **اختراع محتوى داخل عمل غير مراجَع مجهول المؤلّف** — نقيض حفظه. فاختير الأساس ليبقى الفرق أميناً لا حديثاً.
- **لماذا فرع بعيد أصلاً:** كانت محفوظة في `git stash` وملفّات patch تحت `/tmp` — كلاهما يعيش داخل حاوية زائلة ويزول معها.
- **ما لم يُفعَل عمداً:** لم تُدمَج ولا أُعيد أساسها · **لم تُخلَط بأيّ شريحة** (#742 · #743 · #744 · #745 تستثنيها كلّها) · لم تُراجَع ولا تُختبَر ولا أُعيد توليد مصنوعاتها · **ولم يُقرَأ محتواها أو يُفسَّر**.
- **قرار المالك — الاحمرار جزء من الوصف:** «اتركه أحمر كما هو. لا تُصلح الجرد أو التنسيق داخله؛ الاحمرار جزء من وصفه الصادق كعمل غير مراجَع.» **ورفض استثناء `wip/**` من CI** صراحةً: «قد يحوّل فروعاً مستقبليّة غير جاهزة إلى مناطق بلا مراقبة.»
- **النطاق:** `docs/openapi/API_MAP.md` · ستّ وحدات في `raster-service` واختباران لها · `raster_service_client.py` في المنصّة واختبار واحد · وثلاثة اختبارات تحت `tests/architecture` و`tests_v9`.
- **شرط الإغلاق (قرار مالك، ليس عملاً هندسيّاً):** إمّا **مطلوبة** ⇒ مراجعة + إعادة أساس على `main` الحاليّ، أو **غير مطلوبة** ⇒ حذف الفرع. **حذف الفرع قبل البتّ = فقدان لا إغلاق.**
- **لماذا سُجِّلت الآن:** الفرع كان موجوداً ومدفوعاً بلا أيّ إشارة إليه في السجلّ — فمن يفتح الشجرة لاحقاً يرى فرعاً أحمر بلا تفسير، ولا يعرف أنّ احمراره **مقصود**. وهذا بالضبط صنف العطل الذي أغلقته #747 (قياس يعيش في محادثة وحدها).

## CANONICAL-SNAPSHOT-ELIGIBILITY-POLICY-01 — مفتوحة (P1 معماريّة/سياسة، 2026-08-01)

- **الوضع القائم:** `decision_eligible` **قيمة منطقيّة مشتقّة** لا مُدخَلة — `scripts/ci/generate_indicator_artifacts.py:58-59`: `source == "real" and status == "implemented"`. تُقرأ في `services/vegetation-analysis-service/indicator_registry.py:69,77` وتُحمَل داخل `feature_manifest` (`indicator_registry.py:61` · `vegetation_contracts.py:79`).
- **العلّة:** قيمة منطقيّة واحدة تحمل سؤالين مختلفين — «هل المؤشّر مُنفَّذ وحقيقيّ المصدر؟» و«هل يجوز أن يقود قراراً في هذا السياق؟». الأوّل حقيقة عن المؤشّر، والثاني **سياسة** تتغيّر بتغيّر المحصول والمرحلة وجودة المشهد والمعايرة المحلّيّة.
- **القيد الذي يجعلها قراراً لا تنفيذاً:** اللقطة **معنونة بمحتواها** — `services/decision-service/main.py:332`: «content-addressed by snapshot_hash (the hash IS the …)»، و`persistence.py:4473` يُلغي التكرار على `(tenant_id, snapshot_hash)`. فإضافة حقل أهليّة متعدّد المستويات **داخل جسم اللقطة** تُغيّر كلّ `snapshot_hash` قائم، وتكسر إعادة التشغيل ونَسَب الأدلّة.
- **التصميم المُقَرّ (قرار المالك):** تبقى اللقطة **حقائق مرصودة ثابتة**، وتصير الأهليّة **مصنوعاً مشتقّاً** مفتاحه `snapshot_digest` + `policy_version`، **خارج الهاش**. هذا يحفظ إعادة التشغيل ويسمح بإعادة تقييم لقطة قديمة تحت سياسة جديدة. ويبقى `decision_eligible` الحاليّ نقطة توافق للخلف، **بلا** توسيعه مباشرةً إلى حقل متعدّد المعاني داخل اللقطة.
- **لماذا P1 لا P0** (تصنيف المالك): لا يوجد **مستهلك تنفيذيّ** يعتمد القيمة المنطقيّة الحاليّة اعتماداً خطراً — البيان يسافر إلى `decision-service` كـ`feature_manifest_id`/`feature_manifest_hash` فقط، وإلى `agriai-engine` الذي يفحص حضور `manifest_id`/`version` لا الأهليّة. **تُرفَّع إلى P0 فور إثبات أنّ `decision_eligible` يسمح اليوم بتنفيذ غير آمن** — وهذا هو مُحفِّز إعادة التقييم المكتوب.

### مُنفَّذ (2026-08-07): الأهليّة صارت كياناً مشتقّاً — واللقطة لم تُمَسّ

- **بنطاقٍ مُلزَم من المالك، وسبعة بنوده مُنفَّذة:** اللقطة تبقى ثابتة · لا `policy_version`
  ولا `eligibility_assessment_id` في `snapshot_digest` · كيان `EligibilityAssessment` مشتقّ ·
  تقييم حتميّ · الحالات السبع مُختبَرة · لا endpoint ولا خدمة جديدة · وحارسٌ مُثبَتٌ بالتكذيب.
- **الكيان:** `decision_eligibility_assessments` (هجرة `031`) مفتاحه
  `(tenant_id, snapshot_hash, policy_version, as_of)` — **خارج الهاش تماماً**. مرجعٌ مُركَّب
  بالمستأجِر إلى اللقطة، مُشغِّل إلحاق-فقط، RLS بـ`FORCE`، وقيد `CHECK` يرفض تقييماً
  **يطوي المراحل الأربع** في «صالحة/غير صالحة» — وهو الخلط الذي أوجب الفجوة، فتمنعه
  القاعدة لا التطبيق وحده.
- **الحتميّة خاصّيّة لا ادّعاء:** `assessed_at` (ساعة الحائط) **مُستبعَدة من البصمة ومن
  المساواة**، و`as_of` (اللحظة المنطقيّة) داخلهما. مُقاس باختبارين متقابلين.
- **المراحل أربع لا واحدة** (`discover`/`diagnose`/`propose`/`execute`): لقطةٌ تكفي
  للاستكشاف قد لا تكفي للتنفيذ. والأسباب **قابلة للآلة**: رمز + موضوع + المقيس + الحدّ.
- **الدليل الحيّ (٨ اختبارات على PG16):** عزل RLS بدورٍ `sahool_app` مُثبَتٍ أنّه
  `rolsuper=false` و`rolbypassrls=false` · الكتابة باسم مستأجِر آخر يرفضها `WITH CHECK` ·
  الإلحاق فقط · التفرّد عند إعادة التشغيل · رفض طيّ المراحل · ذرّيّة المعاملة · وأنّ جدول
  اللقطات **لم يكتسب عمود أهليّة** — مقيساً على القاعدة لا على النصّ.
- **اكتشافٌ أثناء التنفيذ يستحقّ التسجيل:** تتالي المراحل (`UPSTREAM_STAGE_DENIED`)
  **لا يُطلِق أبداً** بالسياستين المشحونتين، لأنّ عتباتهما **مُطّردة** — فكلّ ما يُسقِط
  `diagnose` يُسقِط `propose` بحدّه هو. كشفَه اختبارٌ سقط، لا قراءتي. أُبقي الثابت لأنّه
  يحرس **سياسةً مستقبليّة غير مُطّردة** (تُرخي مرحلةً متأخّرة فتُقترَح خطّة على لقطةٍ لم
  تُشخَّص)، وأُضيف اختبار يُثبِّت الاطّراد فيسقط يوم يبطل.
- **وخطأٌ ثانٍ كان القيدَ يعمل:** أوّل تجهيزة حيّة أدخلت التقييم بلا اللقطة، فسقطت بـ
  `violates foreign key constraint` — المرجع المُركَّب يفعل ما وُضِع له.
- **حدّ صدق صريح:** المُقيِّم **غير موصول بأيّ مسار طلب** (بنصّ النطاق: لا endpoint جديدة).
  فهو اليوم عقدٌ وكيانٌ ومحروسان، **ولا مستهلِك له** — والوصل قرار منتَج لاحق.
- **و`decision_eligible` لم يُمَسّ:** يبقى حقيقةً عن المؤشّر في سجلّ المؤشّرات، نقطةَ توافق
  للخلف كما نصّ التصميم المُقَرّ.
- **مراجعة المالك على #810 (بعد الدمج) أسقطت أربع فجوات حاجبة — كلّها صحيحة، وكلّها كانت تمرّ:**
  ① `data_available_at` **يدخل البصمة ولا يُفحَص**، فتقييمٌ عند لحظةٍ سابقة لإتاحة البيانات
  يبني قراراً على معلومةٍ لم تكن متاحة — تسريبٌ من المستقبل لا يظهر في أيّ اختبار حتميّة ·
  ② ورصدٌ مستقبليّ يُنتِج **عمراً سالباً** فيُقرأ «طازجاً جدّاً» ويمرّ إلى `execute` — أخطر من
  البائد لأنّ البائد يُرفَض والمستقبليّ يُكافَأ · ③ وفحص المستأجِر كان **بعد** قراءة الجسد
  وبصمِه، فكان `assessment_digest` يتغيّر بتغيّر جسد لقطةِ مستأجِرٍ آخر رغم ثبات سبب الرفض
  — **هاش أوراكل**، ووصفي كان يقول «لا يُقرأ الجسد أصلاً» بينما الكود يقرؤه · ④ و`snapshot_hash`
  مفقود يصير `""` فتُمنَح المراحل الأربع ثمّ ترفضه القاعدة لاحقاً.
- **وخامسة على السياسة:** عتباتي قُدِّمت سياسةً فعليّة بلا تحكيم. الآن كلّ سياسة تحمل
  `provenance` يُسمّي **المُحكَّم** (`source == real` · `status == implemented` ·
  `min_valid_pixel_pct = 60` من `generate_indicator_artifacts.py`) و**غير المُحكَّم** (أعمار
  الطقس والتربة وعتبتا ٣٠/٨٠ — من وضعي)، و`adjudicated=False` مفروضٌ باختبار. **والعقد
  القانونيّ صار مُنفَّذاً لا موازىً:** مؤشّرٌ اصطناعيّ أو غير مُنفَّذ لا يقود مرحلةً مهما
  كانت أعماره سليمة.
- **وثقبٌ في الحارس أمسكه المراجع الآليّ:** `ADD COLUMN IF NOT EXISTS` كان **يفلت** —
  يُلتقَط `IF` بوصفه اسم العمود. والنمط يظهر **٢١ مرّة** في هجرات هذه الخدمة نفسها، فأرجح
  طريقٍ إلى العطل كانت الوحيدة التي لا يراها. وأُضيفت `ONLY` والأسماء المؤهَّلة بالمخطَّط.
- **واختبار PostgreSQL كان ينهار عند الجمع** في بيئة بلا `psql` (‏`FileNotFoundError` قبل أن
  يعمل `skipif`) — انهيارُ جمعٍ يُقرأ عطلاً ويُخفي بقيّة الملفّ. الآن `shutil.which` أوّلاً،
  ومُقاس بـ`PATH` فارغ: **٩ متخطّاة، خروج ٠**.
- **وادّعاءٌ خاطئ في متن #810 صحّحه المراجع:** قلتُ «ثلاث طفرات» والسجلّ يحمل اثنتين. الآن
  **أربع** مُسجَّلة ومُشغَّلة بـ`--run`.
- **المصدر:** `services/decision-service/eligibility_policy.py` · `migrations/031_eligibility_assessment.sql`
  · `tests/test_eligibility_assessment_policy.py` (١٩) · `tests/test_eligibility_assessment_live_pg.py` (٨ حيّة)
  · `scripts/ci/snapshot_eligibility_separation_guard.py` (مُثبَت بثلاث طفرات).


## SILENT-EXCEPTION-HANDLERS-11-01 — مُغلَقة بالقياس (11 ⇒ **0**، 2026-08-01)

- **العدد النهائيّ مقيس على `main` بعد الدمج لا مجموعاً حسابيّاً** (بتوجيه المالك): أُعيد تشغيل **قاعدة الكاشف نفسها** (`tests_v9/test_roadmap_phase23.py:4707` — `except …:` يليه `pass` صرف، خارج الاختبارات) على الشجرة عند `a545d6e3` ⇒ **صفر**. الجمع الحسابيّ كان سيُخفي أيّ موضع جديد دخل الشجرة أثناء الشرائح الأربع.
- **المسار:** ١١ ⇒ ٥ (#742، رؤية فقط) ⇒ ٣ (#743، سلوكيّة: `terrain_analysis` + `production_qdrant`) ⇒ ١ (#744، تصنيف موضعَين بوصفهما `EXPECTED-CONTROL-FLOW-EXCEPTION` مع حارس يفرض ستّة شروط لكلّ موضع) ⇒ **٠** (#746، `cdse_client` — الموضع الوحيد الذي كان يقرّر **هل تُوثَق البيانات**).
- **الانقسام باتّجاه الفشل لا بالعدد** (بتوجيه المالك): الرؤية المحضة والتصحيح السلوكيّ في شرائح منفصلة، فكلّ منهما قابل للتراجع وحده.
- **موضعان لم يُعالَجا كدَين بل صُنِّفا:** `api/main.py:583` و`projection_jobs.py:94` — الاستثناء فيهما **هو** إشارة النجاح. والتصنيف نفسه محروس: `scripts/ci/expected_control_flow_guard.py` يشترط لكلّ إدخال **وجود اختبار شاهد**، لأنّ اختباراً لا يستطيع كشف حذف نفسه.
- **ما تبقّى مفتوحاً وليس جزءاً من هذه الفجوة:** سياسة `missing` في CDSE («اقبل الآن، قِس، ثمّ شدّد») حيّة بثلاثة عدّادات مُعلَنة على `/metrics` — التشديد يحتاج قياساً حيّاً لا تخميناً.

## SILENT-EXCEPTION-HANDLERS-11-01 — النصف الحافظ للعقد مُغلَق (11 ⇒ 5، 2026-08-01)

- **الانقسام باتّجاه الفشل لا بالعدد** (بتوجيه المالك): PR-A تشمل ما **لا يغيّر قراراً ولا أثراً جانبيّاً** — رؤية فقط؛ وPR-B تشمل التصحيحات السلوكيّة الثلاث في مراجعة مستقلّة قابلة للتراجع.
- **المقياس بقاعدة الكاشف نفسها لا بالادّعاء:** ١١ ⇒ **٥**. الباقي بالضبط: `main.py:583` و`projection_jobs.py:94` (`EXPECTED-CONTROL-FLOW-EXCEPTION` — الاستثناء **هو** إشارة النجاح، لا يُعالَجان كدَين)، و`cdse_client.py:642` · `terrain_analysis.py:163` · `production_qdrant.py:240` (سلوكيّة ⇒ PR-B).
- **الستّة المُعالَجة:** ثلاثة `os.unlink` أفضل-جهد في `raster_cdse_tile_runtime` · `aquacrop_adapter:108` · `offline_pending_db:45` · `observability:203`.
- **اكتشافان أثناء التنفيذ لم يظهرا في الاستقصاء:** (١) `offline_pending_db` له **مساران للرفض** لا واحد — `parsed <= 0` يرتدّ للافتراض **بلا المرور بالمعالِج**، فسطر تسجيل داخل `except` وحده كان سيُبقي نصف الصمت قائماً. (٢) `observability` كان يزيد `count` ولا يزيد `size`، فيُبلَّغ عدد بلاطات بحجم ناقص بلا إشارة — وفي نقطة *مراقبة* الرقمُ الخاطئ الصامت أسوأ عطل ممكن؛ فنُشِر عدّاد `skipped` بلا مسّ القرار.
- **درس حارس مصدريّ — رفضتُ تليين حارس أمنيّ:** إعادة صياغة موضع القناع إلى مساعِد أسقطت `tests_v9/test_tile_mask_fail_closed_v29_8.py:49`، وهو حارس **نصّيّ** يفتّش عن `os.unlink(cog_path)` حرفيّاً ليمنع تسريب قرص على مسار fail-closed. توسيعه ليقبل المساعِد كان **إضعاف حارس أمنيّ من أجل إعادة صياغة تجميليّة**؛ فبقيت الصيغة الحرفيّة في ذلك الموضع وحده مع تعليق يشرح اللاتماثل. (هشاشة الحارس النصّيّ أمام إعادة الصياغة ملاحظة مستقلّة، لا تُهرَّب في هذه الشريحة.)
- **`debug` لا `warning` للثلاثة:** التعذّر سباق متوقَّع، ورفع المستوى يُصدِر ضجيجاً يتناسب مع زمن التشغيل — العيب نفسه في الاتّجاه المعاكس.
- **التحقّق:** `pytest -m unit` **3799 نجحت / صفر فشل**. والفشل الوحيد قبلها كان من صنعي، كشفه التشغيل **المتتابع** بعد أن أعطى تشغيلان متزامنان `exit 0` بسجلَّين فارغين لا يصلحان دليلاً — الخطأ التشغيليّ نفسه للمرّة الخامسة.


## SILENT-EXCEPTION-HANDLERS-11-01 — مفتوحة (2026-07-31)

- **المصدر:** كشفها `test_exception_hygiene` داخل `test_roadmap_phase23.py`، وكانت مخفيّة لأنّ الدالّة تُرجِع علاماتها بدل أن تؤكّد (انظر الفجوة أعلاه). رسالة الاختبار نفسها تسمّي **٣ من ١١** فقط (`prod_silent[:3]`) — فاستُخرِجت الأحد عشر بمساراتها الكاملة بإعادة تشغيل منطق الكشف.
- **النمط:** `except …:` يليه `pass` صرف بلا تسجيل ولا تعليق، في كود إنتاجيّ (الاختبارات مستثناة).
- **المواضع الأحد عشر:**
  - `services/agriai-engine/aquacrop_adapter.py:108`
  - `services/raster-service/cdse_client.py:642`
  - `services/raster-service/raster_cdse_tile_runtime.py:151` · `:197` · `:226`
  - `services/raster-service/routers/observability.py:203`
  - `services/raster-service/terrain_analysis.py:163`
  - `services/sahool-platform/api/main.py:583`
  - `services/sahool-platform/api/offline_pending_db.py:45`
  - `services/sahool-platform/core/rag/production_qdrant.py:240`
  - `services/soil-service/projection_jobs.py:94`
- **لماذا تُهمّ:** ابتلاع صامت في مسارات صور/تضاريس/تخزين/RAG — الفشل يختفي بلا أثر، وهو نقيض مبدأ «لا نجاح زائف» المُعلَن في `workflow_engine` وغيره.
- **شرط الإغلاق:** كلّ موضع إمّا يُسجّل (`logger.debug/warning` بسبب) أو يُعلن الفشل، ثمّ يُحوَّل الكشف من علامة نصّيّة إلى حارس CI حقيقيّ.

## DECISION-SERVICE-REDIS-DEPENDENCY-GAP-01 — مفتوحة (2026-07-31)

- **المصدر:** `test_dependency_consistency` داخل `test_roadmap_phase23.py` ⇒ `فجوات تبعيّات: ['decision-service:redis']` — مخفيّة تحت خضرة تامّة للسبب نفسه (دالّة تُرجِع ولا تؤكّد).
- **المضمون:** `decision-service` يستعمل redis دون إعلانه في تبعيّاته المُصرَّحة (أو العكس) — عدم اتّساق بين ما تستهلكه الخدمة وما يُعلنه عقدها.
- **لماذا تُهمّ:** تبعيّة غير مُعلَنة تعني إقلاعاً قد يفشل في بيئة لا تُوفّرها، وتغيب عن حسابات النشر/الجاهزيّة.
- **شرط الإغلاق:** التحقّق من الاستهلاك الفعليّ، ثمّ إمّا إعلان التبعيّة في مصدرها القانونيّ أو إزالتها من الكود إن كانت ميّتة — مع تحويل الفحص إلى تأكيد حقيقيّ.

<!-- القسم التالي هو التفصيل الأصليّ، أُبقي للمصادر -->

## TESTS-PASS-WITHOUT-ASSERTING-01 — تفصيل القياس (2026-07-31)

- **العلّة (مقيسة لا مُرجَّحة):** دوالّ `test_*` تُرجِع `[("✓"|"✗", msg), …]` بدل أن تؤكّد. pytest **يُهمِل القيمة الراجعة** ويكتفي بتحذير `PytestReturnNotNoneWarning` — فالدالّة «ناجحة» مهما كان ما أعادته، بما فيه `✗` صريحة.
- **الدليل المباشر:** `tests_v9/test_roadmap_phase23.py` — pytest يجمع **١٤٣** اختباراً، **واحد** فقط يحوي `assert` (١٤٢ بلا أيّ تأكيد). تشغيل الدوالّ وقراءة حمولاتها (٦٨٣ علامة) كشف **علامتَي ✗ حقيقيّتين** تحت خضرة تامّة: `test_dependency_consistency` ⇒ `فجوات تبعيّات: ['decision-service:redis']`، و`test_exception_hygiene` ⇒ `11 silent متبقٍّ` بمصادر `path:line`. هاتان نتيجتان حقيقيّتان كانتا مخفيّتين خلف «نجاح».
- **النطاق المقيس:** **٢٠٧** دالّة تحمل النمط القاطع (بلا `assert`/`pytest.raises` **و** تُرجِع قيمة) عبر `tests_v9`/`tests`/`services`. أكثر من نصفها في ملفّ واحد.
- **الحارس:** `scripts/ci/assertion_presence_guard.py` + أساس مُجمَّد `docs/architecture/assertion_presence_baseline.json`. يفرض **مجموعة لا عدداً** (نفس درس #733): أيّ دالّة جديدة تحمل النمط تُسقِط CI بالاسم حتى لو انخفض العدد الكلّي — فلا يُستبدَل دَين بدَين.
- **حدود القاعدة عمداً:** بلا تأكيد **ولا** إرجاع (٧٤ دالّة) لا تُرصَد — قد تكون اختبار دخان مشروعاً («لا ينهار»). فُضِّلت صفر إيجابيّة كاذبة على شمول أوسع. و`pytest.raises` يُعَدّ تأكيداً صحيحاً.
- **مُكذَّب:** إسقاط إدخال من الأساس (محاكاة دالّة حيّة غير مُجمَّدة) يُسقِط الفحص **مسمّياً الدالّة**، والاستعادة تُعيده أخضر.
- **ما لم يُفعَل (حدّ صدق):** الـ٢٠٧ لم تُصلَح — إصلاحها تحويل كلّ دالّة إلى `assert` حقيقيّ، وهو عمل منفصل بحجم كبير. الحارس **يمنع النموّ** ويُبقي الدَّين مرئيّاً مُعدّاً، ولا يدّعي إغلاقه. والنتيجتان الحقيقيّتان المكشوفتان أعلاه تستحقّان معالجة مستقلّة.
- **أثره على أرقام هذه الجلسة:** `test_roadmap_phase23.py` **مُستبعَد من `-m unit`** (`143 deselected`) — فأرقام «3776 نجح» غير ملوّثة به. لكنّ الدرس عامّ: «نجح» في هذا المستودع لا يعني «أُكِّد».

## CAPABILITY-LINKER-SCANS-AGENT-WORKTREES-01 — مُغلقة (2026-07-30)

- **العطل:** `scripts/ci/capability_linker.py:discover_files()` يمسح `ROOT.rglob("*")` مباشرةً (فحص نظام ملفّات خام، لا `git ls-files`)، و`EXCLUDED_DIRS` كانت تستبعد `.git`/`node_modules`/`.venv`/`venv`/`dist`/`build`/`coverage`/`.next`/`__pycache__` — **لا `.claude`**. في بيئة هذه الجلسة (توزيع عمل على أربعة وكلاء متوازين عبر `Agent({isolation: "worktree"})`)، كلّ وكيل يعمل في نسخة كاملة من المستودع تحت `.claude/worktrees/agent-<id>/` — دليل حقيقيّ على القرص، مُستبعَد من `git` (`.gitignore:31`) لكن مرئيّ تماماً لأيّ مسح خام يبدأ من `ROOT`.
- **كيف ظهرت:** اكتُشفت لأنّ CI الحقيقيّ على PR #711 (أثناء إعادة بناء شريحة الوكيل D field-segmentation) أسقط `capability-registry` و`tests/architecture/test_capability_traceability.py::test_no_service_or_test_pointer_is_missing` برسائل `missing tests path .claude/worktrees/agent-.../...` — مسارات لا وجود لها على checkout حقيقيّ في GitHub Actions.
- **الأثر المقيس:** تشغيل `capability_linker.py --apply` أثناء إعادة البناء التقط أربع نسخ إضافيّة كاملة من ملفّات الاختبار/الموبايل عبر `.claude/worktrees/agent-{a065bac9508997bd9,a422d27a6fb01ae64,ab8c8dadbe172c08e,aea882e45cd006b77}/...` وكتب مساراتها البادئة بـ`.claude/worktrees/...` في حقول `tests`/`mobile_consumers` لعدّة قدرات (SEC-004 إلى SEC-008، INT-002، INT-003، FM-001 وغيرها) داخل `capabilities/registry/capabilities.json` **المُلتزَم فعليّاً**. عدد المرشّحين المكتشَفين قفز من ~1827 الطبيعيّ إلى 5171.
- **الفرق عن `test_dockerfile_pip_mirror_guard.py`/`test_scout_ingest_service_ownership.py` (فئة العلّة نفسها):** تلك حالتان أنتجتا فشل اختبار عابر لا يُلمَس ولا يُصلَح لأنّه لا يؤثّر على أيّ مصنوع مُلتزَم؛ هذه الحالة كتبت بيانات فاسدة إلى ملفّ **مُلتزَم فعليّاً** عبر `--apply`، لأنّ `capability_linker.py` يكتب لا يقرأ فقط.
- **الإصلاح:** أُضيف `.claude` إلى `EXCLUDED_DIRS` في `scripts/ci/capability_linker.py` — نفس نمط الاستبعاد البنيويّ المعتمَد سابقاً (`_is_test_file` في `api_versioning_policy_guard.py`، PR #709). إعادة تشغيل `--apply` نظَّفت كلّ الإدخالات الفاسدة تلقائيّاً (الحقول `tests`/`services`/`ui_consumers`/`mobile_consumers` تُعاد كتابتها كاملةً من الصفر في كلّ تشغيل، لا إلحاق).
- **البرهان بالتكذيب:** `tests/architecture/test_capability_linker.py::test_discover_files_excludes_claude_worktree_directories` — يزرع ملفّ اختبار داخل `.claude/worktrees/agent-fake123/tests/` في مستودع اصطناعيّ (`tmp_path`) ويؤكّد عدم تسرّبه. إزالة `.claude` من `EXCLUDED_DIRS` تُسقِطه فوراً باسم المسار المتسرِّب حرفيّاً؛ استعادته يُعيده أخضر.
- **التحقّق:** `python scripts/ci/capability_registry_guard.py` ⇒ `capability_registry_guard_ok` · `pytest tests/architecture/test_capability_traceability.py` ⇒ 5 نجحت · `verify_all_generated.py` ⇒ صفر انحراف · `pytest -m unit` ⇒ نجح كاملاً · `ruff check .`/`ruff format --check .` نظيفان.
- **حدّ صدق:** لم يُفحَص باقي حرّاس/مولّدات هذا المستودع بحثاً عن نفس العلّة (مسح خام بلا استبعاد `.claude`) بشكل شامل — هذا الإصلاح ضيّق النطاق لـ`capability_linker.py` تحديداً، المكتشَف بالفشل الفعليّ على CI. أيّ مولّد آخر يستخدم `Path.rglob`/`os.walk` من `ROOT` مباشرةً (لا `git ls-files`) قد يحمل نفس القابليّة للتأثّر في بيئة وكلاء متوازية مستقبليّة.
- **PR:** #711.

- **شريحة الوكيل B الأولى (2026-07-30) — guardrails-engine + supervisor-agent:** ٢٢١ ⇒ **٢١٣** (8 عقود فريدة). فُرِّع الأصل من `7563239b` على `agent-b-guardrails-supervisor-agent-v1`، ثمّ أُعيد بناؤه مرّة واحدة من `origin/main` بعد اندماج PR #711 (b0067e41).
  - **النطاق الحقيقيّ أضيق من النطاق المُسنَد:** خُصِّص للوكيل B أصلاً 115 موضعاً (sahool-platform 107 + guardrails-engine 3 + supervisor-agent 5)، لكن 99 من الـ107 كانت **مُصدَّرة فعلاً** عبر `APIRouter(prefix="/v1/...")` في ملفّاتها (`phase9_autonomous_farm_os.py`، `phase10_continuous_learning.py`، `phase11_federated_agents.py`، `phase12_marketplace_ecosystem.py`، `routers/gis_cloud_native.py`، `routers/irrigation_engineering.py`) — الحارس (`api_versioning_policy_guard.py:collect()`) يقرأ نصّ الديكوريتر فقط عبر AST، لا يُركِّب `prefix=` الراوتر مع مسار المسار، فصنَّفها خطأً كغير مُصدَّرة. **هذا ثالث ظهور لنفس فئة العمى التصنيفيّ في هذه الجلسة** (بعد `/v1/` مقابل `/api/v1/`، واستبعاد ملفّات الاختبار). لم يُصلَح هنا — فجوة كشف منفصلة، تحتاج شريحة تصحيح تصنيف مستقلّة قبل قياس مواضع sahool-platform الفعليّة، مُسجَّلة كملاحظة مفتوحة لا كإصلاح متسرّع. **مُغلَقة لاحقاً (2026-07-30، بعد اندماج شرائح الوكلاء الأربعة كلّها) — انظر قسم `تصحيح تصنيف ثالث` أدناه.**
  - **ما انتقل فعليّاً:** `services/guardrails-engine/routers/validation.py` (لا `prefix=`، مُركَّب مباشرةً فنصّ الديكوريتر هو المسار الفعليّ): `POST /validate`، `POST /approve/{workflow_id}`، `GET /workflow/{workflow_id}` ⇐ `/v1/*`. `services/supervisor-agent/routers/agent.py`: `POST /agent/query`، `POST /agent/optimize`، `GET /agent/tools`، `GET /agent/journal/{invocation_id}`، `GET /agent/actuator-audit` ⇐ `/v1/agent/*`.
  - **كلّ مستدعٍ حرفيّ حُدِّث:** استدعاءا `GUARDRAILS_URL` مباشران (`services/sahool-platform/core/field_intelligence_adapters.py`، `services/supervisor-agent/main.py`)، بوّابة الواجهة (`frontend/src/hooks/useApi.ts` ⇒ `/api/guardrails/v1/validate`، إذ موقع nginx's `/api/guardrails/` تمرير جذريّ شفّاف بلا قدرة rewrite)، ثلاث تشكيلات nginx (`nginx/nginx.fixed.conf`، `nginx/nginx.v9.conf`، `frontend/nginx.conf` — تُعيد كتابة `/api/agent/` إلى مسار خلفيّ غير جذريّ، فتحرّك هدف `proxy_pass` فقط إلى `.../v1/agent/` دون مسّ عقد البوّابة الخارجيّ `/api/agent/*`)، حارس تفكيك guardrails-engine الخاصّ، مرجع قدرة، وستّة مواقع اختبار نداء مباشر.
  - **إعادة بناء واحدة بعد اندماج PR #711 — نفس نمط شرائح الوكيل D:** الفرع بُني أصلاً على `7563239b` القديم؛ أُعيد بناؤه بالكامل من `b0067e41` (بعد اندماج PR #711 وإصلاح `CAPABILITY-LINKER-SCANS-AGENT-WORKTREES-01`). **تعارض محتوى حقيقيّ واحد** (لا مصنوعات مولَّدة فقط) ظهر أثناء إعادة التطبيق: `tests_v9/test_api_versioning_policy_guard.py` — كلّ شريحة من شرائح الوكيل A الثلاث أضافت اختبار تزييف خاصّاً بها إلى نفس الملفّ، وشريحة الوكيل B أضافت اختبارها الخاصّ أيضاً؛ حُلّ بدمج ثلاثيّ (`git apply --3way`) ثمّ دمج يدويّ بسيط (لا تداخل منطقيّ فعليّ بين الدوالّ الأربع، فقط تجاور نصّيّ).
  - **التحقّق:** `verify_all_generated.py` ⇒ صفر انحراف (56 خطوة + 5230 بصمة إصدار) · اختبار `test_guardrails_and_supervisor_agent_routes_are_versioned` (سليم من إعادة البناء) يؤكّد غياب المسارات القديمة وحضور `/v1/*` الجديدة في كلا الملفّين · بقيّة اختبارات الوكيل A الثلاثة في نفس الملفّ ما زالت خضراء بعد الدمج الثلاثيّ.
  - **PR:** #713 (أُعيد بناؤه على نفس رقم الفرع/الـPR؛ انظر `log.md` لرابط الدمج النهائيّ).

- **شريحة الوكيل C الأولى (2026-07-30) — raster-service imagery search — الشريحة الرابعة والأخيرة من الشرائح الأربع المفتوحة:** ٢١٣ ⇒ **٢٠٥** (8 عقود فريدة). ثمانية مسارات بحث صور في `services/raster-service/routers/imagery_search.py` — غير مُصدَّرة منذ ما قبل عرف `/v1` في هذه المنصّة — انتقلت إلى `/v1/imagery/*`: `GET /imagery/search/recent`، `GET /imagery/search/season`، `GET /imagery/best`، `POST /imagery/search`، `GET /imagery/search/radar`، `GET /imagery/search/landsat`، `GET /imagery/search/landsat-thermal`، `GET /imagery/dem`.
  - **مستهلكان حقيقيّان فقط:** `services/sahool-platform/api/raster_service_client.py:390` (`get_best_imagery_scene`) و`:413` (`search_imagery_scenes`) — الستّة الباقية بحث عامّ بلا مستدعٍ داخليّ (لا سجلّ docker-compose/nginx إذ متغيّرات البيئة تحمل عنوان القاعدة فقط لا جزء المسار).
  - **كلّ مستدعٍ حرفيّ حُدِّث:** `tests_v9/test_raster_endpoint_auth_coverage.py` (قوائم `PUBLIC_CATALOG`/`SERVICE_ONLY` — الحارس الذي يصنِّف كلّ نقطة raster حسب حارس المصادقة المطلوب)، `services/sahool-platform/tests/test_p2_1_imagery_automation_raster_facade_guard.py` (تأكيدات مسار حرفيّة)، دقّة docstring/تعليق فقط في `imagery_automation.py`/`imagery_providers.py`/`routers/{fields,analysis}.py`، ووثائق تتبّع (`capabilities/registry/capabilities.json` — 7 مداخل `apis`، `docs/capability-registry/domains/{farm_management,gis,satellite}.yaml`، `docs/openapi/{API_MAP.md,ROUTE_INVENTORY.json}`، `docs/audits/ADDITIONAL_PROVIDERS.md`، `skills/sahool-gis/TERRAIN_DEM.md`).
  - **درس الوكيل A طُبِّق لا تكرَّر خطؤه:** `docs/api/BACKEND_FRONTEND_COVERAGE.md` يُعلِن صراحةً «لا تُحرَّر يدويّاً»؛ الوكيل C شغَّل المولِّد الفعليّ (`endpoint_ui_coverage_gate.py --report`) بدل التحرير اليدويّ الذي وقعت فيه شريحتا الوكيل A الأولى والثانية وسُجِّل خطأً إجرائيّاً في `gaps/registry.md`.
  - **أُعيد بناء الفرع أربع مرّات إجمالاً عبر الجلسة:** الوكيل C نفسه أعاد بناء فرعه ثلاث مرّات تباعاً بمفرده مع اندماج شرائح الوكيل A (`7563239b`⇒`69572be7`⇒`160b0798`⇒`4d4f2d90`، كلّ مرّة يحسب الأثر الصحيح من القياس لا التنقيص الأعمى)، ثمّ أُعيدت بناء رابعة نهائيّة (بعد اندماج PR #711 وPR #713) من `b7fd2643`. **بلا أيّ تعارض محتوى حقيقيّ في أيّ من المرّات الأربع** — الرقعة المصدريّة (مسارات raster-service وملفّات الاختبار المرتبطة) طُبِّقت بلا نزاع كلّ مرّة؛ التعارضات الوحيدة كانت في المصنوعات المولَّدة المشتركة، مُعاد توليدها بالكامل في كلّ إعادة بناء بدل الدمج اليدويّ.
  - **التحقّق:** `verify_all_generated.py` ⇒ صفر انحراف (56 خطوة + 5230 بصمة إصدار) · اختبار تكذيب (عكس `GET /v1/imagery/best` مؤقّتاً إلى `GET /imagery/best`) أسقط اختبارَين بالاسم في `test_raster_endpoint_auth_coverage.py` (مسار غير مُصنَّف؛ مدخل `PUBLIC_CATALOG` بائت)؛ استعادة الإصلاح أعادتهما أخضرَين · `pytest -m unit` كامل بلا تعطُّل جديد · `ruff check .`/`ruff format --check .` نظيفان.
  - **PR:** #714 (أُعيد بناؤه على نفس رقم الفرع/الـPR بعد إعادة البناء الرابعة النهائيّة؛ انظر `log.md` لرابط الدمج النهائيّ). **بهذه الشريحة تُغلَق الشرائح الأربع المفتوحة أصلاً في خطّة توزيع الوكلاء الأربعة** — المتبقّي ٢٠٥ مساراً حقيقيّاً يشمل ٩٩ موضع sahool-platform المعروف عمى تصنيفيّاً (مسجَّل أعلاه) ونطاق Auth المفتوح صراحةً (مسجَّل في شريحة الوكيل A الثالثة) وبقيّة الخدمات الصغيرة، كلّ واحد شريحته المستقبليّة.

- **تصحيح تصنيف ثالث (2026-07-30) — عمى `APIRouter(prefix=...)` — مُغلَقة:** `_routes()` في `scripts/ci/api_versioning_policy_guard.py` كانت تقرأ نصّ الديكوريتر وحده (`@router.get("/plan")`) بلا تركيب بادئة الراوتر نفسه (`router = APIRouter(prefix="/v1/phase9/autonomy")` في نفس الملفّ) — فمسار مُصدَّر فعلاً على الشبكة (`/v1/phase9/autonomy/plan`) صُنِّف «غير مُصدَّر» لأنّ نصّه الحرفيّ لا يبدأ بمقطع إصدار. هذا هو العمى المُسجَّل OPEN في شريحة الوكيل B الأولى أعلاه.
  - **بحث شامل قبل التنفيذ — لا `include_router(prefix=...)` عبر المستودع كلّه:** `grep -rn "include_router(" services/ bots/ | grep "prefix="` ⇒ صفر نتائج. البادئة الوحيدة المُستعمَلة فعليّاً هي `APIRouter(prefix=...)` محليّة الملفّ، في ٦ ملفّات فقط: `services/sahool-platform/api/phase9_autonomous_farm_os.py`، `phase10_continuous_learning.py`، `phase11_federated_agents.py`، `phase12_marketplace_ecosystem.py`، `routers/gis_cloud_native.py`، `routers/irrigation_engineering.py`. فالتركيب محليّ الملفّ بحت — لا حاجة لتتبّع `include_router` عبر `main.py` لكلّ خدمة.
  - **الإصلاح:** دالّة جديدة `_router_prefixes(tree)` تفحص شجرة AST للملفّ وتُخرِج خريطة `{اسم المتغيّر: البادئة}` لكلّ `APIRouter(prefix="...")` (تعمل عبر `ast.walk` فتلتقط التصريح حتى داخل كتلة `if` كما في `phase12_marketplace_ecosystem.py:50-56`). `_routes()` تُركِّب البادئة مع نصّ الديكوريتر حين يكون كائن الاستدعاء (`@X.get(...)`) اسماً معروفاً في الخريطة؛ مسارات `@app.get(...)` (بلا راوتر) تبقى كما هي.
  - **القياس الدقيق:** ٩٩ موضعاً خام انقلب تصنيفه من `legacy_unversioned_business` إلى `versioned` عبر الملفّات الستّة (`phase9`:١١ · `phase10`:١٨ · `phase11`:١١ · `phase12`:١٧ · `gis_cloud_native`:٣٠ · `irrigation_engineering`:١٢). من بين هذه الـ٩٩: **٩٥ نصّاً فريداً** (method+path) — تكرار داخليّ اثنان: `POST /cycle` أربع مرّات (`phase9_autonomous_farm_os.py:148`، `phase10_continuous_learning.py:197`، `phase11_federated_agents.py:171`، `phase12_marketplace_ecosystem.py:239`) و`POST /models/register` مرّتين (`phase9_autonomous_farm_os.py:175`، `phase10_continuous_learning.py:269`). من الـ٩٥: **ثلاثة نصوص بقيت في قائمة السماح** لأنّ خدمة أخرى ما زالت تُعلِن نفس النصّ الحرفيّ بلا إصدار — العقود الذرّية العابرة للخدمات المُوثَّقة مسبقاً في شريحة الوكيل B: `POST /plan` ⇐ `agriai-engine/main.py:311`، `GET /stac` و`GET /stac/collections` ⇐ `raster-service/routers/stac.py:17,25`.
  - **الأثر النهائيّ:** ٩٥ − ٣ = **٩٢ عقداً فريداً أُغلِق** من قائمة السماح. الجرد الخام: legacy_unversioned_business المواضع ٢١٥ ⇒ ١١٦ (تقلّص ٩٩)، والعقود الفريدة ٢٠٥ ⇒ **١١٣** (تقلّص ٩٢).
  - **البرهان بالتكذيب:** اختباران جديدان في `tests_v9/test_api_versioning_policy_guard.py` — `test_router_prefix_is_composed_with_route_path` (اختبار وحدة على مصنَّع اصطناعيّ يثبّت `_router_prefixes`/`_routes` معاً، يؤكّد أنّ `@app.get(...)` بلا راوتر يبقى بلا بادئة) و`test_known_prefixed_sahool_platform_routers_classify_as_versioned` (اختبار تكامل يؤكّد أنّ كلّ مسار في الملفّات الستّة يُصنَّف `versioned`). كلاهما فُشِّل عمداً بإعادة النسخة الأصليّة من `_routes()` (نصّ الديكوريتر وحده بلا تركيب): سقطا بأسماء المسارات المتسرِّبة حرفيّاً (`/plan`، `/verify`، `/cycle`، ...، `/manual-executions/{execution_id}/reconcile`)؛ استعادة الإصلاح أعادتهما أخضرَين.
  - **التحقّق:** `verify_all_generated.py` ⇒ صفر انحراف (٥٦ خطوة + ٥٢٣٠ بصمة إصدار) · `pytest -m unit` كامل بلا تعطُّل جديد · `ruff check .`/`ruff format --check .` نظيفان.
  - **حدّ صدق:** الإصلاح مقصور على `APIRouter(prefix=...)` محليّ الملفّ فقط لأنّه النمط الوحيد المرصود فعليّاً (تحقّق شامل، لا افتراض). إن استُحدِث مستقبلاً نمط `include_router(..., prefix=...)` عابر للملفّات فلن يراه هذا الإصلاح، ويحتاج حينها امتداداً منفصلاً يتتبّع استدعاءات `include_router` عبر `main.py` لكلّ خدمة — لم يُبنَ استباقاً لغياب دليل استعماله الآن.
  - **PR:** انظر `log.md` لرقم PR ورابط الدمج.

- **شريحة الوكيل D الثانية (2026-07-30) — edge-inference + knowledge-graph:** ١١٣ ⇒ **١٠٧** (٦ عقود فريدة، بلا تكرار داخليّ أو عبر خدمات). فُرِّع من `origin/main` بعد اندماج PR #717 (`f6037dd3`)، على فرع `agent-d-slice-02-edge-inference-knowledge-graph`.
  - **كلا الملفّين بلا `prefix=`:** `@app.*` مباشرة، فنصّ الديكوريتر هو المسار الفعليّ — لا حاجة لتركيب بادئة راوتر (خلافاً لشريحة الوكيل A/B سابقاً).
  - **ما انتقل:** `services/edge-inference/main.py`: `POST /inference/pest-detect:199` ⇐ `/v1/inference/pest-detect`، `POST /inference/yield-estimate:261` ⇐ `/v1/inference/yield-estimate`، `POST /sync/trigger:327` ⇐ `/v1/sync/trigger`. `services/knowledge-graph/main.py`: `POST /nodes:119` ⇐ `/v1/nodes`، `POST /edges:127` ⇐ `/v1/edges`، `GET /edges:136` ⇐ `/v1/edges`.
  - **مستدعيات حقيقيّة وُجِدت بالبحث الشامل — فقط اثنان من الستّة يُستدعيان خارج ملفّيهما/اختباراتهما:**
    - `POST /inference/pest-detect`: `mobile/sahool_app/lib/services/api_service.dart:480` (نداء Dio حرفيّ `/api/edge/inference/pest-detect` عبر بروكسي `sahool-platform` الشفّاف `api/routers/service_proxy.py:132`، `proxy_edge` — نفس نمط field-segmentation: المسار يُمرَّر حرفيّاً بلا إعادة كتابة، فتغيّر ما يُرسِله العميل رغم أنّ كود البروكسي نفسه لا يُشفِّر المسار) و`services/video-processor/main.py:270` (نداء خدمة-لخدمة `f"{EDGE_INFERENCE_URL}/inference/pest-detect"`).
    - `GET /edges`: `services/ai_agronomist/ai_evidence_runtime.py:623` (نداء خدمة-لخدمة، يُمرِّر `X-Tenant-Id` الموثوق — حارس C2/C5 في knowledge-graph).
    - `yield-estimate`، `sync/trigger`، `POST /nodes`: بلا مستدعٍ خارجيّ متتبَّع (مُصنَّفة `internal` في `docs/api/BACKEND_FRONTEND_COVERAGE.md` قبل الشريحة وبعدها) — فقط اختباراتها الخاصّة.
  - **كلّ مستدعٍ حرفيّ حُدِّث:** `mobile/sahool_app/lib/services/api_service.dart:465,480` (تعليق + نداء) و`mobile/sahool_app/lib/screens/advisor_screen.dart:74` (تعليق) و`services/video-processor/main.py:258,270` (تعليق + نداء) و`services/ai_agronomist/ai_evidence_runtime.py:623` و`services/edge-inference/tests/test_edge_capabilities_and_fail_closed.py:72` و`tests_v9/test_gateway_trusted_identity_sec3.py:430,442,452,456`.
  - **بوّابة nginx:** `/api/edge/` (v9) تمرّ عبر `platform_backend` (بروكسي شفّاف كما أعلاه) — لا حاجة لتعديل nginx نفسه، المسار الخارجيّ `/api/edge/` ثابت والتغيير فقط فيما يُرسِله العميل بعده. `/api/knowledge-graph/` (v9 فقط، الوحيدة التي تملك هذه البوّابة) تمرّ مباشرةً إلى `kg_backend` بشرطة مائلة زائدة (`proxy_pass http://kg_backend/;`) — عُدِّلت إلى `http://kg_backend/v1/;` بنفس نمط `/api/agent/` من شريحة الوكيل B (PR #713)، رغم عدم وجود مستهلك خارجيّ متتبَّع لهذه البوّابة تحديداً (بحث شامل في frontend/mobile — صفر نتائج؛ العقد يبقى متّسقاً احتياطاً لأنّه مسار nginx حيّ). `nginx.light.conf`/`nginx.unified.conf` بلا بوّابة `/api/knowledge-graph/`، وبوّابتا `/api/edge/` فيهما تمرّان مباشرةً إلى `edge_backend` بمرور شفّاف بلا مسار مُلتصِق — لا حاجة لتعديلهما.
  - **وثائق حُدِّثت:** `RUNBOOK.md:76`، `docs/openapi/API_MAP.md:43-45`، `docs/openapi/ROUTE_INVENTORY.json:46-48` (لقطات ساكنة مُعلَنة «مُولَّدة آليّاً بفحص @app.route» لكن بلا مولِّد حيّ يُطابقه في `scripts/` — حُدِّثت يدويّاً، نفس القرار المتَّخَذ لملفّات مماثلة في شرائح سابقة). `docs/api/BACKEND_FRONTEND_COVERAGE.md` أُعيد توليده فعليّاً عبر `endpoint_ui_coverage_gate.py --report` — لا تحريراً يدويّاً، تطبيقاً لدرس الوكيل A المُسجَّل صراحةً في نفس الملفّ.
  - **تُركت عمداً — سجلّ تاريخيّ:** `docs/history/EDGE_REVIEW.md` (تقرير مراجعة مؤرَّخ يصف حالة كود سابقة — حدّ حجم رفع الصور، معالجة أخطاء Image.open) و`docs/BEST_PRACTICES_BENCHMARK_2026-06.md` (تقرير مقارنة بأفضل الممارسات مؤرَّخ بترقيم أولويّة P0-P3 خاصّ به — نفس فئة التقارير التاريخيّة المتروكة في شريحة MCP للوكيل A).
  - **البرهان بالتكذيب:** `tests_v9/test_api_versioning_policy_guard.py::test_edge_inference_and_knowledge_graph_routes_are_versioned` — كسر مقصود (إعادة `@app.post("/sync/trigger")`) أسقط الاختبار فوراً باسم المسار المتسرِّب حرفيّاً (`{'service': 'edge-inference', 'file': 'services/edge-inference/main.py', 'line': 328, ...}`)؛ استعادة الإصلاح أعادته أخضر.
  - **التحقّق:** `verify_all_generated.py` ⇒ صفر انحراف (٥٦ خطوة + ٥٢٣٠ بصمة إصدار) · `pytest -m unit`: ٣٧٥٨ نجح (+١ عن الشريحة السابقة)، صفر انحدار · `ruff check .`/`ruff format --check .` نظيفان.
  - **PR:** انظر `log.md` لرقم PR ورابط الدمج.

- **شريحة الوكيل D الثالثة (2026-07-30) — tts-service + local-ai-rag:** ١٠٧ ⇒ **١٠٣** (٤ عقود فريدة من ٦ مواضع خام). فُرِّع من `origin/main` بعد اندماج PR #718، على فرع `agent-d-slice-03-tts-local-ai-rag`.
  - **tts-service (`services/tts-service/routers/tts.py`، `router = APIRouter()` بلا `prefix=` — مُسجَّل مسطّحاً عبر `router_registry.py:_include_flat`):** `GET /tts/voices:20`، `GET /tts/status:30`، `POST /tts/synthesize:43`، `POST /tts/stream:124` ⇐ `/v1/tts/*` — الأربعة نصوص فريدة أصلاً، فأُغلِقت أربعتها في قائمة السماح.
  - **local-ai-rag (`services/local-ai-rag/main.py`):** `POST /query:419` ⇐ `/v1/query`، `POST /ingest:429` ⇐ `/v1/ingest` — **كلاهما نصّ كان مُشترَكاً**: `POST /query` مع `ai_agronomist/main.py:359` (خارج النطاق)، و`POST /ingest` مع `rag-retrieval/main.py:89` (خارج النطاق). موضعا local-ai-rag أُغلِقا من الجرد الخام (١١٠ ⇒ ١٠٤، تحقّق مباشر) لكن النصّين نفسيهما بقيا في قائمة السماح لأنّ الخدمتين الأخريين ما زالتا تُعلِنانهما بلا إصدار — سيُغلَقان حين تُهاجَران مستقبلاً. الأثر الصافي على السقف: ٤ عقود فقط لا ٦.
  - **مستدعيات حقيقيّة وُجِدت بالبحث الشامل:**
    - `POST /tts/synthesize`: `bots/telegram/main.py:197` و`agents/notification/agent.py:126` (نداءا خدمة-لخدمة مباشران عبر `TTS_URL`/`tts_url`، حُدِّثا). `frontend/src/services/api.ts:1838` يستدعي `kongApi.post('/tts/synthesize', ...)` **بلا بادئة `/api/`** — بوّابة `nginx.v9.conf`'s `location /tts/` تُمرِّر شفّافاً (`proxy_pass http://tts_backend;` بلا مقطع URI، فتُلحِق نصّ الطلب الأصليّ كاملاً). عُدِّل `proxy_pass` إلى `http://tts_backend/v1/tts/;` (استبدال جزء الموقع المُطابَق `/tts/` بـ`/v1/tts/`، نمط `/api/agent/`) — فبقي نداء الواجهة **بلا أيّ تغيير**.
    - `POST /query`: `services/supervisor-agent/skills/advisory_skill.py:60` (نداء خدمة-لخدمة عبر `LOCAL_AI_RAG_URL`، حُدِّث).
    - `GET /tts/voices`·`/status`·`/stream` و`POST /ingest`: بلا مستدعٍ خارجيّ متتبَّع غير اختباراتها الخاصّة.
  - **كلّ مستدعٍ حرفيّ حُدِّث:** `bots/telegram/main.py:197`، `agents/notification/agent.py:126`، `services/supervisor-agent/skills/advisory_skill.py:60`، `services/sahool-platform/api/decision_explainer.py:38` (تعليق)، `services/tts-service/test_tts_router_decomposition_guard.py:95-97` (`_CRITICAL_ROUTES`)، `tests_v9/test_tts.py:72,85`، `tests_v9/test_tts_providers_20260702.py` (٧ مواضع نصّ/تعليق)، `tests_v9/tts_route_source.py:6`، `tests_v9/test_tts_notification_service_auth.py:169` (تعليقان)، `services/tts-service/README.md` (توثيق نقاط النهاية الثلاث + مثال curl).
  - **بوّابتا nginx:** `nginx.v9.conf`'s `location /tts/` عُدِّلت كما أعلاه. `nginx.unified.conf`'s `location /api/rag/` — **اكتشاف مهمّ**: اسم upstream `rag_backend` يشير في هذه الطبولوجيا تحديداً إلى **`local-ai-rag`** (`upstream rag_backend { server local-ai-rag:8000; }`)، بينما نفس الاسم `rag_backend` في `nginx.v9.conf` يشير إلى **`rag-retrieval`** خدمة مختلفة تماماً (`server sahool-rag-retrieval:8000`) — تسمية متطابقة، خدمتان مختلفتان حسب الطبولوجيا. أُضيف تعليق توضيحيّ صريح لمنع خلط مستقبليّ، وعُدِّل `proxy_pass http://rag_backend/;` إلى `http://rag_backend/v1/;`. `nginx.light.conf` بلا بوّابة `/api/rag/` أصلاً.
  - **فجوة حوكمة ثانويّة أُغلِقت ضمن نفس الشريحة:** `config/platform_catalog_overrides.yml:93,98` كان يحمل قرارين يدويّين (`service_scoped_semantics`) لتصنيف `POST /query`/`POST /ingest` كتكرار نصّ عابر خدمتين. بعد أن أصبح لكلّ نصّ عضو واحد فقط (لا تكرار)، فشل `build_platform_catalog.py` حوكميّاً برسالتين صريحتين (`POST /ingest: stale decision (no measured duplicate group)`، مثلها لـ`/query`) — حُذِف القراران (لا أُعيد ربطهما بمسار جديد كما حدث مع `/products` في شريحة الوكيل A الثانية، إذ العقد الباقي أحاديّ العضو لا يحتاج قرار تصنيف تكرار أصلاً، خلافاً لـ`/products` حيث بقي عضوان بعد الهجرة). **اختباران مثبَّتان (pinned) تأثّرا وحُدِّثا بالقياس الجديد الصحيح** في `tests_v9/test_platform_catalog_gate.py`: `PINNED_UNIQUE_METHOD_PATH` ٩٩١ ⇒ **٩٩٣** (انقسام نصّين مشترَكين سابقاً إلى أربعة نصوص مستقلّة = +٢ فرادة)، و`duplicate_groups_classified` ١٥ ⇒ **١٣** (زوال مجموعتَي `/query`/`/ingest`).
  - **البرهان بالتكذيب:** `tests_v9/test_api_versioning_policy_guard.py::test_tts_service_and_local_ai_rag_routes_are_versioned` — كسر مقصود (إعادة `@app.post("/query")` في local-ai-rag) أسقط الاختبار فوراً باسم المسار المتسرِّب حرفيّاً؛ استعادة الإصلاح أعادته أخضر.
  - **التحقّق:** `verify_all_generated.py` ⇒ صفر انحراف (٥٦ خطوة + ٥٢٣٠ بصمة إصدار) · `pytest -m unit`: ٣٧٥٩ نجح (+١ عن الشريحة السابقة)، صفر انحدار بعد تحديث الثابتين المُثبَّتين · `ruff check .`/`ruff format --check .` نظيفان.
  - **PR:** انظر `log.md` لرقم PR ورابط الدمج.

- **شريحة الوكيل D الرابعة (2026-07-30) — ai_agronomist:** ١٠٣ ⇒ **٩٥** (٨ عقود فريدة من ٩ مواضع خام). فُرِّع من `origin/main` بعد اندماج PR #719، على فرع `agent-d-slice-04-ai-agronomist`.
  - **كلّ المسارات بلا `prefix=`:** `@app.*` مباشرة في `services/ai_agronomist/main.py`، فنصّ الديكوريتر هو المسار الفعليّ.
  - **ما انتقل:** `GET /approvals/pending:125`، `POST /approvals/approve:145`، `POST /approvals/deny:197`، `POST /approvals/resume:243`، `POST /prescription/export-preview:287`، `POST /query:359`، `POST /chat:370`، `POST /explain:381`، `POST /recommend:392` ⇐ `/v1/*`.
  - **`POST /recommend` بقي في القائمة (عقد واحد لا تسعة):** نصّه كان مُشترَكاً مع `agriai-engine/main.py:237` — خارج نطاق هذه الشريحة، مُخطَّط له كشريحة لاحقة قريبة. عضو واحد متبقٍّ فقط، سيُغلَق حين تُهاجَر agriai-engine.
  - **تعارض عرضيّ جديد اكتُشف بعد الهجرة:** `POST /v1/query` — ai_agronomist وlocal-ai-rag (الشريحة السابقة مباشرة، PR #719) صار كلاهما يُعلِن نفس النصّ الحرفيّ **مصادفةً** بعد أن هاجرت كلّ خدمة بمعزل عن الأخرى: كانا `POST /query` نصّاً غير مُشترَك أصلاً بين هاتين الخدمتين تحديداً (النصّ القديم `POST /query` كان مُشترَكاً بين ai_agronomist وagriai-engine من جهة، وbين local-ai-rag وai_agronomist من جهة أخرى — تشابك مختلف)، فالتقيا الآن على `/v1/query` عرضاً. `build_platform_catalog.py` كشف هذا فوراً (`POST /v1/query: measured duplicate group has no decision`) — أُضيف قرار حوكمة جديد `service_scoped_semantics` في `config/platform_catalog_overrides.yml` يوثِّق أنّهما عقدان مختلفان رغم تطابق النصّ الآن. بالتوازي، حُذِف قرار `POST /recommend` القديم (كان لعضوين، صار لعضو واحد بعد هجرة ai_agronomist، فلم يعد تكراراً يحتاج قراراً — نفس درس شريحة الوكيل D الثالثة).
  - **مستدعيات حقيقيّة وُجِدت بالبحث الشامل — أربعة نداءات واجهة حقيقيّة، لا خدمة-لخدمة:**
    - `frontend/src/hooks/useApi.ts:1982` (`kongApi.get('/api/ai-agronomist/approvals/pending')`) و`:1994` (`` kongApi.post(`/api/ai-agronomist/approvals/${decision}`, ...) ``).
    - `frontend/src/sections/ChatbotPage.tsx:217` (نفس نمط approvals) و`:525` (`kongApi.post('/api/ai-agronomist/chat', ...)`).
    - جميعها عبر بوّابة `nginx.v9.conf`'s `location /api/ai-agronomist/` الشفّافة (`proxy_pass http://ai_agronomist_backend/;` بلا مقطع URI) — عُدِّل `proxy_pass` إلى `http://ai_agronomist_backend/v1/;` (نمط `/api/agent/`/`/api/knowledge-graph/`/`/api/rag/` السابق) فبقيت **الأربعة نداءات بلا أيّ تغيير في كود الواجهة**.
    - اختبارا الواجهة الساكنَين (`frontend/src/sections/ChatbotPage.endpoint.test.ts`، `ChatbotApprovalUi.v58.static.test.ts`) يتحقّقان من نصّ `ChatbotPage.tsx` نفسه لا من الخلفيّة — بقيا صحيحَين بلا تعديل، مطابقةً لسلوكهما المتوقَّع بعد امتصاص nginx للإصدار.
    - بقيّة المسارات (`/prescription/export-preview`، `/explain`) بلا مستدعٍ خارجيّ متتبَّع غير اختباراتها.
  - **كلّ مرجع حرفيّ آخر حُدِّث:** `scripts/ci/ai_agronomist_main_decomposition_guard.py` (٤ سلاسل ديكوريتر مُتحقَّقة)، `tests_v9/runtime_activation/test_phase2_ai_gateway_web_binding_static.py` (٤ سلاسل مماثلة)، `tests_v9/test_gateway_trusted_identity_sec3.py` (قسم SEC-3/SEC-3.1 كاملاً — ١٠ مواضع عبر `parametrize` ونداءات مباشرة)، `tests_v9/test_agent_stores_v58_2.py`، `tests_v9/test_ai_approval_endpoints_v58.py`، `tests_v9/test_runtime_evidence_wiring_v62_2.py`، `docs/capability-registry/domains/decision.yaml`، `docs/capability-registry/domains/precision.yaml`. `docs/api/BACKEND_FRONTEND_COVERAGE.md` أُعيد توليده فعليّاً عبر `endpoint_ui_coverage_gate.py --report`.
  - **`docs/security/SEC-3.1_approvals_user_role.md` — نصّ حيّ لا تقرير تاريخيّ:** يصف عقداً أمنيّاً **مُطبَّقاً حاليّاً** (لا مراجعة نقطة-في-الزمن كالتقارير المؤرَّخة المتروكة في شرائح سابقة)، فحُدِّثت مساراته الحرفيّة (`/approvals/*`، مثال كود `@app.post(...)`، `proxy_pass` في مقتطف nginx توضيحيّ). **أُبقيت عمداً** أرقام الأسطر البائتة أصلاً في الوثيقة (`L135/L182/L223`، `nginx/nginx.v9.conf:308-314`) دون تصحيح — انحراف سابق الوجود غير ناتج عن هذه الشريحة ولا تفاقم به (المسارات الفعليّة في `main.py` عند هذه الشريحة كانت 145/197/243 لا 135/182/223 أصلاً)، تصحيحه خارج نطاق هجرة الإصدار.
  - **`docs/openapi/API_MAP.md`/`ROUTE_INVENTORY.json` لا يذكران ai_agronomist أصلاً** — نقص سابق الوجود (الوثيقة لم تكن مكتملة أصلاً، مُلاحَظ في شرائح سابقة)، خارج نطاق هذه الشريحة إكماله.
  - **البرهان بالتكذيب:** `tests_v9/test_api_versioning_policy_guard.py::test_ai_agronomist_routes_are_versioned` — كسر مقصود (إعادة `@app.post("/chat")`) أسقط الاختبار فوراً باسم المسار المتسرِّب حرفيّاً (`{'service': 'ai_agronomist', 'file': 'services/ai_agronomist/main.py', 'line': 371, ...}`)؛ استعادة الإصلاح أعادته أخضر.
  - **التحقّق:** `verify_all_generated.py` ⇒ صفر انحراف (٥٦ خطوة + ٥٢٣٠ بصمة إصدار) · `pytest -m unit`: ٣٧٦٠ نجح (+١ عن الشريحة السابقة)، صفر انحدار · `ruff check .`/`ruff format --check .` نظيفان.
  - **PR:** انظر `log.md` لرقم PR ورابط الدمج.

- **شريحة الوكيل D الخامسة (2026-07-30) — rag-retrieval + agriai-engine — إغلاق نطاق الوكيل D الأصليّ بالكامل:** ٩٥ ⇒ **٨٩** (٦ عقود فريدة من ٦ مواضع خام، صفر تكرار عند لحظة الهجرة نفسها). فُرِّع من `origin/main` بعد اندماج PR #720، على فرع `agent-d-slice-05-rag-retrieval-agriai-engine`.
  - **كلّ المسارات بلا `prefix=`:** `@app.*` مباشرة في كلا الملفّين.
  - **rag-retrieval (`services/rag-retrieval/main.py`):** `POST /ingest:89` ⇐ `/v1/ingest`، `POST /search:114` ⇐ `/v1/search`.
  - **agriai-engine (`services/agriai-engine/main.py`):** `POST /recommend:237` ⇐ `/v1/recommend`، `POST /simulate:297` ⇐ `/v1/simulate`، `POST /plan:310` ⇐ `/v1/plan`، `POST /replay/verify:326` ⇐ `/v1/replay/verify`.
  - **تعارضان عرضيّان جديدان اكتُشفا فوراً بعد الهجرة (تقارب نصّيّ بين شرائح مستقلّة، لا علاقة دلاليّة سابقة):** `POST /v1/ingest` (rag-retrieval × local-ai-rag، الأخيرة من شريحة الوكيل D الثالثة) و`POST /v1/recommend` (agriai-engine × ai_agronomist، الأخيرة من شريحة الوكيل D الرابعة). أُضيف قراران جديدان `service_scoped_semantics` في `config/platform_catalog_overrides.yml` يوثِّقان أنّهما عقود مختلفة تماماً رغم تطابق النصّ عرضاً.
  - **فجوة كشف رابعة من عائلة العمى التصنيفيّ — `POST /plan` وشبح نصّيّ في مولِّد شقيق:** القرار القديم لـ`POST /plan` (`legacy_bff_facade`، `canonical_owner: agriai-engine`، `facade: sahool-platform`) افترض عضوين حقيقيّين مُشترَكين. تبيَّن أنّ عضو sahool-platform لم يكن حقيقيّاً قطّ: `phase9_autonomous_farm_os.py`'s راوتر بادئته `/v1/phase9/autonomy` (مُصدَّر فعلاً)، فمساره الحقيقيّ `/v1/phase9/autonomy/plan` لا `/plan` الخام. السبب: `scripts/ci/generate_service_inventory.py` — المولِّد المسؤول عن `route_inventory.generated.json` الذي يقرأه `build_platform_catalog.py` لكشف التكرار — يحمل **نفس** عمى `APIRouter(prefix=...)` المُصلَح في `api_versioning_policy_guard.py` (PR #717) لكن **لم يُصلَح هنا قطّ**؛ فسجَّل sahool-platform's phase9 كمالك مسار `/plan` خام زوراً. حُذِف قرار `/plan` (بات `stale decision` بعد هجرة agriai-engine — العضو الحقيقيّ الوحيد اختفى، والعضو الوهميّ المتبقّي لا يُشكِّل تكراراً حقيقيّاً). **هذه رابع ظهور لنفس فئة العمى التصنيفيّ في هذه الجلسة** (بعد `/v1/` مقابل `/api/v1/`، استبعاد ملفّات الاختبار، `APIRouter(prefix=...)` في `api_versioning_policy_guard.py` نفسه) — لكن في مولِّد شقيق مختلف تماماً هذه المرّة. غير مُصلَحة في هذه الشريحة، مُسجَّلة كفجوة كشف مستقلّة تحتاج شريحة تصحيح تصنيف مخصّصة في `generate_service_inventory.py` قبل الوثوق بقياس التكرارات عبره بثقة كاملة.
  - **مستدعيات حقيقيّة وُجِدت بالبحث الشامل — واحدة فقط:** `GET /v1/search` عبر `services/ai_agronomist/ai_evidence_runtime.py:605` (نداء خدمة-لخدمة عبر `RAG_BASE_URL`، حُدِّث). بقيّة المسارات الخمسة بلا مستدعٍ خارجيّ متتبَّع — agriai-engine بالذات **غير مُستهلَكة عمداً بالكامل** (`wired=False`، قرار معماريّ مسجَّل مسبقاً في هذا المستودع، ليست فجوة).
  - **بوّابتا nginx (كلاهما داخليّتان بلا وصول متصفّح):** `nginx.v9.conf`'s `location /api/rag/` (تشير إلى rag-retrieval هنا تحديداً، لا local-ai-rag كما في `nginx.unified.conf` — نفس تنبيه التسمية المزدوجة من شريحة الوكيل D الثالثة) عُدِّلت. `nginx.v9.conf`'s و`nginx.unified.conf`'s `location /api/agriai/` عُدِّلتا كلتاهما رغم غياب مستهلك متتبَّع — العقد يبقى متّسقاً احتياطاً. `nginx.light.conf` بلا بوّابتَي `/api/rag/`/`/api/agriai/` أصلاً.
  - **كلّ مرجع حرفيّ آخر حُدِّث:** `tests_v9/test_gateway_trusted_identity_sec3.py` (قسم rag-retrieval كاملاً — ٦ مواضع فاتت الفحص النصّيّ الأوّليّ لهذه الشريحة، اكتُشفت عبر `pytest -m unit` الكامل بعد الالتزام الأوّليّ؛ **درس عمليّاتيّ:** البحث النصّيّ المُسبَق لا يُغني عن تشغيل السويت الكامل قبل الالتزام النهائيّ)، `tests_v9/test_agriai_engine_features_20260702.py` (٧ مواضع)، `docs/openapi/API_MAP.md`+`ROUTE_INVENTORY.json` (إدخال agriai-engine الوحيد الموجود أصلاً — الوثيقتان لا تذكران rag-retrieval إطلاقاً، نقص سابق الوجود). `docs/api/BACKEND_FRONTEND_COVERAGE.md` أُعيد توليده فعليّاً.
  - **ثابتان مثبَّتان (pinned) تأثّرا في `tests_v9/test_platform_catalog_gate.py`:** `PINNED_UNIQUE_METHOD_PATH` ٩٩٣ ⇒ **٩٩٢** (صافي: −١ من إغلاقَي `/ingest`/`/recommend` الحقيقيَّين، +١ محايد من `/search`/`/simulate`/`/replay-verify`، +١ ثابت من شبح `/plan` الذي لا يختفي رغم الهجرة)، و`duplicate_groups_classified` ١٣ ⇒ **١٤** (−١ إزالة `/plan` + ٢ إضافة `/v1/ingest`+`/v1/recommend`)؛ اختبار `test_u4` أيضاً عُدِّل (لم يعد `facades[('POST','/plan')]` مُصنَّفاً).
  - **البرهان بالتكذيب:** `tests_v9/test_api_versioning_policy_guard.py::test_rag_retrieval_and_agriai_engine_routes_are_versioned` — كسر مقصود (إعادة `@app.post("/plan")`) أسقط الاختبار فوراً باسم المسار المتسرِّب حرفيّاً؛ استعادة الإصلاح أعادته أخضر.
  - **التحقّق:** `verify_all_generated.py` ⇒ صفر انحراف (٥٦ خطوة + ٥٢٣٠ بصمة إصدار) · `pytest -m unit`: ٣٧٦١ نجح (+١ عن الشريحة السابقة)، صفر انحدار بعد تحديث الثابتين المُثبَّتين واختبار الواجهة الإضافيّ · `ruff check .`/`ruff format --check .` نظيفان.
  - **بهذه الشريحة يُغلَق نطاق الوكيل D الأصليّ بالكامل:** سبع خدمات (field-segmentation، edge-inference، knowledge-graph، tts-service، local-ai-rag، ai_agronomist، rag-retrieval، agriai-engine — ثماني خدمات فعليّاً بالعدّ الدقيق)، خمس شرائح، خمسة PR (#711، #718، #719، #720، وهذا).
  - **PR:** انظر `log.md` لرقم PR ورابط الدمج.

- **الإصلاح المُنفَّذ:** راتشِت في `docs/architecture/api_versioning_legacy_baseline.json` — سقف **٧٤٩** يتقلّص ولا ينمو. مُكذَّب بالاتّجاهات الثلاثة (نموّ `rc=1` · تقلّص `rc=0` · مطابق `rc=0`)، وبرموز خروج مقروءة **بلا أنبوب** بعد أن خدعني `| tail` أوّل مرّة.
- **القياس الذي يبقى مفتوحاً:** **٥١٧ من ٧٤٩** في القائمة تبدأ بـ`/api/v1/` — أي **مُصدَّرة فعلاً ومُصنَّفة خطأً**. المُصنِّف يعرف `/v1/` ولا يعرف `/api/v1/`.
- **لماذا لم أُصلحه هنا:** تصحيحه يُعيد تصنيف ٥١٧ مساراً (القائمة ٧٤٩ ⇒ ~٢٣٢). التقلّص يسمح به هذا الأساس **ويشجّعه**، لكنّه شريحة قائمة بذاتها تستحقّ قياس أثرها على ما يعتمد على التصنيف قبل تنفيذها.
- **حدّ صدق:** الأساس المُجمَّد يحتوي ٥١٧ مدخلاً **مُصنَّفاً خطأً** — مُعلَناً في الملفّ نفسه لا مخفيّاً. تجميد رقم يعرف المرء أنّه خاطئ مقبول ما دام يمنع النموّ ويُسمّي خطأه؛ غير المقبول تجميده بصمت. — OPEN (P2) 2026-07-28

- **كيف ظهرت:** لم تُبحَث. ظهرت لأنّ `TESTS-UNMARKED-DESELECTED-01` أيقظ
  `test_api_versioning_policy_guard`، وإغلاق سببه استلزم قراءة ما يفعله الحارس فعلاً.
- **العيب الأوّل — «قائمة السماح» مُشتَقّة لا مُقرَّرة:** `write()` في
  `scripts/ci/api_versioning_policy_guard.py:104-113` **يُعيد حساب**
  `api_versioning_legacy_allowlist.generated.json` من الشجرة في كلّ تشغيل. فالفحص الوحيد
  هو «هل يطابق المُلتزَم ما أُعيد حسابه» — كاشف انحراف لا بوّابة سياسة. مسار عمل جديد غير
  مُصدَّر **لا يمكن** أن يُسقِط الحارس: يكفي تشغيل الأمر ليُقبَل، ورسالة الفشل نفسها تأمر
  بذلك (`rerun … and review unversioned allowlist`) — و«المراجعة» بشريّة غير مفروضة.
- **العيب الثاني — المُصنِّف أعمى عن `/api/v1`:** `_classify` يعدّ المسار مُصدَّراً إن بدأ
  بـ`/v1/` فقط (سطر 68). والبادئة القانونيّة في هذه المنصّة هي `/api/v1/*` (‏CLAUDE.md).
  **مقيس:** من ٧٤٩ مسار في «قائمة السماح للأعمال غير المُصدَّرة»، **٥١٧ (٦٩٪) تبدأ بـ
  `/api/v1/`** — أي مُصدَّرة فعلاً ومُصنَّفة خطأً. غير المُصدَّر حقّاً **٢٣٢**.
- **لماذا يهمّ:** الرقم المُعلَن (`legacy_unversioned_business: 769`) يُضخّم الدَّين ثلاثة
  أضعاف تقريباً، فيصير مؤشّراً لا يُقرأ. ومقياس مُضخَّم لا يُصلَح أبداً — لأنّ إصلاحه يبدو
  مستحيلاً.
- **لماذا لم يُصلَح هنا:** تصحيح `_classify` يُعيد تصنيف **٥١٧ مساراً** دفعةً واحدة، ويمسّ
  جرداً يقرأه غيره. تغيير بهذا الحجم يستحقّ شريحته ومراجعته، لا أن يُدسّ في شريحة عن
  علامات الاختبارات.
- **حدّ صدق عن هذه الشريحة:** أُعيد توليد الجرد (وهو شرط إيقاظ الاختبار) فدخلت **٢٢**
  مساراً جديداً إلى الملفّ (‏farm-book · yield-maps · varieties · erp/reconciliations).
  **هذا لا يمنح إذناً**: الملفّ مُشتَقّ ولا يُنفَّذ به شيء — لكنّه يُسجَّل هنا كي لا يُقرأ
  لاحقاً كقبول صامت لاثنين وعشرين مساراً.
- **المصدر:** `scripts/ci/api_versioning_policy_guard.py:68` (المُصنِّف) · `:104-113`
  (الاشتقاق) · `:126-135` (المقارنة) · قياس على `82ba88ad`.
## PATH3-READINESS-CLAIM-UNBACKED-01 — FIXED_IN_CODE (2026-07-29) — **وتصويب على تشخيصي**

- **التشخيص الأوّل كان مقلوباً، وأعلنتُه ثلاث مرّات:** قلتُ إنّ الأثر المُلتزَم «يدّعي جاهزيّةً لا تسندها الشجرة». **العكس هو الصحيح** — الشجرة تسندها، و**الإنذار** هو الذي كان كاذباً.
- **ما فحصتُه أخيراً ولم أفحصه أوّلاً — أيّ الجانبين بائت:** `runtime_probe_plan.json` تغيّر **أربع مرّات** (`cae51f7` ⇒ `6ca361d` ⇒ `4fa8014` ⇒ `fce91a9`/#678، كلّها 2026-07-28)، بينما `compose_runtime_targets.json` لم يُعَد توليده منذ `0dad1a1`/#670. فالمُشتقّ متخلّف عن مصدره، لا الحالة منقلبة.
- **البرهان:** إعادة توليد المُحلِّل ثمّ `path3` ⇒ `closed=true` · `READY_FOR_LIVE_EXECUTION` · `target_plan_hash_matches=true`، و**ملفّ واحد فقط تغيّر** (`compose_runtime_targets.json`). أثر `path3` المُلتزَم لم يتغيّر بحرف — أي أنّه كان **صحيحاً طوال الوقت**.
- **لماذا بقي بائتاً شهراً:** لا workflow يذكر المُحلِّل (الزاوية العمياء، `GENERATED-ARTIFACT-SWEEP-01`). أربع شرائح غيّرت الخطّة ولم يُعِد أيّ منها توليد ما يشتقّ منها.
- **الأثر على الأساسين:** `arch_test_ci_coverage_baseline` تقلّص **3 ⇒ 1**، و`tests_tree_baseline` تقلّص **10 ⇒ 8**، وأُدرِج الاختباران في `capability-governance.yml`. الحرّاس: arch **55/56** · tests-tree **106/114 يُشغَّل**.
- **الدرس الذي دفعتُ ثمنه:** عرضتُ على المالك «قرارين ولا ثالث» — وكان الثالث موجوداً ولم أبحث عنه: **أيّ الجانبين بائت**. صياغة الخيارات بديلٌ رديء عن إتمام التشخيص، وقد أوقفتُ عملاً بانتظار قرار لم يكن لازماً.
- **يبقى مُعفى واحد:** `test_runtime_environment_preflight` — بصمة بيئة حقيقيّة، علاجها تصميميّ (`docker_reachable` بدل نصّ خطأ العميل).

- **الأثر:** `governance/path3-generated/PATH3_RUNTIME_READINESS_CLOSURE.json` المُلتزَم يقول `target_plan_hash_matches=true` · `closed=true` · `status=READY_FOR_LIVE_EXECUTION`. إعادة توليده **على الشجرة نفسها بلا أيّ تغيير** تقول `false` · `false` · `BLOCKED_STATIC_READINESS`.
- **السبب المُثبَت (سلسلة من خطوتين):** `runtime-verification/generated/runtime_probe_plan.json` يُعلن `plan_sha256=f82e9be9…`، بينما `runtime-verification/generated/compose_runtime_targets.json` يسجّل `source_plan_sha256=07820538…` — بصمة خطّة **أقدم**. تغيّرت الخطّة ولم يُعَد توليد المُحلِّل، فورث `path3` مقارنةً كاذبة.
- **لماذا P0:** وثيقة حوكمة مُلتزَمة **تدّعي جاهزيّةً لا تسندها الشجرة** — صنف «الأخضر الكاذب» الذي بُنيت له هذه المنظومة، مُعلَناً في وثيقة لا في تعليق.
- **لماذا لم أُصلحه:** إعادة التوليد تقلب حالة حوكمة إلى `BLOCKED_STATIC_READINESS`. **تغيير حالة لا تحديث بصمة** — لا يُقلَب بأمر آليّ ولا بقرار وكيل، وتحت قاعدة المالك «لا تمسّ حالات الاعتماد».
- **القراران المتاحان ولا ثالث:** (١) تصحيح بصمة الخطّة فتعود المطابقة صادقةً ويبقى `closed=true` بحقّ؛ (٢) قبول `BLOCKED_STATIC_READINESS` بوصفه الحقيقة وإعادة التوليد. إبقاء الحال = إبقاء ادّعاء غير مسنَد.
- **لماذا لا تراه المكنسة (#691):** اكتشافها من الـworkflows — وهو تصميم صحيح لما **يُشغّله** CI، أعمى بالتعريف عمّا **نسيه**. القياس: **٤٣ مولِّداً في الشجرة · ٣٩ مذكوراً في workflow · ٤ عمياء**، والثلاثة المنحرفة كلّها منها. تُبلِّغ عنها المكنسة الآن ولا تُشغّلها.
- **الثالث ليس من هذه العائلة:** `runtime_environment_preflight` بصمة بيئة حقيقيّة — يكتب `Python: 3.12.3` ونصّ خطأ Docker الخاصّ بعميل مُشغِّله؛ التوليد على آلة أخرى يكتب `3.11.15` ونصّاً مختلفاً لنفس السبب. علاجه تصميميّ: يسجّل **قدرةً** (`docker_reachable: false`) لا نصّ خطأ.

## RUNTIME-ENV-PREFLIGHT-STAMPS-THE-MACHINE-01 — FIXED_IN_CODE (2026-07-29)

- **العلّة:** أثر `runtime_environment_preflight` كان يسجّل **هويّة الآلة** لا **قدرة المنصّة**: نصّ خطأ عميل Docker حرفيّاً (يختلف بين إصداراته لنفس السبب)، و`platform.release`/`python_version`، ونسخة كلّ أداة ومسارها المطلق. فكان `--check` يفشل على **كلّ آلة غير المولِّدة** — لا لانحراف بل لاختلاف صياغة.
- **الإصلاح — قدرة لا هويّة:** سبب الخفيّ يُصنَّف (`daemon_unreachable` · `daemon_permission_denied` · `daemon_error` · `probe_failed`) بدل نقل نصّه؛ و`platform` يحتفظ بـ`system`+`machine` وحدهما؛ والأداة تُبلِّغ `available` بلا `version` ولا `path`.
- **لم يُوسَّع `normalized()`:** توسيعه كان **يُخفي** التباين، وتغيير ما يُسجَّل **يُزيله**. الفرق أنّ الأوّل يجعل الفحص يكذب بلطف، والثاني يجعله صادقاً.
- **مُثبَت:** `--check` ⇒ `rc=0` · الاختبارات الثلاثة تمرّ · الأثر صار `{"machine","system"}` و`reason: daemon_unreachable` و`tools.docker: {"available": true}`.
- **الأثر على الأسس:** `arch_test_ci_coverage_baseline` تقلّص **1 ⇒ 0** فحُذِف الملفّ (بقاعدته المكتوبة فيه: «الأساس فارغ ⇒ احذف الملفّ»)، والحارس صار **56/56 · صفر إعفاء**. وأساس المكنسة: المنحرفون **2 ⇒ 1** (بقي `capability_linker` وحده، وهو الوحيد **بلا حارس البتّة**).
- **حدّ صدق:** يبقى في الأثر `machine`/`system` — وهما وصف آلة أيضاً، لكنّهما ثابتان عبر عدّاءات هذا المشروع (`x86_64`/`Linux`). لم أُسقطهما لأنّ إسقاطهما يُفرِغ الحقل من معناه؛ وإن اختلفت معماريّة عدّاء مستقبلاً فسيظهر الفحص أحمر بحقّ لا بخطأ.

### الشطر الثاني (#700، مُنفَّذ 2026-07-29): حدّ الصدق أعلاه كان **أقلّ ممّا يستحقّ**

- **ما كشفه CI بعد الإصلاح الأوّل:** الفحص بقي أحمر — لا لصياغة بل لأنّ عدّاء GitHub يملك
  Docker (‏`28.0.4`) فيولّد `RUNNABLE`، والأثر المُلتزَم من صندوق بلا خفيّ يقول
  `BLOCKED_ENVIRONMENT`. **والاثنان صادقان.** فالمتبقّي لم يكن `machine`/`system` كما
  قُدِّر أعلاه، بل `docker_daemon.reachable` و`state` و`blockers` — أي **جوهر الأثر**، ولا
  يُسقَط بلا إفراغه من غرضه.
- **الحكم:** `docstring` الملفّ يقول إنّه يقيس «**هذا** الـcheckout». فمقارنة إجابة مُلتزَمة
  بآلة أخرى ليست كشف انحراف بل ادّعاءً بأنّ الآلات كلّها آلة واحدة.
- **الشكل المعتمَد — طبقتان:** `capability_scope` يُعلن البيئة التي يصفها الأثر، فتُفرَض
  **المساواة الكاملة** حين يتطابق النطاق و**تُعلَن صراحةً** حين تُتخطّى؛ وفوقها
  `shape_problems` تُفحَص **في كلّ مكان** لأنّها لا تعتمد على آلة: حالة تناقض حاجبها ·
  ادّعاء `runtime_verified`/`production_certified` · سبب خارج المفردات المُصنَّفة · سجلّ
  أداة يحمل أكثر من `available`.
- **وطبقة الشكل كشفت تسرّباً تركه الشطر الأوّل:** الأداة **المفقودة** كانت تُسجَّل بثلاثة
  مفاتيح (`available`/`path`/`version`) و**الموجودة** بمفتاح واحد — أي أنّ **شكل السجلّ**
  نفسه يتغيّر بتغيّر الآلة، وهي بصمة في البنية لا في القيمة. صارتا `{"available": …}` معاً.
- **مُكذَّب حيث يُهمّ:** التكذيب أُجري على آلة **تُحاكي CI** (Docker متاح)، أي حيث تُتخطّى
  المقارنة وأيّ ثقب فيها غير مرئيّ — والأربعة تُسقِط الفحص هناك.
- **الدرس المُسجَّل:** «حدّ الصدق» الذي يُكتب من آلة واحدة يميل إلى تصغير نفسه. الأوّل سمّى
  الحقلين الظاهرين وأغفل الحقول التي **هي** الأثر؛ ولم يظهر ذلك إلّا حين شغّلته آلة مختلفة.

## GEOSPATIAL-GOVERNANCE-LIVE-CERT-01 — OPEN / BLOCKED-OPERATIONAL (2026-07-30)

- **المصدر:** `sahool-brain/hot.md` (قسم الحوكمة الجغرافية) · غياب `scripts/ci/geospatial_contract_index_guard.py` · الحاجة إلى PostgreSQL/CDSE/MinIO حيّة.
- **النطاق:** ثلاث نتائج مترابطة لا يجوز إعلانها من فحص ساكن: تصنيف سجلّ جغرافي v2 للبدائل الدلالية الحاملة، حارس فهرس العقود الجغرافية، وشهادة تشغيل حيّة لمسار PostgreSQL→CDSE→MinIO.
- **الحالة:** OPEN / BLOCKED-OPERATIONAL — لا يوجد الحارس في الشجرة، ولا بيئة الخدمات الحية في لقطة ZIP. لا `runtime_verified` ولا `production_certified` حتى تنفيذ البرهان الحي وتسجيل نتائجه.
- **شرط الإغلاق:** مواصفة التصنيف مع أمثلة مضادة، إضافة الحارس وربطه بالـCI، ثم تشغيل شهادة حية تحفظ أوامرها ومخرجاتها ومعرّفات الآثار.


## GENERATED-CHECK-IGNORES-ITS-OWN-COMPANION-ARTIFACTS-01 — مُغلقة (2026-08-01)

- **المصدر:** قياس مباشر على `09e34e1d`: لكلّ مولّد في أساس `docs/architecture/generated_sweep_unmapped_generators.json` اكتُشفت مصنوعاته بمقارنة أزمنة تعديل الملفّات المتعقَّبة قبل/بعد تشغيل علم الكتابة، ثمّ أُفسِدت كلّ مصنوعة على حدة وأُعيد تشغيل `--check`.
- **العلّة:** بوّابة `--check` تُقارِن **بعض** ما يكتبه مولّدها لا كلّه. النمط المتكرّر: تُقارَن `*.generated.json` ويُترك رفيقاها `.csv` و`.md` المكتوبان في التشغيل نفسه بلا حراسة.
- **القياس — ١٣ مصنوعة من ١٦ عمياء** (على `bbfe121f`): `scripts/ci/ai_container_contract_guard.py` ٢/٢ · `scripts/ci/duplicate_definition_guard.py` ١/١ · `scripts/ci/runtime_container_deep_contract_guard.py` ٢/٢ (هذه الثلاثة **عمياء تماماً** — لا مصنوعة واحدة محروسة) · `scripts/ci/capability_registry_v1.py` ٤/٥ · `scripts/ci/platform_main_subinventory_guard.py` ٢/٣ · `scripts/ci/production_certification_checklist_guard.py` ٢/٣.
- **تصحيح رقم مُسجَّل:** كُتِب هنا سابقاً «١٢ من ١٦». إعادة الجمع على نفس الأرقام لكلّ حارس تُعطي **١٣**. جمعٌ خاطئ لا قياسٌ مختلف.
- **تصحيح سبب مُسجَّل:** كُتِب أنّ الثلاثة العمياء تماماً تُعيد التوليد أثناء الفحص فتمحو الإفساد. القياس بأزمنة التعديل كذّب ذلك: **واحد فقط** يكتب أثناء `--check` (`duplicate_definition_guard`)؛ أمّا `ai_container_contract_guard` و`runtime_container_deep_contract_guard` فلا يكتبان و**لا يقارنان الملفّ إطلاقاً** — يعيدان بناء الجرد في الذاكرة ويؤكّدان قواعدهما الدلاليّة عليه ولا ينظران إلى الملفّ المُلتزَم مرّة. الأثر واحد والسبب مختلف.
- **العلاج — وحدة واحدة لا ستّة إصلاحات:** `scripts/ci/generated_artifact_contract.py`. الكتابة والفحص يمرّان بدالّة الرسم **نفسها**، فلا يمكن أن يتباعد ما يُكتَب عمّا يُقارَن — وهو الفخّ الذي أوقع `capability_linker` سابقاً حين كُتِبت المصنوعة بترجمة أسطر وقُورنت بغيرها. والمقارنة **بالبايت** لا بالنصّ المُترجَم: `read_text` يُوحّد نهايات الأسطر فيُخفي إفساداً حقيقيّاً في CSV تنتهي أسطره بـCRLF.
- **مُكذَّب بإعادة المصادر الستّة إلى `bbfe121f`:** عاد العمى **١٣ من ١٦** بالضبط، وبعد الوصل **صفر من ١٦**. والاستعادة في كلّ قياس من نسخة **في الذاكرة** للملفّ الواحد المُفسَد — لا `git checkout`.
- **تكذيب فاشل أضاف اختباراً:** جعلتُ `enforce` تكتب بلا شرط (فيصير الفحص إصلاحاً) وبقيت ملفّة الاختبارات خضراء — فالخاصّيّة كانت مُدّعاة في التوثيق وغير محروسة. أُضيف `test_checking_never_repairs_what_it_is_checking`، وأربع تكذيبات تسقط الآن جميعاً.
- **قفل الانحدار:** `tests_v9/test_generated_artifact_contract.py` (‏`unit`، ١٦ فحصاً). **لا يُفسِد ملفّات مُلتزَمة**: إفسادها في كلّ تشغيل وحدات — محليّاً وفي CI — يترك الشجرة موسَّخة إن قُتِل التشغيل قبل الاستعادة (`finally` لا يُنقِذ من SIGKILL). بدلاً منه ثلاثة شروط قراءة صرفة مجموعها يُساوي ما قاسه الإفساد: `drift` ترصد بايتاً واحداً (على `tmp_path`) · كلّ حارس يُمرّر إلى `drift`/`enforce` نتيجة `artifacts(...)` الخاصّة به (مُتحقَّق **بشجرة AST** لا بـgrep، فلا يكفي أن يستورد العقد ثمّ يقارن غيره) · وعدد مصنوعات كلّ حارس مُعلَن كبيانات فلا يمرّ تضييق المجموعة سرّاً.
- **الأثر على الفجوة الجارة:** الستّة صارت قابلة للإغلاق في `VERIFY-ALL-GENERATED-WRITER-FLAG-MISMATCH-01` ووُصِلت بـ`_GENERATE_FLAG` بالشرط المُعلَن كاملاً (٩ ⇒ ٣).

## GENERATED-SWEEP-UNINDEXED-FILES-INVISIBLE-01 — FIXED_IN_CODE (2026-08-01)

- **العلّة:** المولّدات تمسح `git ls-files` (متعقَّب فقط — قرار #660 لمنع التقاط ملفّات محلّيّة غائبة عن checkout الـCI؛ مثال حيّ `scripts/ci/capability_mapping_engine.py:203`). فملفّ جديد لم يُضَف إلى الفهرس **لا يراه أيّ مولّد**، وتخرج المكنسة بصفر بينما CI يرصد الانحراف بعد الالتزام.
- **والقاعدة كانت مكتوبة ولا تُفرَض:** docstring المكنسة نفسه يقول «`git add` قبل التشغيل **ضرورة لا عادة**» ويشرح الآليّة بدقّة — ثمّ لا تفعل الأداة شيئاً. **قاعدة بلا إنفاذ ليست قاعدة**، وخضرتها تُقرأ تصديقاً لتشغيلٍ لم يرَ نصف المُدخَل.
- **الشاهد الحيّ (سبب التسجيل):** تشغيل CI رقم `30711928974` على `fe44832a` — سقط `test_mapping_has_no_drift` بـ`only-fresh=['tests_v9/test_generated_artifact_contract.py']`، ورسالة الالتزام نفسها تقول «the sweep converges in one cycle at EXIT=0». **الاثنان صحيحان**: المكنسة رأت شجرةً بلا ذلك الملفّ.
- **لماذا لم يسدّها `tree_state()`:** يستعمل `--untracked-files=no` **عمداً** — يقيس *تغيّر* المتعقَّب أثناء الفحص، لا *اكتمال المُدخَل* قبله. سؤالان مختلفان، وعلمٌ واحد لا يجيبهما؛ والخلط بينهما هو سبب بقاء الثغرة مفتوحة رغم أنّ الأداة تفحص حالة git أصلاً.
- **الإصلاح:** `unindexed_files()` + بوّابة **قبل كلّ قياس** في `main()` تُسمّي الملفّات وتخرج بـ`1`. الرسالة تقول العلاج (`git add -A`) والسبب، لا «فشل» مجرّد. والمُتجاهَل (`.gitignore`) مستثنى: لا يراه المولّد ولا يُفترَض أن يراه، فالإبلاغ عنه ضجيج.
- **الترتيب مقصود:** البوّابة أوّل ما يُنفَّذ بعد الاكتشاف، لأنّ كلّ ما يليها مبنيّ على مُدخَل يُفترَض اكتماله.
- **التكذيب:** إعادة `--untracked-files=no` ⇒ يسقط اختباران · تمرير المُتجاهَل عبر المرشِّح ⇒ يسقط اختبار الاستثناء. استُعيد الأصل ⇒ **٢٦ نجحت**.
- **الفحص سلوكيّ لا نصّيّ:** يُبنى مستودع git مؤقّت فعليّ ويُقاس عليه — الادّعاء أنّ الأداة **ترصد**، لا أنّها تذكر الكلمة. (الدرس المتكرّر هذه الجلسة: الحارس المصدريّ يقيّد الإملاء لا العقد.)

## GENERATED-SWEEP-CONTINUATION-BLIND-01 — FIXED_IN_CODE (2026-08-01)

- **العلّة:** `_STEP` مقصور على سطر واحد **عمداً** (`\s` كان يبتلع كتلة YAML كاملة ويُنتج «خطوة» وهميّة تمرّ خضراء بلا تنفيذ). لكنّ القصر **بلا طيّ متابعات السطر** جعل كلّ استدعاء مكتوب بشرطة مائلة عكسيّة خارج مدى الاكتشاف **تماماً** — لا مُصنَّفاً ولا مُبلَّغاً عنه ولا مُعاد توليده. **وما لا يُكتشَف لا يُصنَّف**، فلا يُنقذه أيّ حارس لاحق.
- **القياس على `d4549ef6`:** الاكتشاف **٥٩ ⇒ ٦٢**. الثلاثة الغائبة كلّها في `.github/workflows/platform-route-budget.yml`: `platform_route_ownership_guard` · `platform_route_budget_guard` · `platform_route_governance_attestation`.
- **ليست نظريّة:** هذه الثلاثة **عطّلت شريحة #751** فعليّاً — سقطت تسعة اختبارات في CI، وشُغِّلت يدويّاً لأنّ المكنسة أعلنت `EXIT=0` وهي منحرفة. **مكنسة خضراء ليست CI خضراء.**
- **الإصلاح:** طيّ `\` في نهاية السطر قبل المطابقة. لا يُعيد فتح ثغرة `\s`: سطر YAML بلا شرطة مائلة يبقى منفصلاً.
- **التكذيب:** إلغاء الطيّ ⇒ يسقط اختباران (`..._across_continuation_lines_is_discovered` و`..._attestation_runs_after_both_inventories...`).

## GENERATED-SWEEP-WRITE-FLAG-FAMILY-BLIND-01 — FIXED_IN_CODE (2026-08-01)

- **العلّة:** `_WRITE_FLAGS` كانت **قائمة مغلقة** تُفحَص بعضويّة تامّة (`flags & set(...)`)، فغابت عنها عائلة `--write-*` كاملةً. والنتيجة أنّ الحارس الوقائيّ الذي أضافه #750 — وهو صحيح في مبدئه — **أعلن نظافةً** بينما أربعة مولّدات خارج `_GENERATE_FLAG`.
- **التناقض كان داخل الملفّ الواحد:** `_WRITE_FLAG_DECL` (مسح المصدر) يطابق `--write-*` **بالبادئة**، فالماسح المصدريّ كان يراها والمُستجوِب عبر `--help` لا يراها. معياران متعارضان لسؤال واحد.
- **الأربعة:** `platform_route_ownership_guard` · `platform_route_budget_guard` · `platform_route_governance_attestation` (بـ`--write-generated`) · `platform_route_release_binding` (بـ`--write-source`).
- **الإصلاح:** `write_flags_of()` بالعائلة (`--write*` · `--generate*` · `--apply*` + `--fix` تحديداً). **البادئة مقصودة أوسع من التعداد:** خطؤها المحتمل «سمِّه في الأساس» كلفته سطر مُعلَّل، وخطأ التعداد «لا يُعاد توليده أبداً» كلفته انحراف صامت. والفحص لا يُصنَّف كتابةً (`--check-generated` لا يمرّ) وإلّا صار كلّ حارس «مولّداً».
- **ولم تُوصَل الأربعة بالثقة:** أُغلِق لكلٍّ منها الشرط المُعلَن في `generated_sweep_unmapped_generators.json` — أُفسِدت مصنوعته ⇒ `--check` رصد (خرج `1`)، ثمّ شُغِّل العلم ⇒ `--check` عاد `0` **والملفّ استُعيد بايتاً بايت**. أربعة من أربعة أغلقت.
- **وعيب ترتيب ثالث انكشف بالوصل:** `attestation` يستدعي جرد الملكيّة ويقرأ جرد الميزانيّة، والأبجديّة كانت ترتّبه `budget → attestation → ownership` — أي **قبل أحد مصدرَيه**، فيبقى بائتاً **بلا خطأ خاصّ به**. صار صريحاً في `_ORDER_TIER` بدل الاتّكال على أنّ دورة `--fix` ثانية ستُصحّحه مصادفةً.
- **التكذيب — ثلاثة أقفال، كلٌّ على حدة:** إعادة التعداد المغلق ⇒ يسقط اختبار العائلة وحده · إلغاء الطيّ ⇒ يسقطان · حذف طبقة الترتيب ⇒ يسقط اختبار الترتيب وحده. استُعيد الأصل ⇒ **٢٤ نجحت**.
- **الفرق عن فجوتَي #750:** تلك عن `--check` يقارن **بعض** مخرجاته، وعن خلط مجموعتَي `uncovered()` و`unreferenced_generators()`. وهذه ثالثة مستقلّة: **معيار التعرّف على علم الكتابة نفسه**.

## GENERATED-WRITE-ONLY-GENERATORS-UNCLASSIFIED-01 — CLOSED (2026-08-20) — كانت OPEN / كامنة منذ 2026-08-01

- **المصدر:** `scripts/ci/verify_all_generated.py` — كتلة الإبلاغ عن `unreferenced_generators()`؛ ونصّها السابق كان يُعلن أنّ كلّ عضو «مُصنَّف في الأساس» ويحيل إلى `classify_uncovered` كفارضٍ له.
- **العلّة:** المجموعتان ليستا واحدة. `uncovered()` يجمع من يُعلن `--check`، و`unreferenced_generators()` يجمع من يُعلن علم كتابة. فمولّد بلا وضع فحص إطلاقاً لا يقع تحت أيّ فرض — ولا يستطيع الإبلاغ عن انحرافه أصلاً. وقد قيس سابقاً أنّ **واحداً من أربعة** كان مُصنَّفاً فعلاً والثلاثة الباقية في لا شيء، بينما تُطبَع الأربعة بوصفها مُصنَّفة.
- **العلاج في هذه الشريحة:** التصنيف صار يُشتَقّ من `generated_chain_known_drift.json` وقت الطباعة بدل أن يُدَّعى، والمجهول يُسمّى مجهولاً باسمه.
- **الحالة:** OPEN وكامنة. `unreferenced_generators()` تُرجِع **صفراً** على `fde6f955`، فالكتلة لا تُطبَع اليوم ولا يُوجد فرض عليها. التصحيح عبارةٌ صادقة تنتظر أوّل مولّد كتابة يدخل الشجرة بلا ذكر في أيّ workflow.
- **شرط الإغلاق:** إمّا فرض تصنيف صريح على هذه المجموعة كما يُفرَض على معلني `--check`، وإمّا إثبات أنّ المجموعة لا يمكن أن تنمو (وهو ما لا يسنده شيء اليوم).


## CANONICAL-FIELD-STATE-ELIGIBILITY-IS-PRESENCE-ONLY-01 — مُغلقة جزئيّاً (2026-08-01)

- **المصدر:** `services/sahool-platform/core/canonical_field_state.py` — كان الحكم التشغيليّ كلّه `operational_eligible = not missing_required`، أي **سؤال الوجود وحده**.
- **العلّة، مُثبَتة بالتشغيل لا بالقراءة:** منتَج حاضر بمخطّط صحيح يُعلن مالكه أنّه `degraded` كان يُبقي `operational_eligible=True` — فتبدو الحالة صالحة لتوصية تنفيذيّة بينما مالك البيانات نفسه يقول إنّها ليست كذلك. «موجود» و«صالح» ليسا سؤالاً واحداً.
- **ما لم يُغيَّر عمداً:** `operational_eligible` باقٍ بمعناه حرفيّاً. له مستهلكون قائمون (`core/field_digital_twin.py:71` وغيره)، وتشديد معناه تحتهم صامتاً أخطر من نقصه. **مُقاس:** البصمات والحقول السابقة كلّها متطابقة قبل/بعد على أربع حالات (‏`state_digest` · `operational_eligible` · `limitations` · `availability`).
- **العلاج (إضافيّ):** حقل `eligibility` بسُلَّم رتيب — `discover` · `diagnose` · `propose` · `execute` — كلّ مستوى بـ`allowed` وأسبابه. الرتابة مفروضة باختبار: ما يمنع مستوى أدنى يمنع كلّ ما فوقه، وإلّا فهي أربعة أحكام لا سُلَّم.
- **الحدّ الحاكم:** المُجمِّع يحكم على **الإعلانات** لا على الوقائع، ولا يخترع عتبات حداثة. المالك يعرف متى يبيت رصده ويقوله في منتَجه (`quality_status` · `operational_eligible` · `limitations`)؛ وحساب العمر هنا بعتبة محلّيّة كان سيفرّع منطق المالك إلى نسخة ثانية تتباعد صامتاً — وهو ما يُحرّمه عقد الوحدة المكتوب أصلاً («never computes weather, water, soil or spectral facts»).
- **مفردات الجودة غير موحَّدة — مقيس:** `canonical_weather_state` يُخرِج validated/degraded/insufficient/invalid، و`canonical_water_state` يُخرِج verified/degraded. فالمقبول اتّحاد المصطلحين الصحّيّين، و**المجهول يُعامَل غير مُثبَت لا سليماً**: قائمة سوداء كانت ستُمرّر أيّ مصطلح جديد من مالك جديد بلا قراءة.
- **`execute` ممنوع دائماً من هذه البنية:** التنفيذ نوع آخر من الإذن لا درجة أعلى من الاقتراح. الحالة لا تحمل إذناً ولا توقيعاً ولا هويّة مُوافِق، فتُعلن أنّها لا تملك الجواب بدل أن تُجيب `true` من مُدخَلات لا تخصّ الإذن.
- **`eligibility` خارج الجسم المُبصَم:** البصمة تُعرِّف المُدخَلات لا الحكم عليها؛ إدخالها كان سيُغيّر بصمة كلّ حالة قائمة بلا تغيّر مُدخَل واحد ويكسر كلّ ما رُبِط ببصمة مُخزَّنة.
- **مُكذَّب أربعاً، وكلّ قفل على حدة:** تحويل فحص الجودة إلى قائمة سوداء ⇒ يسقط اختبار المفردة المجهولة · اعتبار الصمت سلامةً ⇒ يسقط اختبار الجودة غير المُعلَنة · جعل `execute` يتبع `propose` ⇒ يسقط اختبار الإذن · إسقاط الصحّة من `propose` ⇒ تسقط خمسة.
- **حدّ صدق:** هذا يُغلق **مستوى الإعلانات**. ولا يُغلق: ربط المستأجر/الحقل، نسخة الهندسة، المواءمة الزمنيّة بين المنتَجات، ولا الطابع الزمنيّ المستقبليّ — لأنّ أيّاً منها يحتاج حقولاً لا تحملها البنية اليوم أو حكماً يخصّ المالك. تبقى مفتوحة بأسمائها، ولا يُدَّعى أنّ P0-3 أُغلقت كاملةً.

## RUNTIME-CONTRACT-INDIRECT-ENV-01 — ✅ FIXED (2026-08-01، PR #754)

- **المصدر:** `scripts/ci/runtime_contract_generator.py:42` (`ENV_CALL_RE`) · الحادثة في `services/raster-service/cdse_client.py:127,157` · البرهان: `--check` يمرّ على شجرة `fde6f955` بينما `grep -c CDSE_CLOUD_POLICY runtime-contracts/generated/runtime_contracts.json` = **0**.
- **العلّة:** النمط يلتقط اسم المتغيّر **نصّاً حرفيّاً داخل النداء** فقط. فـ`os.getenv(_CLOUD_POLICY_ENV, "strict")` — حيث `_CLOUD_POLICY_ENV = "CDSE_CLOUD_POLICY"` — غير مرئيّ تماماً. والأخطر أنّ البوّابة **تمرّ**: الصمت يُقرأ «لا متغيّر هنا» وهو يعني «لم أنظر». بوّابة اكتمال تُبلِغ باكتمال لا تملكه.
- **السعة المقيسة — ١٣ متغيّراً عبر ٥ خدمات، لا واحد:** `auth` (`MFA_SECRET_ENCRYPTION_KEY` · `MFA_SECRET_DECRYPTION_KEYS` — **سرّان** لم تكن الحوكمة تراهما) · `decision-service` (`DECISION_WORKER_ASSERTION_KEY`) · `raster-service` (`CDSE_CLOUD_POLICY`) · `edge-inference` (`PEST_MODEL_PATH` · `YIELD_MODEL_PATH`) · `sahool-platform` (`APPLY_NDVI_THRESHOLDS` + خمس رايات `FEATURE_*`).
- **العلاج:** `resolve_indirect_env` — حلٌّ بخطوة واحدة داخل الملفّ نفسه: معرّف مجرّد يُمرَّر إلى القراءة يُبحَث عنه في ارتباطات `NAME = "ENV_VAR"` للوحدة. ما لا يُحلّ يُسقَط ولا يُخمَّن؛ وثابت لا يُمرَّر إلى قراءة لا يُقبَل.
- **درس التكذيب (مُسجَّل لأنّه فشل أوّلاً):** أوّل محاولة تكذيب **نجحت خضراء** — فصلُ الحلّ عن مسار المسح لم يُسقِط اختباراً، لأنّ اختبار الأثر يقرأ ملفّاً مُولَّداً سلفاً واختبار الدالّة يستدعيها مباشرة، فلا أحد يمرّ بالمسح. أي أنّ الاختبار كان سيسمح بعودة العطل بشكله الأصليّ: قدرة موجودة لا تجري. فأُنشئ مَفصِل واحد (`extract_env_names`) يقرأ منه المسح ويُمسَك منه الاختبار.
- **الحالة:** FIXED في الكود ومُثبَت على مستوى الوحدة والمصنوعة (`tests_v9/test_runtime_contract_indirect_env.py`، ٩ اختبارات). **حدّ صدق:** لا برهان تشغيليّ حيّ بأنّ الثلاثة عشر تُقرأ في بيئة منشورة.

## IMAGERY-SCAN-SERIAL-WAIT-01 — ✅ FIXED (2026-08-01، PR #754)

- **المصدر:** `services/sahool-platform/api/imagery_automation.py` `scan_all` (المرور التسلسليّ) + `_await_batch_terminal` (الانتظار المُضاف في #749) + `load_from_db` (جلب بلا `LIMIT`) · الكادينس في `api/scheduler.py:214` (86400ث) · غياب المهلة في `scheduler.py:122`.
- **العلّة:** المرور التسلسليّ كان مقبولاً حين كان العمل لكلّ حقل نداءً أو نداءين. بعد `SPECTRAL-COLLECTOR-ASYNC-RACE-01` صار كلّ حقل بصورة جديدة ينتظر دفعته حتّى `IMAGERY_BATCH_WAIT_BUDGET_S` (١٢٠ث افتراضاً)، و`load_from_db` يجلب حقول كلّ المستأجرين بلا حدّ ⇒ أسوأ حالة للدورة = عدد الحقول × الميزانيّة.
- **حجم الادّعاء بدقّة:** الجدولة **لا** تضع مهلة على المهمّة (تنتظر انتهاءها ثمّ تنام)، فالأثر **انزياح دورة** لا تداخل ولا تعليق؛ و١٢٠ث سقفٌ لا يُبلَغ إلّا عند مهلة لا كلفة لكلّ حقل. النموّ الخطّيّ بعدد الحقول حقيقيّ، والمنصّة المتوقّفة ليست كذلك — ولا يُدَّعى ذلك.
- **العلاج:** نفس علاج `GAP-B1-ALLFIELDS-SEQ` — `asyncio.gather` تحت `Semaphore` (`IMAGERY_SCAN_CONCURRENCY`، افتراض ٨، أرضيّة ١ لأنّ صفراً يعني سيمافوراً لا يُفتَح أبداً). زمن الجدار = أبطأ حقل لا مجموعها.
- **ما كان التزامن قد يكسره ولم يكسره:** عزل فشل الحقل · **الحتميّة** (`gather` يُرجِع بترتيب الدخل، فـ`errors[:10]` ليست عيّنة عشوائيّة من الفشل) · حوض القاعدة (أربعة مواضع `acquire` متتابعة داخل الحقل، غير متداخلة) · حارس الكادينس الذي يبقى تسلسليّاً قبل التوزيع.
- **عيب فرعيّ أُصلِح معه:** `return_exceptions=True` يلتقط `BaseException`، فكان الإلغاء يُسجَّل «فشل فحص N حقلاً» وتمضي الكنسة إلى نهايتها بدل أن تنتهي — ابتلاعُ إشارة تحكّم وإعادة تسميتها عطلاً، وهو نمط `SILENT-EXCEPTION-HANDLERS-11-01` نفسه. صار `CancelledError` يُعاد رميه.
- **الحالة:** FIXED في الكود (`tests_v9/test_imagery_scan_bounded_concurrency.py`، ٩ اختبارات). التكذيب سلوكيّ لا شكليّ: ذروة التوازي **مقيسة أثناء تنفيذ حقيقيّ** لا مُستنتَجة بالبحث عن `gather` في المصدر — فحصٌ كهذا يمرّ على كود يستدعيها ويتسلسل. **حدّ صدق:** لا قياس إنتاجيّ لزمن الدورة قبل/بعد.

## RUNTIME-CONTRACT-KEY-SUFFIX-NOT-SECRET-01 — ✅ FIXED (2026-08-01، بأمر المالك)

- **المصدر:** `scripts/ci/runtime_contract_generator.py` — `SECRET_MARKERS` تُفحَص **كسلاسل جزئيّة**، فيلزم الاسمَ أن يحوي `PRIVATE_KEY`/`API_KEY`/`ACCESS_KEY`. واللاحقة المجرّدة `..._KEY` لا تطابق أيّاً منها.
- **العلّة والأثر المقيس:** **عشرة** مفاتيح توقيع وHMAC نُشِرت بوصفها تهيئة عاديّة: `FCM_SERVER_KEY` · `SEASON_EDGE_HMAC_KEY` · `FIELD_FORMS_SYNC_HMAC_KEY` · `MFA_AUDIT_HASH_KEY` · `ACTIVATION_EVIDENCE_SIGNING_KEY` · `ACTIVATION_PROBE_SIGNING_KEY` · `DECISION_WORKER_ASSERTION_KEY(+_PREVIOUS)` · `FIELD_SERVICE_TENANT_ASSERTION_KEY(+_PREVIOUS)`. عقدٌ يذكر مفتاح توقيع بجوار مستوى السجلّ **يُبلِّغ سطح الأسرار أصغر ممّا هو** — وهذا نوع العطل نفسه الذي عالجته `RUNTIME-CONTRACT-INDIRECT-ENV-01`: بوّابة تصف الواقع وصفاً ناقصاً وهي خضراء.
- **العلاج — قاعدة لا تعديل قائمة:** اللاحقة `_KEY`/`_KEYS` تعني مادّة مفتاح ⇒ **سرّ، مُغلَقاً عند الفشل**؛ والاستثناء إعلانٌ صريح في `docs/architecture/runtime_contract_nonsecret_keys.json` يحمل كلٌّ منه **سطر المصدر المقروء**. وتعذُّر قراءة الإعلان يجعل الجميع أسراراً — الفشل يقع في الجهة الآمنة من السؤال.
- **ولماذا ليست نمطاً أذكى:** `MFA_ALLOW_DERIVED_KEY` و`MFA_AUDIT_HASH_KEY` يفترقان بكلمة واحدة في الخدمة نفسها، والأوّل **راية منطقيّة** لا مفتاح (`mfa_crypto.py:119` يقرأه كنصّ صدق). ونمطٌ يفصل بينهما يكون مُفصَّلاً على ثلاثة عشر اسماً معروفاً — قائمةً في ثوب نمط، تنهار عند الرابع عشر.
- **ثلاثة إعفاءات مقيسة بقراءة مستهلكيها:** `JWT_PUBLIC_KEY` (النصف العامّ لزوج غير متماثل — `actuator_runtime.py:443`؛ وعدّه سرّاً **تضخيم كاذب** للسطح) · `MFA_ALLOW_DERIVED_KEY` (راية) · `STAGING_PROBE_IDEMPOTENCY_KEY` (معرّف إلغاء تكرار بقيمة افتراضيّة **صريحة في المصدر** — `staging_probe.py:238`؛ وهو ما لا يفعله سرّ).
- **تصويب عدّ:** قِيلت «٢٤ متغيّراً» سابقاً وهي أزواج (خدمة × متغيّر)؛ العدد الصحيح **١٣ متغيّراً متمايزاً**، أُعيد تصنيف **١٠**.
- **الحالة:** FIXED (`tests_v9/test_runtime_contract_key_classification.py`، ٣٠ اختباراً). **التكذيب مزدوج:** حذف قاعدة اللاحقة ⇒ ١٢ تسقط · تجاهل الإعفاءات ⇒ ٣ تسقط. **ودرس مُعاد:** أوّل صياغة للاختبار قرأت الأثر المُولَّد فبقيت خضراء والإعفاءات مُعطَّلة كلّيّاً — نفس عمى التكذيب المُسجَّل في `RUNTIME-CONTRACT-INDIRECT-ENV-01`، وقعتُ فيه مرّتين في جلسة واحدة. الاختبار الآن يؤكّد على `is_secret` مباشرةً **وعلى** الأثر.

## TEXT-DECODED-WITH-THE-MACHINES-LOCALE-01 — مُغلقة النموّ / الدَّين مُجمَّد (baseline **184** بعد تصحيح الدقّة أدناه، كان 188، 2026-08-01)

- **المصدر:** تقرير فحص خارجيّ على Windows أبلغ عن **١٢ فشلاً** وصنّفها «بيئة Windows — لا فشل منطقيّ في الكود».
- **لماذا لم يُصدَّق التصنيف ولم يُرفَض:** أُعيد إنتاج العطل **على Linux** بفرض لغة C (`LC_ALL=C PYTHONUTF8=0` ⇒ الترميز الافتراضيّ ANSI_X3.4-1968) فظهرت **١٢ بالضبط**، كلّها Unicode. فالعطل ليس خاصّيّة Windows بل **اعتماد الشيفرة على ترميز الآلة**؛ وWindows يكشفه فقط لأنّ افتراضيّه ليس UTF-8.
- **ولماذا الفرق ليس لفظيّاً:** «عطل بيئة» يُغلَق بتغيير الجهاز ويبقى الكود كما هو؛ و«اعتماد على ترميز الآلة» عيبٌ في الكود يُغلَق بإصلاحه. التصنيف الأوّل كان سيجعل CI الأخضر شهادةً على أنّ Linux افتراضيّه UTF-8 لا على أنّ الحارس يقرأ ما يدّعي قراءته.
- **ثلاثة متّجهات لا واحد — وهذا تصحيح للتقرير:** ① قراءة مباشرة `read_text()`/`open()` بلا `encoding`. ② `subprocess.run(..., text=True)` — **الأب** يفكّ مخرَج الابن بترميز اللغة. ③ **مخرَج الابن نفسه**: `encoding` على الأب لا يُملي على الابن بماذا يكتب، فرسالة تحوي عربيّة أو «—» تُسقِط الابن بـ`UnicodeEncodeError`؛ يُغلَق بـ`PYTHONIOENCODING=utf-8` في بيئته. العلاج الذي وصفه التقرير (إضافة `encoding` إلى القراءات) يُغلق **٨ من ١٢** لا ١٢ — مقيس لا مُقدَّر: بعد تطبيقه وحده بقيت أربعة.
- **القياس:** ١٢ ⇒ **٠** تحت لغة C (`EXIT=0`، 3895 نجحت). ثمانية ملفّات أُثبِت انهيارها وأُصلِحت، لكلٍّ منها فشلٌ قبل ونجاحٌ بعد **تحت نفس اللغة**.
- **الإنفاذ:** `tests_v9/test_text_encoding_locale.py` (`unit`) + `docs/architecture/text_encoding_locale_baseline.json` — ١٨٨ ملفّاً، يتقلّص ولا ينمو، وبإنفاذ عكسيّ (مدخل بائت يُسقِط الاختبار كعقد #735). والماسح يرى متّجه العمليّات لا القراءات وحدها — مُثبَت بفحص مباشر، لأنّ فحصاً يبحث عن `open(` وحده كان سيُخفي ثلث الفشل.
- **مُكذَّب:** إعادة ملفّ واحد من الثمانية إلى قراءة بلا ترميز ⇒ يسقط اختباران يسمّيانه؛ والاستعادة تُعيد الأخضر.
- **حدّ صدق:** الأساس **يمنع النموّ ولا يدّعي أنّ ما فيه سليم**. المُدرَجون لم يُثبَت انهيارهم؛ يقرؤون ASCII اليوم — وهو حظّ لا تصميم، فتوثيق هذا المستودع عربيّ، وأوّل حرف عربيّ يدخل ملفّاً مقروءاً يحوّل المدخل إلى عطل. وهذا لا يُغلق أيّاً من فجوات التقرير الأربع عشرة الأخرى: كلّها تحتاج stack حيّاً ولا تُغلَق بإصلاح ترميز.

- **تصحيح دقّة أمسك به فحصٌ خارجيّ لا أنا (١٨٨ ⇒ ١٨٤):** ماسحي الأوّل أدرج أربعة ملفّات دَيناً وهي نظيفة — قرأ وسيط الوضع من الموضع الثاني دائماً، وموضعه في `path.open("rb")` **الأوّل**، فحُسِب كلّ فتح ثنائيّ على كائن مسار عيباً؛ وأدرج `read_text(path)` كاسم عارٍ وهي دالّة محلّيّة لا طريقة مسار. أساسٌ يُبالغ في الدَّين يُدرَّب قارئه على تجاهله — وهو عطل الحارس الأكثر شيوعاً. الشكلان مُقفَلان الآن باختبار صريح.
- **حدّ صدق:** الأساس **يمنع النموّ ولا يدّعي أنّ ما فيه سليم**. المُدرَجون لم يُثبَت انهيارهم؛ يقرؤون ASCII اليوم — وهو حظّ لا تصميم، فتوثيق هذا المستودع عربيّ، وأوّل حرف عربيّ يدخل ملفّاً مقروءاً يحوّل المدخل إلى عطل. وهذا لا يُغلق أيّاً من فجوات التقرير الأربع عشرة الأخرى: كلّها تحتاج stack حيّاً ولا تُغلَق بإصلاح ترميز.
## CONFLICT-MARKER-GUARD-SKIPS-MARKDOWN-01 — مُغلقة (2026-08-01)

- **المصدر:** حادثة حقيقيّة لا استقصاء. دفعةٌ متزامنة على `claude/project-exploration-dtjw3p` (`e20a0ccd`) حملت سطر `=======` عارياً داخل `sahool-brain/log.md`، بقيّةً من حلّ تعارض. اكتُشِف عند مقارنة نسختي بنسختها قبل الدفع، لا بحارس.
- **العلّة — الحارسان معاً عميان عن نفس الصنف، ولسببين مختلفين:** `scripts/ci/conflict_marker_guard.sh` نمطه يطابق `=======$` لكنّ **pathspec** عنده لا يذكر `*.md` إطلاقاً؛ و`no_merge_conflict_markers_guard.py` **يتجاهل `=======` وحدها عمداً** لأنّها مسطرة setext شرعيّة. فالنتيجة أنّ صنف الملفّات **الأكثر تعارضاً في هذا المستودع** هو الصنف الوحيد بلا فحص.
- **ولماذا هي الأكثر تعارضاً:** `sahool-brain/*.md` ملفّات **ملحقة**؛ كلّ جانب يُضيف مدخلاً مختلفاً، فتتعارض في **كلّ** إعادة تأسيس. أربع إعادات تأسيس في هذه الجلسة وحدها تعارضت عليها كلّها.
- **والضرر صامت لا صاخب:** `=======` في Markdown يُحوّل **السطر الذي فوقه** إلى عنوان H1. فبند قائمة يصير عنواناً، والملفّ يبدو سليماً في `git diff` ويُقرأ خطأً في العرض.
- **مقيس قبل التوسيع لا مُفترَض:** صفر ملفّ متعقَّب من `*.md`/`*.txt`/`*.toml`/`*.cfg`/`*.ini` يحوي سطراً يطابق النمط اليوم — فالتوسيع لا يُنتج إنذاراً كاذباً واحداً.
- **مُكذَّب بالحادثة نفسها:** أُعيد إدراج السطر عينه في `log.md` ⇒ الحارس يخرج بـ**1** ويسمّي `sahool-brain/log.md:4721`؛ والـpathspec القديم على نفس الشجرة يخرج بـ«لم أجد شيئاً». فالإصلاح هو الـpathspec لا النمط.
- **حدّ صدق:** هذا يمنع **الالتزام** بالعلامة ولا يمنع نشوءها. سببها الجذريّ أنّ حلّ التعارض الآليّ «أبقِ الجانبين» صحيحٌ للمداخل المختلفة وخاطئٌ حين يكون أحد الجانبين نسخةً أقدم من المدخل نفسه — وهو ما أفسد `hot.md` في الجولة السابقة أيضاً (ختم مكرّر + ثلاث علامات «الأحدث»). الحلّ الآليّ يبقى بحاجة فحصٍ بعده، وهذا الحارس هو ذلك الفحص.

### أُعيد فتحها (2026-08-07، #804) ثمّ أُغلقت في الحارس الباقي

- **كيف انفتحت:** `#804` حذف `scripts/ci/conflict_marker_guard.sh` بدعوى أنّه مكرَّر لـ`no_merge_conflict_markers_guard.py`. **والدعوى مُكذَّبة بزرعة:** `=======` مجرَّداً في `sahool-brain/log.md` ⇒ البايثونيّ `exit=0` والباش `exit=1`. أي أنّ المحذوف كان **الكاشف الوحيد** للصنف، والإغلاق أعلاه كان يعتمد عليه وحده.
- **والـPR يحمل تكذيب متنه:** حذف السطر وأبقى التعليق فوقه — «٢) حارسا تعارض الدمج — **لا يغني أحدهما عن الآخر**».
- **الإغلاق الآن في `no_merge_conflict_markers_guard.py` نفسه** — لا بإحياء المحذوف: `_MARKER` صار `^((<{7}|>{7}) |={7}$)`.
- **وتصحيح ادّعاء في عقد الحارس:** docstring‏ه كان يقول إنّ «وجود إحدى علامتَي السهم كافٍ، فالثلاث تظهر معاً دائماً». **يسقط عند الحلّ الجزئيّ** — من يحذف السهمين ويُبقي الوسطى يترك `=======` وحدها، وهو ما وقع فعلاً. واختباره كان يُثبّت الفجوة عقداً: `assert not _MARKER.match("=" * 7)`.
- **مقيس قبل التوسيع لا مُفترَض:** `^={7}$` ⇒ **صفر** سطر في الشجرة المتعقَّبة · و**٢٢٩** ملفّاً يحمل مسطرة `^={20,}$` تبقى كلّها خارج النطاق. الدقّة على **سبع بالضبط** (صيغة git حرفيّاً) هي ما يمنع الإيجابيّ الكاذب.
- **مُكذَّب في الاتّجاهين:** إعادة النمط إلى السهمين وحدهما ⇒ يسقط اختباران (النمط + `scan()` طرفاً لطرف على `log.md` حقيقيّ)؛ وفحص المساطر (٨/٢٠/٤٠/٧٩) يبقى أخضر تحت الزرعة — فالحدّ لم يُفقَد.
- **حدّ صدق:** يبقى الحدّ الأصليّ قائماً (يمنع الالتزام لا النشوء). ويُضاف: الصنف الآن محروس بحارسٍ **واحد** بعد أن كان اثنين — فسقوطه يعني عودة العمى، ولذلك صار له اختبار يُشغّل `scan()` لا يقرأ النمط.

## BRAIN-TRANSITION-GUARD-MATCHES-FAIL-CLOSED-01 — ✅ FIXED (2026-08-01، كشفه فشل CI على #760)

- **المصدر:** `scripts/ci/brain_state_transition_guard.py` — `CLOSED_RE` كان `^\+[^+].*\b(CLOSED|VERIFIED|RUNTIME_VERIFIED|PRODUCTION_CERTIFIED)\b` بـ`re.I`.
- **كيف انكشف:** حجب شريحة بروتوكول دماغ **لا تدّعي إغلاقاً** — لأنّ سطراً فيها يشرح *لماذا* قاعدة تصنيف المفاتيح `fail-closed`. أي أنّ العطل ما كان ليظهر إلّا في شريحة دماغيّة بحتة تكتب المصطلح.
- **العلّة — خطأ في الاتّجاهين، وكلّ واحد يُخفي الآخر:**
  - **إيجابيّة كاذبة:** الشرطة حدُّ كلمة، فـ`\bclosed\b` يطابق داخل `fail-closed` و`open-closed`. والمصطلح يظهر **٢٧٣ مرّة في `sahool-brain/` وحده** و**٤٧٧ ملفّاً** في المستودع. حجبٌ صحيح **بسبب كاذب**، وهو أسوأ من عدم الحجب: الرسالة تُرسِل القارئ يبحث عن ادّعاء لم يُكتَب.
  - **سلبيّة كاذبة:** `CLOSED_IN_CODE` و`CLOSED_IN_CODE_AND_PG_PROVEN` — **مفردة الإغلاق الفعليّة في هذا السجلّ** — كانت تمرّ من أمامه، لأنّ `\b` يسقط على `_` اللاحقة. أي أنّ الادّعاءات التي وُجِد الحارس لأجلها لم تكن تُلتقَط.
- **العلاج:** نظرة خلفيّة سالبة ترفض شرطةً أو حرف كلمة قبله (تقتل `fail-closed`)، وذيل `_UPPER` اختياريّ يقبل مفردة الحالة الحقيقيّة، ونظرة أماميّة تمنع `closedness`.
- **الحالة:** FIXED (`tests_v9/test_brain_transition_guard_vocabulary.py`، ١٦ اختباراً). **التكذيب:** إعادة النمط القديم ⇒ **٩ تسقط**. وستّة منها تُثبّت أنّ الإصلاح **لا يُضعِف** الحارس: الادّعاء الحقيقيّ بلا كود تنفيذيّ يبقى محجوباً، والادّعاء مع كود يمرّ.
- **النمط المتكرّر:** ثالث حارس في هذه الجلسة يُبلِّغ نتيجةً عن سؤال لم يطرحه — بعد `RUNTIME-CONTRACT-INDIRECT-ENV-01` و`RUNTIME-CONTRACT-KEY-SUFFIX-NOT-SECRET-01`.

## MERGE-RESOLUTION-BY-HAND-LOSES-WORK-01 — ✅ FIXED (2026-08-02)

- **المصدر:** حادثة في هذه الجلسة، لا استقصاء. حُلَّت أربعة ملفّات إلحاقيّة (`sahool-brain/*.md`) يدويّاً حلّاً **صحيحاً**، ثمّ مرّت حلقة `git checkout --theirs` على «المتبقّي» من `git diff --name-only --diff-filter=U` — والملفّات المحلولة لم تكن مُفهرَسة بعد، فبقيت في تلك القائمة **فدهست الحلقة على الحلّ كلّه**.
- **الضائع بالعدّ:** مدخلا سجلّ · تصحيح سطر كاذب · قرار دفتر · ختم لقطة · مدخل فجوة. **خمس قطع عمل.**
- **ولماذا هو أخطر من عطل عاديّ:** لم يُبلِّغ عنه شيء. `git` أعلن دمجاً نظيفاً، والشجرة اتّسقت، والفحوص خضراء — لأنّ المحذوف **مدخلات سجلّ** لا كود، ولا حارس يقيس أنّ سجلّاً إلحاقيّاً لم ينقص. أمسكه `brain_commit_claim_guard` **مصادفةً**: رسالة الالتزام ذكرت معرّف فجوة لم يعد موجوداً في السجلّ بعد الدهس.
- **العلّة الحقيقيّة — ليست جهلاً بالقاعدة:** القواعد الثلاث (إلحاقيّ ⇒ أبقِ الاثنين · مولَّد ⇒ خُذ main وأعِد التوليد · مصدر ⇒ توقّف) كانت معروفة ومكتوبة و**مُطبَّقة يدويّاً خمس مرّات في الجلسة نفسها**، ثمّ نُقِضت في السادسة. فالعطل في **ترتيب العمليّات** لا في المعرفة: الفجوة الزمنيّة بين «حُلَّ» و«فُهرِس» هي النافذة التي وقع فيها الإتلاف.
- **العلاج:** `scripts/ci/resolve_merge_conflicts.py` — يُصنّف ثمّ يُعالج، و**يُفهرِس داخل نفس تكرار الحلّ** لا بعده. والمصدر يُوقِف السكربت قبل أيّ كتابة (لا قاعدة آليّة تصلح لدمج كود).
- **عيبٌ ثانٍ أُمسِك أثناء البناء لا بعده:** أيّ الجانبين هو `main` **ليس ثابتاً** — في `merge` هو `--theirs` وفي `rebase` ينقلب إلى `--ours` لأنّ HEAD أثناء الإعادة هو المُنبَع. سكربت يُثبّت جانباً يكون صحيحاً في عمليّة وخاطئاً في الأخرى **بلا إبلاغ**؛ فالجانب يُقرأ من العمليّة الجارية، وما لا يُعرَف يُوقِف السكربت.
- **الحالة:** FIXED (`tests_v9/test_resolve_merge_conflicts.py`، ٢٩ اختباراً). **التكذيب بخمس طفرات، كلٌّ تُسقِط اختباراً يسمّيها:** تأجيل الفهرسة ⇒ ١ · تثبيت `--theirs` ⇒ ١ · نزع توقّف المصدر ⇒ ١ · أخذ جانب واحد ⇒ ٥ · نزع حارس «لا عمليّة جارية» ⇒ ١.
- **ودرسٌ ثالث في نفس الجلسة عن عمى التكذيب:** أوّل صياغة لاختبار الخاصّيّة المحوريّة **مرّت خضراء تحت الطفرة**. كانت تُشغّل كنسة `--theirs` **بعد** عودة الدالّة — وعندها يكون كلّ شيء مُفهرَساً في الحالتين، فهي تقيس «هل انتهت الدالّة بفهرسة» لا «هل يبقى ملفّ محلول عارياً لحظةً». والخطر يقع **بين** الحلّ والفهرسة، فصار الاختبار يقطع الحلّ في منتصف الدفعة ويسأل عمّا حلّ بما سبق.
- **حدّ صدق:** السكربت **يُتاح ولا يُفرَض** — لا حارس يمنع حلّاً يدويّاً، ولا شيء يقيس أنّ سجلّاً إلحاقيّاً لم ينقص عبر دمج. أي أنّ هذا يُزيل سبب الحادثة ولا يُغلق صنفها.

## CLAIMS-WITHOUT-A-MEASURED-BASE-01 — ✅ FIXED جزئيّاً (2026-08-02)

- **المصدر:** `docs/architecture/` — ٢٢ مصنوعة مُعلَنة، **٤** منها تحمل `measured_on` و**٤** تحمل `adjudicated_on`، اختارها كاتبوها كلٌّ على حدة **بلا قاعدة تسمّيهما**. المفردتان موجودتان في المستودع ولم تُعرَّفا قطّ.
- **العلّة — الصنفان يُخلطان لا الختم يُنسى:** القياس عددٌ أو مجموعة يشتقّها ماسحٌ من شجرةٍ في لحظة، فيَبيت حين تتحرّك الشجرة تحته. والقرار حكمٌ اتّخذه إنسان، لا يَبيت بحركة الشجرة بل بتغيّر أسبابه. ورقمٌ مقيس يُقرأ عقداً **لا يُعاد قياسه أبداً** — يبقى منشوراً بوصفه واقعاً بلا أحد يعرف متى كان صحيحاً.
- **الدليل حيّ لا افتراضيّ:** `platform_extraction_map.json` يقول `baseline_route_count = 633` بينما قائمة `routes` **في الملفّ نفسه** تعدّ **635**. القياس انحرف عن القائمة التي يعدّها بمقدار ٢، ولم يرصده شيء — لأنّ **لا حارس ولا اختبار ولا workflow يقرأ ذلك الحقل إطلاقاً** (مقيس بالبحث في `scripts/` و`tests_v9/` و`.github/`: صفر نتيجة). رقمٌ بلا أساس وبلا قارئ.
- **وختمان لا يُحلّان محلّ بعضهما:** `measured_on` يقول «على أيّ شجرةٍ قِسته»، و`adjudicated_on` يقول «متى حكمتُ فيه». قبولُ أحدهما مكان الآخر يُعيد إنتاج العطل بصياغة أخرى — فيُحجَبان منفصلين، ومُثبَت بطفرتين متقابلتين.
- **العلاج:** `docs/architecture/claim_base_registry.json` (تصنيف صريح لكلّ مصنوعة) + `scripts/ci/claim_base_guard.py` في وظيفة *Lint & Static Analysis*.
- **ما يُحجَب وما يُبلَّغ، والفرق مقصود:** يُحجَب **غياب الأساس** (ملفّ غير مصنَّف · قياس بلا ختم خارج الدَّين · قرار بلا تاريخ خارج الدَّين · نموّ الدَّين فوق السقف · مدخل دَين بائت). ويُبلَّغ **البيات** ولا يُحجَب عليه: الحجب على تقادم رقم يُحوّل كلّ PR إلى حملة إعادة قياس ويُدرّب قارئه على تجاهل الحارس، وهو أشيع أعطال الحرّاس في هذا المستودع نفسه.
- **الدَّين مُعلَن ومسقوف بلا فسحة:** ٤ قياسات بلا أساس (`assertion_presence` · `brain_deferral` · `platform_extraction_map` · `platform_python_module`) و٩ قرارات بلا تاريخ. السقف مشدود على العدد الحاليّ، فمصنوعةُ قياسٍ **جديدة** لا تدخل الدَّين — من قاس اليوم يعرف على أيّ شجرة قاس. وقائمةٌ يُقال عنها «تتقلّص ولا تنمو» **بلا سقف لا تمنع النموّ**: يكفي أن يُضاف إليها المدخل الجديد.
- **وإنفاذ عكسيّ:** مدخلٌ اكتسب ختماً يجب أن يخرج من قائمة الدَّين وإلّا سقط الحارس — وإلّا أطالت القائمة نفسها بمداخل بائتة، وهو ما فعله كلّ أساس في هذا المستودع لم يُنفَّذ عكسيّاً.
- **ما كشفه التقرير فور تشغيله:** ثلاثة من الأختام الخمسة القائمة تُسمّي شجرةً **غير قابلة للحلّ في هذا المستودع** (`6c966bab` · `249d94c1` · ونصّ حرّ بلا SHA) — رموز فروع ابتلعها الدمج squash. أي أنّ الختم كُتِب صادقاً وصار غير قابل للتحقّق؛ والحارس يقول ذلك صراحةً بدل أن يُبلِّغ «صفر التزام» (مُكذَّب بطفرة).
- **الحالة:** FIXED (`tests_v9/test_claim_base_guard.py`، ٢٨ اختباراً). **التكذيب بثماني طفرات**، كلٌّ تُسقِط اختباراً يسمّيها: مطابقة المفتاح بالبادئة (٣ — وأوّل ضحاياها `baseline_route_count` نفسه) · نزع السقف · نزع الإنفاذ العكسيّ · تبادُل الختمين (٢) · نزع حجب غير المصنَّف · نزع حجب المدخل البائت · اعتبار SHA المجهول صفراً.
- **حدّ صدق:** يحرس **مصنوعات `docs/architecture/` المُعلَنة وحدها**. الادّعاءات المقيسة في نثر `sahool-brain/*.md` أكثر عدداً بفارق كبير وهي خارج مداه — ولا قاعدة آليّة تُميّز رقماً مقيساً من رقمٍ مذكور في جملة. ولذلك الحالة «FIXED جزئيّاً» لا FIXED.

## GUARDS-WITHOUT-A-PLANTED-DEFECT-01 — ✅ FIXED جزئيّاً (2026-08-02)

- **المصدر:** ١٢٠ حارساً في `scripts/ci/*_guard.{py,sh}`، ولا واحد منهم مطلوبٌ منه أن يُثبِت أنّه **يُطلِق**.
- **العلّة في جملة:** الحارس الأخضر يقول شيئاً واحداً بيقين — **لم يُطلِق**. وهذا يحتمل معنيين لا يفرّق بينهما شيء: «لم يجد عطلاً» و«لا يرى العطل أصلاً».
- **ثلاثة في المعنى الثاني، في جلسة واحدة، وهم خُضر:** `runtime_contract_generator` (نمطه لا يرى الاسم غير المباشر ⇒ ١٣ متغيّراً) · تصنيف الأسرار فيه (لاحقة `_KEY` وحدها لا تطابق علامةً ⇒ ١٠ مفاتيح توقيع نُشِرت تهيئةً) · `brain_state_transition_guard` (نمطه خاطئ في الاتّجاهين معاً).
- **و«له اختبار» ليس دليلاً — وهذا لبّ الأمر:** أكثر من ثلثي حرّاس هذا المستودع لهم ملفّ اختبار، وكان أخضر طوال المدّة التي كان فيها الثلاثة عُمياً. اختبار الحارس المعتاد يقيس أنّه **يمرّ على شجرة سليمة** — وهي خاصّيّة يُحقّقها حارسٌ لا يفعل شيئاً على الإطلاق.
- **العلاج:** `docs/architecture/guard_mutation_registry.json` + `scripts/ci/guard_mutation_guard.py`. لكلّ حارس مُواصَف طفرةٌ تزرع العطل الذي وُجِد ليمسكه، واسمُ الاختبار الذي **يجب** أن يسقط عندها. `--run` يزرع فعليّاً ويُشغّل ويؤكّد.
- **وشرطان لا واحد:** «أخضر تحت عطل مزروع» إخفاق — والحارس لا يحرس تلك القاعدة، أو اختباره يقرأ مصنوعةً مُولَّدة سلفاً بدل أن يمرّ بها. و«أحمر بغير الاختبار المُسمّى» إخفاق أيضاً — «سقط شيء ما» يمرّ على طفرةٍ كسرت الاستيراد لا القاعدة، وهي أرخص طريقة لادّعاء تغطية غير موجودة.
- **وقعتُ في هذه بالضبط أثناء بنائها:** أوّل مواصفتين كتبتهما لـ`brain_state_transition_guard` حملتا `expect: "test_"` — بادئة تطابق أيّ سقوط — **ومرّتا خضراوين**. أي أنّ الآليّة أثبتت التغطية بشرطٍ يُحقّقه أيّ انهيار: نفس عطل «حارس يُبلِّغ نتيجةً عن سؤال لم يطرحه»، داخل الحارس المصنوع لمنعه. فصار `expect` يُطابَق بوجود `def <name>(` في ملفّ الاختبار المُعلَن، وصار ذلك نفسه تحت طفرة.
- **المقيس:** ٣ حرّاس مُواصَفون بـ**١٨ طفرة**، كلّها **مزروعة ومُشغَّلة فعليّاً** لا موصوفة. و**١١٧ ديناً مُعلَناً** بسقفٍ مشدود، فحارسٌ جديد لا يدخل الشجرة بلا مواصفة — من عرف العطل عرف كيف يزرعه. ولا يُدَّعى أنّ المُدرَجين في الدَّين معطوبون؛ يُدَّعى **أنّه لم يُقَس**، وهو الفارق نفسه بين «لم يجد» و«لم ينظر».
- **الحالة:** FIXED جزئيّاً (`tests_v9/test_guard_mutation_guard.py`، ١٧ اختباراً على حرّاس صناعيّين يُبنَون في `tmp_path` ويُشغَّل عليهم pytest حقيقيّ — لأنّ قراءة السجلّ والتأكّد من امتلائه كانت ستقيس **حالة السجلّ** لا **قاعدة الحارس**، وهو عمى التكذيب عينه).
- **حدّ صدق:** الخضرة تعني «**ما قِيس** يُطلِق» لا «كلّ حارس يُطلِق». ١١٧ من ١٢٠ لم تُقَس تغطيتهم بعد، والآليّة تمنع نموّ العدد ولا تُقلّصه من تلقاء نفسها.

## MCP-AUTH-BEFORE-BODY-01 — هبطت على main في `54a91d8e` (PR #769، P1 أمنيّة، 2026-08-02)

- **المصدر:** حزمة رقعة خارجيّة اقترحت الإصلاح؛ والبرهان أنّي طبّقتُ **اختبار عقدها وحده** على شجرة `main` غير المُرقَّعة (`ec9b86e0`) فسقط: `assert 422 == 401`.
- **العلّة:** تحليل جسم الطلب يسبق المصادقة في نقطة السياق العامّة المحميّة. مُستدعٍ **بلا مصادقة** يُرسل JSON مُشوَّهاً فيتلقّى `422` تحمل تفصيل خطأ التحليل (`loc` · `msg` · `ctx`) — أي تُكشَف بنية العقد لمن لم يُصادَق.
- **تصحيح توصيف سابق:** وُصِفت قديماً بأنّها «يُعيد 400 بدل 401». التوصيف الدقيق **ترتيبيّ لا رقميّ**: `HTTPBearer(auto_error=False)` يقود إلى 401 **إن بلغه التنفيذ**، لكنّ الجسم المُشوَّه يُنهي دورة الطلب قبل أن تصل التبعيّة إليه. ففحص التبعيّة منفردةً لم يكن برهاناً على ترتيب ASGI/FastAPI.
- **العلاج:** استُخرج تحقّق التوكن إلى مُتحقِّق واحد يستعمله كلٌّ من تبعيّة FastAPI ووسيط ASGI سابق للمصادقة، فيُرفض الاعتماد الناقص/المُشوَّه **قبل** أيّ فكّ JSON أو تحقّق Pydantic.
- **شرط القبول — أربع حالات، كلّها مقيسة:** جسم مُشوَّه بلا توكن ⇒ 401 · جسم صالح بلا توكن ⇒ 401 · بلا جسم وبلا توكن ⇒ 401 · **جسم مُشوَّه مع توكن صالح ⇒ 422**. الرابعة تمنع أن يتحوّل الإصلاح إلى إخفاء أخطاء الجسم عن عميل مُصادَق.
- **مُكذَّب:** إعادة `services/mcp_servers/shared/oauth_middleware.py` وحده إلى نسخة `main` ⇒ يسقط اختبارا العقد كلاهما؛ والاستعادة تُعيدهما خضراء. فالإصلاح هو الوسيط لا شيء آخر في الرقعة.
- **الهبوط (2026-08-02):** الشرط الذي اشترطتُه على نفسي تحقّق — «الحالة لا تصير إغلاقاً إلّا على SHA مدموج ينجح عليه الحارس». دُمِجت #769 squash إلى `54a91d8e`، و**٦٥ فحصاً** اكتملت على رأس الـPR (`958eef3a`) بلا إخفاق واحد، منها *Unit Tests* و*Lint & Format* و*Security Scan* و`capability-registry` و`no-report-only-change`.
- **حدّ صدق:** يُغلق «المصادقة قبل التحليل» لهذه النقطة. **لا يُغلق** مصفوفة حالات MCP كاملةً — 403 لتوكن صالح بلا صلاحيّة، و2xx لمسموح — وتلك تحتاج بوّابة حيّة وتبقى في `docs/runbooks/LIVE_GAP_CLOSURE_AGENT_RUNBOOK.md`.

## ROOT-GAPS-CLOSURE-EVIDENCE-BOOTSTRAP-01 — هبطت على main في `54a91d8e` (PR #769، P0، 2026-08-02)

- **الصنف:** `self-blocking verification bootstrap` — أداة الإغلاق تمنع نفسها من الإقلاع.
- **المصدر:** عيب أدخلتُه أنا في تمريرة إضافة الحرّاس إلى `docs/runbooks/LIVE_GAP_CLOSURE_AGENT_RUNBOOK.md`، ثمّ أمسكتُه بقراءة الملفّ كما صار لا بالثقة في التمريرة التي كتبته.
- **العلّة:** وُضِع `: "${EV:?…}"` على **كتلة 0.1** — وهي التي تُنفّذ `mkdir` وتُصدِّر `EV`. فالحارس يطلب postcondition قبل تنفيذ الـbootstrap الذي يُنشئها؛ ونقطة الدخول تُلصَق في صدفة نظيفة فتخرج بـ**1** مطالِبةً بمتغيّر كانت على وشك تعريفه.
- **السبب الجذريّ في أداتي:** سكربت الإدراج يتخطّى الكتلة إن كان الإسناد في **بداية سطر**، و0.1 تُسنِده وسط أمر مركّب (`… && export EV=$PWD && cd -`). وتركت التمريرة نفسها حارساً **مكرّراً** في كتلة الاكتشاف.
- **العلاج — نُقِل لا حُذِف:** bootstrap بلا حارس (0 من 1)، وكلّ الكتل المستهلِكة تحمله (**31 من 31**)، وصفر تكرار. حارسٌ يمنع الخطوة التي ينتمي إليها يُدرِّب المُشغّل على حذف الحرّاس.
- **مُثبَت بالتشغيل لا بالتركيب:** كتلة 0.1 في صدفة نظيفة داخل مستودع git فارغ ⇒ خروج **0** وإنشاء وطباعة مجلّد الأدلّة · `bash -n` على **34 كتلة** ⇒ صفر خطأ نحويّ · وتشغيل كتلة الـheredoc فعليّاً بمُدخَلات اصطناعيّة ⇒ خروج 0 وكتابة ملفّ الدليل.
- **الهبوط (2026-08-02):** دُمِجت #769 squash إلى `54a91d8e` بـ**٦٥ فحصاً** مكتملاً بلا إخفاق.
- **حدّ صدق:** هذا يُصلح إقلاع أداة القياس، ولا يُغلق أيّ فجوة تشغيليّة من الفجوات الثلاث عشرة التي تحتاج stack حيّاً.

## CONFLICT-RE-MATCHES-PROSE-MENTIONS-01 — ✅ FIXED (2026-08-02، كشفه أوّل استعمال حقيقيّ)

- **المصدر:** `scripts/ci/resolve_merge_conflicts.py` — `CONFLICT_RE` كان `r"<<<<<<< (?:HEAD|[^\n]*)\n(.*?)\n=======\n(.*?)\n>>>>>>> [^\n]*\n"` بـ`re.S` **بلا `^` وبلا `re.M`**.
- **كيف انكشف:** أوّل تعارض حقيقيّ بعد دمج #761 مباشرةً (فرع `claude/project-exploration-dtjw3p`، PR #767). سبعة ملفّات: ستّ مولَّدة وواحد إلحاقيّ — لا مصدر، أي الحالة التي بُني لها السكربت.
- **العلّة:** العلامة **علامةٌ في بداية السطر فقط**؛ وبلا مرساة، أيّ ذكرٍ نصّيّ للرمز وسط سطر يفتح كتلة كاذبة. والذكر النصّيّ ليس حالةً نادرة هنا: `sahool-brain/log.md` **يصف حوادث التعارض بأسمائها**، فهو مضمون الملفّ الذي يُحلّ. المطابقة بدأت عند `log.md:3404` («تركت علامات تعارض `<<<<<<< …`») ومدّ `.*?` **٣٤٩ ألف حرف = ١٣٦٧ سطراً** حتّى أوّل `=======` حقيقيّ، فعُدّ كلّ ذلك «جانب ours».
- **والضرر شكله مُميِّز:** **لم يضِع محتوى** — الجانبان بقيا — لكنّ ترتيب ١٣٦٧ سطراً انقلب، و**خرج الملفّ بعلامة `<<<<<<< HEAD` حقيقيّة داخله**. ولم يمسكها إلّا `conflict_marker_guard` **بعد** الحلّ، أي بنفس آليّة «أمسكه حارسٌ آخر مصادفةً» التي وُجِد هذا السكربت ليُنهيها.
- **العلاج:** `^` + `re.M` على الحدود الثلاثة، والجانبان يشملان سطر النهاية فيكفي `\n` بينهما. والبحث يستأنف بعد المُدرَج لا من الصفر (كلفة خطّيّة لا تربيعيّة).
- **الحالة:** FIXED (`tests_v9/test_resolve_merge_conflicts.py`، ٣٩ اختباراً). **التكذيب:** نزع المرساة ⇒ **تسقط اثنتان**.
- **وتصحيح قياسٍ لي، مُسجَّل لأنّ أوّل رقم كتبتُه كان خطأً:** قلتُ «تسقط ٦» قبل أن أشغّل الطفرة، والمقيس **٢**. والسبب درسٌ في بناء الاختبار نفسه: أربع حالات نثريّة كتبتُها **لا تُميّز** — النثر وحده بلا `=======` بعده لا يُكمِل مطابقةً، فيمرّ تحت النمط المعطوب والسليم سواءً. صار كلّ نثرٍ يليه **كتلةٌ حقيقيّة**، فظهر أنّ المُميِّز واحد منها فقط.
- **والمتّجه المُميِّز مقيس لا مُقدَّر:** فتحُ الكتلة الكاذبة يتطلّب `<<<<<<< ` **متبوعاً بمسافة** وسط السطر. فذكرٌ مثل ``` `<<<<<<<`/`=======` ``` (شرطة مائلة أو علامة اقتباس خلفيّة بعد الرمز) لا يفتح شيئاً، وذكرُ `=======` أو `>>>>>>>` وحدهما كذلك — لا افتتاح فلا كتلة. أي أنّ سطح العطل أضيق ممّا يبدو، وأخطرُ ممّا يبدو في آنٍ: الصيغة الوحيدة التي تفتحه هي **الصيغة التي يكتبها من ينقل رسالة git حرفيّاً**، وهي أشيع صيغة في سجلّ يصف حوادث دمج.
- **النمط للمرّة الرابعة، والآن في أداتي أنا:** كاشفٌ يُعرَّف بنمطٍ لا تُقاس تغطيته هو نفسه. **ولماذا لم تره اختباراتي الأصليّة:** كلّها بنت نصّاً صناعيّاً تقع فيه العلامات في بداية السطر دائماً — فالاختبار قاس الحالة التي يعرفها الكاتب، لا الحالة التي يقع فيها السكربت. والفرق بين ١٩ طفرة مزروعة و**استعمالٍ واحد على مُدخَل حقيقيّ** ظهر هنا: الطفرات تُثبِت أنّ القاعدة تُطلِق، ولا تُثبِت أنّ المُدخَل الحقيقيّ يشبه ما فُرِض.
- **حدّ صدق:** الإصلاح يُثبّت الحدود ولا يُعالج تعارضاً **داخل** كتلة مقتبَسة (كتلة كود في Markdown تحوي علامات في بداية أسطرها) — حالة لم تقع بعد ولا يُدَّعى أنّها مغطّاة.

## BRAIN-TRANSITION-GUARD-BLIND-TO-ARABIC-STATUS-01 — مفتوحة (P2 حوكمة، 2026-08-02)

- **المصدر:** قياس أُجري أثناء تحضير شريحة التوثيق نفسها، على `54a91d8e`. النصّ المقيس: عناوين `## ` في `sahool-brain/gaps/registry.md`.
- **العلّة:** `scripts/ci/brain_state_transition_guard.py:28-31` يُعرّف مفردات الحالة **بالإنجليزيّة وحدها**. والسجلّ يكتب حالاته بالعربيّة في أكثر الأحيان.
- **القياس:** ١٠٠ عنوان فجوة · **١٦** منها يحمل حالة إغلاق عربيّة · يلتقطها الحارس: **٠** · ويلتقط ١٣ عنواناً بمفردات إنجليزيّة. فالثغرة ليست نظريّة: أكثر من نصف إعلانات الإغلاق في السجلّ خارج مدى الحارس.
- **إقرار على هذه الشريحة نفسها:** تحديث حالتي `MCP-AUTH-BEFORE-BODY-01` و`ROOT-GAPS-CLOSURE-EVIDENCE-BOOTSTRAP-01` أعلاه يمرّ من الحارس **بسبب هذه الثغرة**، لا لأنّه أثبت شيئاً. ما يجعله صادقاً هو `54a91d8e` المدموج وفحوصه، لا خُضرة الحارس. تسجيل هذا هنا شرط ألّا يُقرأ المرور شهادةً.
- **لماذا لم يُوسَّع النمط في هذه الشريحة:** توسيعه بالكلمة العربيّة المجرّدة يُعيد إنتاج العطل المُصلَح في `BRAIN-TRANSITION-GUARD-MATCHES-FAIL-CLOSED-01` حرفيّاً — **٤٠ سطراً** في الدماغ تحمل صيغة «يفشل مُغلَقاً»/«مُغلَقاً» وهي **وصف تصميم لا انتقال حالة**، فتصير إيجابيّات كاذبة. والإيجابيّ الكاذب أسوأ من غياب الحجب لأنّه يُرسل القارئ يبحث عن ادّعاء لم يُقَل.
- **الاتّجاه المقترح (غير مُنفَّذ):** ربط المطابقة **ببنية** لا بكلمة — سطر مُضاف يبدأ بـ`## ` داخل `gaps/registry.md`، أو سطر `- **الحالة:**` — فتُستبعد نثريّات «مُغلَقاً» بالبناء لا بقائمة استثناءات. يلزمه تمرير الفروق مفصولةً حسب الملفّ، وهو تغيير في توقيع `check()` يستوجب تحديث `tests_v9/test_brain_transition_guard_vocabulary.py` (١٦ اختباراً خضراء اليوم).
- **الحالة:** OPEN. لا حارس، ولا اختبار، ولا ادّعاء إغلاق. الأثر: انتقال حالة عربيّ في الدماغ وحده يمرّ بلا شيفرة تنفيذيّة تسنده.

## RELEASE-MANIFEST-SELF-REGENERATION-01 — مُغلَقة بالحذف (P2 حوكمة، 2026-08-08)

**الصنف:** مصنوعةٌ مُلتزَمة **لا تستطيع مطابقة إعادة توليدها على التزامها نفسه** — لا لعطلٍ
في الحتميّة، بل لأنّ ختمها يشير إلى الالتزام الذي يحملها.

**تصحيح سببٍ سبق الإصلاح:** أبلغتُ المالك أنّ `generated_at` **ساعةُ حائط**، فبنى عليه قرار
شريحة. والقياس على `fc79fbbe` يُكذّبه: بناءان متتاليان على رأسٍ ثابت ⇒ **نفس القيمة
بالثانية**، مطابقةً لختم آخر التزام مسّ الحمولة. عقد `SOURCE_DATE_EPOCH` كان **مُنفَّذاً
بالفعل** (`scripts/ci/deterministic_time.py`) بكلّ بنوده.

**العطل الحقيقيّ، وهو مكتوبٌ في المصدر نفسه** (`deterministic_time.py:49-60`): البيان
يُولَّد **قبل** الالتزام الذي يحمله؛ فبعد التزامه يصير ذلك الالتزام «آخر تعديل للحمولة»،
وتكتب إعادةُ التوليد زمنه الجديد ⇒ دورة ذاتيّة لا تنتهي. والدمج بالـsquash يجعل التأخّر
بالتزامٍ واحد **حتميّاً**.

**والأهمّ منهجيّاً — صنفٌ يستحقّ اسماً:** المصدر أعلن ذلك «غير ضارّ» **بشرطٍ مُصرَّح**: «لا
شيء يفحص تطابق البيان مع إعادة توليده». وشرطُ القبول الذي أضافه المالك
(`test -z "$(git status --porcelain)"` بعد إعادة البناء) **هو** ذلك الفحص. فالعطل لم يظهر
لأنّ الكود تغيّر، بل لأنّ **الافتراض المكتوب بطل**: توثيقٌ صادقٌ يوم كُتِب، يصير ادّعاءً
يوم يُضاف الفاحص الذي نفى وجوده.

**العلاج (قرار المالك): حذفٌ لا استثناء.** بقياسين: الحقل **بلا مستهلِك واحد** في المستودع
كلّه، و**لا يمثّل وقت البناء الحقيقيّ أصلاً** بل زمن التزامٍ سابق. وإعفاء البيان من فحص
الانحراف كان سيُبقي العيب ويُطفئ الكاشف.

**ما بقي عمداً:** `deterministic_time.py` (يستهلكه `runtime_environment_preflight.py`) ·
و`payload_pathspec` بلا مستدعٍ إنتاجيّ، **مُعلَنةً في docstringها** بدل أن تبقى شيفرةً ميّتة
يحرسها اختبار أخضر. ووقتُ البناء الفعليّ، عند الحاجة، يذهب إلى `attested_at` **خارج**
المصنوعة المُلتزَمة.

**والخاصّيّة المُختبَرة صارت أقوى:** كان التأكيد «الختم وحده يتبع `SOURCE_DATE_EPOCH`»،
وصار «**البايتات كلّها ثابتة مهما اختلف المتغيّر**» — وهي ما يفحصه شرط النظافة مباشرةً،
ومعه اختبارٌ يمنع عودة الختم أو الساعة صامتةً.

**معايير القبول الستّة، مقيسةً على `d76d7766`:** بناءان ⇒ تطابق بايتيّ · بناءٌ بعد التزام
المصنوعة ⇒ **شجرة نظيفة** (كان مستحيلاً بنيويّاً) · `file_count` ثابت (٥٣٨٤) ·
`validate_release_package` PASS · لا `generated_at` · لا استثناء.

**المصدر:** `scripts/release/build_release_bundle.py` · `tests_v9/test_deterministic_generation.py`
· قرار المالك على #811.

## DETERMINISTIC-GENERATION-AND-MERGE-SAFETY-01 — هبطت على main في `0bf19688` (PR #770)، **والادّعاء صُحِّح بعدها** (P2 حوكمة، 2026-08-02)

- **المصدر:** قياس على تاريخ المستودع بعد تكرار التعارض عشرات المرّات. ١٧٣ التزاماً في التاريخ يذكر تعارضاً، وسطحه **مركَّز لا موزَّع**: أربعة ملفّات دماغ إلحاقيّة (89+77+75+32 = **٢٧٣ من ٢٨١** لمسة على `sahool-brain/` منذ 2026-07-01) ومصنوعات مولَّدة يتصدّرها `release/SAHOOL_RELEASE_MANIFEST_20260626.json` (**١٢٨** التزاماً — الأعلى في الشجرة).
- **الجذران منفصلان، ولذلك عولجا منفصلين:** ① **لاحتميّة**: البيان كان يكتب `datetime.now(UTC).isoformat()` بدقّة الميكروثانية، فيكتب فرعان متوازيان قيمتين مختلفتين في **نفس السطر** ⇒ تعارض مضمون بالبناء حتّى مع حمولة متطابقة. ② **تعدّد كتّاب على ملفّ مشترك**: كلّ جلسة تُلحق بذيل الملفّات الأربعة.
- **تصحيح رقم ذكرتُه أنا:** قلتُ «٧٤ من ١٢٨ التزاماً غيّرت الختم فقط». إعادة القياس بتفصيل أدقّ: **٣** غيّرت `generated_at` وحده · **٧١** غيّرته مع `file_count`/`total_size_bytes` (حمولة تغيّرت فعلاً) · **٥٢** محتوى آخر. فالمكسب ليس «إلغاء ٧٤ التزاماً» بل خاصّيّة أدقّ وأقوى: **إعادة التوليد على شجرة لم تتغيّر حمولتها تُنتج صفر فرق** بدل فرق سطريّ مضمون.
- **L0 — الحتميّة:** عقد مركزيّ في `scripts/ci/deterministic_time.py` بترتيب ثلاثيّ صريح (`SOURCE_DATE_EPOCH` ⇒ ختم آخر التزام ⇒ **فشل صريح**). **لا ارتداد إلى الساعة**: الارتداد الصامت يعمل في CI حيث المتغيّر مضبوط، وينهار عند المطوّر بلا رسالة. **مقيس:** ثلاث توليدات تحت `TZ=UTC/LC_ALL=C` و`TZ=Asia/Singapore/LC_ALL=en_US.UTF-8` ومصدرَي زمن ⇒ **نفس SHA-256**.
- **وحقل يُسرّب الآلة، حُذِف:** `source_root: root.name` كان يطبع **اسم مجلّد السحب** — قِيس فعليّاً: التوليد في شجرة عمل اسمها `wt768` كتب `"source_root": "wt768"` في مصنوعة إصدار. له **صفر قارئ** في المستودع كلّه. نفس صنف `RUNTIME-ENV-PREFLIGHT-STAMPS-THE-MACHINE-01`.
- **L2 — حارس الهويّة المتلاصقة:** `scripts/ci/brain_duplicate_gap_identity_guard.py`. **تصميمه صُحِّح بالقياس مرّتين:** ① المقارنة على **معرّف الفجوة** لا على نصّ العنوان، لأنّ الحالة الخطرة عنوانان مختلفان نصّاً متطابقان هويّةً. ② والقاعدة على **التلاصق** لا على التكرار: أوّل تصميم أعطى **١١** إصابة على الشجرة، **عشرٌ منها شرعيّة** (سلاسل تاريخيّة مقصودة مثل `SILENT-EXCEPTION-HANDLERS-11-01` ×٣). حارسٌ يرفع عشرة إنذارات كاذبة يُعطَّل في أوّل يوم.
- **وأوّل إصابة حقيقيّة له كانت قائمة في الشجرة قبل وصله:** `BRANCH-GRAVEYARD-POLICY` عنوانان متلاصقان بلا متن — أثر دمج قديم. أُصلِح بدمج النصّين بلا حذف كلمة.
- **L3 — `merge=union` على أربعة مسارات صريحة** لا glob. **مُكذَّب بالاتّجاهين:** أُعيد بناء تعارض حقيقيّ (القاعدة `f9dec1d9`، الجانبان `808d85f9` و`main`) ⇒ بلا union **٣** علامات تعارض، ومع union خروج **0** ونتيجة تُطابق الحلّ اليدويّ المدفوع (١٠١ عنوان، نفس المجموعة والترتيب، صفر تكرار، فرق سطر فارغ واحد).
- **L4 — `scripts/dev/enable_rerere.sh`** بـ`--local` وidempotent ومُتحقِّق بعد الكتابة. **ليس بوّابة CI عمداً**، ومُختبَر أنّه ليس مذكوراً في أيّ workflow: CI يبدأ من نسخة نظيفة بلا `rr-cache`، فإفشاله على غياب rerere إبلاغ عن سؤال لم يُطرَح.
- **تكذيب فاشل، مُسجَّل لأنّه علّمني:** زرعتُ أربع طفرات على مرساة الحارس (نزع `^`، `match`⇒`search`، كلٌّ وحدها، ثمّ معاً) فبقيت **١٦ اختباراً خضراء** في الأربع. السبب أنّ اختبار «الذكر النثريّ» استعمل سطراً لا يحوي `##` إطلاقاً — فكان يوثّق النيّة ولا يقيسها، وهو صنف #768 حرفيّاً، وقعتُ فيه **داخل الحارس المصنوع لمنع صنفه**. أُعيدت صياغته على الحالتين الحسّاستين وحدهما (عنوان مُقتبَس بـ`>` وعنوان يسبقه نصّ)، فصارت الطفرة المزدوجة تُسقِط اختباراً.
- **حدّ صدق حاسم:** **GitHub يتجاهل `.gitattributes` المُعرَّف من المستخدم** (ردّ دعم صريح، المطلب مفتوح منذ 2021). فـL3 يُصلح الدمج وإعادة التأسيس **على سطر الأوامر فقط**، و**لا يُزيل لافتة «This branch has conflicts»**. الحلّ الجذريّ للافتة بنيويّ وهو `BRAIN-FRAGMENTED-SOURCE-OF-TRUTH-01` أدناه، مؤجَّل بقرار المالك.
- **وحدّ ثانٍ:** L2 **يكتشف** الفشل الصامت ولا يمنعه؛ وL3 وL4 لا يُزيلان الجذر. اسم الفجوة يقول ذلك عمداً: «حتميّة وأمان دمج»، لا «إغلاق تعارضات الدماغ».

## BRAIN-FRAGMENTED-SOURCE-OF-TRUTH-01 — مفتوحة، الاتّجاه معتمَد والتصميم مؤجَّل (P2 معماريّة، 2026-08-02)

- **المصدر:** قرار المالك في مراجعة `DETERMINISTIC-GENERATION-AND-MERGE-SAFETY-01`: «اعتماد الاتّجاه، تصميم منفصل» — لأنّ تحويل نموذج تخزين الدماغ يُغيّر **مصدر الحقيقة وبروتوكول الكتابة**، بينما الطبقات الأخرى تحسينات محدودة قابلة للرجوع.
- **العلّة:** أربعة ملفّات مشتركة يكتب فيها كلّ فرع. ملفّان مختلفان **لا يتعارضان أبداً** — لا محلّيّاً ولا على GitHub. وهو النمط المعتمَد صناعيّاً: `changelogs/unreleased/` عند GitLab، و`changelog.d` في `towncrier`.
- **الاتّجاه المعتمَد:** شظايا مستقلّة بهويّة دائمة (`<GAP-ID>.<commit-or-id>.yaml`) لا باسم يعتمد التاريخ وحده — جلستان في اليوم نفسه تتصادمان. مُجمِّع يُولّد الملفّات التجميعيّة من الشظايا.
- **تصنيف لازم قبل التنفيذ، لأنّ الأربعة ليست صنفاً واحداً:** `gaps/registry.md` وhot.md **views** مولَّدة من مدخلات الفجوات · `log.md` أحداث جلسات إلحاقيّة · `decisions/ledger.md` شظايا قرارات مستقلّة. جمعها في schema واحد لتقليل عدد الملفّات يخلط مفاهيم مختلفة.
- **شروط الشريحة:** هجرة مزدوجة القراءة · مقارنة byte/دلاليّة بين المولَّد القديم والجديد · ثمّ قطع الكتابة المباشرة إلى الملفّات التجميعيّة.
- **الحالة:** OPEN. لا شيفرة، ولا حارس، ولا ادّعاء. الاتّجاه معتمَد والتصميم لم يُكتَب.

## IMAGERY-BLANK-THUMBNAIL-CLIENT-URL-01 — هبطت في `0bf19688` (#770) (P1 نَسَب/واجهة، 2026-08-02)

- **المصدر:** تقرير تحقيق خارجيّ مع حزمة رقعة. الادّعاء الأساسيّ (Root Cause 1) مُتحقَّق منه هنا بالتنفيذ لا بالقراءة.
- **العلّة:** `frontend/src/services/api.ts::fieldCdseThumbnailUrl` كان يبني الرابط **بلا** `source=persisted`، فيسقط إلى `source=auto`. والمسار الحيّ في `services/raster-service/routers/cdse_tiles.py` يُعيد عند غياب المشهد **`TRANSPARENT_PNG` بحالة 200** — و`<img>` **لا يقرأ ترويسات الاستجابة**، فيُطلِق `onLoad` وتنتقل البطاقة إلى `ready` وهي بكسل شفّاف 1×1: **مربّع فارغ بلا تفسير**.
- **والإصلاح كان قائماً على الخادم ولم يُطبَّق على العميل:** `services/sahool-platform/api/routers/field_workspace_imagery.py:132` يبني الرابط بـ`&source=persisted` صراحةً منذ `IMAGERY-BLANK-THUMBNAIL-01`. فالفجوة **عدم تناظر** بين بانيَي الرابط لا عيب في العقد.
- **العلاج:** سطر واحد — `params.set('source', 'persisted')`. والمسار المُدام fail-closed: `_persisted_thumbnail` يُعيد **404** عند غياب الأصل، فيُطلِق `onError` وتُظهر `ImageryTimelineThumb` «تعذّر العرض» المرئيّة.
- **التكذيب — نفّذتُه لأنّ الحزمة لم تستطع:** بيئتها بلا `node_modules` (فشل `npm ci` على مرآة داخليّة: 404 لـ`zustand-5.0.14.tgz`). هنا `vitest` متاح، فطبّقتُ **اختباراتها وحدها** على المصدر غير المُرقَّع ⇒ **٣ اختبارات تسقط** بالرسالة الصحيحة (`expected … to contain 'source=persisted'`)، وبعد الإصلاح ⇒ **٢٦ تمرّ**. والجناح الكامل **١٣٠٠ اختبار في ١٩٤ ملفّاً** أخضر ⇒ صفر انحدار.
- **مسح المستهلكين قبل التعميم (الادّعاء الحامل في التقرير):** مستهلكان إنتاجيّان فقط — `MapHub.tsx:2474` (لا يبني الرابط إلّا حين `d.has_cog`، أي حين أعلن الخادم وجود الأصل) و`SatellitePage.tsx:331` (احتياطيّ `p.thumbUrl ?? …`؛ والرابط المُسلَّم من الخادم يحمل `persisted` أصلاً، فالإصلاح يجعل الاحتياطيّ **متناظراً** لا مُنحدِراً). ولا مستهلك يستعمل `latest` — و`_persisted_thumbnail` يدعمه أصلاً (`requested=None` ⇒ أحدث أصل).
- **تصنيف بقيّة أسباب التقرير، ولا يُخلَط بالأوّل:** ② اختيار `truecolor` وإلّا أوّل مؤشّر محفوظ **سلوك صحيح**؛ العيب كان طلب المؤشّر المحفوظ عبر `auto`. ③ إخفاء الشريط افتراضيّاً قرار تجربة مستخدم لا سبب فراغ. ④ فشل الكوكي يُنتج **401 ⇒ حالة مرئيّة**، لا الفراغ الصامت. ⑤ قائمة تواريخ فارغة لا تُنشئ بطاقات أصلاً — حالة مختلفة عن بطاقة `has_cog=true` فارغة.
- **حدّ صدق:** هذا يُغلق **الفراغ الصامت** لبطاقة أعلنت أصلاً مُداماً. لا يُغلق ④ (صلاحيّة الكوكي على HTTP بلا `AUTH_COOKIE_SECURE=0`) ولا يُثبِت الإغلاق الحيّ: معايير القبول الحيّة (رابط يحمل `persisted` · أصل موجود ⇒ 200 وصورة · أصل مفقود ⇒ 404 و«تعذّر العرض» · **صفر نداء CDSE** · كوكي غير صالح ⇒ 401) تبقى في `docs/runbooks/LIVE_GAP_CLOSURE_AGENT_RUNBOOK.md`.

## DETERMINISTIC-STAMP-SCOPED-TO-HEAD-NOT-PAYLOAD-01 — هبطت في `8f2c63b2` (#771) (P2 حوكمة، 2026-08-02)

- **المصدر:** تحقّقٌ بعديّ على `main = 0bf19688` بأمر المالك («تحقّق»). أعدتُ توليد بيان الإصدار على شجرة نظيفة فانحرف — والانحراف يُكذّب ادّعاءً كتبتُه أنا في **رسالة التزام مدموجة وجسم PR**.
- **الادّعاء المُصحَّح، حرفيّاً:** «إعادة التوليد على شجرة لم تتغيّر حمولتها تُنتج **صفر فرق** بدل فرق سطريّ مضمون». **غير صحيح كما نُفِّذ.**
- **العلّة:** ربطتُ الختم بـ`git log -1` أي **`HEAD`**. و`HEAD` يتغيّر مع كلّ التزام، ولكلّ فرع `HEAD` مختلف — فبقي فرعان متوازيان يكتبان قيمتين مختلفتين في نفس السطر، وهو **بالضبط** ما زعمتُ إزالته. مقيس على `main`: إعادة التوليد ⇒ `15:29:56Z` ⇒ `15:54:04Z`.
- **المُنجَز الفعليّ كان أضيق:** إزالة اهتزاز الميكروثانية، وثبات القيمة عند إعادة التوليد **على الالتزام نفسه** (مُتحقَّق: نفس HEAD مرّتين ⇒ بايتات متطابقة). مفيد، لكنّه ليس إزالة سبب التعارض.
- **ولماذا لم يمسكه اختبار القبول:** كلّ اختباراته تُثبّت `SOURCE_DATE_EPOCH` صراحةً (`1700000000`)، فلا تعبر حدّ الالتزام أبداً ولا تستطيع رؤية الفرق. **قياسٌ داخل ما افترضتُه** — وهو **رابع** وقوع في هذا الصنف بعينه في جلسة واحدة (بعد مرساة الحارس، واختبارَي `--global` و`root.name` اللذين عاقبا التعليق الشارح).
- **الإصلاح:** `source_epoch`/`generated_at_utc` يقبلان `payload` — نطاق مسارات تُشتقّ منه لحظة **آخر التزام مسّ الحمولة** بدل `HEAD`. وهو المعنى القانونيّ لـ`SOURCE_DATE_EPOCH` («آخر تعديل للمصدر») لا حيلة.
- **والنطاق مُشتقّ لا مكتوب بيد:** `build_release_bundle.payload_pathspec()` يبنيه من `EXCLUDE_DIRS` و`SELF_GENERATED` نفسيهما. قائمتان تصفان الشيء نفسه تنحرفان، فيصير الختم مشتقّاً من نطاق غير الذي يُجزَّأ — عطل صامت لأنّ المصنوعة تبقى صالحة الشكل. والأهمّ عمليّاً استبعاد `sahool-brain/`: كلّ جلسة تُلحق به، فدخوله يُعيد العطل كاملاً.
- **مُثبَت على مستودع حقيقيّ بفرعين لا يمسّان الحمولة:** بنطاق `HEAD` ⇒ `1785686683` و`1612137600` (مختلفان) · بنطاق الحمولة ⇒ `1577836800` **لكليهما**.
- **التكذيب:** إعادة النطاق إلى `HEAD` (`scope = []`) ⇒ يسقط `test_payload_scoped_stamps_are_identical_across_branches` **وحده**، والباقي أخضر — فالاختبار يقيس القاعدة لا شيئاً آخر.
- **وحدٌّ مقابل مُختبَر:** تغيّر الحمولة **يجب** أن يُحرّك الختم (`test_a_real_payload_change_does_move_the_stamp`)، وإلّا مرّ إصلاحٌ يُعيد ثابتاً دائماً — حتميّ وبلا معنى.
- **وخاصّيّة بنيويّة اكتشفتُها بمسبار على المستودع نفسه، تُقال ولا تُترَك للاحق:** المصنوعة **لا تُطابق إعادة توليدها على التزامها هي**، لأنّها تُولَّد قبل ذلك الالتزام فيكون ختمها ختم أحدث سلف مسّ الحمولة. ومحاولة تثبيتها بـ`--amend` لا تنتهي (قِيس: ثلاث دورات، فرق ثانية واحدة كلّ مرّة). **وغير ضارّ مقيساً:** `build_release_bundle` بلا `--check`، وذكره في المكنسة **صفر**، ويعمل في وظيفتَي بناء إصدار فقط؛ وبوّابات الـPR تتحقّق من جزئات الملفّات الأخرى والبيان مستبعَد من بصمته الخاصّة.
- **ومسبار أوّل صمّمتُه خطأً:** قِستُ «قبل التزام دماغ / بعده» بينما كنتُ قد صنعتُ للتوّ التزام حمولة، فخلطتُ الأثرين وقرأتُ فشلاً حيث لا فشل. وأخطأتُ ثانيةً بتشغيل البناء بـ`SOURCE_DATE_EPOCH=` (سلسلة فارغة = **مضبوطة** لا غائبة) فانهار البناء صامتاً وابتلعتُ رمز خروجه، فبدت الشجرة «مستقرّة» وهي لم تُبنَ أصلاً. التصميم الصحيح: تثبيت أوّلاً، ثمّ التزام دماغ وحده، ثمّ التزام حمولة — وفحص رمز الخروج في كلّ خطوة.
- **البرهان النهائيّ على هذا المستودع:** التزام يمسّ الدماغ وحده ⇒ **صفر فرق** (`e08b8ba4` قبل وبعد) · التزام يمسّ الحمولة ⇒ **يتحرّك** (`ea6d640d`).
- **حدّ صدق:** هذا يجعل فرعين **لم يمسّا الحمولة** يُنتجان نفس الختم. فرعان غيّرا الحمولة فعلاً يبقى بيانهما مختلفاً — وهو صحيح لا عيب. ولم يُوسَّع الإصلاح إلى `runtime_environment_preflight.json`: حمولته هي البيئة لا الشجرة، وتحديد نطاقها يحتاج قياساً مستقلّاً.

## TEST-PROBE-LEAKS-INTO-THE-TREE-01 — هبطت في `b83c4ecf` (#772) (P1 حوكمة/تشخيص، 2026-08-02)

- **المصدر:** تقرير اعتماد خارجيّ (SAHOOL v22) أصدر **NO-GO** وعزا **١٩ إخفاقاً** إلى «تغيير غير محكوم أضاف `GET /api/probe-newservice/readyz` في `compat_gateway.py:145` بلا مصادقة ولا تصنيف»، وأوصى بحذفه أو تقنينه بصلاحيّة.
- **والمسار لم يدخل هذا المستودع قطّ.** `git grep` على `main` ⇒ **صفر**؛ و`git log --all -S "probe-newservice"` ⇒ التزام **واحد**، وهو التزام الاختبار الذي يُعرّف المِسبار. أي أنّ التقرير شخّص مسارَ اختبارٍ اصطناعيّاً على أنّه عيب إنتاج.
- **العلّة الحقيقيّة:** `tests_v9/test_api_versioning_policy_guard.py` يحقن المِسبار في `compat_gateway.py` **المتعقَّب** ويستعيده في `finally`. و`finally` لا ينجو من SIGKILL ولا من إلغاء وظيفة CI ولا من إغلاق طرفيّة.
- **مُعاد إنتاجه بالضبط:** `timeout -s KILL 3 pytest <الاختبار>` على `main` ⇒ `M compat_gateway.py` + انحراف ثلاثة جرود مولَّدة. هذه هي الملفّات الثمانية التي وصفها التقرير بأنّها «شجرة غير نظيفة».
- **وخطره أكبر من شجرة متّسخة:** أنتج **تشخيصاً واثقاً وخاطئاً**، والعلاج الموصى به (إضافة المسار إلى `PUBLIC_ALLOWLIST` أو تصنيفه) كان سيُحوّل مِسبار اختبار إلى **عقد دائم** في سطح API العامّ.
- **العلاج شطران:** ① المِسبار انتقل إلى ملفّ **غير متعقَّب** (`_probe_unadjudicated_route.py`) — الحارس يكتشف المسارات بـ`ROOT.glob("services/**/*.py")` ويحلّلها بـAST بلا استيراد، فملفّ جديد يُرى تماماً كتعديل ملفّ قائم. **مقيس:** نفس المقاطعة ⇒ **صفر** ملفّ مصدر متعقَّب متأثّر (كان ١). ② `scripts/ci/probe_leak_guard.py` يُسمّي ما يبقى (الجرود المولَّدة) بسطر واحد وعلاجه، **ويمنع العلاج الخاطئ صراحةً** في رسالته.
- **التكذيب:** إعادة إنتاج الحادثة ⇒ الحارس يُسمّي الملفّات الخمسة ويخرج بـ1؛ وبعد التنظيف ⇒ 0. والحدّ المقابل مُختبَر: المواضع الثلاثة التي تذكر الرمز **شرعيّاً** (الاختبار · خريطة القدرات · الدماغ) لا تُدين، وإلّا عُطِّل الحارس في أوّل يوم.
- **ووقعتُ في الصنف نفسه داخل اختبار الحارس، وأمسكته CI لا أنا:** `test_a_probe_marker_in_a_generated_inventory_is_caught` كتب الرمز في `api_versioning_inventory.csv` **المتعقَّب** ثمّ «استعاده» بـ`write_text`. و`read_text` يُترجم `\r\n` إلى `\n` فالاستعادة **مُفقِدة**: عاد الملفّ بمحتوى مطابق ونهايات أسطر مختلفة (١٠٧١ سطراً «تغيّرت» وصفر تغيّر محتوى)، ففشلت جزئته في `validate_release_package` وأسقطت *Repository Tests*. العلاج: `leaks(root=...)` تقبل مستودعاً مؤقّتاً، فلا يُمَسّ ملفّ متعقَّب أصلاً. **مقيس بعد الإصلاح:** `pytest tests/` ⇒ 621 ناجحاً والشجرة نظيفة (كان يترك `M api_versioning_inventory.csv`).
- **وسطحُ الفشل كان أوسع ممّا رأيتُه أوّلاً:** الجزئة البائتة أسقطت *Repository Tests (tests/)* **وخطوة `verify_all_generated` داخل `capability-registry`** معاً — والثانية سقطت **بعد** أن أبلغت الاثنتان والستّون خطوة `--check` كلّها `✓`، أي أنّ التحقّق النهائيّ من حزمة الإصدار هو مَن أمسكها لا أيّ حارس مفرد. مُقاس بعد الهبوط: كلا الفحصين **أخضر** على `b83c4ecf`، و**٦٤ من ٦٤** فحصاً خضراء.
- **حدّ صدق:** الشطر ② **يكشف** ولا يمنع؛ الاختبار يُعيد التوليد عمداً ليُثبِت أنّ إعادة التوليد لا تُبيّض مساراً جديداً، فالمقاطعة تترك الجرود منحرفة. المنع الكامل يحتاج تشغيل الاختبار في شجرة عمل معزولة، وهو أثقل ولم يُقَس نفعه بعد.
- **وقعت ثانيةً بعد أن كُتِب حارسها (2026-08-18) — والعطل هذه المرّة ليس في الحارس بل في أنّه لم يُسأل:** تقرير بيئة محليّة للمالك على شجرة `8ba4dbc7` أبلغ **أحد عشر إخفاقاً** في `pytest -m unit` ونسبها إلى «انحراف المصنوعات المولَّدة»، وسمّى ضمن تحذيراته ملفّاً غير متعقَّب هو `_probe_unadjudicated_route.py` نفسه. أي أنّ الحادثة عادت بأعراضها لا بسببها: أحد عشر عرَضاً في جرودٍ مشتقّة من المسارات، والسبب سطرٌ واحد.
- **ولماذا لم يُسأل:** `probe_leak_guard.py` يحجب في CI (`ci.yml:536`) وكان **غائباً عن `scripts/ci/preflight.sh` بأطيافه الثلاثة**. وخطوة ٠ب تطبع «⚠ ملفّ غير متعقَّب» — **تحذير لا إخفاق**، بلا تسمية الملفّ سبباً ولا طباعة علاجه — فأنهى `--fast` تقريره بـ«إخفاقات=0» على شجرةٍ تحجبها CI. وهذا هو صنف «أخضر عن سؤال لم يُطرَح» الذي بُني هذا السكربت كلّه لمقاومته، واقعاً في السكربت نفسه.
- **العلاج (الشطر ③):** الحارس صار خطوة `٠ج` في `preflight.sh` **داخل الطيف السريع** — بعد ٠ب مباشرةً حيث يُطبَع التحذير الذي يُفسّره — ودخل `required_scripts` في `docs/architecture/preflight_required.json` فحذفُه يُسمّى تقلّصَ تغطية لا بوّابةً مرّت. مقيس بإعادة إنتاج الحادثة: زرعُ الملفّ ⇒ الحارس يخرج بـ1 ويطبع `rm -f …` وسطرَي الاستعادة والتحقّق؛ حذفُه ⇒ 0.
- **والتكذيب ثلاثيّ لأنّ الخاصّيّة ثلاثيّة:** نزعُ الخطوة · نقلُها إلى ما بعد الخروج المبكر للطيف السريع (فتبقى «موجودة» ولا تُسأل حيث يُدفَع) · حذفُ المدخل من العقد — كلٌّ منها أسقط `test_a_leaked_test_probe_fails_the_fast_tier_instead_of_warning` وحدها. الثانية هي المهمّة: «موجود» ليس «يُقاس في الطيف الذي يُشغَّل فعلاً».
- **حدّ صدق مُعاد تأكيده:** ما يزال الشطر ② كاشفاً لا مانعاً، وهذا الشطر يوسّع **مَن يسأله** لا **ما يمنعه**. والمنع الكامل (شجرة عمل معزولة للاختبار) لم يُقَس نفعه بعد، ولا يُدّعى هنا.
- **ومراجعة Copilot على #871 أصابت في مرساة الاختبار نفسه — CONFIRMED بالقياس لا بالقبول:** كانت المرساة `text.index("scripts/ci/probe_leak_guard.py")`، والمسار **عارٍ** يظهر أيضاً في `require_file` وفي أيّ تعليق يُسمّي الحارس. فسيناريو «ذكرٌ نصّيّ فوق الخطوة + الاستدعاء منقولٌ خلف الخروج المبكر» كان **يمرّ**: قِيس مباشرةً ⇒ الصياغة القديمة `True` (تمرّ على العطل) والجديدة `False`. أي أنّ اختبار الموضع كان سيكفّ عن قياس ما يدّعيه في أوّل تعليق يُضاف — وهو صنف هذا الملفّ نفسه («assertion that stops measuring what it claims»).
- **العلاج:** المرساة صارت على **الاستدعاء** (`python3 scripts/ci/probe_leak_guard.py`) لا على المسار العاري، مع تأكيد **الوحدانيّة** (استدعاءان يجعلان `index` يقرأ الأوّل) وتأكيدٍ مستقلّ أنّ `require_file` نفسه داخل الطيف. والتكذيب صار **رباعيّاً**: نزع · نقل-مع-ذكر-نصّيّ · استدعاء ثانٍ · حذف مدخل العقد — كلٌّ أسقط الاختبار وحده، والشجرة السليمة 19/19.

## CI-HOST-PSQL-NOT-CONTAINER-OWNED-01 — مفتوحة (P2 بنية CI، 2026-08-18)

- **تصحيح قبل أيّ شيء:** سُجِّل في محادثة شريحة تصلّب CI أنّ هذه الفجوة «مُسجَّلة كدَينٍ مُعلَن». **ولم تكن.** `git log -S` على المُعرِّف عبر التاريخ كلّه ⇒ **صفر**. فالدَّين عاش في محادثة لا في الشجرة، وهو بالضبط الصنف الذي يوجد هذا السجلّ لمنعه. هذه أوّل مرّة يُكتَب فيها.
- **العطل:** خمس وظائف في `ci.yml` تُقيم حاوية Postgres ثمّ **تُثبِّت `postgresql-client` من APT على المضيف** لتستجوب جاهزيّتها. فالتجهيز يحمل اعتماداً شبكيّاً خارجيّاً (مرآة APT) لا علاقة له بما تختبره الوظيفة، وسقوطُه يُسقِط الوظيفة كلّها.
- **وقع اليوم مقيساً — والتصلّب عمل كما صُمِّم:** وظيفة `Decision Service Tests` (تشغيل 32156730870، مهمّة 95775765165، رأس `b01abc7d`): الحاوية أُنشِئت 15:49:36؛ `apt-get` بلغ سقفه الجداريّ (240ث) في 15:53:36 ثمّ ثانيةً في 15:57:46؛ فسقطت المهمّة 15:57:56 برسالة **مُسمّاة** `apt-get تجاوز مهلته مرّتين`. **ثماني دقائق وأربع عشرة ثانية إلى فشلٍ يُقرأ** بدل ستّ ساعات صامتة — وهو ما بُني `#868` و`ci_unbounded_wait_guard` لأجله بالحرف.
- **والشجرة ليست السبب، مقيساً لا مُرجَّحاً:** نفس الوظيفة على **نفس الرأس** نجحت في التشغيل المتوازي 32156721379 عند 15:50:25. فالمتغيّر هو مرآة APT على المُشغِّل، لا الالتزام.
- **وتضييقٌ جديد يُغيّر حجم الإصلاح:** في `decision-service-tests` وحدها، `postgresql-client` مُثبَّت **لأجل `pg_isready` فقط** (`ci.yml:985-990`)؛ كلّ ما بعده يمرّ عبر Python/`asyncpg` (`migration_runner.py` والاختبارات بـ`DATABASE_URL`). فلا `psql` في هذه الوظيفة أصلاً — أي أنّ اسم الفجوة أوسع من حالتها هنا، والحاجز **جاهزيّة لا عميل**.
- **وطريقٌ مسدود مُسجَّل كي لا يُعاد:** «اسأل الجاهزيّة داخل الحاوية» (`docker exec … pg_isready`) **كذّبه القياس** في التشغيل 32125050692: عبر مقبس يونكس يقول «accepting connections» أثناء طور التهيئة — نقطةُ دخول صورة postgres تُشغّل خادماً مؤقّتاً ثمّ تُعيد تشغيله — فيسقط الفحص النهائيّ بـ«no response». الاستجواب من المضيف عبر TCP هو المقياس الصحيح، ويحرس ذلك `test_the_host_side_readiness_probe_is_deliberately_not_forbidden`.
- **فالإصلاح المرشَّح:** استجوابٌ من المضيف **بلا APT** — اتّصالٌ حقيقيّ بـ`asyncpg` بعد تقديم خطوة تثبيت التبعيّات على خطوة الإقلاع. أقوى من `pg_isready` (يُنهي مصافحة libpq فعلاً) ولا يكذب في طور التهيئة ولا يلمس مرآة.
- **ولماذا لم يُشحَن اليوم:** لا يمكن تكذيبه في هذه الجلسة — لا خادم Postgres ولا عفريت docker. وتغييرٌ في `ci.yml` يُقاس بتشغيل CI وحده هو «مقيسٌ بمحاكاة»، وشحنُه تحت ضغط اخضرار جولةٍ هو أسوأ صيغه. **الحالة: OPEN بدَينٍ مكتوب لا محكيّ.**
- **وحتّى يُغلَق، الإجراء على سقوطٍ من هذا الصنف هو إعادة التشغيل لا تعديل الشيفرة** — بشرط أن يكون التشخيص مُسمّى كما هنا: الرسالة تقول السبب، والوظيفة نفسها خضراء على نفس الرأس في تشغيلٍ آخر. وإعادةُ تشغيلٍ بلا هذين الشرطين تدريبٌ على تجاهل الأحمر.
## CI-UNBOUNDED-PROVISIONING-WAIT-01 — مفتوحة/محروسة (P1 بنية CI، 2026-08-18)

- **تصحيحٌ قبل أيّ شيء:** هذه الفجوة يحملها اسمُها ثلاثةُ ملفّات (`scripts/ci/ci_unbounded_wait_guard.py` · اختباره · `GUARD_CATALOGUE.md`) و**لم يكن لها مدخل هنا قطّ**. ثاني حالة في اليوم نفسه يعيش فيها دَينٌ في الشيفرة والمحادثة دون السجلّ — وهو الصنف الذي يوجد هذا السجلّ لمنعه. `brain_commit_claim_guard` هو من أمسكها، لا القراءة.
- **الحادثة الأصل:** في التشغيل 32073296568 علقت `Integration Tests` **١١٢ دقيقة** ثمّ بقيت معلَّقة. الحصر يضع التعليق داخل `apt-get`: السحب اكتمل ومعرّفا الحاويتين طُبِعا، ولم يظهر سطرُ جاهزيّةٍ واحد — والحلقة مسقوفة (٣٠×٢ث) فلا تُفسّر ١١٢ دقيقة. **والسبب** (مرآة أو DNS أو قفل) **غير مُثبَت، والعلاج لا يحتاجه**: حدٌّ جداريّ يحوّل الصمت إلى فشلٍ مُسمّى.
- **المواضع أُصلحت في #868، والحارس مُنِع به عودةُ الصنف** (`ci.yml` — وظيفة `lint`). وقاعدةٌ ثالثة كانت مطروحة **حُذِفت لأنّ القياس كذّبها**: «لا `pg_isready` من المضيف» كسر التجهيز في التشغيل 32125050692 — مقبس يونكس يقول «accepting connections» أثناء طور التهيئة. الاستجواب من المضيف عبر TCP هو المقياس الصحيح، ويحرسه `test_the_host_side_readiness_probe_is_deliberately_not_forbidden`.
- **وثقبٌ ثالث في التصلّب نفسه، كشفه تعليقٌ حيّ لا مراجعة (2026-08-18):** الحدّ كان مفروضاً على **اسم الأمر** (`apt-get` نصّاً في الـworkflow) وعلى **وظائف حاويات القواعد**؛ و`npx playwright install --with-deps` ليس واحداً منهما — يستدعي `apt-get` من جوفه، ووظيفته لا تُقيم حاوية. فبقي **بلا حدَّين معاً**، وعَلِق في التشغيل 32160054946 **٨٠+ دقيقة** فحجب PR شجرتُه خضراء بالكامل (٦٧/٦٨). والحاسم أنّ الخطوة نفسها نجحت على **الرأس نفسه بالبايت** في التشغيل الشقيق 32160058172 في **2م55ث** — فالمتغيّر مرآة لا شجرة، والعطلُ في غياب السقف لا في الشبكة.
- **العلاج ثلاثيّ:** `timeout -k 10 300` على الخطوة · `timeout-minutes: 20` على الوظيفة · وقاعدة ③ في `ci_unbounded_wait_guard` تفرضهما، مع توسيع ① من «حاوية قاعدة» إلى «تجهيزٌ شبكيّ». والقائمة `_APT_INVOKING_TOOLS` **مقيسة لا متخيَّلة**: يُضاف إليها ما وقع فعلاً، لأنّ التوسيع بالتخمين يُنتِج إدانات لا يفهمها قارئها.
- **ودرسٌ عامّ يتجاوز الأداة:** حدٌّ يُفرَض على **اسم أمر** يفوته كلُّ من يستدعيه من جوفه. وأيّ ماسح نصّيّ على الـworkflows يحمل هذا العمى بنيويّاً — يُقال ولا يُصلَح بالنصّ.
- **والحدُّ أطلق فعلاً في اليوم التالي، فأثبت نفسه وأثبت نقصه معاً (2026-08-19، تشغيل 32269598189 على `d5fd1ec3`):** سقطت `Frontend E2E` بـ**`exit code 124`** — رمز `timeout` حرفيّاً. **خمس دقائق إلى فشلٍ مُسمّى بدل ٨٠+ دقيقة صامتة**؛ وهو بالضبط ما بُني له. لكنّه الدرس نفسه الذي تعلّمناه في APT: **الحدّ يحوّل الحرق إلى فشل ولا يُنجِح التثبيت**.
- **فعُمِّم علاج APT (بأمر المالك):** `scripts/ci/resilient_playwright_install.sh` — ثلاث محاولات · تراجعٌ متزايد · تبديل مرآة APT **قبل** النوم (`--with-deps` يستدعي apt من جوفه، فالمتّجه مشترك) · وكلّ محاولة مسقوفة. والدالّة **مُستخرَجة** إلى `apt_mirror_fallback.sh` يشترك فيها السكربتان بدل نسختين تنحرفان.
- **وحدٌّ يُعلَن في رسالة الفشل نفسها:** الخطوة تجلب من مصدرين — مرآة APT **وCDN متصفّحات Playwright**. الأولى تُبدَّل، والثاني لا مرآة بديلة مُعدّة له، فلا يُدّعى تبديلٌ لا يقع. الرسالة تقول «ولا مرآة بديلة لـCDN المتصفّحات» كي لا يظنّ قارئ الأحمر أنّ كلّ المصادر جُرِّبت.
- **والعمى نفسه تكرّر للمرّة الثالثة، وأُمسِك بالزرع لا بالقراءة:** نقلُ `--with-deps` إلى السكربت أخرج علامةَ «تجهيزٌ شبكيّ» من متن الوظيفة، فصارت ① لا ترى `frontend-e2e` ولا تطلب سقفاً — **والسقف كان قائماً، فمرّ الحارس أخضرَ لسببٍ خاطئ**. قِيس: نزعُ `timeout-minutes` لم يُدَن. عولج بعلامةٍ **بالبادئة** (`scripts/ci/resilient_`) تصف الصنف ولا تعدّ أفراده، فيرثها من يُضاف غداً.
- **وإيجابيّةٌ كاذبة في القاعدة ③ أمسكها أوّل تشغيل:** كانت تشترط أن **يبدأ السطر** بـ`timeout` (`match`)، فأدانت `if timeout … npx playwright install …; then` وهو مسقوفٌ فعلاً. صار المعيار معيار ② حرفيّاً: `timeout` ثمّ اسم الأداة بلا فاصل أمرٍ بينهما.
- **ومراجعةٌ جنائيّة خارجيّة أمسكت عطلين في عملي لم يمسكهما أيّ حارس هنا (2026-08-19):** ① `switch_apt_mirror` كان يقرأ `/etc/apt` **مُصلَّباً**، فاختبارُ «تُبدَّل المرآة قبل النوم» يمرّ أو يسقط بحسب نظام ملفّات المُشغِّل — يزيّف `sed` ولا يُستدعى أصلاً إن غاب الملفّ. مرّ عندي لأنّ الملفّين موجودان، وسقط عند المراجع لأنّهما ليسا كذلك. **أخضرٌ يعتمد على آلةٍ بعينها**، وهو أسوأ من أحمر. العلاج: `APT_SOURCE_FILES` تُحقَن، واختبارٌ يُثبِت الطرفين (المحقون يُحرَّر · الغائب لا يُفشِل) ومُكذَّب بإعادة التصليب.
- **② وبصمةُ الأرشيف المُعلَنة داخل `MANIFEST.md` كانت خاطئة، والحقل نفسه غير مُعرَّف:** حُسِبت قبل إدراج البيان والبصمات في الـZIP ثمّ أُدرِجا فتغيّرت البايتات (المُعلَن `1a546fd4…` والفعليّ `ea59bb7f…`). **ولا ترتيبَ خطواتٍ يُصلِح هذا**: بصمةُ أرشيفٍ موضوعةٌ داخله تُغيّره فتُبطِل نفسها، إلّا ببروتوكول تقنينٍ يستثني الحقل. فأُزيل الادّعاء بدل تصحيح رقمه، وحلّ محلّه بصمتان مُعرَّفتان: `SHA256SUMS.txt` **داخل** الأرشيف تصف محتواه، وملفٌّ جانبيّ `.zip.sha256` **خارجه** يصف بايتاته. والدرس: **مصنوعةٌ تشهد على نفسها من داخلها ليست شهادة**.
- **وخطأٌ ثانويّ أمسكه التكذيب لا القراءة:** بعد توسيع ①، بقيت رسالتها تقول «تُقيم حاوية قاعدة» — فوظيفة `frontend-e2e` كانت ستُدان بسببٍ لا يخصّها، فيُصلَح الخطأ الخطأ. صارت تسمّي **ما وُجِد** (`--with-deps` أو `docker run -d --name`)، ويحرس ذلك تأكيدٌ صريح.
- **وتكرارٌ ثالث في اليوم نفسه بلغ العتبة التي وضعها المالك، فصار الحدُّ وحده غير كافٍ:** 15:53 (`Decision Service Tests`، تشغيل 32156730870) · 16:14 (`Integration Tests`، 32158772016) · 18:09 (`Integration Tests`، 32169040894). وفي كلٍّ منها بلغ `apt-get` سقفه (٢٤٠ث) مرّتين فسقطت الوظيفة **مُسمّاةً في ثماني دقائق** بدل ستّ ساعات صامتة. فالتصلّب عمل — لكنّه **يحوّل الحرق إلى فشل ولا يُنجِح التثبيت**، وثلاث مرّات تقول إنّ ذلك لم يعد كافياً.
- **العلاج المأذون (bounded retry/backoff + mirror fallback)، مُخرَجاً من YAML إلى سكربتٍ يُختبَر:** `scripts/ci/resilient_apt_install.sh` — ثلاث محاولات، تراجعٌ متزايد، و**تبديل المرآة قبل النوم لا بعده** (النوم على مرآةٍ متعثّرة إنفاقُ وقتٍ على نفس الشرط)، وكلّ استدعاء يبقى مسقوفاً. والمواضع الثلاثة المتطابقة في `ci.yml` صارت تُفوِّض إليه — ثلاث كتلٍ تنحرف عن بعضها عند أوّل تعديل، والانحراف صامت. ٧ اختبارات بـ`apt-get`/`sudo` مزيّفين تقيس **ما نُفِّذ**.
- **والسببُ ما يزال غير مُثبَت، ولا يُفترَض:** ازدحامٌ أو DNS أو قفل. ولذلك لا يفترض العلاج سبباً — يُعيد، ويُبدّل، ويبقى مسقوفاً؛ فإن كان عابراً نجحت الثانية، وإن كان في مرآةٍ بعينها نجحت الثالثة، وإن كان الشبكة كلّها سقط سريعاً ومُسمّى.
- **وإصلاحٌ كاد يفتح ثغرة، أمسكتُه قبل الدفع:** نقلُ الكتلة إلى سكربت أخرج `apt-get` من ملفّات الـworkflows، ومدى الحارس كان عليها وحدها ⇒ القاعدة ② تصير **بلا مادّة تقيسها** والاختبار يزرع حيث لا يُقاس. وُسِّع المدى إلى `scripts/ci/*.sh`، ويقفله `test_moving_apt_into_a_script_does_not_move_it_out_of_the_guard`. وهو درس ③ بصيغةٍ أخرى: **حدٌّ مربوطٌ بموضعٍ يفوته من ينتقل عنه**.
- **وخطأ قياسٍ في اختباري أمسكه أوّل تشغيل:** `sudo` المزيّف ينفّذ ما بعده، فكلّ استدعاء يُسجَّل سطرين (الغلاف والمغلَّف)، فعدَّ التأكيدُ الضِّعف. العدّ صار على الاستدعاء المباشر — صنف «قياسٌ يعدّ غير ما يدّعي».

## CI-DUPLICATE-PUSH-RUN-BLOCKS-THE-PR-01 — مُغلَقة بالقياس (P1 بنية CI، 2026-08-18)

- **العطل:** `ci.yml` كانت `on: [push, pull_request]`، فكلّ دفعةٍ على فرع شريحة تُنشئ **تشغيلين** على الرأس نفسه. وتشغيل `push` **لا يُلغى أبداً** لأنّ مجموعة التزامن تحوي `run_id` فهي فريدة — وذلك مقصودٌ **على main** (لكلّ التزامٍ سجلُّه، لأنّ `certify-run` يستهلكه) لكنّه كان مطبَّقاً على كلّ مرجع.
- **والضرر ليس الكلفة بل الحجب — وهذا ما لم أرَه إلّا بعد أن وقع:** GitHub يقرأ **أحدث** سجلٍّ لكلّ اسم فحص. فتشغيل `push` يُلغى أو يسقط **بعد** أن اخضرّ تشغيل الـPR ⇒ نتيجته الحمراء تعلو على الخضراء، ويبقى الـPR محجوباً بلا شيء يُصلَح.
- **المقيس على `claude/claude-md-docs-p6qqir` في يومٍ واحد:** `6400` failure · `6402` عالق ٨٠+ دقيقة · `6404` failure · `6406` **cancelled بعد ٦٥ دقيقة** (بينما أنهى شقيقه `6407` نفسَ الخطوة في ٢٩د٤٥ث). **أربعة تشغيلات، صفر فائدة، وحجبٌ مرّتين** — والثانية لم تكن لتزول من تلقائها.
- **العلاج:** `on.push.branches: [main]`. و**لا يُنقِص مستهلِكاً واحداً، مقيساً في المصدر لا مُرجَّحاً:** المستهلك الوحيد لتشغيلات push هو `certify-run.yml` وهو يشترط صراحةً `workflow_run.event == 'push' && head_branch == 'main'` — فتشغيلات push على غير main لم تكن تُغذّي شيئاً أصلاً، وتغطية فروع الشرائح يوفّرها تشغيل الـPR كاملاً.
- **والعقد يحرس الطرفين لا طرفاً:** `test_ci_trigger_contract.py` يفرض القصر، **ويفرض أيضاً أنّ شرط `certify-run` ما يزال main-only** — فلو خُفِّف ذلك الشرط لاحقاً صار القصر يُسقِط مستهلِكاً حقيقيّاً، ويُحمِرّ الاختبار قبل أن يقع ذلك صامتاً. وثالثٌ يمنع أن يسقط مع التغيير إلغاءُ الجولة البائتة على الـPR.
- **حدّ صدق:** هذا يُغلق التكرار في `ci.yml` وحدها. و~٣٥ workflow أخرى ما تزال `[pull_request, push]` — لكنّها ثوانٍ لا دقائق، فلا تحجب ولا تُكلِّف؛ ولم تُمَسّ لأنّ أثرها **لم يُقَس** ومسُّها بلا قياس يُكرّر العيب الذي أُغلِق.
## GUARD-MUTATION-RUN-FLAKED-ONCE-UNREPRODUCED-01 — مفتوحة (P2 حوكمة/بوّابة، 2026-08-02)

- **ما حدث بالضبط، بلا تفسير مُضاف:** `guard_mutation_guard.py --run` أخفق مرّة واحدة على `claim_base_guard.py[4]` برسالة «حمرّ بغير الاختبار المُتوقَّع `test_a_decision_stamp_does_not_satisfy_a_measurement`». تشغيلان تاليان على **نفس الشجرة بالضبط** مرّا (rc=0)، وزرعُ الطفرة نفسها يدويّاً أحمرَّ **بالاختبار الصحيح** (`1 failed, 27 passed`). وعلى `origin/main` في شجرة عمل منفصلة: rc=0.
- **ولا سبب مقيس.** الفرضيّات المتاحة (ضغط موارد على المُشغِّل · حالة عابرة في جمع الاختبارات) **لم تُقَس**، ولا تُكتَب هنا بوصفها سبباً. المسجَّل هو الملاحظة لا تفسيرها.
- **ولماذا يُسجَّل أصلاً:** `--run` **بوّابة حاجبة** (`ci.yml:548`). فحصٌ يحمرّ مرّة ويخضرّ بإعادة التشغيل يُدرّب قارئه على إعادة التشغيل بدل القراءة — وهو أخطر عطل يصيب بوّابة، لأنّه يُطفئها بلا تعديل سطر.
- **والحارس يملك أصلاً تمييز «المُشغِّل لم يعمل» (`ran_at_all`)** — وهو ما وُضِع بعد حادثة الثمانية عشر إخفاقاً الكاذبة. الرسالة التي ظهرت **ليست** تلك، أي أنّ pytest عمل فعلاً. فالتمييز القائم لا يغطّي هذه الحالة.
- **الخطوة التالية نُفِّذت، وأثمرت في أوّل تشغيل:** الفرع صار يطبع `الساقط فعلاً` (`failing_tests` على سطور `FAILED`/`ERROR`) ومخرَج pytest. وتكرّر الإخفاق فوراً، **فلم يعد مجهولاً**: الساقط هو `test_a_measured_stamp_does_not_satisfy_a_decision` — أي **الاختبار المتوقَّع للطفرة المجاورة [3]**، لا اختبارٌ عشوائيّ ولا انهيار استيراد. والتشغيل التالي مرّ.
- **وهذا يُضيّق الفرضيّات بلا أن يحسم:** [3] و[4] طفرتان متناظرتان على سطرين متجاورين (`_has_base(data, m_keys)` سطر 120 · `_has_base(data, d_keys)` سطر 134)، وكلٌّ تُزرَع على نسخة أصليّة مستقلّة — فالتداخل ليس في الزرع. الأرجح حالة مشتركة بين الاختبارين أو قراءة للشجرة الحيّة، **ولم يُقَس أيّهما**، فلا يُكتَب سبباً.
- **الحالة:** OPEN. الكاشف أُصلِح، والعطل المكشوف لم يُصلَح. الخطوة التالية: عزل ما يتقاسمه الاختباران (`tmp_path` مقابل قراءة الشجرة) بتشغيلهما منفردين ومتتاليين ومعكوسَي الترتيب.
- **تكرار ثالث مقيس (2026-08-03، شريحة إرساء كاشف الترميز):** أخفق في أوّل تشغيل بالساقط **نفسه** — `test_a_measured_stamp_does_not_satisfy_a_decision` — ومرّ في التشغيل التالي على الشجرة ذاتها. الشريحة لا تمسّ `claim_base_guard` ولا اختباراته، فالتكرار **يستبعد** ارتباطه بمحتوى التغيير ويُبقي الفرضيّة على حالة مشتركة بين [3] و[4]. لا يزال غير محسوم؛ الخطوة التالية كما هي أعلاه.

## BRAIN-TRANSITION-GUARD-MATCHES-A-QUOTED-STATUS-TOKEN-01 — مفتوحة (P2 حوكمة، 2026-08-02)

- **مقيسة لا مفترَضة، وأطلقت عليّ:** `brain_state_transition_guard` رفض التزاماً يُصحّح حالات بائتة في الدماغ، والسطر الذي طابقه يقول حرفيّاً إنّ `production_certified=0/81` **ليس عيباً** وإنّ رفعه بلا دليل **يُفشِل البناء** — أي نفيٌ صريح للادّعاء، قُرِئ ادّعاءً.
- **العلّة:** `CLOSED_RE` يطابق `CLOSED|VERIFIED|RUNTIME_VERIFIED|PRODUCTION_CERTIFIED` بـ`re.I` في **أيّ موضع** من سطر مُضاف. فذكرُ اسم الحقل — اقتباساً أو نفياً أو شرحاً — يُعَدّ انتقال حالة. والنثر الذي يشرح ثوابت الصدق يذكر هذه الأسماء **بالضرورة**.
- **وهو تكرار صنف مُصلَح سابقاً لا عطل جديد:** `BRAIN-TRANSITION-GUARD-MATCHES-FAIL-CLOSED-01` كان نفس الشكل (`fail-closed` يطابق `CLOSED`)، وعُولِج بتضييق الحدود لا بإرساء الادّعاء. **الحدّ ليس مرساة**: يمنع المطابقة داخل كلمة، ولا يفرّق بين ادّعاءٍ وذِكر.
- **الاتّجاه البنيويّ (لا يُنفَّذ هنا):** الادّعاء في هذا المستودع يقع في **عنوان `## ` داخل `gaps/registry.md`** أو في إسناد حقل، لا في متن. الإرساء على العنوان هو ما جعل `brain_duplicate_gap_identity_guard` و`api_versioning_policy_guard` يعملان — ونفس الإرساء يُطبَّق هنا.
- **ولا يُرقَّع بالاستثناء:** إضافة «تجاهل السطر إن حوى نفياً» تُنتِج نمطاً يفشل عند الصياغة الرابعة عشرة — وهو **قائمةٌ في ثوب نمط**، الشكل المرفوض صراحةً في قرار تصنيف المفاتيح.
- **مُصلَحة في مرشّح الدمج — بالمرساة الدلاليّة لا بالاستثناء:** **اقتباسٌ يقول إنّ القيمة صفر لا يمكن أن يكون ادّعاء إغلاق.** `_CITED_AS_ZERO` يحذف من السطر كلّ ذِكرٍ متبوع بـ`=`/`:` وقيمة صفريّة (`0` · `0/81` · `false`)، ثمّ يُعاد الفحص على الباقي.
- **والقيد على القيمة هو ما يمنع التضييق من فتح ثغرة:** إعفاءُ `TOKEN=` مطلقاً كان سيُعفي إسناد **قيمة موجبة** لنفس الحقول — وهو **شكل الادّعاء الحقيقيّ بعينه**. أي أنّ إصلاح إيجابيّة كاذبة كان سيصنع سلبيّة كاذبة أخطر منها. مثبَّت باختبار مُسمّى وطفرة مزروعة.
- **والبديل المرفوض:** «تجاهل السطر إن حوى نفياً» — قائمةٌ في ثوب نمط، تنهار عند الصياغة الرابعة عشرة.
- **مقيس على ١١ حالة** (خمس اقتباسات صفريّة · ثلاثة ادّعاءات بقيمة موجبة · `fail-closed` و`open-closed` · سطر يجمع اقتباساً صفريّاً وادّعاءً غير مقتبَس ⇒ **يبقى ادّعاءً**، فالفشل في الجهة الآمنة). وطفرتان جديدتان في سجلّ الطفرات تُسقِطان الاختبارين المُسمّيَين.
- **وكيف مرّ الالتزام إذن:** بحمل `tests_v9/` فيه — وهو ما يطلبه الحارس فعلاً (دليل تنفيذيّ خارج الدماغ)، لا بتحايل على النمط. الرفض الأوّل كان لسبب خاطئ، والمرور الآن لسبب صحيح.

## RASTER-IMAGE-SHA-NOT-INJECTED-01 — مُصلَحة في مرشّح الدمج (P1 إصدار، 2026-08-02)

- **المصدر:** تقرير SAHOOL v22 — `raster-service` يُبلّغ `GIT_SHA=not-set`، خرق `P-CERT-2` (هويّة صورة ثابتة).
- **مُتحقَّق منه في المستودع:** `SAHOOL_GIT_SHA: ${TESTED_SHA:?...}` يُحقَن في **ثلاث خدمات فقط** — `sahool-platform` و`sahool-weather-service` و`sahool-soil-service`. كتلة `raster-service` في `docker-compose.v9.yml` **لا تحوي** الوسيط.
- **لماذا لم تُدمَج في شريحة التسريب:** إصلاحها يحتاج `ARG SAHOOL_GIT_SHA` في `services/raster-service/Dockerfile` أيضاً وإعادة بناء صورة — أثر تشغيليّ لا ساكن، ونطاق مختلف عن تسريب المِسبار.
- **الحالة:** OPEN. لا شيفرة ولا ادّعاء إغلاق. والأصحّ توسيعها لتشمل **كلّ** الصور لا الرستر وحده، منعاً لخليط SHA.

- **الإغلاق — خمسة أسطح لا أربعة، والخامس والسادس هما محلّ الفجوة:** ① `Dockerfile` بـ`ARG SAHOOL_GIT_SHA`/`SAHOOL_BUILD_ID` + وسوم OCI + ملفّ هويّة `chmod 0444` · ② `main.py` يُعلن `GET /runtime-identity` عبر `shared/runtime_identity.py::load_build_identity` (لا `os.getenv`) · ③ وسائط البناء في compose تفشل بلا `TESTED_SHA` · ④ **مصفوفة `runtime-image-provenance.yml`** · ⑤ **خطّة مِسبار `functional_probes/raster-service.json` بـ`identity_path`**. بلا ④ لا تُبنى صورة موثَّقة أصلاً؛ وبلا ⑤ لا يُفحَص شيء حيّاً. **صورةٌ مبنيّة محلّيّاً تحمل SHA صحيحاً تبقى غير موثَّقة** — والفجوة نصّها «يمكن بناء صورة لا يمكن ربطها بالـSHA المختبر»، والربط attestation لا وسم.
- **وسطحٌ سادس انكشف بالقياس أثناء الاستعادة من طفرة، ولم يذكره أحد:** وظيفة `publish-manifest` تحمل `expected={'weather-service','soil-service','sahool-platform'}` **مثبَّتةً نصّاً** وتُفشِل التجميع إن خالفتها الشظايا. فإضافة صفٍّ إلى المصفوفة وحدها كانت تُنتج **بناءً ناجحاً وتوثيقاً ناجحاً ثمّ انهياراً في آخر خطوة** — الجزئيّة نفسها، طبقةً أعمق.
- **والعلاج يمنع الصنف لا الحالة:** `test_every_identity_service_is_attested_and_probed` **يشتقّ** الخدمات من الشجرة (وسيط `load_build_identity`، وهو الاسم الذي تتحقّق منه الخدمة مقابل ملفّ الصورة فلا مجال لاسمين) ثمّ يُطابقها بالمصفوفة وبالمجموعة المتوقَّعة وبخطط المسابير. قائمةٌ مكتوبة بيد كانت ستبقى صحيحة حتّى الخدمة الخامسة.
- **التكذيب:** أربع طفرات مزروعة تُسقِطه — خارج المصفوفة · بلا خطّة مِسبار · خطّة بلا `identity_path` · مصفوفة تخالف `expected`.
- **وثلاث إصابات صحيحة على تغييري أمسكها الجناح:** `/runtime-identity` غير مُصنَّف في تصنيف صلاحيّات راستر (أُدرِج في `PUBLIC_CATALOG` تحت **بنية تحتيّة** مع الثلاثة الأخرى — تصنيفٌ مبدئيّ لا تمريرَ لتخضير: عقد الموضع يُصنّفه `infrastructure/provenance`، والحمولة نَسَب عامّ بلا سرّ، وحجبُها يكسر الغرض) · تعليقي في `Dockerfile` احتوى عبارة `pip install` فأطلق حارس مرآة pip (أُعيدت صياغته) · و`subprocess(text=True)` بلا `encoding` في الأداة الجديدة (أُضيف).
- **حدّ صدق:** كلّه ساكن. **لا برهان تشغيليّ حيّ**: لم تُبنَ صورة raster ولم يُشغَّل مِسبار على مكدّس. شرط الإغلاق الحيّ (`git_sha == TESTED_SHA` · `service == raster-service` · `metadata_source == immutable-image-file`، وبناءٌ بلا SHA صحيح **يفشل**) يبقى واجب مشغّل.

## GATEWAY-READINESS-PATHS-FALL-TO-SPA-01 — مفتوحة (P2 تشغيل، 2026-08-02)

- **المصدر:** تقرير SAHOOL v22 — `/readyz` و`/runtime-identity` عبر nginx يُعيدان **HTML** (SPA fallback) بدل JSON، و`/api/v1/healthz` يُعيد 404.
- **مُتحقَّق منه:** `frontend/nginx.conf:23` يُعرّف `location = /healthz` صراحةً (فالادّعاء عنه لا ينطبق على هذا المسار)، لكن **لا يوجد** `location` لـ`/readyz` ولا لـ`/runtime-identity` ⇒ يسقطان إلى SPA.
- **والأخطر ليس عدم الكشف بل أنّ SPA fallback يُعيد 200 وHTML لمسار جاهزيّة**، فيُخفي خطأ توجيه خلف نجاح ظاهريّ — نفس صنف «PNG شفّاف بحالة 200» في `IMAGERY-BLANK-THUMBNAIL-CLIENT-URL-01`.
- **الحالة:** OPEN. يلزم أوّلاً حسم العقد الخارجيّ المقصود (داخليّ فقط أم مكشوف لمنسّق النشر)، فالكشف بلا قرار يُوسّع السطح.

## CAPABILITY-WAVE-V217-V231-DEFERRED — OPEN (مؤجَّلة بقرار القاعدة، لا مرفوضة) — رُصِدت عند إعادة تشكيل #775
- **المصدر (قياس استيراد على كامل الشجرة):** أربع عشرة وحدة في `services/sahool-platform/api/` (`canonical_as_applied_operation` · `canonical_capability_runtime_evidence` · `canonical_mobile_offline_sync` · `canonical_multi_season_analysis` · `canonical_nutrient_ledger` · `canonical_phenology_state` · `canonical_salinity_state` · `canonical_season_outcome` · `canonical_yield_forecast_evaluation` · `governed_runtime_verification_promotion` · `governed_yield_model_activation` · `governed_yield_model_promotion` · `machinery_delivery_confirmation` · `validated_machine_telemetry`) — **صفر مستورد غير اختباريّ** لكلٍّ منها. وجداول `v217`→`v231` **لا يكتب فيها أيّ خدمة**.
- **القاعدة المُطبَّقة:** `registry.md:383-385` (قرار مالك مُلزِم) ⇒ لا يدخل اسمُ وحدة الأساسَ إلّا في الـPR الذي يضيف مستهلكها الإنتاجيّ وحارساً يثبته. سابقة #676 = إسقاط من الشريحة.
- **الحالة:** الموجة مؤجَّلة برأس مثبَّت `98283bca` (في سجلّ أحداث #775) وحزمها الأصليّة قائمة. الإغلاق = شريحة لكلّ وحدة: مستهلك إنتاجيّ + حارس + إدامة.
- **يُحمَل مع أوّل شريحة (عيب حقيقيّ مقيس، لا يُنزَل وحده):** `v219_machinery_delivery_consumption.sql:10` يستشهد بـ`machinery_export_artifacts(tenant_id, id)`؛ العمود الحقيقيّ `artifact_id` (`v216_machinery_export.sql:57`). أثبتته `Integration Tests` بـ`column "id" referenced in foreign key constraint does not exist`.
- **قيد نطاق مقيس على الوصل:** ميزانية مسارات النطاق 627/629 — الهامش **٢**. وصلُ أربع عشرة وحدة بمسارات جديدة مستحيل داخل الميزانية؛ الوصل يمرّ عبر نقاط قائمة (سابقة INT-004A / `?summary=true`) أو لا يمرّ.

## MIGRATION-DECLARED-BUT-NEVER-EXECUTED-01 — CLOSED (حارس مُثبَت بالتكذيب) — رُصِدت في نفس الجلسة
- **المصدر:** موجة `v217`→`v231` أضافت خمسة عشر ترحيلاً إلى `migrations/MANIFEST.txt` بلا سطر `\i` في `scripts_v9/run_migrations.sql`. مرّت بكلّ الحرّاس الساكنة و**لم تمسّ PostgreSQL قطّ** — «قدرة موجودة لا تجري» في طبقة المخطّط.
- **الدليل على أنّ الفجوة مُكلِفة لا نظريّة:** أوّل تشغيل بعد الوصل أسقط `Integration Tests` على عيب مفتاح أجنبيّ حقيقيّ في `v219` كان مستوراً منذ وصول الحزمة.
- **الإغلاق:** `tests/test_migration_manifest_execution_guard.py` (مُعلَّم `unit`، ويعمل في *Repository Tests* و*Unit Tests* معاً بلا ضريبة تسجيل جديدة) — الاتّجاهان + منع التكرار + بقاء `v206_rls_final_hardening.sql` آخِراً في السجلّين.
- **مُثبَت بالتكذيب:** إعلانٌ بلا وصل ⇒ FAIL على `test_every_declared_migration_is_wired_into_the_runner` · وصلٌ بعد `v206` ⇒ FAIL على `test_the_runner_executes_each_migration_once` و`test_rls_final_hardening_stays_last_in_both_records`. الشجرة نظيفة بعد استعادة الزرعين. المقيس اليوم: ٢٢٢ مُعلَناً = ٢٢٢ موصولاً.

### تحديث CAPABILITY-WAVE-V217-V231-DEFERRED (2026-08-03): سلسلة الحقيقة المُدامة نزلت — ٥ من ٢٣ **قابلة للوصول**
- **قرار المالك:** «اعتمد سلسلة الحزمة و اغلق 777». أُغلِق #777 (كان أخضر) لصالح سلسلة أفضل، وأُعيد الفرع من `main`.
- **لماذا أفضل:** #777 كان يمرّر `accumulated_gdd=None` ويصل وحدةً واحدة؛ سلسلة الحزمة تقرأ **الحالة المُدامة الحقيقيّة** وتصل **ثلاث** وحدات نطاق عبر نفس المسار القائم `/api/v1/recommendations/for-field`. **صفر مسار جديد** (سطح الراوترات 573⇒573).
- **القياس الحاسم الذي غيّر شكل الشريحة:** من ٢٣ وحدة في الحزمة، **٥ فقط قابلة للوصول** من راوتر يُركِّبه `router_registry` فعلاً؛ **١٨ غير قابلة للوصول** لأنّ مستهلكيها الأربعة (`canonical_event_consumers` · `execution_state_consumers` · `final_consumer_workflows` · `season_learning_consumers`) **لا يستوردها أحد**. وحدةٌ مستوردها وحدةٌ غير قابلة للوصول تبقى ميتة — والاستيراد يجعل الفجوة **أصعب رؤيةً** لأنّ فحص «هل لها مستهلك؟» صار يمرّ عليها كلّها.
- **التمييز صار مفروضاً لا موصوفاً:** `services/sahool-platform/tests/test_canonical_state_reachability_guard.py` يمشي على مخطّط الاستيراد من الراوترات المُركَّبة. **مُثبَت بالتكذيب على شكل الحزمة نفسه**: وحدةٌ تستورد السلسلة ولا يستوردها أحد ⇒ يسقط `test_every_declared_canonical_module_is_reachable_from_a_mounted_route`. وزرعان آخران: بصمة يقدّمها العميل ⇒ FAIL، ومستودع يكفّ عن قراءة جدول مُدام ⇒ FAIL.
- **الأساس 675⇒680** للخمس القابلة للوصول حصراً. الثماني عشرة **خارج الأساس** — الفجوة تبقى OPEN.
- **مُستبعَد بصدق مع سببه:** سجلّ مصادر الحقيقة الزراعيّة — صفوفه تُعلن `workflow_consumer: canonical_event_consumers.py` (وحدة استُبعِدت) و`acceptance_tests` تشير إلى ملفّ سقط معها، و`writer` يسمّي خدمةً **لا تكتب الجداول أصلاً**. أُزيلت تأكيداته الثلاثة بتعليق يسمّي كلّ ذلك، وأُبقيت تأكيدات الترحيل/RLS/سجلّ القدرات لأنّها صحيحة.
- **وضريبة التسجيل كانت غير مدفوعة في الحزمة:** ٦٩٨ وحدة مقابل أساس ٦٧٥ (٢٣ غير مسجَّلة)، و١٨ خطأ `ruff` (منها `F401` واستيرادات غير مرتّبة) — أي أنّ الحزمة لم تُلَنت. صُحِّحت، ووُجِّه المهيّئ اليدويّ لـ`sys.path` إلى المساعد القانونيّ `tests_v9/sahool_platform_path.py`.

### تحديث CAPABILITY-WAVE-V217-V231-DEFERRED (2026-08-03): حارس الوصول بالتصنيفات + حارس التوفيق موصولان
- **قرار المالك (مراجعة الحزمة الثالثة):** الحارس المطلوب قبل الدمج لا يكفيه «له مستورد غير اختباريّ»؛ يجب أن يُثبِت جذراً تنفيذيّاً ويصنّف: `REACHABLE_FROM_MOUNTED_ROUTE` · `REACHABLE_FROM_REGISTERED_WORKER` · `REACHABLE_FROM_EVENT_SUBSCRIBER` · `REACHABLE_FROM_OPERATOR_CLI` · `UNREACHABLE_TERMINAL_CHAIN`، ولا يُحتسَب في الأساس إلّا الأربعة الأولى.
- **حارس الحزمة لم يكن يفعل ذلك:** ٥١ سطراً بجذر **واحد مثبَّت نصّاً** (`ROOTS={'api/routers/recommendations.py'}`) وبلا تصنيفات أصلاً. كُتِب `scripts/ci/platform_module_reachability_guard.py` بالجذور **مشتقّة من الشجرة**: راوترات مُركَّبة تلقائيّاً · وحدات يبدؤها compose بـ`python -m api.X` · مداخل `scripts/ops`. وفئة المشترِكين **فارغة بالقياس لا بالإغفال** (لا جذر مشترِك متمايز عن العمّال اليوم).
- **عيبان في حارسي أنا كشفهما التحقّق لا الثقة:** ① `pkg/__init__.py` كان يُفهرَس `pkg.__init__` فقط ⇒ كلّ سلسلة تمرّ بحزمة تبدو مقطوعة، و**عشر وحدات موصولة فعلاً** صُنِّفت غير قابلة للوصول (منها `core/crop_intelligence/canonical_inputs.py`). ② الاستيراد النسبيّ (`from .canonical_water import …`) لم يكن يُحَلّ ⇒ `canonical_water`/`canonical_boundary` بدتا ميتتين. صُحّح الاثنان، وارتفع المقيس 501⇒**522** قابلاً للوصول من مسار.
- **دَين موروث مُجمَّد لا محذوف:** سبع وحدات كنسيّة كانت في الأساس وغير قابلة للوصول **قبل** هذه الشريحة ⇒ `FROZEN_UNREACHABLE` **يتقلّص ولا ينمو**، والحارس يفشل على **الجديد** لا على ما ورثه. تُحقِّق فرديّاً: `canonical_hydraulic_capability` و`canonical_vri_prescription` **بلا مستورد واحد**، و`canonical_field_state_lock` يستورده جسرٌ غير قابل للوصول — سلسلة طرفيّة بعينها. و١٥٠ وحدة أساس أخرى غير قابلة للوصول **تُبلَّغ ولا تحجب** (لا يُبنى حجبٌ على دَين لم تُحدِثه الشريحة).
- **مُثبَت بالتكذيب على فرعيه:** وحدة كنسيّة في الأساس يستوردها مستهلك طرفيّ ⇒ FAIL بالاسم · ومدخل مُجمَّد صار قابلاً للوصول ⇒ إشعار راتشِت يسمّيه (تُحقِّق أنّ الإشعار يُطلَق فعلاً، فلا يكون شيفرة ميتة).
- **P0-2 لم يُغلَق — وسببه مقيس لا مُقدَّر:** وصلُ `capability_registry_reconciliation_guard` كشف **دورة** بينه وبين `capability_runtime_evidence`: كلٌّ يكتب `capabilities/registry/capabilities.json` ويُلغي الآخر، فلا تتقارب المكنسة بأيّ ترتيب. المقيس بعد التوفيق: **تسع قدرات** تختلف — `runtime` في ثمانٍ (`FM-001` · `OPS-008` · `SEC-003` · `SEC-004` · `SEC-005` …) و`status` في `FM-003`. الحسم يحتاج قراراً: **أيّ كاتب يملك أيّ حقل** — ووثيقة الحارس نفسها تقول إنّ JSON يملك مخرجات التتبّع بينما هو يدمج `runtime`. أُخرِج الحارس من هذه الشريحة بدل إنزال حلٍّ نصفيّ يجعل CI غير قادر على التقارب. **الفجوة تبقى مفتوحة بقياسها.**

### تحديث CAPABILITY-WAVE-V217-V231-DEFERRED (2026-08-03): كُتّاب الإسقاط الكنسيّ — عيبُ FK لا يراه اتّصالٌ مزيَّف
- **ما فحصته الحزمة الرابعة (`canonical_projection_outbox_final`):** ست دوالّ كتابة على `api/persisted_canonical_repositories.py` (`persist_*_state`/`persist_*_projection`) تُديم الأدلّة الخام + الحالة الكنسيّة + نيّة outbox في معاملة واحدة، وتوحيدُ معاملةِ مسار `/api/v1/recommendations/for-field` بحيث تشترك قراءةُ الحالة المُدامة وكتابةُ التوصية وحدثُها في لقطة واحدة. **صفر مسار جديد** (631 خاماً قبل وبعد؛ الاختلاف الوحيد أرقام أسطر).
- **العيب الحاسم — `command_id` مُختلَق يكسر قيداً مرجعيّاً:** الحزمة تولّد `uuid5(NAMESPACE_URL, f"sahool:{kind}:{digest}")` وتمرّره إلى `emit_event` كـ`p_command_id` بحجّة «مفتاح تكرار ثابت». لكنّ `events.command_id` هو `UUID REFERENCES commands(command_id)` ([`migrations/v11_events_bus.sql:11`](../../migrations/v11_events_bus.sql) `:39`، لم يُسقَط في أيّ ترحيل لاحق)، و**لا يكتب `commands` إلّا** [`api/command_store.py:139`](../../services/sahool-platform/api/command_store.py). **مُعاد إنتاجه على PostgreSQL 16 بمخطّط v11 نفسه:** `insert or update on table "events" violates foreign key constraint "events_command_id_fkey"`. أي أنّ **الدوالّ الثلاث لا تنجح ولا مرّة** على قاعدة حقيقيّة.
- **ولماذا لم يره اختبار الحزمة:** كلّ اختباراتها تعمل على `FakeConn` — و`fetchval` مزيَّفة تقبل أيّ وسيط. الاتّصال المزيَّف يقيس **شكل الاستدعاء** لا **قبول القاعدة**. الإصلاح: `NULL::uuid` كما يفعل [`api/irrigation_execution_request_port.py`](../../services/sahool-platform/api/irrigation_execution_request_port.py) حين لا يوجد أمر، والتكرارُ محميّ أصلاً بـ`dedup_key` (مستأجِر + نوع + كيان + بصمة الحمولة + تاريخ `occurred_at`) وكلّها مشتقّة من حالة غير قابلة للتغيّر — ولا يُصدَر الحدث إلّا إن أبلغ إدراجُ الحالة صفّاً جديداً.
- **صنف جديد مفروض — «دالّة ميتة داخل وحدة حيّة»:** حارس الوصول يقيس **الملفّ**، و`persisted_canonical_repositories.py` قابل للوصول فعلاً (الراوتر يستدعي `load_agronomic_context` منه). فكلّ كاتب يُضاف بجواره **يرث قابليّة وصول لم يكسبها** ويمرّ صامتاً. القياس: **ستّ دوالّ كتابة بصفر مستدعٍ إنتاجيّ** — مستدعوها الوحيدون في ملفّ الاختبار. [`services/sahool-platform/tests/test_canonical_writer_call_sites.py`](../../services/sahool-platform/tests/test_canonical_writer_call_sites.py) يُثبِّت المجموعة **تقلّصاً لا نموّاً**، ويفشل على كاتبٍ جديد بلا مستدعٍ (مُثبَت بالتكذيب: زرعُ `persist_unwired_thing` ⇒ FAIL يسمّيه).
- **حدّ الصدق الباقي كما هو:** الجداول الستّة ما زالت **تُقرأ ولا تُكتَب في الإنتاج**؛ ما نزل هو *القناة* لا *المسار*. `db_ownership.yml` يقول ذلك نصّاً بدل أن يدّعي كتابةً جارية.
- **ونقضٌ لقرار مالك رُفِض:** الحزمة نقلت `canonical_agronomic_context` من `provenance.input_snapshot` إلى `provenance` مباشرةً و**عدّلت الاختبار ليطابق** — وهو عكس حكم P0 الصريح. أُعيد الموضع، وأُعيد معه مسارُ التدهور الصادق الذي حذفته الحزمة: عند فشل القراءة يبقى المفتاح موجوداً بـ`limitations: ["CANONICAL_CONTEXT_UNAVAILABLE"]`، وإلّا صار «لا حالة مُدامة» و«القراءة انكسرت» إشارةً واحدة.

### تحديث CAPABILITY-WAVE-V217-V231-DEFERRED (2026-08-04): الكتابة وُصِلت بجذر مُسجَّل، وبوّابة حيّة لا تعمل حيّاً
- **الفجوة التي فتحتُها أمس أُغلِقت للإسقاطات الثلاث:** `scripts/workers/canonical_execution_learning_worker.py` صار خدمةً في [`docker-compose.v9.yml`](../../docker-compose.v9.yml) (`command: python /app/scripts/workers/…`, healthcheck بـ`--preflight`) ويستدعي `persist_phenology_projection` و`persist_salinity_projection` و`persist_nutrient_projection` على `agronomy.projection.requested`. الجداول الستّة لم تعد «تُقرأ ولا تُكتَب في الإنتاج».
- **المجموعة المُثبَّتة تقلّصت ٦ ⇒ ٣** في [`test_canonical_writer_call_sites.py`](../../services/sahool-platform/tests/test_canonical_writer_call_sites.py). والثلاث الباقية (`persist_*_state` · `persist_nutrient_ledger`) ادّعاءٌ **أضعف** من «ميتة» وسُجِّل كذلك: تستدعيها الإسقاطات داخل وحدتها، فتصلها عبوريّاً من العامل نفسه؛ وتبقى مُدرَجة لأنّ الحارس لا يعدّ نداء الوحدة لنفسها دليلَ وصل — وهي القاعدة التي أظهرت الستّة أصلاً، وتليينها الآن تقاعُدٌ عن القياس لا وفاءٌ به.
- **`command_event_causality_live_gate.sql` كان يستحيل تشغيله على قاعدة سهول:** يمرّر `entity_id` بـ`::uuid`، و[`v18_entity_ids_text.sql`](../../migrations/v18_entity_ids_text.sql) أعاد نوع العمود إلى TEXT و**أسقط صراحةً** حِمل `emit_event` ذا الـUUID (`DROP FUNCTION IF EXISTS emit_event(TEXT,TEXT,UUID,…)`) كي لا يتعايش التوقيعان. **مقيس على PostgreSQL 16:** ينجح على `v10+v11` (الشرط المُعلَن في رأس الملفّ) ويفشل على `v10+v11+v18` بـ`function emit_event(unknown, unknown, uuid, uuid, jsonb, …) does not exist`. كلّ قاعدة منشورة مرّت بـv18 (الترحيل ١٨ من ٢٢٧). أُصلِح بثلاثة `::text`، ثمّ نجح على الشكل الإنتاجيّ — وما زال يُثبِت قاعدة الـFK التي كُتِب لأجلها.
- **وصنف «الحارس يمرّ وهو يشهد بالباطل» تكرّر في حارسيّ أنا، لا في الحزمة:** نطاق مسح مواضع الاستدعاء كان `services/sahool-platform` وحدها والعامل خارجها، و`_WORKER_CMD` في [`platform_module_reachability_guard.py`](../../scripts/ci/platform_module_reachability_guard.py) طابق `python -m api.X` فقط فلم يرَ أمر compose المسارِيّ. صمتُ الحارس يُقرأ دليلاً، فالحارس الأعمى أسوأ من غيابه. وُسِّعا وأُعيد القياس (`MOUNTED_ROUTE` 522⇒523 · `TERMINAL` 157⇒156).
- **حدّ الصدق:** العامل **مُسجَّل** لا **مُثبَت حيّاً**. البوّابتان الحيّتان (السببيّة + RLS) أداتا إثبات لا إثبات؛ `runtime_verified` و`production_certified` باقيان صفراً.

## GUARD-PINS-IMPLEMENTATION-NOT-PROPERTY-01 — مفتوحة (P1 منهجيّة، رُصِدت 2026-08-04)

**الصنف:** حارسٌ يُثبّت **كيف** يعمل الكود بدل **ماذا** يضمن، فيحمي العطل لا المستخدم — وأيّ إصلاح صحيح يبدو انحداراً.

**الحالة المُثبِتة:** [`tests_v9/test_imagery_timeline_endpoint_v31_4.py`](../../tests_v9/test_imagery_timeline_endpoint_v31_4.py) اسمه `test_route_exists_and_is_month_bounded` — والخاصّيّة في اسمه صحيحة — ثمّ كان يؤكّد:

```python
assert "cutoff" in b and "timedelta(days=months" in b
```

أي وجودَ الحساب اليوميّ نصّاً. والشهر ليس ٣١ يوماً: عند `months=24` يُرجِع الحدُّ اليوميّ `2024-07-21` بينما التقويميّ `2024-08-04` — **أربعةَ عشرَ يوماً** من المشاهد تدخل النافذة بصمت. فلمّا صُحِّح الحساب سقط الحارس، وأسقط `Unit Tests` **مرّتين** على PR #780.

**العلاج المُنزَل:** التأكيد على الخاصّيّة (`_subtract_calendar_months` + `datetime.now(UTC).date()`) مع **تأكيد سلبيّ يُسمّي السبب** فلا يعود العطل صامتاً:

```python
assert "timedelta(days=months" not in b, "الشهر ليس ٣١ يوماً — لا تُعِد الحدّ اليوميّ"
```

**المدى غير المقيس بعد:** هذا المستودع يعتمد كثيراً على **حرّاس ساكنة تقرأ المصدر نصّاً** (`assert "..." in source`). القوّة فيها أنّها ترى ما لا يراه التنفيذ؛ والخطر أنّ أيّ تأكيد يذكر تفصيلاً تنفيذيّاً يُجمّده. الفارق العمليّ: **هل يبقى التأكيد صحيحاً بعد إعادة صياغة صحيحة؟** إن لا، فهو يُثبّت تنفيذاً. لم يُمسَح الجرد بعد.

**الأثر المُصاحَب (مسجَّل بصدق):** لم أُشغّل `pytest -m unit` قبل الدفع لأنّ الشريحة بدت واجهيّة وهي تحمل تغييراً خلفيّاً — عكس القاعدة المكتوبة في §٣.١٧ من دليل البوّابات في اليوم نفسه. الجناح يكشفه في خمس دقائق محلّيّاً؛ كلّف دورتَي CI.

**المصدر:** PR #780 · `2781d6e6` · وظيفة *Unit Tests* على `731d263e`.

### مُنفَّذ (2026-08-07): المسح الأوّل — والنصف القابل للحسم صار محروساً

- **الجرد الذي طلبَته هذه الفجوة وُجِد لأوّل مرّة** (‏`docs/architecture/source_text_assertion_inventory.json`،
  مقيس على `8de1eb91`): **٢٠٥٠** تأكيداً ساكناً على نصّ مصدر · منها **٢٩٢** موجباً يثبّت
  **نداءً بوسائطه** (صنف الحادثة) · و**١٥٣** مَنعاً، **١٠١** منها بلا سببٍ مُعلَن.
- **والقياس مُصدَّق بأنّه يُعيد إنتاج الحادثة:** `timedelta(days=months` يظهر مرّةً واحدة،
  مَنعاً **يحمل سببه** — أي الحالة المُصحَّحة في #780 بالضبط. ولو غاب لكان المسح يقيس شيئاً
  آخر، أو العلاجُ تراجع. مربوطٌ باختبار (`..._reproduces_the_incident_that_created_the_gap`).
- **ولم يُحرَس إلّا ما يُحسَم.** المَنع بلا سبب **قابل للحسم**: إمّا ثمّة رسالة أو لا.
  أمّا «هل يبقى التأكيد صحيحاً بعد إعادة صياغة صحيحة؟» — معيار الفجوة نفسه — فغير قابل
  للحسم آليّاً، و**مُصنِّفٌ استدلاليّ يُنتِج قائمةً تُقرأ ديناً وهي ما طابق نمطاً**. فالـ٢٩٢
  **تُنشَر ولا تُحجَب**، والحدّ مكتوب في الجرد ومحروسٌ باختبار يقرأ نصّه ويؤكّد أنّ الصنف
  الاستدلاليّ لا يدخل دالّة `check()`.
- **لماذا المَنع بلا سبب عطلٌ مؤجَّل، لا أناقة:** ① حين **يُطلِق** يقول «كسرتَ شيئاً» وهو
  يعني «نمنع هذا عمداً» — والقارئ الذي لا يعرف السبب يُرضي النصّ أو **يحذف المَنع**، وحذفُ
  مَنعٍ لا أحد يعرف سببه هو كيف يعود العطل الأصليّ · ② وحين **لا يُطلِق** لا يُميّزه شيء
  عن مَنعٍ بطل سببه، فيُقرأ حراسةً قائمة وهو أثرُ قرارٍ انتهى.
- **سُدِّد ١٧ بأسبابٍ مُستخرَجة من سياقها لا مُختلَقة** (‏١١٧ ⇒ **١٠٠**): تفويض النواة في
  weather-service · تجاوز `weather-service` إلى المزوّد · `continue-on-error` و
  `pull_request_target` · مفتاح خاصّ في سجلّ الأسماء · `TESTED_SHA=local` · عميل axios خاصّ
  وعناوين مُصلَّبة. **وواحدٌ منها لي**: `f"exception:{e}"` في `test_backfill_failure_reason_persisted.py`
  من #798 — شحنتُ مَنعاً بلا سبب في الشريحة التي كتبتُ فيها عن الأسباب.
- **الباقي ١٠٠ مَعدودٌ لا محكومٌ عليه**، ومكتوبٌ ذلك في الجرد ومحروسٌ باختبار: لم يُثبَت أنّ
  أيّاً منها خاطئ، بل أنّ سببه غير مكتوب. ولم أكتب لها أسباباً أُخمّنها — **سببٌ خاطئ أسوأ
  من غيابه لأنّه يُصدَّق**.
- **واختباران عندي كانا يمرّان بالسبب الخطأ:** `survey()` يتخطّى الملفّ الخالي من القارئات،
  فملفّاي الاصطناعيّان لم يبلغا فحصَ الحاوية الذي يدّعيان حراستَه. كشفَته طفرة مزروعة بقيت
  **خضراء** — لا قراءتي. أُصلِح الملفّان بإضافة قارئ حقيقيّ، فصارت الطفرة تُسقِطهما.
- **المصدر:** `scripts/ci/prohibition_reason_guard.py` · `tests_v9/test_prohibition_reason_guard.py`
  · `docs/architecture/source_text_assertion_inventory.json` · مواصفتا طفرة مُشغَّلتان بـ`--run`.

## WORKER-REGISTERED-BUT-CANNOT-START-01 — CLOSED، هبطت في `6b6ffe82` (PR #785) (مُثبَتة بالتشغيل الحيّ، رُصِدت 2026-08-04)

**الصنف:** وحدةٌ خضراء عند كلّ إشارة ساكنة — مُسجَّلة، ومُعلَنة خدمةً في compose، و`--preflight` يخرج بصفر ويطبع حقائقه — **والعمليّة تموت عند الإقلاع**. لا يكشفه إلّا تشغيلها.

**العطل:** [`scripts/workers/canonical_execution_learning_worker.py`](../../scripts/workers/canonical_execution_learning_worker.py) كان يشترك في **ثلاثة** مواضيع باسم durable **واحد**:

```python
durable = os.getenv("CANONICAL_LEARNING_DURABLE", "canonical-execution-learning-v1")
for subject in SUBJECTS:
    await js.subscribe(subject, durable=durable, cb=callback, manual_ack=True)
```

والمستهلك المُعمَّر في JetStream يرتبط باشتراك **واحد**. مُعاد إنتاجه على nats-server v2.10.22 مع nats-py:

```
nats.js.errors.Error: nats: JetStream.Error consumer is already bound to a subscription
```

الرمية تقع في **الدورة الثانية** من الحلقة، قبل أن يبلغ العامل حلقة الخمول ⇒ **لم يعالج حدثاً واحداً قطّ**، لا محلّيّاً ولا في أيّ نشر.

**ولماذا لم يره شيء:** `--preflight` يسأل «هل يغطّي دفقٌ كلّ موضوع؟» — والجواب نعم؛ وهو سؤال **التغطية** لا سؤال **الارتباط**. وحرّاس الوصول والتسجيل تقيس أنّ الوحدة مُستدعاة من جذر، وهي كذلك. الصنف نفسه المُسجَّل في `MIGRATION-DECLARED-BUT-NEVER-EXECUTED-01`: «مُسجَّل» ≠ «يعمل».

**العلاج المُنزَل:** durable مشتقّ لكلّ موضوع من **الموضوع كاملاً** (النقاط ⇒ شرطات) لا من مقطعه الأخير — `season.closed` و`irrigation.closed` يشتركان في المقطع الأخير، فلاحقةُ المقطع الأخير تُعيد التصادم نفسه تحت اسم يبدو متمايزاً. ولا هجرة مستحقّة على أيّ نشر: مستهلِك الاسم المشترك لم يكن ليُنشَأ لأكثر من موضوع واحد، والعامل الذي يملكه لم يُقلِع قطّ.

**التكذيب (طفرتان، كلٌّ أُعيدت إلى الشجرة وشُغّلت):** ① الاسم المشترك ⇒ سقط اختباران بالرسالة الحيّة نفسها · ② لاحقة المقطع الأخير ⇒ سقط اختبار التصادم بـ`canonical-execution-learning-v1-closed` مرّتين. وبعد الإصلاح: أربعة خضراء، **وتحقّقٌ حيّ** على nats-server يُظهر ثلاثة مستهلكين متمايزين لكلٍّ `filter_subject` الصحيح.

**المصدر:** [`tests_v9/test_canonical_execution_learning_worker_subscriptions.py`](../../tests_v9/test_canonical_execution_learning_worker_subscriptions.py) · القياس الحيّ على nats-server v2.10.22 · PR #785 (`6b6ffe82`).

## JETSTREAM-STREAM-TOPOLOGY-OWNED-BY-A-CONSUMER-01 — مفتوحة (P2 معماريّة، رُصِدت 2026-08-04؛ الحافّة وحدها هبطت في `6b6ffe82` / PR #785)

**الصنف:** طوبولوجيا ناقل الأحداث يملكها **مستهلِك** لا الناقل ولا الهجرات.

**القياس:** الدفق `sahool` الذي يحمل كلّ مواضيع `sahool.>` يُنشَأ في [`agents/notification/agent.py:449`](../../agents/notification/agent.py) — `await _js.add_stream(StreamConfig(name="sahool", subjects=["sahool.>"]))`. لا `sahool-nats` ينشئه ولا `sahool-migrate`. فصلاحيّة عامل التعلّم القانونيّ معلَّقة على إقلاع **وكيل الإشعارات** أوّلاً؛ وقد ظهر ذلك عمليّاً: أوّل `--preflight` محلّيّ فشل مغلقاً بـ`JetStream has no stream covering required subjects` حتّى أُنشئ الدفق يدويّاً.

**ما أُنزِل الآن (وحدّه):** حافّة `depends_on` صريحة على `sahool-notification-agent` في [`docker-compose.v9.yml`](../../docker-compose.v9.yml) — **ترتيب فقط**: `service_started` يقول إنّ عمليّة الوكيل بدأت، لا إنّ الدفق صار موجوداً. الضمان الحقيقيّ يبقى إقلاع العامل المُغلَق عند الفشل + `restart: unless-stopped`.

**ما لم يُنزَل ولماذا:** نقل ملكيّة الدفق إلى مُهيِّئ صريح (خطوة provisioning أو الهجرات) قرارٌ معماريّ يمسّ كلّ مشترِك على الناقل، وخارج نطاق شريحة إصلاح العامل. لا يُغيَّر بلا سلطة معماريّة.

**الجرد أُنجِز (2026-08-04):** [`docs/architecture/jetstream_topology_inventory.md`](../../docs/architecture/jetstream_topology_inventory.md) — دفق واحد · **١٣ مستهلكاً دائماً** من **ثلاثة مالكين** (`agents/` · `services/weather-polygon-worker/` · `scripts/workers/`) بلا سجلّ جامع قبل هذا. وكشف أربعة بنود لم تكن معروفة: ① التهيئة **مفتوحة عند الفشل** — `add_stream` يبتلع كلّ استثناء عدا «already exists» ثمّ يُعلن الوكيل `✅ ready` بلا ناقل · ② الدفق **بلا سياسة احتفاظ** (`max_age=0`, `max_msgs=-1`, `max_bytes=-1`)، والحدّ الوحيد `max_file_store: 2GB` على الخادم كلّه ⇒ نموّ حتّى الرفض، **والرفض صامت** (`shared/helpers.py:318-325` يلتقط ويُرجِع `False`) · ③ `num_replicas=1` ⇒ فقد المجلّد يفقد مواضع كلّ المستهلكين · ④ **لا حدّ إعادة تسليم ولا DLQ** على أيّ من الثلاثة عشر (`max_deliver=-1`)، ورسالةٌ تفشل عبوريّاً دائماً تُعاد إلى الأبد.

**الحسم المطلوب قبل النقل (قرارات منتَج لا تنفيذ):** سياسة الاحتفاظ · حدّ إعادة التسليم وDLQ · ملكيّة الأسماء الدائمة (مركزيّة تمنع التصادم الذي وقع فعلاً في `WORKER-REGISTERED-BUT-CANNOT-START-01`، أم لامركزيّة تحفظ استقلال الخدمات) · `num_replicas`.

**المصدر:** [`agents/notification/agent.py:449`](../../agents/notification/agent.py) · [`docker-compose.v9.yml`](../../docker-compose.v9.yml) `sahool-canonical-execution-learning-worker.depends_on` · قياس محلّيّ 2026-08-04.

## FAKE-CONNECTION-ENFORCES-NOTHING-01 — verified (خضرة Live PG Proofs على GitHub 2026-08-08؛ رُصِدت 2026-08-04)

**الصنف الجامع لأربعة عيوب في جلسة واحدة:** كلّ اختبارات مسار التعلّم القانونيّ تعمل على **اتّصال وهميّ**. والوهميّ لا يفرض `CHECK`، ولا يُطلِق `TRIGGER`، ولا يُعيد الأنواع التي يُعيدها asyncpg. فما مرّ خضراء سنةً كاملة كان يسقط في أوّل لقاء بقاعدة حقيقيّة — والأربعة أدناه سقطت **بالتسلسل**، كلّ واحد يحجب الذي بعده، فلم يُرَ أيّ منها قبل تشغيل الرحلة كاملةً.

**البرهان:** بعد تطبيق **٢٢٦ هجرة** من `MANIFEST.txt` على PG16 نظيفة (v206 آخِراً، صفر فشل) وتشغيل `run_canonical_execution_learning_live_gate.sh`، تعطّلت الرحلة أربع مرّات متتالية بأربعة أسباب مختلفة، وكلّ إصلاح كشف التالي.

**ما لم يُقَس:** كم اختباراً في هذا المستودع يعتمد على وهميّ لا يفرض ما تفرضه القاعدة. الأربعة أدناه هي ما التقته رحلة **واحدة**؛ السطح غير ممسوح.

**مُسِح السطح ثمّ سُدِّد (2026-08-08):** الماسح يرى **٣٨** ملفّاً على وهميّ، منها **٨** تدّعي دلالةً تفرضها القاعدة. الثمانية أُثبِتت على PG16 حيّة في [`tests_v9/test_live_pg_fake_connection_debt.py`](../../tests_v9/test_live_pg_fake_connection_debt.py) — ٣٠ اختباراً، لكلّ ادّعاء قبولٌ ورفض بـ`SQLSTATE`، و١٩ زرعاً تُثبِتها. الدَّين القائم = **صفر** (٨ خاماً − ٨ مُسدَّداً)، والملفّات تبقى في `fake_connection_tests` لأنّ الوهميّ نافع لمنطق التطبيق.

**رُقِّيت إلى `verified` بقياسٍ لا بادّعاء:** الشرط الذي كتبتُه كان «خضرة وظيفة `Live PG Proofs` على GitHub لا قياسي المحلّيّ»، وقد تحقّق: التشغيل `31257392372` على `b669c1d5` أنهى الوظيفة `success` وطبعت خطوةُ الحصر `اختبارات حيّة مجموعة: 30` — فالخضرة مقترنة بعددٍ مُنفَّذ لا بتخطٍّ صامت. وشرطٌ مكتوب يتحقّق ولا يُحدَّث سجلُّه يصير بدوره ادّعاءً بائتاً.

**وطريق الخروج نفسه كان معطوباً:** `$comment` يُعلن الخروج بالإثبات الحيّ بينما `claiming_db_enforced` مُشتقّ من **نصّ** الملفّ الذي لا يتغيّر بالإثبات. أُضيف `proven_live` (لا يُشتقّ، يُحمَل عبر `--generate`، ويُفحَص بأربعة شروط منها أنّ ملفّ الإثبات **يذكر** مصدره).

**فرعٌ مفتوح منها:** [`LIVE-PG-01`](../../docs/architecture/live_pg_findings.md) — `FORCE ROW LEVEL SECURITY` خامدٌ ما دام مالك الجداول superuser.

## PUSH-WITHOUT-FAIL-CLOSED-WRAPPER-01 — open (دين تشغيليّ، P2، سُجِّل 2026-08-08 بأمر المالك)

**لماذا سُجِّل ديناً لا درساً:** تكرّر **خمس مرّات**. والمتكرّر خمساً لم يعد سهواً يُروى في `log.md` بل عيبٌ في الأداة، وحكم المالك: «حادثة الدفع ليست فقد بيانات، لكنها تكررت خمس مرات؛ لذلك لم تعد درساً سردياً فقط».

**الحادثة المرجعيّة:** سلسلةٌ بـ`A; B` بدل `A && B` — أُجهِض `checkout` بعد ارتداد الشجرة ومع ذلك **نُفِّذ الدفع** فوضع لقطةً بائتة (`ab88ca41`) فوق فرع العمل. `main` لم تُمَسّ، وأُصلِح بـ`--force-with-lease`. فقدُ عملٍ لا فقدُ بيانات — وهو ما يجعله ديناً P2 لا حادثةً P1.

**العلاج المُقرَّر (غلاف نشر fail-closed) — بنوده كما حدّدها المالك:**

- `set -euo pipefail`
- `A && B` لكلّ عملية تعتمد على سابقتها
- التحقّق من الفرع وHEAD والشجرة **قبل** الدفع
- `--force-with-lease=refs/heads/<branch>:<expected_remote_sha>` صريح (لا `--force-with-lease` مجرّداً: بلا القيمة يقيس ما التقطه الجلب الأخير لا ما يتوقّعه الكاتب)
- منع الدفع إذا تغيّر الرأس البعيد أو فشل `checkout`/`rebase`

**لم يُعالَج الآن بأمر صريح:** «لا توسّع شريحة PG لإصلاح هذا الغلاف الآن». فالتسجيل هو كامل المطلوب في هذه الجولة، والعلاج شريحةٌ مستقلّة.

**شرط الإغلاق:** غلافٌ يفرض البنود الخمسة، **ومُكذَّب بزرع**: سلسلةٌ بـ`;` بدل `&&` يجب أن تُسقِط اختباراً مُسمّى، وإلّا كان الغلاف وصفاً لا حارساً.

**المصدر:** `sahool-brain/log.md` (وقائع الجلسة) · حكم المالك 2026-08-08.

## LIVE-PG-01 — open (P2، رُصِدت 2026-08-08 بزرعٍ لم يُسقِط شيئاً)

**العطل:** `FORCE ROW LEVEL SECURITY` مُفعَّلة في الكتالوج (`relforcerowsecurity = true`) و**خامدة أثراً**: مالك الجداول `sahool_user` هو **superuser**، وsuperuser يتخطّى RLS مهما كان `FORCE`. مقيس على PG16 بعد `MANIFEST.txt` كاملاً:

```
$ psql -d sahool -U sahool_user -qAtc "select count(*) from water_ledger;"
6
```

بلا `app.current_tenant` وبلا أيّ سياق مستأجِر ⇒ كلّ الصفوف عبر كلّ المستأجِرين.

**كيف ظهر:** لم يظهر بقراءة. زرعُ `ALTER TABLE water_ledger NO FORCE ROW LEVEL SECURITY` على نسخةٍ من القاعدة **لم يُسقِط أيّ اختبار** — والزرع الذي لا يُسقِط شيئاً يُثبِّت وهماً.

**الأثر:** العزل الفعليّ يعتمد كلّيّاً على أنّ التطبيق يتّصل بدورٍ مقيَّد. وهذا شرطٌ **تشغيليّ** مُعلَن في تعليقِ هجرة (`migrations/v56_rls_dynamic_all.sql:27`) ولا تُنشئه هجرة ولا يحرسه شيء.

**لم يُصلَح عمداً:** إصلاحه تغييرُ نموذج أدوار (نزع superuser عن المالك أو نقل الملكيّة) يمسّ الترحيل والنشر؛ خارج نطاق شريحة إثبات الادّعاءات.

**ما فُعِل:** وظيفة `Live PG Proofs` تُنشئ `sahool_app` بـ`NOSUPERUSER NOBYPASSRLS`، و`test_the_app_role_is_provably_restricted` يقيس الاثنين **قبل** أيّ ادّعاء عزل.

**شرط الإغلاق:** إمّا مالكٌ غير superuser (فيصير الأثر قابلاً للرصد ويُرقَّى التأكيد من كتالوجيّ إلى سلوكيّ)، أو حارسٌ يفرض أنّ سلسلة اتّصال التطبيق في `docker-compose.v9.yml` لا تستعمل دور المالك.

**المصدر:** [`docs/architecture/live_pg_findings.md`](../../docs/architecture/live_pg_findings.md) · [`tests_v9/test_live_pg_fake_connection_debt.py`](../../tests_v9/test_live_pg_fake_connection_debt.py) · قياس على PG16.

## WORKER-JSONB-READ-ASSUMES-DECODED-01 — CLOSED (مُثبَتة بالتشغيل الحيّ، رُصِدت 2026-08-04)

**العطل:** asyncpg يُعيد `jsonb` **نصّاً** ما لم يُسجَّل codec، ومسبح هذا العامل لا يُسجّل شيئاً. فـ`dict(row["canonical_payload"])` رمى على كلّ حدث إسقاط:

```
ValueError: dictionary update sequence element #0 has length 1; 2 is required
```

**والأسوأ من الرمية تصنيفها:** ردّ نداء العامل يُصنّف `ValueError` **مدخلاً باطلاً دائماً** فيستدعي `msg.term()` — أي أنّ عيب فكّ ترميز في كودنا **يتخلّص من حدث صحيح** ويحمّل المنتِج وزره. ولو لم يرمِ الأوّل لكان `list(row["evidence_payload"])` على النصّ `"[]"` يُعطي `['[', ']']` — مشاهدتان مختلقتان **بصمت**.

**العلاج:** `decode_jsonb` — رُقّي من `_json` الخاصّ في `persisted_canonical_repositories.py` إلى اسم عامّ يستورده العامل، فتبقى **تعريفة واحدة** بدل سادسة مكرّرة.

**المصدر:** [`scripts/workers/canonical_execution_learning_worker.py`](../../scripts/workers/canonical_execution_learning_worker.py) · [`tests_v9/test_canonical_event_emission_contracts.py`](../../tests_v9/test_canonical_event_emission_contracts.py) · قياس على PG16.

## EVENT-SOURCE-IS-A-SERVICE-NAME-01 — CLOSED (مُثبَتة بالتشغيل الحيّ، رُصِدت 2026-08-04)

**العطل:** `events.source` عمود **enum بسبعة قيم** (`migrations/v11_events_bus.sql:47-48`)، وثلاثة كُتّاب كانوا يمرّرون **اسم خدمة/وحدة**:

| الملفّ | القيمة الممرَّرة |
|---|---|
| `persisted_canonical_repositories.py` | `'sahool-platform'` |
| `learning_feedback.py` | `'sahool-platform.learning_feedback'` |
| `irrigation_closed_loop_runtime.py` | `'sahool-platform.irrigation_closed_loop_runtime'` |

كلّها مرفوضة: `CheckViolationError: new row for relation "events" violates check constraint "events_source_check"`. أي أنّ **كامل سطح إصدار الأحداث** في مسار التعلّم القانونيّ — الإسقاط، وإغلاق الموسم، وإغلاق حلقة الريّ — لم يلمس قاعدة حقيقيّة قطّ.

**العلاج:** `EventSource.SYSTEM` (نفس القيمة التي يستعملها `irrigation_execution_request_port.py:61`)، وحارس تكافؤ يقارن **الـenum في الكود** بالقائمة المُستخرَجة من الهجرة نفسها — لا بقائمة أُعيدت كتابتها في الاختبار.

**حدّ صدق:** هويّة الوحدة المُصدِرة **لا موطن لها** في مخطّط `events` (لا عمود منتِج؛ و`actor_id` دلالته الفاعل لا المُنتِج). ما كانت تلك السلاسل تحاول قوله ضاع، ولم أخترع له عموداً — بند للمالك.

**المصدر:** [`migrations/v11_events_bus.sql:47-48`](../../migrations/v11_events_bus.sql) · [`api/event_bus.py`](../../services/sahool-platform/api/event_bus.py) `EventSource` · قياس على PG16.

## LIVE-GATE-TEARDOWN-DELETES-APPEND-ONLY-01 — CLOSED (مُثبَتة بالتشغيل الحيّ، رُصِدت 2026-08-04)

**العطل:** تنظيف جولة JetStream كان يحذف من جدولين **append-only بالعقد**، فترفضه محفّزات القاعدة:

```
events                    -> trg_append_only_events
canonical_salinity_states -> canonical_salinity_states_append_only
```

**فالبوّابة لم تكن قادرة على الخروج بصفر أبداً:** الرحلة نفسها **نجحت** — الحدث كُتِب، والحالة القانونيّة واحدة، وسجلّ الصادر واحد، وإعادة التشغيل لم تُكرِّر — ثمّ ماتت وهي **تنظّف بعد نفسها**، مرّتين، جدولاً بعد جدول.

**العلاج:** لا يُحذَف ما لا يُحذَف. يُحذَف صفّ الطلب وحده (المتغيّر الوحيد)، ويُعلَن الباقي في حقل `residue` داخل الحقائق المنشورة. إضعاف المحفّز ليتمكّن اختبارٌ من الترتيب كان سيكون الإصلاح الخاطئ: السجلّ المناعيّ صحيح والتنظيف هو الخاطئ.

**ودرس اكتشاف داخل الاختبار نفسه:** أوّل صياغة لحارس «لا تحذف من append-only» مسحت `CREATE TRIGGER` نصّاً فوجدت **٢٤ جدولاً** وفاتها `events` — لأنّ `v9_append_only_enforcement.sql` يبني محفّزاتها **ديناميّاً** من `tables TEXT[] := ARRAY[...]` عبر `EXECUTE format()`. حارسٌ يمسح شكلاً واحداً يُبلِّغ نظافةً وهو أعمى عن أهمّ جدول.

**المصدر:** [`scripts/e2e/canonical_projection_jetstream_roundtrip.py`](../../scripts/e2e/canonical_projection_jetstream_roundtrip.py) · [`migrations/v9_append_only_enforcement.sql`](../../migrations/v9_append_only_enforcement.sql).

## LIVE-EVIDENCE-SHA-UNBOUND-TO-A-CLEAN-TREE-01 — CLOSED (رُصِدت 2026-08-04)

**العطل:** مُشغّل الأدلّة يثبّت `git rev-parse HEAD` في الشاهد، **ولا يفحص نظافة الشجرة**. فأوّل مرّة اخضرّت البوّابة كانت ثلاثة إصلاحات إنتاجيّة **غير ملتزَمة**، والشاهد ختم `e57570f3` — وهي شجرة **لا يمكن أن تكون قد مرّت**.

**ولماذا هذا أخطر من الأحمر:** الأحمر يُوقِف؛ والأخضر المنسوب إلى الالتزام الخطأ يدخل الأرشيف بوصفه إثباتاً. والـSHA لا يُسمّي تشغيلاً بل **شجرة**؛ فإن اختلفت الشجرة سقط كلّ معنى الختم.

**العلاج:** رفض مُغلَق عند الفشل قبل أيّ فحص، **بعد** حلّ الـSHA كي لا يُهرَّب `EXPECTED_SHA` صريحٌ فوق شجرة متّسخة.

**المصدر:** [`scripts/e2e/run_canonical_execution_learning_live_gate.sh`](../../scripts/e2e/run_canonical_execution_learning_live_gate.sh).


## CAPABILITY-IMPACT-TOOLS-DISAGREE-01 — CLOSED (مُقاسة على تجهيزة ثابتة، رُصِدت 2026-08-04)

**الصنف:** أداتان تُجيبان سؤالاً واحداً — «ما الذي يمسّه تغييري؟» — بجوابين مختلفين، إحداهما ما يوصي `docs/capabilities/CAPABILITY_GOVERNANCE.md` بتشغيله، والأخرى ما يحجب الدمج.

**القياس على تجهيزة ثابتة من عشرة مسارات** (واجهة المنصّة · هجرة · عامل · سكربتا e2e · compose · الواجهة الأماميّة):

```
direct      legacy=0   gate=5    (DEC-006, GIS-003, INT-002, SEC-001, WX-006)
affected    legacy=0   gate=12
```

**والفرق ليس معرّفاً شارداً بل طبقة كاملة:** `capability_impact.py` كان يمشي على قوائم `capabilities/registry` المصونة يدويّاً وحدها (`services`/`tests`/`ui_consumers`/`evidence`)، بينما تقرأ البوّابة معها `capability_mapping.json` المولَّد — خريطة المسارات الحقيقيّة إلى القدرات بأبعادها (`mapping:backend` · `mapping:events` · `mapping:web` · `mapping:other_evidence`). كلّ قدرة فاتت الأداة وصلت عبر تلك الخريطة، ولذلك **تتّسع الفجوة باتّساع الفرق** لا تبقى ثابتة.

**ولماذا يهمّ:** جوابٌ أصغر من الحقيقة هو كيف يفلت تغيير من إعلان الأثر؛ ومساهمٌ يثق بالأداة يُحجَب ببوّابة تقتبس رقماً آخر — وهو ما وقع لي حرفيّاً في PR #785.

**العلاج:** محرّك واحد لا ثانٍ مُصحَّح. `capability_impact.py` صار غلافاً رفيعاً على `pr_capability_impact_gate.impact` + `current_snapshot`، ومصدر الحقيقة هو محرّك البوّابة لأنّه يقرأ الخريطة المشتقّة من الشجرة لا قائمة تُصان بيد.

**التكذيب:** أُعيدت النسخة القديمة إلى الشجرة وشُغّلت ⇒ سقط اختبارا التكافؤ وعدم-الازدواج؛ استُعيدت ⇒ ثلاثة خضراء. ومع اختبار التكافؤ اختبارُ **عرضٍ للتجهيزة** يمنع الخضرة الفارغة: تجهيزة لا تُطابِق شيئاً تجعل التكافؤ صحيحاً بلا معنى.

**المصدر:** [`tests_v9/test_capability_impact_parity.py`](../../tests_v9/test_capability_impact_parity.py) · [`scripts/ci/capability_impact.py`](../../scripts/ci/capability_impact.py).

## JSON-SCHEMAS-WITH-NO-VALIDATOR-01 — CLOSED بمُتحقِّق موحَّد (رُصِدت 2026-08-04، أُغلِقت 2026-08-05)

**الصنف:** مصنوعة تبدو بوّابةً ولا تُطلِق أبداً — نفس صنف `npm run lint` الزخرفيّ الذي أُغلِق في PR #780، بشكل آخر.

**القياس — والرقم صُحِّح من ٤ إلى ١٥:** أوّل عدّ لي طابق الملفّات التي **تُعلِن** الميتا-مخطَّط
(`"$schema": "https://json-schema.org…`) فوجد أربعة. والعدّ بالاسم يعطي **خمسة عشر**:

```
shared/contracts/soil/{soil_observation,soil_profile_snapshot}.v1.schema.json
shared/contracts/remote_sensing/schemas/*.schema.json        ← تسعة
shared/contracts/indicator_observation.schema.json
services/sahool-platform/api/food_grain_varieties_verified_v1.schema.json
capabilities/schema/capability-registry.schema.json
docs/capability-registry/schema/capability-card.schema.json
```

**والفرق نفسه فجوة داخل فجوة:** أحد عشر ملفّاً اسمه `*.schema.json` **لا يُعلِن أيّ
ميتا-مخطَّط**، فلا يُعرَف بأيّ مواصفة يُقرَأ. ورقمي الناقص كان **قياساً بمعيار أضيق من
السؤال**: بحثتُ عمّا يُعلِن الميتا-مخطَّط وأجبتُ عن «كم مخطَّطاً في المستودع».

**ولا مُتحقِّق لأيٍّ منها:**

```bash
$ python3 -c "import jsonschema"                    → ImportError
$ grep -rn "import jsonschema\|from jsonschema" .   → صفر
$ grep "^jsonschema" requirements*.txt              → صفر
```

فالمخطَّطات موجودة، والمكتبة غير مثبَّتة ولا مُعلَنة تبعيّةً، ولا سطر واحد يستوردها. أي أنّ **أربعة عقود بيانات تُقرَأ كأنّها محروسة وهي غير محروسة** — وقارئُ المخطَّط يفترض أنّ الملفّ المطابق له مُتحقَّق منه.

**كيف ظهرت:** لم أفتّش عنها. حزمة مرفوعة اقترحت إضافة مخطَّط **خامس** (`preflight_required.schema.json`)، ففحصتُ ما إذا كان سيُتحقَّق منه — فظهر أنّ الأربعة القائمة كذلك.

**ولذلك رُفِض المخطَّط الخامس — وبدقّة أعلى بعد تصحيح:** الحزمة تحمل مُتحقِّقاً **مكتوباً صحيحاً** (`test_json_schema_validation_standard`، يستورد `jsonschema` ويفشل صريحاً لا صامتاً). فليست إهمالاً بل **تبعيّة ناقصة**: الاختبار سليم، ونتيجته على هذه الشجرة **فشل** لأنّ المكتبة غير مثبَّتة ولا مُعلَنة. والفرق يهمّ لأنّ العلاج مختلف — الأوّل يُصلَح بكتابة مُتحقِّق، والثاني بإعلان تبعيّة.

وهذا **يُقوّي** الفجوة لا يُضعفها: أربعة مخطَّطات قائمة بلا أيّ مُتحقِّق، وخامسٌ يأتي بمُتحقِّق بلا مكتبة.

**وخطأ مراجعة منّي في الطريق:** قلتُ أوّلاً إنّ الحزمة «بلا مُتحقِّق». السبب أنّي قارنتُ ملفّاتها بـ`diff` مقابل الحزمة **السابقة لها مباشرةً** فقال «unchanged»، ولم أفتح الملفّ — وقد تغيّر قبل ذلك بحزمة (`09c533ce` → `a97f69ff`). **`diff` مقابل الجار الخطأ يُنتج ثقةً كاذبة**؛ قارِن مقابل ما راجعتَه فعلاً لا مقابل ما قبله.

المبدأ الذي حمله المخطَّط («لا مفتاح تشغيليّ مجهول») أُخِذ ونُفِّذ في `tests_v9/test_local_preflight_contract.py` حيث يعمل فعلاً. **والاعتراض الثاني قائم:** المخطَّط يرفض `adjudicated_on` الذي يُلزِم به `claim_base_guard` (مُثبَت بالتكذيب) — واختبارٌ يعمل على مخطَّط خاطئ يُثبّت الخطأ بإحكام أكبر.

**وعيب ثانٍ في المخطَّط المقترح يستحقّ التسجيل:** نمط `patternProperties` فيه يرفض كلّ مفتاح خارج `schema|version|note_ar|required_*` — ومنها **`adjudicated_on`** الذي **يُلزِم به `claim_base_guard`** كلّ مصنوعة `decided` تحت `docs/architecture/`. قاعدةٌ تمنع ما تفرضه الحوكمة ليست أشدّ بل خاطئة.

**ما يلزم لإغلاقها (قرار مالك):** إمّا إعلان `jsonschema` تبعيّةً ووصل مُتحقِّق موحَّد
بالخمسة عشر، أو حذف ما لا يُراد حراسته. الحالة الوسطى — مخطَّطات بلا مُتحقِّق — هي
الوحيدة غير المقبولة.

**والحزمة العاشرة أنزلت نصف العلاج صحيحاً:** اقترحت ملفّ متطلّبات جديداً
(`requirements-preflight.txt` — **ملفّ الحزمة، لم يُعتمَد في هذا المستودع**) يُعلِن
`pytest>=8.0` و`jsonschema>=4.20`. وهو العلاج المطابق للتصنيف المُصحَّح — تبعيّة ناقصة
تُعالَج بإعلان تبعيّة، لا بكتابة مُتحقِّق ولا بتليين اختبار. عند الإغلاق أُعلِنت
`jsonschema>=4.20.0` في **`tests_v9/requirements-test.txt`** (الموضع القائم) بدل استحداث
ملفّ ثانٍ. يبقى النصف الآخر: **وصل مُتحقِّق بالخمسة عشر القائمة**، وهو قرار مالك لأنّه
يمسّ عقوداً في أربعة مجالات.

**المصدر:** قياس محلّيّ 2026-08-04 · الحزم المرفوعة (٦ و٧).

**الإغلاق (2026-08-05) — مُتحقِّق واحد لا أربعة:**

`scripts/ci/schema_validation_guard.py`. الجرد **يُشتقّ** من `git ls-files '*.schema.json'`
لا من قائمة، والسياسة (`docs/architecture/schema_validation_policy.json`، مُصنَّفة
`decided`) تُعلِن **نوع** المقبول لا **أسماء** الملفّات: الـdrafts المسموحة · قاعدة `$ref`
المحلّيّ · منع الشبكة · واستثناءات مؤرَّخة تُفشِل الحارس عند انقضائها.

**والأحد عشر عولجت بتحديد الـdraft لا بقيمة عمياء:** القياس أظهر أنّها تستعمل `$defs`
(2019-09 فما فوق) و**صفر** مفتاح تختلف دلالته بين 2019-09 و2020-12 (`additionalItems` ·
`prefixItems` · `$recursiveRef` · `items` كمصفوفة)، وتصحّ تحت كليهما. فإعلان 2020-12 —
المطابق للأربعة المُعلَنة سلفاً — **محايد دلاليّاً ومقيس**. الفرق سطر واحد لكلّ ملفّ، بلا
إعادة تنسيق.

**والوصل مركزيّ لا مجالّيّ:** خطوة `--check` في وظيفة *Repository Structural Lint*،
فاكتشفتها المكنسة **تلقائيّاً** من الـworkflow (`[('scripts/ci/schema_validation_guard.py',
['--check'])]`) بلا تسجيل يدويّ. السلسلة مُثبَتة بزرع عطل حقيقيّ (حذف `$schema` من
`soil_observation.v1`): الحارس يفشل بـ`NO_META_SCHEMA` ⇒ `verify_all_generated --check`
⇒ `preflight` ⇒ CI.

**شروط القبول، مقيسة:**

```
15/15 schemas discovered      15/15 declare $schema      15/15 validated by one validator
0 unknown meta-schemas        0 external/unresolved refs  0 network dependency
```

**التكذيب:** ستّ حالات فساد مزروعة (JSON تالف · `$schema` مفقود · ميتا-مخطَّط مجهول ·
مخطَّط غير صالح لـdraftه · `$ref` محلّيّ مفقود · `$ref` خارجيّ) + ملفّ صحيح يمرّ — ١٤
اختباراً في `tests_v9/test_schema_validation_guard.py`.

**والتبعيّة مُعلَنة لا ضمنيّة:** `jsonschema>=4.20.0` في `tests_v9/requirements-test.txt`
(نظيفة عند `pip-audit`) وخطوة تثبيت صريحة في الوظيفة — لأنّها لا تُثبِّت شيئاً آخر.
والحارس يخرج بـ`2` عند غيابها بدل أن يتخطّى صامتاً.

**حدّ صدق:** هذا يُثبت أنّ المخطَّطات **صالحة كمخطَّطات**، لا أنّ البيانات التي تصفها
مُتحقَّق منها عند التشغيل. ربط كلّ مخطَّط بمُنتِجه/مستهلِكه سؤال آخر لم يُقَس.

## `UNIT-SUITE-RUN-TWICE-01` — الجناح يعمل مرّتين في وظيفة واحدة (مُغلَقة 2026-08-05)

**الحالة:** مُغلَقة · **المصدر:** قياس جولة حدث PR على #788 + قياس محلّيّ مزدوج على `82a6e5ae`.

`.github/workflows/ci.yml` (وظيفة *Unit Tests*) حمل خطوتين تُشغّلان الجناح نفسه بنفس
العلامة ونفس التغطية: `pytest -v -m unit --cov=services --cov-report=…` ثمّ
`pytest -m unit --cov=services --cov-fail-under=43 -q`.

| المقيس | القيمة |
|---|---|
| `Unit Tests` في CI (#788) | ١٩:٠٩ |
| الجناح محلّيّاً بلا تغطية | ٤:٠٢ |
| الجناح محلّيّاً بالتغطية | ٦:٣٥ |
| ٦:٣٥ × ~١.٤٥ × ٢ | **١٩:٠٦** ⇒ يُطابق |

**العلاج:** `--cov-fail-under=43` صارت راية على الاستدعاء الواحد. لا تنازل: الأرضيّة ٤٣
باقية · `coverage.xml` باقٍ إلى codecov · تقرير `term` باقٍ.

**الحارس:** `tests_v9/test_ci_suite_invocation_budget.py` — يعدّ استدعاءات الجناح لكلّ
وظيفة (استدعاءٌ بلا مسارات صريحة)، مُثبَت بثلاث زراعات نُفِّذت.

**حدّ الصدق:** هذا يقيس **التكرار داخل وظيفة**. لا يقيس ما إذا كانت وظيفتان مختلفتان
تُشغّلان الجناح نفسه، ولا يقترح ذلك.

## `UNIT-SUITE-FLAKE-API-VERSIONING-01` — تقلّبٌ غير مُثبَت السبب (مفتوحة)

**الحالة:** مفتوحة · **المصدر:** جولة محلّيّة على `82a6e5ae` (2026-08-05).

`tests_v9/test_api_versioning_policy_guard.py::test_new_unversioned_route_is_rejected_without_adjudication`
فشل مرّةً واحدة في جولة كاملة، ونجح: منفرداً (١١ث) · بملفّه كاملاً (٢٧ ناجحاً) · وفي
جولة التغطية على الشجرة نفسها. الجولة الفاشلة بدأت مباشرةً بعد قتل جولةٍ في منتصفها.

الاختبار **يكتب في الشجرة الحقيقيّة**: مِسبار غير متعقَّب في `api/routers/` + إعادة توليد
مصنوعة متعقَّبة، ويستعيد في `finally` — وتعليقه هو نفسه يوثّق أنّ `finally` لا ينجو من
القتل (سبق أن تسرّب مِسباره إلى شجرة اعتماد خارجيّة وأنتج NO-GO بـ١٩ إخفاقاً كاذباً).

**غير مُثبَت:** لم يُعَد إنتاج الفشل. لا يُغلَق بترجيح، ولا يُنسَب إلى التزام بعينه.
**ما يلزم لإغلاقه:** إعادة إنتاج محكومة (جولة كاملة بعد قتل مقصود عند هذا الاختبار)،
أو عزل المِسبار عن الشجرة الحقيقيّة بحيث لا يعتمد الاستعادة على `finally`.

## `BRAIN-APPEND-ONLY-TRUNCATION-GUARD-01` — سجلّ إلحاقيّ فُرِّغ وكلّ البوّابات خضراء (مُغلَقة 2026-08-05)

**الحالة:** مُغلَقة · **المصدر:** قياس محلّيّ على `ddf8716f` + شهادة حيّة من وكيل آخر (SHA خارجيّ).

**الواقعة:** `sahool-brain/log.md` ذهب من **١٬٣٨٣٬٣٦٨ بايت إلى صفر** في `cb6598fe` (#789)
وبقي فارغاً على `main` نحو خمس ساعات. لم يُحجَب شيء.

| الالتزام | بايت | أسطر |
|---|---|---|
| `32efdc90` | ١٬٣٨٣٬٣٦٨ | ٥٠٢٥ |
| `cb6598fe` | **٠** | **٠** |
| `ddf8716f` (بعد دمج #791) | ١٬٣٩٢٬٥٤٥ | ٥٠٥٤ |

**والاستعادة مُثبَتة لا مفترَضة:** محتوى `32efdc90` **بادئة بايتيّة تامّة** لـ`main` — ولا
بايت فُقِد، بل زِيد ٩٬١٧٧.

**لماذا لم يُمسَك:** الحرّاس الثلاثة تفحص الادّعاءات والانتقالات لا الحجم ·
`resolve_merge_conflicts` يعرف التصنيف لكنّه لا يعمل إلّا عند تعارض مُبلَّغ، **والدمج
الصامت لا تعارض فيه** · و**بصمة ملفّ فارغ بصمة صحيحة** فالمولّدات تختمها راضية.

**العلاج:** `scripts/ci/brain_append_only_guard.py` موصولاً في `no-report-only-change.yml`.
يفحص **كلّ التزام مقابل كلّ والد له** — ووعي الدمج جوهر الأمر: النجاة وقعت لأنّ والداً
يحمل الملفّ والآخر لا، ففحصٌ مقابل **أحد** الوالدَين يمرّ ومقابل **كليهما** يُمسِك.

**والخاصّيّة مقيسة لا مفترَضة.** على **٢٠٢** زوج (التزام، والد):

| الملفّ | أزواج | تقلّص | حُذِف | أكبر تقلّص |
|---|---|---|---|---|
| `log.md` | ٢٠٢ | **١** | ٠ | ١٬٣٨٣٬٣٦٨ ← الحادثة |
| `gaps/registry.md` | ٢٠٢ | ١ | ٠ | ٥٧ |
| `decisions/ledger.md` | ٢٠٢ | ٠ | ٠ | ٠ |
| `hot.md` | ٢٠٢ | ١ | ٠ | ٤٣٢ |

قاعدة **البادئة البايتيّة** كانت ستُسقِط **١٤١ من ٢٠٢** — لأنّ `registry.md` يحمل تحديثات
حالة يوجبها `CLAUDE.md` و`hot.md` لقطة تُعاد كتابتها بالتصميم. فحارسٌ يُطلِق على العمل
الطبيعيّ يُدرّب قارئه على تجاوزه: **التقلّص يحجب، وفقدُ البادئة يُبلَّغ**.

**مُثبَت بالتكذيب أربع مرّات نُفِّذت:** فحص والد واحد · جعل التقلّص إرشاديّاً · تصليب
قائمة الملفّات · فصله عن الـworkflow. وعلى الحادثة نفسها: `32efdc90..cb6598fe` يسقط،
و`cb6598fe..ddf8716f` يمرّ، ودمجٌ اصطناعيّ يأخذ الجانب الفارغ يسقط بوالدٍ واحد من اثنين.

**حدّ الصدق:** يحرس **الحجم والوجود**، لا المحتوى. سطرٌ يُستبدَل بسطر أطول يمرّ، وهو
مقصود — التحرير وسط الملفّ مقيسٌ أنّه طبيعيّ لملفّين من الأربعة. ولا يحرس ملفّات دماغ
خارج تصنيف `resolve_merge_conflicts.APPEND_ONLY`.

## `MUTATION-VERDICT-CONTRADICTS-ITS-OWN-DIAGNOSIS-01` — تصنيف يقلب ما حدث (مُغلَقة 2026-08-05)

**الحالة:** مُغلَقة · **المصدر:** سجلّ الوظيفة `92411900283` على #795 + قياس محلّيّ.

`guard_mutation_guard --run` أسقط بناءً على `claim_base_guard.py[4]` وطبع:

```
التصنيف: STABLE_WRONG_TEST
إعادة التشخيص: expected_red · expected_red · expected_red
الساقط فعلاً: test_a_measured_stamp_does_not_satisfy_a_decision
```

**الإعادات الثلاث كلّها `expected_red`** — أي أنّ الطفرة **تعمل** والاختبار المُسمّى
يسقط. فلا شيء «مستقرّ» ولا «الاختبار خاطئ»؛ الشذوذ في الملاحظة الأولى وحدها.

**السبب:** `stable = len(set(repeats)) == 1` تقيس اتّفاق الإعادات **مع بعضها** لا مع
الملاحظة الأولى، فاتّفاقٌ على «الصحيح» كان يُصنَّف «خطأً مستقرّاً».

**والحادثة موثَّقة في مصدر الحارس نفسه** منذ واقعة سابقة: «أخفق هذا الفرع مرّةً على
`claim_base_guard.py[4]` ولم يتكرّر في ثلاثة تشغيلات» — فهي **الثانية** على الطفرة نفسها.

**العلاج:** تصنيف ثالث `FLAKY_FIRST_OBSERVATION` حين تكون كلّ الإعادات `expected_red`.
**ويبقى حاجباً** — فحصٌ يخضرّ بإعادة التشغيل يُدرّب قارئه على إعادة التشغيل بدل القراءة —
لكنّ الاسم يصف الواقعة بدل أن يقلبها.

**مُثبَت بالتكذيب:** إعادة الترتيب القديم تُسقِط
`test_repeats_that_all_say_expected_red_are_not_called_stable_wrong_test`.

**حدّ الصدق:** هذا يُصحّح **التسمية** لا يُزيل الشذوذ. لماذا شذّت الملاحظة الأولى مرّتين
على هذه الطفرة بالذات **غير مُثبَت**، ولا يُغلَق بترجيح. ما يلزم لإغلاقه: إعادة إنتاج
محكومة تُميّز بين حالة الشجرة وترتيب الاختبارات وبيئة العدّاء.

### الملاحظة الثالثة (2026-08-05، على #798) — دليلٌ جديد يُضيّق السبب

وقعت الرقيعة نفسها للمرّة **الثالثة** على `claim_base_guard.py[4]`، وصنّفها العلاج الذي
أُضيف في #795 تصنيفاً صحيحاً: `FLAKY_FIRST_OBSERVATION` (الإعادات الثلاث كلّها
`expected_red` بالاسم الصحيح). **فالتسمية صارت تصف الواقعة** — وهذا ما كان يُقاس.

**والجديد أنّ السجلّ يحمل توقيعاً محدَّداً لم يُلاحَظ قبلاً:**

```
المُتوقَّع : test_a_decision_stamp_does_not_satisfy_a_measurement   ([4])
الساقط    : test_a_measured_stamp_does_not_satisfy_a_decision       ([3])
```

الطفرتان **مرآتان**: `[3]` تجعل فرع `decided` يقبل ختم قياس، و`[4]` تجعل فرع `measured`
يقبل تاريخ حكم. والساقط في الملاحظة الأولى هو **اختبار الطفرة السابقة لها مباشرةً** — أي
أنّ أثر `[3]` كان حاضراً أثناء تشغيل `[4]`. هذا توقيع **تسرّب حالة بين طفرتين متتاليتين**،
لا عشوائيّة.

**وما يُضعِف الفرضيّة ولا يُسقطها:** لو كانت الطفرتان معاً في الملفّ لسقط اختباران، والسجلّ
يقول `1 failed, 27 passed`. فالتفسير الكامل غير مُثبَت بعد.

**وما نُفِي بالقياس:** كلا الاختبارَين نقيّ (`tmp_path`، بلا قراءة تاريخ git)، فلا علاقة
للاستنساخ الضحل — وهو أوّل ما يُشتبه به في هذا المستودع.

**ولا يُعاد إنتاجها محلّيّاً:** ثلاث تشغيلات كاملة لـ`--run` على هذه الشجرة خضراء. الفارق
بيئة العدّاء، ولم يُعزَل بعد.

**ما يلزم لإغلاقها (كما هو، مع خطوة أدقّ):** إعادة إنتاج محكومة تُقارن الملفّ **بعد استعادة
كلّ طفرة ببصمة** — لا بالثقة في أنّ الاستعادة تمّت. أي: بصمة قبل الزرع، بصمة بعد الاستعادة،
وفشلٌ مُعلَن عند اختلافهما. **الحارس الذي يزرع ويستعيد يحتاج أن يُثبت استعادته.**

## `WOFOST-WHAT-IF-SEVEN-DEFECTS-01` — سيناريو زخرفيّ وأرقام تدّعي ما لا تعنيه (مُغلَقة جزئيّاً 2026-08-05)

**الحالة:** ستّة مُغلَقة · واحد قرار مالك مفتوح · **المصدر:** تقرير الشهادة الحيّة (SHA
`93ed3f47`) + قياس محلّيّ بتشغيل المحرّك بطقس محقون (١٥٠–٢٠٠ يوماً، بلا شبكة).

`/api/v1/simulate/what-if` (`services/sahool-platform/api/routers/simulate.py`) كان يُخرِج
استجابةً كاملة الحقول لا تحمل أيّاً من دلالاتها المُعلَنة. كلّ بند أدناه **مقيس**، لا مُستنتَج:

| العطل | القياس |
|---|---|
| المحرّك **يُعيد** `{"error": ...}` ولا يرفع ⇒ `except` لم يعمل قطّ | الاستجابة `available: true` وكلّ أرقامها `null` |
| `scenario` حرّ يُعاد صدىً ولا يُقرأ عند البناء | `reduce_irrigation` و`no_irrigation` ينتجان الأرقام **نفسها بالضبط** |
| محصول مجهول ⇒ قمح صلب صامتاً | «محصول لا وجود له» ⇒ ٩.٧٨٨ ط/هـ = رقم القمح حرفيّاً |
| تربة مجهولة ⇒ `loam` صامتاً | كذلك |
| تاريخ غير صالح ⇒ `date.today()` | يُحاكى موسمٌ غير المطلوب ويُنسَب إلى تاريخ المستخدم |
| نصّ الاستثناء يعود إلى العميل | `f"تعذّرت المحاكاة (طقس/نموذج): {e}"` |
| `water_saved_mm` طرحُ `irrigation_needed_mm` بين الفرعين | ٨١٣.٨ − ٧٣٩.٩ = **٧٣.٩ = ٠.١ × الطلب** |

**القياس الحاسم على البند السابع:** `engine.py:425` يحسب
`total_irrigation = max(0, etc − rain)` مضروباً في `1.1` حين `irrigation` صادقة. و
`total_etc_mm` **متطابق** بين الفرعين (٧٣٩.٩ في الحالتين) لأنّ `etc = et0·kc·cfet` دالّةُ
طقسٍ ومرحلةٍ فقط. فالفرق بين الفرعين هو **المعامل وحده**: «الماء الموفَّر» كان دائماً
عُشر الطلب الموسميّ، يكبر كلّما جفّ الموسم، ولا يعلم بالسيناريو ولا بالماء المُطبَّق.
فالرقم لم يكن «مقلوباً» — كان **معاملاً بلا دلالة**، وهذا تصحيحٌ لتشخيصي الأوّل.

**الإغلاق:** نسبة ريّ حقيقيّة `irrigation_fraction` تُمرَّر إلى المحرّك ويُراكِم بها الماء
**المُطبَّق فعلاً** (`irrigation_applied_mm`، بلا أيّ معامل) · `scenario` صار `Literal`
بثلاث قيم لكلٍّ نسبة مُعلَنة · فشلٌ مغلق على مخرَج المحرّك لا على الاستثناء · رفض `422`
للتاريخ الفاسد · رمز ثابت + `correlation_id` بدل نصّ الاستثناء · احتياط البارامترات باقٍ
(منعُه يكسر نشراً شرعيّاً) لكنّه **مُفصَح** بـ`parameter_resolution.degraded` · و
`water_saved_mm` مشتقّ من المُطبَّق مع `water_saved_basis` و`water_use_direction`، **بلا قصٍّ
عند الصفر** (نسبة أقلّ قد تُشغّل عتبة الإجهاد أكثر؛ الزيادة تُعلَن سالبةً).

**مُثبَت بالتكذيب تسع مرّات نُفِّذت** (`tests_v9/test_wofost_what_if_contract.py`، ١٩ حالة
تحقن الطقس وتؤكّد القيم النهائيّة): تعطيل فحص `error` · إعادة الريّ بولياناً · تثبيت
`crop_known`/`soil_known` · إعادة `pd = today()` الصامت · إعادة تسريب نصّ الاستثناء ·
إعادة الطرح على `irrigation_needed_mm` · قصّ الزيادة عند الصفر · إعادة `scenario: str`.

**والزرعة الثانية مرّت في الجولة الأولى** — أكّدت أنّ توكيدي قارن «التقليل» بالطرف الأدنى
وحده، فزرعةٌ تُعيد الملء الكامل عند أيّ نسبة موجبة كانت تمرّ. صُلِّب إلى الحصر بين الحدّين
(`a_none < a_half < a_full`). **زرعةٌ لا تُنتِج العطل تُثبِّت وهماً لا خاصّيّة.**

**حدّ الصدق:** الغلّة لا تتحرّك بين ٠.٢٥ و١.٠ في هذا الطقس (٨.٨٧٩ في الأربع)، فـ
`recommended_action_helps` تُخرِج `false` لـ`reduce_irrigation` هنا. هذا **مقيس** لا مُصلَح:
عتبة الإجهاد في المحرّك تُبقي `water_factor` عند ١.٠ عند أيّ ملءٍ جزئيّ في هذا النظام.
هل ذلك سلوكٌ زراعيّ صحيح — سؤالٌ لم يُقَس ولا يُغلَق بترجيح.

**مفتوح — قرار مالك:** `WOFOST-IRRIGATION-EFFICIENCY-COEFFICIENT-01` — ما دلالة `* 1.1` في
`shared/wofost/engine.py:425`؟ إن كانت كفاءة تطبيق الريّ فموضعها حقلٌ مُسمّىً
(`application_efficiency`) لا فرعٌ داخل مقدار الطلب، ويُعاد اشتقاق «الماء الموفَّر» عليها.
أُبقِي المعامل كما هو: تغييره يحرّك كلّ رقم طلبٍ في المنصّة، وهذا ليس قراري.

## `VERIFY-ALL-GENERATED-WRITER-FLAG-MISMATCH-01` — جولة إغلاق ثالثة (٣ ⇒ ٢، 2026-08-05)

**الحالة:** مفتوحة بمدخلَين (كانت ثلاثة) · **المصدر:** `docs/architecture/generated_sweep_unmapped_generators.json`
· `scripts/ci/verify_all_generated.py:171` · `tests/architecture/test_verify_all_generated.py`.

**ورصدَته شريحة عملٍ عاديّة لا مسحٌ عن الحرّاس** — وهذا وجه الفائدة: تغييرٌ في محرّك
WOFOST أكسب `IRR-004` بُعد `events` (تغطية ٥ ⇒ ٦)، فانحرفت `capability_management_matrix.json`
و`--fix` **دارت ثلاث دورات كاملة (~١٥ دقيقة) بلا أن تستدعيه** ثمّ طبعت «لم تثبت
المصنوعات». السبب: يُعلن `--generate` في مصدره ولا تذكره الخريطة، فيُصنَّف `manual`.

**السبب المُسجَّل لاستثنائه كان صحيحاً عند قياسه وصار بائتاً.** الحقل `non_idempotent_3`
يقول: «تشغيل العلم على شجرة نظيفة يُغيّر ملفّاً في كلّ مرّة». أُعيد قياس الثلاثة **فرداً
فرداً لا تعميماً من عيّنة** (تشغيل العلم مرّتين متتاليتين ثمّ عدّ المتغيّر):

| السكربت | ملفّات متغيّرة بعد تشغيلين | الحكم |
|---|---|---|
| `capability_management_engine` | **٠** | السبب بائت ⇒ أُغلِق |
| `capability_registry_guard` | ١ (`capabilities/generated/capability_registry.csv`) | السبب قائم ⇒ يبقى |
| `runtime_environment_preflight` | ١ (مصنوعته — `RUNTIME-ENV-PREFLIGHT-STAMPS-THE-MACHINE-01`) | السبب قائم ⇒ يبقى |

**ولم يُوصَل في الطبقة صفر.** يقرأ خمس مصنوعات، والترتيب الأبجديّ يضعه **قبل ثلاث منها**
(`man` < `map` و`pa` و`re`)، فكان سيقرأ مدخلات بائتة ثمّ «يستقرّ» في الدورة الثانية
بمصادفة تكرار `--fix` لا بترتيب صحيح — حرفيّاً فخّ `platform_route_governance_attestation`
المُسجَّل في الملفّ نفسه. فوُضِع في `_ORDER_TIER = 1`.

**القياس بعد الوصل:** `--fix` تستقرّ في **دورة واحدة** (كانت لا تستقرّ في ثلاث)، و`--check`
يخرج بصفر على ٦٥ خطوة.

**مُثبَت بالتكذيب ثلاث مرّات نُفِّذت:** إسقاط الطبقة (فيعود قبل ثلاثة من مصادره) · إسقاطه
من `_GENERATE_FLAG` · إبقاؤه في أساس غير المُوصَّلين مع تسجيله (المصدران يتناقضان).

**حدّ الصدق:** خريطة «أيّ مولّد يملك أيّ مصنوعة» في الاختبار **مُعلَنة لا مُشتقّة** — لا
سجلّ واحد في الشجرة يربطهما. مدخلاتُ المحرّك وحدها مُشتقّة من بيانه، فتغييرها يُرى.

**والدرس الأعمّ:** **سببٌ مُسجَّل لا يُعاد قياسه يصير حاجزاً دائماً أمام إغلاقٍ صار
ممكناً.** الاستثناء كُتِب بقياسٍ صادق، وبقي سنةً تشريعيّةً بعد أن بطل — لا لأنّ أحداً
أخطأ، بل لأنّ لا أحد أعاد القياس. ولذلك سُجِّل التصحيح في الوثيقة نفسها بحقلٍ مسمّى، لا
بحذف الجملة القديمة.

## `CONTAINER-COMMAND-PATH-NOT-IN-IMAGE-01` — عاملٌ مُسجَّل لا يمكن أن يُقلِع (مُغلَقة 2026-08-05)

**الحالة:** مُغلَقة · **المصدر:** تقرير الشهادة الحيّة + قياس محلّيّ ·
`docker-compose.v9.yml:2561` · `services/sahool-platform/Dockerfile:33-34`.

`sahool-canonical-execution-learning-worker` يُشغّل
`python /app/scripts/workers/canonical_execution_learning_worker.py` ويفحص صحّته بالمسار
نفسه. والـDockerfile ينسخ **سطرَين فقط**: `shared/ → /app/shared/` و
`services/sahool-platform/ → /app/`. والعامل يسكن `scripts/workers/` في جذر المستودع.

**البرهان شاملٌ على مجموعة `COPY` كلّها** (ثلاثة أوامر، لا رابع): لا أمر منها يمكن أن
يضع ذلك المسار. النتيجة في الإنتاج: الحاوية تموت عند الإقلاع، و`restart: unless-stopped`
يُعيدها إلى الأبد، والفحص الصحّيّ يسقط بالسبب عينه.

**والاختبار القائم `test_worker_is_registered_in_compose` كان أخضر طوال الوقت** — يقرأ
نصّ compose ويؤكّد أنّ الاسم والمسار مذكوران. وهما مذكوران. «مُسجَّل» ليس «يعمل» (§٣.٢٧).

**وعطلٌ ثانٍ تحت الأوّل: النسخ وحده لم يكن ليكفي.** الصورة تنسخ **محتويات** جذر الخدمة
إلى `/app`، فـ`api/` تسكن `/app/api`. وحساب العامل كان
`ROOT = parents[2]` ثمّ `API_ROOT = ROOT/"services"/"sahool-platform"` — وداخل الصورة
ذلك `/app/services/sahool-platform`، مسارٌ لا وجود له. أي أنّ إضافة
`COPY scripts/ /app/scripts/` كانت ستُنتِج **إصلاحاً يبدو ناجحاً ويظلّ مكسوراً**.

**الإغلاق:** العامل انتقل إلى `services/sahool-platform/workers/`. عندها `parents[1]` هو
جذر الخدمة في الموضعين معاً — `services/sahool-platform` في المستودع و`/app` في الصورة —
فالشكلان يتطابقان ولا حاجة إلى فرعٍ لبيئة. وحُدِّث ١٠ مراجع (compose · بوّابة حيّة ·
`db_ownership.yml` · سبعة عقود اختبار).

**مُثبَت بالتشغيل في تخطيط صورةٍ محاكاة** (مبنيّ من مجموعة `COPY` حرفيّاً)، لا بادّعاء بنيويّ:

| الحالة | النتيجة المقيسة |
|---|---|
| الأصليّة (`/app/scripts/workers/…`) | الملفّ **غير موجود** ⇒ الحاوية تموت عند الإقلاع |
| «الإصلاح» الناقص (نُسِخ بحسابه القديم) | `ModuleNotFoundError: No module named 'api'` |
| بعد الإصلاح (`/app/workers/…`) | تجاوز الاستيراد، وسقط على **الاتّصال** بالقاعدة — المتوقَّع بلا قاعدة |

**الحارس العامّ:** `scripts/ci/container_command_path_guard.py` — كلّ مسار `.py` يُنفّذه
`command`/`entrypoint`/`healthcheck` يجب أن تضعه مجموعة `COPY` لصورة تلك الخدمة، بدلالات
`COPY` الحقيقيّة و`.dockerignore` و`build.context`. **وكان سيمنع واقعة WOFOST أيضاً**
(`cb6598fe`) — تلك أُغلِقت بعقدٍ خاصّ بها، وهذا يُغلق الخاصّيّة العامّة.

**مُثبَت بالتكذيب أربع مرّات نُفِّذت** (٣٩ طفرة على ١٠ حرّاس): ادّعاء الوجود بلا فحصه ·
تعطيل الفحص · صفر أزواج مفحوصة · إسقاط نسخ ملفّ→ملفّ.

**وطفرتي الأولى مرّت** — غيّرتُ فرعاً لا يمسّ ما يؤكّده الاختبار المُسمّى، فأعاد
`guard_mutation_guard` الحكم عليّ بحقّ. الثالثة في يومين: **زرعةٌ لا تُنتِج العطل تُثبّت
وهماً لا خاصّيّة**، والفرق أنّ الأداة صارت تقولها بدلاً من أن أكتشفها بالحظّ.

**وعيبٌ في حارسي كشفه عقدُه لا قراءتي:** `def audit(root=ROOT)` يُجمّد الجذر وقت تعريف
الدالّة، فلا يستطيع أحد إعادة تجذير الفحص ولا استجواب فرع «صفر أزواج». حارسٌ لا يُمكن
اختبار فشله المُغلَق ليس مُغلَقاً. صار الربط متأخّراً.

**حدّ الصدق:** يفحص مسارات `.py` وحدها — الأصداف والثنائيّات تأتي من الصورة الأساس لا من
`COPY`، فادّعاء غيابها يكون كاذباً. ولا يفحص `--from=` (نسخٌ من مرحلة بناء). و**لا يُبنى
شيء**: يقرأ مجموعة `COPY` ولا يشغّل `docker build`، فصورةٌ تحذف ملفّاً في `RUN` لاحقة تمرّ.
المقيس أربعة أزواج (خدمة، مسار) على ١٠٢ خدمة ذات `build` — والعدد يُطبَع في كلّ تشغيل
لأنّ أخضرَ بصفرِ أزواج هو الصفر الصامت نفسه.

## `BACKFILL-FAILURE-REASON-DISCARDED-01` — «فشل» بلا سبب، وعمودٌ يُقرأ ولا يُكتَب (مُغلَقة 2026-08-05)

**الحالة:** مُغلَقة · **المصدر:** تقرير الشهادة + قياس محلّيّ ·
`services/raster-service/backfill_scan_worker.py` · `db_persist.py:502` · `migrations/v144_backfill_runs.sql:66`.

`_process_scene_index` كان يُرجِع **`bool`**، فتنهار ثلاث حالات فشل متمايزة إلى `False`
واحد، ويُسجَّل السبب في سجلّ العامل ثمّ **يُرمى**. ثمّ يكتب المُستدعي
`UPDATE backfill_run_items SET status='failed', processed_at=now()` — ويترك عمود `error`
(القائم منذ `v144`) **`NULL`**.

| الحالة | ما كانت تُقرأ | ما صارت |
|---|---|---|
| استثناء أثناء المعالجة | `False` | `exception:<النوع>:<مُعرّف ربط>` |
| وظيفة لم تكتمل | `False` | `job_not_completed:<الحالة>` |
| **عولِجت ولم تُحفَظ** | `False` | `processed_not_persisted` |

**والثالثة أخطرها**، ويُحذّر منها تعليقٌ في المصدر نفسه: الصورة عولِجت وبقيت في
الذاكرة/القرص ولم تدخل `raster_assets` — عملٌ تمّ وأثرٌ ضاع، وكان لا يُميَّز عن انقطاع شبكة.

**والأسوأ أنّ جانب القراءة مبنيٌّ على وجود السبب:** `get_backfill_run_status` يختار `error`
صراحةً. فالواجهة تعرض حقلاً لا يصل إليه شيء — والمُشغِّل يرى «٣ فاشلة» بلا سبب واحد،
ويُحال إلى سجلّات حاوية قد تكون دُوِّرت. **العمود المقروء والفارغ ادّعاءٌ كاذب، لا دَين صامت.**

**والدليل أنّ الكاتب عرف أهمّيّة الحقل:** مسار «المشهد غير موجود في الكتالوج» يكتب
`scene_not_found_in_catalog_for_date`. المسار العامّ وحده لا يكتب — وهو الذي تمرّ منه كلّ
حالات الفشل الحقيقيّة.

**شكل ما يُكتَب — قرار متّسق مع `#796`:** رمزٌ ثابت + نوع الاستثناء + مُعرّف ربط في العمود،
والنصّ الكامل في السجلّ بالمُعرّف نفسه. العمود يُقرأ ضمن مستأجِر، ونصّ استثناء قد يحمل
سلسلة اتّصال؛ فالتشخيص يبقى ممكناً بلا تسريب.

**مُثبَت بالتكذيب خمس مرّات نُفِّذت** (`tests_v9/test_backfill_failure_reason_persisted.py`):
إسقاط `error` من تحديث الفشل · طيّ حالتَي فشل في واحدة · تسريب نصّ الاستثناء · إعادة النوع
حاملَ `bool` وحده · عطبٌ في مصدر المشروع.

**والزرعتان الرابعة والخامسة كشفتا عيبَين فيّ لا في الكود:**
- تجهيزتي كانت `except Exception: pytest.skip` مطلقاً، فزرعةٌ تكسر النوع جعلت الاختبارات
  **تتخطّى** بدل أن تحمرّ — fail-open كامل، وهو صنف «الطفرة تُسمّي اختباراً قابلاً
  للتخطّي» المقيس في هذا المستودع قبلاً. صار التخطّي مقصوراً على **تبعيّة طرف ثالث** غائبة؛
  وكلّ عطبٍ في وحدة مشروع يفشل.
- وكاشفُ الزرعات عندي صنّف `1 error` بوصفه «مرّ»، لأنّه يبحث عن `failed` وحدها. **أداةُ
  قياس التكذيب تحتاج تكذيبها هي أيضاً.**

**حدّ الصدق:** الأسباب مُثبَّتة **بالمصدر المُحلَّل** لا بتشغيل العامل مقابل PostgreSQL —
فما قِيس أنّ كلّ `UPDATE` يضع `failed` يضع `error` معه، لا أنّ صفّاً حقيقيّاً حمل سبباً في
قاعدة حيّة. ولم تُصلَح أعطالُ التشغيلة (`backfill_runs.error`) لأنّها كانت تُكتَب أصلاً
(السطر ١٧٦).

### الإغلاق (2026-08-05) — السبب الجذريّ **مُثبَت بإعادة إنتاج محكومة**، لا مُرجَّح

بعد الملاحظة الثالثة عُزِل السبب وأُعيد إنتاجه عمداً ثمّ شُفِي:

**القياس الذي حسمه:** بايثون يُبطِل `.pyc` بـ**(mtime, size)** لا بالمحتوى. وطفرتا
`claim_base_guard.py[3]` و`[4]` هما — بالقياس على كلّ الطفرات الثمانِ لذلك الحارس —
**الزوج الوحيد المتساوي الطول**: ٧١٨٨ حرفاً لكلٍّ (`+9` عن الأصل ٧١٧٩)، لأنّ إحداهما
`d_keys → d_keys + m_keys` والأخرى `m_keys → m_keys + d_keys`. فحين تقع كتابتاهما داخل
دقّة الطابع الزمنيّ نفسها، يقرأ المُشغِّل الفرعيّ **بايتكود `[3]`** أثناء تشغيل `[4]`.

| ما يُتوقَّع | ما يقع | التوقيع |
|---|---|---|
| يسقط `test_a_decision_stamp_does_not_satisfy_a_measurement` (`[4]`) | يسقط `test_a_measured_stamp_does_not_satisfy_a_decision` (`[3]`) | `1 failed, 27 passed` |

وهو **حرفيّاً** ما سجّله الـCI في الملاحظات الثلاث.

**إعادة الإنتاج المحكومة** (بتثبيت `mtime` بين الكتابتَين، وهو ما يفعله عدّاءٌ سريع مصادفةً):

```
── بلا PYTHONDONTWRITEBYTECODE
   [4] المتوقَّع=..._a_measurement   الساقط=['..._a_decision']   ✗ غير مطابق   ← الرقيعة
── مع PYTHONDONTWRITEBYTECODE
   [4] المتوقَّع=..._a_measurement   الساقط=['..._a_measurement'] ✓ مطابق      ← الشفاء
```

**العلاج:** `PYTHONDONTWRITEBYTECODE=1` في بيئة المُشغِّل — بلا `.pyc` لا ذاكرة تبيت.
**وبرهان الاستعادة:** بصمة المحتوى بعد كلّ استعادة، وفشلٌ مُعلَن عند اختلافها عن الأصل —
لأنّ المقارنة بالحجم هي بالضبط ما أخفى العطل.

**ويفسّر هذا كلّ ما كان غامضاً:** لماذا لم تُصِب الرقيعةُ طفرةً أخرى قطّ (لا زوج آخر
متساوي الطول) · لماذا تخضرّ الإعادات (بينها زمنٌ يكفي لاختلاف `mtime`) · ولماذا لا تُعاد
محلّيّاً (تشغيلٌ أبطأ ⇒ طوابع مختلفة).

**مُثبَت بالتكذيب مرّتين نُفِّذتا:** إسقاط `PYTHONDONTWRITEBYTECODE` · إسقاط برهان الاستعادة.

**والدرس:** «رقيعة» ليست تصنيفاً بل **اعترافاً بأنّ القياس لم يُجرَ بعد**. ثلاث ملاحظات
حملت التوقيع نفسه، وما فتحه هو قراءة **اسم الاختبار الساقط** بدل الاكتفاء بأنّه «غير
المتوقَّع» — وهو الحقل الذي أُضيف في #795 لهذا الغرض بالذات. الأداة التي تُسمّي ما سقط
هي التي أغلقت الفجوة، بعد جولتين من عدم تسميته.

## `UNBOUNDED-RASTER-READ-ON-ARBITRARY-URL-01` — سقفٌ يُفحَص قبل التخصيص (مُغلَقة 2026-08-06)

**الحالة:** مُغلَقة · **المصدر:** تقرير الشهادة (P0 «قراءات TrueColor غير محدودة») + قياس
محلّيّ · `raster_pixel_processing.py:250` · `tile_render.py:767` · `raster_security_context.py:186-197`.

**وهذا تصحيحٌ لتصنيف التقرير لا تأكيدٌ له.** التقرير نسب العطل إلى «قراءة مشهد Sentinel-2
كامل» عبر مسار CDSE. القياس يُكذّب ذلك:
`raster_backfill_scene_processing.process_backfill_scene_cdse` يستدعي
`process_index(bbox=…, geometry=clip)` — فالراستر **مقصوصٌ على حدود الحقل قبل أن يصل
الخدمة**. المسار الإنتاجيّ محدودٌ أصلاً.

**وغير المحدود شيءٌ آخر، وهو حقيقيّ وقابل للوصول:** `safe_raster_source` يقبل **أيّ** رابط
`http(s)` غير محجوب (`raster_security_context.py:193-197`). فنداء `/process` بـ
`indicator=truecolor` و`precomputed_index=True` ورابطٍ كبير يصل إلى `src.read()` بلا أيّ
سقف في ذلك المسار.

| المقياس | القيمة |
|---|---|
| مشهد S2 كامل RGBA | 10980×10980×4 = **٤٨٢ م.بكسل-نطاق** (٤٨٢ م.بايت uint8) |
| قناع الهندسة (bool) | ١٢١ م.بايت |
| الذروة ≈ قراءة + قناع + كتابة | **~١٠٨٥ م.بايت** |
| `mem_limit` للخدمة | **1536m** |
| السقف المُعلَن الجديد | ٦٤ م.بكسل-نطاق |
| حقل نموذجيّ 2000×2000×4 | ١٦ م.بكسل-نطاق ⇒ مقبول بهامش ×٤ |

**والسقف يُحسَب بالنطاقات لا بالمساحة:** 5000×5000 = ٢٥ م.بكسل (تحت السقف) لكنّها ×٤
نطاقات = ١٠٠ م.بكسل-نطاق. حسابُ المساحة وحدها يُخطئ بأربع مرّات، وذلك مُثبَّت بطفرة.

**الإغلاق:** `assert_readable_size` يُستدعى **قبل** أيّ تخصيص — `rasterio.open` يعطي الأبعاد
بلا قراءة بكسل، فالفحص مجّانيّ. يرفع `413` برسالة تُسمّي الأبعاد والسقف واسم المتغيّر الذي
يرفعه. **والرفض المُعلَن أصدق من OOM صامت:** حاويةٌ تُقتَل بـSIGKILL لا تترك سبباً في أيّ
سجلّ ولا في أيّ صفّ — وهي بالضبط الحالة التي عجز التقرير عن إثباتها لغياب `OOMKilled`.

**مُثبَت بالتكذيب أربع مرّات نُفِّذت:** تعطيل السقف · إهمال عدد النطاقات · نقل الفحص إلى
**بعد** التخصيص (حارسٌ بعد التخصيص لا يمنع شيئاً — ومطابقةُ النصّ كانت ستمرّ عليه، فالترتيب
مُشتقّ بشجرة AST) · وزوال القصّ أعلى المجرى.

**والاختبار الرابع يحرس التصحيح نفسه:** إن زال `bbox`/`geometry` من نداء CDSE يوماً، يحمرّ
ويُعاد فتح تصنيف «قراءة مشهد كامل» — فلا يُقرأ التوثيق على أنّه ما يزال صادقاً بعد أن يبطل.

**حدّ الصدق:** السقف يمنع **التخصيص الأحاديّ الضخم**، ولا يمنع تراكم طلبات متزامنة كلٌّ
منها تحت السقف. ولم يُبنَ كاتب COG متدفّق: `cog_writer.write_rgba_cog` ما يزال يأخذ مصفوفةً
كاملة، فالسقف هو الحدّ لا البثّ. ولم يُقَس استهلاك ذاكرة حيّ — ما قِيس أبعادٌ وحسابٌ
حسابيّ، لا `docker stats`.

---

## `LIVE-PG-ROLE-CHECK-READS-FOUR-JUDGES-TWO-01` — `fixed` (فرع `claude/live-pg-role-evidence-hardening`)

**المصدر:** `scripts/ci/live_pg_evidence_guard.py` · مقيس على `df9b9e285`.

**الفجوة بين ما تُهيّئه الوظيفة وما يفحصه الحارس — وهي مكتوبة في الملفّين معاً:**

```
ci.yml:1197   create role sahool_app … nosuperuser nobypassrls nocreatedb nocreaterole   ← تُهيَّأ أربع
guard:105     select rolsuper | rolbypassrls | rolcreatedb                               ← تُقرأ ثلاث
guard:228     يُطبَع createdb في الملخّص                                                   ← تُعرَض ثلاث
guard:250     if superuser != false or bypassrls != false                                ← تحجب اثنتان
```

فـ`rolcreatedb` **يُقرأ ويُطبَع ولا يحكم** — رقمٌ معروض لا حارس، وظهورُه في المخرَج
يُقرأ شهادةً على أنّه مفحوص. و`rolcreaterole` **لا يُسأل عنه أصلاً**.

**ولماذا `CREATEROLE` تحديداً:** مالكها يُنشئ دوراً ويمنحه ما يشاء ثمّ يعمل تحته —
فيبلغ **بخطوتين** ما مُنِع منه بخطوة. فادّعاء «الدور مقيَّد» كان أضيق ممّا يُقرأ منه،
وصمتُ الحارس عنه ليس حكماً بغيابها بل بأنّه لم ينظر.

**العلاج:** قائمتان **منفصلتان عمداً** — `_ROLE_CATALOGUE_COLUMNS` (ما يُقرأ) و
`_REJECT_IF_TRUE` (ما يحجب) — والأربع في كلتيهما. والفصل هو ما يجعل الطفرات مستقلّة:
نزعُ عمودٍ من الاستعلام يُسقِط اختبار «الاستعلام يطلب الأربعة»، ونزعُ اسمٍ من قرار
الرفض يُسقِط اختبار تلك الخاصّيّة **باسمها**. ولو اشتُقّت إحداهما من الأخرى لأسقطت
الطفرةُ الواحدة اختبارين، فيُقرأ الادّعاءان مغطّيَين وأحدُهما بلا حارس.

**والفشل المغلق على الصفّ:** عدد حقول ≠ ٤ ⇒ فشل · قيمة ليست `true`/`false` ⇒ فشل.
`split("|")` بلا تحقّق يُنتِج صمتاً خطراً: عمودٌ يُضاف مستقبلاً فتنزلق القيم خانةً —
يُقرأ `rolcreatedb` مكان `rolbypassrls` — ويخرج الحكم **بثقةٍ كاملة** على أسماء لا
تقابل قيمها. رفضُ إصدار حكمٍ عن سؤالٍ لم يُجَب، لا تشدّد.

**المُكذِّبات — عشر طفرات مُسجَّلة، وكلّها زُرِعت وشُغِّلت (‏١٥/١٥ على هذا الحارس):**

| الطفرة | الاختبار الذي سقط |
|---|---|
| `superuser` خارج قرار الرفض | `test_a_superuser_role_is_rejected` |
| `bypassrls` خارج قرار الرفض | `test_a_bypassrls_role_is_rejected` |
| `createdb` خارج قرار الرفض | `test_a_createdb_role_is_rejected` |
| `createrole` خارج قرار الرفض | `test_a_createrole_role_is_rejected` |
| `rolcreaterole` خارج استعلام الكتالوج | `test_the_catalogue_query_asks_for_every_gating_attribute` |
| قبول قيمة غير منطقيّة | `test_a_malformed_role_row_is_fail_closed` |
| قبول صفٍّ بعدد حقول مختلف | `test_a_malformed_role_row_is_fail_closed` |
| نزع `checkout_sha` من الدليل | `test_the_evidence_binds_the_tested_commit_and_tree` |
| نزع `checkout_tree` من الدليل | `test_the_evidence_binds_the_tested_commit_and_tree` |
| لا دليل عند الفشل | `test_the_evidence_is_written_on_failure_not_only_on_success` |

**وطفرةٌ بائتة أُزيلت لا أُبقيت:** المواصفة القديمة كانت مرساةً على السطر
`if role["superuser"] != "false" or role["bypassrls"] != "false":` وقد اختفى بصيرورة
الرفض حلقةً. ومواصفةٌ لا تجد موضعها يرفضها `guard_mutation_guard` بـ«تُبلِّغ تغطيةً لا
تملكها» — فاستُبدِلت بأربعٍ مستقلّة لا بواحدةٍ مُعاد ربطها.

**حدّ الصدق — مكتوبٌ داخل الدليل لا خارجه:** الخصائص **مباشرة** من `pg_roles` للدور
المُسمّى نفسه. ولا يُثبَت الإغلاق الانتقاليّ لعضويّات الأدوار (`pg_auth_members`) ولا
أثر `SET ROLE` ولا صلاحيّات مورَّثة من دورٍ هو عضوٌ فيه. ولذلك اسم الحقل
`direct_role_attributes` لا `role_isolation`.

---

## `LIVE-PG-EVIDENCE-EXISTS-ONLY-WHEN-EVERYTHING-PASSED-01` — `fixed` (فرع `claude/live-pg-role-evidence-hardening`)

**المصدر:** `.github/workflows/ci.yml` — وظيفة `Live PG Proofs` على `df9b9e285`.

الوظيفة كانت تُنتِج `--junitxml=live_pg_evidence.xml` **ولا ترفعه**، والخطوة الأخيرة
بلا `if: always()`. فما تُنتِجه الوظيفة يموت مع الرَّانر، ولا يبقى إلّا سطرٌ في سجلّ
تشغيلٍ يُقادَم ويُحذَف.

**والمعنى المقلوب:** وثيقةٌ لا توجد إلّا حين ينجح كلّ شيء ليست دليلاً — **الدليل
يُطلَب يوم الفشل**.

**العلاج:** `--evidence` يكتب `live_pg_evidence.json` **بحكمه `PASS`/`FAIL` قبل** إعادة
أيّ رمز خروج غير صفريّ، ويُستدعى من مسار الفشل المغلق أيضاً (‏`psql` غائب · دورٌ غير
موجود · صفٌّ مشوَّه) فيبقى أثرٌ مقروء بدل صمتٍ يُقرأ «لم يُشغَّل شيء». ثمّ
`sha256sum` للملفّين، ورفع **الثلاثة** بـ`if-no-files-found: error` وباسمٍ يحمل SHA.

**والربط ثلاثيّ ومنفصل:** `checkout_sha` (‏`git rev-parse HEAD`) و`checkout_tree`
(‏`HEAD^{tree}`) و`github_sha`. **والفصل هو المعلومة:** في أحداث `pull_request` تعمل
الوظيفة على **دمجٍ وهميّ**، فيشير `GITHUB_SHA` إلى غير الشجرة المقيسة — وتوحيدُهما كان
سيُنتِج وثيقةً تدّعي أنّ ما اختُبِر هو ما أطلق التشغيل، وهو غير صحيح **بالبناء**.
والشجرة تُكتَب مع الالتزام لأنّ الالتزام قد يُعاد كتابته بمحتوى الشجرة نفسه.

**وبلا أسرار:** اختبارٌ يُثبِت أنّ الوثيقة لا تحمل `PGPASSWORD` ولا مضيفاً ولا منفذاً —
مصنوعةٌ تُرفَع تُقرأ لاحقاً، فما فيها يُنشَر.
## `MANIFEST-GREP-USES-GNU-ONLY-SHORTHAND-01` — نمطٌ يعمل هنا ولا يعمل هناك (مُغلَقة 2026-08-08)

**الحالة:** مُغلَقة · **المصدر:** تطبيقٌ جزئيّ لرقعةٍ نُشِرت على #814 — طُبِّق **٢ من ٣**،
مقيس على `df9b9e285`: السطران 1176 و1183 مُصحَّحان، و**754 باقٍ بصيغة GNU**.

**العطل:** `\s` امتداد GNU لا POSIX. على `grep` غير GNU (BusyBox في صور alpine ·
macOS/BSD) لا يُطابِق مسافةً بل **الحرف `s` حرفيّاً** — فسطر تعليقٍ لا يُستبعَد ويُقرأ
اسمَ هجرة.

**والموضعان ليسا زخرفاً:** 754 يغذّي الحلقة التي **تُطبّق** الهجرات، و1176 يغذّي
`expected` في بوّابة «طُبِّق N من M» — البوّابة التي تكشف إسقاط ملفٍّ صامتاً. فنمطٌ
يُخطئ الاستبعاد يُفسِد **العدّ الذي تُبنى عليه**.

**ولماذا نجا سنةً:** CI يعمل على `ubuntu-latest` بـ`grep` GNU، فالنمطان متكافئان هناك
**تماماً** — مقيس: كلاهما يُعطي **٢٢٦** على `MANIFEST.txt` الحقيقيّ. العطل **كامنٌ في
المحمولية لا واقعٌ في CI**، وهو بالضبط ما يجعل بقاءه غير مرئيّ: لا فحص يُشغَّل حيث يظهر.

**الإغلاق:** السطر ٧٥٤ مُصحَّح، و`tests_v9/test_manifest_grep_portability.py` يمنع عودته
بثلاثة أوجه:
- **مَنعٌ يُسمّي سببه** لـ`\s`/`\d`/`\w` في أنماط MANIFEST — نصّيّ **بالضرورة**: `grep`
  في هذه البيئة هو GNU، فالفارق لا يظهر سلوكيّاً هنا ولا مُفسِّر لـBusyBox/BSD في الشجرة.
  (امتثال عقد `prohibition_reason_guard`؛ الراتشِت لم يُنمَّ.)
- **وشقٌّ سلوكيّ هو الأهمّ:** تُشغَّل كلّ الأنماط المُستخرَجة على `MANIFEST.txt` الحقيقيّ
  ويُؤكَّد تطابق أعدادها، وأنّ العدد يساوي الهجرات المُعلَنة — فيُمسَك **إصلاحٌ يُغيّر ما
  يُستبعَد** لا محموليّته وحدها، وذاك أخطر لأنّه يفشل في CI بلا سببٍ ظاهر.
- **وإنفاذُ وجود الموضوع:** إن تغيّرت صياغة الاستدعاء فسقط الالتقاط إلى صفر، يحمرّ
  `test_every_manifest_reader_was_found` بدل أن يخضرّ الملفّ كلّه بلا فحص.

**مُثبَتٌ بالتكذيب:** الاختبار كُتِب **قبل** الإصلاح وقِيس سقوطه على `df9b9e285` ⇒
`1 failed, 4 passed`؛ وبعد الإصلاح ⇒ `5 passed`.

**وحدّ صدق:** الشقّ النصّيّ يحرس **الصياغة** لا السلوك على المُفسِّر الهدف. الإثبات
الحقيقيّ يقتضي تشغيل الأمر تحت `grep` غير GNU — غير متاح في هذه الشجرة، ولم يُدَّعَ.

### تصويب صياغة على `MANIFEST-GREP-USES-GNU-ONLY-SHORTHAND-01` (2026-08-08)

**المدخل أعلاه ادّعى أكثر ممّا يملك**، والمالك ردّه: قال إنّ `\s` «على BusyBox/macOS
**يُطابِق الحرف `s` حرفيّاً**». وهذا **غير مُثبَت** — إثباتُه يقتضي تشغيل تلك التطبيقات
فعلاً، وحدّ الصدق في المدخل نفسه يعترف بعدم توفّرها.

**والصياغة الدقيقة:** `\s` **ليس جزءاً من POSIX ERE**، وتفسيرُ الشرطة المائلة قبل حرفٍ
عاديّ مثل `s` **غير محدَّد** بالمواصفة خارج امتدادات التطبيق. فالسلوك **قد يختلف** بين
GNU وBusyBox وBSD، **ولا يجوز الاعتماد عليه**. والبديل المحمول `[[:space:]]`.

**والفارق ليس لفظيّاً:** «يُطابِق `s` حرفيّاً» ادّعاءُ سلوكٍ مُعيَّن يحتاج قياساً؛
و«غير محدَّد» ادّعاءُ مواصفةٍ يكفي وحده — **بوّابةٌ تعتمد سلوكاً غير محدَّد بوّابةٌ لا
تعرف ماذا تقيس**. والثاني أضعف لفظاً وأقوى إثباتاً، وهو ما يُبرِّر الإصلاح.

**والتصويب أُلحِق ولم يُحرَّر المدخل**: السجلّ إلحاقيّ، وتعديل نصٍّ سابق يمحو أنّ
الادّعاء قِيل ثمّ رُدّ — وذلك جزءٌ من السجلّ لا ضجيجٌ فيه.

### تصويب ثانٍ — يحلّ محلّ تفسير `f28f7d27f` (2026-08-08)

**هذا التصويب يحلّ محلّ التفسير الوارد في الالتزام `f28f7d27f`** لفجوة
`MANIFEST-GREP-USES-GNU-ONLY-SHORTHAND-01`. ما وُصِف هناك بأنّ `\s` «على BusyBox/macOS
**يُطابِق الحرف `s` حرفيّاً**» **لا يُعتمَد**؛ المُعتمَد ما يلي:

> `\s` **ليس جزءاً من POSIX ERE**، وتفسيرُ الشرطة المائلة قبل حرفٍ عاديّ مثل `s`
> **غير محدَّد** بالمواصفة خارج امتدادات التطبيق. فالسلوك **قد يختلف** بين GNU
> وBusyBox وBSD، **ولا يجوز الاعتماد عليه**. والبديل المحمول `[[:space:]]`.

والفارق ليس لفظيّاً: الأوّل ادّعاءُ **سلوكٍ مُعيَّن** يقتضي تشغيل تلك التطبيقات — ولم
تُشغَّل، وحدّ الصدق نفسه يعترف بذلك. والثاني ادّعاءُ **مواصفة** يكفي وحده: بوّابةٌ
تعتمد سلوكاً غير محدَّد بوّابةٌ لا تعرف ماذا تقيس.

**وتقويةٌ ثانية في الالتزام نفسه — على الحارس لا على النصّ:**

* كان الفحص يعمل على `range(3)` — **رقمٌ ثابت لا علاقة له بالشجرة**. صار يُوسَم بكلّ
  نمطٍ مُستخرَج فعلاً، فرابعٌ يُضاف يُفحَص تلقائيّاً بدل أن يُهمَل بصمت.
* وكان الاكتمال يُقاس بـ`len(found) >= 3` — **عتبةٌ تمرّ خضراء وفيها استدعاءٌ لا
  يُفحَص**. صار يُقارَن **مجموع** استدعاءات `grep` التي تذكر `MANIFEST.txt` بعدد
  الأنماط المُلتقَطة: كلّ استدعاءٍ يُرى يجب أن يُلتقَط نمطُه.

**مُثبَتٌ بالتكذيب:** تحويل اقتباس أحد الاستدعاءات من مفرد إلى مزدوج يُبقيه مرئيّاً
ويُسقِط التقاط نمطه ⇒ يحمرّ `test_the_extraction_covers_every_manifest_grep` بعينه
(‏`1 failed, 3 passed`)، وبالاستعادة `5 passed`.

**ولماذا إلحاقاً لا تحريراً:** السجلّ إلحاقيّ بالعقد، ومحوُ تفسيرٍ قِيل ثمّ رُدَّ يمحو
أنّه رُدّ — وذلك جزءٌ من السجلّ لا ضجيجٌ فيه.
## ATTESTED-IS-NOT-CERTIFIED-01 — `fixed` (القاعدة والمُنتِج · 2026-08-13) · كشفها المالك

**أُغلِقت بالمُنتِج (2026-08-13) — وفي الطريق سقط تصميمي الأوّل.** كنت وضعتُ
`execution_outcome` **حقلاً في البيان**، وذلك **غير قابل للتنفيذ** لا مجرّد أضعف:
`live_pg_canonical_manifest.json` من الموضوعات الموقَّعة الأربعة، فبصمتُه داخل الشهادة —
وإضافةُ حقلٍ إليه بعد التشغيل تُغيّر البصمة فتكسر التحقّق نفسه. فصار وثيقةً مستقلّة،
والرابطُ بينهما **الالتزامَ المُختبَر** لا مجاورةً في ملفّ.

- **`scripts/ci/run_outcome_guard.py`** يشتقّ الخلاصة من استجابتَي GitHub (التشغيل +
  الوظائف) ويرفض: تشغيلاً لم يكتمل · لمستودعٍ آخر · لـworkflow آخر · جرداً فارغاً ·
  ووظيفةً لم تكتمل تُسجَّل بحالتها لا بخلاصةٍ فارغة (فتُقرأ لاحقاً «ليست success»).
  أربع طفرات، إحداها تُكذِّب قراءة الفراغ نجاحاً.
- **`.github/workflows/certify-run.yml`** يعمل على `workflow_run: completed` لـ`SAHOOL
  v9.1.0 CI`: يجلب الخلاصة، ويُنزّل حزمة الأدلّة من التشغيل المشهود له، ويُشغّل الحارس
  بـ`--require-execution-outcome`. وهو **الموضع الوحيد** الذي تُعرَف فيه الخلاصة.
- **والراية في وظيفة الاعتماد وحدها** — مُثبَتٌ باختبار يقرأ الـworkflowين: لو حملها
  استدعاءُ `ci.yml` لاحمرّ `main` على غياب شيءٍ لا يملك المُنتِج إنتاجه.
- **والوصل مقيس من طرفٍ إلى طرف:** ما يُنتِجه المُشتقّ هو ما يرفضه الحارس — مُختبَراً
  على بيانات التشغيل `31728316326` الحقيقيّة: `EXECUTION_RUN_NOT_SUCCESSFUL`.
- **ولا تحجب دمجاً:** تُنتِج حالةً ثانية مستقلّة (`certification_accepted`) بجانب
  `provenance_verified`. وجعلُها فحصاً إلزاميّاً قرارُ مالكٍ في إعدادات الفرع.
- **وحدُّ الصدق الباقي (سجّله المالك):** التسمية الصارمة «FULL SIGSTORE TRUST-ROOT
  VERIFIED» تحتاج تحقّقاً مقابل `TrustedRoot` رسميّة. والحارس يستعمل
  `gh attestation verify --custom-trusted-root` بجذرٍ مجلوب مستقلّاً — فالشرط مُرضىً في
  مسار CI، ولا يُرضيه تحقّقٌ يدويّ بالمواد المضمَّنة وحدها.

- **المصدر:** `scripts/ci/sot_provenance_guard.py` — سُلَّم الضمان كان `release_bound` (من أين) + `evidence_passes` (حكمُ مصنوعتَي Live-PG). ولا شيء يقرأ **خلاصة التشغيل**. مقيس بمسحٍ على `scripts/` كلّها: **صفر** موضع يقرؤها.
- **العطل:** الشهادة تقول بصدق «هذا الـworkflow وهذه اللقطة أنتجا هذه البايتات ووقّعا منشأها»، وهي **لا** تقول «هذه اللقطة اجتازت البوّابة». فتشغيلٌ تسقط فيه وظيفةُ اختبارات يُنتِج مصنوعتين تقولان `PASS` ويوقّعهما، فتبلغ L5 — أي «attested ⇒ certified».
- **وكيف كُشِف — وهو الأهمّ:** بتحقّقٍ مستقلّ من حزمة Sigstore للشهادة `40565914`، أُعيد فيه بناء DSSE PAE والتحقّق من ECDSA بمفتاح شهادة Fulcio، وطُوبِق `sha256(payload)` بـ`payloadHash` داخل `canonicalizedBody`، وأُعيد حساب مسار Merkle حتّى الجذر فطابق، وفُكَّت امتدادات الشهادة (issuer · repo · ref · run · sha). **كلّ ذلك سليم** — والتشغيل `31728316326` خلاصتُه `failure` (سقطت `Repository Tests`). فالحزمة **شهادةٌ صحيحة لحالةٍ فاشلة**.
- **والفرق ليس لفظيّاً:** `provenance_verified` و`certification_accepted` حالتان مستقلّتان. الأولى تُثبِت **من قال ماذا وعن أيّ بايتات**؛ والثانية قرارُ سياسةٍ يشترط فوقها: التزاماً بعينه · تشغيلاً ناجحاً · **وظائفَ ناجحة إفراديّاً** · حداثةً · ومرجعاً معتمداً.
- **ما نُفِّذ:** `execution_clean(manifest, tested_commit)` يفرض `run_conclusion == success` وكلَّ `job_conclusions` ناجحة و`head_sha` مطابقاً للالتزام المُختبَر، ويفشل مغلقاً على الغياب. **خمس طفرات** تُكذِّبه، إحداها تُثبِت أنّ الخلاصة المجمَّعة ليست دليلاً (`JOB-STATUS-HID-A-FAILED-STEP-01` — وهو ما وقع حرفيّاً في ذلك التشغيل).
- **ولماذا يبقى `open`:** الشرط **معطَّل بمفتاح سياسة** لسببٍ مقيس لا تساهُلاً: **خلاصةُ التشغيل لا تُعرَف من داخله** — وظيفةٌ تعمل الآن لا تستطيع أن تقول كيف انتهى تشغيلُها. فالبيان المُولَّد داخل CI لا يستطيع إعلانها بصدق، وفرضُها اليوم يُحمِّر `main` على غياب شيءٍ لا يملك المُنتِج إنتاجه — لا على عطل.
- **شرط الإغلاق (واحد):** وظيفةُ اعتمادٍ تعمل على `workflow_run` **بعد** انتهاء التشغيل، تقرأ خلاصته وخلاصات وظائفه وتكتب `execution_outcome` في بيانٍ مُعاد توليده، ثمّ يُقلَب `require_execution_outcome` إلى `true`. وهذا يُحقّق أيضاً الفصل الذي أوصى به المالك: `PR_EVIDENCE` قبل الدمج، و`MAIN_CANONICAL_EVIDENCE` مُعاداً توليدها على التزام `main` بعده — فلا يُحتاج إثباتُ أنّ merge-ref مؤقّتاً «يعادل» main بعد squash.
- **وحتّى ذلك لا يُطوى الدَّين:** كلّ سجلّ تحقّق يحمل `EXECUTION_OUTCOME_MISSING` و`EXECUTION_OUTCOME_NOT_ENFORCED`، وطفرةٌ تُكذِّب إسكاتَهما. فالمعطَّل **مُعلَن** لا صامت.
- **حدّ صدق ثانٍ سجّله المالك ولم يُغلَق هنا:** التحقّق أعلاه استعمل المواد **المضمَّنة في الحزمة**. والتسمية الصارمة «FULL SIGSTORE TRUST-ROOT VERIFIED» تحتاج التحقّق مقابل `TrustedRoot` رسميّة (سلسلة Fulcio · مفتاح Rekor · شمولُ CT)، وإلّا فمهاجمٌ يستطيع نظريّاً استبدال المواد المضمَّنة كلَّها معاً. والحارس يستعمل `gh attestation verify --custom-trusted-root` بجذرٍ مجلوب مستقلّاً، وهذا **يُرضي الشرط في مسار CI** ولا يُرضيه في تحقّقٍ يدويّ بالمواد المضمَّنة وحدها.

## STATIC-GUARD-MEASURES-OCCURRENCE-NOT-EFFECT-01 — `mitigated` (2026-08-13 · ثلاثة مسارات من أربعة) · `open` (الصنف)

**وتوسعةٌ في نفس اليوم — مسارُ القواعد:** الشريحة الأولى غطّت التعويض والراوتر اليدويّ.
و`evaluate_rules` كان مقيساً بالحارس الساكن وحده، وهو **المسار الذي يعمل بلا إنسان**:
قاعدةٌ آليّة تفتح صمّاماً على قراءة مستشعر، فلا مراجِع ولا استجابة HTTP يُرى فيها الفرق.
أُضيفت له ثلاثة اختبارات (النطاق · الحجب · وألّا يُحجَب المشروع) وطفرتان — فصارت
الطفرات السلوكيّة **٩**.

**وأمسك حارسُ الطفرات مرساةً غير محدَّدة الموضع أثناء ذلك:** `valve_id=device` سلسلةٌ
جزئيّة من `valve_id=device_id` في موضع الإرسال، فطابقت موضعين. وُسِّعت المرساة إلى قوس
الإغلاق. ومرساةٌ تُطابِق موضعين تزرع في الأوّل وتُحاكَم بالثاني — وهو صنف «حكمٌ صحيح عن
موضعٍ غير الذي قِيس».

**والمسار الرابع باقٍ مُعلَناً:** مستهلك التوزيع (`dispatch consumer`) يستشير بنطاق
**المستأجِر وحده** قبل المطالبة، وله موضع استشارةٍ ثانٍ مُنطَّق بعد تحليل الأمر. لم
يُقَس سلوكيّاً في هذه الشريحة، وقياسُه يحتاج تجهيز عميل HTTP وطابور — فيُسجَّل ديناً
مكشوفاً لا يُقرأ مغطّى.

- **المصدر:** `scripts/ci/actuation_killswitch_coverage_guard.py` — يفرض أنّ كلّ موضع إطلاق فيزيائيّ **يستشير** مفتاح الطوارئ. وحدُّه مكتوبٌ في موضعه وفي `docs/architecture/gates/adjudications/GATE01-ADJ-2026-08-13-001.json` (`$honesty_limit_ar`) حرفيّاً: «يقيس **وقوع** استشارة المفتاح لا أنّ نتيجتها تمنع الإرسال».
- **العلّة:** بين «يستشير» و«يمنع» ثلاثة أعطال يمرّ عليها الحارس **أخضر**: (١) يستشير ثمّ **يتجاهل** النتيجة · (٢) يستشير **بنطاقٍ أضيق** (`field_id=None`) فلا يُطابِق مفتاح الحقل — وهو `MANUAL-COMMAND-KILLSWITCH-SCOPE-BLIND-01` بعينه · (٣) يستشير **بعد** النشر، فالاستشارة موجودة والأثر وقع.
- **وأضعفُ موضعٍ كان الراوتر:** `/v1/command` كان مقيساً بفحصٍ **نصّيّ** وحده (`test_the_router_passes_the_field_to_the_killswitch`)، ووثيقتُه تُقرّ بذلك: «ما يبقى بلا تغطية هو **أنّ الراوتر يستعمل القيمة**». وفحصٌ نصّيّ يمرّ على استشارةٍ نتيجتُها مُهمَلة.
- **العلاج المُنفَّذ:** قسمٌ ثانٍ في `docs/architecture/guard_mutation_registry.json` اسمه `behavioural`، مفاتيحه **مسارات مصادر إنتاج** لا أسماء حرّاس، وطفراتُه تُزرَع في المنطق نفسه ويجب أن يحمرّ اختبارُ **أثره** المُسمّى. سبعُ طفرات على `services/actuator-service/actuator_runtime.py` و`routers/commands.py` — وهما بعينهما ما أذن به `GATE01-ADJ-2026-08-13-001`، فيقيس التفويضُ ما مُنِح لأجله.
- **ونتيجةٌ قِيست ولم تكن متوقَّعة:** أكثر الاختبارات كانت **قائمة** (`test_compensation_killswitch.py` · `test_manual_command_killswitch_scope.py`) منذ إغلاق الدَّينين؛ الناقص أنّ أحداً لم يزرع العطل ويُثبِت أنّها تحمرّ. فالجديد **تسجيلٌ وزرع** لا كتابةُ اختبارات — عدا الراوتر، فأُضيف له `tests_v9/test_actuation_killswitch_behaviour.py` (أربعة اختبارات تُشغّل `send_command` وتقيس ما وصل إلى الوسيط).
- **والآليّة نفسها مُكذَّبة:** ثلاث طفرات على `guard_mutation_guard.py` تمنع إهمال القسم صامتاً — إفراغُه · تخطّي مصدرٍ مفقود · فحصٌ ثابت بلا زرع — ورابعة تُثبِت أنّ `test` على مستوى الطفرة يُحترَم (وحدةُ إنتاجٍ واحدة تُقاس بأكثر من جناح).
- **حدّ صدق — ولهذا الصنف `open`:** ما سُدّ هو **مسارا المُشغّلات** وحدهما. وحارسُ التغطية الساكن ما زال يقيس الوقوع على كلّ ما عداهما، و`GUARD_CATALOGUE.md` يقول المقياس: **٢٤٠ حارساً يحجب في CI، ٢٩ منها مُثبَتة بالتكذيب**. ولا يُشغَّل هنا stack حيّ ولا PostgreSQL — القياس بمحاكاة وحدة، و`aiomqtt` مُرقَّع بجذع.

## COMPENSATION-BYPASSES-KILLSWITCH-01 — `fixed` (2026-08-12 · رُفِع الحجر بقرار المالك)

**أُصلِح.** أُضيف مَفصِل `_consult_killswitch(tenant, field, valve)` و**استشارة لكلّ جهاز**
داخل حلقة `_compensate`، و`field_id` يُمرَّر من `evaluate_rules` الذي يملكه — فتطابق
نطاقُ التعويض نطاقَ القواعد (مستأجِر+حقل+صمّام). والمحجوب يُسجَّل `blocked` لا `failed`.

**والآليّة عملت كما صُمِّمت:** أوّل تشغيل بعد الإصلاح أعطى `8 failed` وكلّها
`[XPASS(strict)]` — نجاحٌ غير متوقَّع طالب بنزع العلامة، فنُزِعت. علامةٌ غير صارمة كانت
ستبقى صامتة إلى الأبد.

**مُثبَت بالتكذيب:** زرعُ `halted = (False, None)` أسقط **٥** اختبارات بالاسم؛ والاستعادة
أعادت الثمانية. **وحدّ صدق باقٍ:** مُثبَت بمحاكاة وحدة — لم يُشغَّل stack حيّ ولا PostgreSQL.

**ولحقَه ختمُ 2026-08-13 — صار مُثبَتاً بالتكذيب في السجلّ لا في جلسةٍ عابرة:** ثلاث
طفرات مُسجَّلة تحت `behavioural` تُزرَع في `_compensate` و`_consult_killswitch` وتُشغَّل
في CI (`guard_mutation_guard --run`): إسقاطُ الاستشارة ⇒ يُسقِط
`test_engaged_killswitch_blocks_the_inverse_command` · إسقاطُ `continue` بعد التسجيل
`blocked` (يستشير ثمّ يتجاهل) ⇒ يُسقِط
`test_a_blocked_compensation_is_recorded_as_blocked_not_failed` · تضييقُ النطاق داخل
المَفصِل ⇒ يُسقِط `test_the_seam_forwards_the_full_scope`. والاختبارات كانت قائمة؛
الجديد أنّ أحداً زرع العطل وأثبت احمرارها.

**ولحقَه `REVERSE-ENFORCEMENT-BLIND-TO-ITS-OWN-PATCH-01`:** الإصلاح ترك ترخيصاً ميّتاً
في `actuation_killswitch_coverage_guard` لأنّ الاستشارة تمرّ بمَفصِل. انظر المدخلة أدناه.

<details><summary>الوصف الأصليّ (قبل الإصلاح)</summary>


- **المصدر:** `services/actuator-service/actuator_runtime.py` — `_compensate` (`706-755`) يستدعي `send_mqtt_command` عند `:743` بالأمر **العكسيّ** (`open↔close` · `on↔off` · `start↔stop`)، **ولا `is_actuation_halted` في الدالّة كلّها**. يُبلَغ من `evaluate_rules:937`.
- **العلّة — والتوقيت هو ما يجعلها حرجة:** التعويض يُطلَق **عند فشل أمر في منتصف تسلسل**، أي في اللحظة التي يرجَّح فيها أنّ المشغّل اشتبك مفتاح الطوارئ للتوّ. فالمسار الوحيد الذي يتجاهل المفتاح هو **المسار الذي يعمل حين يُضغَط المفتاح**.
- **وهو مسار الأثر الفيزيائيّ الرابع، والوحيد بلا فحص إطلاقاً:** الإرسال (`:367`) بفحص بنطاق مستأجِر+حقل+صمّام · القواعد (`:915`) بنفسه · اليدويّ (`commands.py:50`) بنطاق أضيق (انظر `MANUAL-COMMAND-KILLSWITCH-SCOPE-BLIND-01`) · **التعويض بصفر**.
- **ولماذا لم تمسكه المراجعات:** `physical_effect_boundary_guard` يرصد **نمطين نصّيّين** (`mqtt.publish(` · `sahool/actuator/`) ولا يرى استدعاء `send_mqtt_command` بوصفه استدعاءً؛ و`_compensate` يستدعي المُساعِد لا العميل. حارسٌ يفحص **النصّ لا موضع الاستدعاء** — نفس صنف «فاحصٌ يُبلِّغ عن سؤال لم يطرحه».
- **موضعه من v05:** الوثيقة **تذكر `_compensate`** ضمن جرد المسارات (§2.3-4) وتُلزم البوّابة المركزيّة بتغطيته (§4.4-1.1) واختبارُ القبول الأوّل يشترط «لا تعويض» عند إطفاء العلم. فالعيب **ليس غائباً مفاهيميّاً**؛ الغائب **تسجيله عيباً قائماً واختباره سلوكيّاً**.
- **العلاج:** فحص `is_actuation_halted` داخل حلقة التعويض قبل كلّ إرسال، **بنفس نطاق `evaluate_rules`** (مستأجِر+حقل+صمّام)، و`field_id` يُمرَّر من المستدعي الذي يملكه. والمحجوب يُسجَّل `status="blocked"` لا `failed` — الحجب ليس فشلاً.
- **الحالة: العيب قائم في الشجرة، والإصلاح مُؤجَّل بقرار حوكميّ لا بجهل.** v06 يمنع تعديل المسارات الفيزيائيّة قبل تثبيت evidence pack المرحلة 0، والقياس على الحزمة الحاليّة `frozen_commit_sha=null` و`phase0_evidence_status: NOT_FROZEN` ⇒ **GATE-01 لم تُفتح**. رقعة الإصلاح محفوظة خارج المستودع.
- **والتوثيق تنفيذيّ لا نثريّ:** `tests_v9/test_compensation_killswitch.py` — ثمانية اختبارات سلوكيّة بـ`xfail(strict=True)`. **القياس سلوكيّ لا نصّيّ:** يُشغَّل تعويض حقيقيّ ومفتاح مُشتبَك ويُقاس **أنّ `send_mqtt_command` لم يُستدعَ** — لا بحثٌ عن `is_actuation_halted` في المصدر، فبحثٌ كهذا يمرّ على استدعاءٍ في فرعٍ لا يُنفَّذ.
- **ولماذا `strict=True` تحديداً:** علامةٌ غير صارمة تبقى صامتة إلى الأبد بعد دخول الإصلاح — وهي نفسها «فاحصٌ يُبلِّغ عن سؤال لم يطرحه». **مُتحقَّق بالتطبيق:** وضعُ الرقعة يُحوّل الثلاثة عشر إلى XPASS ⇒ الجناح **يحمرّ** ويُطالِب بنزع العلامة.
- **حدّ صدق:** مُثبَت **ساكناً وبمحاكاة الوحدة**؛ لم يُشغَّل stack حيّ ولا PostgreSQL. ولا يُغلق صنف «مسار أثر بلا فحص» — يُوثّق هذا المسار.

</details>

## MANUAL-COMMAND-KILLSWITCH-SCOPE-BLIND-01 — `fixed` (2026-08-12 · رُفِع الحجر بقرار المالك)

**أُصلِح.** `_authorize_device_control` صار يُرجِع `field_id` الجهاز من **نفس الاستعلام**
القائم (‏`fetchrow` بدل `fetchval` — إعادة استعمال لا استعلام ثانٍ)، ويُمرَّر إلى
`is_actuation_halted` في `/v1/command`. فتطابقت نطاقات المسارات الثلاثة.

**مُثبَت بالتكذيب:** إسقاط `field_id=device_field_id` من الراوتر أسقط
`test_the_router_passes_the_field_to_the_killswitch` بالاسم. خمسة `[XPASS(strict)]` عند
دخول الإصلاح ⇒ نُزِعت العلامة. وجهازٌ بلا حقل يُرجِع `None` — محكومٌ بالمستأجِر والصمّام،
**صحيح لا ثغرة**.

**وختمُ 2026-08-13 — سُدّ آخرُ ما كان نصّيّاً:** كان الوصل مقيساً بفحصٍ نصّيّ وحده
(`test_the_router_passes_the_field_to_the_killswitch`)، وهو يمرّ على استشارةٍ نتيجتُها
مُهمَلة. فأُضيف `tests_v9/test_actuation_killswitch_behaviour.py` يُشغّل `send_command`
نفسها، وثلاث طفرات مُسجَّلة تحت `behavioural`: `field_id=None` ⇒ يُسقِط
`test_manual_command_consults_the_killswitch_with_the_authoritative_field` · تعطيلُ
`if halted:` ⇒ يُسقِط `test_a_field_scoped_halt_blocks_a_manual_valve_command` · حجبٌ
شامل ⇒ يُسقِط `test_a_clear_killswitch_still_lets_a_manual_command_through` (فمنعُ
تشغيلٍ مشروع عطلٌ أيضاً).

<details><summary>الوصف الأصليّ (قبل الإصلاح)</summary>


- **المصدر:** `services/actuator-service/routers/commands.py:47` — `is_actuation_halted(ks_conn, tenant_id, valve_id=req.device_id)` **بلا `field_id`**.
- **العلّة:** `match_killswitch` (`shared/actuation_killswitch.py:55`) يشترط `field_id is not None` لمطابقة صفٍّ بنطاق `field`. فمفتاحٌ يوقف **حقلاً بأكمله** يحجب مسار القواعد ومسار الإرسال — **ولا يحجب `/v1/command` اليدويّ**. المشغّل الذي أوقف حقلاً يظنّ الحقل موقوفاً، وبابٌ واحد يبقى مفتوحاً.
- **ولماذا هذا أسوأ من ثغرة نطاق عاديّة:** الفارق **غير مرئيّ في الاستجابة** — الأمر ينجح بـ200 كأنّ لا مفتاح. لا رسالة تقول «مفتاح الحقل لا يشملك».
- **العلاج:** `_authorize_device_control` **يُرجِع `field_id` الجهاز** (وهو يستعلم `iot_devices` أصلاً — إعادة استعمال لا استعلام ثانٍ)، ويُمرَّر إلى `is_actuation_halted`. فتتطابق نطاقات المسارات الثلاثة.
- **الحالة: قائم، والإصلاح مؤجَّل بنفس بند التجميد** (المسار فيزيائيّ). `tests_v9/test_manual_command_killswitch_scope.py`: **ثلاثة اختبارات تمرّ اليوم** على قاعدة `match_killswitch` النقيّة وتُثبِت *لماذا* يلزم الحقل (نفس الصفّ ونفس الصمّام، والفارق تمرير الحقل)، **وخمسة بـ`xfail(strict=True)`** تصف السلوك المطلوب بعد الإصلاح.
- **حدّ صدق:** حتّى بعد الإصلاح يوحَّد النطاق ولا يُثبَت أنّ الثلاثة تُستشار في كلّ الظروف التشغيليّة. وجهازٌ بلا `field_id` في السجلّ يبقى محكوماً بنطاقَي المستأجِر والصمّام — **صحيح لا ثغرة**: لا حقل له. وv06 يصف الحالة بدقّة أكبر من صياغتي الأولى: «مغطّى جزئيّاً tenant/valve وغير مغطّى بنطاق field».

</details>

## GUC-SCOPE-GUARD-SEES-ONE-FILE-01 — `fixed` (الحارس) · `open` (الدَّين المكشوف) — 2026-08-12

**بُنِي الحارس الشجريّ:** `scripts/ci/tenant_guc_scope_guard.py` — يقيس **النطاق لا الوجود**:
كلّ `set_config(..., true)` يجب أن يقع داخل كتلة معاملة، والاحتواء سؤالٌ عن **البنية**
فيُجاب بـAST لا بـregex سطريّ.

**والكاشف التقط شرحه هو في أوّل صيغة** — فصار مُرسًى على **وسائط الاستدعاء**: ملفٌّ يصف
عيباً ليس ملفّاً يرتكبه، والفرق بنيويّ. (طفرة مستقلّة تحرس هذا.)

**والتصادُق أقوى من الثقة بالنفس:** الكاشف المستقلّ أعطى **١٢** في `market_server.py`
و**٣** في `helpers.py` و**٢** في `oauth_middleware.py` — مطابقةً للأرقام الموثَّقة هنا
قبل بنائه.

**راتشِت بأساسٍ مُعلَن (٣٥ موضعاً · ٤ أسماء GUC):** يتقلّص ولا ينمو. ولا توحيد ميكانيكيّ
للأسماء — توحيدُها يكسر سياسات RLS التي تقرأ الاسم الآخر، فتُجرَد ويبقى التوحيد قراراً بشريّاً.

**و`tenant_query_audit.py` صُحِّح:** كان يمنح `EXPLICIT` لمجرّد وجود `set_config` — «الوجود
ليس النطاق». والتصحيح **كشف ٧ استعلامات RAW** كانت تحمل شهادة سلامة كاذبة. ولم تُضَف إلى
`_ALLOWLIST_JUSTIFIED` (ذلك يقول «صحيح ولهذا السبب» وهو كذب) بل إلى `_REVEALED_SCOPE_DEBT`
المنفصل: **«عيبٌ قائم، مقيسٌ ومرئيّ، لم يُصلَح»** — يُطبَع في كلّ تشغيل ويتقلّص ولا ينمو.

**طفرتان مُثبَتتان بالتشغيل:** نزعُ فحص الاحتواء ⇒ يسقط اختبار الحجب · نزعُ الترسية على
الاستدعاء ⇒ يسقط اختبار النثر.

**وما بقي `open` صراحةً:** الـ٣٥ موضعاً والـ٧ استعلامات **لم تُصلَح** — إصلاحها يمسّ مسارات
استعلام في خدمات لم تُقَس حيّاً، وقاعدة المالك «يُسجَّل ويوقف الملفّ المعنيّ؛ لا يُصلَح ضمن
الشريحة». والحارس يمنع **النموّ** لا يُسدّد الدَّين. ولم يُقَس أثرٌ تشغيليّ: تحت دور يتجاوز
RLS يمرّ الفحص لأيّ مستأجِر، وتحته لا يمرّ لأحد — وأيّ الحالتين قائمةٌ إنتاجيّاً لم يُقَس.

<details><summary>الوصف الأصليّ (قبل بناء الحارس)</summary>


- **المصدر:** `services/raster-service/test_tenant_guc_session_scope_guard.py` — الحارس يحمل **التشخيص الصحيح لهذا الصنف مكتوباً** على عيب إنتاجيّ حقيقيّ (`set_config(...,true)` في autocommit يضيع قبل الاستعلام التالي ⇒ RLS يعيد صفراً ⇒ هندسة فارغة)، **لكنّ تأكيده regex على `db_persist.py` وحده**.
- **والمسح الثاني أسوأ:** `scripts/tenant_query_audit.py:9` يصنّف أيّ دالّة فيها `set_config` بأنّها `EXPLICIT ⇒ سياق صريح` — **يفحص الوجود لا النطاق**، فيمنح كلّ المواضع المعيبة شهادة سلامة.
- **المقيس (سطح غير مغطّى):** `services/mcp_servers/market_server.py` — **١٢ من ١٢ خارج معاملة حاوية**؛ الموضع الذي يفتح `conn.transaction()` يفعل ذلك **بعد** `set_config` (`:225` يسبق `:227`) فلا يُحفَظ الـGUC داخلها. منها **١٠ مسارات بيانات مستأجَرة معيبة**، واثنان health/readiness يضبطان مستأجِراً فارغاً ثمّ يُنفّذان `SELECT 1` — **ليسا خرق عزل، والضبط فيهما عديم الجدوى** (استثناءان معلَّلان؛ تصحيح v06 لصياغتي الأولى). ويُضاف `services/mcp_servers/market_db_authz.py:95` · `shared/helpers.py:175,179,184` · `services/mcp_servers/shared/oauth_middleware.py:32,36` — والوصف الأدقّ لهذين (تصحيح v06): **عقدان مساعدان لا يضمنان بذاتهما معاملة حاوية، وخطورتهما تعتمد على المستدعين — فيُجرَد مستوردوهما قبل وصف كلّ استعمال بأنّه عيب مؤكَّد**.
- **العلاج المطلوب (لم يُنفَّذ بعد — تصميم v06 §2.5-6، وهو أدقّ من صياغتي):** حارس شجريّ **لا يفرض اسماً عالميّاً واحداً للـGUC** بل يتحقّق من الثلاثيّة `target table → RLS policy GUC name → store/callsite GUC name`، بستّة فحوص: وقوع `set_config(...,true)` داخل المعاملة · وقوع الاستعلام المستأجَر بعده وقبل انتهائها · توافق اسم الـGUC مع سياسة الجداول المستهدفة (**مع جرد تعدّد الأسماء بلا توحيد ميكانيكيّ**) · منع `tenant_query_audit.py` من منح `EXPLICIT` لمجرّد وجود `set_config` · استثناء health probes المعلَّل · **طفرتان مستقلّتان**: واحدة لـscope mismatch وأخرى لـGUC-name mismatch. ويُنشَأ **قبل** إصلاح E5، ويدخل `guard_mutation_registry.json`.
- **حدّ صدق:** مقيس ساكناً. ولم يُقَس أثرٌ تشغيليّ: تحت دور يتجاوز RLS يمرّ الفحص لأيّ مستأجِر، وتحته لا يمرّ لأحد — وأيّ الحالتين قائمةٌ إنتاجيّاً **لم يُقَس**.

## REVERSE-ENFORCEMENT-BLIND-TO-ITS-OWN-PATCH-01 — `fixed` (2026-08-12)

**الصنف:** إنفاذٌ عكسيّ يَعِد بإسقاط الترخيص عند هبوط الرقعة، ثمّ لا يراها لأنّها هبطت
بشكلٍ لم يتوقّعه كاشفُه. فيبقى **الترخيص حيّاً بعد زوال سببه** — وهو أخطر من غياب
الحارس: غيابُه يُرى، وترخيصُه الميّت يُقرَأ ضماناً.

- **المصدر:** `scripts/ci/actuation_killswitch_coverage_guard.py` — التغطية كانت
  `_calls_name(fn, KILLSWITCH)`، أي **الاستدعاء المباشر وحده**. ورقعة M-01 تستشير
  المفتاح عبر `_consult_killswitch` (مَفصِلٌ **يلزم** كي يُستشار بنفس نطاق القاعدة:
  مستأجِر+حقل+صمّام). فقرأ الحارس `_compensate` «غير مُغطّاة» ⇒ لم يَبِت الاستثناء.
- **والعطل لا يُرى في أيّ من الوضعين، وهذا ما يجعله صنفاً:** مع الاستثناء ⇒ أخضر
  و«دَين مجمَّد معلَن: 1» (ترخيصٌ ميّت). وبنزعه ⇒ `rc=1` يتّهم `_compensate` بالإطلاق
  بلا مفتاح **وهي تستشيره**. فالحارس عاجزٌ عن قول الحقيقة في الحالتين.
- **ولماذا لم يُمسَك:** للحارس طفرةٌ واحدة تقيس الاتّجاه الأماميّ. والإنفاذ العكسيّ
  **مُنفَّذ ومُختبَر بمعطيات مُركَّبة ذات استدعاء مباشر** — فمرّ أخضر ولم يُمارَس قطّ
  على رقعةٍ حقيقيّة. «له اختبار» ليس دليلاً حين يقيس الاختبارُ الشكلَ السهل.
- **العلاج — في الكشف لا في السجلّ:** `_consulting_helpers` تجمع مَفاصِل الوحدة التي
  تستشير المفتاح، و`_is_covered` تقبل **مستوىً واحداً** منها. ثمّ نُزِع الاستثناء
  لأنّه بات فعلاً. ونزعُه وحده كان سيقلب العطل اتّهاماً كاذباً.
- **مُثبَت بالتكذيب على الشجرة الحقيقيّة لا بمعطيات مُركَّبة:** إعادةُ الترخيص ⇒
  `stale=[('…/actuator_runtime.py','_compensate')]` (كان الحارس القديم يُعيد لا شيء) ·
  ونزعُ الاستشارة بعد نزع الترخيص ⇒ `uncovered` يسمّيها. وطفرتان جديدتان في السجلّ
  قتلتا اختباريهما ⇒ **٢٩ حارساً / ١٧٧ طفرة**. والاختبارات ٧ ⇒ ١٣.
- **حدّان مُعلَنان ومُختبَران:** سلسلةُ مَفصِلَين ليست تغطية · ومَفصِلٌ في وحدةٍ أخرى
  لا يُعَدّ (يقتضي حلّ الاستيرادات). حارسٌ يزعم ما لا يقيس أسوأ من حارسٍ يُعلِن حدّه.
- **وحدّ صدقٍ ثالث لم أُصلِحه ولم أُحدِثه:** الحارس يقيس **وقوع الاستشارة** لا أنّ
  نتيجتها تحجب الإطلاق. دالّةٌ تستشير ثمّ تتجاهل الجواب تُقرَأ مُغطّاة — وهي خاصّيّة
  التصميم الأصليّ، تبقى مكتوبة لا مُدّعىً سدُّها.

## BIDI-CONTROL-CHAR-PASSED-THE-DEFAULT-PREFLIGHT-01 — `fixed` (الصنف · 2026-08-13) · `fixed` (الحالة · 2026-08-12)

**أُغلِق الصنف (2026-08-13) — والمسح أعطى رقماً أكبر ممّا ظنّ المُقترَح.** كان التقدير
«٢٧ محرفاً في نطاق bandit»؛ والمقيس على **كامل الشجرة** ٣٥٠ محرفاً في ٩٣ ملفّاً —
`json`·`md`·`yml`·`sql`·`tsx`·`ps1`·`py`. أي أنّ البوّابة القائمة كانت تحرس عُشر السطح
وتُقرأ حراسةً له كلّه.

- **وصنفان لا صنف، والفصل بينهما هو التصميم كلّه:** *قلبُ الاتّجاه*
  (`RLE`·`LRE`·`RLO`·`LRO`·`PDF`·`LRI`·`RLI`·`FSI`·`PDI`) يُعيد ترتيب الرموز بصريّاً —
  سطرٌ يقرؤه المراجع ويُنفَّذ غيرُه، وهو *trojan source* بعينه ⇒ **يُحجَب مطلقاً بلا
  أساس** (والمقيس اليوم صفر). أمّا *العلامات والخفايا* (`RLM`·`LRM`·`ALM`·`ZWNJ`·`BOM`)
  فلا تقلب ترتيباً وأكثرها استعمالٌ مشروع كتبتُه بنفسي لضبط اتّجاه قوسٍ في شرحٍ عربيّ ⇒
  **أساسٌ يتقلّص ولا ينمو**. وحظرُها الشامل كان يُكذَّب أوّل مرّة، وأساسٌ يُكذَّب فوراً
  يُدرَّب قارئه على تعطيله.
- **والثغرة التي أشارت إليها المدخلة أصلاً مسدودة:** `bandit` يحجب `RLM` ولا يحجب `LRM`،
  فالاستبدال كان يُمرِّر البوّابة **ويُبقي المحرف**. الحارس يعدّهما معاً، وله اختبارٌ
  بهذا الاسم.
- **وموضعه الملفّ الافتراضيّ** (§٢ج من `preflight.sh`) + وظيفةٌ في CI — لأنّ الحادثة
  كلّها كانت «اختيارُ ملفٍّ أرخص ثمّ قراءةُ أخضره أخضرَ CI»، فعلاجُها في الملفّ الأرخص.
  Python صرف، أقلّ من ثانيتين.
- **وأمسك الحارسُ نفسَه أوّلَ ما تُتبِّع:** أوّل صياغة لاختباره حملت محارف القلب
  **حرفيّاً** كثوابت، فكان سيُسقِط نفسه فور إضافته إلى git. أُعيدت الثوابت إلى
  `chr(0x202E)` — واختبارٌ يُدخِل ما يمنعه ليس اختباراً بل حالةً أولى للعطل.
- **والأساس تقلّص فور إنشائه:** ٣٥٠ ⇒ **٣٢٣** في ٨٢ ملفّاً، بنزع ٣٨ علامةً من الملفّات
  التي كتبتُها في هذه الشريحة. أربع طفرات مُسجَّلة.
- **حدّ صدق:** يمسح **ملفّات git المتتبَّعة** النصّيّة وحدها؛ والثنائيّات خارجه.

**الحالة المقيسة:** محرف `U+200F` (RLM) في docstring بـ`actuator_runtime.py:523` كتبتُه
لضبط اتّجاه قوسٍ في نصٍّ عربيّ. أسقط `Security Scan` في CI بـ**B613 trojansource**
(‏HIGH ⇒ حاجب)، على رأسٍ أعلنتُه أخضر.

- **ولماذا فات:** `preflight.sh` بالملفّ الافتراضيّ **لا يُشغّل bandit** — هو في
  `--full` وحده. ودفعتُ على الافتراضيّ. وهو الصنف الإجرائيّ نفسه الذي وقع في هذه
  الجلسة على `--fast`: **اختيارُ ملفٍّ أرخص ثمّ قراءةُ أخضره «أخضر CI»**.
- **وقياسٌ يخصّ الحارس نفسه:** في نطاق bandit **٢٧** محرف اتّجاه، وواحدٌ فقط حُجِب —
  لأنّ B613 يلتقط `U+200F` ولا يلتقط `U+200E` (LRM)، وهو المستعمل في ٢٦ موضعاً قائماً.
  فـ«استبدال RLM بـLRM» كان يُمرِّر البوّابة **ويُبقي المحرف الخفيّ**. لذلك حُذِف
  المحرف ولم يُستبدَل: الغرض سلامة المصدر لا خضرة البوّابة.
- **الصنف يبقى `open`:** لا شيء في الملفّ الافتراضيّ يمنع تكراره، والفحص رخيص
  (‏Python صرف بلا bandit). لم أُضِفه في هذه الشريحة لأنّها شريحةُ حارسٍ آخر —
  وإضافةُ بوّابة أثناء إصلاح غيرها تُخفي أيّهما قِيس. مُقترَحٌ مُسجَّل لا مُنفَّذ.
- **حدّ صدق:** الحالة الواحدة أُصلِحت ومُتحقَّق منها بـ`bandit -r services/ bots/ agents/
  --severity-level high` ⇒ `rc=0`. والصنف **غير محروس** — وإغلاقه يخلط «أصلحتُ ما وقع»
  بـ«منعتُ أن يقع».

## GUARD-DIES-PRINTING-ITS-OWN-SUCCESS-UNDER-C-LOCALE-01 — `fixed` (الصنف · 2026-08-13) · `fixed` (الحالة الأولى · 2026-08-12)

**أُغلِق الصنف بمسحٍ لم يكن قائماً (2026-08-13).** المُقترَح المُسجَّل هنا — «إشعالُ كلّ
حارسٍ عمليّةً فرعيّة تحت لغة C» — نُفِّذ، وأعطى أرقاماً أكبر ممّا رجّحته العيّنة:

- **٣٥ حارساً** ماتوا بـ`UnicodeEncodeError` على تشغيلٍ حقيقيّ (لا ٣ كما قاست العيّنة)،
  و**٢٢** ماتوا بـ`UnicodeDecodeError` **عند التحميل** — وهؤلاء صنفٌ ثانٍ لم يكن مرصوداً:
  حرّاسٌ **بلا `main()`**، جسدُها يعمل عند الاستيراد وتقرأ بـ`read_text()` بلا ترميز،
  فتنهار **قبل أن تقيس شيئاً**. أي حارسٌ يُبلِغ حجباً وهو لم ينظر.
- **وكلّها كانت خضراء في CI** — لأنّ عدّاء Linux افتراضيّه UTF-8. فخضرة البوّابة كانت
  شهادةً على **لغة العدّاء** لا على الحرّاس. وهذا هو الفرق الذي وُجِد المسح لأجله.
- **والثالث والعشرون درسٌ في ترتيب الأعطال:** `brain_commit_claim_guard` كان يموت في
  القراءة (`subprocess(text=True)` على رسائل التزام عربيّة — المتّجه ②)، فلمّا ثُبِّتت
  ظهر أنّه يموت في **الكتابة** أيضاً. عطلان في ملفٍّ واحد والثاني مستورٌ بالأوّل، ولا
  يكشفه إلّا إعادةُ القياس بعد كلّ إصلاح.
- **العلاج عند التحميل لا داخل `main()`**: الصيغة الأولى وضعته في `main`، وهي لا تنفع
  حارساً بلا `main` — والموضع الموحَّد هو ما جعل القاعدة قابلة للقياس بمسبارٍ واحد.
- **والحارس `scripts/ci/guard_locale_survival_guard.py`** يفرضها الآن: يُشعِل ١٤٦ حارساً
  تحت `LC_ALL=C PYTHONUTF8=0` في ~٨٠ ثانية، ويسأل سؤالاً واحداً — هل مات **لسببٍ ترميزيّ**؟
  لا يُدين رمز خروجٍ غير صفريّ لسببٍ آخر (حارسٌ يطلب وسيطاً ليس عطلاً)، ولا يبحث عن
  `reconfigure` في النصّ (السطر قد يقع بعد أوّل طباعة فلا ينفع). أربع طفرات مُسجَّلة.
- **ويُعلِن ما لم يقِسه:** حارسٌ يموت باستيرادٍ ناقص لا يطبع شيئاً فيُقرأ مرورُه سلامةً —
  فيُعَدّ ويُطبَع. ولهذا وُضِعت البوّابة في وظيفة *Unit Tests* لا في *Lint*: تلك تملك
  تبعيّات الجناح، وبدونها كانت ستخضرّ على **صفر قياس**.
- **حدّ صدق باقٍ:** يُشغَّل كلّ حارس **بلا وسائط**، فمسارات `--check`/`--fix` غير مقيسة
  وقد تحمل الصنف نفسه. و`*_guard.sh` خارج النطاق. والأخضر يعني «لا حارس ينهار ترميزيّاً
  على مساره الافتراضيّ» — لا أكثر.

**الانقلاب:** حارسٌ يحسب **صحيحاً** ثمّ يموت وهو يطبع نجاحه، فيخرج بـ`1` — أي
يُبلِغ حجباً على شجرةٍ سليمة، ورسالتُه traceback يسمّي الترميز لا الموضوع. وهو أسوأ
من الصمت: الصامت يُرى غيابُه، وهذا يُرى **ضدّ** ما قاس.

- **المصدر:** `print` يُرمّز بلغة الآلة. وأساس `text_encoding_locale` يحكم **القراءة**
  (‏`read_text(encoding=...)`) ولا شيء يحكم **الكتابة** إلى `stdout`. والقراءة في
  `tenant_guc_scope_guard` كانت مثبَّتة منذ البداية — والمنسيّ الكتابة.
- **الصنف أوسع من ملفّي، وهذا مقيس لا مُرجَّح:** تحت
  `env -u PYTHONIOENCODING LC_ALL=C PYTHONUTF8=0` سقطت **٣ من ٣** عيّنة:
  `tenant_guc_scope_guard` · `actuation_killswitch_coverage_guard` · `claim_base_guard`
  — كلّها `UnicodeEncodeError` وrc=1.
- **ولماذا لم يظهر إلّا عندي:** اختباري وحده **يُشعِل الحارس عمليّةً فرعيّة**، فترث
  لغة الآلة. وبقيّة الحرّاس تُستدعى داخل العمليّة وpytest يلتقط مخرَجها بـUTF-8 —
  فهي **غير مقيسة، لا محصَّنة**. والفرق هو كلّ شيء.
- **المُصلَح:** `tenant_guc_scope_guard` وحده — لأنّه وحده كان يُسقِط بوّابة (§١٠ من
  `preflight --full`). `sys.stdout/stderr.reconfigure(encoding="utf-8")` ⇒ مخرَجٌ
  واحد تحت اللغتين وrc=0 في كلتيهما.
- **ولماذا لم أكنس البقيّة:** كنسُ ١٤٣ حارساً داخل شريحةٍ موضوعها حارسٌ آخر يُخفي
  أيّهما قِيس، ولا بوّابة تسقط عليها اليوم. والصنف يبقى `open` بلا حارس: لا شيء
  يمنع الحارس القادم من الوقوع فيه، والفحص الصادق هو **إشعال كلّ حارسٍ عمليّةً
  فرعيّة تحت لغة C** — مُقترَحٌ مُسجَّل لا مُنفَّذ.

## UNPROTECTED-BRANCH-CAN-ATTAIN-L5-01 — `fixed` (2026-08-13 · كشفها المالك بتحقّقٍ مستقلّ)

**الفجوة:** `release_bound` في `sot_provenance_guard` كان يقيس اتّساق الالتزام/الشجرة
**ولا يسأل عن المرجع إطلاقاً**. فالسلسلة `push` + `exact_commit` + أدلّة حيّة ناجحة
تبلغ **L5** من أيّ فرع. والعقد المُعلَن كان: أدلّة PR/فرع ≤ L3، وأدلّة main/إصدار
مؤهَّلة لـL4/L5 — فالتنفيذ يخالف العقد بلا أن يُحمِرّ شيء.

- **مقيسة بحادثةٍ حقيقيّة لا بتخيّل:** الحزمة `attestation/40374289` على
  `ffc29415` من `refs/heads/claude/project-exploration-dtjw3p` تحمل
  `verdict=VERIFIED · assurance_level=L5`. وسلامتُها التشفيريّة **تامّة** — فُكَّ
  DSSE وتُحقِّق من التوقيع وسلسلة Fulcio وSET وإثبات Merkle وتوقيع checkpoint،
  وطابقت بصماتُ الـsubjects الأربعة الملفّات الفعليّة. **العطل في الحارس لا في
  Sigstore**، وظهورُ L5 هنا هو نفسه الدليل الذي كشفه.
- **ولم يُكشَف قبلاً لأنّ الاختبارات غطّت المحور الخطأ:** كان اختبارٌ يمنع
  `pending_final_rerun` من بلوغ الربط، وآخرُ يقيس `exact_commit`. ولا اختبار يقول
  **«فرع عمل + exact_commit ≠ مؤهَّل للإصدار»**. أي أنّ التغطية كانت في اتّساق
  البيان، والمحور المفقود مصدرُه.
- **العلاج — في الحارس لا في YAML:** `release_refs` بياناتٌ في السياسة المُصدَّرة
  (`["refs/heads/main"]`، `policy_version: 2`، `adjudicated_on: 2026-08-13`)، و
  `release_bound(manifest, policy, source_ref)` يشترطها. شرطٌ في `ci.yml` وحده يحرس
  مساراً واحداً ويستطيع أيّ workflow آخر تمرير `exact_commit` من فرعٍ غير معتمد.
- **والوضعان يُقاسان بما يدّعيانه:** `exact_commit`/`exact_tree` يقولان «المصدر هو
  الإصدار» فيُقاسان بـ`source_ref`؛ و`tested_merge_to_release` غرضُه أنّ المصدر
  **ليس** الإصدار فيُقاس بـ`accepted_ref` الذي يسمّيه — وغيابُه رفضٌ لا تساهُل.
- **وسياسةٌ بلا القائمة تفشل مغلقةً** (`RELEASE_REF_POLICY_MISSING`) — لا تُقرَأ
  «كلّ المراجع مقبولة»، وإلّا صار حذفُ حقلٍ طريقاً صامتاً إلى L5.
- **والمطلوب في `ci.yml` قُلِب معه، وهو لازمٌ لا تجميل:** كان «كلّ ما ليس PR ⇒ L5»،
  فمع تسقيف الفرع عند L3 كان يحجب **كلّ** دفعةٍ إلى فرع. صار الافتراضيّ L3،
  وL5 لدفعة `refs/heads/main` وحدها. السقف والطلب وجها عقدٍ واحد.
- **مُثبَت بالتكذيب ٣/٣:** نزعُ نطاق المرجع · قراءةُ سياسةٍ ناقصة متساهلةً · وضعُ
  الدمج بلا قياس مرجعه — كلٌّ أحمرّ باختباره المُسمّى. و١٠ اختبارات جديدة (٥٤ ⇒ ٦٤)،
  منها أنّ `main-backup` و`mainline` و`refs/tags/v9.1.0` **ليست** main: المطابقة
  تامّة لا بادئة.
- **حدّ صدق:** هذا **لا يُعيد تصنيف** الحزمة القديمة بأثر رجعي. هي دليلٌ صالح على
  أنّ Live-PG نجح لذلك الالتزام بعينه، و«L5» المكتوب فيها أثرُ الحارس القديم.
  وL5 المقبول للإصدار يُنتَج بإعادة Live-PG **على main** بعد الدمج، لا بإعادة قراءة
  وثيقةٍ صدرت قبل الإصلاح.

## GATE01-STATE-MODEL-POORER-THAN-ITS-DECISIONS-01 — `fixed` (2026-08-13 · بقرار المالك)

**العطل ليس في الحارس — الحارس كان يعمل كما صُمِّم.** العطل أنّ **نموذج الحالة أفقر من
القرارات الحقيقيّة**: `state` = OPEN/CLOSED وحدها لا تُمثِّل الحالة المشروعة «البوّابة
مغلقة عالميّاً، ولهذه الرقعة بعينها على هذه البايتات بعينها إذنُ مالكٍ بعد تجميد أدلّة
المرحلة ٠». فكان الخياران **فتحَ كلّ المسارات لأجل رقعة** أو **ردَّ إصلاحٍ صحيح**.

- **الحادثة المقيسة:** #837 تُصلِح M-01/M-02، وهما **بالضبط** في المسارات المجمَّدة،
  فحجبها `gate01_frozen_path_guard` بحقّ. ولا مخرج ضمن النموذج القديم إلّا أحد السيّئين.
- **العلاج — عقدٌ من أربع طبقات لا مفتاح:** سياسةٌ تدوم (`gate01_policy.json`: ماذا
  يُحمى وبأيّ مرحلة) · **نسخةُ تفويض تُستهلَك** (`gates/adjudications/*.json`: من أذن
  وبأيّ نطاق) · وحارسٌ **يشتقّ** PASS/BLOCK منهما ولا يملك القرار أيٌّ منهما وحده.
  والنسبة كنسبة سياسة RBAC إلى رمز وصول — لا مصدرَ حقيقةٍ ثالثاً.
- **والربط بالبايتات لا بالاسم:** `authorized_patch_sha256` على نصٍّ قانونيّ من
  `path\0blob_sha` مرتّبةً. فالقرار «أوافق على هذه البايتات» لا «أوافق على PR ٨٣٧»،
  وتغيُّر محرفٍ يُبطِله.
- **و`OPEN` صارت انتقالَ مرحلةٍ لا استثناءَ PR** — مكتوبةً في السياسة: لا transition من
  CLOSED إلى OPEN لمجرّد أنّ رقعةً تحتاج لمسَ ملفّ.
- **والتفويض لمرّةٍ واحدة:** `ISSUED` ⇒ `CONSUMED`/`REVOKED`، والمُستهلَك يُرفَض —
  وإلّا صار إذنٌ صدر لرقعةٍ باباً دائماً لكلّ PR لاحقة.
- **`GATE01-DIAGNOSIS-HIDDEN-BY-THE-JOB-NAME-01`:** كان الفحص خطوةً في وظيفة
  `no-report-only-change`، فيُقرأ الأحمر باسمٍ لا يصف سببه. فُصِل إلى وظيفة
  `gate01-physical-effect-freeze` — والاسم الذي يصف غير ما قاس يُطيل التشخيص.
- **مُثبَت بالتكذيب ١٠/١٠**، منها **ثلاثٌ موروثة من #836 أُعيد رسوّها بأسمائها** كي لا
  يُسقِط تحسينُ النموذج ما أثبته غيري: رصدُ المسّ · الفشل المغلق على حالةٍ غير OPEN ·
  الفشل المغلق على قائمةٍ فارغة. والسبعة الجديدة: مسارٌ زائد · بايتاتٌ تغيّرت · بصمةٌ
  تناقض بصماتها · مُستهلَك · أساسٌ مخالف · بوّابةٌ أخرى · مخطَّطٌ مجهول.
  ‏٣٢ اختباراً بعد ١١ ⇒ **٣١ حارساً / ١٩٣ طفرة**، والدَّين ١١٥ بلا زيادة.
- **وقرارٌ صغير خالف مقترح المالك بسببٍ مقيس:** السياسة بقيت في `docs/architecture/`
  مباشرةً لا في `gates/`، لأنّ `claim_base_guard` يمسح المستوى الأعلى وحده — فنقلُها
  كان **يُخرِجها من فحصٍ قائم** يُلزِمها ختمَ تحكيم. التفويضات في `gates/adjudications/`
  كما اقتُرِح.
- **ودورةُ الحياة اكتملت بعد الدمج (`09dbaeb7`):** خُتِم التفويض `CONSUMED` بـ`merge_sha`
  الحقيقيّ، فصار المسّ نفسه **محجوباً ثانيةً** — و`one_time` نيّةٌ حتّى يُثبِتها الرفض.
  ويُقاس ذلك بثلاثة تأكيدات: المُستهلَك لا يُمرِّر · وبإعادته `ISSUED` يمرّ (فالرفض
  سببه الاستهلاك لا عطبٌ في المطابقة) · و`CONSUMED` بلا `merge_sha` بطول ٤٠ مرفوض.
  والسجلّ يبقى قابلاً للفحص بعد الاستهلاك: بايتاتُه هي بايتاتُ ما دخل فعلاً.
- **وفجوةٌ P0 مفتوحة كشفها المالك — `GATE01-AUTHORIZATION-ORIGIN-UNENFORCED-01`:**
  الحارس يقرأ `approved_by: owner` **ولا يُثبِت منشأه**. والمقيس: لا `CODEOWNERS` في
  أيٍّ من المواضع الثلاثة، و`branch_protection_contract_guard` يفرض بنداً واحداً هو
  `required_conversation_resolution` — لا مراجعةً مطلوبة ولا مالكي كود. فطبقةُ
  AUTHORIZATION اليوم **وثيقةُ قدرةٍ محكومة النطاق**، لا برهانَ هويّة: من يحتاج
  التفويض يستطيع نظريّاً إصداره في نفس الـPR. والعلاج الأبسط حمايةُ المسار بهويّةٍ
  مراجِعة مستقلّة (‏CODEOWNERS + مراجعة مطلوبة) — **وهو إعدادُ مستودعٍ لا يملكه وكيل**.

- **حدّا صدق:** بصماتُ أدلّة المرحلة ٠ **مقروءة من واجهة GitHub** لا مُنزَّلة ومُعاد
  حسابها هنا — مرساةٌ تكشف التبديل لا تحقّقٌ مستقلّ. و`require_exact_head_sha` **منفَّذ
  ومُختبَر لكنّه off في هذه النسخة بسببٍ مقيس**: ملفّ التفويض يُلتزَم بعد الرقعة فأيّ
  رأسٍ فيه يسبق النهائيّ، وmain تحرّكت **مرّتين** أثناء هذه الـPR وحدها.

## GATE01-AUTHORIZATION-ORIGIN-UNENFORCED-01 — `mitigated` (الإنفاذ مبنيّ · 2026-08-13) · `open` (يحتاج إعدادَ مالكٍ)

**بُنِيَ الإنفاذ (2026-08-13) — والباقي فعلٌ لا يملكه وكيل.** المدخلة تقول إنّ الإغلاق
يحتاج «حمايةَ المسار بهويّةٍ مراجِعة مستقلّة **مع** بندٍ في `branch_protection_contract_guard`
يجعل الإعداد نفسه مفروضاً». البند نُفِّذ، والملفّ أُضيف، والإعداد وحده متبقٍّ:

- **`.github/CODEOWNERS`** يُسمّي مالك `docs/architecture/gates/adjudications/**`
  و`gate01_policy.json` — أوّل CODEOWNERS في المستودع (كان غائباً عن المواضع الثلاثة).
- **وبندٌ مشروط لا دائم** في `branch_protection_contract_guard`: يفرض
  `require_code_owner_review` على القواعد النافذة فعلاً **حين تمسّ الـPR مسار التفويضات
  وحدها**. والتناسب قرارٌ مقيس لا ذوق: بندٌ دائم كان يحجب **كلّ** دمجٍ في المستودع حتّى
  يُفعَّل إعدادٌ لا يملكه وكيل — وحمايةٌ تُوقِف العمل كلّه تُطفَأ، فتُنتِج حمايةً صفراً.
  فالحجب يقع على **الفعل الذي يحتاج الحماية**: إصدارُ تفويضٍ لا يمرّ إلّا ومراجعةُ
  مالكي الكود مفروضة.
- **والملفّ لا يُقرأ تفعيلاً:** الاختبار يفحص وجود السطر ويقول صراحةً إنّ التفعيل يقيسه
  البند على القواعد النافذة. فبلا الإعداد يبقى الملفّ خاملاً — وهو ما حذّرت منه المدخلة
  الأصليّة حرفيّاً، فلم يُخالَف.
- **ثلاث طفرات:** إسقاطُ البند ⇒ عودةُ الفجوة · جعلُه دائماً ⇒ حجبُ المستودع كلّه ·
  قراءةُ الغياب تفعيلاً ⇒ «نتيجةٌ عن سؤالٍ لم يُطرَح».
- **وما يبقى على المالك — فعلٌ واحد:** Rulesets → قاعدة على `main` →
  *Require review from Code Owners*. وفور تفعيله يصير البند مقيساً أخضر، ويُقفَل المدخل.
  وقبله: أوّل PR تمسّ مسار التفويضات **تُحجَب** برسالةٍ تسمّي الإعداد — وهو الإنفاذ
  المقصود لا عطل.

**تصحيحٌ مقيس (2026-08-14) — البند لم يكن يُقيَّم أصلاً.** كُتِب الاشتقاق أعلاه
بـ`git diff … > changed.txt || : > changed.txt` فوق استنساخٍ بعمق ١ وجلبٍ بـ`--depth=1`.
رفعت مراجعةٌ آليّة على #844 أنّه **يفشل مفتوحاً**، فجُعِل مغلقاً — وأوّل تشغيلٍ صادق
(job 94753838446) ردّ `fatal: origin/main...HEAD: no merge base`. أي أنّ `changed.txt`
كانت **فارغة في كلّ تشغيلٍ سابق**، و`touches_authorization` قرأ الفراغ «لم تُمَسّ» في
كلّ مرّة: البند المشروط لم يُقيَّم مرّةً واحدة منذ كُتِب، والخضرة كانت عن سؤالٍ لم
يُطرَح. العلاج: `fetch-depth: 0` وإسقاط `--depth=1`، وفرعٌ صريح لحدث `push`
(`github.event.before`)، وطباعة عدد المسارات المشتقّة. ومقفلا انحدار في
`tests_v9/test_run_outcome_guard.py` (الفشل المغلق · وجودُ تاريخٍ يُشتقّ منه)،
كلاهما مُكذَّب بزرع العطل.

والدرس أعمّ من الحادثة: **فشلٌ مفتوح لا يُخفي عطلاً محتملاً بل أخفى عطلاً واقعاً** —
ولم يظهر إلّا حين مُنِع الصمت. فالفارق بين «لم يُمَسّ» و«تعذّر أن أعرف» هو نفسه
الفارق الذي تطارده هذه الجلسة كلّها.

**الفجوة:** الحارس يقرأ `approved_by: owner` من ملفّ التفويض **ولا يُثبِت منشأه**.
فطبقة AUTHORIZATION اليوم **وثيقةُ قدرةٍ محكومة النطاق** — قويّة في النطاق والبايتات —
لكنّها ليست برهانَ هويّة: من يحتاج التفويض يستطيع نظريّاً إصداره في نفس الـPR.

- **المقيس لا المُرجَّح:** لا `CODEOWNERS` في أيٍّ من المواضع الثلاثة القانونيّة
  (`.github/` · الجذر · `docs/`). و`scripts/ci/branch_protection_contract_guard.py`
  يفرض **بنداً واحداً** هو `required_conversation_resolution` — لا مراجعةً مطلوبة،
  ولا مراجعةَ مالكي كود، ولا حمايةً على `docs/architecture/gates/adjudications/**`.
- **ولماذا لا يسدّها وكيل:** العلاج الأبسط `CODEOWNERS` + «مراجعة مطلوبة من مالكي
  الكود» — و`CODEOWNERS` وحده **ملفٌّ خامل** ما لم يُفعَّل الإعداد في GitHub، وذلك
  **إعدادُ مستودعٍ لا يملكه وكيل**. وإضافةُ الملفّ بلا الإعداد تُنتِج مظهرَ حمايةٍ بلا
  حماية — وهو صنف «حارسٌ يمرّ ليس حارساً يقيس» بعينه.
- **والبديل الثاني** توقيعٌ/تصديقٌ مستقلّ على ملفّ التفويض يتحقّق منه الحارس. لم
  يُبنَ: بناءُ توقيعٍ جديد أثقل من تفعيل حمايةٍ قائمة، وقرارُ أيّهما للمالك.
- **حدّ صدق:** ما نُفِّذ يمنع **توسيع** النطاق (مسارٌ زائد · بايتاتٌ مبدَّلة · إعادةُ
  استعمال) ولا يمنع **إصداراً ذاتيّاً** لتفويضٍ صحيح الشكل. والفرق مكتوبٌ هنا كي لا
  يُقرأ النموذج الرباعيّ مكتملاً حتّى طبقة السلطة.
- **الإغلاق يحتاج:** إمّا حمايةَ المسار بهويّةٍ مراجِعة مستقلّة **مع** بندٍ في
  `branch_protection_contract_guard` يجعل الإعداد نفسه مفروضاً (فلا ينحرف صامتاً)،
  وإمّا تصديقاً مستقلّاً يفحصه الحارس. وكلاهما يلزمه طفرةٌ تُكذّبه.
## GATE01-ONE-SHOT-LIFECYCLE-INCOMPLETE-01 — `fixed` (2026-08-13 · رصده المالك)

**الوعد كُتِب وفُرِض عند الاستعمال، ولم يُنهَ عند الدمج.** التفويض يحمل `one_time: true`
و`_authorization_errors` يشترط `status == "ISSUED"` — فالمُستهلَك يُرفَض بحقّ. لكن **لا
شيء في المستودع يُحوِّل `ISSUED` إلى `CONSUMED` بعد الدمج**، فبقيت الحالة الابتدائيّة
هي الحالة النهائيّة. أي أنّ الطبقة الوحيدة الناقصة في العقد رباعيّ الطبقات كانت
**إنهاء الدورة**، وهي بالضبط ما يُحوِّل «إذناً لمرّةٍ واحدة» إلى «باب دائم».

- **المصدر:** رصده المالك في مراجعته لـUEP-01، وأنا قرأتُ **الفرع** (`4c426308`) لا
  `main` فزعمتُ أنّ الختم تمّ — قراءتُه كانت الصحيحة.
- **القياس لا الاستنتاج:** شُغِّلت `evaluate()` حيّةً على `main = 2e390d10` بتفويض
  `GATE01-ADJ-2026-08-13-001` ومسّ `actuator_runtime.py` + `routers/commands.py`
  ⇒ **PASS**. والربط بالبايتات كان يعمل — فما مرّ ليس بايتاتٍ أخرى، بل **إعادة مسّ
  المسارين نفسيهما إلى الصيغة المأذونة** في أيّ PR لاحقة، بلا قرارٍ جديد من أحد.
  وذلك بعينه ما يُبطِل معنى «لمرّةٍ واحدة»: الإذن صدر لعملٍ تمّ، وبقي يُجيزه بعد تمامه.

- **وقوعٌ ثانٍ مقيس (2026-08-28) — والكاشفُ أطلق كما صُمِّم، فلا تُعاد الفجوةُ `open`.**
  بعد دمج #954 في `99000487` بقي `GATE01-ADJ-2026-08-28-001` بحالة `ISSUED` وبايتاتُه
  هابطة، فأحمرّ `gate01_frozen_path_guard` على **أوّل قياسٍ لاحق** — وكان على فرعٍ
  **لا يمسّ مجمَّداً أصلاً**. خُتِم `CONSUMED` بـ`merge_sha = 99000487` فعاد أخضر.
- **وما يستحقّ التسجيل ليس الوقوع بل موضعُ كلفته:** الإنذارُ صحيحٌ **ويقع على الطرف
  الخطأ**. مَن يدمج لا يرى الحمرة؛ يراها **مَن يدفع بعده** على تغييرٍ لا صلة له
  بالبوّابة، فيقرؤها عطلاً في عمله — وهو صنفُ «حارسٌ يُحمِّر الصوابَ» الذي يُدرَّب
  القارئُ على تخطّيه. **والعلاجُ ليس توسيعَ الحارس** بل صاحبٌ آليٌّ لخطوة الختم، وهي
  **غيرُ قابلةٍ للتنفيذ داخل الـPR بالبناء**: بصمةُ الدمج لا توجد قبل الدمج — القيدُ
  نفسُه المسجَّل في `MEASURED-ON-SQUASH-FRESHNESS-01`.
- **الختم:** `GATE01-ADJ-2026-08-13-001` صار `CONSUMED` مع
  `consumption.merge_sha = 09dbaeb75b77a7f0137b2df5d6ad4b5dfe214b47` وتاريخ الاستهلاك.
  وبعده: `evaluate()` على المسارين ⇒ **BLOCK** برسالة «حالته `CONSUMED` لا `ISSUED`».
- **والحارس لا يكتفي بالختم اليدويّ** — فرعٌ جديد يرصد التخلّف عنه:
  `stale_authorization_errors` يُحمِّر على تفويضٍ `ISSUED` **هبطت بايتاتُه في الشجرة**.
  والمُميِّز ليس تطابق البايتات (فهو حاصلٌ بالضرورة أثناء الـPR المأذونة) بل أن يكون
  الـdiff الحاليّ **لا يلمس** المسارات المأذونة: عندها التطابق يعني أنّها هبطت سلفاً.
- **ولا يُسأل GitHub «أمدموجةٌ الـPR؟»:** حالة GitHub تُقاس في الوظيفة ولا تدخل أداةً.
  المُميِّز أعلاه يُشتقّ من **الشجرة وحدها**، فيعمل محلّيّاً بلا شبكة ويلتقط الحالة نفسها.
- **والحارس بقي للقراءة فقط** — يكشف ولا يختم، بطلب المالك: حارسٌ يكتب أثناء CI يصير
  طرفاً في القرار الذي يحكم فيه. الختم إجراءٌ بشريّ بعد الدمج، والحارس يُذكِّر به.
- **واختبارٌ كان يحرس العطل:** `test_the_live_tree_is_permitted_only_by_an_exact_authorization`
  كان يؤكِّد أنّ التفويض المُنفَق **يمنح** PASS — أي أنّ الفجوة كانت مكتوبةً في اختبارٍ
  لا في شيفرة، وهو أخفى موضعٍ تختبئ فيه. أُعيد كتابته
  `test_the_live_authorization_is_spent_and_no_longer_grants`.
- **مُثبَت بالتكذيب ٦/٦ جديدة** (‏١٦/١٦ للحارس): تعطيل رصد الهبوط · نزع المُميِّز
  (فيتّهم الرقعة المأذونة أثناء PR-ها) · قلبه (فيتّهم ما لم يهبط) · قراءة الغياب هبوطاً ·
  مطالبة المختوم بختمٍ تمّ · **وفصلُ الاستدعاء عن نقطة الدخول** — دالّةٌ صحيحة غير
  مُستدعاة خضرةٌ عن سؤالٍ لم يُطرَح. ‏٣٩ اختباراً بعد ٣٢ ⇒ **٣١ حارساً / ١٩٩ طفرة**،
  والدَّين ١١٥ بلا زيادة.
- **حدّ صدق:** هذا يرصد **التخلّف عن الختم** ولا يختم، ولا يمنع مالكاً من إصدار تفويضٍ
  جديد لنفس البايتات — وهو الباب الصحيح: إذنٌ جديد بقرارٍ جديد.
## BRAIN-CLAIM-GUARD-CONFLATES-ADJUDICATION-WITH-GAP-01 — `fixed` (2026-08-13 · أسقط CI)

**المصدر:** `brain_commit_claim_guard` على `c210bc7` في #840 — «يذكر
`GATE01-ADJ-2026-08-13-001` — لا قسم ولا صفّ جدول يبدأ به».

معرّف التفويض يُطابِق شكل معرّف الفجوة (مقاطع كبيرة بشرطات)، فطولب بتسجيله في
`gaps/registry.md`. **وكِلا المخرجين كان كذباً:** تسجيلُه فجوةً كذبٌ صنفيّ — التفويض
إذنُ مالكٍ لا عطلٌ مرصود، وحالته `ISSUED`/`CONSUMED` لا `open`/`fixed`؛ وحذفُ المعرّف
من الرسالة يُخفي **أيّ تفويضٍ خُتِم**، وهو الكتمان الذي حذّر منه شرحُ الحارس نفسه حين
استُثنيت أرقام الاستشارات الأمنيّة.

**والعلاج ليس استثناءً ثالثاً بل تحقّقاً:** الاستشارة تُستثنى **اضطراراً** لأنّ مصدرها
خارج الشجرة ولا سبيل لقياسه؛ أمّا التفويض فمِلفٌّ **هنا** — فيُقاس وجوده في
`docs/architecture/gates/adjudications/<ID>.json`. وهذا **أقوى** من الاستثناء: معرّف
تفويضٍ ملفَّق يبقى ساقطاً، فمبدأ الحارس («الذكر ادّعاء») يبقى قائماً بحذافيره، وإنّما
صُوِّب السجلّ الذي يُسأل.

**والشكل كامل لا بادئة:** `^GATE\d{2}-ADJ-\d{4}-\d{2}-\d{2}-\d{3}$`. البادئة وحدها كانت
ستبتلع `GATE01-ONE-SHOT-LIFECYCLE-INCOMPLETE-01` — وهي فجوة حقيقيّة مسجَّلة أعلاه — وهو
بعينه فخّ `startswith("CVE-")` الذي أسقطه تكذيبُ الاستشارات قبله.

**والحارس خرج من الدَّين لا زاد فيه:** كان مُدرَجاً «سابق للآليّة — لم تُقَس تغطيته».
سُجِّل بسبع طفرات مُثبَتة بالتكذيب (ثلاثٌ للصنف الجديد وأربعٌ لسلوكه القائم: الفحص
الأساسيّ · استثناء الاستشارات · صفوف الجدول · حدّ المعرّف الملتصق بالعربيّة) ⇒
**٣٢ حارساً / ٢٠٦ طفرة، والدَّين ١١٥ ⇐ ١١٤**.
## MUTATION-ORACLE-DECIDES-ON-RAW-OUTPUT-01 — `fixed` (2026-08-13 · رصده المالك)

**المصدر:** `scripts/ci/guard_mutation_guard.py:256` و`:324` قبل الإصلاح — `expected not in out`.

الآليّة كلّها تقوم على تمييزٍ واحد: «سقط **المُسمّى**» لا «سقط شيء ما». والحكم كان
يُتَّخذ ببحثٍ نصّيّ في **كامل** مخرَج pytest، بينما `failing_tests()` موجودة في نفس
الملفّ وتستخرج أسماء `FAILED/ERROR` فعلاً. فالفجوة كانت في **مصدر القرار** لا في
القدرة على القياس.

**السيناريو الذي يمرّ خطأً:** المواصفة تُسمّي `test_A`، والطفرة تُسقِط `test_B`، ونصّ
مخرَج pytest يحوي `test_A` في موضعٍ ليس سطر سقوط — رسالة تأكيد، أو تتبُّع مكدّس، أو
معامل `parametrize`، أو سطر تجميع. عندها يُقرأ الحكم `expected_red` والقاعدة **غير
محروسة**. وهو العطل الذي وُجِد `expect` ليمنعه، بصيغةٍ أخبث: يختبئ خلف اسمٍ صحيح.

**ولم يكن تشغيلٌ سابق مزوَّراً:** الـ٢٠٧ طفرة كانت صحيحة **بالنسبة للعقد المنفَّذ**؛
والعطل أنّ العقد المنفَّذ **أضعف من العقد المعلَن**. ولا تناقض بين «٢٠٧ خضراء» و«فجوة
في المِعيار»: الطفرة التي تكشفها لم تكن مكتوبةً أصلاً.

- **العلاج:** `expected not in observed` حيث `observed = failing_tests(out)`، **في
  الموضعين**: `_outcome` و`_run_mutations_in_place`. والثاني ليس تكراراً — هو **مسار
  الحجب الفعليّ**، وتصحيح الأوّل وحده كان يترك القرار الحاجب على البحث النصّيّ: دالّةٌ
  صحيحة لا تحكم.
- **ومُثبَتٌ بطفرتين تُعيدان الصيغة القديمة حرفيّاً** (`in observed` ⇐ `in out`)، لا
  بـ`if False:` — لأنّ السؤال هنا «أيّ مصدرٍ يقرأ» لا «أيفحص أم لا».
- **والاختباران يُبنيان على معطىً يحوي الاسم نصّاً:** بلا ذلك لا يُميّز الاختبار بين
  الصيغتين ويمرّ تحت الطفرة. المُدخَل الاصطناعيّ يجعل `test_beta` يسقط برسالةٍ تذكر
  `test_alpha`، والمواصفة تُسمّي `test_alpha` السليم.
- **وأُعيد ترسية طفرةٍ قائمة:** `guard_mutation_guard.py[3]` كانت ترسو على السطر القديم
  فصارت بائتة بالتصحيح — أمسكها `test_real_registry_passes_the_static_check` في أوّل
  تشغيل، وهو الفحص الثابت يحرس مواصفاته من التعفّن.
- **والقياس بعد التشديد:** `--run` **كاملاً** ⇒ **٢٠٩/٢٠٩** خضراء، فلم ينقلب حكم أيّ
  طفرة قائمة. أي أنّ التشديد أغلق باباً ولم يكشف تغطيةً كاذبة قائمة.

**حدّ صدق:** هذا يُحكِم **إسناد** السقوط إلى اسمه، ولا يقيس أنّ الاختبار سقط **للسبب**
المزروع — طفرةٌ تكسر شيئاً آخر داخل الاختبار المُسمّى نفسه تبقى خارج المدى.
## RLS-DOCS-TEACH-A-COMMAND-LINE-PASSWORD-01 — `fixed` (2026-08-14)

**المصدر:** `scripts_v9/README_RLS_TESTING.md:18` · `scripts_v9/test_tenant_isolation.sql:8`
· `scripts_v9/runtime_truth_report.py:62` — ثلاثتها تحمل
`postgresql://sahool_user:PASS@…` داخل **أمرٍ يُنسَخ ويُشغَّل**.

والقاعدة مكتوبة في المستودع منذ v208: «لا تضع كلمة المرور في سطر أوامر مشترك ولا في
سجلّ». فكانت الوثائق **تنهى في موضعٍ وتُعلِّم في آخر** — وسطرُ الأوامر يُقرأ من `ps`
ويُحفظ في تاريخ الصدفة.

**والعطل في الشكل لا في الكلمة:** `PASS` نفسها ليست سرّاً. العطل أنّ **شكل** المثال
يضع الاعتماد في الموضع الخطأ، فمن يستبدلها بسرٍّ حقيقيّ يتبع ما رآه. ولذلك يرصد
الفحص `scheme://role:anything@` لا السلسلة `PASS`.

- **العلاج:** الدور يبقى (`sahool_user` هو الدرس: غير superuser وإلّا تُجوَّز RLS
  ويُقرأ الفشل نجاحاً)، والاعتماد يُنزَع، ويُذكَر **بديلُه** في كلّ موضع: `~/.pgpass`
  بصلاحية `0600` أو `PGPASSWORD` من مخزن أسرار. و«لا تكتبها هنا» بلا «اكتبها هناك»
  تُنتِج التفافاً لا امتثالاً — فيُقاس ذكرُ البديل باختبارٍ مستقلّ.
- **ويُقاس بقاء الدرس لا زوال الشكل وحده:** حذفُ المثال كلّه كان يُرضي الفحص الأوّل
  بلا إصلاح، فأُضيف تأكيدٌ على بقاء `sahool_user` في نفس الملفّ.
- **وحدّ الفحص مُعلَن ومقيس:** يحرس **ثلاثة ملفّات** لا الشجرة. المسح الشجريّ يعطي
  **١٢٣ موضعاً في ٧١ ملفّاً**، وأغلبها مشروع: قواعد CI المؤقّتة (`.github/workflows/ci.yml`
  وحدها ٣٠ موضعاً)، وتجهيزات اختبار، و`${VAR}` في compose. فحارسٌ شجريّ كان يقتضي
  مُصنِّفاً لا أملك تبريره، وحارسٌ يتّهم الصحيح يُنزَع في أوّل يوم.
- **ولم يُصحَّح `docs/history/POST_EXECUTION_PLAN.md:27`** وفيه الشكل نفسه: سجلٌّ يقول
  ما قيل حينها، وتصحيحُه يجعل السجلّ يخالف نفسه — ولا أحد يُشغّل خطّةً من أرشيف.
  مذكورٌ هنا كي لا يُقرأ الإغفال سهواً.

**حدّ صدق:** هذا يمنع **تعليم** الشكل الخاطئ في ثلاثة ملفّات، ولا يمنع أحداً من كتابة
الاعتماد في طرفيّته، ولا يفحص بقيّة الشجرة.
## TRANSPORT-ACK-MISLABELED-AS-EXECUTED-01 — `open` (مقيس · محجوب بـGATE-01)

**المصدر:** `services/actuator-service/actuator_runtime.py:144-146`.

```python
def _dispatch_outcome_status(send_success: bool) -> str:
    """دالّة نقيّة: نتيجة النشر ⇒ حالة التنفيذ. نجاح النشر ⇒ executed (نُشِر≠نُفِّذ)، وإلّا failed."""
    return "executed" if send_success else "failed"
```

دالّةٌ تُترجم **إقرار الوسيط** (نجاح `publish` بـ`qos=1` إلى MQTT) إلى الكلمة
`executed`. و`send_mqtt_command` لا تنتظر إقراراً من الجهاز إطلاقاً: تُعيد `True` فور
نجاح النشر (`services/actuator-service/actuator_runtime.py:604-611`). فالكلمة تدّعي **أثراً فيزيائيّاً** عن قياسٍ
لا يبلغ إلّا الوسيط — وشرحُ الدالّة نفسه يقول «نُشِر≠نُفِّذ»، أي **تُقرّ بالفارق ثمّ
تطمسه في القيمة المُعادة**.

**وتصحيحُ ادّعائي السابق — والفارق جوهريّ:** صغتُ هذه الفجوة أوّلاً بأنّ المسار الحيّ
يُبلِّغ إقرار النقل تنفيذاً. **القياس ردّ ذلك:** المسار الحيّ **صادق**:

```
services/actuator-service/actuator_runtime.py:368   receipt_status = "accepted" if sent else "failed"
services/actuator-service/actuator_runtime.py:378   "published": bool(sent),
services/actuator-service/actuator_runtime.py:379   "note": "published != physically executed — outcome verification is a separate step"
services/actuator-service/routers/commands.py:66    "sent": success
```

`accepted` · `published` · `sent` — ثلاثتها تصف النقل ولا تدّعي أكثر منه، ومعها ملاحظة
صريحة بالفارق. فالعطل **ليس** في ما يُكتَب اليوم.

**بل هو سلاحٌ مُعبَّأ لا عطلٌ عامل:** لا مستدعي لـ`_dispatch_outcome_status` في الإنتاج
البتّة — الوحيد الذي يُبقيها حيّةً اختبارُها
(`services/actuator-service/test_dispatch_bridge.py:108-109`)، وهو يُثبِّت التسمية بدل
أن يكذّبها. فمن يصل غداً إلى هذا الملفّ يجد دالّةً جاهزة اسمها ومخرَجها يقولان
«حالة التنفيذ»، فيستعملها — ويرث ادّعاءً لم يقِسه أحد. وهذا صنفٌ مُسجَّل في هذا
المستودع: **كلمةٌ تدّعي أكثر ممّا قِيس**.

**العلاج المقترَح (لم يُنفَّذ):** تسمية المُخرَج بما قِيس — `dispatched` أو `published`
بدل `executed` — أو حذف الدالّة وتحرير اختبارها، لأنّ الدالّة بلا مستدعٍ لا تُفقَد.
و`executed` تبقى محجوزةً لِما يُثبِته **تحقّقٌ من الأثر**، وهو خطوة منفصلة تقول الشجرة
نفسها إنّها منفصلة.

**ولماذا `open` لا `fixed`:** `services/actuator-service/actuator_runtime.py` **مسارٌ
مجمَّد** في `docs/architecture/gate01_policy.json`، والبوّابة `CLOSED` والتفويضات الحيّة
صفر. فمسُّه يقتضي تفويض مالكٍ مقيَّداً — ولا يُفتَح من طرف المنفِّذ.

**حدّ صدق:** المرصود **تسمية** في دالّة غير مُستدعاة. لا يُدَّعى أنّ أثراً فيزيائيّاً
أُبلِغ خطأً في أيّ سجلّ حيّ — القياس يقول عكس ذلك.
## CI-JOB-NAME-CLAIMS-MORE-THAN-IT-MEASURES-01 — `fixed` (2026-08-14 · الحدّ لا العطل)

**المصدر:** `.github/workflows/field-workspace-production-closure.yml` — اسم الوظيفة
«Field Workspace **Production Closure**»، والمقيس فيها **عقودٌ ساكنة** لا غير.

الخطوات المقيسة: تحقّق أنواع عقد Field Workspace · بناء الواجهة · ميزانية الحزمة ·
سجلّ الطبقات · ثلاث بوّابات إغلاق بايثون · أربع بوّابات Decision SoR · اثنا عشر اختبار
حارس. **ولا بيئة حيّة في أيّ خطوة:** لا قاعدة، ولا PostGIS، ولا وسيط، ولا واجهة
منشورة، ولا طلبٌ واحد إلى خدمةٍ تعمل.

**والفارق ليس تسميةً:** «العقود متماسكة» و«النظام يعمل» جوابان عن سؤالين مختلفين،
وأخضرٌ واحد يُقرأ كأنّه يحملهما معاً. وهو الصنف المتكرّر في هذا المستودع: **خضرةٌ عن
سؤالٍ لم يُطرَح** — ونظيره المُسجَّل `GATE01-DIAGNOSIS-HIDDEN-BY-THE-JOB-NAME-01`
حيث كان الاسم يصف غير ما قاس فأطال التشخيص.

- **العلاج المتاح بلا بيئة حيّة:** أن **تقول الجولة ما قاسته وما لم تقِسه** — في
  `$GITHUB_STEP_SUMMARY` نفسه لا في وثيقةٍ جانبيّة يقرؤها من يبحث أصلاً. الوسم
  `CONTRACT_CLOSURE_ONLY`، ثمّ تعداد المقيس، ثمّ **تعداد غير المقيس** صراحةً، ثمّ
  تصريحٌ بأنّ `runtime_verified` و`production_certified` لا تتحرّكان بهذه الجولة.
- **و`if: always()` مقصود:** حدٌّ يظهر عند النجاح وحده يُقرأ تهنئةً، وأوان الحاجة إليه
  الفشل. وهو **أوّل استعمال** لـ`$GITHUB_STEP_SUMMARY` في ٥٦ workflow في هذا المستودع.
- **ومعه ثلاثة إحكامات تشغيليّة مقيسة:** `permissions: contents: read` (السعة التي لا
  تُستعمَل تبقى سطحاً قائماً؛ ١٥ من ٥٦ تفعلها) · `timeout-minutes: 20` (المقيس ~٧٠ ثانية
  والسقف الافتراضيّ ست ساعات؛ **واحدة** من ٥٦ تضبطه) · `concurrency` بالإلغاء **في الـPR
  وحدها** — على main يبقى لكلّ التزامٍ مدموج سجلٌّ خاصّ به، وإلغاؤه يُفقِد دليلاً هبط فعلاً.
- **ولم تُقسَّم الوظيفة إلى نطاقات عطل، وهذا قرارٌ لا إغفال.** التقسيم آمنٌ تقنيّاً —
  قِيس أنّ بوّابات بايثون تقرأ **مصادر** الواجهة لا مصنوعات بنائها (لا `dist/` ولا
  `node_modules`) — لكنّ اسم الفحص `field-workspace-closure` قد يكون **فحصاً مطلوباً**
  في حماية الفرع، ولا أستطيع قراءة قائمة الفحوص المطلوبة بالأدوات المتاحة. فالتقسيم
  إمّا يُيتِّم اسماً مطلوباً فلا يُبلَّغ أبداً، أو يُنشئ وظيفةً **غير حاجبة** — أي مظهرَ
  صرامةٍ مع نزع حجب. والقاعدة: لا يُنزَع حجبٌ لأجل شكل.
- **ويُحرَس الحدّ باختبار** (`tests_v9/test_field_workspace_closure_workflow_declares_its_boundary.py`،
  ٧ حالات): حدٌّ مكتوب في YAML يُحذَف بسطرٍ ولا يُحمِرّ شيء، فيعود الاسم يدّعي وحده.
  ويُقاس معه **بقاء الخطوات العشر المقيسة** — فحدُّ ادّعاءٍ أصدق مع فحصٍ أقلّ صفقةٌ خاسرة.

**حدّ صدق:** هذا يجعل الجولة **تُصرِّح** بما لا تقيسه؛ ولا يقيس شيئاً جديداً، ولا
يُقرّب الإغلاق الحقيقيّ خطوةً. والإغلاق الحيّ يبقى حيث كان.
## API-PACKAGE-NAME-COLLIDES-ACROSS-SERVICES-01 — `open` (مقيس 2026-08-14)

**المصدر:** خدمتان تُصدِّران حزمةً عليا اسمها `api`. و`tests_v9/test_roadmap_phase23.py`
يُدخِل مسارات خدماتٍ إلى `sys.path` (`:97` · `:236` · `:1310` · `:1971` …)، فيصير
`api.connectors.openmeteo` في `sys.modules` **نسخةَ weather-service** بدل نسخة
sahool-platform. ومن يستورد أوّلاً يفرض تفسيره على الجلسة كلّها.

**مُثبَتٌ بالعزل لا بالترجيح:**

```
test_weather_solar_fields + test_sensing_adapter_service_token      ⇒ ٧ ناجحة
  + test_tool_contracts                                            ⇒ ١٩ ناجحة
  + test_sahool_brain_forensic                                     ⇒ ١٢ ناجحة
  + test_roadmap_phase23                                           ⇒ ٥ ساقطة
AttributeError: module 'api.connectors.openmeteo' has no attribute '_build_daily'
```

**وكشفه وسمٌ لا حدس:** وسمتُ `test_roadmap_phase23` بـ`unit` فأسقط **خمسة اختبارات
موسومة سلفاً وخضراء منذ سنة**. أي أنّ الملفّ لم يكن «مؤجَّلاً لتبعيّة ناقصة» فحسب —
دخولُه الجناح **يُعدي غيره**. ونُزِع الوسم، وصار سببه في الأساس مقيساً
(`shadows_api_package_in_sys_modules`) بدل `missing_test_dependency` وحده.

**وهو الصنف المُسجَّل في هذا المستودع باسم #590:** «ناجح منفصلاً ≠ ناجح مُجمَّعاً» —
وقد حذّر منه الأساس نفسه في دليل `test_field_forms_api_integration`، وكنتُ سأقع فيه
لولا أنّ الجناح الكامل قِيس **بالاسم لا بالعدد**.

**العلاج المقترَح (لم يُنفَّذ):** تسميةُ حزم الخدمات تسميةً مميّزة، أو عزلُ استيراد
كلّ خدمة في عمليّة فرعيّة. وكلاهما أكبر من شريحة وسم، ويمسّ خدماتٍ متعدّدة.

**حدّ صدق:** المقيس تصادمُ اسمٍ واحد (`api.connectors.openmeteo`) بين خدمتين. لم أجرد
بقيّة الأسماء المتصادمة، ولا أدّعي أنّها وحدها.
## TEST-NAMED-FILES-THAT-ARE-NOT-TESTS-01 — `open` (مقيس 2026-08-14)

**المصدر:** `tests_v9/test_db_integration.py` (٢٠٩ أسطر) · `tests_v9/test_e2e_offline_flow.py`
(١٦٠ سطراً) — يجمع pytest من كلٍّ منهما **صفر** عنصر.

كلاهما **سكربت** بـ`__main__` ودالّة `run_all()`/`run_e2e_flow()`، وتأكيداتُه داخل
دوالٍّ لا يبلغها المُجمِّع (`_run_async` · `run_e2e_flow`). ووثيقة الأوّل تقول صراحةً
«التشغيل: `python3 tests_v9/test_db_integration.py`» — أي أنّه صُمِّم سكربتاً وسُمّي
اختباراً ووُضِع في شجرة الاختبارات.

**والأثر:** الاسم يَعِد بتغطية، والشجرة تعدّه ملفَّ اختبار، وpytest لا يرى فيه شيئاً.
فهو **صفر تغطية بمظهر تغطية** — ولا يُحمِرّ لأنّه لا يُنفَّذ أصلاً.

- **ولم يُوسَما في شريحة الوسم عمداً:** العلامة على ملفٍّ يجمع صفراً تُنقِص عدّاد
  الأساس بلا أن يُنفَّذ شيء — **تجميلُ رقم لا سدادُ دَين**. والأساس يصنّفهما
  `not_a_pytest_module` بحقّ.
- **العلاج المقترَح:** إمّا تحويلُهما إلى اختبارات حقيقيّة (الثاني **يعمل بلا بنية
  تحتيّة** فيصلح `unit`؛ والأوّل يحتاج PostgreSQL حيّة فيصلح `integration`)، أو نقلُهما
  خارج `tests_v9/` بأسماء لا تَعِد بما لا تعطيه.

**حدّ صدق:** المرصود ملفّان بهذا الشكل في `tests_v9/`. لم أجرد بقيّة الشجرة.

## GUC-NAME-MISMATCH-CLAIM-REFUTED-01 — ⛔ سجلّ تحكيميّ لا فجوة تنفيذيّة (2026-08-08 · M-05 = `WITHDRAWN_FALSE_POSITIVE` في v06)

- **الادّعاء:** `services/soil-service/p1_store.py:9` · `p2_store.py:9` · `p3_store.py:17` تضبط `app.current_tenant_id` بينما «كلّ سياسات RLS تقرأ `app.current_tenant`» ⇒ متغيّر لا يقرؤه أحد.
- **الردّ بالدليل:** `migrations/v161_soil_p1_products.sql:35` · `v162_soil_p2_spatial_products.sql:27` · `v163_soil_p3_assessment_products.sql:32` تُنشئ `CREATE POLICY tenant_isolation ... current_setting('app.current_tenant_id', true)` — **مطابقةً للمخزن حرفيّاً**.
- **علّة الخطأ (لي):** فحصتُ **جانب الضبط** وعمّمتُ على السياسات بلا فحصها. أي أنّي حكمتُ على تغطية لم أقِسها — **نفس العطل الذي وُجِد هذا الفحص كلّه ليكشفه، داخل الفحص نفسه**.
- **لا يُنفَّذ أيّ إصلاح E6 — وإدخاله كان سيُعطّل RLS الصحيح في p1/p2/p3.** هذا المدخل **سجلّ تحكيميّ** يُحفظ لئلّا يُعاد اقتراح «إصلاحه»، وليس بنداً تنفيذيّاً؛ والبنود التنفيذيّة خمسة: M-01 · M-02 · M-03 · M-04 · M-06.
- **ما يبقى مشروعاً:** تعدّد أسماء الـGUC (`app.current_tenant` · `app.current_tenant_id` · `app.tenant_id`) يستحقّ **جرداً** ضمن حارس M-06، بلا توحيد ميكانيكيّ.

## FORCE-WITH-LEASE-DEFEATED-BY-ITS-OWN-FETCH-01 — ⚠️ حادثة مقيسة بلا تلف (2026-08-08)

- **المصدر:** إجراء الدفع في هذه الجلسة: `git fetch origin <branch>` ثمّ `git push --force-with-lease` — وهو الترتيب الذي اتّبعتُه، وهو الذي يُبطِل الحماية.
- **العلّة:** الـlease يقارن الرأس البعيد بـ**`remote-tracking ref`** المحلّيّ. والـ`fetch` يُحدِّث ذلك المرجع بعينه للتوّ. فالشرط يتحقّق **لأنّ الأساس الذي يقيس عليه تحرّك بيدي**، لا لأنّ البعيد لم يتحرّك. حمايةٌ تُبلِّغ «آمن» عن سؤالٍ أُبطِل قبل طرحه.
- **ما وقع:** كان الفرع البعيد قد تحرّك من `808d85f93` إلى `4ffe262f6`، ودفعتُ فوقه فقُبِل الدفع.
- **ولماذا لم يقع تلف — بالقياس لا بالاطمئنان:** `4ffe262f6` **دمجٌ** والداه `808d85f93` (مدموج في `main` عبر #768) و`54a91d8ee` (على `main`)؛ `git show --stat` مصنوعات مولَّدة فقط، وفحص الكائنات على كلّ ملفّ مختلف أعطى **صفر blob فريد**. لا شيء ضاع — **بالحظّ لا بالتصميم**، وهو تمييزٌ يُسجَّل لأنّ إخفاءه يُنتِج ثقةً كاذبة بالإجراء.
- **الإجراء الصحيح:** يُقرأ الرأس البعيد **قبل** أيّ `fetch` ويُمرَّر صريحاً — `git push --force-with-lease=<ref>:<sha-known>` — أو يُتحقَّق من محتوى ما سيُدهَس **قبل** الدفع لا بعده. و`fetch` يسبق `--force-with-lease` **يُلغيه**.
- **صلته بالنمط:** هذا رابع ظهور لصنف «فاحصٌ يُبلِّغ نتيجةً عن سؤال لم يطرحه» في هذه الجلسة، والفرق أنّ الثلاثة السابقة كانت في أدوات، وهذا **في ترتيب أصابعي** — والأداة التي بُنيت لمنع صنف الإتلاف الصامت (`resolve_merge_conflicts.py`) لا تغطّي الدفع، بالتصميم.
- **حدّ صدق:** حادثة مُسجَّلة لا حارس. لا شيء في CI يمنع تكرارها، ولا يُدَّعى غير ذلك.
## `ALTER-TABLE-PREFIX-ORDER-BLINDS-TWO-DETECTORS-01` — نفس العطل في كاشفين (مُغلَقة 2026-08-08)

**الحالة:** مُغلَقة · **المصدر:** مراجعة #811، مُعادُ القياس على `fc79fbbef` (رأس `main` بعد دمج #811 بالضغط) ·
`scripts/ci/snapshot_eligibility_separation_guard.py:66` · `scripts/ci/capability_mapping_engine.py:168`.

**قواعد PostgreSQL:** `ALTER TABLE [ IF EXISTS ] [ ONLY ] name [ * ]` — أي `IF EXISTS`
**قبل** `ONLY`. وكلا الكاشفين كتب الترتيب المعكوس، فالصيغة القانونيّة تمرّ من أمامهما.

**والوجهان مقيسان لا مفترضان:**

| الكاشف | ماذا يفعل النمط الخاطئ | الأثر المقيس |
|---|---|---|
| `snapshot_eligibility_separation_guard` | `(?:only\s+)?(?:if\s+exists\s+)?` ⇒ `ALTER TABLE IF EXISTS ONLY <t> ADD COLUMN decision_eligible` **لا يُرى** | صفر — لا استعمال حيّ للكلمتين على `ALTER TABLE` في الشجرة. **العطل كامنٌ لا واقع** |
| `capability_mapping_engine.TABLE_RE` | `(?:\s+if\s+not\s+exists)?` اختياريّة **قابلة للتراجع**: عند `CREATE TABLE IF NOT EXISTS + DROP POLICY…` (تعليقٌ عربيّ في هجرة) يفشل ما بعدها فيتراجع المُطابِق إلى صفر تكرار ويلتقط `IF` **اسم جدول** | **١٢ مدخلاً كاذباً** على `fc79fbbef`، مصادرها تعليقات وملفّات اختبار |

**ولماذا وجدناه أصلاً:** لأنّ نصّ الطفرة الجديدة يحوي حرفيّاً
`ALTER TABLE IF EXISTS ONLY <t>`، فوُلِّد في `GUARD_CATALOGUE.md:209` ⇒ التقطه المُصنِّف
وأضاف **أربعة** مداخل كاذبة جديدة، ورفع `capabilities_multidimensional` من **٤٨ إلى ٤٩**.
أي أنّ إصلاح الكاشف الأوّل هو ما كشف الثاني — والرقم الحوكميّ تحرّك على كذبة.

**وأثر الإصلاح مقيس على المخرَج المُلتزَم:** ١٦ ⇒ **٠** مدخلاً باسم كلمة مفتاحيّة ·
`capabilities_multidimensional` ٤٩ ⇒ **٤٨** (قيمة `fc79fbbef` نفسها) · `mapped` ٧٤ بلا تغيّر.
فالإصلاح **يُزيل ادّعاءً** ولا يُنشئ واحداً.

**والعلاج مختلف في الكاشفين لأنّ الخطر مختلف:**

* في الحارس: تُقبَل الكلمتان **بأيّ ترتيب** وتُقبَل النجمة الوراثيّة — هذا **كاشف** لا
  مُحلِّل نحويّ، والإفراط في الالتقاط لا يكلّف شيئاً (SQL غير القانونيّة تفشل في الترحيل
  أصلاً)، أمّا التقصير فهو العطل بعينه.
* في المُصنِّف: **نظرة أمام سالبة** تمنع أن يكون الاسم الملتقَط كلمةً مفتاحيّة — أيّاً كان
  مسار التراجع. لأنّ المطلوب هنا ليس «التقِط أكثر» بل «لا تُسمِّ ما ليس جدولاً جدولاً».

**مُثبَت بالتكذيب:** طفرتان مُسجَّلتان في `guard_mutation_registry.json` (الخامسة والسادسة
على هذا الحارس، RUN أخضر على الستّ جميعاً) تُسقِطان `test_the_full_postgresql_grammar_is_caught`
و`test_every_legal_alter_prefix_is_caught` · وإعادة النمط القديم
في المُصنِّف تُسقِط **خمسة** اختبارات مُسمّاة في
`tests_v9/test_capability_mapping_table_extraction.py`، بينها واحد يقيس **المخرَج المشحون**
لا الدالّة وحدها — لأنّ دالّةً تُصلَح ومصنوعةً لا يُعاد توليدها تبقى تُقرأ صادقة.

**وحدّ الصدق:** `capability_mapping_engine.py` ليس `*_guard.py`، فلا يقبله
`guard_mutation_guard` (نطاقه `GUARD_GLOBS`). التكذيب هنا **نُفِّذ يدويّاً ووُثِّق**، وليس
مفروضاً آليّاً في CI. وهذه فجوة نطاقٍ في آليّة الطفرات نفسها: **المولِّدات خارج مداها**.

## `GENERATED-AT-STILL-WALL-CLOCK-IN-THREE-GENERATORS-01` — شريحة مستقلّة (مفتوحة، رُصِدت 2026-08-08)

**الحالة:** 🔴 مفتوحة · **شريحة منفصلة بقرار المالك** — لا تُخلَط بـ#811 ·
**المصدر:** `scripts/ci/deterministic_time.py` (العقد قائم) مقابل ثلاثة مُنتهِكين مقيسين:

| الملفّ | السطر | ما يُكتَب |
|---|---|---|
| `scripts/ci/runtime_deployment_manifest.py` | 102 | `datetime.now(UTC).isoformat()` |
| `scripts/ci/unified_production_readiness_gate.py` | 113 | `datetime.now(UTC).isoformat()` |
| `scripts/ci/functional_probe_runner.py` | 321 | `started` (ساعة حائط) |

**والعقد المعياريّ موجود ومُطبَّق في مكان واحد فقط** —
`runtime_environment_preflight.py:144` يستدعي `generated_at_utc(cwd=ROOT)`. أي أنّ
`DETERMINISTIC-GENERATION-AND-MERGE-SAFETY-01` **مكتوبٌ ومُنفَّذ جزئيّاً**، وما بقي ليس
تصميماً جديداً بل **توسيع تطبيق**.

**والقاعدة الحاسمة المكتوبة في العقد نفسه:** `int(os.getenv("SOURCE_DATE_EPOCH") or time.time())`
**ممنوعة** — تُعيد اللاحتميّة صامتةً (تعمل في CI حيث المتغيّر مضبوط، وتفشل عند المطوّر بلا
رسالة). فالتوسيع يمرّ عبر `generated_at_utc` لا عبر ارتدادٍ محلّيّ.

**وحدّ الصدق:** لم يُقَس بعدُ **كم التزاماً** غيّرته هذه الثلاثة وحدها (القياس المُوثَّق
في `deterministic_time.py` يخصّ `SAHOOL_RELEASE_MANIFEST` فقط: ٣ التزامات غيّرت الختم
وحده من أصل ١٢٨). فالأولويّة **غير مُثبَتة** — تُقاس قبل فتح الشريحة، لا بعدها.

---

## `CAPABILITY-DB-DIMENSION-COUNTS-NO-RELATION-CONTRACT-01` — `fixed` (‏#812)

**المصدر:** `scripts/ci/capability_mapping_engine.py:TABLE_RE` · مقيس على `68cc8cfb7`.

> **تصويب مستوى العنوان — `###` بدا تسجيلاً ولم يدخل سجلّ العناوين.** كُتِب هذا المدخل
> أوّلاً بـ`### `، فظهر في الوثيقة وقُرِئ مُسجَّلاً وهو ليس كذلك: `brain_deferral_registry_guard`
> يبني مجموعة المعرّفات المُعلَنة من `line.startswith("## ")` أو من صفّ جدولٍ يبدأ عموده
> الأوّل بالمعرّف — و`### ` لا يُطابِق الأوّل (الحرف الثالث `#` لا مسافة) ولا الثاني.
> فكانت الفجوة **مكتوبةً وغير مُسجَّلة**، وأسقط الحارسُ الدفعةَ محقّاً.
>
> وهو صنف «شكلٌ يُقرأ ادّعاءً لا يحمله» بعينه الذي تلاحقه هذه الشريحة كلّها: مثل نمطٍ
> يصمت عن `TEMP` فيُقرأ حكماً وهو مصادفة. والدرس واحد في الحالتين — **ما يُحتَجّ به يجب
> أن يكون ما يُقاس فعلاً**، لا ما يشبهه في العين.

**الادّعاء الذي كان يُقرأ:** بُعد `database` في `capability_mapping.json` يُقرأ «العلاقات
التي تعيش في هذه المنصّة». **والمقيس أنّه لم يكن يسأل ذلك السؤال أصلاً.** النمط طلب
`TABLE` **مباشرةً** بعد `CREATE`، فسقط كلّ ما بينهما مُعدِّل:

| الصيغة | قبل | بعد | الحكم |
|---|---|---|---|
| `CREATE TABLE orders (` | `['orders']` | `['orders']` | ✓ |
| `CREATE TEMP TABLE staging (` | `[]` | `[]` | ✓ لكن **بالمصادفة** قبلُ، **بالعقد** بعدُ |
| `CREATE GLOBAL/LOCAL TEMP(ORARY) TABLE` | `[]` | `[]` | كسابقتها |
| `CREATE UNLOGGED TABLE fast_cache (` | **`[]`** | `['fast_cache']` | ✗ **علاقةٌ دائمة كانت مفقودة** |

**ولماذا كان الصمت عن المؤقّت خطراً وهو صحيح:** لأنّه لم يكن حكماً. يوم يُدعَم أيّ
مُعدِّل — وقد دُعِم `UNLOGGED` في الشريحة نفسها — يعود المؤقّت مع الدائم **صامتاً**، ولا
شيء يقول إنّ معنى الرقم تغيّر. الصمت الصحيح لسببٍ خاطئ لا يبقى صحيحاً.

**العلاج:** `_NOT_TEMPORARY` نظرةٌ نافية تُبطِل المطابقة عند `TEMP`/`TEMPORARY` وببادئتَي
`GLOBAL`/`LOCAL`، و`UNLOGGED` وحدها تُقبَل مُعدِّلاً — لأنّها تفقد **بياناتها** عند
انهيارٍ غير نظيف لا **تعريفها**: مالكٌ وقيودٌ وفهارس وهجرةٌ تُنشئه.

**المُكذِّبات (مقيسة، لا مُدَّعاة):**

- قبل الإصلاح: `test_an_unlogged_table_is_a_permanent_relation` ⇒ **٣/٣ حمراء**.
- طفرة «دعم مُعدِّل ثالث» (`_NOT_TEMPORARY = ""` + `(?:\w+\s+){0,2}`) ⇒
  `test_a_temporary_table_is_never_a_database_relation` **٧/٧ حمراء**،
  و`test_the_declared_out_of_scope_forms_are_silent[جدول أجنبيّ]` **حمراء** — أي أنّ
  اختبار حدّ النطاق حدٌّ حيّ لا حشو.

**حدّ الصدق — مكتوبٌ في المصدر لا هنا وحده:** هذا ماسحُ **الجداول المحلّيّة الدائمة**
المُعلَنة بـ`CREATE TABLE`/`ALTER TABLE`، لا ماسحُ علاقات PostgreSQL كلّها. خارج مداه:
`CREATE FOREIGN TABLE` · المشاهد المُجسَّدة · `SELECT … INTO` · المتتاليات. **وخلوّ بُعد
`database` من إحداها ليس حكماً بغيابها.**

**وحدّ صدقٍ ثانٍ:** `capability_mapping_engine.py` ليس `*_guard.py` فهو **خارج مدى**
`guard_mutation_guard` (`GUARD_GLOBS`). التكذيبان أعلاه يدويّان ومقيسان، **ولا يفرضهما
CI** — ما يفرضه CI هو بقاء الاختبارات خضراء، لا بقاء قدرتها على الاحمرار.

---

## `SPEC-LOADER-ASSERTED-AFTER-THE-CALL-THAT-NEEDS-IT-01` — `fixed` (‏#812)

**المصدر:** خمسة مواضع `spec_from_file_location` في دلتا #812.

> **تصويب مستوى العنوان — والقرابة مع العطل الموصوف تحته ليست مصادفة.** كُتِب هذا المدخل
> أوّلاً بـ`### `، فبدا مُسجَّلاً ولم يدخل مجموعةَ المعرّفات التي يبنيها
> `brain_deferral_registry_guard` من `startswith("## ")` أو من عمود جدولٍ أوّل. ذكرٌ في
> النثر لا يُنشئ مدخلاً ولا حالة — وهذا نصّ الحارس صراحةً.
>
> **ونفس البنية في العطل الذي يصفه هذا المدخل:** تأكيدٌ على `spec.loader` **بعد**
> `module_from_spec` يبدو حارساً ولا يُبلَغ حين يكون `spec` نفسه `None`. حارسٌ على بابٍ خلف
> الباب المكسور هناك، وتسجيلٌ خلف عتبة التسجيل هنا. **والموضع هو الحكم، لا الوجود.**

`spec_from_file_location` يُرجِع **`None`** لمسارٍ غير قابل للتحميل — ملفٌّ نُقِل أو
أُعيدت تسميته. وموضعان كانا يؤكّدان `assert spec.loader is not None` **بعد**
`module_from_spec(spec)`؛ فعند `spec is None` يرمي `module_from_spec` خطأً خاماً عن
`None` **قبل** بلوغ التأكيد. حارسٌ على بابٍ خلف الباب المكسور: يُقرأ الفشل خطأً برمجيّاً
في الاختبار بدل «الملفّ ليس هناك».

**العلاج:** `assert spec is not None and spec.loader is not None` برسالةٍ تُسمّي المسار،
**قبل** `module_from_spec`، في المواضع الخمسة.

**وعطلٌ ثانٍ ظهر أثناء العلاج — خارج النطاق المُعلَن وكان لازماً:** في تجهيزتَي
`actuator` (`test_manual_command_killswitch_scope.py` · `test_compensation_killswitch.py`)
كان التأكيد **خارج `try`** بينما أكعاب `sys.modules` حُقِنت **قبله**. فأيّ خروجٍ منه
يترك الأكعاب مُسرَّبة إلى بقيّة الجناح — وهو **بالحرف** الصنف الذي يُكذِّبه
`test_a_failed_load_does_not_leave_stubs_behind`، والمُسجَّل في هذا السجلّ نفسه بشرط
إغلاقٍ يقول «لا يبقى في `tests_v9` حقنٌ دائم في `sys.modules` لوحدة أمنيّة». نُقِل
التأكيد **داخل `try`**، فصار كلّ خروجٍ ينظّف.

---

## `LIVE-PG-EVIDENCE-LEAKS-THE-DIAGNOSTIC-IT-DENIES-01` — `fixed` (رقعة متابعة #816)

**المصدر:** `scripts/ci/live_pg_evidence_guard.py` · مقيس على `bff877fe7` (بعد دمج #816).

**وثيقةٌ تُقرِّر خاصّيّةً لا تحملها — الصنف نفسه، في المصنوعة هذه المرّة.** `$comment`
في `live_pg_evidence.json` يقول حرفيّاً «لا تحوي مضيفاً ولا منفذاً ولا مستخدماً ولا
كلمة مرور»، بينما مسار الفشل المغلق كان يكتب `str(exit_.code)` في `problems` —
و`psql()` تضمّ أوّل **٤٠٠ محرف** من `stderr` في رسالتها.

**والقياس على تشخيص اتّصالٍ واقعيّ:** تسرّب إلى الملفّ المرفوع مصنوعةً **المضيف
(`db.internal`) وعنوانه (`10.0.0.7`) والمنفذ (`5435`) واسم المستخدم (`sahool_user`)
وكلمة المرور** — خمسة من خمسة.

**والاختبار القائم لا يمسكه، وهذا هو الأهمّ:**
`test_the_evidence_carries_no_connection_variable` يزرع متغيّرات الاتّصال في البيئة،
لكنّه يُبدِّل `role_properties` و`server_identity` و`schema_drift` — فلا يُستدعى `psql`
أصلاً ولا يدخل `stderr` الوثيقة. **يحرس قناةً غير القناة المكسورة**، وخضرتُه كانت
تُقرأ شهادةً على الاثنتين.

**العلاج فصلٌ بنيويّ لا تنقية نصّيّة:** `GuardExit` يحمل سببين — خاماً يُعاد رفعه فيظهر
في **سجلّ الوظيفة** حيث موضع التشخيص، ومُعرَّفاً ثابتاً (`PSQL_CATALOGUE_QUERY_FAILED`
وأخواته) هو وحده ما يدخل المصنوعة. ومسار المصنوعة **لا يرى النصّ الخام أصلاً**.

**ولماذا رُفِضت التنقية بتعبير نمطيّ** (بنصّ المالك): تشخيصات libpq متعدّدة الصيغ، فقد
تُسرِّب اسم قاعدةٍ أو مستخدمٍ بعد حذف المضيف والمنفذ — ومُنقٍّ يُقرأ ضماناً وهو **تخمينٌ
عن صيغٍ لم تُحصَ**.

**والافتراضيّ الآمن هو الصمت لا النشر:** `SystemExit` عاديّة — مسارٌ يُنسى تصنيفه —
تُنتِج `UNCLASSIFIED_FAIL_CLOSED_EXIT` لا النصّ الخام. فالإصلاح غير مشروطٍ بأن يتذكّر
كاتبُ المسار القادم.

---

## `LIVE-PG-ROLE-NAME-ENTERS-SQL-UNESCAPED-01` — `fixed` (رقعة متابعة #816)

**المصدر:** `scripts/ci/live_pg_evidence_guard.py:role_properties` · مقيس على `bff877fe7`.

`app_role` — من `--app-role` أو `SAHOOL_TEST_PGROLE` — كانت تدخل `rolname='{app_role}'`
**بلا تهريب**:

| القيمة | ما يصل إلى `psql` | الأثر |
|---|---|---|
| `sahool_app` | `rolname='sahool_app'` | سليم |
| `ops'role` | `rolname='ops'role'` | **استعلامٌ مكسور** |
| `x' OR true --` | `rolname='x' OR true --'` | **يُغيّر الصفّ المقروء** |

**ووصفُ المدى يُضيَّق بصدق:** CI يمرّر `sahool_app` **ثابتاً**، فلا استغلال قائم اليوم.
المُدَّعى **عطلُ سلامةٍ في الواجهة** — وهي تقبل القيمة من راية وبيئة — لا اختراقٌ واقع.

**العلاج `_sql_literal` بتضعيف الاقتباس، لا حذفه:** `ops'role` اسمٌ **مشروع** في
PostgreSQL، وتنقيةٌ تحذف العلامة كانت ستُنتِج العمى المقابل — بحثاً عن دورٍ آخر **بصمت**،
وهو أسوأ من الكسر لأنّه يُجيب عن سؤالٍ غير الذي طُرِح.

---

## `MERGED-WHILE-A-REVIEW-WAS-IN-FLIGHT-01` — `open` (حادثة إجرائيّة مقيسة)

**المصدر:** #816 · مقيس من طوابع GitHub.

```
تعليقا المراجعة أُنشئا      2026-08-09T00:06:17Z
#816 دُمِج                  2026-08-09T00:06:58Z      ← بعدهما بـ41 ثانية
حالة الخيطين                is_resolved=false · is_outdated=false
```

فحصتُ الفحوص ووجدتُها خضراء ودمجتُ **دون قراءة خيوط المراجعة**، فصار `NO_MERGE` مرفوعاً
شكلاً وغيرَ محقَّقٍ فعلاً: المراجعة كانت قد وصلت ولم تُقرأ. **والملاحظتان صحيحتان معاً**،
فالكلفة لم تكن نظريّة.

**وهذا الدرس مُسجَّل في هذا المستودع من قبل** (‏`hot.md`، ختم 2026-08-07): «الاخضرار ليس
إذناً بالدمج حين تكون المراجعة معلنة ومنتظَرة». تكرارُه يعني أنّه **لم يصر إجراءً**.

**ولا يُعالَج بإعادة كتابة التاريخ** (بنصّ المالك): #816 مدموج، والعلاج التزامٌ جديد
وPR مستقلّ — وهو هذا. **والبند يبقى مفتوحاً** لأنّ ما يمنع التكرار ليس هذه الرقعة:
قراءةُ خيوط المراجعة قبل الدمج **غير مفروضة بأيّ حارس**، وتسجيلُها هنا لا يفرضها.

---

### تحديث `MERGED-WHILE-A-REVIEW-WAS-IN-FLIGHT-01` (2026-08-09) — البند يبقى `open`، ومعه الآن مدقّق

**ما تغيّر:** أُضيف `scripts/ci/branch_protection_contract_guard.py` ووظيفة
`branch-protection-contract` في `capability-governance.yml`. تجلب الوظيفة
`repos/<owner>/<repo>/rules/branches/main` — **القواعد النافذة** (كان `branches/main/protection`؛ أجاب `404 Branch not protected` والقفل مُفعَّل عبر Ruleset، تشغيل 31407522822) — ويحكم الحارس على الملفّ: البند المفروض
واحد — `required_conversation_resolution.enabled == true`.

**وما لم يتغيّر — ولهذا يبقى البند مفتوحاً:**

| السؤال | الجواب المقيس |
|---|---|
| هل يمنع الحارس دمجاً؟ | **لا.** يمنعه إعدادُ GitHub وحده |
| هل يرى خيط مراجعة؟ | **لا.** يرى إعداداً، لا حالةَ خيط |
| هل يُغلِق السباق (خيطٌ يُفتَح بين الفحص والدمج)؟ | **لا.** لا شيء في CI يُغلِقه |
| فماذا يفعل؟ | يمنع أن **يُطفَأ القفل صامتاً** بعد تفعيله |

**والاعتماد على المالك صريحٌ وحاجب:** الوظيفة حمراء حتّى (١) يُفعَّل
`Require conversation resolution before merging` على حماية `main`، و(٢) يُوفَّر سرّ
`BRANCH_PROTECTION_AUDITOR_TOKEN` — إذ `GITHUB_TOKEN` الافتراضيّ **لا يقرأ**
`branches/*/protection`. وهذا مقصود: الـPR لا يخضرّ إلّا بعد تفعيل القفل، فيصير
**إثبات التفعيل شرطَ الدمج** بدل سطرٍ آخر يقول «اقرأ الخيوط».

**والقسمة بنيويّة لا ذوقيّة:** الشبكة في الوظيفة والحكم في الحارس. فـ`scripts/ci/**` لا
يستدعي GitHub في هذا المستودع (مقيس)، وعقد `test_local_preflight_contract:83` يمنع ذلك
على الأداة المحلّيّة؛ ودرسُ `resilient_docker_pull.sh` يمنع دفن المنطق في `run: |`.
والسابقة العاملة: `runtime-verification-promotion.yml` يُدقّق `required_reviewers` لبيئة
النشر بالنمط نفسه.

**خمس طفرات مُسجَّلة، كلّها زُرِعت وأسقطت اختبارها المُسمّى.** وواحدة **لم تزرع شيئاً في
أوّل صياغة**: تبديلُ `except FileNotFoundError` بصنفٍ آخر يلتقطه `except OSError` التالي
فيبقى الفشل مغلقاً — صُحِّحت لتُرجِع «مضبوط» عند غياب الملفّ. الآليّة عملت **عليّ** لا لي،
للمرّة الرابعة.

## `BRANCH-PROTECTION-TEST-FIXTURE-BREAKS-UNDER-C-LOCALE-01` — `fixed` (على main، لا على الشريحة)

**المصدر:** `tests_v9/test_branch_protection_contract_guard.py` (‏#820) · مقيس على
`c636b437` **النقيّ** بصفر تغيير منّي.

خطوة ١٠ من بروتوكول ما قبل الدفع تُشغّل `pytest -m unit` تحت `LC_ALL=C PYTHONUTF8=0`
عمداً — «المتّجه الذي يخفيه Linux». والاختبار يستعمل اسم ملفّ **عربيّاً**
(`لا-وجود-له.json`)، فتحت لغة C يصير ترميز نظام الملفّات ASCII:

```
UnicodeEncodeError: 'ascii' codec can't encode characters in position 63-64
```

**والحارس سليم؛ التجهيزة هي الهشّة.** الاستثناء يقع **قبل** أن يبلغ الاستدعاءُ الحارسَ،
فالاختبار يسقط على اسم ملفّه لا على ما يقيسه — وتأكيدُه عن **ملفّ غائب**، والعربيّة فيه
زينة لا خاصّيّة.

**والسببيّة مقيسة لا مُستنتَجة:** على `c636b437` النقيّ ⇒ `rc=1`؛ وبعد تحويل الاسم إلى
ASCII ⇒ `rc=0`؛ وتحت UTF-8 يبقى الملفّ كلّه أخضر (لا انحدار). المحتوى العربيّ في
`write_text(..., encoding="utf-8")` سليمٌ ولم يُمسّ — **المسار وحده** هو ما لا يحتمل
لغة C.

**وأثره أنّه يُحمِّر `preflight --full` للجميع على main**، فبوّابةٌ وُضِعت لتقيس متّجه
الترميز صارت تسقط على تجهيزةٍ من نفس الصنف الذي تقيسه.

## `NON-ASCII-TEST-FIXTURE-PATH-BREAKS-C-LOCALE-01` — `fixed` (نمطٌ تكرّر ثلاثاً فصار حارساً)

**المصدر:** `#820` ثمّ `#824`، وكلاهما مقيس على `main` **النقيّ** بصفر تغيير منّي.

خطوة ١٠ تُشغّل `pytest -m unit` تحت `LC_ALL=C PYTHONUTF8=0` عمداً. وتحت هذه اللغة يصير
ترميز نظام الملفّات ASCII، فمسارٌ عربيّ يرفع `UnicodeEncodeError` **قبل** أن يبلغ
الاستدعاءُ الحارسَ.

```
#820  test_branch_protection_contract_guard.py   "لا-وجود-له.json"   main النقيّ rc=1
#824  test_frontend_lint_debt_guard.py            "لا-وجود-له.json"   main النقيّ rc=1
```

**والتأكيد في الحالتين عن ملفٍّ غائب، والعربيّة في الاسم زينةٌ لا خاصّيّة.** أمّا المحتوى
العربيّ في `write_text(..., encoding="utf-8")` فسليمٌ تماماً — الترميز مُثبَّت صراحةً.
فالعطل في **المسار** وحده، وهذا ما يجعل العلاج ممكناً بلا مساس بعربيّة المستودع.

**ولماذا حارسٌ لا تصحيحٌ ثالث:** التصحيح يُصلح ما وقع، والنمط يتكرّر لأنّ كاتب الاختبار
لا يرى خطوة ١٠ وهو يكتب. وكلّ تكرارٍ **يُحمِّر `preflight --full` للجميع على main** —
فالبوّابة الموضوعة لقياس متّجه الترميز تسقط على تجهيزةٍ من الصنف نفسه.

**والكاشف بنيويّ لا نصّيّ:** يقرأ بـ`ast` ويُميّز السلسلة المستعملة في بناء مسار
(`tmp_path / "…"` · `Path("…")` · `os.path.join`) عن أيّ نصّ عربيّ آخر. وregex على السطر
كان سيُنذِر على آلاف الأسطر المشروعة — **إنذارٌ يُدرَّب قارئُه على تجاوزه ليس حارساً**،
ولذلك للاختبار الثاني شقٌّ يُثبِت أنّه **لا** يُمسِك النصّ العربيّ غير المساريّ.

**التكذيب:** زرعان واحداً واحداً ⇒ كلٌّ أسقط اختباره **بالاسم** وسمّى السطر بعينه.

## `BRAIN-ENTRIES-REAUTHORED-NOT-CARRIED-ACROSS-REBASES-01` — `fixed` (‏`d3e09a60`)

**المصدر:** جردٌ على `d3e09a60` بعد دمج #825 — **اثنتا عشرة فجوة من أربع عشرة كتبتُها
في هذه الجلسة غائبة عن main**، والناجيتان هما الأحدث وحدهما.

الشريحة أُعيد تأسيسها **خمس مرّات** على قواعد متتالية. وفي كلّ مرّة كنتُ أحمل الملفّات
المصدريّة برقعة، ثمّ **أكتب مداخل الدماغ من جديد** بـ`cat >>` بدل حملها من الرأس السابق.
فحملت كلّ جولةٍ مداخلَها وحدها، وسقط ما قبلها.

```
كُتِبت في هذه الجلسة   14 فجوة
وصلت main              2   (الجولة الأخيرة وحدها)
ضاعت                  12   منها سجلّ الحزمة المحجوبة والعطل الإنتاجيّ المُسجَّل
```

**وحارس الإلحاق لم يُطلِق، وهذا ليس عيباً فيه.** `brain_append_only_guard` يقيس أن
**لا يصغر** الملفّ، وقاعدته مُصرَّح بها: «القاعدة ليست بادئة‑بايت» لأنّ `registry.md`
يحمل تعديلات حالة مشروعة. وفي كلّ جولة كان الملفّ = دماغ main + مداخلي الجديدة، فهو
**أكبر دائماً**. المفقود لم يكن حجماً بل **مداخل بعينها**.

**والصنف هو صنف الجلسة معكوساً:** أطاردتُ طوال الجلسة «مصنوعةً تُحمَل بدل أن تُولَّد»،
ووقعتُ في نقيضها — **سجلٌّ يُكتَب من جديد بدل أن يُحمَل**. والمصنوعة تُعاد توليداً
فتُصحِّح نفسها، أمّا السجلّ فلا مولِّد له: ما لم يُحمَل ضاع بلا أثر.

**والعلاج إجرائيّ لا نصّيّ:** عند إعادة التأسيس تُحمل `sahool-brain/` **بالرقعة من الرأس
السابق مقابل قاعدته**، كما تُحمل المصادر — لا تُكتب من جديد. واستُعيدت الاثنتا عشرة هنا.

## `GATE-01-EXECUTION-CONTROL-SLICE-WITHHELD-01` — `blocked` (حكم المالك 2026-08-09)

```
PHASE_0_EVIDENCE_FREEZE   NOT_PROVEN
PHASE_1_CODE_CHANGES      NOT_AUTHORIZED
REAL/CUTOVER              BLOCKED
```

**٢٣ ملفّاً محجوباً:** التنفيذ الفيزيائيّ (`actuator_runtime.py` · `routers/commands.py`)
· claim/lease وv228 ومنظومتها (`phase_runtime_workers.py` · `phase_runtime_store.py` ·
`event_bus.py` · `v228_phase_runtime_claim_leases.sql` · `MANIFEST.txt` ·
`run_migrations.sql`) · اختبارات killswitch والحدث والـoutbox والclaim ·
`db_ownership.yml` · `physical_effect_boundary_contract.json` · تدقيق المستأجِر واختباره
· وستّة ملفّات كود خدميّ شُحِنت خطأً ثمّ أُخرِجت.

**والفصل مقيس لا مُسمّى:** `event_bus.py` يقرأ `claim_token` و`claimed_at` و
`claim_expires_at`، ولا يُنشئها إلا v228 ⇒ اختباراه مشدودان إليه بنيويّاً. و
`db_ownership.yml` ليس «مختلطاً» كما بدا بعدّ الأسطر: كلا تعديليه يستشهد بـv228 —
**عدّ الأسطر يقيس الحجم لا الانتماء**.

**لا تُدمَج حتّى تجميد evidence pack وقبولها صراحةً على SHA نهائيّ.**

## `WORKER-TENANT-GUC-SET-OUTSIDE-ANY-TRANSACTION-01` — `blocked` (مُسجَّل لا مُصلَح)

**المصدر:** `services/sahool-platform/api/phase_runtime_workers.py:47-50,378,387` و
`shared/helpers.py:171-186`.

`set_config(…, true)` محلّيّ للمعاملة؛ وخارج معاملة صريحة تكون العبارة معاملةَ نفسها
فيزول الضبط. والعامل ينادي `_set_tenant` في **سبعة** مواضع تحت `pool.acquire()` **بلا**
`conn.transaction()`.

```
تحت sahool_app (NOBYPASSRLS · FORCE RLS)   صفر صفوف — عطلٌ صامت
تحت دور خدميّ BYPASSRLS                     قراءةٌ عابرة للمستأجِرين
```

**وتأكيدٌ مستقلّ:** نسخة الفحص الجنائيّ تضيف **٧** كتل `conn.transaction()` حيث الأساس
**صفر**. و`shared/helpers.py` يحمل العطل نفسه **بلا مستدعٍ واحد** ⇒ كامن.

**وثلاثة تبريرات allowlist تقول «tenant GUC set tx-locally … (RLS-scoped)»** واصفةً ضبطاً
معامليّاً لا وجود له — فلم تُنسخ صياغتها إلى مفتاح جديد.

**ولا يُصلَح:** الملفّان في الحزمة المحجوبة، وقاعدة المالك «يُسجَّل ويوقف الملفّ المعنيّ؛
لا يُصلَح ضمن الشريحة». **ولا يُدَّعى في أيّ موضع أنّ الإصلاح دخل.**

## `TENANT-AUDIT-PRECISION-COUPLED-TO-A-BLOCKED-FILE-01` — `blocked` (اقتران مقيس)

`scripts/tenant_query_audit.py::_tables_in_call` المُحسَّن يقطع المسح عند **النداء
التالي**، فيَنسِب الجداول إلى استعلامها؛ فمفتاحٌ كان `soil_lab_tests,water_ledger` صار
`soil_lab_tests` مفرداً بلا مفتاح، فاحمرّ على `phase_runtime_workers.py:403`.

**المقياس الحاسم:** يمرّ **٨/٨** مع العامل المُعاد كتابته ويسقط مع الأصليّ.

**ولم يُحَلّ بمفتاح allowlist** (‏للـRAW **المتعمَّد** بنصّ وثيقته، وهذا عطلٌ لا قصد)
**ولا بتليين الاختبار** — بل بنقل الملفّين إلى المحجوبة حيث إصلاحُهما.

## `PHASE-0-SLICE-OVERSHIPPED-UNAUTHORIZED-CODE-01` — `fixed` (‏`d3e09a60`)

**المصدر:** `blocked-paths.txt` في `SAHOOL_GATE01_TOOLCHAIN_v3.1` مقابل الشريحة المدفوعة.

دُفِعت شريحة Phase 0 بـ**٥٦** ملفّاً، وفيها **ستّة ملفّات كود خدميّ**: `agents/base_agent.py`
· `services/mcp_servers/market_server.py` · `market_db_authz.py` · `shared/oauth_middleware.py`
· `services/sahool-platform/api/trueup.py` · `shared/helpers.py`.

**وحكم المالك حصر Phase 0 في أربعة أصناف:** الأدلّة · الجرد · الحرّاس · الاختبارات.
والكود التشغيليّ ليس أحدها، و`PHASE_1_CODE_CHANGES: NOT_AUTHORIZED` نصٌّ صريح. صُنِّفت
Phase 0 لأنّها «غير فيزيائيّة» — **وغير الفيزيائيّ ليس أحد الأربعة**: استدلالٌ بالنفي لا
بالانتماء.

**والخضرة لم تكن حارساً:** `preflight --full` أعطى **صفر إخفاقات** على تلك الشريحة.
البوّابات تقيس **الاتّساق لا الإذن**، فمجاوزةُ حكمٍ حوكميّ تمرّ خضراء **بالضرورة**.
لولا القياس الخارجيّ لَما ظهر.

## `PHASE-0-SUBJECTS-WIDENED-THROUGH-THE-JOURNAL-01` — `fixed` (‏`d3e09a60`)

طُوِيت ملفّات الدماغ الثلاثة داخل `phase0-paths.txt` فصار العدد **٣٩**، فبدت مواضيع
Phase 0 تسعةً وثلاثين. **وإعادة كتابة السجلّ ليست موضوعاً من مواضيع الشريحة**، وطيُّها
داخلها يجعل «‏subjects = N» عدداً لا يعني ما يقول — ويفتح باباً يدخل منه مسارٌ محجوب
تحت عنوان «تحديث سجلّ».

**العلاج فئة ثالثة مُعلَنة لا توسعةٌ للأولى:** `governance-journal-paths.txt` منفصل،
والحارس يرفض تقاطع السجلّ مع المواضيع **ويرفض** تقاطعه مع المحجوب — وكلاهما مُثبَت
بطفرة أسقطت اختبارها بالاسم. ويبقى السجلّ **محكوماً**: تعديلٌ غير مُعلَن فيه يُرفض.

## `CRLF-PHANTOM-ARTIFACT-DRIFT-01` — `fixed` (‏`d3e09a60`)

**المستودع مُنصَّب على Windows**، و`.gitattributes` كان يثبّت LF لـ`.sh` و`.sql` و`.py`
**ولا يذكر `.json` ولا `.md` ولا `.csv`**. فما لا يُثبَّت يُحوَّل عند السحب، والمولِّدات
تكتب `\n` ⇒ حرّاس المصنوعات يُبلِّغون انحرافاً **لا وجود له**.

```
مصنوعات مولَّدة متعقَّبة        165
منها غير مثبَّتة               158  (٩٥٪) — .json ٨٨ · .csv ٣٤ · .md ٢٩ · .sha256 ٤
التقرير الوارد قدّر             9
```

**والتكذيب مباشر:** زُرِع CRLF في مصنوعة واحدة ⇒ الحارس `rc=1` **بالرسالة نفسها**،
والاستعادة ⇒ `rc=0`.

**و`.csv` استُثنيت عمداً — مقيساً لا احتياطاً:** `csv.writer` في بايثون افتراضُه
`lineterminator='\r\n'` والمولِّدات تفتح بـ`newline=""` فتحفظه، بينما ثلاثة عشر موضعاً
تضبطه إلى `\n`. فالمُلتزَم **مختلط بحقّ**: ٢٦ بـCRLF و٢١ بـLF، وكلٌّ يطابق مولِّده.
`eol=lf` هناك كان سيفرض **انحرافاً دائماً على كلّ المنصّات بما فيها CI** — أسوأ ممّا
يُصلح. و`-text` يحفظ بايتات كلّ ملفّ كما كتبها مولِّده. وبعد التصحيح:
`git add --renormalize .` ⇒ **صفر تغيّر محتوى**.

## `CI-GUARDS-CRASH-ON-NON-UTF8-CONSOLE-01` — `fixed` (‏`d3e09a60`)

الحرّاس يطبعون بالعربيّة، وطرفيّة Windows الافتراضيّة `cp1252` لا تُرمِّزها ⇒
`UnicodeEncodeError` يُسقِط الحارس **قبل أن يقيس شيئاً**. سبعة من أربعة عشر حارساً ثابتاً
سقطت هكذا، وصفرٌ على Linux؛ وأُعيد إنتاجه بـ`PYTHONIOENCODING=cp1252` ⇒ نفس الاستثناء.

**وأوّل صياغة أبطلت بوّابةً قائمة.** `export` عامّ ورِثته خطوة ١٠
(`LC_ALL=C PYTHONUTF8=0`) — وهي موجودة **لتقيس متّجه الترميز نفسه**. القياس المباشر:
الاختبار يمرّ بلا المتغيّر ويسقط معه. فصار الضبط داخل `run` وحده، مع
`env -u PYTHONIOENCODING` صريحة في خطوة ١٠. **النطاق جزءٌ من الإصلاح لا تفصيلٌ فيه.**

**وخطوة ١٠ لم تكن تغطّي العطل أصلاً:** pytest يلتقط المخرجات فلا تمرّ بمُرمِّز الطرفيّة،
بينما `preflight.sh` يطبع مباشرةً.

## `TASK-COMPLETION-NOTIFIED-BEFORE-THE-PROCESS-EXITS-01` — `open` (دين قياس)

أُطلِق `verify_all_generated.py --fix` في الخلفيّة فوصل إشعار «اكتمل بالرمز 0»، فقُرِئت
الشجرة وأُعلِنت نتيجتان. ثمّ أظهر `pgrep` **ثلاث** عمليّات ما تزال حيّة تكتب الشجرة نفسها:
الإشعار كان خروج الغلاف لا خروج العمليّة.

```
المُعلَن (باطل)     ٥٩ ملفّاً · «--check يمحو الزرع» · «عدم تقارب ٥٩→٥٧»
المعزول (صحيح)     fix_rc=0 · check ×2 rc=0 بشجرة ثابتة · --check لا يكتب
مدّة --fix          > ١١ دقيقة ⇒ كلّ قراءة قبلها من منتصف التشغيل
```

**والعلاج علامة إتمام يكتبها السكربت نفسه** والاستطلاع عليها. **ويبقى مفتوحاً:** لا حارس
يمنع قراءة شجرة تكتبها عمليّة حيّة.

## `PIPE-TO-HEAD-ABORTED-AN-ATOMIC-GIT-APPLY-01` — `open` (دين قياس)

`git apply -3 patch | head -5` طبع «Applied patch … cleanly» خمس مرّات ورمزَ خروجٍ صفراً،
**والشجرة لم تتغيّر**: `head` أغلق الأنبوب فوصل SIGPIPE إلى `git apply`، وهو **ذرّيّ**
فأجهض بلا كتابة — والرمز المقروء رمزُ `head` لا `git`.

وفي الجولة نفسها: `git diff` لم يلتقط `.gitattributes` لأنّها **مُدرَجة**، فضاع نصف
إصلاحٍ صامتاً حتّى كشفه عدُّ القواعد. **الجامع: قناة القياس تكذب، لا المقيس** — وهو ثالث
صنف من نوعه في هذه الجلسة.

## `GATE01-TOOLCHAIN-PHASE0-MANIFEST-NOT-A-FIXED-POINT-01` — `fixed` (خارج المستودع · v3.2)

`phase0-paths.txt` في أداة GATE-01 v3.1 (‏٢٠ مساراً) تشحن `route_inventory.csv` بلا
`route_inventory.generated.json`، و`service_inventory.csv` بلا قرينه — **أزواج مولِّدٍ
واحد مشقوقة**.

```
verify_all_generated --check على الـ20      rc=1 — «حارس كتب أثناء الفحص»
--fix ⇒ الحمولة الحقيقيّة                   36
--check على الـ36                            rc=0 · مستقرّة
```

**ولماذا لم يمسكها `audit_phase0_composition`:** يفرض `phase0-paths == archive payload`
بالضبط، فيجعل القائمة والحزمة تتّفقان — **ووثيقتان تتّفقان وكلتاهما خاطئة**. لا شيء فيه
يسأل *المستودع* إن كانت الحمولة كاملة. والعلاج يسأل **بوّابة المستودع نفسها**، ورُفِضت
قاعدة «الزوج القرين» لأنّها تخمينٌ يبيت أوّل ما يتغيّر مولِّد.

**سُلِّم في `SAHOOL_GATE01_TOOLCHAIN_v3_2` — حزمة مستقلّة، لا في هذا المستودع.**

## `GATE01-TOOLCHAIN-V3-ARCHIVE-IS-NOT-THE-PATCH-BASE-01` — `open` (تعارض مُدخَلات)

```
v3.zip   e37535c438dce71edbbc7a7cbc6b5db129ff14cee1aff2e96869842421ba5da7
v3.1.zip 2d9a3350cb74e7bdf092f86c2ef35a8fff750d5d6152163317062a4aa4f7cd83
patch    826d4b214a63f9dae4967946ef78c8f3f586295d6dd0140fc0b2b08a61cdc1c7
```

الرقعة تُضيف ملفّين من `/dev/null` **وكلاهما موجود في v3 المرفوع**، وv3 يحمل
`test_phase0_composition.py` حيث يحمل v3.1 `test_audit_phase0_composition.py`.
فالمرفوع **ثلاث نسخ لا اثنتان**، والرقعة لا تنطبق على ما وصل — قِيس الفرق بمقارنة
شجريّة مباشرة.

**وما صمد مقيسٌ لا مقروء:** `SHA256SUMS` ١٦/١٦ · الجناح **٣٨/٣٨** · ومرساة السلطة على
`d303d9c6`: **١٩/١٩** موضع نداء، **١١/١١** علماً، **٨/٨** قواعد اكتشاف. (وظهرت واحدة
مختلّة حتّى تبيّن أنّ `path_globs` تُوسَّع بـ`fnmatch` — **الخطأ في القراءة لا في
المرساة**، وإعلانه فجوةً كان سيُتلِف مرساةً سليمة.)

## `AI-SOT-REMEDIATION-BASE-IS-NOT-ITS-DECLARED-BASELINE-01` — `open` (حزمة واردة)

`SAHOOL_AI_SOT_LIVE_CERT_REMEDIATION.patch` تُعلِن `Baseline: d303d9c6` ولا تنطبق عليه:
**٢٨ خطأً / ١٤ ملفّاً**. وعلى شريحة Phase 0 تنجح ستّة منها، والباقي بالضبط ما أثبتَت
إعادةُ التوليد أنّه مشتقّ من الشريحة المحجوبة. فقاعدتها الحقيقيّة `d303d9c6` **زائداً
دلتا الـ٩٢ غير المدموجة**.

**و`overlay` النسخة الثانية كان يُسقِط ثلاثة حرّاس** (`actuation_killswitch_coverage` ·
`branch_protection_contract` · `visual_fixme_baseline`) لأنّ سجلّه مبنيّ على قاعدة أقدم،
**ويحمل سطرَي v228** في `db_ownership.yml`، **و٢٤٤ ملفّاً فقدت بتّ التنفيذ** في التغليف.
أُعيد تأسيسها على `c636b437` وأُصلحت عيوب تكاملها الثمانية وسُلِّمت حزمةً مستقلّة؛
وثلاثة بنود محتوى تنتظر قرار المالك: تصنيف مصنوعاتها الثلاث · ثمانية أسباب مَنع تحتاج
كتابة لا `--generate` · وسقف الجرد ٩٩٨→١٠٠٢.

## `BRAIN-REGISTRY-LOSS-IS-INVISIBLE-TO-A-SIZE-GUARD-01` — `fixed` (‏#827)

**المصدر:** ‏`tests_v9/test_brain_narrative_registry_consistency.py` · مقيس على `d3e09a60`.

الحارس الجديد يقارن معرِّفات الجرد بـ`origin/main`: **مدخلةٌ في جرد main تختفي من الفرع
⇒ حجب**. ويُمسَك ذلك حتّى حين **يكبر** الملفّ — وهو ما لا يقيسه `brain_append_only_guard`
بنصّه المُصرَّح («لا يصغر»، لا «بادئة‑بايت»).

**وحدُّ صدقٍ مقيس لا مُقدَّر:** أوّل صياغة بنت الحارس على ثابتٍ آخر — «معرِّفٌ يرويه
السجلّ يجب أن يوجد في الجرد» — ثمّ أسقط الزرعُ الادّعاء: حُذِفت
`CRLF-PHANTOM-ARTIFACT-DRIFT-01` من الجرد فبقي الفحص **أخضر**، لأنّ مداخل تلك الجلسة
تروي الفجوات **نثراً بلا معرِّفات**. فالفحص النصّيّ يُغطّي صنفاً آخر (فقدٌ يترك أثره
في السجلّ) ولا يُدَّعى له أكثر — والمكتوب في وثيقته صار يقول ذلك صراحةً.

**وإيجابيّة كاذبة كشفتها الشجرة لا التكذيب المُختلَق:** الشرطة حدُّ كلمة في `re`، فـ`\b`
وحدها التقطت **قُصاصة** من معرِّف أطول (`API-VERSIONING-GUARD-IS-A-MIRROR-01` بُلِّغت
ناقصةً). أُضيفت `(?<![A-Z0-9-])`. وتكذيبي الأوّل لم يمسكها لأنّي جرّبتُ نصوصاً
مُختلَقة لا الشجرة.

**وستّة معرِّفات تاريخيّة أُعلِنت أساساً يتقلّص ولا ينمو** — وسومُ PR وأسماءُ شرائح
مُغلَقة من يوليو، لا مداخل ضائعة. إعلانُها دَيناً أصدقُ من توسيع النمط ليتجاهلها:
التوسيع يُخفي الصنف كلّه، والإعلان يُبقيه مرئيّاً ويمنع نموّه. ويحرس الأساسَ فحصٌ
يرفض إبقاء ما صار مُسجَّلاً وما لم يعد يُروى.

## `THE-NEW-GUARD-SKIPPED-ITSELF-IN-CI-01` — `fixed` (‏#828 · مراجعة آليّة أصابت)

**المصدر:** مراجعة Copilot على #828 · ومُتحقَّق منها بقراءة `.github/workflows/ci.yml`
وبمحاكاة استنساخ ضحل.

`test_no_registry_entry_that_main_has_disappears_from_this_branch` يحتاج
`merge-base origin/main HEAD`. ووظيفة *Unit Tests* تستعمل `actions/checkout` **بلا**
`fetch-depth` (الافتراضي `1`) ⇒ المرجع غير قابل للحلّ ⇒ كان الفحص يُنفِّذ `pytest.skip`
**فيمرّ أخضر وهو لم يقس شيئاً**.

```
unit-tests                  fetch-depth غير محدَّد ⇒ 1
platform-unit-tests         غير محدَّد ⇒ 1
weather-service-unit-tests  غير محدَّد ⇒ 1
```

**والعطل هو الصنف الذي كُتِب الحارس ليمنعه، داخل الحارس نفسه.** بنيتُ فحصاً ضدّ «فقدٍ
لا يُرى»، ثمّ جعلتُه **يختفي بصمت** حيث يُفترض أن يعمل. والتخطّي في CI يُقرأ نجاحاً
تماماً كما يُقرأ الصمت.

**والعلاج شقّان، لأنّ أحدهما وحده يكذب:** `fetch-depth: 0` لوظيفة *Unit Tests* كي
يتوفّر التاريخ · و`pytest.fail` برسالة **تسمّي العلاج** بدل `pytest.skip`. لو أضفتُ
العمق وحده لبقي التخطّي جاهزاً لأوّل وظيفة ضحلة قادمة؛ ولو أضفتُ الفشل وحده لَاحمرّ CI
بحقّ. **مُثبَت بالتكذيب:** استنساخ `--depth 1` ⇒ الفحص **يفشل** بالرسالة الصحيحة،
وبالتاريخ الكامل ⇒ يمرّ.

**وملاحظة ثانية صحيحة في المراجعة نفسها:** تمهيد الملفّ كان يقول إنّ القياس مقارنةٌ
بـ`origin/main` مباشرةً بينما التنفيذ يقارن بقاعدة الاشتقاق — **وثيقةٌ تصف غير ما
تقيس**، وهو صنف هذه الجلسة المتكرّر. صُحِّحت الصياغة، وأُضيف فيها سببُ الحاجة إلى تاريخٍ
كامل كي لا يُقرأ الشرط لاحقاً تزيّداً.

**وحدّ يُقال:** الوظيفتان الأخريان (`platform-unit-tests` · `weather-service-unit-tests`)
ما تزالان ضحلتَين. لم تُمَسّا لأنّهما لا تُشغّلان هذا الفحص، والتوسيع بلا حاجة مقيسة
يُبطئ CI بلا مقابل — والحدّ مذكور هنا كي لا يُقرأ صمتُه تغطيةً.

## `JOB-STATUS-HID-A-FAILED-STEP-01` — `fixed` (‏#828 · أبلغ عنه المالك)

**المصدر:** `mcp__github__pull_request_read(get_check_runs)` على #828 مقابل
`actions_list(list_workflow_jobs)` للتشغيل `31507538982` — قياسان متعارضان لنفس الوظيفة.

أعلنتُ «٦٦ من ٦٧ · إخفاقات: ٠» **وكان في المجموعة فشلٌ حاجب.** وظيفة
`capability-registry` تُبلَّغ على مستوى الـcheck-run:

```
status: in_progress · conclusion: null      ← الحالة المُجمَّعة (بائتة)
```

بينما خطواتها **مكتملة** منذ `15:34:31`، وفيها:

```
step[41] Enforce declared PR capability impact   → failure
step[42..48]                                     → skipped (بسببها)
```

**والعطل في القارئ لا في المقروء:** رشّحتُ على `job['status']`/`job['conclusion']`،
فوظيفةٌ حالتها `in_progress` وخلاصتها `null` **لا تُحتسَب فاشلة ولا ناجحة** — تسقط من
العدّ صامتةً. وهو صنف الجلسة نفسه: **قناة القياس كذبت، لا المقيس.** والأسوأ أنّ الصمت
هنا قُرِئ «ما زالت تعمل»، وهي أقنعُ صور الكذب: تُؤجِّل الشكّ بدل أن تُثيره.

**والقاعدة المستخلَصة:** حالةُ الوظيفة المُجمَّعة **ليست** برهاناً؛ البرهان خطواتها.
وكلّ عدٍّ لإخفاقات CI يجب أن يُصنّف `in_progress` **مجهولاً يُفحَص**، لا صفراً يُطوى.

**والسبب الجذريّ للفشل نفسه — إعلانٌ ضاق عن أثره:** الإعلان كان ٢٦ قدرة مشتقّاً عند
`6afbd898`. ثمّ أضاف `6de78d43` تعديلَ `.github/workflows/ci.yml` وملفّ الاختبار
وملفّات الدماغ، **فاتّسع الأثر ولم يتّسع الإعلان** ⇒ `missing_direct: [OPS-004, SOIL-001]`.

صار **٢٩** مشتقّاً من **الأداة الحاجبة نفسها** على `a2cefaac..6de78d43`، لا مُلحَقاً
بالاسمين الحاجبين وحدهما: `SOIL-005` **غير مطلوبة للمرور** (أثر عبوريّ لا مباشر) لكنّها
مقيسة ضمن `affected`، وإغفالها كان يجعل الإعلان أضيق ممّا قِيس — وهو الدَّين نفسه بصورة
أصغر.

```
direct      11   (منها OPS-004 وSOIL-001 اللتان حجبتا)
transitive  18   (منها SOIL-005)
affected    29   ⇒ decision: PASS
```

**وحدّان يُقالان بدل أن يُكتشفا:**

- **تحرير نصّ الـPR وحده لا يُعيد البوّابة.** `capability-governance.yml` يُعلن
  `on: pull_request:` بلا `types` ⇒ الافتراضيّ `[opened, synchronize, reopened]`،
  و`edited` **ليست** منها. وإعادةُ تشغيل الوظيفة لا تُجدي كذلك: تُعيد الحدث بحمولته
  الأصليّة فتقرأ النصّ القديم. المسار الوحيد دَفعةٌ تُولّد `synchronize` — وهذا الالتزام هو هي.
- **ولا حارس يمنع تكرار سوء القراءة.** الإصلاح هنا **إجرائيّ ومُسجَّل**، لا مفروضٌ
  بكود: لا شيء في CI يمنع وكيلاً لاحقاً من عدّ `in_progress` صفراً. تسجيلُه أصدق من
  الادّعاء بأنّه مسدود.

**ولا تعارضَ دمج، خلافاً لِما بدا:** قِيس بـ`git merge-tree --write-tree` ⇒ `rc=0`
وشجرة نظيفة `7800d2b2`، و`merge-base --is-ancestor origin/main HEAD` ⇒ صحيح
(`main` سلفٌ صِرف). و`mergeable_state: "blocked"` سببها **الفحص الحاجب الفاشل** لا
تعارضاً نصّيّاً — واللفظان يُقرآن واحداً في الواجهة.

## `VERIFY-ALL-GENERATED-FIX-GREEN-IS-NOT-A-CHECK-01` — `fixed` (‏#828 · أمسكته §٢)

**المصدر:** `/tmp/regen.log` (‏`--fix`) مقابل `verify_all_generated.py --check` على **نفس
الشجرة النظيفة** بعد الالتزام — قياسان متناقضان لنفس السؤال.

بعد دمج `ad4510db` وحلّ تسعة تعارضات في مصنوعات مولَّدة، شغّلتُ `--fix` فأعلن:

```
— دورة توليد 1/3
  ✓ scripts/ci/capability_mapping_engine.py --check        ← السطر ١٥
✅ كلّ المصنوعات المولَّدة المُكتشَفة متّسقة.   rc=0
```

فالتزمتُ على أساسه. ثمّ قال `--check` على الشجرة **النظيفة** (‏`git status` = ٠):

```
✗ scripts/ci/capability_mapping_engine.py --check
    capability mapping drift; run capability_mapping_engine.py --generate
```

**والفصل بين الاحتمالين كان بالتجربة لا بالترجيح:** «حارسٌ يكتب أثناء الفحص» كان
يُبقي الشجرة متّسخة بعد `--check` — وقد بقيت **نظيفة**. و`--generate` غيّر **٤ ملفّات**
ثمّ مرّ `--check`. إذن الالتزام كان قديماً حقّاً، و`--fix` أعلن اتّساقاً لم يكن.

**ونصف قطر الأثر بوّابتان حاجبتان، لا واحدة:**

```
FAILED tests/architecture/test_capability_mapping_engine.py::test_mapping_has_no_drift
FAILED tests/release/test_phase14_release_packaging_contracts.py::test_release_checksum_validator_passes
```

والثانية **أثرٌ للأولى**: حزمة الإصدار تبصم ما سبقها، فتغيّرُ `CAPABILITY_MAPPING_REPORT.md`
يُنتِج `checksum mismatch`. عطلٌ واحد يظهر بوجهين — ولو قُرِئ الثاني وحده لَبدا مشكلة
حزمة إصدار.

**والقاعدة المستخلَصة — مقيسة لا مُستنتَجة من آليّة داخليّة:** أخضرُ `--fix` **ليس
فحصاً**؛ هو تقريرُ أداةٍ عن نفسها. الفحص هو `--check` **مستقلّاً بعده**. وقد شُغِّل
`--fix` مرّةً ثانية فأبلغ «دورة 1/3» أيضاً، لكنّ `--check` بعده مرّ — أي أنّ **عدّ
الدورات ليس الفارق**، والفارق أنّ التحقّق جاء من خارج الأداة.

**والفرضيّة عن الآليّة تبقى فرضيّة:** الأرجح أنّ خطوةً يمرّ `--check` الخاصّ بها **مبكّراً**
في الدورة تُبطِلها مولّداتٌ تكتب **بعدها** في الدورة نفسها، فيُحسَب الأمر تقارباً. لم
أُثبِت هذا بقراءة الكود، فلا أُقدّمه مقيساً.

**وحدٌّ أقولُه على نفسي:** غيّرتُ الشجرة بـ`--generate` و`preflight` ما تزال تعمل، فأفسدتُ
قياسها — وهو الخطأ الذي وقعتُ فيه سابقاً في هذه الجلسة. لم يُبطِل ذلك النتيجة لأنّ
الفشلين أُعيد إنتاجهما **مستقلّاً** على الشجرة النظيفة، لكنّ الخضرة النهائيّة أُخِذت من
تشغيلٍ نظيفٍ غير مُتداخِل.

## `DELETING-A-JOURNAL-FILE-SILENCED-ITS-OWN-GUARD-01` — `fixed` (‏#828 · مراجعة آليّة أصابت)

**المصدر:** مراجعة Copilot على #828 (سطرا ١٤٧ و١٨٢) · ومُثبَتة بالزرع.

`test_brain_narrative_registry_consistency.py` كان يتخطّى ملفّ رواية غير موجود
(`if not path.is_file(): continue` و`if path.is_file():`). فـ**حذفُ** `log.md` كان
يُمرّر الفحص أخضر بلا قياس — أي أنّ **أرخص طريقة لإسكات الحارس تصير حذفَ ما يقيسه**.

**والأسوأ أنّ تمهيد الملفّ كان يدّعي العكس حرفيّاً:**

```
يفشل مغلقاً: ملفّ دماغٍ لا يُقرأ يُبلَّغ فشلاً، لا يُتخطّى.
```

و`_read` **كان** يفشل مغلقاً فعلاً (‏`read_text` يرفع `FileNotFoundError` وهو `OSError`)
— لكنّ حارسَي الوجود يقطعان الطريق إليه. فالادّعاء صحيح والتنفيذ يلتفّ حوله: **وثيقةٌ
تصف غير ما تقيس**، وهو ثالث تكرار لهذا الصنف في هذا الملفّ وحده.

**والعلاج حذفُ الحارسَين لا إضافةُ فحص:** الفشل المغلق كان موجوداً، والزائد هو ما عطّله.

**مُثبَت بالتكذيب:** نُقِل `sahool-brain/log.md` مؤقّتاً ⇒

```
FAILED ::test_every_gap_id_the_journal_narrates_exists_in_the_registry
FAILED ::test_the_baseline_only_shrinks_and_names_nothing_the_registry_already_has
2 failed, 3 passed
```

وبإعادته ⇒ `5 passed`. والاختباران الحمراوان هما بعينهما اللذان سمّتهما المراجعة.

**وحدٌّ يُقال:** هذا يحمي من **حذف** ملفّ رواية، لا من **تفريغه**. ملفّ موجود فارغ
يُقرأ بنجاح ويُنتِج مجموعة معرِّفات خالية — فيمرّ. لم أُضِف فحص «غير فارغ» لأنّي لم
أقِس حادثةً من هذا الصنف، وحارسٌ بلا عطلٍ مقيس يُضخّم العدد ولا يُضيف تغطية.

### تحديث `KNOWLEDGE-CANONICAL-CONSUMPTION-01` (2026-08-11) — البند يبقى `fixed`، ومعه الآن حارسٌ يمنع عودته

الإصلاح الأصليّ (`ad4510db`) أثبت بالتشغيل أنّ السلسلة تعمل، لكنّه ترك بابين لا يقيسهما شيء:
**لا مانعَ من أن يكتب مُستهلِكٌ قادم `safe_depth = raw_mm * 0.8` حين يجد الحقل غائباً**، ولا
شيء يجعل تلك التبعيّة **مُعلَنةً** أصلاً. وحدُّ الصدق المُسجَّل حينها — أنّ الحرّاس الثلاثة غير
مُواصَفين بطفرات لأنّ لا اختبار يُشغّلها — بقي قائماً على حاله.

أُضيفت طبقةُ `shared/knowledge/`: سجلٌّ محكَّم لمصادر الحقيقة (`decided`) · عقدُ سياق مهمّةٍ
يُعلِن ما تحتاجه توصيةُ الريّ · مُحلِّلٌ يُحجب ولا يُسلِّم `None` صامتاً · وغلافُ نَسَبٍ موحَّد.
ويفرضها `canonical_consumer_bypass_guard.py` — **٧/٧ طفرة مُكذَّبة**، وهو أوّل حارسٍ في هذا
المسار يحمل مواصفةً أصلاً.

**وحدّ صدقٍ جديد يحلّ محلّ السابق:** لا التفافَ قائماً في الشجرة اليوم؛ المستهلكون الأربعة
المُسجَّلون يقرؤون الحقول القانونيّة وقد فُحِصوا قبل التسجيل. فهذا الحارس يمنع **انحداراً**
ولا يُصلِح عطلاً حاضراً. والسجلّ مقصورٌ على مفتاحين — `field.geometry` و`weather.et0` واردان
في المقترح ولم يُسجَّلا لأنّ تسجيلهما بلا مستهلكٍ مربوطٍ ومقيس زينةٌ لا حارس.
## `FAILURE-MESSAGE-ASSERTED-A-CAUSE-IT-NEVER-MEASURED-01` — `fixed` (مراجعة آليّة على #828)

**المصدر:** مراجعة Copilot (سطرا ١٢٦ و١٣٢) · ومُثبَتة بزرعين.

رسالتا الفشل في `test_brain_narrative_registry_consistency.py` كانتا **تجزمان بسبب**:
«استنساخ ضحل على الأرجح» و«كائن مفقود من الاستنساخ» — و`_registry_ids_at` تُعيد `None`
وحدها فتبتلع `stderr`. أي أنّ **تشخيص git كان يُرمى ويُستبدل بترجيحي**.

**والزرعان أثبتا أنّ الترجيح كان خاطئاً في الحالتين:**

```
زرع ١ (استنساخ --depth 1):
  fatal: Not a valid object name origin/main        ← مرجعٌ غير موجود، لا عمق

زرع ٢ (قاعدة تُحَلّ لكنّ المسار غائب عندها):
  fatal: path 'sahool-brain/gaps/registry.md' exists on disk,
         but not in '4b825dc…'                      ← لا «كائن مفقود من الاستنساخ»
```

في الحالتين العلاجُ المُرجَّح (`fetch-depth: 0`) **مجاورٌ للحقيقة لا مطابقٌ لها**، وقارئٌ
يتبعه حرفيّاً قد يُطارد عمقاً بينما العطل مرجعٌ أو مسار.

**والعلاج بنيويّ لا لفظيّ:** أُضيف `_git` و`_diagnosis`، و`_registry_ids_at` صارت تُعيد
`(ids, proc)` — فتُطبَع مخرجات git حرفيّاً **قبل** الترجيح، ويبقى العلاج الأشيع مذكوراً
بوصفه ترجيحاً لا تشخيصاً.

**والصنف هو صنف هذه الجلسة كلّها بصورته الأصغر:** ادّعاءٌ يتجاوز ما قِيس. وقد وقع في
رسالةِ حارسٍ كُتِب ضدّ هذا الصنف بعينه — وهي الآن **رابع** مرّة يُصاب فيها هذا الملفّ
بالعطل الذي وُجِد ليمنعه.

## `REGENERATED-FROM-AN-UNRESOLVED-INDEX-01` — `fixed` (‏#831 · مراجعة آليّة أصابت)

**المصدر:** مراجعة Copilot على `release/FILE_CHECKSUMS.sha256:557,582` · ومُثبَتة بالمحاكاة.

شغّلتُ `verify_all_generated --fix` **قبل** `git add`، أي والفهرس يحمل أربعة مسارات
**غير مدموجة**. والمولّدات تُعدِّد بـ`git ls-files`:

```
scripts/release/build_release_bundle.py:181      ["git","ls-files","-z"]
scripts/ci/capability_mapping_engine.py:270      ["git","ls-files","-z"]
```

و`git ls-files` على مسارٍ غير مدموج يُخرِج **ثلاثة صفوف** — مراحل الدمج
(‏`1` base · `2` ours · `3` theirs). مُثبَت بمحاكاة مستقلّة على مستودع خام.

**فصار كلّ مسار إدخالٍ متعارض يُعَدّ ثلاثاً:**

```
مساران × ٣ صفوف   ⇒  +٤ صفوف زائدة في FILE_CHECKSUMS.sha256
                      +٤ في file_count      (5425 بدل 5421)
                      +٤ في files_scanned   (4975 بدل 4971)
```

**والأخطر أنّ `--check` مرّ.** سجّلتُ صباحاً قاعدة «`--check` مستقلّاً بعد `--fix`»
(‏`VERIFY-ALL-GENERATED-FIX-GREEN-IS-NOT-A-CHECK-01`) وطبّقتُها هنا حرفيّاً ⇒ `rc=0`.
**واستقلالُ الفحص لا يكفي حين يتشارك الطرفان المُدخَل الفاسد:** كلاهما قرأ الفهرس
ثلاثيَّ المراحل فاتّفقا على رقمٍ خاطئ. اتّفاقُ قياسين لا يعني الصحّة إن كان مصدرهما واحداً.

**والقاعدة المُصحَّحة:** لا توليد إلّا من **فهرسٍ محلول** — `git add` للتعارضات **قبل**
إعادة التوليد، عكس الترتيب المُسجَّل في §٢ لحالة `--fix` العاديّة. والترتيبان لا يتعارضان:
§٢ تمنع تثبيت مصنوعٍ بائت، وهذا يمنع توليده من فهرسٍ مزدوج — والجامع أنّ **التوليد يقرأ
الفهرس، فحالة الفهرس شرطٌ في صحّة المُخرَج**.

**وتشخيصي الأوّل كان خاطئاً:** رجّحتُ «ملفّات مؤقّتة من تشغيلٍ متوازٍ» لأنّ §٢ كانت تعمل،
وهو ترجيحٌ معقول أسقطه القياس — المكرّران هما **بعينهما** ملفّا الإدخال المتعارضان، لا
ملفّات عشوائيّة.

**وحدٌّ يُقال:** لا حارس يمنع التوليد من فهرسٍ غير محلول. الإصلاح إجرائيّ ومُسجَّل.
</details>

## `S5-EXEC-01` — `fixed` (`ee4fdff7` · دلتا واردة مُراجَعة)

**المصدر:** `services/decision-service/persistence.py` · مفروض بـ
`services/decision-service/tests/test_s5_exec_01_decision_record_immutable.py`
و`tests_v9/test_s5_exec_01_edge_freeze.py` · مقيس على `010c9627+delta`.

**الفجوة.** رأس سلسلة القرار وحلقتاها الدنيا (`decision_record` · `outcome_record` ·
`recommendation_outcomes`) كانت تُكتَب بـ`ON CONFLICT … DO UPDATE SET` مع
`content_digest = COALESCE(EXCLUDED.content_digest, …)`. أي أنّ **سجلّ القرار قابل
لإعادة الكتابة بعد إصداره**: مفتاح تعاملٍ مُعاد بمحتوًى مختلف يُبدّل الصفّ صامتاً بدل
أن يُرفَض — فالسجلّ الذي يُفترَض أن يكون شاهداً يصير قابلاً للتحرير، ويضيع تمييز
«إعادة إرسال» عن «تغيير أثر رجعيّ».

**الإغلاق.** الكتابات الثلاث صارت إلحاقاً غير قابل للتغيير: `ON CONFLICT … DO NOTHING`
زائداً **كشف إعادة صريح** (`SELECT` عند التعارض، ورفض fail-closed إن أُعيد مفتاح
التعامل بمحتوًى مختلف التجزئة). و`dispatch_decisions` وحده أُبقي على نمط الدمج القابل
للتحديث — وهو مقصود ومُوثَّق في `tests_v9/test_content_digest_lineage_column_v167.py`،
لأنّه صفّ إرسالٍ يُحدَّث بحالته لا شاهدُ قرار.

**حدّ صدق مقيس:** هذا تصليبُ كتابةٍ ساكن مفروض بقراءة المصدر؛ **لا يُرقّي أيّ سلطة**
ولا يُثبِت السلوك على Postgres حيّ. الإثبات الحيّ يبقى دَيناً على أدلّة
`decision_sor_live_closure_collector.py` — والسلطات لم تتغيّر: القرار
`CUTOVER_CAPABLE/INTERIM` · الحقل `BLOCKED` · الرسم المعرفيّ `SERVICE_OWNED`.

## OFFLINE-CURSOR-BOUND-TO-A-NAIVE-TIMESTAMP-01 — `open` (P2 · دَينٌ مُعلَن ومحروس · 2026-08-19)

- **العلّة:** `core/offline_first.py` يُنتِج `created_at` بالساعة المُهمَلة — نصٌّ **بلا منطقة**. و[`api/sync_delta.py`](../../services/sahool-platform/api/sync_delta.py) يُصرّح في تعليقه أنّ مقارنة الـcursor **نصّيّة معجميّة** وأنّها مبنيّة على هذا الشكل بعينه.
- **لِمَ لم تُغلَق مع شريحة التنظيف:** تحويلُ المُنتِج وحده يُدخِل لاحقة `+00:00`، فتصير القيمة القديمة والجديدة مختلفتَي الطول عند **اللحظة نفسها**: النصّ الأقصر يسبق الأطول معجميّاً. فينشأ حدُّ ترتيبٍ مختلط يُدخِل عمليّةً مكرّرة أو يُسقِط أخرى عند الحدّ تماماً. وإن حُوِّل الطرفان إلى كائناتٍ زمنيّة بدل المقارنة النصّيّة، فمقارنةُ واعيةٍ بساذجة ترفع `TypeError`.
- **صنفه:** ليس إهمالاً لغويّاً بل **عقدَ بيانات**: إغلاقه يحتاج حسم دلالة الـcursor (تطبيعٌ عند الاستقبال · أو ترحيل القيم المخزّنة · أو مقارنةٌ زمنيّة لا معجميّة)، لا إعادة تسمية دالّة.
- **وهو محروسٌ لا متروك:** [`tests_v9/test_deprecated_utc_clock_cleanup.py`](../../tests_v9/test_deprecated_utc_clock_cleanup.py) يحصر الساعة المُهمَلة في ملفَّي العنقود صراحةً، ويحجب أيّ استعمالٍ جديد خارجهما، **ويرفض** بقاء مدخلٍ في الدَّين بلا استدعاءٍ فعليّ — فلا يتحوّل إلى إعفاءٍ دائم. ويحمرّ أيضاً إن زال العقد المعجميّ من `sync_delta.py`، فيُعاد تقييم التأجيل بدل أن يُنسى.
- **المصدر:** قياس مباشر 2026-08-19 أثناء شريحة تنظيف الساعة المُهمَلة على `707ef54e`.

## DEPRECATED-UTC-CLOCK-01 — CLOSED (2026-08-19) — ومعه عطلٌ لم يكن إهمالاً

- **العلّة المُعلَنة:** `datetime.utcnow()` مُهمَلة منذ Python 3.12 لأنّها تُرجِع لحظةً **بلا منطقة**: نصٌّ يقول UTC ونوعٌ لا يقوله. فمقارنتُها بلحظةٍ واعية ترفع `TypeError`، وتخزينُها في `timestamptz` يُفسَّر بتوقيت الخادم.
- **وما كشفه القياس أنّ التحويل ليس مسحاً ميكانيكيّاً:**
  - **موضعٌ كان عطلاً حقيقيّاً لا إهمالاً:** `services/ai_agronomist/guardrail_events.py` حمل الساعة **قيمةً افتراضيّة لحقل dataclass**، فقُيِّمت مرّةً واحدة عند تنفيذ جسد الصنف — أي عند الاستيراد. مقيسٌ بالتشغيل: حدثان أُنشئا بفارق 1.1 ثانية حملا الطابع ذاته حرفيّاً. وحقلٌ اسمه `timestamp` في مسارٍ تدقيقيّ يُقرأ لحظةَ وقوع، فكان ترتيبُ الأحداث كلّه غير قابلٍ للاستخراج بلا أن يُحمِرّ شيء.
  - **وموضعٌ كان تحويلُه سيُغيّر عقداً سلكيّاً بصمت:** `shared/memory/models.py` حمل `json_encoders` المُهمَلة. وإسقاطُها **ليس محايداً**: التسلسل المدمج في Pydantic v2 يُخرِج لاحقة `Z` بينما `.isoformat()` تُخرِج `+00:00`، و`farm_memory.py` يُدِيم هذه النماذج بـ`model_dump(mode="json")` — فالإزالة الساذجة كانت ستُعيد كتابة شكل كلّ مخزنٍ على القرص وتترك ملفّاتٍ مختلطة الشكل. `PlainSerializer` قِيس **مطابقاً بايتاً** في الوضعين، والتحذيرات الأربعة صارت صفراً.
  - **وأربعة مواضع قِيست آمنة قبل لمسها:** الحقبة في توقيع JWT مطابقة بفارق صفر ثانية · `.date()` بلا تسلسل · حقل النَّسَب في الموصّلات بلا مستهلكٍ نصّيّ · وحقل `generated_at` في تقرير العمليّات كان **الشاذّ** بين أربعة راوترات شقيقة تستعمل الصيغة الواعية سلفاً، فتحويلُه توحيدٌ لا انحراف.
- **ما بقي مفتوحاً بصدق:** عنقود `offline_first` — مُسجَّلٌ ومحروس في `OFFLINE-CURSOR-BOUND-TO-A-NAIVE-TIMESTAMP-01` أعلاه.
- **الحارس:** [`tests_v9/test_deprecated_utc_clock_cleanup.py`](../../tests_v9/test_deprecated_utc_clock_cleanup.py) — خمسة عقود، كلٌّ مُكذَّبٌ بزرع: عودة الطابع المُجمَّد · إسقاط المُسلسِل · عودة الساعة المُهمَلة خارج الدَّين · مدخل دَينٍ بائت. والفحص بـ`ast` لا بـ`grep`، فذِكرُ الاسم في تعليقٍ يشرح العطل توثيقٌ لا ارتكاب.
- **المصدر:** قياس مباشر 2026-08-19 على `707ef54e`.

## UNIT-TEST-DORMANCY-BY-DEPENDENCY-LAYER-01 — `mitigated` (السبات الحرّ أُوقِظ) · `open` (الصنف مُعلَنٌ ومحروس) — 2026-08-20

- **العلّة:** الآليّة **الثالثة** لسبات اختبارات الوحدة. ليست العلامة (`TESTS-UNMARKED-DESELECTED-01`) ولا مسار الجمع (`RASTER-SERVICE-TESTS-UNWIRED-TO-CI-01`)، بل **طبقة التبعيّات**: ملفٌّ مُعلَّم `unit` ومجموعٌ فعلاً، لكنّ `pytest.importorskip("X")` في رأسه يُخرِجه من التنفيذ لأنّ `X` غير مثبَّتة في الوظيفة التي تجمعه.
- **ولمَ هي أخبثُ من أختيها:** مُخرَجها `skipped` لا `deselected` — سطرٌ في ذيل التقرير بين آلاف النقاط الخضراء، لا رقمٌ ناقص يلفت النظر.
- **الحالة المؤسِّسة المقيسة:** [`tests_v9/test_prescription_shapefile.py`](../../tests_v9/test_prescription_shapefile.py) مُعلَّم `unit` ويصف نفسه «نقيّاً بلا خدمات/شبكة»، ويتخطّى على `shapefile`. و`pyshp` مُعلَنة في `api/requirements.txt` تُثبّتها *Platform Unit Tests* وحدها — وهي تُشغّل `services/sahool-platform/tests` أي **دليلاً آخر** لا `tests_v9/`. فالوظيفة المالكة للحزمة لا تجمع الملفّ، والجامعة له لا تملكها ⇒ **سبعةُ اختباراتٍ على مُصدِّر وصفة VRA لم تُنفَّذ في CI قطّ**.
- **وكلفة الإيقاظ كانت صفراً:** عجلةٌ نقيّة-Python بـ٤٦ كيلوبايت بلا تبعيّات. لم يكن السبات قراراً بل سطراً ناقصاً — وهذا بعينه ما يجعل الصنف خطراً: لا أحد وازن كلفةً، لأنّ لا أحد رأى السؤال.
- **وما بقي `open` بصدق:** ستُّ وحداتٍ أخرى خامدة بقرارِ كلفةٍ حقيقيّ (`rasterio` · `shapely` · `sklearn` · `pyarrow` · `aiomqtt` · `edge_tts`) وسابعةٌ داخليّة. لم أُدخِلها إلى طبقة الوحدة من تلقائي — عجلاتُ GDAL/GEOS وscikit-learn قرارُ كلفةٍ لا تنظيف. صارت **مُعلَنةً بكلفةٍ مكتوبة** بدل أن تكون خمولاً غير مرئيّ.
- **الحارس:** [`tests_v9/test_unit_dependency_dormancy_guard.py`](../../tests_v9/test_unit_dependency_dormancy_guard.py) يقيس القابليّة بـ`find_spec` **داخل الوظيفة نفسها** لا بجدولٍ يصفها (الجدول يبيت؛ والقياس النصّيّ على `requirements-test.txt` أدان `cryptography` خطأً لأنّها تصل عبوريّاً مع `python-jose[cryptography]`). ويحجب أيّ تخطٍّ جديد غير مُعلَن، ويرفض بقاء مدخلٍ بائت في الجرد.
- **مُكذَّب ثلاثاً:** نزعُ وحدةٍ غائبة من الجرد يُحمِرّ · مدخلٌ لا يتخطّاه أحد يُحمِرّ · إعلانُ `shapefile` خامدةً (تنكُّراً لعودة العطل) يُحمِرّ.
- **المصدر:** قياس مباشر 2026-08-20 على `f0c45340`.

## CLASSIFIER-BLIND-TO-GENERATORS-OUTSIDE-generated-DIRS-01 — `fixed` (البقعة أُغلِقت بالمقيس) · `open` (الاشتقاق العامّ غير آمن) — 2026-08-20

- **العلّة:** [`scripts/ci/resolve_merge_conflicts.py`](../../scripts/ci/resolve_merge_conflicts.py) يُصنّف الملفّ المتعارض بـ**قائمة علاماتٍ في المسار** (`/generated/` · `.sha256` · …). فمصنوعةٌ تُعيد المكنسةُ توليدها ولا يحمل مسارُها علامةً تُقرأ **مصدراً**، فتقف الأداةُ طالبةً إنساناً.
- **مقيس على دمج #876:** ثلاثةٌ تحت `docs/architecture/` (`fake_connection_debt.json` · `source_text_assertion_inventory.json` · `tenant_guc_scope_baseline.json`) وقعت في ذلك — واثنان منها **مُسجَّلان صراحةً** بـ`--generate` في `verify_all_generated.py`. والوقوف نفسه سلوكٌ صحيح (فشلٌ مغلق لا تخمين)، لكنّه كان عن سؤالٍ للمكنسة فيه جواب.
- **ولمَ لم يُغلَق باشتقاقٍ عامّ — وهذا أهمّ ما في البند:** جُرِّب الاشتقاق «أيّ مسار يُذكَر في مُولِّدٍ مُعلَم» فأعطى **١٩** مساراً، ومنها [`guard_mutation_registry.json`](../../docs/architecture/guard_mutation_registry.json) — وثيقةُ سياسةٍ **بخطّ اليد** يقرؤها `capability_mapping_engine.py` ولا يكتبها. وتصنيفُها «مولَّدة» يعني أخذَ جانب main ثمّ إعادة التوليد، أي **إتلاف طفراتٍ مكتوبة بصمت**. و`platform_extraction_map.json` مثلها. **الذِّكرُ ليس كتابةً**، والاشتقاق على أساسه كان سيُنتِج عطلاً أسوأ من الوقوف.
- **فالعلاج بالمقيس وحده:** وُسِّعت العلامات بالثلاثة **المرصودة فعلاً**، وأُضيف حدّان يفرضان بقاء التوسيع صادقاً: `GENERATED_OWNERS` يربط المصنوعة بمُولِّدها ويفرض بقاءه مُسجَّلاً في المكنسة، و`HAND_WRITTEN_POLICY` يفرض بقاء وثائق السياسة `source` مهما اتّسعت العلامات.
- **البرهان أنّ البقعة أُغلِقت:** الأداة حلّت **الستّة عشر** تعارضاً آليّاً بعد الإصلاح، بعد أن كانت تقف على ثلاثة.
- **مُكذَّب ثلاثاً:** نزعُ مصنوعةٍ من العلامات يُحمِرّ · تصنيفُ سجلّ الطفرات مولَّداً يُحمِرّ · زوالُ تسجيل المُولِّد من المكنسة يُحمِرّ.
- **حدّ صدق:** الصنف يبقى `open` لأنّ العلاج **توسيعٌ مقيس لا اشتقاق**. مصنوعةٌ جديدة خارج أدلّة `generated/` ستُقرأ مصدراً وتُوقِف الأداة مرّةً أخرى — وهو أفضل الأخطاء المتاحة (وقوفٌ لا إتلاف)، لكنّه ليس إغلاقاً للصنف.
- **المصدر:** قياس مباشر 2026-08-20 أثناء دمج `f9feb14e` في الفرع.


## MARKER-GUARD-COUNTS-FILES-WHILE-THE-DEFECT-LIVES-IN-A-FUNCTION-01 — `fixed` (2026-08-20)

- **العلّة:** `test_marker_coverage_guard.py` يسأل «أفي هذا الملفّ علامة **مُسجَّلة**؟» — فيمرّ الملفّ إن حملت **دالّةٌ واحدة** علامةً، ولو كانت أخواتها عارية. والعطل يعيش في الدالّة لا في الملفّ.
- **المقيس على `258a5835`:** [`tests_v9/test_decision_governance.py`](../../tests_v9/test_decision_governance.py) — خمس دوالّ `unit` وسادسةٌ عارية: `test_approved_guardrails_alone_not_executable_by_default`، وهو **اختبارُ حوكمةٍ على قابليّة تنفيذ القرار** (`DECISION-CENTER-UNIFY-01`: بلا علم التجاوز لا يصير القرار قابلاً للتنفيذ). مُستبعَدٌ من كلّ وظيفة، والحارس يقول عن ملفّه PASS.
- **العلاج:** `unmarked_tests()` تقيس على مستوى الدالّة (وترث علامةَ الصنف)، وتتخطّى الملفّات المُعلَنة في الأساس كي لا يُضاعَف الدَّين الواحد. والاختبار اليتيم وُسِم فصار يعمل: `-m unit` ⇒ 6/6.
- **مُكذَّب:** نزعُ العلامة يُخرِج الحارس بـ`rc=1` باسم الاختبار، وإعادتُها تُعيده إلى `rc=0`.
- **المصدر:** قياس مباشر 2026-08-20 أثناء العمل على `TESTS-UNMARKED-DESELECTED-01`.

### تصحيحُ قياسٍ خاطئ منّي على `TEST-NAMED-FILES-THAT-ARE-NOT-TESTS-01` (2026-08-20)

- **قلتُ إنّ الصنف «نما من ٢ إلى ٤» — وهو خطأ.** خلطتُ ثلاث آليّات مختلفة في عدّادٍ واحد: سكربتان بصفر جمع (الصنف الحقيقيّ)، وملفٌّ يتخطّى على مستوى الوحدة لأنّه **تكامليٌّ بالتصميم** (`test_h51_field_source_binding_pg.py` ⇒ `-m integration`)، ورابعٌ كان يتخطّى لأنّ `pyshp` غير مثبَّتة **في بيئتي المحلّيّة** بعد رجوع حاوية — لا في CI.
- **المقيس بعد تثبيت `requirements-test.txt`:** 737 ملفّاً · **٣** بصفر جمع = سكربتان + تكامليٌّ واحد. أي أنّ الصنف **ثابتٌ عند ٢ كما سُجِّل**، ولم ينمُ.
- **الدرس:** «صفرُ جمع» ليس صنفاً واحداً. عدٌّ يجمع آليّاتٍ مختلفة تحت رقمٍ واحد يُنتِج إنذاراً كاذباً بحجم ١٠٠٪ — وهو ما فعلتُه.


## SEC-QDRANT-AUTH-FAIL-CLOSED-01 — `fixed` (P0 أمنيّة، 2026-08-20)

- **المصدر:** `docker-compose.unified.yml:409` — كانت `QDRANT__SERVICE__API_KEY: "${QDRANT_API_KEY}"`. و`.env.example:272` يشحن `QDRANT_API_KEY=` فارغاً (وهو الصواب لملفّ مثال). فمن نسخ المثال وأقلع المكدّس الموحَّد حصل على Qdrant **بلا مصادقة**.
- **الخاصّيّة المنتهَكة:** خادمٌ تعتمد حمايتُه على سرٍّ أقلع والسرُّ فارغ. ومفتاحٌ فارغ يُعامَل كغير مضبوط، فتقبل الخدمة كلّ طلب.
- **حدُّ الأثر — وتصحيحُ لفظٍ لي:** قلتُ «مكشوف» وهو **خطأ**. المنفذ مربوطٌ بـ`127.0.0.1:6333`، فالخطر «خدمةٌ محلّيّة بلا مصادقة» لا «مكشوفةٌ للعالم». يبقى عيباً حقيقيّاً: حدُّ الثقة يتّسع لكلّ عمليّةٍ أو مستخدمٍ محلّيّ، ولأيّ مسار وكيلٍ يُضاف لاحقاً.
- **الانحراف المقيس:** ثلاثةٌ من أربعة مواضع تُرضي الخاصّيّة — `fixed.yml:248` و`v9.yml:405` بـ`:?`، و`test.yml:33` بقيمةٍ حرفيّة تُقلِع بالاستيثاق **مُفعَّلاً**. و`unified.yml` وحدها شذّت.
- **جدولُ الصيغ — مقيسٌ بـ`docker compose config` (v5.1.1) لا مأخوذٌ من وثيقة:**

  | الصيغة | غير مضبوط | **مضبوط فارغاً** | بقيمة |
  | --- | --- | --- | --- |
  | `${V:?e}` | rc=1 | **rc=1** | يمرّ |
  | `${V?e}` | rc=1 | **يمرّ خالياً** | يمرّ |
  | `${V}` | خالٍ | **خالٍ** | يمرّ |
  | `${V-d}` | `d` | **خالٍ** | يمرّ |

  العمودُ الأوسط هو العقد كلُّه: `:?` وحدها تحجب البابين، و`?` بلا نقطتين فخٌّ يبدو علاجاً.
- **العلاج:** `unified.yml` ⇒ `${QDRANT_API_KEY:?QDRANT_API_KEY required}`. والخدمة **ليست خلف profile** (مقيس) — فالقيدُ الذي فرض `:-` الفارغة في مواضع أخرى (الاستيفاء يسبق ترشيح الـprofiles) لا ينطبق.
- **الحارس — وعقدُه منفصلٌ عمداً:** `scripts/ci/compose_auth_sink_guard.py` يفرض `SERVER-AUTH-SECRET-MUST-BE-NONEMPTY-01`، لا توسعةً لـ`COMPOSE-DEFAULT-SECRET-IS-A-PUBLISHED-SECRET-01`. **ولا نمط `.*API_KEY`:** بعض متغيّرات المفاتيح اعتمادُ عميلٍ اختياريّ لا مفتاحٌ يحمي خادماً، وإلزامُها عالميّاً يكسر مكدّساتٍ تعمل بلا مزوّدٍ خارجيّ بحقّ — فالنطاق سجلٌّ صريح (`docs/architecture/compose_auth_sinks.json`) بمصرفٍ **مقيسٍ** واحد. والمقيسُ خاصّيّةٌ لا صيغة: أقلُّ ما تؤول إليه القيمة.
- **البقعة العمياء التي كشفت هذا:** `compose_no_default_secrets_guard` يقول PASS على `"${QDRANT_API_KEY}"` — استيفاءٌ صحيحٌ بلا افتراضيّ، فلا يقع في فئتَيه. مثالٌ حيّ على `GUARD-PINS-IMPLEMENTATION-NOT-PROPERTY-01`.
- **مُكذَّب:** ثلاث طفرات مُسجَّلة تعمل بـ`--run`. أبرزُها معاملةُ `?` كـ`:?` — تُحمِّر اختبار الاشتقاق.
- **حدُّ صدق — ما لم يُقَس:** **لم تُقلَع Qdrant ولم يُسبَر منفذُها**. المقيس هو دلالةُ الاستيفاء وانحرافُ المكدّسات. وأنّ Qdrant تُعطّل الاستيثاق عند مفتاحٍ فارغ هو سلوكُها الموثَّق، لا نتيجةَ سبرٍ حيّ في هذه الجلسة. وادّعاءُ «مقفلٌ حيّاً» يحتاج إقلاعاً وطلباً بلا مفتاح يُرَدّ بـ401.
- **شرط الإغلاق النهائيّ:** سبرٌ حيّ يُثبِت الرفض، أو قبولُ المالك للحدّ المُعلَن أعلاه.


## SERVER-AUTH-SECRET-MUST-BE-NONEMPTY-01 — ⛔ عقدُ حراسةٍ لا فجوة تنفيذيّة (2026-08-20)

- **ما هو:** اسمُ **عقد** يفرضه `scripts/ci/compose_auth_sink_guard.py`، لا عطلٌ مفتوح. سُجِّل هنا لأنّ شكله شكلُ مُعرِّف فجوة، فذكرُه في رسالة التزامٍ يقرؤه `brain_commit_claim_guard` ادّعاءَ وجود — والسجلّ فيه سابقةٌ لمداخل تقول عن نفسها إنّها ليست فجوة (`GUC-NAME-MISMATCH-CLAIM-REFUTED-01`).
- **المصدر:** `docs/architecture/compose_auth_sinks.json` (`contract`) · `scripts/ci/compose_auth_sink_guard.py` · `tests_v9/test_compose_auth_sink_guard.py`.
- **الخاصّيّة:** خادمٌ تعتمد حمايتُه على سرٍّ لا يجوز أن يُقلِع والسرُّ فارغ.
- **وما ليست:** «لا سرَّ افتراضيّ منشور» (`COMPOSE-DEFAULT-SECRET-IS-A-PUBLISHED-SECRET-01`). القيمةُ الحرفيّة `test_qdrant_key` تُدان هناك وتمرّ هنا بحقّ — والفصلُ مقصود: عقدٌ داخل عقدٍ يُخفي أحدهما.
- **النطاق:** سجلُّ مصارفَ صريحٌ بالاسم، لا نمط `.*API_KEY`. التوسيع بمصرفٍ **مقيسٍ** واحدٍ في المرّة.
- **العطل الأوّل الذي أوجده:** `SEC-QDRANT-AUTH-FAIL-CLOSED-01` أعلاه.


## COMPOSE-DEFAULT-SECRET-IS-A-PUBLISHED-SECRET-01 — ⛔ عقدُ حراسةٍ لا فجوة تنفيذيّة (2026-08-20)

- **ما هو:** اسمُ **عقد** يفرضه `scripts/ci/compose_no_default_secrets_guard.py` (هبط في #878)، لا عطلٌ مفتوح. سُجِّل لنفس سبب شقيقه أعلاه: شكلُه شكلُ مُعرِّف فجوة.
- **المصدر:** `scripts/ci/compose_no_default_secrets_guard.py` · `docs/architecture/compose_secret_exceptions.json` · `tests_v9/test_compose_no_default_secrets_guard.py`.
- **الخاصّيّة:** لا قيمةَ سرٍّ افتراضيّة ولا حرفيّة في Compose — `${APP_DB_PASSWORD:-sahool_app_pw}` كلمةُ مرورٍ **منشورة** يعرفها كلّ من قرأ المستودع.
- **الشكلان المقبولان — ولمَ اثنان:** `${VAR:?…}` لخدمةٍ دائمة، و`${VAR:-}` **فارغاً** لخدمةٍ خلف profile. القياسُ الذي فرض الثاني: الاستيفاء يسبق ترشيح الـprofiles، فـ`:?` على خدمةٍ مُرشَّحة تكسر `docker compose config` للمكدّس الافتراضيّ.
- **وما ليست:** «لا يُقلِع بسرٍّ فارغ» (`SERVER-AUTH-SECRET-MUST-BE-NONEMPTY-01`). و`${VAR:-}` الفارغة تُرضي هذا العقد وتنتهك ذاك — وهو بالضبط ما يجعلهما عقدين.


## QDRANT-AUTH-EMPTY-SECRET-FAIL-OPEN-01 — لقبٌ لا مدخلٌ ثانٍ (2026-08-20)

- **المصدر:** تحكيمُ المالك 2026-08-20 — سمّى الشريحة في عنوانه `SEC-QDRANT-AUTH-FAIL-CLOSED-01` وسمّاها في قسم «سجل الفجوات» `QDRANT-AUTH-EMPTY-SECRET-FAIL-OPEN-01`.
- **الحالة:** لقبٌ (alias) للهويّة القانونيّة `SEC-QDRANT-AUTH-FAIL-CLOSED-01`. **لا فجوة ثانية ولا حالةٌ مستقلّة.**
- **ولمَ لقبٌ لا إعادةُ تسمية:** نفس القاعدة التي أقرّها المالك لدَين التأكيدات — لا تُكتَب المراجع التاريخيّة فوقاً، ولا يُنشَأ مُعرِّفان لدَينٍ واحد بلا جرد مُشيرين. الهويّة القانونيّة هي المُلتزَمة في `compose_auth_sinks.json` (`sinks.*.gap`) وفي رسالة الالتزام.
- **الاسمان يصفان الحالتين لا شيئين:** `…FAIL-OPEN-01` يصف الحال **قبل** الإصلاح (فتحٌ صامت)، و`SEC-QDRANT-AUTH-FAIL-CLOSED-01` يصف العقد **بعده**. وهذا سببُ اختلافهما، لا انقسامُ الفجوة.


## BRAIN-REGISTRY-TRUTH-01 — مفتوحة (مؤجَّلةٌ بقرار المالك، 2026-08-20)

- **المصدر:** تحكيمُ المالك 2026-08-20 على تقرير حالة الفجوات · `sahool-brain/gaps/registry.md` · `docs/architecture/assertion_presence_baseline.json`.
- **العلّة (ثلاثُ شُعَب، مقيسةٌ بدرجاتٍ متفاوتة من الوثوق):**
  - **(أ) انحرافُ نصٍّ مؤكَّد:** الأساس المُجمَّد يقول `count: 206` منذ `ab3d133f` (#872، 2026-08-19) — خرج منه `tests_v9/test_roadmap_phase23.py::test_cdse_provider`. ومدخلا السجلّ ما زالا يقولان **207**. الراتشِت سليم؛ العطل في النصّ وحده.
  - **(ب) مُعرِّفان لدَينٍ واحد:** `PYTEST-NONASSERTING-EXISTING-DEBT-01` و`TESTS-PASS-WITHOUT-ASSERTING-01`. والأساس القانونيّ يشير إلى الثاني (`"gap"`)، فهو المُرشَّح للهويّة والأوّل لقبٌ مهجور. **ولا دمجَ تدميريّاً** قبل جردِ المُشيرين.
  - **(ج) مفرداتُ حالةٍ حرّة:** قِستُ ~٧٠ صيغة عبر ١٢٥ مدخلاً، و١١٦ فجوة فريدة، و٤٢ بلا سطر «المصدر». **وهذه الأعداد لا تُتبنّى أساساً حاكماً** — خوارزميّتي عدّت كلّ عنوان `##` بمُعرِّف وحدةً قانونيّة، والملفّ يحوي أقساماً تاريخيّة وألقاباً ومداخل «التفصيل الأصليّ»، فقد تكون خلطت الحاضر بالتاريخ.
- **شرطُ العمل (بترتيبه):** ① تصويب 207 ⇒ 206 نصّاً · ② تسمية الهويّة القانونيّة واللقب بلا كتابةٍ فوق المراجع · ③ **حفظُ خوارزميّة الجرد أداةً باختبارات** تحسم `canonical_record` صراحةً (صفُّ جدول؟ قسمُ `##`؟ كلاهما؟) · ④ مفرداتٌ محصورة (`OPEN`/`FIXED`/`VERIFIED`/`PARTIAL`/`ACCEPTED_RISK`/`BLOCKED`) **راتشِتاً**: الصفوف الجديدة والمعدَّلة تلتزم، والقديمُ المخالف أساسٌ مُجمَّد يتقلّص ولا ينمو — فلسفةُ `assertion_presence_guard` نفسها.
- **وما لا يُفعَل:** لا إعادةَ كتابةٍ لـ١١٦ بنداً دفعةً واحدة، ولا توسيعٌ عشوائيّ لـ`brain_state_transition_guard` ليقرأ كلّ نثرٍ عربيّ — الآلةُ القانونيّة تقرأ سجلّاتٍ **بنيويّة** أوّلاً.
- **شرط الإغلاق:** ①–④ منفَّذة، والأعداد مُعادُ اشتقاقها من الأداة المحفوظة لا من قياسٍ عابر.


## CLASSIFIER-BLIND-TO-GENERATORS-OUTSIDE-generated-DIRS-01 — `fixed` بمعيارٍ مشتقّ (2026-08-21) — كان مُعالَجاً بقائمةٍ منتقاة

- **المصدر:** `scripts/ci/resolve_merge_conflicts.py` (`GENERATED_MARKERS`) · `scripts/ci/generated_write_targets.py` · `tests_v9/test_generated_write_targets.py`.
- **الارتداد الذي فرض إعادة الفتح:** في دمج #881 صنّف المُصنِّف `docs/runbooks/GUARD_CATALOGUE.md` **مصدراً** فأوقف نفسه وطلب إنساناً — وهي مصنوعةٌ يقول رأسُها «لا تُحرَّر يدويّاً» ويكتبها `guard_catalogue.py:36`. أي أنّ العلاج السابق (ثلاثةُ مسارات بأعيانها) أغلق حالاتٍ معلومة وترك الصنف مفتوحاً؛ وهذه ثالثةُ ظهوره.
- **ولمَ لم يُوسَّع بالاشتقاق النصّيّ:** جُرِّب وقِيس ضارّاً — «أيّ مسارٍ يُذكَر في سكربت» يعطي **٢١٩** مساراً، منها `guard_mutation_registry.json`: وثيقةُ سياسةٍ بخطّ اليد يقرؤها المحرّك ولا يكتبها. تصنيفُها مولَّدةً يعني «خُذ جانب main ثمّ أعِد التوليد» — أي **إتلاف طفراتٍ مكتوبة**، عطلٌ أسوأ من الوقوف.
- **المعيار المعتمَد:** مسارٌ ثابت يُمرَّر إلى **عمليّة كتابة** (`write_text` · `open` بوضع `w`/`a`/`x`)، مشتقٌّ من شجرة الصياغة. المقيس: **٣١** هدفاً — وفي الفارق عن الـ٢١٩ تقع وثائقُ السياسة.
- **وتصحيحُ تصميمٍ أوّل لي:** بدأتُ بقياسٍ **ديناميكيّ** يُشغّل المكنسة ويرصد زمن الكتابة. عمل، لكنّه ورث هشاشتها و**كسر نقطة الثبات نفسها**: أداةٌ تُعلن `--generate` ولا تعرفها المكنسة تجعلها لا تستقرّ. المقيس: ثلاث دورات بلا ثبات معه، ودورةٌ واحدة بعد إزالته. والساكن يتمّ في **٢.٤ ثانية**.
- **والاتّجاه الخطر محروسٌ بطبقتين:** البيان **يُضيف** ولا يستبدل العلامات، و`HAND_WRITTEN_POLICY` منعٌ صريح **يعلوه**؛ ويفرض اختبارٌ أنّ المجموعتين منفصلتان. وغيابُ البيان يُرجِع «مصدر» — أي يُوقِف الأداة، لا يكتب فوق عمل.
- **حدُّ صدق مُعلَن في البيان نفسه:** مسارٌ يُبنى في وقت التشغيل (حلقة، أو اسمٌ من وسيط) لا يُرى ساكناً.
- **شرط الإغلاق النهائيّ:** ألّا يُضاف مسارٌ يدويّاً إلى `GENERATED_MARKERS` بعد اليوم؛ كلّ جديدٍ يدخل بالاشتقاق أو لا يدخل.
## RAG-ROW-FILTER-HIDES-A-TRUNCATED-ANSWER-01 — عولجت بالتصميم (D09، 2026-08-21)

- **المصدر:** تحكيمُ المالك 2026-08-21 (شريحة D09) · `services/sahool-platform/core/rag/production_qdrant.py` (`canonical_storage_shape` · `corpus_identity` · `readiness_problems`) · `services/rag-retrieval/main.py:75` · `tests_v9/test_rag_corpus_identity_readiness.py`.
- **الخاصّيّة المنتهَكة:** انحرافُ المجموعة حالةُ **خدمة**، لا شرطُ تصفيةٍ لكلّ نتيجة. والتصميمُ الوارد في الحزمة كان يحذف الصفَّ غيرَ القانونيّ من الكثيف ومن المتفرّق معاً.
- **لِمَ الحذفُ أسوأ من المنع:** مِصفاةُ الصفوف تُحوِّل `503` صريحاً إلى `200` بنتائجَ ناقصة **لا يعرف المستهلكُ نقصَها** — إجابةٌ مبتورة تُقرَأ كاملة. وفي مسار RAG هذا يُنتِج جواباً واثقاً مبنيّاً على شاهدٍ غائب، وهو الوضعُ الذي بُنيت المجموعةُ كلُّها لمنعه.
- **العلاج (ثلاث شُعَب بحدودٍ مفصولة عمداً):**
  - **D09-C — سياسة:** `canonical_storage_shape(payload)` مُسنَدٌ نقيٌّ **موضعيّ** لا يقرأ إيصالاً ولا أساساً. وقياسٌ سابق: `production_qdrant.py` لم يكن يقرأ أيّاً منهما أصلاً، فادّعاءُ «فكُّ الارتباط» في الحزمة كان يصف عملاً لا محلَّ له — سُجِّل التصويبُ ولم يُنفَّذ فكٌّ صوريّ.
  - **D09-M — قياس:** `corpus_identity()` هويّةٌ **مركّبة** (`point_count` + `id_set_digest` + `content_digest`). والعددُ وحده يمرّ على استبدالِ المحتوى كلِّه.
  - **D09-E — إنفاذ:** `readiness_problems(report)` حكمٌ **دالّةٌ نقيّة**، يستهلكه `/readyz` و`/v1/search` فيفشلان مغلقاً.
- **ولمَ الحكمُ دالّةٌ نقيّة:** أوّلُ صياغةٍ للاختبار فحصت **نصَّ** المصدر، فمرّت على التعطيل الصريح `if False and …` — النصُّ يبقى قائماً بعد تعطيله. صنفُ `TEXT-GUARD-ANCHORED-IN-THE-WRONG-FILE-01` بعينه. فاستُخرِج الحكمُ دالّةً تُستدعى بتقريرٍ مُختلَق فيُكذَّب بالسلوك.
- **مُكذَّب:** ٦/٦ طفرات على الملفّ تعمل بـ`--run` (اثنتان سابقتان وأربعُ D09)، منها إعادةُ مِصفاةِ الكثيف، واختزالُ البصمة إلى المُعرِّفات، وتعطيلُ حكم الجاهزيّة، وقبولُ هويّةٍ لم تُقَس. و١٤ اختباراً مرسًى بـAST لا بالنصّ.
- **حدُّ صدق — ما لم يُقَس:** لا Qdrant حيّة ولا إيصالُ جرد. السلطةُ لم تتحرّك: `EVIDENCE_REQUIRED · capable=False`. وD09-M/E مقيسان على تقاريرَ مُختلَقة لا على مجموعةٍ حقيقيّة.
- **شرط الإغلاق النهائيّ:** إيصالُ جردٍ حيّ يُنتِج `corpus_identity` من المجموعة الفعليّة، ويُثبِت أنّ `noncanonical_serving_points` يطابق التصنيفَ في الإيصال.


## MUT-REGISTRY-DUPLICATE-KEY-SHADOWS-A-BLOCK-01 — مسدودةٌ بحارسٍ حاجب (2026-08-21)

- **المصدر:** `docs/architecture/guard_mutation_registry.json` على main `a1f5da7f` — مفتاحان مكرّران تحت `behavioural`: `.github/workflows/ci.yml` و`docs/architecture/rag_authority_convergence.json`.
- **الخاصّيّة المنتهَكة:** `json.load` يأخذ **الأخير** ويطرح ما قبله. فكتلةٌ ثانية لملفٍّ له كتلةٌ أصلاً تُعطِّل **كلَّ** طفرات الأولى — بلا رسالة، وبلا أن يحمرّ شيء.
- **الأثرُ المقيس هنا: صفر.** الكتلتان الأوليان متطابقتان بتّاً، والثانية من الزوج الآخر **مجموعةٌ فائقة** لسابقتها. فالمُشغَّل فعلاً كان يحوي كلَّ الطفرات الأربع. القياسُ جرى بـ`object_pairs_hook` لأنّ `json.load` نفسه لا يرى التكرار.
- **ولمَ تُسجَّل رغم صفريّة الأثر:** الصنفُ هو العطل لا الحادثة. أوّلُ كتلةٍ ثانية **أصغر** من سابقتها تُسقِط الفرقَ صامتاً — وهو «حارسٌ كفّ عن الحجب بلا أن يحمرّ» المُسجَّل في هذا المستودع بعينه، واقعاً في السجلّ المبنيّ لقياسه.
- **كيف نشأ:** إلحاقُ كتلٍ في جلساتٍ متعاقبة بلا فحصِ وجودِ المفتاح. ولا شيءَ في الشجرة يمنعه: كلُّ قارئٍ يستعمل `json.load`، وهو **أعمى عن التكرار بالتصميم**.
- **ما فُعِل في D09:** طيُّ التكرار وقع اضطراراً — أيُّ تحريرٍ يمرّ بـ`json` يطويه، وإعادةُ كتابته يدويّاً كتابةُ وثيقةِ سياسةٍ معطوبةٍ عن عِلم. المُتَّحَدُ محفوظٌ بالقياس أعلاه (٩٢ مفتاحاً فريداً، والكتلتان بطفرتيهما قائمتان).
- **العلاج (شريحةٌ مستقلّة فوق `7fecea3d`، لم تُخلَط بـD09):** `scripts/ci/json_duplicate_key_guard.py` — حاجبٌ في `structural-lint` وفي `preflight` خطوةً `٢ﻫ`، ومُعلَنٌ في `preflight_required.json`.
- **الكشفُ عند المحلّل لا بمسحٍ معجميّ — وهذا انحرافٌ مقصودٌ عن صياغة التكليف:** التكليفُ قال «النصّ الخام قبل التحليل»، والمُنفَّذ `object_pairs_hook` — وهي الواجهة التي تُسلِّم كلَّ زوجٍ **رآه المحلّل** قبل انهياره إلى `dict`. والخاصّيّةُ المطلوبة («ما يُحمَّل ≠ ما كُتِب») تتحقّق بها تماماً، بينما المسحُ النصّيّ يرى `"dup": 1` داخل **قيمةٍ نصّيّة** مفتاحاً فيُدين وثائقَ سليمة — وهو `GUARD-PINS-IMPLEMENTATION-NOT-PROPERTY-01` بعينه. والمرفوضُ هو `json.load` **الافتراضيّ** الذي يطوي التكرار، لا وحدةُ `json`. والتكذيبُ محفوظٌ اختباراً: `test_a_key_shaped_string_value_is_not_a_duplicate` يُحمِّر التصميمَ البديل.
- **النطاق بلا استثناءٍ ولا أساسٍ مُجمَّد — وهذا مقيس:** ٢٣٣ ملفّاً متعقَّباً، صفرُ تكرار، صفرُ متعذّرِ القراءة. ومفتاحٌ مكرَّر لا حالةَ استعمالٍ مشروعةً له في وثيقة سياسة، فالاستثناءُ ثقبٌ لا مرونة.
- **مُكذَّب على التاريخ لا على تجهيزةٍ وحدها:** الآليّةُ شُغِّلت على شجرة `a1f5da7f` فأخرجت المفتاحين بمسارهما `$.behavioural` ورمزِ خروجٍ ١، وصمتت على `7fecea3d`. و٦/٦ طفرات مزروعة تُحمِّر اختباراتٍ مسمّاة.
- **ولا اختبارَ مشروطاً بـSHA:** كان يُغري تثبيتُ `a1f5da7f` شاهداً، لكنّ استنساخ CI بعمق ١ لا يبلغه فيصير `skipif` صمتاً لا تكذيباً (`STABLE_WRONG_TEST`). فشكلُ العطل مُثبَّتٌ حرفيّاً في `test_a_duplicate_inside_behavioural_is_detected`.
- **وما لم يُغيَّر عمداً:** دلالاتُ سجلّ الطفرات لم تُمَسّ — لا صيغةَ جديدة ولا مفتاحَ جديد ولا قارئَ مُعدَّل. الحارسُ يقول «لا تكتب مفتاحاً مرّتين»، ولا يقول للسجلّ ما يعني.
- **حدُّ صدق:** يحرس التكرارَ وحده. وثيقةٌ بمفتاحٍ **مفقود** أو بقيمةٍ خاطئة تمرّ منه بحقّ — ذلك عملُ حرّاسِ المخطّط، لا عملُه.


## QDRANT-CLIENT-CREDENTIAL-LOCALITY-01 — `fixed` (P1 تقويةُ عقد، 2026-08-21)

- **المصدر:** `docker-compose.v9.yml:1710,1758,1872` · `docker-compose.fixed.yml:862,894` · `scripts/ci/compose_auth_sink_guard.py` (`client_binding_defects`) · `docs/architecture/compose_auth_sinks.json` (`required_clients`).
- **المقيس قبل الإصلاح:** خمسةُ ارتباطات عملاء Qdrant إنتاجيّة لا تُثبِت الاعتماد محلّيّاً — أربعةٌ `${QDRANT_API_KEY}` عارية وواحدٌ `${QDRANT_API_KEY:-}`.
- **وليست تجاوزَ استيثاقٍ مُثبَتاً حيّاً، وهذا حدُّ صدقٍ لا تحفّظ:** مصرفُ الخادم في المكدّسات نفسها يُلزِم **المتغيّر ذاته** بـ`:?`، فلا يبلغ العميلَ مفتاحٌ خالٍ ما دام الملفّان معاً. الخطرُ **انحرافُ محلّيّة العقد**: نقلُ الخادم إلى profile أو override، أو استخراجُ الخدمة إلى مكدّسٍ آخر، يحوّل الاعتماد الضمنيّ إلى إقلاعٍ بلا اعتماد صالح.
- **وبقعةٌ عمياء في حارسي:** سجلّ المصارف كان يحمل متغيّر **الخادم** (`QDRANT__SERVICE__API_KEY`) وحده، فلم يكن يرى ارتباطات العملاء أصلاً.
- **العلاج بثلاث خصائص لا واحدة:**
  ① `_accepted_required_nonempty(value, source_env)` — **مصدرُ قرارٍ واحد** للمصرف وللعملاء معاً. وشكلُ `:?` وحده لا يكفي: `${WRONG_SECRET:?x}` غير فارغ حقّاً لكنّه ليس السرَّ الذي يملكه العقد.
  ② كلُّ عميلٍ إنتاجيّ مُسجَّل يجب أن يكون `REQUIRED_NONEMPTY` **محلّيّاً**.
  ③ **واكتشافٌ لا قائمة:** خدمةٌ جديدة على `production_stacks` تستعمل متغيّراً مُسجَّلاً ولم تدخل السجلّ ⇒ تحجب؛ ومُسجَّلٌ اختفى ⇒ يحجب. ومجموعةُ متغيّرات الاكتشاف تُشتقّ من السجلّ نفسه، فلا قائمة Qdrant موازية.
- **مُكذَّب:** ١١/١١ طفرة بالزرع الفعليّ — منها ثلاثٌ جديدة: قبولُ أيّ متغيّر `:?` · حذفُ فحص رابط العميل · وعميلٌ إنتاجيّ جديد خارج السجلّ لا يحجب.
- **حدُّ صدق:** لم تُقلَع Qdrant ولم يُسبَر منفذُها. المقيس دلالةُ الاستيفاء وانحرافُ الارتباطات، لا رفضٌ حيّ بـ401.


## AUTHENTICATED-QDRANT-CLIENT-CREDENTIAL-MUST-BE-NONEMPTY-01 — ⛔ عقدُ حراسةٍ لا فجوة تنفيذيّة (2026-08-21)

- **ما هو:** اسمُ **عقد** يفرضه `scripts/ci/compose_auth_sink_guard.py` عبر `client_binding_defects()`، لا عطلٌ مفتوح. سُجِّل هنا لأنّ شكله شكلُ مُعرِّف فجوة، فذكرُه في دفتر القرارات يقرؤه `brain_narrative_registry_consistency` ادّعاءَ وجود — وهي ثالثةُ مرّةٍ يقع فيها هذا الصنف في هذه الجلسة (`SERVER-AUTH-SECRET-MUST-BE-NONEMPTY-01` و`COMPOSE-DEFAULT-SECRET-IS-A-PUBLISHED-SECRET-01` قبله).
- **المصدر:** `docs/architecture/compose_auth_sinks.json` (`client_contract` · `required_clients`) · `scripts/ci/compose_auth_sink_guard.py` · `tests_v9/test_compose_auth_sink_guard.py`.
- **الخاصّيّة:** خدمةٌ في مكدّسٍ إنتاجيّ تتّصل بخادم Qdrant المُفعَّل استيثاقُه يجب أن تستقبل `QDRANT_API_KEY` من استيفاءٍ يُثبِت الوجود وعدم الفراغ **محلّيّاً عندها** — لا أن ترثه من مجاورةِ مصرف الخادم في الملفّ نفسه.
- **وما ليست:** `SERVER-AUTH-SECRET-MUST-BE-NONEMPTY-01` (عقدُ الخادم). والعلاقة احتواءٌ لا ترادف: الخادمُ يُلزِم متغيّره، والعميلُ يُلزِم اعتمادَه — ونقلُ الخادم إلى profile يُسقِط الثاني ولا يمسّ الأوّل.
- **العطل الذي أوجده:** `QDRANT-CLIENT-CREDENTIAL-LOCALITY-01` أعلاه.
## RAG-D12-PLANNER-INERT-AGAINST-THIS-TREE-01 — عولجت (2026-08-22)

- **المصدر:** حزمةُ D08–D12 (`scripts/architecture/rag_logical_identity_migration_plan.py`) · `scripts/architecture/rag_live_corpus_audit.py` على `f8b49acb` · قياسُ هذه الجلسة.
- **العطل:** مخطِّطُ D12 يقرأ `explicit_logical_chunk_id` و`logical_identity_source` من كلّ سجلّ نقطة، وجردُ هذه الشجرة لا يُنتِج أيّاً منهما. فعلى إيصالٍ حقيقيّ تكون الهويّةُ الصريحة معدومةً في كلّ صفّ، ويرمي أوّلُ صفٍّ `CANONICAL_ACTIVE` ⇒ `ValueError: canonical point … lacks explicit logical chunk identity` وتسقط الخطّةُ كلُّها.
- **السبب الجذريّ:** D12 بُني على توسعةٍ لجرد D08 لم تهبط قطّ — الذي نزل في #884 جاء من رقعةٍ أخرى. فحزمةٌ واحدة، ومُنتِجان مختلفان لعقدٍ واحد.
- **ولمَ الحقلُ الجديد ليس زينة:** «هل استُعير المُعرِّف» لا تقول أين الهويّةُ ولا ما هي، وقرارُ الهجرة يحتاج الاثنين — صفٌّ بلا هويّةٍ في حمولته لا يُهاجَر، وصفٌّ بهويّةٍ صريحة يُهاجَر إليها هي لا إلى UUID التخزين.
- **العلاج (شريحتان):** `D12-PRE` يُنتِج الحقلين ويشتقّ `fallback_identity_used` من `logical_identity_source` (سلطةٌ واحدة)، وحارسُ الإيصال يرفض إيصالاً بلا مصدرِ هويّةٍ أو بتناقضٍ بين الحقلين — فرفضٌ مُسمًّى عند البوّابة بدل انهيارٍ في الأداة. ثمّ D12 نفسُه.
- **مُكذَّب:** ٤ طفرات لـ`D12-PRE` و٥ لـD12، كلُّها مقتولة بالزرع. والتكافؤُ الإضافيّ مُثبَتٌ بالجداء الكامل: **صفرُ انحرافٍ في ٨/٨**.
- **حدُّ صدق:** لا Qdrant حيّة ولا إيصالُ جرد — فلم تُنتَج خطّةٌ حقيقيّة قطّ. المقيسُ حمولاتٌ وتقاريرُ مُختلَقة.


## RAG-STORAGE-PROJECTION-RESTATED-FOUR-TIMES-01 — عولجت (2026-08-22)

- **المصدر:** `services/sahool-platform/core/rag/production_qdrant.py` (كان مضمَّناً في `upsert`) · حزمةُ D12 (نسختان) · `services/qdrant-seed/seed.py:324`.
- **العطل:** صيغةُ إسقاط الهويّة المنطقيّة إلى مُعرِّف تخزين (`uuid5(NAMESPACE_URL, "sahool-rag:" + id)`) مُعادةُ الكتابة في **أربعة** مواضع. وتبديلُ الفضاء أو البادئة في أحدها يجعل الآخرين يحسبون مُعرِّفاتٍ لا يُنتِجها الكاتب — انحرافٌ صامتٌ يظهر أوّلَ ما يظهر في هجرةٍ تكتب فوق لا شيء أو فوق الخطأ.
- **العلاج:** `canonical_storage_point_id()` سلطةٌ واحدة في `production_qdrant.py`؛ الكاتبُ يناديها، والمخطِّطُ وحارسُه يستورانها بدل نسخِ الصيغة. **مُثبَتٌ بالقياس:** المواضعُ الثلاثة تُعطي القيمةَ نفسها على ٤/٤ مدخلات (منها عربيّةٌ وطويلة)، وصفرُ دالّةِ عكسٍ في أيٍّ منها.
- **والباذرُ استُثني بقياسٍ لا بإهمال:** `services/qdrant-seed` خدمةٌ محاويَة مستقلّة (Dockerfile ومتطلّباتٌ خاصّة) لا ترى `core.rag` وقتَ التشغيل، ففرضُ الاستيراد يكسر حاويتَها — علاجٌ أسوأ من العطل. فيُترَك الاقتران **ويُفرَض التطابق**: `test_every_writer_of_qdrant_points_projects_identity_identically` يقرأ صيغةَ الباذر من مصدرها ويُحمِّر إن اختلف الفضاءُ أو البادئة.
- **حدُّ صدق:** العقدُ يفرض تطابقَ **الصيغة** لا تطابقَ ناتجٍ حيّ — لم يُقلَع الباذرُ ولم تُقارَن نقاطُه بنقاط الكاتب على مجموعةٍ حقيقيّة.


## RAG-D12-GUARD-CONDEMNS-A-CORRECT-PLAN-01 — عولجت قبل التبنّي (2026-08-22)

- **المصدر:** `scripts/architecture/rag_logical_identity_migration_plan_guard.py` كما سُلِّم في الحزمة · قياسُ هذه الجلسة قبل الالتزام.
- **العطل:** الحارسُ كان يفرض على كلّ صفٍّ مستعارِ المُعرِّف أن يكون `HOLD_IDENTITY_EVIDENCE` **بالاسم**. وصفٌّ مستعارٌ مُصنَّفٌ `ORPHANED_UNATTRIBUTED` يُنتِج له المخطِّطُ `HOLD_UNATTRIBUTED` بحقّ — وهو احتجازٌ لا يقلّ منعاً — فيرفضه الحارس. أي أنّ المخطِّطَ وحارسَه يتناقضان على مُدخَلٍ مشروع، والحارسُ هو المخطئ.
- **ولمَ يهمّ:** حارسٌ يُحمِّر الصوابَ يُدرِّب قارئَه على تخطّيه — وهو أسوأ من غيابه. والحالةُ ليست نظريّة: الشاهدُ الحيّ يقول إنّ في المجموعة صفوفاً غيرَ قابلةٍ لإعادة البناء.
- **العلاج:** ضُيِّق الشرطُ إلى الثابت المقصود — «لا تُرقَّى هويّتُه ولا يُهاجَر» — بدل تثبيت اسمِ الاحتجاز. ومُثبَتٌ بشاهدين: أحدهما يعزل الترقية على إيصالٍ متناقض، والآخر يمرّ على ثلاثة تصنيفاتٍ ويُثبِت أنّ أيّاً منها لا يُدان لاسم احتجازه.
- **وكيف انكشف:** لم يكشفه اختبارٌ بل **مكنسةُ الطفرات**: نجت طفرتان لأنّي سمّيتُ لهما اختبارَين لا يمرّان بالقاعدتين. فالمكنسةُ أمسكت خطأً في شهادتي لا في الشيفرة، ثمّ قاد استقصاءُ النجاة إلى العطل الحقيقيّ.


## PREFLIGHT-LOCALE-GUARD-TRAPPED-IN-THE-EXPENSIVE-LAYER-01 — مسدودةٌ بخطوةٍ في الطبقة السريعة (2026-08-22)

- **المصدر:** `scripts/ci/preflight.sh` خطوة `٢و` · `tests_v9/test_local_preflight_contract.py::test_the_locale_decoding_guard_runs_in_the_fast_tier_not_only_inside_the_suite` · `docs/architecture/preflight_required.json`.
- **الخاصّيّة المنتهَكة:** حارسٌ قائمٌ ويحجب، لكنّه اختبارُ pytest فلا يعمل إلّا في الجناح الكامل (٨أ). فالطبقةُ التي يُشغّلها المطوّر قبل الدفع **لم تكن تسأل السؤال أصلاً**.
- **والحادثةُ مقيسة لا مُفترَضة:** على #886 مرّ `preflight --fast` بـ«إخفاقات=0» على شجرةٍ حمّرها الجناحُ الكامل — أربعةُ مواضع `subprocess(text=True)` بلا `encoding` في ملفّ اختبارٍ متبنًّى.
- **وما يجعلها تستحقّ اسماً:** الصنفُ نفسُه أُصلِح على #884 **في الجلسة نفسها**، ثمّ أُعيد بتبنّي شيفرةٍ واردة بلا إعادة فحصها. القراءةُ لم تمسكه؛ المسحُ أمسكه بعد ٦ دقائق كان يكفيها ٤٫٦ث.
- **العلاج:** خطوة `٢و` تُشغِّل **الاختبارَ الحاجب وحده** (٤٫٦ث) لا الملفّ كلَّه (١٧٫٧ث).
- **والحدُّ مُعلَنٌ لا مُهرَّب:** حارسا التملّص — «الأساس لا ينمو» و«ملفٌّ مُؤسَّس لا يُضيف مخالفة» — يبقيان في ٨أ بقرار. **المخالفةُ خفيّةٌ في المراجعة والمهربُ ظاهرٌ فيها:** نموُّ الأساس يُرى في الـdiff، وقراءةٌ بلا ترميز في ملفٍّ جديد لا تُرى إلّا بالمسح. ويُثبِّت الاختبارُ هذا الحدَّ صراحةً كي لا يُستبدَل بالملفّ كلِّه بلا قرارٍ معلَن.
- **الإرساءُ على الاستدعاء لا على المسار** — درسُ ٢د: المسارُ يرد في الشرح وفي العقد، فالإرساءُ عليه قد يُطابِق نثراً فوق الخطوة بينما السطرُ المنفَّذ تحت الخروج المبكر.
- **مُكذَّب:** طفرةٌ مزروعة تُخرِج الخطوة من الطبقة السريعة فتُحمِّر الاختبارَ المسمّى.
- **حدُّ صدق:** لا يُغلِق `GUARD-DIES-PRINTING-ITS-OWN-SUCCESS-UNDER-C-LOCALE-01` نفسَه — ذاك قائمٌ ومحروس. هذه تُغلِق **موضعَ قياسه** فقط.

## SQUASH-MERGE-MAKES-ANCESTRY-AN-UNSATISFIABLE-PROOF-01 — مسدودةٌ بعقد انضباط (2026-08-22)

- **المصدر:** `tests_v9/test_ancestry_proof_discipline.py` · `production_qdrant` NO-GO الكاذبان (مرساتا `7fecea3d` و`3635dfb8`) · `git merge-tree` تكافؤ الشجرات في G2.
- **الخاصّيّة المنتهَكة:** المستودع يُدمَج سحقاً، فالتزامُ الفرع **لا يصير سلفاً لـmain أبداً** — وبرهانُ الوجود بـ`merge-base --is-ancestor` على SHA فرعٍ غيرُ قابلٍ للإرضاء بالبناء: يفشل على محتوًى هابطٍ فعلاً.
- **والحادثة مقيسة ثلاثاً في يوم واحد:** تدقيقان خارجيّان أصدرا NO-GO كاذباً على D09 («D09-C/M/E NOT FOUND») لأنّ مرساتيهما التزاما فرعٍ سُحق، وثالثةٌ على D06-C1 («غير موجود على 3635dfb8» — وهو التزامُ D06-C1 نفسُه على صفر فرع).
- **العلاج:** عقدُ انضباطٍ ذو وجهين — مسحٌ يُبقي كلّ استعمالٍ لـ`--is-ancestor` في الشيفرة التنفيذيّة ضمن قائمة سماحٍ **مسبَّبة** (ثلاثة مواضع مدقَّقة: مُصنِّفُ تنظيفٍ ينحرف آمناً · برهانُ أسلافٍ داخل تاريخ main الخطّيّ · إنفاذٌ يرفض SHA الفرع أصلاً)، وبرهانٌ تنفيذيّ يبني السيناريو في مستودعٍ مؤقّت: السلفيّة تكذب والشجرةُ تصدق.
- **مُكذَّب:** زرعُ استعمالٍ جديد في ملفٍّ متعقَّب يُحمِّر المسح؛ والبرهانُ التنفيذيّ يفشل لو صار السحقُ يورّث السلفيّة.
- **حدُّ صدق:** لا يمنع الفخَّ في أدواتٍ خارج المستودع (كتدقيقات بيئاتٍ أخرى) — يمنع نموَّه هنا ويوثّق المعيارَ البديل تنفيذيّاً.

## PREFLIGHT-3J-BLIND-TO-BEHAVIOURAL-SOURCES-01 — مسدودةٌ بتوسيع الالتقاط (2026-08-22)

- **المصدر:** `scripts/ci/preflight.sh` كتلة تقصير ٣ج · `tests_v9/test_local_preflight_contract.py` (الاختبارات الثلاثة) · قياسا #886/#888.
- **الخاصّيّة المنتهَكة:** كتلة التقصير كانت تقرأ `registry["mutated"]` وحدَه — فمصدرٌ سلوكيّ متغيّر (وطفراتُه تحجب في CI سواءً) يطبع «لا حارسَ مسّه التغيير» زوراً ويمرّ بلا زرع. وطفراتُ `preflight.sh` نفسِه سلوكيّة: تغييرُ الأداة لم يكن يُزرَع محلّيّاً أبداً.
- **العلاج:** القسمُ السلوكيّ يدخل الالتقاط (مفاتيحُه مسارات)، والتصعيدُ من الشاهد صار مجموعاتٍ لا مفتاحاً أخيرَ الترجيح، ويلتقط حقل `test` في المستويين، ومفاتيحُ `$…` الوصفيّة محصَّنة.
- **مُكذَّب:** الاختباراتُ الثلاثة تشغّل الكتلةَ المشحونةَ المستخرَجة من preflight.sh على مستودعٍ مُختلَق — الشيفرةُ القديمة تُحمِّرها — وطفرتان مسجّلتان مقتولتان، والبرهانُ الذاتيّ: `--fast` صار يزرع preflight.sh لأنّه مصدرٌ سلوكيّ متغيّر.
- **حدُّ صدق:** يغلق شقّ ٣ج من G18؛ دينُ ترميز Windows شقُّه الآخر في شريحةٍ شقيقة.

## CORPUS-RECONCILIATION-01 — منفّذ التسوية مكتوبٌ بالبوّابة؛ التنفيذ الحيّ للمالك (فُتحت 2026-08-23 · **open**)

- **المصدر:** حادثة البذر المكرَّر (199=128+64+7 · `seed:114`) · حكما المالك النهائيّان: تفرّدٌ منطقيّ على كامل المجموعة بما فيها `__seed_quarantine__` (`services/sahool-platform/core/rag/production_qdrant.py:1018` يفرضه قبل استثناء الحجر) · «أيّ HOLD_LOGICAL_ID_COLLISION يبقى HOLD ولا يُنفَّذ ضدّه شيء» · بذرٌ قانونيّ لا حذف · بوّابة قبولٍ من ثلاث عشرة خطوة.
- **الخاصّيّة المنتهَكة:** الجسم الحيّ يحمل تصادمات هويّةٍ منطقيّة عبر النطاقات ولا أداة تنفيذٍ تُحوّل أحكام المالك إلى مسارٍ كتابيّ مقيسٍ مغلقٍ على HOLD.
- **العلاج (المُنجَز):** `scripts/architecture/rag_corpus_reconciliation_executor.py` — تشغيلٌ جافّ افتراضاً (حكمه لا يبلغ PASS أبداً)، `--execute` يضيف ٦–١٣، البذر القانونيّ وحده يكتب، والهويّات المتصادمة تُستثنى عبر `QDRANT_SEED_EXCLUDE_CHUNK_IDS_FILE` الذي صار البذّار يقرؤه مغلقاً؛ بقايا التصادم بعد البذر ⇒ حكم HOLD يعود للمالك. ٩ اختبارات + طفرتان مسجَّلتان مُكذَّبتان.
- **مُكذَّب:** إسقاط الاستثناء يُحمّر شاهد ملفّ الاستثناء الفعليّ؛ قراءة الغياب نجاحاً يُحمّرها شاهد التشغيل الجافّ.
- **حدُّ صدق — لماذا تبقى مفتوحة:** الأداة لا تساوي التسوية. الإغلاق يتطلّب التنفيذ الحيّ في بيئة المالك: جرد الهويّة → الخريطة → `--execute` → الثلاث عشرة كلّها خضراء بإيصالٍ مربوطٍ بالمرساة — وذلك بيد المالك ومقامه، لا من هذه الشجرة.

## RZ-VARIETY-POLICY-RESOLUTION-01 — حلّ سياسة الجذور أعمى عن الصنف (فُتحت 2026-08-24 · **fixed** في شريحة `rz-variety-01`)

- **المصدر:** `services/sahool-platform/api/canonical_root_zone_profile.py` (`resolve_canonical_root_zone_profile`) · `migrations/v169_canonical_root_zone_hydraulic_profile.sql:8` (`variety text NOT NULL DEFAULT ''`) · رقعة المالك المرفوعة + مراجعته الثانية.
- **الخاصّيّة المنتهَكة:** الجدول يميّز الصنف بالتصميم (قيد فريد وفهرس مركّب على `variety`) والمُحلّ كان يتجاهله كليّاً — سياسة صنف مسجَّلة لا تُنتقى أبداً، والعامّ يحكم دائماً.
- **العلاج (المُنجَز):** حلّ بطبقتين فاشل-مغلق: الصنف المطابق ثم العامّ `variety=''` ثم الحجب — الخصوصيّة تسبق الحداثة (`specificity > recency`). مصدر الصنف متعاقد: `seasons.cultivar` وحده (v32 «الصنف / variety»)؛ `seed_variety_source` مستبعَد صراحةً (v42: مورّد لا صنف). اللقطة القانونيّة تسجّل `root_policy_variety` (بترقية `root-zone-hydraulics/1.2.0`) كي يثبت الدليل وحده أيّ خصوصيّة اختيرت. ٩ اختبارات موجَّهة بالوسائط لا بالترتيب + اختبار بصمة حقيقيّ (v1≠v2) + اختبار RLS تكاملي على PG حيّ مربوط بنصّ الاستعلام الإنتاجي.
- **حدُّ صدق:** ادّعاء المراجعة أنّ التوقيع SyntaxError (P0) مُكذَّب قياساً — المعاملات بعد `*` كلمات-مفتاحيّة ولا يقيّدها ترتيب الافتراضيّات؛ الملفّ يُجمَع والاختبارات تمرّ. أُعيد الترتيب تحسيناً أسلوبيّاً لا إصلاحاً.

## WOFOST-UNKNOWN-FALLBACK-01 — المحصول المجهول كان يُصنَّف شجرة معمّرة صامتاً (فُتحت 2026-08-24 · **fixed** في شريحة `rz-variety-01`)

- **المصدر:** `services/sahool-platform/api/wofost_crop_params.py` (`crop_model_type` كان `or "perennial_tree"`) · مراجعة المالك (البند ١١).
- **الخاصّيّة المنتهَكة:** تصنيف ملفَّق: محصول غير معرَّف يستعير إطار الشجرة المعمّرة كاملاً (نسب تغيير، بارامترات، R²) بلا أساس — «قابليّة الإرجاع ليست أهليّة تصنيف».
- **العلاج (المُنجَز):** `crop_model_type(مجهول) = "unsupported"`، و`wofost_adaptation_guidance` يُرجع حمولة حجب صريحة (`status=blocked · reason=crop_model_type_unknown`) بلا أيّ قيمة إطار مستعارة؛ المعروف بلا تغيير. ٤ اختبارات وحدويّة تكذّب التسريب.

## BRAIN-DUP-ROW-ESCAPES-THE-ADJACENCY-NET-01 — صفُّ سجلٍّ مكرَّر يقفز فوق شبكة التلاصق (فُتحت 2026-08-25 · **fixed** في شريحة `brain-row-uniqueness-01`)

- **المصدر:** `sahool-brain/gaps/registry.md` (صفّا `GATE-READS-A-FROZEN-EVENT-PAYLOAD-NOT-THE-LIVE-BODY-01` في 115/117 بينهما صفُّ #914) · `scripts/ci/brain_duplicate_gap_identity_guard.py` (`adjacent_duplicate_identities`) · دمج union عبر PRs متتابعة.
- **الخاصّيّة المنتهَكة:** بصمة union الأصلية سطران **متلاصقان**، لكنّ التكرار العائد عبر دمجٍ لاحق يهبط **غير متلاصق** — فحارس التلاصق أعمى عنه بالتصميم، وصفّ الجدول إعلانُ الحالة الوحيد لفجوته فلا يحتمل التعدّد.
- **العلاج (المُنجَز):** فحص تفرُّد **عالميّ لصفوف الجدول** في سجلّ الفجوات وحده (`global_duplicate_row_identities` + `ROW_FULL_ID_RE` بهويّة الخليّة الكاملة **بالنقاط**)؛ العناوين مستثناة — السلاسل التاريخية المقصودة مقيسة قائمة (1478/1489، 1582/1590/1601). والبقايا المكرَّرة أُزيلت **بصفر فقد نصّ**: قِيس احتواء نصّها حرفيّاً بكامله (2262/3300 بايتاً) في المدخل المدموج القانوني، الذي وُسِّع بسجلّ العودة.
- **مُكذَّب من ثلاث جهات (3/3 بالزرع):** تحييد الفحص العالميّ يُحمِّر شاهد اللاتلاصق · إسقاط النقطة من الهويّة **يُعمي** الشبكة عن الصفوف المنقوطة (لا يدمج الهويّات — مرساة `\s*\|` تُفشِل المطابقة عند النقطة، مقيس ضدّ فرضيّتي الأولى) · التكرار-بدل-التلاصق يرفع السلاسل التاريخية إنذاراً.
- **محاسبة البايتات (سبب هذا الملحق):** إزالة صفّ البقايا (2262 بايتاً) قابلها سجلُّ العودة وقسمُ الفجوة (1877) ⇒ تقلّصٌ صافٍ 385 بايتاً، و`brain_append_only_guard` يفرض **رتابةً بايتيّة** على هذا السجلّ بين كلّ (التزام، والد) بلا استثناء احتواء — وهو نفس الحجب المقيس في سابقة 2026-08-23 (`JOURNAL_SHRANK`، فُقِد 2794). فالمخرجُ المنضبط ليس حشواً بل **إثباتُ تكذيبٍ كامل يُدوَّن هنا بدل أن يبقى في مخرَج جلسة**: الطفرة الأولى (`return []` مكان جامع الصفوف) قتلها `test_a_non_adjacent_row_duplicate_is_caught_globally` بشاهد `[('GAP-AA-01', [1, 3])]` على نصٍّ يفصل التكرارَ صفٌّ وسيط؛ والثانية (إسقاط النقطة من `ROW_FULL_ID_RE`) قتلها `test_a_dotted_row_id_duplicate_is_still_visible_to_the_global_net` — وكانت فرضيّتي الأولى أنّ الإسقاط «يدمج» الإعفاءين المنقوطين هويّةً واحدة، فأثبت الزرعُ أنّ المطابقة **تفشل كليّاً** عند النقطة بمرساة `\s*\|` فتعمى الشبكة عن الصنف المنقوط كلّه: إيجابيّ كاذب سالبٌ لا موجب، والاختبار أُعيدت كتابته على المقيس.
- **حدُّ صدق:** المقترح الوارد (تفرّد عالميّ ساذج بقائمة بادئات مثبَّتة + حذف الصفّ المدموج 117) كان سيحذف **المدخل القانوني** ويُبقي البقايا، ويُعيد الإنذارات الكاذبة العشرة، وتفوت قائمتُه معظمَ المعرّفات الحقيقية — نُفِّذ عكسُه المقيس.
## MUT-SWEEP-RUNS-THE-WHOLE-FILE-PER-PLANT-01 — كلّ زرعة كانت تشغّل ملفّ الاختبار كاملاً (فُتحت 2026-08-25 · **fixed** في شريحة `mut-narrow-01`)

- **المصدر:** `scripts/ci/guard_mutation_guard.py` (`_run_tests` كان يستقبل `test_file` كاملاً لكلّ زرعة) · قياس 2026-08-24: ملفّ حارس التفرّد كاملاً ~9.7ث (23 اختباراً تبني مستودعات git) مقابل الاختبار المتوقَّع وحده ~0.5ث · مكنسة CI التاريخية ~50 دقيقة داخل وظيفة *Unit Tests* (سقفها رُفع إلى 90 في `MUT-SWEEP-TIMEOUT-01`).
- **الخاصّيّة المنتهَكة:** حكم «مقتولة» لا يحتاج إلا سقوط الاختبار المُسمّى — تشغيل بقية الملفّ لكلّ زرعة كلفة بلا معلومة في الحالة الغالبة قطعاً (شجرة خضراء = كلّ الزرعات مقتولة).
- **العلاج (المُنجَز):** «ضيّق ثم تراجَع» (`_run_tests_for_mutation`): معرّف عقدة صريح `file::name` (لا `-k` — المطابقة الجزئية تجرّ ما لم يُقصَد)؛ المسار السريع يحسم «مقتولة» بنفس معيار `_outcome` حرفيّاً، وكلّ ما عداه (مرّ المتوقَّع · سقط غيره · لم يُجمَع الاسم · انهيار) يتراجع إلى الملفّ الكامل فتُحسَم `unexpected_green`/`wrong_test`/`runner_did_not_run` من نفس المشهد القديم — **لا حكم يتغيّر**. مسار التشخيص المكرَّر (`_diagnose_repeat`) على نفس المقعد.
- **مُكذَّب:** 3 اختبارات جديدة (قتل ضيّق باستدعاء واحد · تراجُع عند مرور المتوقَّع بحكم `wrong_test` محفوظاً · تراجُع عند تعذّر الجمع) + طفرتان مسجَّلتان (تحييد المسار السريع ⇒ عودة الصنف؛ إسقاط التراجع ⇒ حكم من مشهد ناقص) — **2/2 مقتولتان بالزرع**، و49/49 جناح المُشغِّل أخضر.
- **حدُّ صدق:** القياس المحليّ لا يصلح لتقدير مكسب CI — استدعاء `--only` ينسخ المرآة المعزولة في كلّ مرّة فيهيمن النسخ على الزمن الحائطي (sys ~5–9ث)، بينما CI ينسخها مرّة واحدة للمكنسة كلّها. المقيس محليّاً بصدق: زمن CPU الاختباري هبط ~3× حيث تكثر الزرعات (claim_base: user 14.0→4.7ث لثماني زرعات). **رقم CI بعد الدمج هو الحكم**، والتقدير ~50 ← ~15–25 دقيقة. والمرحلة الثانية (تقسيم متوازٍ بوظيفة مصفوفة) تبقى مؤجَّلة بشرطها الموثَّق في `MUT-SWEEP-TIMEOUT-01`: عقد فحوص-مطلوبة قبل أيّ نقل خارج الوظيفة.

## REQUIRED-CHECKS-DRIFT-IS-INVISIBLE-IN-BOTH-DIRECTIONS-01 — سطحُ الإنفاذ نفسه لم يكن مقيساً (فُتحت 2026-08-25 · **fixed** في شريحة `required-checks-contract-01`)

- **المصدر:** `scripts/ci/branch_protection_contract_guard.py` (كان يفرض `required_review_thread_resolution` وحده من ظرف القواعد النافذة) · `tests_v9/test_ci_pipeline_settings.py` (قائمة ١٤ اسماً تُقارَن بأسماء وظائف `ci.yml` لا بالمُنفَذ) · تعليق `ci.yml:timeout-minutes` و`MUT-SWEEP-TIMEOUT-01` (كلاهما يقول «القائمة أربعةَ عشرَ اسماً»).
- **الخاصّيّة المنتهَكة:** أسماء الفحوص المطلوبة في الـRuleset هي سطحُ إنفاذ **كلّ** البوّابات، ولم يكن يقيسها شيء. والانحراف صامت في الاتّجاهين: سياقٌ يسقط ⇒ بوّابتُه تحمرّ ولا تحجب (إرشاديّةٌ صامتة — صنفُ العطل الذي يطارده هذا المستودع كلّه)؛ واسمٌ يبقى بلا وظيفةٍ تُبلِّغه ⇒ كلّ PR يُعلَّق على فحصٍ لا يصل.
- **مقيسٌ لا مفترَض — والانحراف كان قائماً عند الكشف:** تشغيل 97630483312 على `77fc290e` يُظهر ruleset `main-protection` (active, `~DEFAULT_BRANCH`) يفرض **١٥** سياقاً، والشجرة تحمل **١٤** — ينقصها `Frontend E2E (Playwright · MapLibre/WebGL QA)`. أي أنّ رقم الشجرة كان بائتاً عن الواقع، ولا شيء يقيس الفرق.
- **العلاج (المُنجَز):** `docs/architecture/required_status_checks_contract.json` مصدراً واحداً يقرؤه القارئان معاً — الاختبار مقابلَ الشجرة، والحارس مقابلَ الإنفاذ الحيّ — بمساواة مجموعاتٍ في الاتّجاهين، وقراءةُ العقد فاشلة-مغلقة (غيابٌ/قائمة فارغة ⇒ خروج لا تخطٍّ).
- **مُكذَّب (4/4 بالزرع):** إسقاط اتّجاه النقص · إسقاط اتّجاه الزيادة · تحييد فرع «لا قاعدة إطلاقاً» · تسطيح سطر الخضرة.
- **حدّا صدق مقيسان أثناء البناء:** ① أوّل صياغة لاختبار «لا قاعدة» أثبتت رمز الخروج لا السبب، فنجت الطفرة (الحالة تسقط في فرع «سياقاتٌ ناقصة» فيبقى الرمز ١) — شُدَّت على الرسالة المميِّزة، وهو نفس درس `test_no_pull_request_rule_is_a_failure` حرفيّاً. ② وأوّل تشغيلٍ لتحقّقي من الطفرات أعطى «ناجيةً» كاذبة أعادت إنتاج `MUTATION-VERDICT-CONTRADICTS-ITS-OWN-DIAGNOSIS-01`: طفرتان متساويتا الطول (−٢٣ بايتاً كلٌّ) تقاسمتا `.pyc` لأنّ مِسباري لم يضع `PYTHONDONTWRITEBYTECODE` الذي يضعه المُشغِّل الحقيقيّ.
- **وهذا العقد شرطٌ مسبق لتقسيم مكنسة الطفرات** (`MUT-SWEEP-TIMEOUT-01`): بلا قياسِ سطح الإنفاذ، أيّ وظيفةٍ جديدة تُنقَل إليها المكنسة تصير إرشاديّةً صامتاً — وهو العائق الذي أجّل النقل منذ كُتِب.

## MUT-SWEEP-SHARDING-01 — تقسيم مكنسة الطفرات: الآلة والاتّحاد (فُتحت 2026-08-25 · **fixed جزئيّاً** — الآلة في `mut-shard-01`، والتفعيل موقوف على الـRuleset)

- **المصدر:** `MUT-SWEEP-TIMEOUT-01` (النقل مؤجَّل بشرطٍ حوكميّ) · قياس المالك على #920: *Unit Tests* ٢٨:٢١ وهي **٢٫٦×** التالية لها (`capability-registry` ١٠:٥٠) ⇒ عنق الزجاجة انتقل إليها.
- **الخاصّيّة المنتهَكة:** مكنسةٌ تسلسليّة داخل وظيفةٍ واحدة تجعل الزمن الحائطيّ مجموعَ كلّ الزرعات، والعتاد المتاح خاملٌ بجانبها.
- **المنجَز:** `--shard i/N` بتوزيع **حتميّ موزون بالطفرات** لا بتجزئة الاسم؛ و`--shard-inventory N` حارسَ اتّحادٍ فاشل-مغلق (مجموع الأنصبة = الكون، والحزمة الفارغة فشل).
- **قياسان صحّحا التصميم أثناء البناء:** ① تجزئة الاسم (`sha256 % N`) أعطت توزيعاً من **٣٣ إلى ١٥٢** طفرة (٤٫٦×) — والزمن الحائطيّ يحكمه الأثقل، فكان نصفُ مكسب التقسيم يضيع في حزمة؛ والتوزيع الموزون (الأثقل أوّلاً إلى أخفّ حزمة) أعطى **٩٠–٩٥** (١٫٠٦×). ② والتحقّق **بالتشغيل الحقيقيّ لا بالجرد**: حزمتان زرعتا ٩٣ طفرة كلٌّ فعلاً، مطابقاً لما أعلنه الجرد.
- **مُكذَّب:** ٨ اختبارات (اتّحاد على ٤ مقامات · اسمٌ في حزمة واحدة بالضبط · حتميّة عبر الاستدعاءات · حدّ التوازن ≤١٫٥ · حزمة فارغة · اتّحاد ناقص · ٨ صيغ `--shard` مشوّهة تفشل مغلقاً · غياب الراية = الكون).
- **حدُّ صدق — لماذا `fixed جزئيّاً`:** الآلة وحدها لا تُسرّع شيئاً. التفعيل يتطلّب وظيفة مصفوفة + إضافة أسماء الحزم الخمسة إلى الفحوص المطلوبة في الـRuleset (**بيد المالك حصراً**) — وقبله يبقى النقل ممنوعاً لأنّه يجعل المكنسة إرشاديّةً صامتاً. والتسلسل الآمن **خمس خطوات لا أربع**: عقدُ الفحوص (#922) ← الحزم تُبلِّغ والمكنسة باقية مؤقّتاً في *Unit Tests* ← ضبط الـRuleset ← التزامٌ واحد يحذف المكنسة ويضيف الأسماء للعقد معاً. وأيّ ترتيبٍ آخر إمّا يحجب كلّ شيء أو يُعلّق كلّ PR أبداً.
- **والتقدير المُصحَّح:** المكنسة **~١٨ دقيقة** لا ٢٥ (٦٤−٢٨=٣٦ وفّرها التضييق، والجزء غير القابل للشطب ~١٠) ⇒ التقسيم خمساً يُنزِل الوظيفة إلى **~١٠–١٢ دقيقة**. ورقم «~٢٫٨ث إقلاع pytest لكلّ زرعة» **غير مقيس ولا يُتبنّى**.

## MUT-SHARD-JOB-01 — تفعيل الحزم الخمس: التغطية لا تُنزع قبل أن يحجب البديل (فُتحت 2026-08-25 · **fixed جزئيّاً** — الوظيفة تعمل وتُبلِّغ، والحجب موقوف على الـRuleset)

- **المصدر:** `MUT-SWEEP-SHARDING-01` (الآلة هبطت في #923 بلا تفعيل) · [`ci.yml`](../../.github/workflows/ci.yml) (وظيفة `mutation-sweep`) · [`test_ci_pipeline_settings.py`](../../tests_v9/test_ci_pipeline_settings.py) (`test_the_sweep_stays_in_unit_tests_until_the_ruleset_is_set`).
- **الخاصّيّة المنتهَكة:** بين بناءِ الآلة وضبطِ الـRuleset تُفتَح **نافذةُ صمت**: من ينزع المكنسة من *Unit Tests* قبل أن تصير أسماءُ الحزم فحوصاً مطلوبة يترك ٣٢٠ طفرةً تُبلِّغ ولا تحجب — وهو صنف «حارسٌ كفّ عن الحجب بلا أن يحمرّ» نفسه الذي أجّل النقل من البداية.
- **المنجَز:** وظيفة `mutation-sweep` بمصفوفة خمس حزم (`fail-fast: false`، سقف ٣٠ دقيقة)، وأسماءُ الفحوص **حرفيّة** في `include` لا مُشتقّة من تعبير — لأنّ الـRuleset يُطابِق الاسمَ حرفيّاً فاسمٌ مبنيٌّ وقتَ التشغيل لا يُطابَق. وحارسُ الاتّحاد (`--shard-inventory 5`) يعمل في **كلّ حزمة قبل الزرع** لا في واحدة: حزمةٌ لا تُشغَّل أصلاً لا تفحص شيئاً، والفحصُ الواقع في أختها لا يشهد لها. والمكنسة الكاملة **تبقى** في *Unit Tests*.
- **مُكذَّب:** الحارسُ على التتابع ثنائيّ الاتّجاه — اسمُ حزمةٍ واحد في العقد يوجِب الخمسة **ويوجِب** النزع؛ وغيابُ الأسماء يوجِب البقاء. فلا نزعَ قبل إنفاذ ولا إنفاذَ جزئيّ. وزرعُ `run: echo skipped` في خطوة *Unit Tests* أسقط اختبارَين مستقلّين (`test_the_sweep_still_runs_inside_the_job_the_ruleset_actually_requires` و`test_the_sweep_stays_in_unit_tests_until_the_ruleset_is_set`) — فلا تغطيةَ يبتلعها جارٌ.
- **عطلٌ حقيقيّ كشفته هذه الشريحة:** مَرسى الطفرة في السجلّ كان `run: python … --run` وحده، فلمّا أضافت الوظيفةُ الجديدة سطراً يبدأ بالنصّ نفسه صار الزرعُ **غير محدَّد الموضع** وحمّر `guard_mutation_guard` محلّيّاً. ضُمَّ سطرُ اسمِ الخطوة إلى المَرسى فعاد فريداً. الدرس: مرسى الطفرة في YAML يجب أن يحمل هويّة الخطوة لا نصَّ أمرها.
- **حدُّ صدق:** التقسيم يقصّ الزمن الحائطيّ لا الكلفة — الكلفة الثابتة لكلّ زرعة تبقى موزّعةً على خمسة عمّال. ورقم «~٢٫٨ث لكلّ زرعة» يبقى **غير مقيس ولا يُتبنّى**. والمكسبُ الفعليّ لا يُعرَف قبل أن تعمل الحزم الخمس مرّةً في CI.
- **والقياس وقع (`7fadf14e`، #924):** ٣:٤٥ · ٤:٢٠ · ٤:٢٨ · ٤:٣٢ · **٥:٠٤** — الأثقلُ يحكم، مقابل *Unit Tests* **٣٤:٢٧** في الجولة نفسها، والخمسُ خضراء. والأسماء ظهرت في GitHub **حرفيّاً** كما كُتِبت، وهو التحقّق الذي كانت الخطوة ④ تنتظره. **وثلاثةُ تحفّظاتٍ على الرقم:** ① يشمل ~دقيقةَ إعدادٍ تتكرّر خمس مرّات — عتادٌ إضافيّ لا كفاءة. ② التوازنُ المُصمَّم بعدد الطفرات ١٫٠٦× أعطى زمناً **١٫٣٥×**، فكلفةُ الطفرة ليست موحّدة والوزنُ بالعدد تقريبٌ لا مطابقة. ③ و*Unit Tests* ٣٤:٢٧ مقابل ٢٨:٢١ المقيسة على #920 — **لا يُدّعى سببٌ** لفارق الستّ دقائق، لكنّه يعني أنّ مكسب ⑤ يُقاس من خطّ أساسٍ متحرّك فيُقرأ بعده لا قبله.
- **الباقي (بيد المالك حصراً):** إضافة `Mutation Sweep 1/5` … `Mutation Sweep 5/5` إلى الفحوص المطلوبة في الـRuleset، ثمّ التزامٌ واحد يحذف المكنسة من *Unit Tests* ويضيف الأسماء الخمسة إلى [`required_status_checks_contract.json`](../../docs/architecture/required_status_checks_contract.json) معاً — الاقترانُ مفروضٌ بالاختبار، لا بالانضباط.

## MUTATION-ANCHOR-MATCHES-A-COMMAND-NOT-A-STEP-01 — مَرسى الطفرة يُطابِق أمراً لا خطوة (فُتحت 2026-08-25 · **fixed** — المَرسى الوحيد المتأثّر صُحِّح)

- **المصدر:** [`guard_mutation_registry.json`](../../docs/architecture/guard_mutation_registry.json) (`behavioural/.github/workflows/ci.yml/mutations[1]`) · [`guard_mutation_guard.py:189`](../../scripts/ci/guard_mutation_guard.py) (`content.count(m["find"])`) · كُشِفت على فرع `mut-shard-job-01` قبل الدفع.
- **الخاصّيّة المنتهَكة:** الزرعُ `str.replace(find, replace, 1)` — فمَرسًى يتكرّر يزرع في **أوّل موضعٍ نصّاً** لا في الموضع المقصود. والحارس يفشل مغلقاً عند التكرار (وهو الصواب)، لكنّ العطل أنّ المَرسى كان هشّاً أصلاً.
- **كيف انكسر:** المَرسى `        run: python scripts/ci/guard_mutation_guard.py --run` كان فريداً حتّى أضافت وظيفةُ `mutation-sweep` سطر `--run --shard ${{ matrix.shard }}` — وهو يبدأ بالنصّ نفسه. فصار العدد ٢ وحمّر `guard_mutation_guard` محلّيّاً.
- **العلاج:** ضُمَّ سطرُ `- name:` إلى المَرسى، فصار يحمل **هويّة الخطوة** لا نصَّ أمرها.
- **مُكذَّب:** بعد التصحيح زُرِعت الطفرة فعلاً (لا جرداً): أسقطت `test_the_sweep_still_runs_inside_the_job_the_ruleset_actually_requires` **و**`test_the_sweep_stays_in_unit_tests_until_the_ruleset_is_set` — اختباران مستقلّان، فلا تغطيةَ يبتلعها جار.
- **حدُّ صدق:** صُحِّح المَرسى المتأثّر وحده. **لم يُمسَح** بقيّةُ مراسي الـYAML بحثاً عن هشاشةٍ مماثلة، ولا يوجد حارسٌ يمنع تسجيل مَرسًى يطابق أمراً بلا هويّة خطوة — يظهر العطلُ فقط حين يتكرّر فعلاً.

## CAPABILITY-IMPACT-DERIVED-FROM-A-STALE-STAGED-SNAPSHOT-01 — سطرُ القدرات مُشتقٌّ من لقطةٍ تَبيت (فُتحت 2026-08-25 · **fixed** — الإعلان صُحِّح، والدرس مُسجَّل)

- **المصدر:** [`pr_capability_impact_gate.py`](../../scripts/ci/pr_capability_impact_gate.py) (تشتقّ من `base..head`) · [`capability_impact.py`](../../scripts/ci/capability_impact.py) (تقبل أيّ قائمة مسارات) · وظيفة `capability-registry` على #924، حجبت بـ`missing_direct: ["IRR-009"]`.
- **الخاصّيّة المنتهَكة:** الأداةُ تقبل **أيّ** قائمة مسارات، فاشتقاقُها من `git diff --cached` لحظةَ الالتزام يُنتج إعلاناً صحيحاً **لتلك اللحظة** ثمّ يَبيت بأوّل تغيُّرٍ في الشجرة. البوّابةُ تشتقّ من `base..head` — وهو المرجع الوحيد.
- **كيف انكسر:** اشتُقّ الإعلانُ من ٢٠ قدرة، ثمّ لمست دورةُ التوليد `GUARD_CATALOGUE.md` و`log.md` فأضافتا `IRR-009` إلى المخروط. المُعلَن ٢٠ والمقيس ٢١.
- **العلاج:** أُعيد الاشتقاق من `origin/main...HEAD`، وتُحُقِّق محلّيّاً بالبوّابة نفسها (`decision: PASS`) قبل تعديل المتن، ثمّ `rerun_failed_jobs` — البوّابة تقرأ المتن حيّاً منذ #907.
- **حدُّ صدق:** لا شيفرةَ تغيّرت — العطلُ في طريقة استعمالي للأداة لا في الأداة. و**لا حارس** يمنع تكراره: البوّابة تمسكه في CI بعد جولةٍ كاملة، بينما `preflight` §١١ب يطبع الاقتراح الصحيح ولا يقارنه بما في المتن (المتن غير موجودٍ بعد وقتَ التشغيل المحلّيّ). المكسب الحقيقيّ هنا انضباطٌ لا آليّة.

## SERVICE-MAIN-NAME-COLLISION-REMEDY-UNADOPTED-01 — العلاجُ مكتوبٌ ويستعمله ملفٌّ واحد (فُتحت 2026-08-25 · **fixed** — بعد تصحيح القياس الأوّل)

> **تصحيحُ قياسٍ لي (2026-08-25، لاحقٌ على ما دُوِّن أدناه):** رقمُ «١ مقابل ١٦» صحيحٌ **كعدٍّ لمستعملي المساعِد**، لكنّي قرأتُه «١٦ غيرَ آمن» — وهو خلطٌ بين «لا يستعمل المساعِد» و«غيرُ محروس». التصنيف المقيس فعلاً على `5bb84cb4`:
> - **٥ آمنة** بإسقاطٍ وتحقّقٍ **داخليّين** (`test_auth_admin_stepup_mfa` · `test_auth_mfa_enforcement` · `test_soil_field_tenant_authz` · `test_video_processor_features_20260702` · `test_video_stream_tenant_authz`). وقد ظننتُ أنّ اختبار تفويض soil يقرأ وحدةَ auth — **مكذَّبٌ بالقياس**: يُسقط المُخبّأ ويؤكّد `ingest_reading`.
> - **١٠ في `services/weather-service/tests/`** تعمل في وظيفةٍ **معزولة** (`pytest tests` داخل الخدمة) فلا تُستورَد فيها وحدةُ خدمةٍ أخرى إطلاقاً — هشّةٌ مبدئيّاً، **غيرُ معطوبةٍ عمليّاً**.
> - **١ غيرُ آمن حقّاً**: `tests_v9/test_tenant_provisioning.py` — الوحيد في العمليّة المشتركة بلا إسقاط.
>
> **وقلقي الأكبر مكذَّبٌ أيضاً:** ادّعيتُ احتمالَ أنّ حرّاس تهيئة المستأجِر **لا تُقاس في CI**. القياس: `pydantic[email]` و`bcrypt` **مُعلَنتان** في `tests_v9/requirements-test.txt` (١٩ و٢٠)، فالملفّ **يعمل في CI ويمرّ** — لا يُتخطّى. الإخفاق المحلّيّ كان ثغرةَ بيئةٍ عندي (`pydantic[email]` غير مثبَّتة) جعلت `test_auth_*` تتخطّى فلا تخزّن وحدةَ auth، فتخزّن ملفّاتٌ لاحقة وحدةَ خدمتها.
>
> **الحكم الصادق:** لم يكن حارسٌ أمنيّ غيرَ مقيس. كان ملفٌّ صحيحاً **بالحظّ لا بالعقد** — صحّتُه رهنُ ترتيب الجمع وأيّ تبعيّةٍ اختياريّة صادف وجودُها.
>
> **العلاج (هذه الشريحة):** رُحِّل الملفّ إلى `load_service_main`. ومُكذَّب: تلويثٌ متعمَّد (وحدةُ soil مخزَّنةً باسم `main` قبل الجمع) ⇒ ١١/١١ تمرّ؛ ونزعُ الإسقاط من المساعِد ⇒ **يُقتَل**. وأُضيف حارسُ منعٍ يرفض أيّ استيرادٍ عارٍ جديد في `tests_v9`، بقائمة استثناءٍ **مُعلَنة** تُلزَم بإثبات إسقاطها.
>
> **وعطلان في اختباراتي أنا، مسكهما التكذيب لا المراجعة:** ① تأكيدٌ على «تصادم أسماء» لا يميّز فحصَ المسار من فحص السمات (`COVERAGE-MASKED-BY-A-NEIGHBOURING-GUARD-01`) — صُحّح بطلب سمةٍ **يملكها** الدخيل فلا يبقى إلّا المسار. ② وحارسُ المنع كان يُعفي أيّ ملفّ **يذكر** `load_service_main` ولو في تعليق — فأعفى تعليقي الملفَّ من نفسه؛ صُحّح إلى **استدعاء** لا ذِكر.
>
> **وحدُّ صدقٍ باقٍ:** العشرة في خدمة الطقس **لم تُرحَّل** — عزلُ وظيفتها يحميها اليوم، ولا حارسَ يمنع ضمَّها لاحقاً إلى عمليّةٍ مشتركة. ولا يمتدّ حارسُ المنع خارج `tests_v9/`.

**(النصّ الأصليّ كما كُتِب أوّلاً — يُبقى للمقارنة لا للاعتماد):**

- **المصدر:** [`tests_v9/service_module.py`](../../tests_v9/service_module.py) (`load_service_main`، نمط #570) · [`tests_v9/test_tenant_provisioning.py:31-40`](../../tests_v9/test_tenant_provisioning.py) (`importlib.import_module("main")` بتخطٍّ على `ImportError` وحده) · تشغيلُ `pytest -m unit` محلّيّاً على `7fadf14e`: **٤ إخفاقات**.
- **الخاصّيّة المنتهَكة:** ٢٤ خدمةً تحمل `main.py`، و`sys.modules` مفتاحه **الاسم لا المسار**. فإن خزّن اختبارٌ أسبقُ وحدةَ `main` لخدمةٍ أخرى، لا يقع `ImportError` أصلاً ⇒ **لا تخطّي**، ويقيس الاختبارُ ملفّاً غير الذي يدّعيه.
- **النصّ المقيس:** `AttributeError: module 'main' has no attribute 'TenantProvisionRequest'` و`… no attribute 'require_role'`.
- **والخطرُ ليس هذا الاتّجاه:** الوحدةُ الخاطئة هنا **افتقدت** السمة فظهر الإخفاق. ولو حملت خدمتان سمةً متشابهة الاسم لمرّ الاختبارُ **أخضرَ وهو يقرأ الملفّ الخطأ** — وهو ما يقوله توثيق العلاج حرفيّاً: «الخطر ليس فشلاً بل **نجاحاً كاذباً**». ولهذا يُثبِت `load_service_main` هويّةَ الوحدة **بمسارها** (`is_relative_to`) لا بسماتها.
- **المقيس على `786e5d03`:** يستعمل العلاجَ **ملفٌّ واحد** (`test_unit_environment_completeness.py`) · ويستورد `main` عارياً بدونه **١٦** ملفّاً (٦ في `tests_v9/`، ١٠ في `services/weather-service/tests/`).
- **لماذا `open` لا `fixed`:** خارجَ نطاق شريحة التقسيم، ولم تُقحَم فيها. والعلاجُ يلزمه ترحيلُ الستّة عشر + حارسٌ يمنع عودةَ الاستيراد العاري.
- **وشرطٌ يسبق الترحيل:** لم يُقَس بعدُ هل الأربعةُ في CI **تمرّ** أم **تُتخطّى**. الفرقُ جوهريّ: التخطّي يعني أنّ حرّاس تهيئة المستأجِر (دور `owner` حصراً · `require_role("admin")` · منعُ العميل من اختيار `role`/`password`/`tenant_id`) **لا تُقاس في CI أصلاً**، وخُضرتها صمت. فقد يُحمِّر الترحيلُ اختباراتٍ خضراء — وذلك **كشفٌ لا انحدار**، ويجب أن يُقرأ كذلك سلفاً.
- **حدُّ صدق:** الأربعةُ لا تحجب CI اليوم (*Unit Tests* خضراء على #923 و#924)، فالعطلُ **كامنٌ لا حاجب** — وهذا بالضبط ما يجعله جديراً بالتسجيل لا بالتجاهل.

## REGEN-RESTAMPS-UNCONDITIONALLY-AND-TRIPS-THE-REPORT-ONLY-GUARD-01 — ختمٌ يتجدّد بلا قياسٍ تغيّر (فُتحت 2026-08-25 · **open** — مقيسة، غير مُصلَحة)

- **المصدر:** [`verify_all_generated.py`](../../scripts/ci/verify_all_generated.py) `--fix` · [`no_report_only_change_guard.py`](../../scripts/ci/no_report_only_change_guard.py) · قِيست على #925 (`d358bf11`) حين حجب الحارسُ شريحةَ صيانةِ دماغٍ خالصة.
- **الخاصّيّة المنتهَكة:** `--fix` يُجدّد `measured_on` في المصنوعات **بلا شرط** — حتّى حين لا يتغيّر شيءٌ مقيس. فينتج فرقٌ محتواه **ختمٌ فقط**.
- **والتصادم مقيس لا مُستنتَج:** اثنان من تلك المصنوعات «تقريريّان» بمعيار الحارس (`generated_write_targets.json` باسمٍ يحوي `generated` · `source_text_assertion_inventory.json` باسمٍ يحوي `INVENTORY`). وشريحةُ الدماغ الخالصة لا تحمل شيئاً **جوهريّاً** بمعيار `is_substantive` — إذ `sahool-brain/` مُستثنًى من `is_report_like` **ولم يُدرَج** في `SUBSTANTIVE_PREFIXES`. فالنتيجة `report_like and not substantive` ⇒ حجب.
- **والحارسُ يُعلن نيّةً لا تُحقّقها آليّتُه:** تعليقُه يقول صراحةً إنّ استثناء `sahool-brain/` «يُتيح لصيانة الدماغ المفروضة أن تهبط بلا اختلاق تغييرٍ برمجيّ لا صلة له» — لكنّ دورةَ التوليد **المفروضة هي الأخرى** تجرّ معها ختمين تقريريّين، فتُبطِل الاستثناء عمليّاً.
- **المخرج المقيس (وهو ما فُعِل):** إعادةُ **مجموعة المصنوعات كاملةً** إلى حالة `main` — فيصير الفرقُ دماغاً خالصاً. النتيجة: `no_report_only_change_guard_ok` **و**`verify_all_generated --check` rc=0 (٥٦٦٠ بصمة). أي أنّ الختم المُتجدِّد لم يكن مطلوباً أصلاً.
- **وتصحيحُ فرضيّةٍ لي أثناء القياس:** ظننتُ الحارسَين **في تصادمٍ بنيويّ** لا مخرجَ منه، لأنّ إرجاع ملفَّين فقط أعطى `rc=1`. القياسُ كذّب الظنّ: السببُ كان `checksum mismatch` من إرجاعٍ **جزئيّ** لا رفضاً للختم البائت. الإرجاعُ الكامل يمرّ من البوّابتين معاً.
- **لماذا `open`:** المخرجُ يدويٌّ ويعتمد على انتباه الكاتب. ولا حارسَ يمنع تكراره، ولا آليّةَ تجعل `--fix` يمتنع عن الختم حين لا يتغيّر المقيس. العلاجُ المُقترَح: إمّا ألّا يُجدَّد `measured_on` إن تطابق المحتوى المُعاد اشتقاقه، وإمّا إدراج `sahool-brain/` في `SUBSTANTIVE_PREFIXES` — والأوّل أدقّ لأنّه يعالج السبب لا العرَض.
- **حدُّ صدق:** لم يُقَس كم مصنوعةً أخرى تُختَم بلا داعٍ، ولا كم شريحةً تاريخيّة حملت ختماً مجّانيّاً. المقيس حالةٌ واحدة — هذه.

## MUTATION-PROVES-THE-TEST-NOT-THE-NEIGHBOURS-01 — الطفرةُ تشهد للاختبار لا للجوار (فُتحت 2026-08-25 · **open** — مقيسة، بلا آليّة)

- **المصدر:** #927 · وظيفة CI `97763140295` على `2ad6b8e1` · `services/auth/mfa_runtime.py:20` (`import main` داخل `_main()`) · `tests_v9/test_auth_admin_stepup_mfa.py:46`.
- **الخاصّيّة المنتهَكة:** التكذيبُ بالطفرة يُجيب سؤالاً واحداً: **هل يمسك هذا الاختبارُ العطلَ الذي صُمِّم له؟** ولا يُجيب سؤالاً ثانياً مختلفاً: **هل يمسّ تغييري اختباراتٍ أخرى؟** وكنتُ أعامِلهما كسؤالٍ واحد، فأُعلن «مُكذَّب ٤/٤» وأقرؤها ضماناً للسلامة.
- **الحادثة المقيسة:** شريحةٌ رحّلت ملفّاً إلى `load_service_main` — ٤/٤ طفرات مقتولة، والملفّان معاً يمرّان. ثمّ حمّرت CI اختباراً في **ملفٍّ لم تمسّه الشريحة** (`test_correct_code_is_true`): الإسقاطُ وقتَ الجمع شطر وحدةَ auth كائنَين، فوقع الترقيع على الأوّل والقراءةُ على الثاني.
- **ولماذا لم يكشفه تكذيبي:** شغّلتُ الملفَّين المعنيَّين معاً فمرّا — الطفرةُ تقيس الملفَّ المستهدَف، والضحيّةُ كانت ثالثاً. كشفه **تشغيلُ الجناح كاملاً** لا غير.
- **العلاج المُتّبَع (انضباطٌ لا آليّة):** كلُّ تغييرٍ يمسّ حالةً عالميّة مشتركة (`sys.path` · `sys.modules` · مُتغيّرات بيئة · مُخبّآت وحدات) يُشغَّل عليه **الجناح كاملاً محلّيّاً** قبل الدفع، لا التكذيبُ المُوجَّه وحده.
- **لماذا `open`:** لا حارسَ يفرض ذلك، ولا معيارَ آليّ يُصنّف «تغييراً يمسّ حالةً عالميّة». ولم يُقَس كم شريحةً سابقة دُفِعت بتكذيبٍ موجَّه وحده.

## CI-EVIDENCE-CAN-BE-ABSENT-WHILE-LOOKING-PRESENT-01 — شهادةٌ غائبة تبدو حاضرة (فُتحت 2026-08-25 · **open** — حالتان مقيستان)

- **المصدر:** تشغيلات #927: `32835399486` (فشل) · `32840092421` (**ملغاة**) · `32841607576` (نجاح) · وإشعارات `check_suite.completed` على `47e5f596` و`8ff58dba`.
- **الخاصّيّة المنتهَكة:** «لا شيءَ يُخفِق» ≠ «كلُّ شيءٍ نجح». وبينهما حالةٌ ثالثة — **الملغاة** — تُقرأ خضراءَ إن لم يُنظَر إليها بالاسم.
- **الحالة ①:** إشعار `check_suite.completed` وصل على `47e5f596` نصُّه «لا شيء يعمل أو يُخفِق». وكان **صادقاً حرفيّاً**: `Unit Tests` كانت `cancelled` — لا عاملةً ولا مُخفِقة. ونصُّ الإشعار نفسه يستثني الملغاة صراحةً. لو قُرِئ على ظاهره لأُعلِن «الإصلاح مُثبَتٌ في CI» وهو غير مُثبَت. مُسِك بجرد الوظائف: `Counter({('completed','success'): 20, ('completed','cancelled'): 1})`.
- **الحالة ② — والسبب فِعلي:** الدفعُ القسريّ **يُلغي التشغيلة الجارية** لنفس الفرع. وكنتُ قد أعلنتُ أنّي أنتظر تلك التشغيلة **لأنّها الشاهد على إصلاح انحدار MFA**، ثمّ أعدتُ الأساس ودفعتُ قسريّاً — فأتلفتُ الشاهدَ الذي أنتظره بيدي، ولم أنتبه إلّا عند الجرد.
- **القاعدة المُستخلَصة:** الحكمُ الوحيد جردُ الوظائف على **الرأس الحيّ**، وشرطُه ثلاثيّ: `status == completed` **و** `conclusion in (success, skipped)` **و** لا وظيفةَ خارج ذلك. و«لا إخفاق» ليست شرطاً. وترتيبُ العمل: **انتظرِ الشاهد ثمّ أعِد الأساس** — لا العكس.
- **لماذا `open`:** لا آليّةَ تمنع الدفع القسريّ أثناء تشغيلةٍ حاسمة، ولا فحصَ يُنبِّه أنّ شهادةً كنتَ تنتظرها أُتلِفت. والانضباطُ وحده يحرسها.

## CALLER-KEPT-THE-OLD-SCALAR-CONTRACT-AFTER-THE-CALLEE-RETURNED-A-TUPLE-01 — عقدٌ تغيّر ونداءٌ لم يتغيّر (فُتحت 2026-08-25 · **fixed** — الأربعة مُصلَحة ومحروسة)

- **المصدر:** `services/weather-service/weather_runtime.py:414` · `:482` · `:512` · `:539` · `services/weather-service/cache.py:46` · `017c035b` (الثلاثيّة) · `b614b3ee` و`ca91905f` (المُعالِجات، 2026-07-10) · `services/weather-service/tests/test_crop_stress_endpoints.py`.
- **الخاصّيّة المنتهَكة:** تغييرُ عقد المُستدعَى لا يُحمِّر المُستدعِيَ في بايثون. `cache.get` صارت تُعيد `(value, state, age)`، والنداءُ القديم `series = cache_get(key)` بقي **يُترجَم بلا خطأ** ويُسنِد ثلاثيّةً إلى اسمٍ يعني قيمة. فالفحصُ التالي `if series is None` صار **ميّتاً بالبناء** لا خاطئاً بالمنطق.
- **الحادثة المقيسة:** أربعُ نقاطٍ إنتاجيّة — `/v1/weather/thermal-stress` و`/lodging-risk` و`/pollination-risk` و`/chill-accumulation` — لم تُعِد `200` **قطّ** منذ يوم كتابتها. مقيسٌ بالتنفيذ لا بالقراءة: `cache_get('probe:unused') -> (None, 'miss', None)` ثمّ `'tuple' object has no attribute 'get'` من الأربعة جميعاً.
- **ولماذا نجا شهراً ونصفاً:** الموضعان الصحيحان في **الملفّ نفسه** (`:153` · `:292`) يفكّكان الثلاثيّة — فالاصطلاح الصحيح كان أمام كاتب الأربعة ولم يُتَّبع، ولا حارسَ يقارن اصطلاحَي نداءٍ لدالّةٍ واحدة. والاختباراتُ القائمة تستورد النوى النقيّة، فمرّت خضراءَ على منطقٍ صحيحٍ خلف مُعالِجٍ ميّت.
- **العلاج:** `series, state, _age = cache_get(key)` ثمّ `if series is None or state != "fresh":` في الأربعة — نفس اصطلاح `:153`. **ولم يُضَف تراجعٌ إلى المُخبّأ البائت عند فشل الجلب**: `503` باقية كما كانت عمداً، فذاك قرارُ تصميمٍ لا إصلاحُ عطل، وخلطُه هنا كان يُخفي حدود ما قِيس.
- **التكذيب:** ١٢/١٢ مقتولة **في الموضع** (٤ نقاط × ٣ طفرات): عودةُ الاصطلاح القديم · إسقاطُ شرط المخبّأ · `if series is None` وحدها. والثالثةُ هي مبرّرُ فرع «البائت» الذي كان سيبدو زائداً بلا قياس.
- **لماذا `fixed` لا `verified`:** مُثبَتٌ بـ`TestClient` وجلبٍ مُستبدَل، لا بنداءٍ حيٍّ إلى خدمةٍ مرفوعة أمام Open-Meteo. **ولا سلطةَ تحرّكت.**

## SERVICE-ROUTES-WITNESSED-ONLY-AT-THE-PURE-CORE-01 — النواةُ محروسة والمسارُ مكشوف (فُتحت 2026-08-25 · **open** — مقيسة، بلا آليّة)

- **المصدر:** `services/weather-service/tests/test_crop_stress_products.py` (يستورد `compute_lodging_risk` وأختَيها مباشرةً) · `services/weather-service/main.py` (٢٧ مساراً) · وظيفة CI `Weather Service Unit Tests`.
- **الخاصّيّة المنتهَكة:** اختبارُ النواة يشهد للحساب، ولا يشهد لشيءٍ ممّا بين الطلب والنواة: المخبّأ · الجلب · تفكيك العقود · تحويل المُعاملات. وهو **بالضبط** حيث وقع `CALLER-KEPT-THE-OLD-SCALAR-CONTRACT-…-01`.
- **القياس (2026-08-25):** ٢٧ مساراً مُسجَّلاً في `main.py`؛ **١٠ لم يُسمِّها أيُّ اختبارٍ** في جناح الخدمة قبل هذه الشريحة، **٦ بعدها**: `/healthz` · `/health` · `POST /v1/weather/agro/etc/hourly` · `POST /v1/weather/agro/canonical-state` · `POST /v1/weather/agro/state-report` · `GET /v1/weather/cache-stats`. (القياسُ بمطابقة بادئة المسار قبل `{`، فيحتسب المُبنيّة بـf-string.)
- **وحدُّ صدقٍ على القياس نفسه:** «يُسمّيه اختبار» أضعفُ من «يُختبَر سلوكُه» — ورودُ المسار نصّاً لا يعني تأكيداً على جوابه. فالرقم سقفٌ متفائل لا أرضيّة.
- **لماذا `open`:** لا حارسَ يفرض أن يُسمّى كلُّ مسارٍ مُسجَّل، ولا راتشِتَ يمنع مساراً جديداً بلا شاهد. الأربعةُ أُغلِقت لأنّها حملت العطل، لا لأنّ آليّةً أغلقتها.
- **العلاجُ المُقترَح المتناسب:** راتشِتٌ لا يصعد على عدد المسارات غير المسمّاة (٦ سقفاً اليوم)، على غرار `visual_fixme_baseline_guard` — لا حجبٌ فوريّ يُوقِف الخدمة على دَينٍ موروث.
## TYPED-CONTRACT-FORBIDS-ABSENCE-SO-THE-EDGE-INVENTS-ZERO-01 — عقدٌ يمنع الغياب فتختلقه الحافّة صفراً (فُتحت 2026-08-25 · **open** — مقيسة، خارج نطاق H1)

- **المصدر:** `services/sahool-platform/api/connectors/openmeteo.py:168-169` (`temp_max_c: float` · `temp_min_c: float` — **غير اختياريَّين**) و`:218-219` (`_daily_at(d, "temperature_2m_max", i, 0)`).
- **كيف انكشفت:** بتدقيق المستهلكين الذي فرضه المالك شرطاً لـH1 — لا بمراجعةٍ للملفّ. البحثُ عن مستهلكي الحرارة اليوميّة أخرج **مُنتِجاً ثانياً** لم تذكره مراجعةُ الطقس ولا وثيقةُ البحث.
- **الخاصّيّة المنتهَكة:** نفس كذبة `WEATHER-NORMALIZER-ZERO-COERCION` (غياب ⇒ `0.0°C`) في مسارٍ منفصل تماماً: موصِّل المنصّة لا مُطبِّع خدمة الطقس.
- **وآليّتها مختلفة — وهذا ما يجعلها شريحةً أخرى لا امتداداً:** تصفيرُ خدمة الطقس كان سهواً؛ وهذا **مفروضٌ بالنوع**. `_daily_at` يشرح في صدره أنّ الوصول المباشر «كان يمرّر `None` لحقل `float`» — أي الصفرُ اختيرَ عمداً لحماية عقدٍ لا يقبل الغياب. فالإصلاح يبدأ من `float | None` في `DailyForecast`، لا من الحافّة.
- **نطاق الانفجار (مقيس):** خمسة مواضع تقرأ الحقلين بوصفهما `float` مضموناً — `connectors/openmeteo.py:703` (`forecast.temp_max_c > 35`) · `routers/field_ai_context.py:624` · `routers/seasons.py:239-240` · `routers/etc_dual.py:214-215` و`:304-305`. ثلاثةٌ منها تُمرِّر إلى `core/engines/fao56.py:55-56` — وهو أيضاً `float` غير اختياريّ.
- **لماذا لم تُضَمّ إلى H1:** أمرُ المالك حدّد `normalize_daily` ونطاقَ الحرارتين فيه. وضمُّ عقدٍ مطبوع بخمسة مستهلكين يُبدّل حجم الشريحة ويخلط تكذيبَين — نفس مبدأ إبقاء P3 خارج P1.
- **لماذا `open`:** لا حارسَ يمنع مُنتِجاً ثالثاً من اختراع صفرٍ للحرارة، ولا فحصَ يربط «حقل حرارة» بـ«يقبل الغياب». والمقيس أنّ مُنتِجَين بُنِيا مستقلَّين بالكذبة نفسها.

## CACHE-AGE-FABRICATED-AS-ZERO-AND-COMPARED-ACROSS-PROCESSES-01 — عمرٌ لم يُحسَب قطّ (فُتحت 2026-08-25 · **fixed** — مسار Redis، والذاكرة لم تُمَسّ)

- **المصدر:** `services/weather-service/cache.py:53` (`int(payload.get("age_hint_s", 0))`) · `:79` (`"age_hint_s": 0` تُكتب حرفيّاً) · `:57` (`monotonic() - stored_monotonic` عبر عمليّتين) · `:58` (`max(age, int(TTL_S))`) · وناشرو الرقم في `weather_runtime.py:157/334/918/973`.
- **الخاصّيّة المنتهَكة:** ما يُبلَّغ «عمراً» يجب أن يكون **قياساً**. وهنا لم يكن قياساً في أيٍّ من الفرعَين: الطازجُ ثابتٌ مكتوبٌ مسبقاً، والبائتُ فرقٌ بين مبدأَين لا بين لحظتين.
- **ولماذا الصفرُ أخطرُ من رقمٍ خاطئ:** المستهلِك يقرأ `cache_age_s` ليقرّر أيثق بالقراءة أم يُجدّدها. و`0` تعني «طازجةٌ تماماً» — **أقوى ما يمكن قوله**. فالعطل لم يكن رقماً مغلوطاً بل أشدّ الأرقام طمأنةً يُقال في أسوأ الحالات.
- **والمعيار يسمّيه:** PEP 418 ينصّ أنّ نقطة مرجعيّة `monotonic` غير معرَّفة وأنّ القيمة لا تعني شيئاً خارج العمليّة. فتخزينُها في Redis **مشترَك** خطأٌ بنصّ المواصفة لا باجتهاد.
- **العلاج:** `_age_from_ttl(client, key, ttl_total)` — `العمر = المدّة الكاملة − TTL(key)`. العدُّ داخل Redis فلا ساعةَ تُشارَك. و`None` عند تعذّر العدّ أو عند حارسَي `-1`/`-2`. وقصٌّ إلى صفر عند تجاوز المتبقّي المدّةَ الكاملة (يقع حين تُخفَّض `TTL_S` بعد كتابة مدخلة) — لأنّ عمراً سالباً يدّعي كتابةً في المستقبل.
- **وأُسقِط `max(age, TTL_S)`:** كان يرفع رقماً بلا معنى إلى حدٍّ معقول المظهر. والعدُّ الصحيح يُخرِج عمرَ البائت أكبر من `TTL_S` **بطبيعته** — لأنّ المفتاح الطازج انتهى قبل بلوغ ذلك الفرع.
- **وحُذِف ما لم يعد يُقرأ:** `stored_monotonic` و`age_hint_s` من الحمولة المخزَّنة. إبقاؤهما دَينٌ صامت يُغري بالعودة إليهما، وحذفُهما محروسٌ باختبار.
- **مسارُ الذاكرة لم يُمَسّ عمداً:** `monotonic` صحيحةٌ **داخل** العمليّة، و`_CACHE` لا يُشارَك أصلاً. PEP 418 يمنع المشاركة لا القياس. ومحروسٌ باختبارٍ يقتل تصفيرَه.
- **التكذيب: ٧/٧** — عودةُ الصفر المُلفَّق · المجهولُ يصير صفراً · حارسا `-1`/`-2` يُقرآن ثوانيَ · عمرٌ سالب يُنشَر · عودةُ `max(age, TTL_S)` · عودةُ الساعة المحلّيّة إلى الحمولة · تصفيرُ مسار الذاكرة.
- **لماذا `fixed` لا `verified`:** الشاهدُ Redis وهميٌّ يعرف `TTL`. والاختبارُ الحيّ (`test_weather_cache_live_redis_roundtrip`) مشروطٌ بمتغيّر بيئة **غير مضبوط في CI** فيُتخطّى — أي لا خادمَ حقيقيّاً شهد. **ولم يُقَس الأثرُ الزمنيّ لنداء `TTL` الإضافيّ.**

## CONFIDENCE-FABRICATED-FROM-AN-INVENTED-DENOMINATOR-01 — ثقةٌ بلا دليل، ومقامٌ يساوي بسطَه (فُتحت 2026-08-25 · **fixed** — الصقيع والحرارة؛ الباقي مُعلَن)

- **المصدر:** `core/weather_signals.py:38` (`h = max(1, scores.hours_evaluated)`) · `core/weather_overlay_pipeline.py:84` (`hours_evaluated=max(1, heat, frost)`) · `core/weather_overlay.py:82` (`compute_scores([])` ⇒ `trafficability_score=0.0`) · والمستهلِك `core/decision_playbook.py:117`.
- **الخاصّيّة المنتهَكة:** الثقةُ يجب أن تعكس **الدليل**: حجمَ العيّنة، وتماسكَها، ووجودَها أصلاً. ولم تكن تعكس أيّاً من الثلاثة.
- **① صفر مشاهدة ⇒ ثقةٌ كاملة:** التراكبُ الفارغ يُرجِع `trafficability_score=0.0`، و0.0 دون عتبة `_TRAFFIC_POOR=30`، فتُطلَق «التربةُ غير سالكة» بثقة `1.0 − 0/100 = 1.0`. والدرجةُ الصفريّة هناك تعني «لا شيء رُصِد» لا «رُصِد صفر». **لم تذكره مراجعةُ الطقس ولا وثيقةُ البحث** — كُشِف بتنفيذ `generate_signals(compute_scores([]))`.
- **② حجمُ العيّنة غيرُ مرئيّ:** ساعةُ صقيعٍ من ساعة، وأربعٌ وعشرون من أربعٍ وعشرين — نسبتُهما 1.0 معاً.
- **③ المقامُ مُخترَع، وهذا أخطرُها لأنّه المسارُ الطبيعيّ:** سجلُّ التراكب لا يُخزّن `hours_evaluated`، فكان `build_signal_records` يشتقّه `max(1, heat, frost)`. والاشتقاقُ **يُساوي المقامَ بالبسط** حين يكون الصقيعُ أكبر — فالنسبة 1.0 مهما اتّسعت النافذة. **مقيس: ٦ من ٢٤ ⇒ كانت `1.0`، صارت `0.135`.** وتعليقُ الشيفرة نفسُه ادّعى أنّه «لا يؤثّر على وجود الإشارة» — وهو صادقٌ حرفيّاً وأخفى أنّه يُحدّد **الثقة** كلَّها.
- **④ والمقامُ المحمولُ نفسُه لم يكن وحدةَ القياس الصحيحة** — كشفه تدقيقُ المصدر الذي فرضه المالك **قبل** اختيار الإصلاح، بعد أن كان الالتزامُ الأوّل قد بُني على `hours_evaluated`. فالأخيرُ يعدّ كلّ ساعةٍ **حاضرة**، بينما `frost_risk_hours` يشترط `temp_min_c is not None`. فالساعةُ الحاضرة بلا `temp_min` تدخل المقامَ ولا يمكنها دخولُ البسط **أبداً**: بسطٌ ومقامٌ من فضاءَي ملاحظةٍ مختلفَين. **مقيس:** ٢٤ حاضرة · ١٢ بلا `temp_min` · ٦ صقيع ⇒ `0.135` بدل `0.286` — بخسٌ بالضعف، باتّجاهٍ معاكسٍ لعطل الاختراع ونفسِ الخطأ.
- **العلاج:** حارسُ اللادليل (`hours_evaluated <= 0` ⇒ لا إشارة) · **مقامان مخصوصان** (`frost_evaluable_hours` = ساعاتُ `temp_min_c` المتاحة · `heat_evaluable_hours` = ساعاتُ `temp_max_c`) يُحسَبان في `compute_scores` ويُحمَلان في سجلّ التراكب · و`_wilson_lower_bound` بـz=1.645 **فوقهما** لا فوق الحضور. وغيابُ المقام ⇒ لا إشارة، لا اختراع. وحقلان صريحان لا تجريدٌ عامّ.
- **وقاعدةٌ صارت صريحة:** Wilson يُحسِّن تقديرَ اللايقين ولا يُصلِح مقاماً خاطئاً. فلا يُستدعى قبل إثبات أنّ `(k, n)` من فضاءٍ واحد.
- **ولماذا Wilson لا Wald:** عند `p̂ = 1` يعطي Wald فترةً طولُها صفر — أي يقينٌ كامل من أيّ عيّنة. وWilson يبقى صالحاً عند الأطراف وهو المعياريّ لنسبةٍ من عيّنة صغيرة.
- **التكذيب: ٨/٨** — نزعُ حارس اللادليل · عودةُ النسبة الخام · قصُّ المتناقض بدل رفضه · عودةُ اختراع المقام · عدمُ حمله في السجلّ · اختراعُه عند غيابه · حجبُ أساس الرقم · وعودةُ القسمة الخام في المُولِّد.
- **واختبارٌ قائم كان يحرس الكذبة:** `test_confidence_clamped` يؤكّد أنّ `50/24` «تُقَصّ إلى 1.0». استُبدِل بنقيضه — والاستبدالُ جزءٌ من الإصلاح لا أثرٌ جانبيّ له.
- **حدُّ صدق — ما لم يُمَسّ:** ثقةُ `spray_window_open` و`disease_risk_high` و`trafficability_poor` ما زالت **الدرجةَ نفسَها** (خلطُ المقدار بالثقة). عدّاداتُها غيرُ قابلة للاسترداد من كسرٍ مُقرَّب بأربع منازل، فتصحيحُها يحتاج حملَ بسطِها كما حُمِل المقامُ هنا — شريحةٌ أخرى.

## GUARD-ALTER-ADD-SYNTAX-BLINDSPOT-01 — نحوٌ واحد من نحوٍ كثير (سُجِّلت 2026-08-25 · **fixed** — مُتحقَّقٌ منها على الشجرة)

- **المصدر:** `scripts/ci/snapshot_eligibility_separation_guard.py` · `docs/architecture/guard_mutation_registry.json` · وثيقةُ تحكيم حزمة Sigstore (2026-08-12).
- **لماذا تُسجَّل الآن:** السجلُّ **لم يكن يحمل المعرِّف إطلاقاً** — لا فتحاً ولا إغلاقاً. فوثيقةُ التحكيم توثّق علاجاً لفجوةٍ لا يعرفها السجلّ، وهو أسوأ من فجوةٍ مفتوحة: لا أثرَ لها يُراجَع.
- **الخاصّيّة المنتهَكة:** حارسٌ يفهم صياغةً واحدة من نحوٍ له صياغاتٌ كثيرة يُبلِّغ «نظيف» عن مِلفٍّ لم يقرأه. و`ALTER TABLE` في PostgreSQL يقبل بادئاتٍ مشروعةً متعدّدة ومعرّفاتٍ مُقتبَسة.
- **التحقّق (على الشجرة لا من الوثيقة):** السجلُّ يحمل **٩ طفرات** لهذا الحارس، وأسماءُ اختباراتها تُغطّي المدى الذي وصفته الوثيقة: `add_column_if_not_exists` · `every_legal_alter_prefix` · `quoted_identifier` · `quoted_column_inside_create_table` · `the_word_column_is_never_captured` · `losing_its_subject_is_a_failure_not_a_pass`.
- **وفارقٌ مقيس:** الوثيقةُ قالت **٨** والمقيسُ **٩** — طفرةٌ أُضيفت بعد 2026-08-12. الوثائقُ تبيت والشجرةُ لا.

## LIVE-PG-PSQL-ABSENCE-COLLECTION-ERROR-01 — انهيارُ جمعٍ يُقرأ إخفاقَ اختبار (سُجِّلت 2026-08-25 · **fixed** — مُتحقَّقٌ منها على الشجرة)

- **المصدر:** `tests_v9/test_live_pg_fake_connection_debt.py:53` و`:89` · `services/decision-service/tests/test_eligibility_assessment_live_pg.py:280` · وثيقةُ التحكيم نفسها.
- **الخاصّيّة المنتهَكة:** غيابُ أداةٍ خارجيّة يجب أن يُنتِج **تخطّياً مُعلَناً**، لا خطأَ استيرادٍ يُسقِط الجمع. وانهيارُ المُشغِّل يُقرأ إخفاقَ اختبار — وهو نفسُ صنف `RUNNER-CRASH-READS-AS-A-TEST-FAILURE-…-01` المسجَّل هنا سلفاً.
- **التحقّق:** `shutil.which("psql")` يسبق أيّ استدعاءٍ للأداة في الموضعَين، واختبارُ الانحدار المُسمّى في الوثيقة (`test_the_module_imports_even_without_a_psql_client`) قائمٌ فعلاً في الشجرة.
- **ولماذا تُسجَّل الآن:** لنفس سبب أختها — المعرِّفُ غائبٌ عن السجلّ منذ 2026-08-12.

## LESSON-CONCURRENT-PREFLIGHT-CONTAMINATION-01 — تشغيلتان متزامنتان تُفسِدان قياسَ بعضهما (سُجِّلت 2026-08-25 · **open** — مقيسة، بلا آليّة)

- **المصدر:** `tests_v9/test_api_versioning_policy_guard.py:44-62` (المِسبار) · `scripts/ci/route_mount_contract_guard.py:107-121` (العدُّ بمسح القرص) · حادثةُ شريحة H1.
- **الحادثة المقيسة:** أربعةُ إخفاقات ظهرت على شريحة H1 ونسبتُها إليها. والحقيقة أنّ ثلاثتها من تشغيلتَي `preflight` متزامنتَين شغّلتُهما أنا — أطلقتُ الثانية قبل أن يصل إشعارُ انتهاء الأولى.
- **الشاهد ثلاثيّ:** `main` منفرداً ٥٨١١/٠ · الفرع منفرداً ٥٨١١/٠ · `preflight` منفردة `إخفاقات: 0` — بينما المتزامنة أسقطت `route_mount`. والفرعُ لا يضيف اختباراً واحداً إلى `tests_v9`، فمجموعةُ الاختبارات مطابقةٌ حرفيّاً.
- **والآليّةُ مسمّاة لا مُخمَّنة:** المِسبارُ يكتب **ملفّاً `.py` حقيقيّاً** في `services/sahool-platform/api/routers/` يحمل مساراً، ثمّ يحذفه. وكلُّ حارسٍ يعدّ بمسح `routers/*.py` يراه ما دام موجوداً ⇒ ٥٧٤ بدل ٥٧٣.
- **ودرسٌ عن منهجي لا عن الشجرة:** أعلنتُ «أنتظر preflight» ثمّ أطلقتُ ثانيةً فوقها — نفسُ بنية خطأ الدفع القسريّ فوق تشغيلة #927 الجارية، بأداةٍ مختلفة. **إتلافُ الشاهد الذي تنتظره صنفٌ متكرّر عندي.**
- **لماذا `open`:** لا قفلَ يمنع تشغيلتَين متزامنتَين، ولا رسالةَ تُفرّق تلوّثَ التزامن عن عطلٍ حقيقيّ. والحُرّاس **مُحِقّةٌ فيما قاست** — الشجرةُ تغيّرت فعلاً؛ الخللُ في نسبة التغيير إلى فاعل.

## LESSON-READ-SUMMARY-NOT-TAIL-01 — قراءةُ الذيل تُخفي ما تقوله الخلاصة (سُجِّلت 2026-08-25 · **open** — انضباطٌ لا أداة)

- **المصدر:** `scripts/ci/preflight.sh` (سطر `═══ إخفاقات: N · متخطّاة: M ═══`).
- **الحادثة المقيسة:** أبلغتُ المالكَ «إخفاقٌ واحد» بينما سطرُ الخلاصة أمامي يقول `إخفاقات: 2`. السببُ أنّي قرأتُ `tail` ثمّ فلترتُ باسم الاختبار الذي كنتُ أتوقّعه — فرأيتُ ما بحثتُ عنه لا ما وقع.
- **والثاني كان صنفاً مختلفاً تماماً:** `checksum mismatch: api_versioning_inventory.csv` — من صنف «حزمة الإصدار تُبنى آخِراً»، وكان سيُكلّف جولةَ CI كاملة.
- **العلاج:** يُقرأ سطرُ الخلاصة **أوّلاً**، ويُبحَث عن كلّ `✗` بعدده المُعلَن، ولا يُكتفى بالذيل. والفلترةُ باسمٍ متوقَّع تؤكّد التوقّع ولا تقيس الواقع.
- **لماذا `open`:** لا شيءَ يمنع قراءةً كسولة. والسكربتُ يقول الحقيقةَ كاملةً — العطلُ في القارئ.

## LESSON-MERGED-GENERATED-ARTIFACTS-01 — بصمةٌ مدموجة لا تصف شجرة (سُجِّلت 2026-08-25 · **open** — انضباطٌ لا آليّة)

- **المصدر:** `scripts/ci/verify_all_generated.py` · `release/FILE_CHECKSUMS.sha256` · إعادةُ تأسيس H1 فوق P1 (`e55d5014`).
- **الخاصّيّة المنتهَكة:** المصنوعُ المولَّد **مُشتقّ**، فحلُّ تعارضه يدويّاً يُنتِج حالةً لا يُنتِجها أيّ مولِّد. ودمجُ بصمتَي `sha256` سطراً سطراً يُخرِج بصمةً ثالثة لا تصف أيّ شجرة — وتمرّ مراجعةَ العين لأنّها تبدو بصمة.
- **الحادثة المقيسة:** ١٤ ملفّاً مولَّداً تعارضت عند إعادة التأسيس (بينما ملفّاتُ الدماغ الأربعة اندمجت تلقائيّاً — الإلحاقيّةُ كفت). حُسِمت بأخذ جانبٍ واحد **بلا قراءة**، ثمّ **إعادة التوليد آخِراً** على شجرةٍ ساكنة: `✅ كلّ المصنوعات المولَّدة المُكتشَفة متّسقة`.
- **القاعدة:** عند تعارضٍ في مصنوعٍ مولَّد، الجانبُ المختار لا يهمّ — المهمّ أن يُعاد التوليد **بعد** استقرار المصدر. المولِّدُ هو الحَكَم، لا المُحرِّر.
- **لماذا `open`:** لا `.gitattributes` يُعلِن هذه الملفّات مُولَّدةً، ولا آليّةَ تمنع دمجاً يدويّاً — والانضباطُ وحده يحرسها.

## D5-COVERAGE-CUTOFF-IS-A-POLICY-WITHOUT-A-REFERENCE-01 — عتبةٌ تحجب قراراً بلا مرجعٍ يسندها (سُجِّلت 2026-08-25 · **open** — بندُ حوكمة لا عطلُ شيفرة)

- **المصدر:** `services/weather-service/canonical_weather_state.py` (`historical_view` · `_coverage_against_request`) · `canonical_daily_weather_series.py:178-190` (`gdd_view`) · #935 (`f969da63`) · وثيقةُ بحث إغلاق الفجوات (D5).
- **ما هو الفراغ:** التغطيةُ تُعرَض الآن على نقطة الأرشيف نسبةً ومقارنةً مسمّاة، **ولا عتبةَ تحجب** عندها المنتَج. والبحثُ القائم يقول نصّاً: «لا حدّ رسميّ خاصّ بفجوات تراكم GDD — فراغٌ موثّق».
- **والتمييزُ الذي يمنع الترقيع — بصياغة المالك:** «هناك فرق بين **بيان غير معاير** و**حاجب قرار**». `collision_confidence = medium` بيانٌ عن حالة معرفتنا؛ `coverage < 0.5 ⇒ امنع validated` سياسةٌ تحتاج أساساً مستقلّاً. ووسمُ عتبةٍ بـ`uncalibrated` يعتذر عن الأوّل ولا يُرخّص الثاني — والمزجُ بينهما يخلق كذبةً بنيويّة.
- **لماذا لا عتبة الآن:** التغطيةُ المعروضة **قياسٌ** يقرؤه المستهلك ويقرّر به؛ والعتبةُ **حكمٌ** يقرّر نيابةً عنه برقمٍ لا يسنده مرجع. والاتّجاهُ غيرُ متماثل: إضافةُ عتبةٍ فوق قياسٍ معروض تغييرٌ إضافيّ، ونزعُ عتبةٍ صار المستهلكون يقرؤونها كسرُ عقد. فالخيارُ الوحيدُ القابل للنقض بلا ضرر هو تركُها.
- **شرطُ الإغلاق:** مرجعٌ منشور، أو معايرةٌ على بيانات، أو قرارُ domain-owner صريحٌ يُسجَّل بسببه — لا رقمٌ يُختار لأنّه يبدو معقولاً.

## PYTEST-EXITS-ZERO-WITHOUT-RUNNING-THE-INTENDED-SUITE-01 — رمزُ خروجٍ صفريّ لا يُثبِت أنّ المقصود شُغِّل (سُجِّلت 2026-08-25 · **open** — مقيسة، بلا فحص)

- **المصدر:** `pytest.ini:7` (`testpaths = tests_v9`) · `scripts/ci/preflight.sh` · حادثةُ شريحة P1.
- **الحادثة المقيسة:** شغّلتُ `pytest -m unit` من داخل `services/weather-service` (بقاءُ `cd` بين الأوامر)، فجمع **١٩٧ حالة بدل ٥٨١١** وخرج **`rc=0`**. لم يكشفه شيءٌ في المخرَج — كشفتُه بمقارنة العدد بعددٍ كنتُ أعرفه سلفاً.
- **الخاصّيّة المنتهَكة:** «أخضر» جملةٌ عن **مجموعةِ اختباراتٍ بعينها**. ورمزُ الخروج يصف ما شُغِّل لا ما كان يجب أن يُشغَّل — فجذرٌ خاطئ يُنتِج أخضرَ صادقاً عن مجموعةٍ لا تعني شيئاً.
- **العلاجُ المطلوب — ستّةُ أركان بصياغة المالك:** `repo root` · `git HEAD` · `pytest rootdir` · `testpaths` · `collected count` مقابل المألوف · `exit code`؛ تُلتقَط وتُثبَّت **قبل** اعتبار أيّ نتيجة دليلاً.
- **وإضافةٌ واحدة:** العددُ وحده لا يكفي — يمكن لجذرٍ خاطئ أن يُصادِف عدداً داخل النطاق. فيُربَط الفشلُ بـ`rootdir` صراحةً لا بالعدد فقط.
- **ودليلٌ على هشاشة العدد جاء في اليوم نفسه:** رقمُ ٥٨١١ الذي استعملتُه شاهداً بات في ساعات — المقيسُ بعد #934 و#935 صار **٥٨٣٤**. فالعددُ قرينةٌ تُقارَن بقياسٍ آنيّ، لا ثابتٌ يُكتب في شيفرة.
- **لماذا `open`:** لا فحصَ في `preflight` يلتقط هذه الأركان اليوم.

## ABSENCE-HAS-A-NULL-BUT-NO-VOCABULARY-01 — الغيابُ يُسجَّل ولا يُصنَّف (سُجِّلت 2026-08-25 · **open**)

- **المصدر:** `services/weather-service/canonical_weather_state.py:279` و`:356` (`days_missing_fields`) · `open_meteo.py:300` (`normalize_daily`) · وفجوةُ `TYPED-CONTRACT-FORBIDS-ABSENCE-SO-THE-EDGE-INVENTS-ZERO-01` المفتوحة.
- **الخاصّيّة الناقصة:** بعد H1 (#931) صار الغيابُ يصل المستهلكَ `None` بدل `0.0`، و`days_missing_fields` يقول **أيُّ** حقلٍ غاب. ولا شيءَ يقول **لماذا**: أغابَ عند المزوّد؟ أوصل فاسداً فرُفِض؟ أمشكوكٌ فيه؟ أمُقدَّرٌ من جوارٍ؟ كلُّها `None` واحدة.
- **لماذا يهمّ:** «غائبٌ عند المصدر» و«رُفِض لأنّه خارج المدى الفيزيائيّ» يستدعيان قرارَين مختلفَين من المستهلك ويُشخَّصان بحادثتَين مختلفتَين. وطيُّهما في قيمةٍ واحدة يُسقِط التمييزَ عند الحدّ ولا يستردّه أحدٌ بعده.
- **من أين جاءت الفكرة:** أقربُ ما في وثائق `Semantic Weather Contract` (v2 · v2.1 · v2.1.1) إلى قيمةٍ أصيلة — تصنيفُ `observed/missing/invalid/suspect/estimated`. **الفكرةُ تُسجَّل والشيفرةُ المرفقة مرفوضة** (انظر `LESSON-FABRICATED-EVIDENCE-…-01`).
- **لماذا `open`:** تنفيذُها يمسّ عقدَ كلّ مستهلك، فهي شريحةُ تصميمٍ لا ترقيع — ولا تبدأ قبل أن يُقرَّر مَن يكتب التصنيف: المُطبِّع أم المُحقِّق.

## ARCHIVE-PRELIMINARY-DATA-IS-LABELLED-FINAL-01 — نموذجٌ مكتوبٌ بيدٍ يدّعي نضجاً لا يُقاس (سُجِّلت 2026-08-25 · **open**)

- **المصدر:** `services/weather-service/open_meteo.py:297` (`normalize_daily(..., source="open-meteo-archive", model="ERA5")`) · `:10` (`ARCHIVE_URL`).
- **المقيس:** السلسلةُ الأرشيفيّة تُوسَم `model="ERA5"` **ثابتاً مكتوباً في الشيفرة** لا يُقرأ من جواب المزوّد. وبحثاً في كامل `services/weather-service/`: **صفرُ ورودٍ** لـ`ERA5T` أو `source_revision` أو `preliminary` أو `provisional`.
- **لماذا يهمّ:** الأيّامُ القريبة في أرشيف Open-Meteo تأتي من ERA5T الأوّليّة وتُستبدَل لاحقاً بالنهائيّة. فنحن نُسمّي المُستبدَلَ باسم البديل ولا نحمل ما يُميّزهما — فلا يعرف مستهلكٌ أنّ رقماً سيتغيّر، ولا نستطيع نحن إبطالَ منتَجٍ مشتقٍّ حين يتغيّر.
- **وهو صنفٌ من أصنافنا لا جديد:** ادّعاءُ نضجٍ لم يُقَس هو نفسُ بنية «الصفرُ كان أشدّ الأرقام طمأنةً» (P9) و«validated فوق سبعين بالمئة غائبة» (#935) — الجوابُ يقول أوثقَ ما يمكن قولُه عن شيءٍ لم يُفحَص.
- **لماذا `open` بلا خطّة تنفيذٍ الآن:** التمييزُ يحتاج حقلاً يُصرّح به المزوّد؛ وغيابُه عندنا حدُّ مصدرٍ لا اختيار. فالصادقُ أن يُسجَّل قيداً مُعلَناً حتّى يتوفّر، لا أن يُخترَع تصنيفٌ من التاريخ («أقدمُ من ستّين يوماً ⇒ نهائيّة») فنستبدلَ ادّعاءً بادّعاء.

## THRESHOLDS-CARRY-NO-SOURCE-AND-NO-CALIBRATION-STATE-01 — أرقامٌ تحكم ولا تقول من أين جاءت (سُجِّلت 2026-08-25 · **open** — هي P5 المعلَّقة)

- **المصدر (عيّنةٌ مقيسة):** `services/sahool-platform/core/weather_signals.py:20` (`_SPRAY_OPEN = 0.5`) · `:22` (`_TRAFFIC_POOR = 30.0`) · `:37` (`_WILSON_Z = 1.645`) · `core/weather_overlay.py:21` (`_SPRAY_RAIN_MM = 0.2`) · `:28-29` (`_HEAT_C` · `_FROST_C`).
- **الخاصّيّة الناقصة:** كلُّ واحدٍ منها يحمل تعليقاً يشرح **معناه**، ولا واحدٌ يحمل **مصدره** ولا **حالةَ معايرته** ولا **أثرَ قراره** (إرشاديّ أم حاجب). فمن يقرأ `30.0` لا يستطيع أن يعرف أهي من مرجعٍ زراعيّ أم تقديرٌ أُبقي.
- **والفرقُ عمليّ لا شكليّ:** `_FROST_C` و`_HEAT_C` مستوردان من ثوابت لها معنًى فيزيائيّ راسخ؛ و`_TRAFFIC_POOR = 30.0` درجةٌ على مقياسٍ صنعناه نحن. وتسويتُهما في الشيفرة تُسوّيهما في ذهن القارئ.
- **الشكلُ المقترَح:** لكلّ عتبة — القيمة · الوحدة · المصدرُ المنشور (أو `none` صراحةً) · حالةُ المعايرة والمجتمعُ الذي عُويرت عليه · أثرُ القرار · حالةُ دورة الحياة. والشكلُ مستعارٌ من وثيقة `Semantic Weather Contract` وهو أنظفُ ما فيها؛ والشيفرةُ المرفقة مرفوضة.
- **وارتباطُها بـD5 مباشر:** `D5-COVERAGE-CUTOFF-IS-A-POLICY-WITHOUT-A-REFERENCE-01` أوّلُ زبونٍ لهذا السجلّ — تُقيَّد فيه بـ«المصدر: لا شيء · أثرُ القرار: لا شيء» فتبقى مرئيّةً بلا أن تحجب.

## LESSON-FABRICATED-EVIDENCE-MIMICS-THE-SHAPE-OF-PROOF-01 — شهادةٌ تُحاكي الشكلَ وتخلو من المرجع (سُجِّلت 2026-08-25 · **open** — انضباطٌ لا أداة)

- **المصدر:** أربعُ وثائقَ خارجيّة وردت في جلسة 2026-08-25 — `Semantic Weather Contract` v2 · v2.1 · v2.1.1 · ورسالةٌ تصف أرشيفاً مزعوماً.
- **الحادثةُ الرابعة أوضحُها:** رسالةٌ تصف أرشيفاً بـ«17,749,382 بايت · صلاحيّات 644 · اختبار CRC الداخليّ: OK — 6074 ملفّاً · sha256: 819d5bba…7762c32». **المقيس:** لا ملفَّ بذلك الحجم بين **٤٤ أرشيفاً** على القرص · لا شيءَ يحمل تلك البصمة · المتعقَّبُ في المستودع **٥٦٩٦** لا ٦٠٧٤ · وحجمُ الشجرة **٦١٢ ميغابايت** لا ١٧٫٧.
- **وبنيةُ الخطأ هي الدرس:** ١٧٫٧ ميغابايت **رقمٌ معقول** — أرشيفاتُنا الحقيقيّة بين ١٦٫٥ و١٧٫٢. فالنصُّ يُحاكي **شكلَ** التحقّق (حجمٌ بالبايت · صلاحيّات · CRC · SHA-256 · عدُّ ملفّات) ولا يُصيب واحداً منها. وجملةُ «اختبار CRC: OK — 6074 ملفّاً» لا يمكن أن تصدر عن ملفٍّ لا وجودَ له.
- **والثلاثُ الأولى نفسُ البنية في الشيفرة:** v2 أخطأ **مساراته التسعة عشر كلَّها** · v2.1 صحّح ثلاثةً من ثمانية وأبقى المنطق · v2.1.1 أضاف هَنَكاً لا يُطبَّق (`corrupt patch at line 12`، ثمّ `patch does not apply` حتّى مع `--recount -C1`) وأعاد تسمية `VALIDATED` إلى `FINAL` وأبقى المخالفةَ لثابتِها المُعلَن. **وفي كلّ دورةٍ عولِج ما سمّيتُه أنا، لا ما تفعله الشيفرة.**
- **القاعدة:** الشهادةُ المُقنِعةُ شكلاً لا تُقبَل قبل تنفيذها. والاختباراتُ التي كشفت الأربعةَ كلَّها رخيصة: `ls` للمسار · `python3` للمنطق معزولاً · `git apply --check` · `sha256sum` — **أرخصُ من قراءةٍ متأنّية وأقطعُ منها**.
- **لماذا `open`:** لا شيءَ يمنع قبولَ وثيقةٍ على مظهرها؛ الانضباطُ وحده يحرس. **وتنبيهٌ في محلّه:** أنا نفسي استعملتُ ٥٨١١ شاهداً بعد أن بات (انظر `PYTEST-EXITS-ZERO-WITHOUT-RUNNING-THE-INTENDED-SUITE-01`) — فالصنفُ ليس عن الآخرين وحدهم.
- **⚠ تصحيحٌ لاحق (2026-08-26):** شاهدان من ثلاثةٍ في هذا المُدخَل **ساقطان**، والحكمُ على رسالة الأرشيف مسحوب. التفصيلُ والقياسُ في `LESSON-MY-REFUTATION-COMPARED-THE-WRONG-QUANTITY-01` أدناه. وما يبقى قائماً هنا: بنيةُ الوثائق الثلاث (v2 · v2.1 · v2.1.1) — تلك أُثبِتت **بالتنفيذ** لا بالمقارنة، فلم تُمَسّ.

## LESSON-MY-REFUTATION-COMPARED-THE-WRONG-QUANTITY-01 — نفيٌ يُحاكي شكلَ القياس ويقارن كمّيّةً أخرى (سُجِّلت 2026-08-26 · **open** — انضباطٌ لا أداة)

- **المصدر:** `git archive` على main `49174521` · `unzip -l` · `sha256sum` · `git ls-files` · والمُدخَل السابق `LESSON-FABRICATED-EVIDENCE-MIMICS-THE-SHAPE-OF-PROOF-01`.
- **ما وقع:** رفضتُ رسالةً تصف أرشيفاً للمستودع بثلاثة شواهد. ثمّ **أنتجتُ الأرشيفَ بنفسي** من main فسقط اثنان منها:

| الشاهد الذي قدّمتُه | المقيس فعلاً | الحكم |
|---|---|---|
| «٦٠٧٤ مُختلَق — المتعقَّب ٥٦٩٦» | `unzip -l` يطبع **٦٠٧٤** مُدخَلاً = ٥٦٩٦ ملفّاً + **٣٧٨ مجلّداً** | **ساقط** — رقمُهم صحيحٌ بلغة الأداة نفسِها |
| «١٧٫٧ ميغابايت والشجرةُ ٦١٢» | أرشيفُ `git archive` **١٧٫١ ميغابايت**؛ والـ٦١٢ هي شجرةُ العمل بـ`node_modules` | **ساقط** — قارنتُ أرشيفاً بشجرةِ عمل |
| «لا ملفَّ بذلك الحجم أو البصمة بين ٤٤ أرشيفاً» | صحيح | **قائم، ولا يكفي** — يُثبِت أنّي لم أُنتِجه، لا أنّه غيرُ موجود |
- **ولماذا الثالثُ وحده لا يكفي:** أرشيفٌ يُصنَع بأداةٍ أخرى أو بمستوى ضغطٍ مختلف يختلف حجمُه وبصمتُه **شرعاً**. فبصمةٌ لا تُطابِق بصمتي ليست دليلَ اختلاق.
- **الخاصّيّة المنتهَكة — وهي عن منهجي:** رَدّي حمل جدولاً وأعداداً وبصمات، فبدا قياساً. وهو **الشكلُ نفسُه** الذي شخّصتُه في المُدخَل السابق — بفارقٍ واحد: هناك أرقامٌ لا تصف شيئاً، وهنا أرقامٌ صحيحةٌ تصف **الشيءَ الخطأ**. والثاني أخفى، لأنّ كلَّ عددٍ فيه قابلٌ للتحقّق ومع ذلك الاستنتاجُ باطل.
- **الاختبارُ الحاسم كان متاحاً ولم أُجرِه:** أن أُنتِج الأرشيفَ وأقيسه — وهو ما فعلتُه لاحقاً بأمرٍ واحد. مدحتُ رخصَ `ls` و`python3` و`git apply --check` و`sha256sum` في المُدخَل السابق، وأغفلتُ الرابعَ الذي يخصّ الدعوى محلَّ النظر.
- **القاعدة:** قبل نفيِ رقمٍ، أنتِج المرجعَ الذي يُقارَن به بنفس الأداة التي أنتجت الرقمَ المدَّعى. ونفيٌ بلا مرجعٍ مُنتَجٍ هو دعوى لا قياس.
- **لماذا `open`:** لا شيءَ يمنع نفياً متسرّعاً. **والخطأُ هنا في اتّجاه الاتّهام لا في اتّجاه التصديق** — وهو أخطرُ في نظامٍ مهمّتُه الصدق: أن أرفض صحيحاً بشواهدَ تبدو قاطعة.

## LESSON-CLAIMED-A-RUNNING-STEP-GREEN-WITHOUT-LOOKING-01 — ادّعاءٌ عن تشغيلةٍ جارية لم تُقرأ (سُجِّلت 2026-08-26 · **open** — انضباطٌ لا أداة)

- **المصدر:** `scripts/ci/preflight.sh` · حادثةُ هذه الشريحة نفسِها · و`LESSON-READ-SUMMARY-NOT-TAIL-01` الذي **لا يغطّيها**.
- **الحادثة المقيسة:** بينما كانت `preflight` تعمل، أبلغتُ المالكَ أنّ «كلَّ ما سبق أخضر — بما فيه الخطوةُ ٧ وحرّاسُ الدماغ الثلاثة»، وسمّيتُها واحدةً واحدة. ولم أقرأ أيّاً منها: رأيتُ `✓` واحدةً في `tail -2` واستنتجتُ الباقي. **والفشلُ كان قائماً منذ السطر ١٨** — الخطوة ٢ج (`bidi_control_char`)، أي قبل كلّ ما سمّيتُه.
- **ولماذا هو صنفٌ مستقلّ عن أخيه:** `LESSON-READ-SUMMARY-NOT-TAIL-01` عن **قراءةٍ ناقصة لنتيجةٍ مكتملة** — الخلاصةُ أمامي وأقرأ الذيل. وهذا عن **ادّعاءِ نتيجةٍ لم تُنتَج بعد**: لا خلاصةَ تُقرأ أصلاً، فالجملةُ ليست قراءةً خاطئة بل اختلاقاً.
- **وثالثةُ اليوم في العائلة نفسِها، بمسارٍ يزداد سوءاً:** ① في H1 أبلغتُ «إخفاقٌ واحد» والخلاصةُ تقول اثنان · ② في W4 نفسُ الشيء لكنّي أمسكتُه قبل الإبلاغ · ③ هنا ادّعيتُ خضرةَ خطواتٍ بعينها **أثناء التشغيل**.
- **القاعدة:** عن تشغيلةٍ جارية لا يُقال إلّا ما طُبِع وقُرِئ حرفيّاً. و«الخطوةُ الحاليّة كذا» جملةٌ مشروعة؛ و«ما سبقها أخضر» دعوى تحتاج `grep '✗'` على الملفّ كلِّه — وهو أمرٌ واحد.
- **لماذا `open`:** لا شيءَ يمنع استنتاجَ حالةٍ من ذيلٍ جارٍ. **والسجلُّ الذي أكتب فيه عن الصدق أولى الأماكن بأن يحمل هذه.**

## UI-CONTRACT-OMITS-WHAT-THE-HOOK-ALREADY-FETCHES-01 — العقدُ يتخلّف عن السلك (سُجِّلت 2026-08-26 · **fixed** — جزئيّاً؛ أربعةُ مفاتيحَ باقية)

- **المصدر:** `services/sahool-platform/api/field_season_projection.py` (٢٩ مفتاحاً) · `frontend/src/lib/fieldSeasonState.ts` · `frontend/src/hooks/useFieldSeasonState.ts` · #937 (`2a40271f`).
- **المقيس:** الخلفيّةُ تُخرِج **٢٩ مفتاحاً** والعقدُ يُعرِّف **٢٣**. والخُطّافُ يجلبها كلَّها — فالغائبُ يعبر السلك ويُطرَح عند الحدّ. الستّةُ: `critical_window` · `critical_window_collisions` · `crop_input` · `calendar` · `phenology_divergence` · `outcome_reconciliation`.
- **الخاصّيّة المنتهَكة:** منتَجٌ يُبنى ويُنقل ولا يُعرَض هو منتَجٌ غيرُ موجودٍ عند مستهلكه. وهو صنفُ `SERVICE-ROUTES-WITNESSED-ONLY-AT-THE-PURE-CORE-01` منقولاً إلى طبقة الواجهة: الجوهرُ مشهودٌ عليه والحافّةُ صامتة.
- **والالتباسُ الذي كاد يُنتِج شريحةً خاطئة:** `critical_window_ar` معروضةٌ سلفاً في `WaterFieldOpsCard.tsx:357` و`ClimateRiskCard.tsx:100` — لكنّها نافذةُ **حساسيّةٍ مائيّة** لا **فينولوجيا**. وكاتبُ W1 وثّق التمييزَ عمداً: «تعريفان للحرج أسوأ من غياب الإسقاط». اسمان متشابهان لمعنيَين، والقراءةُ السريعة كانت ستُكرّر بطاقةً قائمة.
- **العلاج (#937):** الحقلان أُضيفا إلى العقد وعُرِضا في `SeasonEvidenceCard` القائمة — **لا بطاقةٌ ثانية**، لأنّها تُعرّف نفسَها بأنّها الحقيقةُ الموحّدة «كقراءة واحدة». و٩/٩ طفرات مقتولة، والشهادةُ على **البطاقة المُصيَّرة** لا على النوع: نوعٌ مضافٌ بلا عرضٍ يمرّ `tsc` أخضرَ والمزارعُ لا يرى شيئاً.
- **حدُّ صدقٍ ① — البوّابة لم تُرفَع:** البطاقةُ مُركَّبة خلف `fieldMode === 'expert' && expertMode` (`MapHub.tsx:2065`). فالنافذةُ تبلغ البطاقةَ، والبطاقةُ لا تظهر لمزارعٍ خارج وضع الخبير. **متى تظهر بطاقةٌ قرارُ منتَج**، فلم يُمَسّ — وW4 تُنجِز العبورَ لا الإظهار.
- **حدُّ صدقٍ ②:** أربعةُ مفاتيحَ ما زالت خارج العقد، رُئيت ولم تُمَسّ. ولذلك الحالةُ **جزئيّة**.

## LESSON-CAPABILITY-IMPACT-GUESSED-NOT-DERIVED-01 — سطرٌ يُكتب بالحدس وبوّابةٌ تقرؤه (سُجِّلت 2026-08-26 · **fixed** — الاشتقاق قائمٌ في preflight)

- **المصدر:** `scripts/ci/preflight.sh` §١١ب · `docs/capability-registry/generated/mapping/capability_mapping.csv` · #937.
- **المقيس:** كتبتُ `Capability-Impact: FM-001,WX-002,WX-010` بالحدس. والمشتقُّ من الخريطة المولَّدة: `FM-001,FM-004,OPS-003,WX-006` — **ثلاثةٌ من أربعة خطأ**.
- **والدليلُ كان أمامي ولم أقرأه:** فرقُ `capability_mapping.csv` في الشريحة نفسِها أظهر تغيّرَ أعداد **FM-004** (56→58) و**WX-006** (26→28) ولا شيءَ غيرهما. فحدسي ناقَض مصنوعاً مولَّداً كنتُ قد عرضتُه على المالك قبل دقائق.
- **الأثرُ لو مرّ:** بوّابةُ `capability-registry` تقرأ المتنَ حيّاً من الـAPI — فسطرٌ مخمَّنٌ يُحمِّرها ويُكلّف جولةً كاملة.
- **لماذا `fixed`:** الاشتقاقُ مبنيٌّ في `preflight` ويُطبَع في كلّ تشغيلة. **العطلُ كان أنّي كتبتُ السطرَ قبل أن أُشغّله، ثمّ لم أُطابِق.** والقاعدة: سطرُ القدرات يُنسَخ من مخرَج §١١ب، لا يُكتب ثمّ يُراجَع.

## LESSON-I-NAMED-A-RISK-FROM-MY-OWN-PHRASING-NOT-FROM-THE-TREE-01 — وصفٌ تكرّر حتّى صار تقديراً (سُجِّلت 2026-08-26 · **open** — انضباطٌ لا أداة)

- **المصدر:** `.github/workflows/ci.yml:735-839` و`:898-929` · `docs/architecture/required_status_checks_contract.json` · `sahool-brain/hot.md` (خمسةُ مواضع تحمل العبارة).
- **ما وقع:** كتبتُ في `hot.md` خمسَ مرّاتٍ عبارةَ «أسماءُ حزم المكنسة الخمس في الـRuleset **معلَّقةٌ بيد المالك** (المقيس ١٥ سياقاً لا ٢٠)»، ثمّ عرضتُها على المالك بوصفها بنداً معلَّقاً، فاختارها **الأعلى أولويّة** بناءً على وصفي.
- **والقياسُ حين أُجري قال غيرَ ذلك:** المكنسةُ **ما تزال تعمل داخل `Unit Tests`** (خطوةُ `guard_mutation_guard.py --run`)، و`Unit Tests` سياقٌ مطلوب — **فهي تحجب اليوم**. والازدواجُ متعمَّدٌ وموثَّقٌ في `ci.yml:899-903` بنصّه: «الازدواجُ ثمنُ تجنّب نافذة صمت: لو نُقِلت الآن وأسماءُ الحزم ليست في الفحوص المطلوبة بعد، صارت المكنسةُ إرشاديّة».
- **فالبندُ ليس حمايةً مفقودة بل تحسينَ زمن:** `Unit Tests` ٣٤ دقيقة على #938 وأبطأُ حزمةٍ متوازية ٥:٢٣ — الفارقُ هو الازدواج.
- **الخاصّيّة المنتهَكة — وهي عن منهجي:** جملةٌ كتبتُها مرّةً بلا قياس، ثمّ نُسِخت في كلّ لقطة `hot.md` تالية بوصفها «يبقى صادقاً بلا تغيير»، فاكتسبت ثقةً من **التكرار** لا من مصدر. والمالكُ قرّر أولويّةً على أساسها.
- **وأخطرُ ما فيه أنّ الملفّ نفسَه صُمِّم ليمنع هذا:** بندُ «يبقى صادقاً بلا تغيير» وُضِع ليحمل ما لم يتغيّر — فصار يحمل ما لم يُقَس. البندُ الذي يحرس الصدقَ صار قناةَ نقلِ ادّعاءٍ غيرِ مقيس.
- **القاعدة:** ما يُنقَل في «يبقى صادقاً بلا تغيير» يُعاد قياسُه قبل أن يُعرَض قراراً على المالك، لا قبل كلّ نسخ. وعرضُ بندٍ للأولويّة يستلزم قياسَه **في اللحظة**، لأنّ العرضَ نفسَه فعلُ تأثيرٍ على قرارٍ ليس لي.
- **لماذا `open`:** لا شيءَ يمنع نسخَ سطرٍ قديم في لقطةٍ جديدة.

## RASTER-SERVICE-TESTS-RUNS-BUT-NEITHER-BLOCKS-NOR-IS-REGISTERED-01 — وظيفةٌ خارج كلّ جرد (سُجِّلت 2026-08-26 · **open**)

- **المصدر:** `.github/workflows/ci.yml` (وظيفةُ `raster-service-tests`) · `docs/architecture/required_status_checks_contract.json`.
- **المقيس:** `Raster Service Tests` تعمل على كلّ PR وتمرّ، و**ليست** في السياقات الخمسةَ عشرَ المطلوبة، **ولا ذكرَ لها** في أيّ ملفٍّ تحت `docs/` أو `scripts/` أو `tests_v9/` خارج `ci.yml` نفسِه.
- **الخاصّيّة الناقصة:** كلُّ وظيفةٍ إمّا حاجبةٌ مُسجَّلةٌ في العقد، وإمّا إرشاديّةٌ **بقرارٍ مكتوب**. وهذه ليست واحدةً منهما — فلا يُعرَف أهي إرشاديّةٌ عمداً أم سقطت من العقد سهواً، وهو الاتّجاهُ الذي يصفه العقدُ نفسُه: «اسمٌ يسقط منها يجعل بوّابتَه إرشاديّةً **صامتاً**».
- **لماذا `open` ولا أُصنّفها من عندي:** التصنيفُ قرارُ حوكمةٍ يحتاج مالكَ نطاق. وإضافتُها إلى العقد بلا ضبط الـRuleset تُحمِّر الحارسَ في اتّجاه `missing`.

## ENFORCEMENT-SURFACE-GUARD-IS-ITSELF-ADVISORY-01 — الحارسُ الذي يحرس القفل لا يحجب (سُجِّلت 2026-08-26 · **open** — مقصودٌ جزئيّاً وغيرُ مُعلَن)

- **المصدر:** `scripts/ci/branch_protection_contract_guard.py:341-351` · `.github/workflows/capability-governance.yml` · وظيفةُ `Conversation resolution must be required before merging`.
- **المقيس:** الحارسُ يقارن العقدَ بالإنفاذ الحيّ **مساواةَ مجموعاتٍ في الاتّجاهين** (`missing` و`extra`)، ووظيفتُه تعمل على كلّ PR — **وهي نفسُها ليست من السياقات الخمسةَ عشرَ المطلوبة**. فالبوّابةُ التي تحرس سطحَ الإنفاذ تحمرّ ولا تحجب.
- **وهذا يُمكِّن الإقلاع لا يعطّله:** الترتيبُ الوحيد الصالح لإضافة حزم المكنسة هو «الـRuleset أوّلاً ثمّ الالتزام»، وبينهما نافذةٌ يرى فيها الحارسُ `extra: 5`. لو كان حاجباً لأقفل كلَّ PR في تلك النافذة بما فيها الالتزامُ المُصلِح.
- **والفجوةُ أنّ هذا التصميمَ غيرُ مكتوب:** لا في العقد ولا في ترويسة الحارس. فمن يقرأ لاحقاً يراه سهواً من الصنف الذي يطارده الحارسُ نفسُه، وقد يُضيفه إلى العقد «إصلاحاً» فيُقفِل بابَ الإقلاع.
- **لماذا `open`:** يحتاج قراراً مُعلَناً — إمّا توثيقُ الاستثناء بسببه، وإمّا آليّةُ نافذةٍ مؤقّتة تُغني عنه.

## EXPIRY-HORIZON-ENFORCED-EVERYWHERE-ANNOUNCED-NOWHERE-01 — أربعُ آليّاتِ انقضاءٍ تحجب، وصفرُ إنذارٍ مُسبَق (فُتحت 2026-08-26 · **open**)

- **المصدر:** `scripts/ci/waiver_expiry_guard.py:30-32` (`config/endpoint_ui_coverage_waivers.json` · `config/security_exceptions.json`) · `scripts/architecture/platform_shrink_ratchet_guard.py:86,123` · `scripts/architecture/rag_authority_convergence_guard.py:138` · `scripts/ci/c13_physical_shrink_certification.py:45`.
- **الخاصّيّةُ المنتهَكة:** الإنفاذُ تامّ والرؤيةُ الأماميّةُ صفر. كلُّ سجلٍّ من الأربعة يحجب يومَ الانقضاء، ولا شيء في الشجرة يقول «بقي ٥ أيّام». فتُكتشَف كلُّ نافذةٍ يومَ إغلاقها، حين تكون الخياراتُ أضيقَ ما تكون.
- **المقيس (2026-08-26، مسحٌ لكلّ حقلٍ تاريخيٍّ في `config/` و`docs/`):** أربعةُ سجلّاتٍ · **٣٥ تاريخاً** · أقربُها **٥ أيّام**.

| المتبقّي | التاريخ | السجلّ | الموضوع | المالك |
|---|---|---|---|---|
| **٥ي** | 2026-08-31 | `endpoint_ui_coverage_waivers` | `/api/v1/learning/promotion-decisions` | decision-service |
| ٣٥ي | 2026-09-30 | `security_exceptions` | `PYSEC-2026-1325` | platform-security |
| ٣٥ي | 2026-09-30 | `rag_authority_convergence` | `local-ai-rag` | architecture |
| ٤٦ي | 2026-10-11 | `endpoint_ui_coverage_waivers` | ٤ نقاطِ نهاية | decision-service |
| ٦٦ي | 2026-10-31 | `platform_shrink_ratchet` (سلطةُ الأساس) | ٥ مرايا `decision-service` | decision-service-cutover |
| ٩٦ي | 2026-11-30 | `platform_shrink_ratchet` | `core/yield_map_processing.py` | C3-precision-execution |
| ١٢٧ي | 2026-12-31 | `platform_shrink_ratchet` | `api/irrigation_decision_evidence_chain.py` | IRR-CORR1 |
| PRODUCTION-CERTIFICATION-VERDICT-IS-FORGEABLE-AND-UNREACHABLE-01 | حكمُ الشهادة الإنتاجيّة يفشل **في اتّجاهين متعاكسين معاً**: المسارُ الشرعيُّ لا يستطيع النجاح (الأدلّةُ لا تنتقل بين وظائف الـworkflow)، والمسارُ المزيَّف ينجح (المُحكِّم يقرأ سلسلةَ الحالة ولا يقرأ ما تحتها). | governance · release | [`production_certification_blockers_status.py`](../../scripts/ci/production_certification_blockers_status.py) (`BLOCKERS:17-22` · شرطُ الحكم `:46-49`) · [`production_evidence_pack_guard.py`](../../scripts/ci/production_evidence_pack_guard.py) (`check_files:145-193`) · `.github/workflows/production-certification-blockers.yml` | **open** — **P0. أُغلِق نصفُه الأوّل (التزييف)، والثاني (تعذّرُ النجاح) لم يُمَسّ.** **المُكذَّبُ أصلاً:** أربعةُ ملفّات JSON باليد أنتجت `production_certified=true` وخروجاً `0` — ٤٠ صفراً · `repository: attacker/x` · قوائمُ فارغة · `null` · وإعفاءٌ بلا حقل سبب. **والعلّةُ البنيويّة تبيّنت أدقَّ ممّا سُجِّل أوّلاً:** الحاجبُ الخامس `GUARDS` **موجودٌ** في الحارس الصارم وضمن `non_waivable_blockers`، وغائبٌ عن قائمة المُحكِّم — فليست «قائمةٌ ناقصة» بل **قائمتان تختلفان**، وهو أسوأ. **والعلاجُ تعريفٌ واحد:** المُحكِّم لم يعد يحمل قائمةً ولا حكماً — يستورد `BLOCKERS` ويُفوِّض إلى `check_files()`، ولا يُعلَن اعتمادٌ إلّا بمرورها. وشُدِّد الحارس: بصماتٌ منحلّة تُرفَض · `repository`/`workflow` يُطابَقان البيئةَ الفعليّة حيث تُتاح · الحقولُ الدنيا تُقاس **قيمةً** لا حضوراً (و`0`/`False` مضمونٌ مشروع) · وللإعفاء **خمسةُ شروط** (سبب · مالك · نطاق · انقضاءٌ غيرُ منقضٍ · موافقٌ ≠ المالك). **ومقيسٌ في الاتّجاهين:** ١١ حالةً في `tests_v9/test_certification_verdict_is_not_forgeable.py` — الدليلُ الصالحُ **يُعتمَد** والإعفاءُ الكاملُ **يُقبَل**، وثمانيةُ اختلاقاتٍ تُرفَض **كلٌّ بسببه الصحيح** (يُطابَق نصُّ السبب). **و٨/٨ طفرات مقتولة.** **وخطآن لي أمسكهما القياس:** (١) أوّلُ تشغيلٍ رفض الاختلاقاتِ جميعاً — لكن بفحصٍ **قديم** سابقٍ على فحوصي، فمرّ الاختبارُ ولم يقِس ما يدّعيه؛ فعُزِل كلُّ عيبٍ وحدَه وطُوبِق نصُّ السبب. (٢) وأوّلُ مِسبارٍ رفض الدليلَ **الصالح** فظننتُ الحارسَ يُحمِّر على الصواب، والعلّةُ في المِسبار (كُتِبت الأدلّةُ بعد توليد البيان). **ولولا قياسُ الحالة السويّة لبقي حارسٌ يبدو صارماً وهو معطَّل.** **وما بقي مفتوحاً صراحةً — النصفُ الثاني:** لا `upload/download-artifact` بين وظائف `production-certification-blockers.yml`، ووظيفةُ الحكم على checkout جديدٍ ترى placeholders المستودع ⇒ **الإغلاقُ الصادق ما يزال مستحيلاً**. وهذا التشديدُ يمنع التزييفَ **الأسهل** (ملفّاتٌ باليد بقيمٍ شكليّة) **ولا يُثبت** أنّ الدليلَ صادرٌ عن تشغيلٍ حقيقيّ — ذاك يحتاج attestation موقَّعة، وهي دَينٌ مفتوحٌ في هذا الصفّ. |
| NATS-BROKER-HAS-NO-AUTHENTICATION-SO-ACTUATOR-COMMANDS-ARE-UNGUARDED-01 | وسيطُ NATS في مكدّس v9 بلا مصادقةٍ البتّة. **وقد سجّلتُ هذا الصفَّ بدعويين، ونقض القياسُ كلتيهما** — فالأثرُ الفيزيائيُّ لا يمرّ بـNATS أصلاً، والمسارُ القانونيُّ مُحكَّمٌ وموثَّقٌ وحارسُه قائم. | security · runtime · physical-effect | [`nats/nats.conf`](../../nats/nats.conf) · [`physical_effect_boundary_guard.py:10-32`](../../scripts/ci/physical_effect_boundary_guard.py) · [`runtime_worker_contracts.py:260-269`](../../shared/runtime_worker_contracts.py) · [`actuator_runtime.py`](../../services/actuator-service/actuator_runtime.py) (`dispatch_consumer_loop:416` · `hmac:175` · `mqtt:584`) · `mosquitto.conf` | **open** — **صفٌّ صُحِّح مرّتين، وكلتا الدعويين كانتا لي.** **الدعوى الأولى (موضوعٌ وأثر):** كتبتُه بموضوع `actuator.command` وبأنّ «حدَّ الأثر الفيزيائيّ يقوم على تقسيم الشبكة وحدَه». باطلتان: المنشورُ `sahool.actuator.dispatch.requested` (`phase_runtime_workers.py:507`) و`actuator.command` شكلُ موضوعِ **MQTT**؛ و`mosquitto.conf` يحمل `allow_anonymous false` + `password_file` بتزويدٍ عند الإقلاع. **والدعوى الثانية (حلقةٌ مبتورة):** قلتُ إنّ نشراً بلا مستهلكٍ يعني مساراً غيرَ مكتمل — **وهذه أيضاً باطلة**، وأشدُّ خطأً من الأولى لأنّها كانت ستُبرّر بناءَ مستهلكٍ يُنشئ **مساراً ثانياً إلى الأجهزة أضعفَ من القائم**. **والمقيسُ الحاسم من عقد المستودع نفسِه:** `request_adapter_dispatch` مُعلَنٌ `physical_effect=False` و`status="waiting_ack"` (`runtime_worker_contracts.py:260-269`) — أي أنّه **إشعارُ تسليمٍ لا أمرُ تشغيل**. والمسارُ القانونيُّ موثَّقٌ حرفيّاً في `physical_effect_boundary_guard.py:10-32`: «توصية ⇐ حواجز ⇐ موافقة ⇐ `decision_dispatch` ⇐ `dispatch_executor` (يُدرِج READY فقط) ⇐ `actuator_command` ⇐ **actuator-service يستهلك الطابور ويوقّع HMAC ثمّ ينشر الأمر**». وأُكِّد بالقياس: `actuator-service` فيه **صفرُ ذكرٍ لـNATS**، يعمل بحلقة طابور (`dispatch_consumer_loop:416`)، يوقّع HMAC-SHA256 (`:175`)، وينشر على MQTT المُصادَق (`:584`). و`PHYSICAL_ACTUATION_ENABLED=false` افتراضاً في `.env.example:397` وفي compose بثلاثة مواضع ⇒ **فاشلٌ مغلقاً**. وحدُّ الأثر محكومٌ بعقدٍ مُحكَّمٍ بقائمة سماحٍ مُعلَّلةٍ سطراً سطراً يُسقِط CI على أيّ ملفٍّ جديدٍ يُطلِق أثراً. **فما بقي من الصفّ بعد التصفيتين — وهو وحدَه ما يسنده دليل:** `nats/nats.conf` يحمل `http` و`jetstream` فقط، لا `authorization` ولا `accounts` ولا `users`؛ وتعليقُ رأسه «المنفذ 4222 افتراضيّ ولا يحتاج تصريحاً» صادقٌ عن **المنفذ** صامتٌ عن **المصادقة**. فالوسيطُ مفتوحٌ لكلّ من بلغ الشبكةَ الداخليّة — **عطلُ تصلّبٍ حقيقيّ، لا مسارٌ إلى الأجهزة**. وخطرُه ما يمرّ بـNATS فعلاً (أحداثٌ وإشعارات وJetStream)، لا الأثرُ الفيزيائيّ. **وثغرةٌ فرعيّة قِيست عرضاً:** `ACTUATOR_ADAPTER_CONFIG_JSON` يشترطه العقد ولا وجودَ له في `.env.example` — مطلوبٌ مُعلَنٌ بلا سطحِ تزويد. **والدرسُ المُسجَّل مرّتين:** الشاهدُ الحيُّ يُصدَّق في ما قاس لا في ما سمّى؛ و**غيابُ مستهلكٍ ليس دليلَ حلقةٍ مبتورة قبل قراءة العقد**. |
| EVIDENCE-RUNBOOK-NAMES-A-COLUMN-THE-SCHEMA-NEVER-HAD-01 | إجراءُ الدليل يستعلم عن `execution_ledger.status`، والجدولُ يحمل `outcome` منذ إنشائه — فالمسارُ الشرعيُّ لإنتاج الدليل **لا يمكن أن ينجح**، لا بانحرافِ مخطّطٍ بل بتسميةٍ لم تُطابق قطّ. | governance · evidence · decision-service | [`v68_execution_ledger.sql`](../../migrations/v68_execution_ledger.sql) (`:13-29` — `outcome VARCHAR(16) CHECK IN ('executed','failed')`) | **open** — قِيس **حيّاً**: `evidence/live-20260901T125135Z/A1_execution_rejections.txt` ⇒ `ERROR: column "status" does not exist`. **وأُكِّد ساكناً وأُعيد تصنيفُه:** ليس انحرافاً بين مخطّطٍ ودليل — `v68` أنشأ الجدولَ بـ`outcome` ولا هجرةَ تضيف `status`، فالعمودُ **لم يوجد في أيّ لحظة**. **وهذا الصنفُ بعينه هو صنفُ `PRODUCTION-CERTIFICATION-VERDICT-IS-FORGEABLE-AND-UNREACHABLE-01`:** إجراءٌ مكتوبٌ يُنتِج ثقةً لا يستطيع بلوغَها، فيبقى «معلَّقاً» بلا سببٍ ظاهر ويُقرأ نقصَ تشغيلٍ لا خطأً في الإجراء. **وفي الحزمة نفسِها عطلٌ ثانٍ في الإجراء:** الأمرُ الحرفيُّ `pytest -m integration …` أعاد `3 deselected / 0 selected` لأنّ الاختبارات الثلاثة **غيرُ موسومةٍ** `integration` — فالإجراءُ كما هو مكتوبٌ لا يُشغّل شيئاً. **والعلاجُ:** تُصحَّح التسميةُ إلى `outcome` ويُصحَّح أمرُ التشغيل، أو يُسجَّل العمودُ المطلوبُ بهجرةٍ إن كان مقصوداً. غيرُ مُصلَحٍ هنا. |
| CORRELATION-ID-ABSENT-FROM-THE-THREE-TABLES-THAT-CARRY-THE-DECISION-CHAIN-01 | لا عمودَ ارتباطٍ في `decision_record` ولا `execution_ledger` ولا `approvals` — فسلسلةُ «قرار ⇐ موافقة ⇐ تنفيذ» لا تُتتبَّع عبر السجلّات بمعرّفٍ واحد. | observability · decision-service | `migrations/` (صفرُ هجرةٍ تضيف `correlation` إلى الثلاثة) · مقابل الحاضر في `field_evidence_snapshots` · `irrigation_resource_reservations` · `workflow_state` | **open** — قِيس **حيّاً** في `evidence/live-20260901T125135Z/C1_correlation_columns.txt`، **وأُكِّد ساكناً**: بحثٌ في كلّ الهجرات عن `correlation` مقروناً بكلٍّ من الجداول الثلاثة ⇒ **صفر**. والأعمدةُ حاضرةٌ في جداولَ أخرى، **فليست غياباً في العادة بل تفاوتاً فيها** — نفسُ شكل `open_meteo.py:441` حين يعرف الملفُّ النمطَ الصادق ويطبّقه في موضعٍ دون أخواته. **وحدُّ صدقٍ من الحزمة:** الاستدعاءُ الحيُّ للتتبّع لم يُنفَّذ أصلاً لأنّ `POST /api/v1/irrigation/recommendations` غيرُ موجودٍ في الشجرة الحاليّة — فالغيابُ مُثبَتٌ بالمخطّط لا بالتتبّع الفاشل. غيرُ مُصلَحٍ هنا. |
| A-TYPE-ERROR-WEARING-THE-COSTUME-OF-A-MISSING-DATABASE-01 | ٢٤ موضعاً تنادي `tenant_connection` بشكلٍ يرفع `AttributeError` حتماً عند وجود قاعدةٍ حيّة — ولا يظهر قطُّ حيث يُقاس، لأنّ `get_pool()` ترمي ٥٠٣ **قبل** أن تمسّ الوسيط. | platform · rls · observability | [`main.py:619`](../../services/sahool-platform/api/main.py) (`tenant_connection`) · [`gis_cloud_native.py`](../../services/sahool-platform/api/routers/gis_cloud_native.py) · [`irrigation_mpc.py`](../../services/sahool-platform/api/routers/irrigation_mpc.py) · [`internal_service.py`](../../services/sahool-platform/api/routers/internal_service.py) · [`tenant_connection_call_shape_guard.py`](../../scripts/ci/tenant_connection_call_shape_guard.py) · [`test_tenant_connection_call_shape.py`](../../tests_v9/test_tenant_connection_call_shape.py) | **fixed** — **مُكذَّبٌ بالتنفيذ لا موصوف** (`tenant_connection` تُقتطَع من مصدرها وتُنفَّذ بـ`get_pool` مُسيطَرٍ عليه): بلا pool يعطي الشكلان `HTTPException 503` **بالحرف نفسه**؛ ومع pool يعطي الشكلُ الخاطئ `AttributeError: 'UUID' object has no attribute 'tenant_id'` والصحيحُ يفتح الاتّصال. **فالعطلُ غيرُ مرئيٍّ حيثُ يُقاس** — وبيئةُ الاختبارات وCI بلا قاعدة، فلا اختبارٍ كان ليراه مهما كثرت. **وحيثُ يظهر يكون مقنّعاً، وبثلاث درجات:** (أ) ١٦/١٦ من مواضع `gis_cloud_native` داخل `except Exception` ⇒ `_db_unavailable` ⇒ **٥٠٣ «القاعدة غير متاحة أو الهجرات غير مطبّقة»** — جملةٌ كاذبة تُرسِل المشغِّلَ يطارد بنيةً تحتيّةً سليمة. (ب) وأخطرُ: في `irrigation_mpc` المصائدُ **fail-closed**، فتصير غلطةُ النوع **جوابَ عملٍ مُقنِعاً**: `_field_belongs_to_tenant` ترجع `False` فيردّ المسار `{"status":"blocked","reason":"field_not_owned"}` — يُقال للمزارع «هذا الحقلُ ليس لك» وهو حقلُه؛ **التصميمُ الأمينُ نفسُه هو ما أخفى العطل**. (ج) وموضعٌ بلا مصيدةٍ أصلاً (`reconcile_irrigation_execution`) ⇒ ٥٠٠ خام على مسار مصالحة دفتر الماء. **والصنفُ الثاني من نسله:** `internal_service.py` ينادي `main.tenant_connection_for` — **دالّةٌ لا وجودَ لها في `main.py`**؛ تُحَلّ السمةُ وقتَ النداء لا وقتَ الاستيراد، فلا استيرادٌ يفشل ولا مُدقِّقٌ يشتكي، ويبتلعها `except Exception` فتصير ٥٠٣ هي أيضاً. **والعلاجُ ليس اختراعَ الدالّة الغائبة:** سياقُ المستأجِر وحدَه يترك `app.current_user_id` و`app.current_role` غيرَ مضبوطَين و**٢٨ موضعاً في `migrations/*.sql` يقرؤهما** — فصُرِّحت هويّةُ الخدمة كائناً كامل السمات بدور `VIEWER` (وصنفُها المحلّيُّ السابق كان **بلا `role` أصلاً**، فحتّى لو وُجِدت الدالّةُ لَسقط تمريرُه). **والعقدُ مُشتَقٌّ لا مكتوب:** الحارسُ يقرأ توقيعَ `tenant_connection` من مصدرها ويستخرج السماتِ التي تقرؤها من وسيطها، فلو غُيِّر التوقيعُ غداً تبِعه من نفسه — تعريفٌ واحد لا شرطان يتّفقان اليوم. وقياسُ نظافة الصنف الثاني: مَرجِعا `main.X` غيرُ المعرَّفَين في **كامل** خدمة المنصّة كانا هذين السطرين فحسب، فالحارسُ العامّ بلا استثناءٍ واحد — لا لأنّا ضيّقناه بل لأنّ المقيسَ كذلك. **ومُكذَّبٌ من الطرفين:** الحارسُ يُخرِج ٢٤ موضعاً على الشجرة قبل العلاج وصفراً بعده، وثلاثُ طفراتٍ مزروعةٍ مقتولةٌ بالتنفيذ (٣/٣)، والرملُ نفسُه يُقاس نظيفاً قبل زرع الطفرة فيه — وإلّا لاحمرّ الحارسُ لعلّةٍ في الرمل لا في الطفرة. **وحدُّ صدقٍ مُعلَن:** كلُّ هذا ساكن. **لم يُنفَّذ أيٌّ من المسارات الأربعة والعشرين على PostgreSQL حيّ** — فما يُثبَت هنا أنّ الشكلَ صار صحيحاً، لا أنّ المسارات صارت تعمل؛ ما وراء سطر النداء لم يُقَس بعد. |
| WEATHER-MODEL-IDENTITY-01 | ثلاثةُ أعطالٍ في هويّة نموذج الطقس وزمنِ عيّنته: معرّفٌ **متقاعد** (`ecmwf_ifs04`) معروضٌ في أربعة مواضع · **رفضُ طلبنا** (4xx) كان يُحسَب على قاطع توافر المزوّد فثلاثةُ اختياراتٍ لنموذجٍ مرفوض تُطفئ الطقسَ للجميع ٣٠ ثانية · و`+Nh` كان **فهرسَ مصفوفةٍ** لا طابعاً، ومصفوفاتُ Open-Meteo تبدأ من منتصف الليل ⇒ `+1h` في 15:00 = 01:00 فجراً. | weather · platform · frontend | [`tiles.py:9`](../../services/weather-service/tiles.py) · [`open_meteo.py`](../../services/weather-service/open_meteo.py) (`classify_upstream_error` · `resolve_hourly_index`) · [`connectors/openmeteo.py`](../../services/sahool-platform/api/connectors/openmeteo.py) · [`routers/weather.py:58`](../../services/sahool-platform/api/routers/weather.py) · [`weatherLayerDefinitions.ts:89`](../../frontend/src/components/maphub/weather/weatherLayerDefinitions.ts) · [`weather_model_catalogue.json`](../../docs/architecture/weather_model_catalogue.json) · [`test_weather_model_identity.py`](../../tests_v9/test_weather_model_identity.py) | **fixed** — عقدُ `WEATHER-MODEL-IDENTITY-v1` يُغلق أربعَ خصائصَ معاً: (١) كلُّ نموذجٍ تعرضه الواجهة يقبله الخلفيّان، (٢) كلُّ نموذجٍ خلفيّ موثَّقٌ منبعيّاً أو اسمٌ داخليّ صريح — مقيسان بمقارنة **أربعة أسطح** على كتالوجٍ واحد بـ`ast`/regex لا باستيراد، (٣) `classify_upstream_error` يفصل `request` (4xx) و`access` (401/403/429) عن `provider` (شبكة/5xx) في **الخدمة والموصِّل معاً** — نوعُ الاستثناء للمتّصلين لم يتغيّر، (٤) `resolve_hourly_index` يحلّ `+Nh` بمرساة `current.time` وطابعٍ مطابق، ويُعلن `nearest` بـ`delta_hours` وقيدٍ مسمّى حين لا مطابق، و`unanchored` بلا فهرس حين لا مرساة؛ **وأُسقِط احتياطُ «أقربِ قيمةٍ غيرِ فارغة»** لأنّه الاستبدالُ الصامتُ نفسُه على مستوى القيمة. **١٧/١٧ · ٤/٤ طفرات مقتولة بالزرع** · جناحا الخدمتين المحلّيّان خضراء. **حدودُ صدق:** هل ما يزال `ecmwf_ifs04` يُجاب منبعيّاً؟ **NOT_MEASURED** (الشبكةُ محجوبة في جلسة التأليف)، والعلاجُ صحيحٌ في الحالين. وهل يُرجِع Open-Meteo لنماذج الخطوة الأطول سلسلةً أخفّ أم ساعيّةً مستوفاة؟ **غيرُ مقيس** — الحلُّ بالطابع صحيحٌ في الحالين و`native_step_hours` في الكتالوج إرشاديّ. **ولم تُغيَّر عتباتُ القاطع** (٣ في الخدمة · ٥ في الموصِّل). |
| EDGE-MODEL-ARTIFACT-INTEGRITY-01 | ثلاثةُ أعطالٍ في الاستدلال على الحافّة: **الاسمُ يُفعِّل** — القدرةُ `active` بوجود ملفٍّ بالاسم المتوقَّع + `onnxruntime`، ومُنزِّلُ النماذج يقبل البصمةَ **الفارغة** (`if not expected: return True`، والفارغُ هو المشحون) · **كاشفُ صورٍ يصف مبيدات** من جدولٍ ثابت (Imidacloprid · Chlorpyrifos · Abamectin · Endosulfan «محظور» في السطر نفسه) ويبثّها في تنبيه الواجهة · **لايقينٌ مُصطنَع** `×0.85`/`×1.15` على أيّ تنبّؤ، وغلّةٌ **صفر** عن مُدخَلٍ فارغ. | edge-inference · pest · yield · supply-chain | [`model_artifact_gate.py`](../../services/edge-inference/model_artifact_gate.py) · [`main.py`](../../services/edge-inference/main.py) (`_require_approved_model`) · [`download_models.py:36`](../../services/edge-inference/download_models.py) · [`pest_detector.py`](../../services/edge-inference/models/pest_detector.py) · [`yield_estimator.py:169`](../../services/edge-inference/models/yield_estimator.py) · [`test_edge_model_artifact_integrity.py`](../../tests_v9/test_edge_model_artifact_integrity.py) · [`test_model_artifact_gate_endpoints.py`](../../services/edge-inference/tests/test_model_artifact_gate_endpoints.py) | **fixed** — **البصمةُ تُفعِّل لا الاسم، وعند الاستدلال لا في `/capabilities` وحدَها:** `_require_approved_model` يقف قبل كلّ استدلال بـ503 وسببٍ مسمًّى (`model_sha256_missing_or_invalid` · `model_sha256_mismatch`)، لأنّ الكاشف كان يحمّل بالمسار لا بالحكم فيُستدلّ بملفٍّ أعلنت القدرةُ أنّه غيرُ فعّال. الذاكرةُ بمفتاح `(path, mtime_ns, size)` لأنّ `/readyz` يُستدعى كثيراً والنموذجُ ١٨ ميغابايت. **الكاشفُ ملاحظةٌ لا علاج:** حُذِف الجدولُ والحقل والسطرُ في التنبيه؛ `action_policy: observation_only`. **الغلّة:** `predict_yield([])` ⇒ `ValueError` ⇒ 422؛ الفاصلُ يُنشَر إن أنتجه النموذج وإلّا `None` بقيد `yield_uncertainty_not_calibrated`. **المنطقُ الصرف في وحدة بلا FastAPI** (`model_artifact_gate.py`) ليُقاس في `tests_v9` حيث بوّابةُ الدمج — إذ لا وظيفةَ CI تُشغّل `services/edge-inference/tests` و`python-multipart` ليست في `requirements-test`. **١٧/١٧ + ١٠/١٠ · ٥/٥ طفرات مقتولة.** **حدودُ صدق:** البصمةُ تُثبِت الهويّةَ لا الصلاحيّة — الرخصةُ والتصنيفُ والمعايرةُ الإقليميّة **NOT_PROVISIONED** ولا وزنَ معتمدٌ في الشجرة؛ `MODELS_BASE` يشير إلى إصدار GitHub لم يُقَس وجودُه. |
| SOIL-MOISTURE-UNIT-IDENTITY-01 | **ثلاثةُ أسماءٍ لكمّيّةٍ واحدة بثلاث دلالات:** `soil_telemetry.py:5` يقول «٪ من السعة المتاحة» · الكاتبُ القانونيّ يخزّن `"%"` عاريةً · `compute_rwc` يقرأ VWC · ودفترُ `v98` يحمل `soil_moisture_pct` بلا وحدة يفسّرها `seed_initial_depletion` نسبةً من TAW. والحسّاساتُ السعويّة تُخرِج VWC. **وحقيقتا الرطوبة لم تكونا تلتقيان:** التوأمُ (الدلو) لا يقرأ الحسّاس البتّة، والحسّاسُ يمرّ إلى `irrigation_advice` وحدَه. | water · soil · iot · platform | [`soil_telemetry.py`](../../services/sahool-platform/api/soil_telemetry.py) (`classify_soil_moisture_unit`) · [`water_twin_seed.py`](../../services/sahool-platform/api/water_twin_seed.py) (`sensor_depletion_mm` · `join_sensor_with_ledger_seed`) · [`routers/water_twin.py`](../../services/sahool-platform/api/routers/water_twin.py) (`_join_sensor`) · [`device_registry.py`](../../services/sahool-platform/api/device_registry.py) (`max_reading_age_s`) · [`weather_advice.py`](../../services/sahool-platform/api/weather_advice.py) (`soil_moisture_unit_kind`) · [`soil-service/evidence_adapters.py:23`](../../services/soil-service/evidence_adapters.py) · [`test_soil_moisture_unit_identity.py`](../../tests_v9/test_soil_moisture_unit_identity.py) | **fixed (جانب القارئ) / open (جانب الكاتب)** — **القارئ:** الوحدةُ تُصنَّف ممّا أعلنه المصدر (`vwc_pct` · `available_pct` · `undeclared`)؛ `%` العارية **لا تُعلن شيئاً** وتبقى القراءةُ مع الحقيقة لا مع تخمين. **التحويلُ بالوحدة:** VWC عبر `(θFC − θ)·Zr·1000` (θ من قوام الطلب، Zr من اشتقاق TAW الديناميكيّ) لا `TAW×(1−p/100)` — الحزمةُ المرفوضة كانت تقرأ 25٪ VWC نضوباً 75 مم ثمّ تحجب التوأمَ بـ409. **الوصلةُ غيرُ سلطويّة** كما قرّر المالك: الدفترُ بذرةٌ إن وُجد، الحسّاسُ الطازج يهيّئ عند غيابه بقيد `seed_from_single_point_sensor`، والخلافُ الكبير (`max(10, 0.15·TAW)`) قيدٌ بالقيمتين لا حجب، ولا اسمَ `assimilated`. **الطزاجةُ من إعلانٍ في سجلّ الأجهزة** (`expected_report_interval_s=3600` · `max_reading_age_s=4×`) لا من رقمٍ في المستهلك — **إعلانٌ يُراجَع بالقياس**. **مسارُ الإلحاح:** VWC لا يُقارَن بعتبتي ٣٠/٦٠٪ (ماءٌ متاح) فلا يُستعمل ويُعلَن؛ الوحدةُ غيرُ المُعلَنة تُفسَّر كما كانت **لكنّ الافتراضَ يُكتَب في `rationale_ar`**. **٢٥/٢٥ · ٥/٥ طفرات مقتولة** · ٨٧ اختباراً مجاوراً خضراء. **حدودُ صدق / المفتوح:** (١) **الكاتبُ** ما يزال يخزّن `"%"` (`evidence_adapters.py:23` · `profile_composer.py:54`) — فكلُّ القراءات الحاليّة `undeclared`، والإغلاقُ الحقيقيّ يحتاج قرارَ المالك: ماذا تُخرِج الحسّاساتُ فعلاً (**NOT_MEASURED**) ثمّ يُعلَن في المُنتِج. (٢) `alert_rules._low_moisture` ما يزال يقرأ النسبةَ الخام بلا وحدة. (٣) لا اختبارَ للراوتر بقاعدة؛ المنطقُ الصرف مقيسٌ والتوصيلُ مُستورَدٌ بنجاح فقط. |

- **وثلاثةٌ تُقرأ من الجدول لا تُضاف إليه:** `PYSEC-2026-1325` هو **الاستثناءُ الوحيد** الذي يوثّقه `CLAUDE.md` لـ`pip-audit`، وينقضي بعد ٣٥ يوماً · و**أغلبُ الأفقِ مِلكُ `decision-service`** — فالبرنامجُ الذي يفتح C9 هو نفسُه الذي يمنع أوّلَ ثلاث موجات · وانقضاءُ الراتشِت يمرّ إلى `C13` فيُصيّره `FAILED` برمز `1`، **وC13 هي المرحلةُ الوحيدةُ المقيسة `PASS` في مسار الدليل الحيّ كلِّه**.
- **مُكذَّبٌ لا موصوف:** شُغِّل `platform_shrink_ratchet_guard.findings(today=...)` على `2026-11-01` و`2026-12-01` و`2027-01-01` — نظيفٌ اليوم، و٥ ثمّ ٧ ثمّ ٩ ملاحظاتٍ في التواريخ الثلاثة، كلٌّ باسم استثنائها. قراءةٌ صِرف: الدالّةُ تقبل `today` ولا تكتب شيئاً.
- **ما ليس فجوةً هنا:** التواريخُ نفسُها. مُعلَنةٌ بأسبابها ومُلّاكها، والتجديدُ مسقوفٌ بـ`max_target_days=180` فلا يُمدَّد سنواتٍ بسطر. الفجوةُ **الرؤية** لا الآليّة.
- **لماذا `open`:** العلاجُ سطرٌ لا يحجب — أفقُ انقضاءٍ يُطبَع في `preflight` كما يُطبَع عددُ البوّابات المتخطّاة. ويلزمه سقفُ إنذارٍ مُعلَن (٣٠ يوماً؟) وهو قرارُ سياسةٍ لا قياس، وشريحةُ شيفرةٍ مستقلّة عن هذه.

## C6-EVIDENCE-CHAIN-EXCEPTION-AWAITS-ITS-POLICY-BASIS-01 — بطاقةُ تحكيمٍ ناقصةٌ سؤالين (فُتحت 2026-08-26 · **open**)

- **المصدر:** `docs/architecture/platform_shrink_ratchet.json` (`exceptions[0]`) · `docs/architecture/platform_python_module_baseline.json:722` · `sahool-brain/decisions/ledger.md:1959` · الموضوع `services/sahool-platform/api/irrigation_decision_evidence_chain.py` بمالكٍ `IRR-CORR1-evidence-chain` وتاريخِ إغلاق `2026-12-31`.
- **المقيس:** مستهلكٌ واحدٌ للوحدة، وهو **ملفُّ اختبارها** — بمسحٍ كاملٍ للشجرة. و**C6 الحيُّ غيرُ مُدَّعى**، ولا مُنتِجَ لسلسلة أدلّة الريّ ولا مستهلك.
- **شرطُ الإغلاق المُسجَّل:** مستهلكٌ حيٌّ في مسار أدلّة C6، **أو** انتقالٌ إلى خدمته المالكة — ولا إعفاءَ عدّ (`count_only_waivers_forbidden`).
- **وسؤالُ «ماذا يفعل انقضاءُ التاريخ؟» سقط من البطاقة:** يحسمه الكودُ لا المالك (انظر الفجوةَ أعلاه). فبقي سؤالان، وكلاهما **سياسةٌ لا قياس**: (أ) أيُقبَل التأجيلُ أساساً مُعترَفاً به أم يُسحَب الآن؟ (ب) إن تعذّر «مستهلكٌ حيّ»، أيُقبَل «الانتقالُ إلى الخدمة المالكة» إغلاقاً؟
- **لماذا `open`:** لا قرارَ من المالك بعد. ولا يُسجَّل حكمٌ لم يصدر — والبطاقةُ مسودّةٌ في `LIVE_EVIDENCE_PATH_v2.1` §٧ لا سجلٌّ.

## A-QUEUE-WITH-NO-TERMINAL-STATE-REPUBLISHES-FOREVER-01 — طابورٌ بلا حالةٍ نهائيّة (فُتحت 2026-08-27 · **open**)

- **المصدر:** `services/sahool-platform/api/phase_runtime_workers.py::run_model_registry_once` — حلقةُ الترقيات.
- **المقيس:** شرطُ الالتقاط `WHERE decision='promote'` **بلا أيّ انتقالِ حالةٍ نهائيّة**. فالصفُّ الذي عولج تبقى `decision` فيه `'promote'`، ويُلتقَط ثانيةً في الدورة التالية — و`_publish_nats("sahool.model.promotion.requested", …)` يُطلَق في كلّ مرّة. أمّا `INSERT … ON CONFLICT DO UPDATE` على `model_serving_aliases_runtime` فيُخفي الأثرَ في الجدول لأنّه مُتماثِلُ الاستدعاء — لكنّ **النشرَ ليس كذلك**.
- **اكتُشِفت عرَضاً** أثناء `WORKER-CLAIM-NOT-PINNED-BY-A-TRANSACTION-01`: بناءُ نمط المطالبة تطلّب تحديدَ «متى يخرج الصفُّ من البِركة»، فظهر أنّه **لا يخرج أبداً**.
- **ما غيّرته شريحةُ المطالبة، وما لم تُغيّره:** المطالبةُ تمنع **عاملَين متزامنَين** من نشرِ الصفّ نفسِه في الدورة الواحدة — وهذا مُصلَحٌ ومُكذَّب. ولا تمنع إعادةَ النشر **عبر الدورات**، لأنّ الصفَّ يعود إلى البِركة فور تحرير المطالبة. فالعطلُ سابقٌ للشريحة وباقٍ بعدها.
- **لماذا `open`:** العلاجُ انتقالُ حالةٍ (`promoted` / `acknowledged`) يخصّ **عقدَ الترقية** لا إصلاحَ التزامن: يلزمه حسمُ متى تُعَدّ الترقيةُ منتهية — أعند النشر، أم عند إقرارِ خلفيّةِ التقديم؟ وذلك قرارُ عقدٍ لا اشتقاقٌ من قياس، وشريحةُ شيفرةٍ مستقلّة.
- **حدُّ صدق:** ساكن — من بنية الاستدعاء وشرطِ الالتقاط. لم يُشغَّل عاملٌ على PostgreSQL حيّ.

## A-TEST-THAT-PINS-TODAYS-TREE-AS-A-SECURITY-INVARIANT-01 — لقطةٌ تاريخيّةٌ تُقرأ ثابتاً أمنيّاً (فُتحت 2026-08-28 · **fixed**)

- **المصدر:** `tests_v9/test_gate01_frozen_path_guard.py::test_the_live_authorization_is_spent_and_no_longer_grants` (التأكيد الأخير المنزوع) · `scripts/ci/gate01_frozen_path_guard.py::stale_authorization_errors` · `docs/architecture/gate01_policy.json` (`state_semantics_ar`).
- **المقيس — تناقضٌ يجعل آليّةً مُعرَّفةً في السياسة مستحيلةً:** اختباران على الشجرة الحيّة، أحدُهما يشترط أن تكون بايتاتُ كلّ سجلٍّ `ISSUED` **حاضرةً** في الشجرة، والآخرُ يُمرِّر `touched=set()` إلى `stale_authorization_errors` ويشترط **صفرَ أخطاء** — وتلك الدالّةُ ترصد بالضبط `ISSUED` + بايتاتٌ حاضرة. فالمحصّلة `ISSUED ⇒ بايتاتٌ حاضرة ⇒ يُرصَد بائتاً`، أي أنّ الحالة `ISSUED` مستحيلةٌ في أيّ شجرة — بينما السياسة تُعرِّفها آليّةَ التفويض المقيَّد نفسَها (`CLOSED → تفويضٌ مقيَّد → ISSUED → استعمالٌ واحد → CONSUMED`).
- **وأين ليس الخلل:** الحارسُ صحيح. بالمسّ الحقيقيّ (`touched` = مسارا التفويض) يُرجِع **صفرَ أخطاء**؛ `set()` المُصمَتة وحدَها تصنع الفشل.
- **ولماذا مرّ:** كان التأكيدُ **صادقاً يوم كُتِب** — لم تحمل الشجرةُ حينها إلّا سجلّاً `CONSUMED` واحداً بعد #837. فثُبِّتت **حالةُ المستودع** مكانَ **ثابت السياسة**، ولم يظهر الأثرُ إلّا عند أوّل تفويضٍ جديد.
- **العلاج:** نُزِع التأكيدُ وحدَه (لا الاختبار ولا الحارس ولا الآليّة)، وحلّ محلَّه `test_every_live_record_is_consistent_across_state_bytes_scope_and_lifecycle` — يقيس **العلاقة** (الحالة ↔ البايتات ↔ النطاق ↔ دورة الحياة) لا اللقطة. ومصادرُ التوقّع ثلاثةٌ مستقلّة (السياسة · إعلانُ السجلّ · `git hash-object`) فلا `expected = discover_actual_tree()`.
- **مُكذَّبٌ ستّ مرّات**، أربعٌ منها مُسجَّلة في `guard_mutation_registry.json` على السجلّ **المختوم** (نطاقٌ غيرُ مجمَّد · أساسٌ مخالف · بلا `merge_sha` · بايتاتٌ تخالف الشجرة) — وشُغِّلت بالمكنسة فقُتِلت أربعتُها. وذراعان تخصّان `ISSUED` وحدَه لم تُسجَّلا عمداً: التفويضُ الحيُّ يُختَم بعد الدمج فتصير مرساةُ `find` بائتةً ⇒ `STABLE_WRONG_TEST`.
- **القاعدةُ المستخلَصة (بحكم المالك):** **لا يجوز لاختبارٍ تشغيليّ أن يحوّل لقطةً تاريخيّةً إلى ثابتٍ أمنيّ.** `حالةُ المستودع الراهنة ≠ ثابتُ السياسة`. وموضعُها الطبيعيّ وثيقةُ IFOTS — **ولا وجود لها في الشجرة** (لا ملفّ ولا إشارة)، فسُجِّلت هنا ولم يُدَّعَ تعديلُ وثيقةٍ غير موجودة.

## GATE01-GRANT-IS-NEITHER-TIME-BOUND-NOR-USE-COUNTED-01 — منحةٌ بلا ساعةٍ ولا عدّاد (فُتحت 2026-08-28 · **open**)

- **المصدر:** `scripts/ci/gate01_frozen_path_guard.py::_authorization_errors` · `docs/architecture/gates/adjudications/*.json` · معيارُ المالك «GATE-01 Constrained Delegation Standard» (§٣ §٤ §٥ §١١).
- **المقيس — ثلاثةُ تقييماتٍ متتالية للمنحة نفسِها:**
  ```
  استعمالٌ ١: used=GATE01-ADJ-2026-08-28-001 · errors=0
  استعمالٌ ٢: used=GATE01-ADJ-2026-08-28-001 · errors=0
  استعمالٌ ٣: used=GATE01-ADJ-2026-08-28-001 · errors=0
  ```
  فـ`one_time: true` **ليس مفروضاً زمنَ الـPR**: كلُّ تقييمٍ مستقلٌّ ولا عدّاد استعمالات. المفروضُ فعلاً هو **الكشفُ بعد الدمج** عبر `stale_authorization_errors` (بايتاتٌ هبطت + لا مسّ ⇒ يُرصَد). أي أنّ الوعد رَصديٌّ لاحقٌ لا منعٌ سابق.
- **وأثرُه العمليّ المحصور:** أيُّ PR أخرى تُنتِج **البايتات نفسَها** في المسارين تمرّ بالمنحة نفسِها ما دامت `ISSUED`. ومسٌّ ببايتاتٍ مختلفة يُرفَض (مقيس: `used=None · errors=4`) — فالخطرُ ليس تنفيذَ شيفرةٍ أخرى بل استهلاكَ منحةٍ واحدةٍ مرّتين.
- **ولا حقلَ انتهاءٍ أصلاً:** حقولُ الزمن في السجلّ هي `adjudicated_on` وحدَه — لا `issued_at` ولا `expires_at`. فمنحةٌ نُسِيت تبقى صالحةً بلا أجل، وهو ما ينهى عنه §٥ من المعيار (وصولٌ مرتفعٌ يجب أن يكون مؤقّتاً).
- **وما هو مُنفَّذٌ فعلاً وقويّ:** الربطُ بالبايتات (`authorized_patch_sha256`) يُحقّق ما يطلبه §٣ من ربطٍ بالـSHA وأقوى: «نسخةٌ أخرى من الشيفرة» تعني بصماتٍ أخرى تعني رفضاً — مقيسٌ ومُكذَّب. و`require_exact_head_sha` **منفَّذٌ ومُختبَر** لكنّه مُطفأ بسببٍ مقيس: ملفُّ التفويض يُلتزَم **داخل** الرقعة، فأيُّ رأسٍ يُكتَب فيه يسبق الرأسَ النهائيّ بالضرورة؛ وتحرّكت `main` خمسَ مرّاتٍ أثناء #954 وحدها.
- **لماذا `open`:** العلاجُ يمسّ الحارسَ نفسَه (حقولُ أجلٍ · عدّادُ استعمال · رفضٌ عند الانتهاء)، وهو **تشديدٌ لا ترخيص** — لكنّه شريحةٌ مستقلّةٌ لا تركب على #954، وتلزمها طفراتُها.
- **حدُّ صدق:** المقيسُ سلوكُ `evaluate` على شجرةٍ واحدة. ولم يُقَس تزامنٌ حقيقيّ لأنّ الآليّةَ ليست خدمةً: قراءةُ ملفٍّ زمنَ CI، والدمجُ يُسلسِلها. فمطلبُ §٤ «استهلاكٌ ذرّيّ» لا يُترجَم حرفيّاً هنا، ومكافئُه الصحيح **عدّادُ استعمالٍ يُختَم عند الدمج**.

## GATE01-DELEGATION-STANDARD-NOT-YET-A-CONTRACT-01 — معيارٌ مُقرَّرٌ بلا تنفيذ (فُتحت 2026-08-28 · **open**)

- **المصدر:** حكمُ المالك 2026-08-28 («GATE-01 Constrained Delegation Standard» · مصفوفةُ التجاوز · طبقاتُ الاختبار الثلاث) · `docs/architecture/gate01_policy.json` · `tests_v9/test_gate01_frozen_path_guard.py`.
- **المُقرَّر:** `Default Deny + Least Privilege + JIT + Time-Bound + Scope-Bound + Approval + Audit + Automatic Expiry`، وفصلٌ صريحٌ بين **انتقالِ المرحلة** (`CLOSED → OPEN`) و**التفويضِ المقيَّد** (`CLOSED → ISSUED → CONSUMED → CLOSED`) — لا يُستعمَل أحدُهما بديلاً عن الآخر.
- **المُنفَّذُ اليوم من المعيار:** النطاق (`allowed_paths ⊆ frozen_paths`) · الربطُ بالبايتات · الأساس · مفرداتُ الحالة · الرفضُ عند الاستهلاك أو الإلغاء · الرصدُ بعد الدمج · `one_time:false` مرفوضٌ صراحةً · واتّساقُ الشجرة الحيّة (أُضيف اليوم).
- **غيرُ المُنفَّذ:** أجلٌ زمنيّ · عدّادُ استعمال · هويّةُ طالبٍ مقابلَ مُوافِق (فصلُ الواجبات) · حقولُ تدقيقٍ كاملة (لماذا · مَن · لأيّ عمليّة) · **مصفوفةُ التجاوز** (API · Worker · Event · Retry · Replay · Direct adapter) · الطبقاتُ الثلاث (نموذجٌ مرجعيّ · property-based · تفاضليّ) · ومعايرةُ الاختبارات على تنفيذاتٍ معطوبةٍ مصطنَعة (`VULN-01…05`).
- **وأثقلُ ما ينقص ليس اختباراً:** التحقّقُ يقع في CI على الفرق، **ولا شيء يتحقّق عند آخر نقطةٍ قبل الأثر الفيزيائيّ** (§٨ من المعيار). فحارسُ المسارات يمنع دخولَ الشيفرة، ولا يمنع تنفيذَها لو دخلت بطريقٍ آخر.
- **وIFOTS-HARD-GATE-G01 غيرُ قابلٍ للتسجيل بعد:** لا وثيقةَ IFOTS في الشجرة (لا ملفّ ولا إشارة، بمسحٍ كامل). فالقاعدةُ مسجّلةٌ هنا ولم يُدَّعَ تعديلُ وثيقةٍ غير موجودة.
- **لماذا `open`:** برنامجٌ لا شريحة، ويمسّ الحارسَ والسياسةَ ومسارَ التنفيذ. ولا يُركَّب على #954: تلك تحمل تفويضاً مقيَّداً واحداً وإصلاحَ اختبارٍ واحد.

- **تحديث `GATE01-AUTHORIZATION-ORIGIN-UNENFORCED-01` (2026-08-28):** أُطلِق البندُ المشروط **لأوّل مرّة** على #954 — أوّلُ رقعةٍ تمسّ `docs/architecture/gates/adjudications/` منذ بُني الإنفاذُ في #844 (2026-08-14). فصار للفجوة **حالةٌ مقيسة** بدل وصفٍ نظريّ: `require_code_owner_review = [False]` بينما `.github/CODEOWNERS` يُسمّي المالك — أي أنّ الملفّ خاملٌ كما حذّر متنُه. وحكمُ المالك: **الكود GO · الحوكمة NO-GO** حتّى مراجعةٍ مستقلّة؛ ويلزمها **مالكُ كودٍ ثانٍ** لأنّ صاحبَ الـPR هو المالكُ الوحيد وGitHub لا يقبل مصادقةَ المرء على رقعته. تبقى `open`: العلاجُ إعدادٌ خارج المستودع + هويّةٌ ثانية، ولا يُغني عنه شيءٌ في الشجرة.
## TWO-NAMES-FOR-ONE-DIGEST-IS-NOT-A-RETRY-IDENTITY-01 — مفتاحُ تكرارٍ بلا معلومة (فُتحت 2026-08-28 · **open**)

- **المصدر:** `shared/autonomous_farm_os_phase9.py:210,216,224` · `shared/iot_execution_runtime.py:205,263` · `migrations/v109_phase9_iot_execution_adapters.sql:5-23` · `services/sahool-platform/api/phase_runtime_store.py:185,393` · البطاقة `docs/architecture/m03_command_path_adjudication.md` §٣أ–٣ب.
- **رأسُ القياس:** `main @ 90df6145`.
- **المقيس (أ):** `command_id` و`idempotency_key` يُشتقّان من **المادّة نفسِها** بـ`_stable_id`، والبادئةُ خارج المعمّى ⇒ `cmd_20cea6228512` مقابل `idem_20cea6228512` — بصمةٌ واحدةٌ باسمين. فـ`idempotency_key` لا يحمل بايتاً لا يحمله `command_id`، ولا يستطيع تمييزَ «محاولةٍ ثانية» عن «الأمر نفسِه» — وتلك وظيفتُه المُعلَنة في §٣.
- **المقيس (ب):** `idempotency_key` **ليس عموداً** في `iot_command_dispatch`. القيدُ الوحيدُ على المسار الحيّ `UNIQUE (tenant_id, envelope_id)`، والمفتاحُ ينجو داخل `adapter_receipt::jsonb` وحدَه حيث لا يبلغه قيد.
- **والأثرُ مقيسٌ بالمخطِّط والمُغلِّف الحقيقيَّين:** `envelope_id ← {execution_id, command_id, protocol}`، و`execution_id ← {recommendation_id, gate, commands}`، و`gate` يحمل `max_authorized_effect` المبنيَّ من **السياسة**. فتحريرُ `max_water_mm` من ٢٥ إلى ٣٠ — ولا يمسّ الأمرَ — يُنتج `env_6cef466e2e2a` ثمّ `env_34654ffbe56a` بينما `idem_107b62a47c99` ثابت، وكلا التخطيطين `dispatch_ready`. فلا تصادمَ على القيد ⇒ صفٌّ ثانٍ ونشرٌ ثانٍ للأمر نفسِه.
- **ويُغيّر كلفةَ توصيةٍ قائمة:** `ON CONFLICT (idempotency_key) DO NOTHING` موجودٌ في `actuator_command_outbox` وحدَه — أي أنّ الموضعَ الوحيدَ الذي يمنع التكرار بالمفتاح الصحيح هو الصندوقُ الميّت. فتوصيةُ §٢ أ‑٢ («يُعلَن مهجوراً») تُسقِط العقدَ نصّاً بعد أن سقط أثراً. لا يجعلها خطأً؛ يجعل ثمنَها غيرَ ما هو مكتوب.
- **لماذا `open`:** كلا العلاجين قرارُ مالك لا اشتقاقٌ من قياس — إضافةُ العمود هجرةٌ على مسارٍ مجمَّد خلف `GATE-01`، وفصلُ `command_id` عن `idempotency_key` تغييرُ عقدِ هويّة.
- **حدُّ صدق:** ساكنٌ واشتقاقٌ محلّيٌّ لدوالَّ صِرفة — لا قاعدةَ حيّة ولا عامل. ولم يُقَس أنّ منشوراً حيّاً يُعيد التخطيط بعد تحرير سياسة؛ المقيسُ أنّه **إن فعل** فمفتاحُ المنع يتغيّر.

## CARD-CITES-A-TREE-THAT-MOVED-01 — بطاقةُ تحكيمٍ بلا حارسٍ لاستشهاداتها (فُتحت 2026-08-28 · **fixed**)

- **المصدر:** `docs/architecture/m03_command_path_adjudication.md` §٣أ–٣ب · `tests_v9/test_m03_card_citations_are_live.py` · حاجب `no-report-only-change` على #958.
- **المقيس:** البطاقةُ تُبنى عليها قراراتٌ (أ‑١/أ‑٢ · ب‑١/ب‑٣) وتُقاس أثمانُها، **ولا شيء كان يتحقّق أنّ مصادرَها لا تزال تقول ما نُسِب إليها**. و`CLAUDE.md` يشترط «لا معلومة بلا مصدر» — والشرطُ كان على الكاتب لا على الشجرة.
- **وأثبت الاختبارُ نفسَه فورَ كتابته:** كذّب دعوى §٣ب أنّ الصندوقَ الميّت هو «الموضعُ الوحيدُ **في الشجرة**» الذي يُديدِب على `idempotency_key`. المقيس موضعان: `phase_runtime_store.py:185` و`services/sahool-platform/api/routers/edge.py:42`. صُحِّحت الدعوى إلى **مسار الأوامر**، وسُجِّل التصويبُ في البطاقة.
- **وليس تثبيتاً للعطل:** الحالاتُ تؤكّد أنّ **الاستشهادَ حيّ** لا أنّ الخللَ قائم؛ فهبوطُ العلاج (v109 يكتسب العمود) يُحمِّرها برسالة «حدِّث البطاقة» لا «أعِد العطل».
- **مُكذَّبٌ أربعَ مرّات:** استشهادٌ بملفٍّ معدوم · زوالُ قسم ٣أ · v109 يكتسب العمود · إسقاطُ موضعِ ديدوبٍ معروف — قُتِلت أربعتُها.

- **تصويبُ قياسٍ في `AN-ABSTRACTION-THAT-HIDES-THE-TABLE-SHRINKS-A-BLOCKING-RATCHET-01` (2026-08-28):** أُعلِن أوّلاً أنّ الأساس هبط **٩٣ ⇒ ٨٩** وأنّ الحارسَ «صار أعمى عن `iot_command_dispatch`». **وكلاهما مبالغة، والتصحيحُ مقيس:** الحقلُ القانونيّ `violation_count` هبط **٧٥ ⇒ ٧٣** (والـ٩٣⇒٨٩ مجموعُ مواضع الكتابة داخل المفاتيح لا عددُ المخالفات). والمفتاحان الزائلان هما `marketplace_plugin_execution_runs::sahool-platform` و`marketplace_plugin_runtime_events::sahool-platform` فقط؛ و**`iot_command_dispatch::sahool-platform` باقٍ** في الأساس عبر `phase_runtime_store.py` الذي لا يزال حرفيّاً. فالفقدُ إسهامُ **العامل** في ذلك المفتاح لا المفتاحُ نفسُه. والفجوةُ تبقى `open`: انحدارُ رؤيةٍ حقيقيّ (مفتاحان + أربعةُ مواضع) على راتشِتٍ لا يصعد — لكنّه أضيقُ ممّا أُعلِن.
## E2E-20260902-RUNTIME-STATE-AND-MARKET-REPAIRS — FIXED_IN_CODE (2026-09-02)

- **المصدر:** تقرير E2E الحيّ `evidence/e2e-20260902T181647Z/<domain>/` كما سلّمه المالك، ثم قياس الشجرة على `9b1f630b`: عشرة موجّهات تستورد `_DB_POOL` وقت تحميل الوحدة؛ `mfa.py` ينادي `main.mfa_crypto/main.pyotp` غير المصدّرين؛ وMarket ينادي ستة جداول لا تنشئها أي هجرة ويضبط `set_config(..., true)` خارج معاملة.
- **العلاج:** قراءة `api_main._DB_POOL` وقت الاستعمال في الملفات العشرة؛ تمرير `UserSchema` إلى `tenant_connection`؛ استيراد MFA المباشر مع مفتاح تشفير مطلوب في compose؛ هجرة أمامية `v229_market_mcp_schema.sql`؛ سياق `tenant_connection` معاملاتي لكل عمليات Market؛ فكّ JSONB النصّي قبل حارس الهندسة؛ 422 صريح لمدخل WOFOST غير الصالح.
- **outbox:** صار `FEATURE_NATS_PUBLISHERS` و`JOBS_DATABASE_URL` و`NATS_URL` يصل إلى حاوية المنصّة. الحالة **CODE_READY** فقط: الافتراضي يبقى `false` عمداً، ويلزم تشغيل staging مع الراية وقياس تناقص `event_outbox` قبل الإغلاق الحي.
- **التكذيب:** `tests_v9/test_platform_runtime_db_contract.py` و`tests_v9/test_e2e_findings_regressions.py` وحارس GUC، مع الجناح المتأثر: **135 passed · 3 skipped · 0 failed**.
- **الحالة:** `FIXED_IN_CODE`، لا `CLOSED_LIVE`. لم تُبنَ صور ولم تُطبَّق v229 على PostgreSQL حيّ ولم يُختبر outbox→NATS في هذه الجلسة. `runtime_verified=0` · `production_certified=0`.

- **تحديث `FROZEN-PATH-LIST-NAMES-A-FILE-THAT-DOES-NOT-EXIST-01` (2026-08-29) — `open` ⇒ `fixed` في شقٍّ و`open` في آخر.** **الكشفُ والتشخيصُ ليسا لي:** سجّلتهما جلسةٌ أخرى في الصفّ أعلاه مع #960، ومنها اقتُبِس العلاجُ الأدنى حرفيّاً («شرطٌ يُحمِّر حين يحمل مدخلُ `not_yet_in_tree` اسمَ ملفٍّ قائمٍ في الشجرة عند مسارٍ آخر»). ونُفِّذ هنا بأمر المالك بعد أن رفضته تلك الجلسةُ مرّتين بوصفه توسيعَ نطاقٍ يخصّ المالك — **وهو رفضٌ كان في محلّه**.
  - **وقياسٌ يُضاف إلى تشخيصهم ويشدّده:** `migrations/run_migrations.sql` **لم يوجد في تاريخ المستودع كلِّه** — صفرُ التزاماتٍ تمسّه، مقيسة. فالتجميدُ عليه لم يكن «يحرس اسماً لن يُمَسّ» فحسب، بل **فارغاً منذ كُتِب في #837**. ونصُّ السياسة الذي يقول إنّ المدخلين «من الشريحة المحجوبة لم يُدمَجا قطّ» صحيحٌ في v228 و**خطأٌ في المُشغِّل**؛ صُحِّح.
  - **الشقُّ المُغلَق:** مسارُ v228 صُحِّح إلى `migrations/v228_worker_claim_lease.sql` فصار مجمَّداً فعلاً (كلفةٌ صفر: التزامان). وأُضيف `alias_escape_errors` حاجباً **يعمل دائماً** لا عند المسّ — فتجميدٌ يحرس اسماً لا يُكتشَف بالمسّ بل بوجود النظير.
  - **الشقُّ الباقي `open`:** `scripts_v9/run_migrations.sql` مُقَرٌّ في `alias_mismatch_acknowledged` بـ`owner_decision: PENDING`. **إقرارٌ لا إعفاء، وضيّقٌ بالبناء** — يُسمّي النظيرَ بعينه، فنظيرٌ آخر يبقى حاجباً. وسببُ التأجيل مقيس: التصحيحُ يُجمِّد ملفّاً عُدِّل **٦٩ مرّةً**، فيصير كلُّ تسجيلِ هجرةٍ محتاجاً تفويضاً.
  - **مُكذَّبٌ أربعاً** (إعادةُ المسار القديم · نزعُ الإقرار · إقرارٌ بنظيرٍ خاطئ · إقرارٌ بلا `live_alias`)، ومُسجَّلتان في سجلّ الطفرات. **وجولةٌ أولى أُلغِيت لبطلانها:** `git checkout` سابقٌ أعاد السياسة، فماتت ثلاثٌ بـ`KeyError` في سكربت الزرع لا بحجب الحارس.
  - **وحدُّ صدق:** يُغطّى صنفان من النظائر (رقمُ الإصدار · الاسمُ في مجلّدٍ آخر) لا كلُّ إعادة تسمية؛ ونظيرٌ بمحتوًى مطابقٍ واسمٍ ورقمٍ مختلفَين **لا يُرصَد**.

## CERTIFICATION-BLOCKER-WITHOUT-A-DECLARED-PRODUCER-01 — أربعُ وظائفِ «دليل» لا تكتب دليلاً (فُتحت 2026-09-03 · **fixed**)

- **المصدر:** `.github/workflows/production-certification-blockers.yml` (كلّ الملفّ قبل هذه الشريحة) · `scripts/ci/production_evidence_pack_guard.py:23-76` (`BLOCKERS`) · `scripts/ci/production_certification_blockers_status.py:84-134` · `docs/architecture/certification_evidence_producers.json` · حارس `scripts/ci/certification_evidence_producer_guard.py`.
- **رأسُ القياس:** `main @ ee0bdfc6`.
- **المقيسُ بالتنفيذ لا بالوصف:** الوظائفُ الأربع تستنسخ الشجرة، تُشغّل فحصَها، ثمّ تطبع حالةَ ملفّاتِ الأدلّة **المودَعة كما هي**؛ ووظيفةُ الحكم تستنسخ من جديدٍ فتقرأ النائبات نفسَها. `python3 scripts/ci/production_certification_blockers_status.py --require-certified` على الشجرة ⇒ خمسةُ حواجزَ كلُّها `pending` و`rc=1`. **لا `upload/download-artifact` في الملفّ كلِّه.** فالاعتمادُ لم يكن صعباً؛ كان **مستحيلاً** — وبوّابةٌ لا تُغلَق بعملٍ صحيح تُقرأ بمرور الوقت دعوةً إلى تلفيق مُدخَلها بدل إصلاح مُنتِجه.
- **⚠ والعلاجُ الظاهر كان سيختلق.** «فلتبعث كلُّ وظيفةٍ دليلَها» يبدو ميكانيكيّاً، و**ثلاثٌ من الأربع تقيس شيئاً غير الحاجب المسمّى بها** — مقيسٌ في الشجرة لا مظنون: `P-CERT-1` «Full branch CI» تُشغّل `runtime_real_smoke.sh` وحدَه · `P-CERT-3` «Redis live» تحجب على سرٍّ **يتجاهله السكربت** ويُثبِّت `redis://…@127.0.0.1:6380/0` في سطره الأخير · `P-CERT-4` «model provisioning» تفحص اتّساقَ العقد، والمانيفستُ نفسُه يقول `packaged_in_repository=false` و`operator_must_provision=true` وافتراضُ compose `partial`/`false`. فالانبعاثُ الآليّ كان سيحوّل **أداةَ الصدق إلى مصدرِ الكذبة**.
- **ما أُغلِق:** حلقةٌ من ثلاثٍ — الإنتاجُ في خطوةٍ **تالية** للقياس فهي غيرُ قابلةِ البلوغ ما لم يمرّ (شرطُ وصولٍ لا فحصٌ يُخدَع) · العبورُ بمصنوعاتٍ **بعد مسحِ الاستنساخ** (`--purge`)، وبدونه يمرّ دليلٌ `verified` **مودَعٌ بـ`git add`** بقيمِ أصلٍ عامّةٍ يعرفها أيُّ مؤلّف · والتوقيعُ بـ`actions/attest` بهويّة Sigstore — الحقلُ الوحيدُ في الحزمة الذي لا يملك مؤلّفُ الشجرة إصدارَه.
- **و`P-CERT-1` عولج بشاهدٍ حقيقيّ لا بختم:** `collect_full_branch_ci_evidence.py` يسأل واجهةَ Actions عن عدّاء `ci.yml` على `GITHUB_SHA` نفسِها، ولا يقبل إلّا **مكتملاً وخُلاصتُه `success`**، وينقل أسماءَ الوظائف وخُلاصاتِها كما هي (العددُ يُخفي أيَّ وظيفةٍ تخطّت).
- **وتعريفٌ ثانٍ أُزيل:** `compile_transitive_service_locks.sh` كان يكتب ملفَّ دليله بيده — يقرأ `GITHUB_*` بنفسه، ويضع `verified` بنفسه، ويهبط إلى `evidence_attached` بمقارنةِ سلسلةٍ حارسة (`local-untrusted`) — **بلا تحقّقٍ من الحقول الدنيا**، فينتج دليلاً يقبله الكاتبُ ويرفضه المُحكِّم بعد وظيفتين. بقي فيه **قياسُ الأقفال** وذهب الباقي إلى الباعث الواحد.
- **ولمَ عقدٌ لا كتمان:** `state: no_honest_producer` بسببه المقيس، ويحرسه حارسٌ يرفض **انبعاثاً** لحاجبٍ مُعلَنٍ هكذا — فالإعلانُ لا يبقى نصّاً يُخالِفه العمل. مَن أراد ختمَ حاجبٍ بلا مُنتِجٍ صادق يصطدم بسطرٍ يقول لماذا لا يُختَم.
- **مقيس:** ٢/٥ حواجزَ لها مُنتِجٌ صادق · ٣ مُعلَنةٌ بأسبابها · ١٨ اختبار وحدة · **٤/٤ طفرات مقتولة** تحت `guard_mutation_guard --run`.
- **حدُّ صدقٍ مُعلَن:** **الحكمُ يبقى `production_certified=false`** — هذه الشريحة لا تعتمد المنصّة ولا تدّعي ذلك، ويحرس الادّعاءَ المعاكسَ اختبارٌ صريح. والفرقُ أنّ سببَه صار ثلاثةَ مُنتِجين غائبين **مُسمَّين** بدل «لا شيء يُنتِج شيئاً». والـworkflow نفسُها `workflow_dispatch` فلم تُشغَّل في هذه الشريحة: المقيسُ ساكنٌ ومحلّيّ.

## RESTORE-TARGETED-A-HOST-THAT-DOES-NOT-EXIST-01 — والتعليقُ يدّعي التطابق (فُتحت 2026-09-04 · **fixed**)

- **المصدر:** `scripts/backup_postgres.sh:33,35` (`sahool-postgres`/`sahool_user`) · `scripts/restore_postgres.sh:24-27` قبل الإصلاح (`sahool-postgis`/`postgres`) · `docker-compose.v9.yml:243-255` (الخدمة القانونيّة واسمُها ودورُها) · `tests_v9/test_infra_hardening_72h_static.py:57-63` قبل التوسعة.
- **رأسُ القياس:** `claude/cert-evidence-loop @ 78b04644` (الأساس `main @ 912ad691`).
- **المقيس:** الاستعادةُ تقصد مضيفاً ودوراً **لا وجودَ لهما** في الملفّ القانونيّ — الاسمُ يعيش في `docker-compose.light.yml:357` وحدَه وبدورٍ ثالثٍ هو `sahool_app`. وسطرُها الأوّل يقول «من env، **نفس قيم** `backup_postgres.sh`»: انحرافٌ يحمل معه **دعوى عدم الانحراف**، فلا يفحصه قارئ. والاكتشافُ يقع في اللحظة الوحيدة التي لا تحتمله: بعد فقدِ البيانات.
- **وحارسٌ كان يحرس نصفَ الزوج:** `test_backup_script_targets_real_service_and_role` يفرض الزوجَ الصحيح على النسخ الاحتياطيّ وحدَه، ويسمّي `sahool-postgis/postgres` خطأً **بالحرف** — وهو بعينه ما كان في الاستعادة، بلا أن ينظر إليه.
- **العلاج:** `scripts/lib/pg_conn_defaults.sh` مصدرٌ واحدٌ يقرأ منه الطرفان (إلغاءُ الجدول الثاني لا مطابقتُه)، والاختبارُ يشتقّ الزوجَ من `docker-compose.v9.yml` نفسِه ويرفض أيَّ تعريفٍ محلّيٍّ ثانٍ. **مُكذَّبٌ بزرعين** (إعادةُ الجدول · انحرافُ المصدر عن compose) وكلاهما يُحمِّر حالتين.
- **المصدر الأوّل للكشف:** مراجعةٌ خارجيّة نقلها المالك في هذه الجلسة؛ والقياسُ والتوسعةُ هنا.
- **حدُّ صدقٍ مُعلَن:** أُصلِحت **الوجهة** ولم تُثبَت الاستعادة. **لا drill حيّ جرى**، وPITR غير موصول، ولا إثباتَ حيّ لتزويد الأسرار من مدير أسرار. تبقى الاستعادةُ P0 مفتوحةً بوصفها **قدرةً**، ومغلقةً بوصفها **عنواناً**.

## FORECAST-RAIN-IS-INERT-ON-THE-FIELD-IRRIGATION-PATH-01 — يُوصى بالملء عشيّةَ المطر (فُتحت 2026-09-04 · **MITIGATED**، تبقى مفتوحةً حتّى المعايرة الميدانيّة)

- **المصدر:** `services/sahool-platform/api/weather_advice.py:137-138` (العقد: «المطر المتوقّع **لا يدخل في الكمّيّة** — يُستخدم فقط لخفض الإلحاح») · `services/sahool-platform/api/routers/irrigation_recommendation.py` (استجابةُ `recommendation` تُصدِّر `urgency` ولا تُصدِّر `timing_ar` ولا `rationale_ar`).
- **رأسُ القياس:** `claude/cert-evidence-loop @ 41918184`.
- **المقيس بالتنفيذ:** بثبات `depletion_mm=60`، تمريرُ `forecast_rain_mm=25` **لا يُغيّر شيئاً في الاستجابة**: `net_irrigation_mm=5.9` و`target_refill_mm=48.0` و`urgency=moderate` و`should_irrigate=True` — قبلَه وبعدَه. والنواةُ نفسُها **تُغيّر** ثلاثةَ حقول (`urgency` moderate⇒low · `timing_ar` «خلال ٢٤ ساعة»⇒«خلال الأيّام ٢-٣ القادمة» · `rationale_ar` تكتسب «مطر متوقّع (25 مم خلال ٤٨ ساعة) — انتظِر قبل الريّ»)، لكنّ اثنين منها لا يُصدَّران، والثالثَ يقوده الاستنزاف/الإجهاد فيبتلعه.
- **الأثر:** يُوصى المزارعُ بملءٍ ≈٤٨ مم عشيّةَ مطرٍ متوقَّعٍ **لا يُذكَر له بحرف**.
- **لماذا `open` لا مُصلَحة:** تعديلُ قرار الإطلاق ليُنصِت للمطر المتوقّع **قرارٌ زراعيّ** (كم مم خلال كم ساعة يؤجّل ريّاً، وبأيّ ثقةٍ في التوقّع) لا يُتَّخذ داخل شريحةِ إصلاحِ مُدخَل. وتصديرُ `timing_ar`/`rationale_ar` أرخصُ منه وأقلُّ خطراً — وهو أوّلُ ما يُقترَح.
- **كُشِف** أثناء كتابة الشاهد الموجب لـ«المطر المفقود ≠ صفر»: احمرّت الحالةُ لأنّها انتظرت نقصانَ الكمّيّة من المطر المتوقّع، فقادت إلى قراءة العقد بدل تثبيت سلوكٍ معدوم.

- **تخفيفٌ هبط في اليوم نفسِه (`forecast_rain_hold`) — ولا يُغلِقها.** استُخرِج حكمُ التأجيل القائم في `weather_advice.irrigation_advice` (`forecast_rain_mm >= 5 and net > 0 and urgency != "high"`) إلى حقلٍ `forecast_hold` **بلا تغيير شرطٍ ولا عتبة**، فصار اجتماعُه مع قرار الإطلاق من الاستنزاف يُنتِج **امتناعاً**: `should_irrigate=None` و`target_refill_mm=None` و`trigger_reason="forecast_rain_hold_requires_reassessment"`. و`net_irrigation_mm` يبقى **معلومةً حسابيّة** لأنّه احتياجٌ مقيس لا أمرُ تنفيذ. وصار `timing_ar`/`rationale_ar` يُصدَّران — وهما الموضعان الوحيدان اللذان يذكران المطرَ للمزارع — ويُمنَع `submit_to_decision` في هذه الحالة (`approval_state="blocked_forecast_rain_hold"`).
  - **حجزٌ معرفيّ لا قرارٌ زراعيّ:** لا عتبةَ مُخترَعة ولا «لا تروِ»؛ تعارضُ حكمين يُصعَّد إلى إنسان. و`None` هنا هي **نفسُ** دلالتها عند غياب Dr: لا قرارَ مُختلَق.
  - **ولمَ تبقى مفتوحة:** عتبةُ ٥مم/٤٨ساعة **غير معايَرة ميدانيّاً**، ولا يُثبِت هذا أنّها الصحيحة — يمنع الأمرَ الصامت فحسب. الإغلاقُ يتطلّب معايرةً بمرجعٍ مستقلّ.
  - **مُكذَّبٌ بأربع:** الحجز يمتنع · وبلا مطرٍ متوقَّعٍ يُطلِق (شاهدٌ موجب أنّ الحجز مشروطٌ لا دائم) · والتقديم يُمنَع أثناء الحجز · وردٌّ بلا شاهدِ حفظٍ لا يُنتِج `pending_approval`.

## ABSENT-RAIN-COERCED-TO-ZERO-AT-THREE-MORE-EDGES-01 — أُغلِقت (2026-09-04)

- **الحافّة (`services/weather-service/open_meteo.py:371`):** `normalize_daily` كان يُصفّر `precipitation_sum` الغائب بإعلانٍ صريح في `_DAILY_ZERO_COERCED_FIELD_MAP`. والحجّةُ («لا مطر قراءةٌ معقولةٌ لصفرِ مجموعٍ يوميّ») **تعتمد على المستهلك**: معقولةٌ لعرضٍ على خريطة، كاذبةٌ لكمّيّةِ ريٍّ يُطرَح منها المطر. وقد كان يمنع الفشلَ المُغلَق في المنصّة من أن يرى الغيابَ أصلاً — **حاجزٌ عند الحافّة يُبطِل فشلاً مُغلَقاً في النواة**. أُخرِج من الإعلان في الطبقتين (`open_meteo` و`canonical_weather_state`)، وإلّا بقي **قيدٌ يُعلَن ولا وجودَ له**.
  - وأمسك الحارسُ القائم `test_the_only_zero_coerced_daily_fields_are_the_declared_ones` الخروجَ بشقّه الثاني («أو أُزيل مُعلَن») كما صُمِّم.
- **الواجهة (`frontend/src/components/fieldview/AgronomyConsistencyCard.tsx:227-228`):** `parseMeasure(...) ?? 0` كان يجعل **حقلاً فارغاً يُرسَل «صفر مطر»** — أي أنّ تركَ الحقل فارغاً يُنتِج توصيةً **أسخى**. أُلحِق المطران بقاعدة الحرارة القائمة في الملفّ نفسِه (`return null` قبل الطلب)، فلا يُخفي المتصفّحُ فشلاً مُغلَقاً خادميّاً خلف رقمٍ مُختلَق.
- **المصدر:** المراجعةُ الخارجيّة سمّت الحدّين؛ والقياسُ والعلاجُ هنا.

## IRRIGATION-CANDIDATE-SUBMITTED-WITH-A-CONTRACT-THE-RECORDER-DOES-NOT-READ-01 — أُغلِقت (2026-09-04)

- **المصدر:** `services/sahool-platform/api/routers/irrigation_recommendation.py` (مسار `submit_to_decision` قبل الإصلاح) مقابل `services/sahool-platform/api/crop_decision_bridge.py:248-291`.
- **المقيس:** كان يُرسَل `recommendation` و`status: "pending_approval"` — وعقدُ `record_decision` هو `stage="candidate"` + `decision_value`. فحقلان لا يقرؤهما المُسجِّل، وقد تُحفَظ قيمةٌ فارغة. ثمّ يُستنتَج `pending_approval` **محلّيّاً من غياب استثناء** — إعلانُ نجاحٍ بلا شاهدٍ عليه، في مسارٍ يقود إلى ماءٍ يُصرَف.
- **العلاج:** إعادةُ استعمال نمط `crop_decision_bridge` نفسِه — `CANDIDATE_STAGE` **مستورَدةً لا مكرَّرةً**، و`decision_value` يحمل المرشَّح كاملاً بـ`status`/`approval_required` بداخله، ولا `pending_approval` إلّا بـ`authoritative=true` و`persisted=true` ومعرّفٍ صالحٍ و`stage` مُعاد. وإلّا `submit_unproven`.
- **حدُّ صدق:** مقيسٌ بنقطة وصلٍ مُثبَّتة (`monkeypatch`) لا بخدمةِ قرارٍ حيّة.

## A-DECLARATION-FIELD-SATISFIED-BY-PROSE-NOT-BY-REGISTRATION-01 — حقلٌ يُغلِق بوّابةً بالكتابة (فُتحت 2026-09-05 · **fixed**)

- **المصدر:** `docs/architecture/blocking_surface_additions.json` (الحقل `mutation` في أوّل إقرار) · `scripts/ci/guard_mutation_guard.py::addition_violations` قبل الإصلاح (`if not str(declaration.get(field) or "").strip()` — حضورُ نصٍّ غيرِ فارغ وحدَه).
- **رأسُ القياس:** `claude/blocking-surface-freeze @ 188c0936` (الأساس `main @ d3471e39`).
- **المقيس:** الخصائصُ الأربع تُفحَص بـ**الحضور** لا بالدلالة. وأوّلُ إقرارٍ كُتِب في الملفّ — إقرارُ الآليّة نفسِها — حمل `"guard_mutation_registry.json :: blocking_surface_advisory — … ويجب أن يحمرّ \`test_an_undeclared_addition_is_reported\`"`: اسمٌ صحيحٌ **داخل جملة**. والحقلُ كان سيقبل `"طفرةٌ ما"` بالقدر نفسِه، أي أنّ شرطاً من الأربعة **يُستوفى بحسن النيّة**.
- **الأثر:** إقرارٌ يسمّي تكذيباً **لا وجودَ له** يمرّ صحيحَ الشكل، فيُرقَّى حاجبٌ بأربع خصائصَ إحداها جوفاء — «بوّابةٌ تُغلَق بالنثر»، وهي صنفٌ من **«حارسٌ يبدو أنّه يحرس ولا يحرس»** داخل آليّةٍ موضوعُها ذلك الصنفُ بعينه.
- **العلاج:** `mutation` يجب أن يكون **اسمَ اختبارٍ مسجَّلاً لهذا الحارس بعينه** في `guard_mutation_registry.json`، مطابقةً تامّة؛ والنثرُ إلى `$mutation_ar`. و**لم يُقبَل الاحتواءُ النصّيّ عمداً** — مطابقةُ السلاسل هي بعينها ما عولج في `188c0936` قبل التزامين. و**التسجيلُ «في مكانٍ ما» لا يكفي**: استعارةُ اسمِ اختبارٍ يُكذِّب حارساً آخر تُرفَض.
- **مُكذَّبٌ بطفرتين مسجَّلتين ومقتولتين بالزرع الفعليّ** (`guard_mutation_guard.py` ⇒ ٢٥/٢٥)، **وشاهدٌ موجب** `test_a_mutation_naming_a_registered_test_passes` — بدونه يرفض الحقلُ **كلّ** إقرار، وذاك منعٌ لا تسجيل.
- **وعطلٌ ثانٍ وُلِد أثناء العلاج ومُثبَّت:** قُرِئ `mutation_test` (يُعيد **ملفَّ** الجناح) بدل `expect` (اسمُ الحالة)، فأُبلِغ عن طفرةٍ **مسجَّلةٍ** بأنّها غيرُ مسجَّلة. والاتّجاهُ هو الأسوأ: إنذارٌ كاذبٌ يدفع كاتبَ الإقرار إلى **تعطيل الفحص** لا إلى تسجيل طفرة. كشفه **تشغيلٌ لا قراءة**، وله `test_the_registry_reader_reads_the_expected_test_not_the_suite_file`.

## THE-FREEZE-LINE-WAS-A-SNAPSHOT-TAKEN-BEFORE-OTHER-WORK-LANDED-01 — أساسٌ يصف كوناً سابقاً (فُتحت 2026-09-05 · **fixed**)

- **المصدر:** `docs/architecture/blocking_surface_baseline.json` (`measured_on`/`frozen_at_sha` = `912ad691`) · `main @ d3471e39` بعد دمج #979.
- **المقيس:** بين قياسِ الأساس ودمجِ الآليّة هبطت #979 فزاد سطحُ الحجب **ستّ ثلاثيّات** (حرّاسُ أدلّة الاعتماد). واللقطةُ البائتة كانت ستُبلِّغ عنها «زيادةً بلا إقرار» — وهي **سابقةٌ للتجميد لا لاحقةٌ له**.
- **العلاج:** خطُّ التجميد = **قاعدةُ الطلبِ الذي يُنزِل الآليّة** — قاعدةٌ تسري على كلّ داخلٍ بالتساوي، لا لقطةٌ تُختار بعد رؤية النتيجة. أُعيد القياسُ على `d3471e39`: **٣٠٠ · ٢٧١ · ٤٩ ⇒ ٢٢٢ بلا تكذيبٍ مسجَّل**. ويحرسه `test_the_baseline_is_frozen_at_the_current_merge_base`.
- **حدُّ صدقٍ يُقال ولا يُطوى:** الستُّ من #979 و**كاتبُها كاتبُ هذه الآليّة نفسُه**، فتوريثُها **إعفاءٌ للنفس**. ما يجعله مقبولاً أنّه بالقاعدة لا بالاستثناء، وأنّ `legacy_blocking` **لا يشهد لها بشيء**، و**صفرٌ من الستّ** له طفرةٌ مسجَّلة — فهي في الدَّين المعلَن لا خارجَه.

## SWEEP-DRIFT-CEILING-FIRED-AND-MAIN-WAS-SITTING-ON-IT-01 — هامشٌ صفر بلا أن يُقال (فُتحت 2026-09-05 · **fixed**)

- **المصدر:** `tests_v9/test_mutation_sweep_headroom.py` (الزوجُ ٣٧٫٢٣د/٥٠٦ · الحدّ ٥٤٠) · `docs/architecture/guard_mutation_registry.json`.
- **المقيس:** `origin/main @ d3471e39` بلغ **٥٤٠ بالضبط** — أي أنّ البيانةَ كانت تمرّ بهامشٍ **صفر**، وأوّلُ طفرةٍ تُسجَّل بعدها تُحمِّرها. وهذا بعينه ما وُجِدت لتقوله **قبل** أن يُقال بحرقِ ساعةٍ في CI.
- **العلاج — إعادةُ قياسٍ حقيقيّة لا تحريكُ رقم:** قُرِئ توقيتٌ حيّ (run 33970429290 · job 101317844845 على `d3471e39`): `Unit Tests` = **٢٩٫٨٥ دقيقة**، وقُرِن بعددِ تلك الجولة نفسِها (**٥٤٠**). ثمّ أُعيد الاشتقاق بالصيغة **غيرِ الممسوسة** والكلفةِ المتحفّظة نفسِها ⇒ العلامة **٦١٧** · الحدّ **٥٧٨**.
- **ولم يُقرَن زمنٌ من جولةٍ بعددٍ من أخرى:** ذاك يصنع زوجاً **لم يُرصَد قطّ** — وهو العطلُ الذي تحرسه البيانةُ أصلاً.
- **إفصاحٌ في الاتّجاه غير المريح:** المرساةُ الزمنيّةُ **نزلت** (٣٧٫٢٣ ⇒ ٢٩٫٨٥) فاتّسع الهامشُ المشتقّ. وليس تسريعَ مكنسة: عنقودُ ٢٩ آب **أبطأُ عند كونٍ أصغر** (٣٣٫٩٨–٣٧٫٢٣ عند ٥٠٣–٥٠٩)، والتشتُّتُ المرصود عند العدد الثابت **٦٫٠٤ دقيقة** — فالعدّاءُ تبدّل. **والسقفُ الذي يحرس السلامة فعلاً تسعون دقيقة، ولم يتحرّك.**

## A-BLOCKER-CAN-LEAVE-THE-SURFACE-IN-SILENCE-01 — والعلاجُ المأمورُ به يمحو الدليل (فُتحت 2026-09-05 · **fixed**)

- **المصدر:** `scripts/ci/guard_mutation_guard.py::blocking_surface_findings` (ثلاثةُ اتّجاهاتٍ فقط قبل الإصلاح) · `scripts/ci/guard_catalogue.py --check` · `docs/architecture/blocking_surface_baseline.json`.
- **رأسُ القياس:** `main @ a3124ccf` (بعد دمج #982 مباشرةً).
- **المقيس بالتنفيذ — لا موصوف:** نُزِع **سطرٌ واحد** (استدعاءُ `vegetation_runtime_truth_guard.py` من `ci.yml`) ⇒ هبط السطحُ **٣٠١ ⇒ ٣٠٠** و`blocking_surface_ok`. واشتكى فحصُ انحراف الكتالوج وحدَه، **وعلاجُه المنصوصُ عليه إعادةُ التوليد** — فلمّا أُعيد قال الاثنان معاً `guard_catalogue_ok` و`blocking_surface_ok`.
- **ولذلك هو أخطرُ من صمتٍ عاديّ:** **العلاجُ الذي يأمر به النظامُ هو ما يمحو الدليل**. والمُصلِحُ يتبع التعليماتِ حرفيّاً فيُخفي الأثرَ وهو يظنّ أنّه ينظّف.
- **والأثرُ الباقي:** ملفُّ الحارس يبقى في مكانه، ومواصفةُ طفرته صالحة، والمكنسةُ تقتلها (لأنّها تُشغّل اختبارات لا workflows) — فكلُّ الشواهد خضراء و**لا شيءَ يُشغّل الحارس**. «حارسٌ يبدو أنّه يحرس ولا يحرس» على مستوى الـworkflow لا الشيفرة.
- **ولمَ لم يُمسَك بـ`ghost`:** `ghost` يمسك **مدخلاً لحارسٍ ملفُّه غائب**. هنا الملفُّ حاضرٌ والاستدعاءُ غائب — وهو الفرق بين «الحارسُ محذوف» و«الحارسُ معطَّل».
- **العلاج:** اتّجاهٌ رابع — `frozen - live - retired` يُبلَّغ حتّى تُدرَج الثلاثيّة في `retired` بـ`reason` و`retired_on`. **والتقاعدُ لا يُمنَع بل يُنطَق:** لا تكذيبَ ولا شاهدٌ موجبٌ مطلوب، لأنّ التقاعدَ إزالةُ حجبٍ لا إضافتُه. ويُبلَّغ أيضاً **إقرارُ تقاعدٍ لحاجبٍ ما زال يعمل** — وإلّا صار سطرٌ واحدٌ يشتري صمتاً دائماً.
- **مُكذَّبٌ بطفرتين** مسجَّلتين ⇒ `guard_mutation_guard.py` **٢٧/٢٧**؛ ومنه الشاهدُ الموجب `test_a_declared_retirement_passes` — فبدونه يفرض التجميدُ بقاءَ كلّ حاجبٍ إلى الأبد ويُعاقِب التضييقَ المشروع.
- **حدُّ صدقٍ مُعلَن:** الفحصُ **إرشاديٌّ** كسائر التجميد (يُعيد `0`)، فهو يجعل النزعَ **مرئيّاً** لا **ممنوعاً**. والترقيةُ إلى الحجب قرارٌ لاحقٌ يُتَّخذ بقياس.

## A-WORKFLOWS-PATH-HAS-NO-CODE-OWNER-01 — مسارُ تعريف الحجب بلا مالك (فُتحت 2026-09-05 · **open**)

- **المصدر:** `.github/CODEOWNERS` (يغطّي `/docs/architecture/gates/adjudications/` و`/docs/architecture/gate01_policy.json` و`/.github/CODEOWNERS` فقط) · `scripts/ci/branch_protection_contract_guard.py:114` (`AUTHORIZATION_PATH` وحدَه).
- **المقيس:** #982 مسّت `.github/workflows/capability-governance.yml` وانتقلت من `blocked` إلى `clean` **بلا اعتمادٍ يُضاف** — أي أنّ شريحةً موضوعُها «سطحُ الحجب لا ينمو بلا إثبات» تستطيع أن تُدمَج بصفر مراجعةٍ بشريّة مستقلّة.
- **ولا خرقَ في ذلك:** الضوابطُ القائمةُ كلُّها مرّت؛ المقصودُ أنّ المسارَ الذي يُعرِّف **ما الذي يحجب أصلاً** لا مالكَ له.
- **ولمَ تبقى `open` لا مُصلَحة هنا:** إضافةُ `/.github/workflows/` إلى `CODEOWNERS` **تكلفتُها بشريّة**: المؤلّفُ عادةً `@kafaat`، وGitHub تمنع اعتمادَ المؤلّف لطلبه، فيصير كلُّ تعديلِ workflow معلَّقاً على `@haithmgarallah-ye` وحدَه — وهو بعينه «مالكٌ واحدٌ قفلٌ لا حراسة» الذي يشرحه `CODEOWNERS` نفسُه. قرارٌ تنظيميٌّ للمالك لا يُتَّخذ داخل شريحةٍ تقنيّة.
- **وعلاجٌ جزئيٌّ هبط اليوم:** الاتّجاهُ الرابع أعلاه يجعل **نزعَ** حاجبٍ مرئيّاً، وهو الخطرُ الأخصّ في هذا المسار — لكنّه لا يُغني عن مراجعةٍ بشريّة لتعديلٍ يُبقي الاستدعاءَ ويُفرِغه.
## A-STALE-APPROVAL-SURVIVES-A-NEW-HEAD-01 — اعتمادٌ ينجو من رأسٍ لم يرَه أحد (فُتحت 2026-09-05 · **fixed**)

- **المصدر:** `scripts/ci/branch_protection_contract_guard.py` (بندان فقط قبل الإصلاح: `required_review_thread_resolution` دائماً و`require_code_owner_review` مشروطاً).
- **المقيس:** الإعدادُ **مُفعَّلٌ فعلاً** على `main` — ولا شيءَ في الشجرة يحمرّ إن أُطفِئ. حمايةٌ قائمةٌ تُقرأ عقداً وهي إعدادٌ يزول بنقرة، وهو الصنفُ الذي وُجِد لأجله هذا الملفّ في بنده الأوّل.
- **والأثرُ يمسّ صدقَ الاعتماد لا التنظيم:** الاعتمادُ شهادةٌ على **بايتاتٍ بعينها**؛ فبدونه يعتمد المراجعُ رأساً ثمّ يُدفَع غيرُه، ويبقى الاعتمادُ سارياً على شيفرةٍ **لم يرَها أحد** — أي نقلُ توقيعٍ إلى مستندٍ غير الذي وُقِّع. ولا تُغني `required_status_checks`: تلك تشهد للآلة على الرأس الجديد، ولا تشهد أنّ **إنساناً** قرأه.
- **ودائمٌ لا مشروط** (بخلاف بند مالكي الكود): لا ثمنَ له على الدمج ما دام الرأسُ ثابتاً، ونطاقُه **كلُّ** اعتمادٍ في المستودع لا ملفّان.
- **مُكذَّبٌ** بـ`test_a_stale_approval_that_survives_a_new_head_is_a_failure`، وشاهدُه الموجب `test_the_enabled_stale_review_lock_passes`.

## A-A-DEFENSIVE-BRANCH-THAT-CANNOT-BE-KILLED-01 — دفاعٌ لا يُكذَّب (فُتحت 2026-09-05 · **fixed**)

- **المصدر:** `stale_review_violations` في صياغتها الأولى — فرعُ «لا كتلة `parameters` مفهومة».
- **المقيس:** زُرِع العطلُ فيه فبقي الاختبارُ **أخضر**. والسببُ أنّه **غيرُ بالغٍ أصلاً**: `violations` تُبلِّغ السببَ الجذريّ نفسَه وتخرج بـ1 قبل أن يُغيّر هذا الفرعُ حكماً، ولا مُدخَلَ تمرّ منه تلك ويسقط فيه هذا.
- **العلاج: الحذف لا التوسيع.** دفاعٌ لا يُكذَّب **يبدو حمايةً وليس بها**، وإبقاؤه يُضخِّم عددَ ما يبدو محروساً بلا زيادةِ حراسة.
- **وكيف كُشِف:** تشغيلُ المكنسة على أساسٍ أخضر — لا قراءةُ الرمز. وأوّلُ تشغيلٍ أعطى `✓` كاذبةً لأنّ الأساسَ كان أحمرَ بـ`NameError`؛ **المكنسةُ تتحقّق من الحمرة بعد الزرع ولا تشترط الخضرةَ قبله**، فتُقرأ نتيجتُها قتلاً وهي حمرةٌ سابقة. يُسجَّل بنداً للمكنسة نفسِها.
