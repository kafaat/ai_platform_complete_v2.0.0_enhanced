# كتالوج الحرّاس — ما يفرضه كلّ حارس وأين يحجب

> **مصنوعة مولَّدة.** لا تُحرَّر يدويّاً: `python scripts/ci/guard_catalogue.py`.
> مشتقّة من الـworkflows (أين يحجب) · `guard_mutation_registry.json` (ما يمسكه،
> بكلمات كاتبه) · وسطر التوثيق الأوّل في الحارس نفسه (ما يفرضه).

**كيف تقرأ هذا الجدول عند فشل بوّابة:** ابحث عن اسم السكربت في رسالة الفشل، ثمّ
اقرأ عمود «ما يمسكه» — فهو يصف العطل الذي وُجِد الحارس لأجله، لا القاعدة مجرّدة.
و«الاختبار الشاهد» هو ما يجب أن يحمرّ إن عُطِّل الحارس؛ شغّله لتفهم الخاصّيّة.

## ما يقوله هذا الجرد قبل أيّ تفصيل

- حرّاس تحجب في CI: **258**
- منها **مُثبَتة بالتكذيب** (لها مواصفة طفرة نُفِّذت): **40**
- إجماليّ الطفرات المُسجَّلة: **269**
- وطفراتٌ **سلوكيّة** تُزرَع في منطق الإنتاج نفسه: **101** على 36 مصدراً

والسلوكيّة محورٌ آخر لا زيادةٌ في العدد: الحارس الساكن يقيس **وقوع** الشيء —
أنّ المسار يستشير مفتاح الطوارئ مثلاً — ويمرّ أخضر على مسارٍ يستشيره ثمّ يتجاهل
نتيجته، أو يستشيره بنطاقٍ أضيق فلا يُطابِق. فتلك تُزرَع في المصدر الفيزيائيّ
ويجب أن يحمرّ اختبارُ **أثرها**.

أي أنّ **218** حارساً يحجب الدمج ولم يُثبَت قطّ أنّه
يفشل حين يوجد العطل. هذا ليس اتّهاماً لها بل **قياس لِما نعرفه عنها**: اختبار
الحارس المعتاد يقيس أنّه يمرّ على شجرة سليمة، وهي خاصّيّة يُحقّقها حارسٌ لا يفعل
شيئاً. ومواصفة الطفرة هي الفرق بين «يمرّ» و«يمسك».

---

## الحرّاس المُثبَتة بالتكذيب (40)

لكلٍّ منها عطلٌ يُزرَع في مصدرها فعليّاً (`guard_mutation_guard --run`) واختبارٌ
**مُسمّى** يجب أن يحمرّ عندها. حمرةٌ باختبار آخر ليست دليلاً.

### `action_pin_agreement_guard.py`

**يفرض:** ترقيةُ تثبيتٍ نصفُها ترقيةٌ ونصفُها كذبة.

**يحجب في:** `sahool-production-gates.yml` → `supply-chain-static-scan`

**الاختبار الشاهد:** `tests_v9/test_action_pin_agreement_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- نزعُ بند «بصمةٌ واحدة لكلّ عمل» ⇒ ترقيةٌ تُبدّل ثلاثة من ثلاثة وعشرين تمرّ خضراء، وهو بالحرف ما كانت الحزمة المقترَحة ستفعله؛ و`github_actions_policy_guard` لا يراه لأنّه يسأل «أمثبَّتٌ ببصمة؟» لا «أبصمةٌ واحدة؟» — يُسقِط `test_a_half_upgrade_is_blocked`
- أساسٌ يبقى بعد توحيدٍ يبتلع عودة التباعد صامتاً: يُوحَّد `checkout` ثمّ يتباعد ثانيةً فيبقى تحت سقفه القديم والحارس أخضر. درسٌ مقيس مرّتين قبله في راتشِتَي `fixme` ودَين الواجهة — يُسقِط `test_unifying_without_lowering_the_baseline_is_blocked`
- `@<بصمة v7> # v4` أسوأ من تعليقٍ غائب: القارئ التالي يقرؤه وسماً ويبني عليه قرار ترقيةٍ أو تدقيقٍ أمنيّ. وهو الخطأ الذي تقع فيه كلّ ترقيةٍ تُبدّل البصمة وتنسى تعليقها — يُسقِط `test_a_sha_carrying_two_different_tags_is_blocked`
- مدخلٌ لعملٍ زال من الشجرة يُقرأ ديناً قائماً وقد انتهى — فيُدرَّب قارئه على تجاهل الأساس كلّه، وهو عطل الحارس الأكثر شيوعاً في هذا المستودع — يُسقِط `test_a_stale_baseline_entry_is_blocked`
- مجلّدٌ غائب أو مسارٌ تغيّر ⇒ صفر بصمة ⇒ صفر مخالفة ⇒ PASS: «لم يُقَس» يُقرأ «متّسق»، وهي الحالة التي تجعل الحارس أخضرَ إلى الأبد وهو يحرس لا شيء — يُسقِط `test_a_missing_workflows_directory_fails_closed`

### `bidi_control_char_guard.py`

**يفرض:** محارف الاتّجاه الخفيّة — BIDI-CONTROL-CHAR-PASSED-THE-DEFAULT-PREFLIGHT-01.

**يحجب في:** `ci.yml` → `structural-lint`

**الاختبار الشاهد:** `tests_v9/test_bidi_control_char_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- إسقاطُ رصد القالبات يفتح **هجوم trojan source** بعينه (CVE-2021-42574): سطرٌ يقرؤه المراجع `if (admin)` ويُنفَّذ غيرُه. وهذا هو الشيء الوحيد الذي يحجبه هذا الحارس مطلقاً. — يُسقِط `test_a_direction_override_is_blocked_with_no_baseline`
- تخطّي القالبات يجعل الحارس يقيس العلامات وحدها — أي يحرس المشروع ويترك الهجوم. والأساس لا يُرخّصها بحال، وهذا يُثبِته. — يُسقِط `test_an_override_is_not_excusable_by_the_baseline`
- سقفٌ يساوي المقيس يجعل كلّ ملفٍّ جديد يُرخّص نفسه، فينمو الأساس بلا حساب — وهو «أساسٌ يُصادِق على ما وجده» لا أساسٌ يحدّه. — يُسقِط `test_a_file_with_no_entry_may_not_introduce_marks`
- بلا حدٍّ للنموّ يصير الأساس جرداً لا عقداً: يُسجّل ما وقع ولا يمنع تكراره — وهو حرفيّاً ما قاله سجلّ الفجوة: «إغلاقه يخلط أصلحتُ ما وقع بمنعتُ أن يقع». — يُسقِط `test_one_more_mark_than_declared_is_blocked`

### `brain_append_only_guard.py`

**يفرض:** An append-only journal may not shrink — and a merge must preserve **both** parents.

**يحجب في:** `no-report-only-change.yml` → `no-report-only-change`

**الاختبار الشاهد:** `tests_v9/test_brain_append_only_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- فحصُ والدٍ واحد ⇒ عمى الدمج نفسه الذي أنجى `cb6598fe`: الملفّ محفوظ عند والد ومفقود عند الآخر، فالفحص مقابل أحدهما يمرّ — يُسقِط `test_both_parents_are_examined_not_just_one`
- جعلُ التقلّص إرشاديّاً ⇒ يعود ١٬٣٨٣٬٣٦٨ بايت إلى صفر بلا حجب، وهي الواقعة الأصليّة. والاختبار المُسمّى **اصطناعيّ عمداً**: اختبار الواقعة الحقيقيّة (test_the_guard_fails_on_the_truncation_that_created_it) يحتاج التاريخ الكامل ويُتخطّى في استنساخ CI الضحل — وطفرةٌ تُسمّي اختباراً مُتخطّى ليست تكذيباً بل صمتاً. — يُسقِط `test_a_merge_that_takes_the_empty_side_is_caught`
- إسقاطُ فحص الغياب ⇒ شجرةٌ بلا سجلّات تُنتِج صفر أزواج وتطبع ok — «لا شيء للمقارنة» يُقرأ نجاحاً، وهو صنف الفجوة نفسه داخل علاجها — يُسقِط `test_a_missing_journal_at_head_blocks_even_with_nothing_to_compare`
- تصليبُ القائمة ⇒ فهرس ثانٍ ينحرف عن `resolve_merge_conflicts`، وهو صنف «قائمتان تصفان الشيء نفسه» — يُسقِط `test_the_file_list_comes_from_the_existing_classifier`

### `brain_commit_claim_guard.py`

**يفرض:** يمنع رسالة التزام من ادّعاء تسجيل فجوة لم تُسجَّل.

**يحجب في:** `no-report-only-change.yml` → `no-report-only-change`

**الاختبار الشاهد:** `tests/architecture/test_brain_commit_claim_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- معرّف تفويضٍ يُطالَب بقسمٍ في سجلّ الفجوات ⇒ إمّا إدخالٌ كاذب (التفويض إذنُ مالكٍ لا عطلٌ مرصود) أو حذفُ المعرّف من الرسالة، أي كتمان أيّ تفويضٍ خُتِم. — يُسقِط `test_a_gate_adjudication_id_is_not_demanded_as_a_gap_section`
- الصنف يصير استثناءً بدل تحقّق ⇒ معرّف تفويضٍ ملفَّق يمرّ، والذكر يعود ادّعاءً غير مفحوص — وهو العطل الأصليّ الذي بُني الحارس له. — يُسقِط `test_a_fabricated_adjudication_id_is_still_rejected`
- استثناءٌ بالبادئة يبتلع كلّ فجوة تبدأ بـGATE (منها GATE01-ONE-SHOT-LIFECYCLE-INCOMPLETE-01 نفسها) — نفس فخّ `startswith("CVE-")` الذي أسقطه تكذيبُ الاستشارات قبله. — يُسقِط `test_the_adjudication_class_did_not_swallow_real_gap_ids`
- الفحص الأساسيّ يُفرَّغ: كلّ معرّف يُذكَر يُقرأ مسجَّلاً ⇒ يعود عطل #683 (رسالةٌ تُعلِن أربع فجوات وتصل اثنتان) بلا أن يُحمِرّ شيء. — يُسقِط `test_it_catches_the_real_historical_miss`
- استثناء الاستشارات يبتلع كلّ معرّف ⇒ الحارس يمرّ على كلّ شيء صامتاً، وهو أخطر من سقوطه لأنّه يُقرأ خضرةً. — يُسقِط `test_the_advisory_exemption_did_not_swallow_real_gap_ids`
- قصرُ القراءة على العناوين يُعيد الإيجابيّة الكاذبة المشحونة: ٢٢ فجوة مسجَّلة كصفوف تُعامَل كغير مسجَّلة، فتسقط PR تذكر ما هو مسجَّل سلفاً. — يُسقِط `test_table_row_ids_count_as_registered`
- حدُّ الكلمة يقتطع المعرّف الملتصق بالعربيّة فيخترع وهميّاً (`E2E-UNDER-…`) ويُفوّت الحقيقيّ (`AUTH-E2E-…`) في آنٍ — عطبان متعاكسان من سببٍ واحد. — يُسقِط `test_an_id_glued_to_arabic_text_is_read_whole_not_from_its_middle`

### `brain_duplicate_gap_identity_guard.py`

**يفرض:** يمسك الفشل الصامت الذي يتركه دمج `union` — `DETERMINISTIC-GENERATION-AND-MERGE-SAFETY-01`.

**يحجب في:** `no-report-only-change.yml` → `no-report-only-change`

**الاختبار الشاهد:** `tests_v9/test_brain_duplicate_gap_identity_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- التكرار بدل التلاصق ⇒ السلاسل التاريخيّة المقصودة تُرفَع إنذاراً (١٠ من ١١ على الشجرة) — يُسقِط `test_a_deliberate_history_chain_passes`

### `brain_state_transition_guard.py`

**يفرض:** Prevent sahool-brain-only edits from claiming executable/certification closure.

**يحجب في:** `no-report-only-change.yml` → `no-report-only-change`

**الاختبار الشاهد:** `tests_v9/test_brain_transition_guard_vocabulary.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- إعادة النمط القديم `\b(CLOSED|…)\b` — خاطئ في الاتّجاهين: يطابق داخل fail-closed ولا يطابق CLOSED_IN_CODE — يُسقِط `test_the_underscore_vocabulary_was_the_false_negative`
- نزع اشتراط كود تنفيذيّ خارج الدماغ ⇒ ادّعاء إغلاق دماغيّ صرف يمرّ — يُسقِط `test_brain_only_diff_with_a_real_claim_is_still_rejected`
- نزع اشتراط القيمة الصفريّة من الاستثناء ⇒ `runtime_verified: 1` يصير اقتباساً معفىً — إصلاحُ إيجابيّة كاذبة يصنع سلبيّة كاذبة أخطر — يُسقِط `test_a_positive_valued_claim_is_still_rejected`
- إعادة المطابقة الخام بلا مرساة دلاليّة ⇒ اقتباس `production_certified=0/81` نفياً يُقرأ ادّعاءً — يُسقِط `test_a_zero_valued_citation_is_not_a_closure_claim`

### `branch_protection_contract_guard.py`

**يفرض:** القفل الذي يمنع الدمج لا يعيش في المستودع — فيُدقَّق وجودُه.

**يحجب في:** `capability-governance.yml` → `branch-protection-contract`

**الاختبار الشاهد:** `tests_v9/test_branch_protection_contract_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- قبولُ القفل المُطفَأ ⇒ يعود المستودع إلى الحالة التي وقع فيها العطل مرّتين (#810 و#816). والحارس كلّه موجودٌ لهذا الشرط وحده — تعطيلُه يجعله يُبلِغ خضرةً عن سؤالٍ لم يطرحه — يُسقِط `test_conversation_resolution_disabled_is_a_failure`
- مقارنةٌ بالصدق بدل المنطقيّ: `"true"` نصّاً و`1` صادقتان في بايثون فتُقرآن قفلاً مُفعَّلاً وهو ليس العقد. طفرةٌ مستقلّة عن سابقتها: تلك تحرس **الحكم** وهذه تحرس **نوع القيمة** — وحقلٌ يتغيّر تمثيله في API يُصيب الثانية وحدها — يُسقِط `test_a_non_boolean_enabled_is_rejected`
- قراءةُ الشرط الغائب قبولاً ⇒ «لم يُقرأ» تصير «مُفعَّل». قاعدة `pull_request` نافذة بلا هذا المفتاح (إصدار API تغيّر، أو رمزٌ رأى حقولاً جزئيّة) تُقرأ قفلاً قائماً — يُسقِط `test_a_missing_key_is_not_read_as_enabled`
- نزعُ فحص غياب قاعدة `pull_request` ⇒ فرعٌ محميّ من الحذف والدفع القسريّ وحدهما يُقرأ مشمولاً بشرط المراجعة. ورمزُ الخروج يبقى `1` عبر الفرع التالي — ولذلك يقيس الاختبار **السبب** لا الرمز — يُسقِط `test_no_pull_request_rule_is_a_failure`
- ملفٌّ غائب يُقرأ «مضبوطاً» ⇒ الحارس أخضرُ **بالضبط حين لا يُقاس شيء**. والحالة مرجَّحة لا نادرة: خطوةُ جلبٍ تفشل أو رمزٌ بلا صلاحية قراءة القواعد يُنتِجان غياباً لا رفضاً. **وتبديلُ صنف الاستثناء وحده لا يزرع شيئاً** — يلتقطه `except OSError` التالي فيبقى الفشل مغلقاً؛ فالزرع بإرجاع وثيقةٍ مُرضية — يُسقِط `test_an_unreadable_protection_file_fails_closed`
- استجابةُ خطأٍ من GitHub أو جسمٌ غريب في موضع الظرف لا يُقرأ دليلاً؛ قبولُه يجعل كلّ فحوص المصدر تقرأ حقولاً غائبة `None` — استجابةٌ لا تُفهَم فشلٌ لا قبول — يُسقِط `test_a_scalar_json_document_is_rejected`
- قبولُ مصفوفة القواعد العارية «للتوافق الخلفيّ» يُعيد فتح الباب الذي وُجِد الظرف لأجله: دليلٌ بلا مصدر يمرّ من فرعٍ آخر أو من تشغيلٍ سابق بلا أثر — يُسقِط `test_a_bare_rule_array_is_rejected_as_evidence_without_a_source`
- ظرفٌ لا يُعرَف شكلُه يُقرأ دليلاً ⇒ حقولٌ غائبة تُقرأ `None` وتمرّ فحوصُها بصمت. ونسخةٌ أحدث قد تنقل معنى حقلٍ قائم — فالتوافق يُقرَّر بترقية الحارس — يُسقِط `test_an_unknown_envelope_schema_is_rejected`
- ‏`401/403/404/429/5xx` تُنتِج جسماً صالح البنية لا قواعد؛ إهمالُ الرمز يحوّل «لم يُقرأ» إلى «صفر قاعدة» ثمّ إلى رسالةٍ صحيحة عن سببٍ خاطئ. وهو الحقل الذي يفصل عطلَ الشبكة عن عطل الإعداد — يُسقِط `test_a_non_200_response_fails_closed`
- مقارنةٌ نصّيّة تقبل `"200"` القادمة من `jq` بلا `--argjson`. طفرةٌ مستقلّة عن سابقتها: تلك تحرس **وجود** الفحص وهذه تحرس **نوع** القيمة — يُسقِط `test_a_success_status_as_text_is_not_read_as_success`
- دليلٌ عن مستودعٍ آخر — ولو كان قفلُه مُفعَّلاً — يُخضِر الحارس عن سؤالٍ ليس هو السؤال — يُسقِط `test_evidence_from_another_repository_is_rejected`
- فروع العمل في هذا المستودع تحمل حمايةً؛ فقراءةُ قواعد أحدها بدل `main` تُنتِج خضرةً كاملةً بينما الفرع الافتراضيّ مكشوف — وهي الحالة التي وقعت فعلاً في تشغيل 31411680450 — يُسقِط `test_evidence_for_another_branch_is_rejected`
- ‏`repository`/`branch` إعلانٌ يكتبه المُشغِّل، والنقطة المُستدعاة هي ما قِيس. إهمالُها يجعل خطأ تحريرٍ في مسار الوظيفة (تغيير الفرع وحده) يمرّ كاملاً بإعلانٍ صحيح — يُسقِط `test_a_declared_branch_cannot_launder_a_different_endpoint`
- مصنوعٌ مُعاد استعماله بين تشغيلين يُنتِج خضرةً عن حالةٍ انقضت — الصنف نفسه الذي أضاع ثلاث جولات حين قُرِئ سجلٌّ بختمٍ زمنيّ قديم بوصفه نتيجةً جديدة — يُسقِط `test_evidence_from_an_older_commit_is_rejected`
- حقلٌ فارغ أو بحالة أحرفٍ كبيرة لا يربط الدليل بشيء؛ وقبولُه يجعل مطابقة الـSHA التالية تقارن نصّين لا بصمتين — يُسقِط `test_a_matching_but_malformed_commit_sha_is_still_rejected`
- خطوة الجلب تُجسّد `null` حين يتعذّر تحليل الجسم (خنقٌ يُعيد HTML)، فقبولُه يُنتِج انهياراً في التكرار أو «صفر قاعدة» — رسالةٌ صحيحة عن سببٍ خاطئ — يُسقِط `test_a_non_array_rules_field_fails_closed`
- خضرةٌ بلا عدّ لا يفرّق قارئُها بين «فُحِصت قاعدة فمرّت» و«لم يُفحَص شيء» — وهو بند «صفر checks منفَّذة» بصيغته القابلة للقياس — يُسقِط `test_the_pass_line_states_what_was_examined`
- إسقاطُ البند يُعيد الفجوة P0 كما كانت: من يحتاج التفويض يُصدره في نفس الـPR، وطبقةُ AUTHORIZATION تُقرأ مكتملةً حتّى طبقة السلطة وهي ليست كذلك. — يُسقِط `test_touching_the_authorization_path_requires_code_owner_review`
- بندٌ دائم يحجب **كلّ** دمجٍ في المستودع حتّى يُفعَّل إعدادٌ لا يملكه وكيل — وحمايةٌ تُوقِف العمل كلّه تُطفَأ، فتُنتِج حمايةً صفراً. التناسب شرطٌ في التصميم لا ذوق. — يُسقِط `test_an_unrelated_pr_is_not_blocked_by_the_conditional_term`
- الغياب يعني أنّ الشرط **لم يُرَ**، وقراءتُه «مُفعَّل» هي بعينها «نتيجةٌ عن سؤالٍ لم يُطرَح» — وهو الصنف الذي وُجِد هذا الملفّ كلّه ليطارده. — يُسقِط `test_a_missing_code_owner_key_is_not_read_as_enabled`

### `canonical_consumer_bypass_guard.py`

**يفرض:** `KNOWLEDGE-CANONICAL-CONSUMPTION-01` — مُستهلِكٌ لا يُعيد اشتقاق ما له مُنتِجٌ قانونيّ.

**يحجب في:** `ci.yml` → `structural-lint`

**الاختبار الشاهد:** `tests_v9/test_canonical_consumer_bypass_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- نزعُ التقاطع ⇒ الحارس يفقد سببَ وجوده كلّه: `cap.get(F) or raw_mm` يمرّ خضراء. والتقاطعُ بعينه هو القاعدة — لا وجودُ الخام ولا وجودُ القراءة القانونيّة منفردين. — يُسقِط `test_an_or_fallback_to_raw_is_blocked`
- عدُّ مفاتيح القواميس قراءةً ⇒ `{"raw_mm": x}` يُلوِّث الاسم، فيُطلِق الحارس على كلّ مُنتِجٍ يعرض حقله. والإيجابيّة الكاذبة تُسقِط الحارس بلا أن تُعطِّله: قارئُ الأحمر يتعلّم تجاهله. — يُسقِط `test_a_dict_key_is_a_write_not_a_read`
- نزعُ البند الإيجابيّ ⇒ مُستهلِكٌ كفّ عن قراءة الحقل يبقى مُدرَجاً، فيقول السجلّ إنّه محروسٌ وهو لا يُقرأ أصلاً — مدخلٌ يَعِد بحراسةٍ لا تقع. — يُسقِط `test_a_consumer_that_never_reads_the_field_is_blocked`
- قبولُ «صفر مفحوص» ⇒ سجلٌّ بلا مستهلكين يُنتِج PASS: أخضرُ لأنّه لم ينظر، وهو الصنف الذي يطارده هذا المستودع كلّه. — يُسقِط `test_zero_examined_consumers_fails_closed`
- نزعُ فحص المُنتِج ⇒ إعادةُ تسمية الحقل تترك السجلّ يصف عقداً زال، والحارس يقيس مقابل اسمٍ لا وجود له فيمرّ كلّ شيء. — يُسقِط `test_a_producer_that_lost_the_field_is_blocked`
- قبولُ مدخلٍ بلا مدخلات خام محظورة ⇒ قيدٌ يُعلَن ولا يمنع شيئاً؛ ويصير التقاطع فارغاً دائماً فيمرّ الارتداد نفسه من بابٍ آخر. — يُسقِط `test_an_entry_without_forbidden_inputs_is_blocked`
- قبولُ أيّ مخطَّط ⇒ الحارس يفحص وثيقةً ليست وثيقتَه ويُبلِغ عنها خضرة؛ ووثيقةٌ بمفاتيح فارغة تُقرأ «لا قيود». — يُسقِط `test_a_wrong_schema_fails_closed`

### `capability_authority_completeness_guard.py`

**يفرض:** A′-4c — fail closed when a compatibility field has no explicit authority/disposition.

**يحجب في:** `capability-governance.yml` → `capability-registry`

**الاختبار الشاهد:** `tests/architecture/test_capability_authority_completeness_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- حقلٌ توافقيّ بلا سلطة مصنَّفة يعبر صامتاً ⇒ وعدُ «كلّ حقل له مالك معلَن» يصير فارغاً — وهذا هو العطل التأسيسيّ الذي بُني الحارس ليمسكه (7 من 20 حقلاً كانت بلا تصنيف قبل A′-4c) — يُسقِط `test_unclassified_legacy_field_fails`
- سلطةٌ مخترَعة (سجلّ ثالث بالتسمية) تعبر كتصنيفٍ صحيح ⇒ يعود no_third_value_registry حبراً على ورق من باب الأسماء لا القيم — يُسقِط `test_unknown_authority_fails`
- إعلان legacy_writer بائت على حقلٍ canonical يعيد ترخيص ازدواج الكتابة الذي أغلقته A′-4b — نصُّ السياسة نفسه يصير بابَ الردّة — يُسقِط `test_canonical_field_cannot_reauthorize_legacy_writer`

### `capability_compatibility_roundtrip_guard.py`

**يفرض:** A′-4c — compatibility projection convergence and non-authority preservation gate.

**يحجب في:** `capability-governance.yml` → `capability-registry`

**الاختبار الشاهد:** `tests/architecture/test_capability_compatibility_roundtrip_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- انحرافُ الإسقاط لا يُبلَّغ من بوّابة الإغلاق المركّبة ⇒ «متقارب» تشهد به بوّابة عمياء عن أوّل شروطه — يُسقِط `test_a_planted_projection_drift_is_reported`
- مزامنة الإسقاط تمسّ حقلاً أجنبيّاً (مملوكاً لكاتبٍ آخر) بلا بلاغ ⇒ حدُّ «لا يمسّ إلا ما تملكه السلطة القانونيّة» بلا شاهد مستقلّ عن المُسقِط نفسه — يُسقِط `test_a_foreign_field_touched_by_projection_is_reported`
- فحصٌ فرعيّ أحمر (رابط/تشغيل/إسقاط/مطابقة) يُبتلَع ⇒ round-trip أخضر فوق سلسلةٍ مكسورة — رمزُ الخروج يُقرأ ولا يُحكَم به — يُسقِط `test_a_failing_subcheck_is_reported`

### `capability_legacy_access_guard.py`

**يفرض:** A′-4c — deny unclassified direct consumers of capabilities/registry/capabilities.json.

**يحجب في:** `capability-governance.yml` → `capability-registry`

**الاختبار الشاهد:** `tests/architecture/test_capability_legacy_access_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- مستهلكٌ مباشر جديد للسجلّ القديم يعبر بلا تصنيف ⇒ deny-by-default يصير allow-by-default والهجرة إلى عرض السلطة تتوقّف بصمت — يُسقِط `test_new_direct_consumer_fails_closed`
- رخصةٌ بائتة لملفٍّ زال وصولُه تبقى ⇒ القائمة تتضخّم برخصٍ ميّتة يرثها ملفٌّ جديد بالاسم نفسه دون قرار — يُسقِط `test_stale_allowance_is_rejected`
- سياسةٌ مشوّهة تنفجر AttributeError صاخباً بدل بلاغٍ مسمّى — الأثر أحمر لكنّ رسالته لا تقود مصلحاً (رفعته مراجعة آليّة وأصابت) — يُسقِط `test_a_malformed_policy_is_a_named_finding_not_a_stack_trace`

### `capability_writer_authority_guard.py`

**يفرض:** A′-4c — source-level ratchet for writers of the legacy compatibility projection.

**يحجب في:** `capability-governance.yml` → `capability-registry`

**الاختبار الشاهد:** `tests/architecture/test_capability_writer_authority_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- عودةُ سطر كتابة canonical في الرابط تعبر ⇒ قفل A′-4b النصّيّ يفقد نسخته المصدريّة AST — وهي النسخة التي لا يخدعها تنويع التنسيق أصلاً — يُسقِط `test_linker_reacquiring_canonical_owner_is_blocked`
- كاتب التشغيل يكتب production_certified ⇒ قرارُ الإطلاق الخارجيّ للمالك يُشتَقّ آليّاً من التحقّق — الخلط الذي حرّمه العقد نصّاً («لا يُشتقّ من L5») — يُسقِط `test_runtime_apply_cannot_write_production_certified`
- فهرسة policy["field_authority"] على شكلٍ مشوّه ترمي KeyError/TypeError بلا اسم مخالفة — التحقّق من الشكل قبل القاعدة يجعل الفشل قابلاً للإصلاح من رسالته — يُسقِط `test_a_malformed_policy_is_a_named_finding_not_a_stack_trace`

### `ci_unbounded_wait_guard.py`

**يفرض:** انتظارٌ بلا سقف — `CI-UNBOUNDED-PROVISIONING-WAIT-01`، الشطر الذي يمنع العودة.

**يحجب في:** `ci.yml` → `lint`

**الاختبار الشاهد:** `tests_v9/test_ci_unbounded_wait_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- تثبيتٌ شبكيّ بلا حدّ جداريّ هو ما أحرق 112 دقيقة ثمّ بقي معلَّقاً — والصمت يُقرأ عملاً جارياً. — يُسقِط `test_an_unbounded_apt_get_is_blocked`
- وظيفةٌ تُجهّز اعتماداً شبكيّاً بلا سقف تحرق runner ستّ ساعات. والعلامة الثالثة أُضيفت بعد أن عمي الحارس بإصلاحٍ صحيح: نقلُ `--with-deps` إلى سكربتٍ صامد أخرج السلسلة من متن الوظيفة، فمرّ أخضرَ لسببٍ خاطئ (مقيس بالزرع). — يُسقِط `test_a_db_job_without_a_job_timeout_is_blocked`
- وثيقةٌ لا تُقرأ تُخرِج وظائفها من القياس كلّه، فيصير «لم يُقَس» «مرّ». — يُسقِط `test_an_unreadable_workflow_fails_closed_instead_of_being_skipped`
- ذِكرُ `apt-get` داخل رسالة `echo` ليس استدعاءً — وإدانتُه إيجابيّةٌ كاذبة تُسقِط الحارس بلا تعطيله (وقعت على ci.yml:839). — يُسقِط `test_the_current_tree_has_no_unbounded_provisioning_wait`
- حدٌّ يُفرَض على **اسم الأمر** يفوته كلُّ من يستدعيه من جوفه: `playwright install --with-deps` عَلِق ٨٠+ دقيقة بينما نجح على الرأس نفسه بالبايت في تشغيلٍ شقيق في 2م55ث. — يُسقِط `test_a_tool_that_calls_apt_from_inside_itself_must_be_bounded`

### `claim_base_guard.py`

**يفرض:** كلّ ادّعاء يحمل أساسه — CLAIMS-WITHOUT-A-MEASURED-BASE-01.

**يحجب في:** `ci.yml` → `lint`

**الاختبار الشاهد:** `tests_v9/test_claim_base_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- مطابقة المفتاح بالبادئة بدل التامّة ⇒ `baseline_route_count` يُقبَل أساساً — يُسقِط `test_a_count_is_not_a_base`
- نزع سقف الدَّين ⇒ قائمة «تتقلّص ولا تنمو» تنمو — يُسقِط `test_debt_growth_is_blocked_by_the_ceiling`
- نزع الإنفاذ العكسيّ ⇒ مدخل اكتسب ختماً يبقى ديناً بائتاً — يُسقِط `test_debt_that_gained_a_base_must_leave_the_list`
- قبول ختم القياس مكان تاريخ الحكم — يُسقِط `test_a_measured_stamp_does_not_satisfy_a_decision`
- قبول تاريخ الحكم مكان ختم القياس — يُسقِط `test_a_decision_stamp_does_not_satisfy_a_measurement`
- نزع حجب المصنوعة غير المصنَّفة ⇒ ملفّ جديد يدخل بلا صنف — يُسقِط `test_unclassified_artifact_is_blocked`
- نزع حجب مدخل الدَّين البائت — يُسقِط `test_stale_debt_entry_is_blocked`
- SHA مجهول يُبلَّغ «صفر التزام» بدل «غير قابل للحلّ» — يُسقِط `test_an_unknown_sha_reports_unresolvable_not_zero`

### `compose_no_default_secrets_guard.py`

**يفرض:** لا سرَّ افتراضيّ في Compose — `COMPOSE-DEFAULT-SECRET-IS-A-PUBLISHED-SECRET-01`.

**يحجب في:** `ci.yml` → `structural-lint`

**الاختبار الشاهد:** `tests_v9/test_compose_no_default_secrets_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- القيمة الحرفيّة بلا استيفاء سرٌّ منشور لا يراه فحصُ الافتراضيّات — وإسقاطُ فحصها يدفع الكاتب إلى صيغةٍ لا يراها الحارس. — يُسقِط `test_the_live_tree_carries_no_default_secret`
- استثناءٌ يُعَدّ حيّاً دائماً يصير إعفاءً أبديّاً بلا صاحب — والقائمة تتوقّف عن التقلّص. — يُسقِط `test_a_stale_exception_is_reported_so_the_list_can_only_shrink`

### `container_command_path_guard.py`

**يفرض:** مسارٌ يُنفّذه compose يجب أن تضعه صورةُ الخدمة فعلاً — «مُسجَّل» ليس «يعمل».

**يحجب في:** `ci.yml` → `compose-validate`

**الاختبار الشاهد:** `tests_v9/test_container_command_path_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- ادّعاء الوجود بلا فحص وجود ⇒ كلّ مسار «تضعه الصورة» والعطل الأصليّ يمرّ — يُسقِط `test_the_old_location_is_still_unreachable_from_that_image`
- تعطيل الفحص كلّيّاً ⇒ الحارس يخضرّ على شجرة معطوبة — يُسقِط `test_a_missing_path_is_reported_with_the_service_that_executes_it`
- صفر أزواج مفحوصة ⇒ «أخضر لأنّه لم ينظر» — الصفر الصامت نفسه — يُسقِط `test_it_actually_examines_something`
- إسقاط نسخ ملفّ→ملفّ ⇒ ثلاث خدمات سليمة تُتَّهم (الإيجابيّة الكاذبة المقيسة) — يُسقِط `test_copy_semantics_are_applied_not_approximated`

### `env_compose_default_override_guard.py`

**يفرض:** حارس إبطال الافتراض الآمن: `.env.example` لا يجوز أن يهزم افتراضَ `compose` إلى `localhost`.

**يحجب في:** `ci.yml` → `structural-lint`

**الاختبار الشاهد:** `tests_v9/test_env_compose_default_override_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- نزعُ الكشف نفسه ⇒ يمرّ `.env.example` الذي يُبطِل افتراض compose أخضر — وهو بالحرف ما فصل أربعة عمّال عن NATS في البيئة الحيّة 2026-08-12. — يُسقِط `test_a_localhost_value_that_defeats_a_container_default_is_blocked`
- نزعُ استثناء «compose نفسه يقصد المضيف» يُجرّم `CORS_ORIGINS` و`DOMAIN` — إيجابيّات كاذبة تُسقِط الحارس بلا تعطيله، لأنّ قارئ الأحمر يتعلّم تجاهله. — يُسقِط `test_a_localhost_default_in_compose_is_a_legitimate_purpose`
- توسيعُ النطاق إلى قيمٍ ليست عناوين يجعل `localhost` في أيّ سلسلة مخالفةً — ضجيجٌ يُخفي المخالفة الحقيقيّة بين كاذبات. — يُسقِط `test_a_non_url_default_is_out_of_scope`

### `fake_connection_debt_guard.py`

**يفرض:** راتشِت الدَّين: اختبارٌ على اتّصال وهميّ يدّعي سلوكاً تفرضه القاعدة —

**يحجب في:** `ci.yml` → `lint`

**الاختبار الشاهد:** `tests_v9/test_fake_connection_debt_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- قلبُ شرط الماسح ⇒ يمسح ما لا يستعمل وهميّاً، فيغيب ملفّ الحادثة (jsonb) عن المسح. والمرساة على **ملفّ الحادثة** لا على عدّاد الحجم: أوّل صياغة عندي سمّت `test_the_scanner_actually_sees_something` فلم يسقط — القلب يُبقي العدّ كبيراً بملفّات أخرى، فالعدّاد لا يُميّز — يُسقِط `test_the_incident_file_is_named_by_the_survey_not_by_hand`
- قبولُ سدادٍ يُسمّي ملفّ إثبات غير موجود ⇒ الدَّين يُغلَق بسطرٍ مكتوب، وهو بالضبط «حذف الكلمة من نصّه» الذي يمنعه عقد `$comment` — يُسقِط `test_a_settlement_must_name_a_proof_file_that_exists`
- نزعُ اشتراط أن **يذكر** ملفُّ الإثبات مصدرَه ⇒ أخطر صنف يمرّ: مدخلٌ يشير إلى ملفّ قائم لا علاقة له بالمصدر، فيمرّ فحصا الوجود والدليل ويبقى الدَّين غير مسدَّد — يُسقِط `test_a_settlement_whose_proof_never_mentions_the_source_is_refused`
- قبولُ سدادٍ جزئيّ ⇒ «كلّ ادّعاءاته» يصير شعاراً، وادّعاءٌ جديد يظهر في ملفّ مُسدَّد لا يُعيد فتح الدَّين — يُسقِط `test_a_partial_settlement_does_not_close_the_debt`
- «المصنوع يدهس المكتوب» — `--generate` يمحو `proven_live` فيرجع الدَّين المُسدَّد صامتاً عند أوّل إعادة توليد، والقسم لا يُشتقّ فلا سبيل لاستعادته — يُسقِط `test_regenerating_the_baseline_does_not_erase_the_settlements`
- نزعُ حصر مسار الإثبات داخل الجذر ⇒ `../…` يُقبَل ما دام الملفّ موجوداً، فيقرأ الحارسُ ملفّاً خارج المستودع ويُسدّد ديناً بشيء لا يخصّ الشجرة. حدُّ العقد («ملفّ إثبات في الشجرة») يُفرَض بدل أن يُفترَض — يُسقِط `test_a_proof_path_that_escapes_the_repository_root_is_refused`

### `frontend_lint_debt_guard.py`

**يفرض:** تحذيرُ الواجهة دَينٌ — والدَّينُ يُحرَس أو ينمو صامتاً.

**يحجب في:** `ci.yml` → `frontend-typecheck`

**الاختبار الشاهد:** `tests_v9/test_frontend_lint_debt_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- نزعُ الراتشِت الصاعد ⇒ تحذيرٌ جديد يدخل بلا حجب، و`eslint` هنا يُبلِّغ تحذيراً لا خطأً فتبقى الوظيفة خضراء — نموٌّ صامت لا يراه أحد لأنّ GitHub يعرض عشرة تعليقات من ثمانين — يُسقِط `test_one_more_warning_is_blocked`
- سقفٌ يبقى بعد سداد دَينٍ يبتلع **عودته**: تُصلَح خمس ثمّ تُضاف خمس فيثبت العدّاد والحارس أخضر. راتشِتٌ لا يُخفَّض ليس راتشِتاً بل سقفٌ مُرتخٍ — يُسقِط `test_paying_debt_without_lowering_the_ceiling_is_blocked`
- إهمالُ القواعد خارج الأساس يجعل السقف إجماليّاً فعليّاً: تحويلُ عشرة `any` إلى عشرة `no-unsafe-assignment` يمرّ بلا أثر — استبدالُ دَينٍ بأسوأ منه بمجموعٍ ثابت — يُسقِط `test_a_rule_outside_the_baseline_is_blocked`
- رسالةٌ تقول «زاد العدد» بلا أسماء ملفّات تترك قارئها يبحث في ثلاثين ملفّاً؛ ومن يقرأ الأحمر يجب أن يعرف **أين** ينظر وإلّا تعلّم تجاهله — يُسقِط `test_the_failure_names_the_files_to_look_at`
- تقريرٌ غائب أو مشوَّه يُقرأ «صفر تحذير» ⇒ الحارس أخضرُ بالضبط حين لا يُقاس شيء. و«لم يُقَس» ليس «لم ينمُ» — يُسقِط `test_an_unreadable_report_fails_closed`
- طباعةُ مخالفةٍ متعدّدة الأسطر كتلةً واحدة تُخرِج سطر الملفّات بلا `✗` ولا إزاحة، فيُقرأ مخالفةً مستقلّة وتنكسر القراءة السطريّة لسجلّ CI — والرسالة جزءٌ من الحارس لا زينةٌ فوقه — يُسقِط `test_every_printed_failure_line_keeps_its_prefix`

### `gate01_frozen_path_guard.py`

**يفرض:** حارس المسارات المجمَّدة خلف GATE-01 — بوّابةُ **تفويضٍ مقيَّد**، لا مفتاحٌ ثنائيّ.

**يحجب في:** `no-report-only-change.yml` → `gate01-physical-effect-freeze`

**الاختبار الشاهد:** `tests_v9/test_gate01_frozen_path_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- تعطيل رصد المسّ يُفرِّغ البوّابة: يمرّ كلّ مسارٍ مجمَّد صامتاً (موروثة من #836، أُعيد رسوّها على النموذج الجديد). — يُسقِط `test_touching_a_frozen_path_is_blocked`
- حالةٌ غير OPEN تُقرأ مفتوحةً ⇒ CLOSED نفسها تصير إذناً عامّاً (موروثة من #836). — يُسقِط `test_any_state_that_is_not_open_fails_closed`
- قائمةٌ مجمَّدة فارغة تُقرأ «لا شيء يُحمى» بدل «عقدٌ ناقص» — تُفرِّغ الحارس بلا أن تُحمِّره (موروثة من #836). — يُسقِط `test_an_empty_frozen_list_fails_closed`
- تفويضٌ لمسارَين يُرخّص لأيّ مسارٍ مجمَّد آخر في الدفعة نفسها — أوسع ممّا أذن به المالك. — يُسقِط `test_an_extra_frozen_path_beyond_the_authorization_is_blocked`
- نزعُ ربط البايتات يُحوّل الإذن من «هذه البايتات» إلى «هذا المسار» — فتُبدَّل الرقعة بعد الموافقة بلا أن يُحمِرّ شيء. — يُسقِط `test_a_single_changed_byte_invalidates_the_authorization`
- بصمةٌ مُعلَنة لا تُشتقّ من بصماتها تمرّ ⇒ تفويضٌ يناقض نفسه يُقرأ إذناً. — يُسقِط `test_a_forged_patch_digest_is_rejected`
- المُستهلَك والملغى يُعاد استعمالهما ⇒ إذنٌ لمرّةٍ واحدة يصير باباً دائماً لكلّ PR لاحقة. — يُسقِط `test_a_consumed_or_revoked_authorization_cannot_be_reused`
- تفويضٌ على أساسٍ غير المُجمَّد يمرّ ⇒ ينفصل الإذن عن الأدلّة التي بُني عليها. — يُسقِط `test_an_authorization_against_a_different_baseline_is_rejected`
- إذنُ بوّابةٍ أخرى يفتح هذه ⇒ تتسرّب التفويضات بين البوّابات. — يُسقِط `test_an_authorization_for_another_gate_does_not_authorise_this_one`
- مخطَّطٌ مجهول يُقرأ إذناً ⇒ أيّ JSON في المجلَّد يصير تفويضاً. — يُسقِط `test_a_malformed_authorization_fails_closed`
- تعطيل رصد الهبوط يُعيد الفجوة نفسها: تفويضٌ استُهلِك ولم يُختَم يبقى `ISSUED` حيّاً بلا أن يُحمِرّ شيء (GATE01-ONE-SHOT-LIFECYCLE-INCOMPLETE-01). — يُسقِط `test_an_issued_authorization_whose_bytes_already_landed_is_flagged_as_spent`
- نزعُ المُميِّز يجعل الفحص «كلّ تفويضٍ بايتاتُه مطابقة» — فيتّهم الرقعةَ المأذونة أثناء PR-ها بأنّها بائتة، وهي بالضرورة مطابقة حينها. — يُسقِط `test_an_authorization_in_flight_on_its_own_paths_is_not_flagged`
- قَلبُ الشرط يجعل «الشجرة تخالف المأذون» تُقرأ هبوطاً — فيُتَّهم تفويضٌ لم تهبط رقعتُه بعد بأنّه مُستهلَك، والحارس الذي يتّهم الصحيح يُنزَع. — يُسقِط `test_an_authorization_whose_bytes_have_not_landed_is_not_flagged`
- غيابُ الملفّ يُقرأ هبوطاً حين يُعلِن التفويض `null` — فيُتَّهم إذنٌ لم تهبط رقعتُه بأنّه مُستهلَك. — يُسقِط `test_an_authorization_over_a_path_absent_from_the_tree_is_not_flagged`
- المختوم يُطالَب بختمٍ تمّ ⇒ حمرةٌ دائمة لا تُرفَع بعملٍ صحيح، وهي أسرع طريق إلى تعطيل الحارس. — يُسقِط `test_a_sealed_authorization_is_not_flagged_again`
- دالّةٌ صحيحة غير مُستدعاة من نقطة الدخول خضرةٌ عن سؤالٍ لم يُطرَح — كلّ اختبارات الوحدة تبقى خضراء وCI لا تفحص شيئاً. — يُسقِط `test_the_lifecycle_check_is_wired_into_the_entry_point`
- `one_time: false` يُقرأ ترخيصاً بإعادة الاستعمال بدل وضعٍ غير منفَّذ ⇒ حقلٌ إعلانيّ يُسكِت فحص دورة الحياة بلا أن يمنحه أحد ذلك، فيُعيد GATE01-ONE-SHOT-LIFECYCLE-INCOMPLETE-01 من حيث أُغلِقت. — يُسقِط `test_a_reusable_authorization_is_refused_as_an_unimplemented_mode`

### `guard_locale_survival_guard.py`

**يفرض:** حارسٌ يموت وهو يطبع نجاحه — GUARD-DIES-PRINTING-ITS-OWN-SUCCESS-UNDER-C-LOCALE-01.

**يحجب في:** `ci.yml` → `unit-tests`

**الاختبار الشاهد:** `tests_v9/test_guard_locale_survival_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- تعطيلُ الرصد يجعل الحارس يمرّ على ١٤٦ حارساً منها ٣٦ تنهار فعلاً — وهو بعينه العطل الذي وُجِد له: أخضرُ يعني «لم أنظر». — يُسقِط `test_an_encoding_death_is_reported`
- `PYTHONIOENCODING` موروثة تجعل المخرَج UTF-8 رغم لغة C، فتمرّ كلّ الحرّاس — تجربةٌ يُبطِلها متغيّرٌ موروث تُبلِغ نجاحاً لم يقع. ومُثبَتٌ بالمقابل: نفس الحارس الميّت يُرصَد بالبيئة المعزولة ولا يُرصَد بالمسرَّبة. — يُسقِط `test_the_probe_strips_inherited_encoding_overrides`
- إشعالُ النفس تعشيشٌ بلا قاع — وقع في أوّل تشغيل فعليّ: ثلاث دقائق لجولةٍ تستغرق دقيقة، والسبب تعشيشٌ لا بطء. — يُسقِط `test_the_guard_never_probes_itself`
- حارسٌ يموت باستيرادٍ ناقص لا يطبع شيئاً، فيعود المسبار فارغاً ويُقرأ سلامةً. وبلا عدّه تصير البوّابة في وظيفةٍ بلا تبعيّات **خضراء على صفر قياس** — وهو الصنف نفسه الذي أسقط `guard_mutation_guard --run` بثمانية عشر «إخفاقاً» صحيحاً بسببٍ خاطئ. — يُسقِط `test_a_guard_that_dies_on_import_is_counted_unmeasured`

### `guard_mutation_guard.py`

**يفرض:** لا حارس بلا عطلٍ مزروع يُثبِت أنّه يُطلِق — GUARDS-WITHOUT-A-PLANTED-DEFECT-01.

**يحجب في:** `ci.yml` → `lint` · `ci.yml` → `unit-tests`

**الاختبار الشاهد:** `tests_v9/test_guard_mutation_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- نزع حجب الحارس الجديد بلا مواصفة ⇒ الآليّة كلّها تصير اختياريّة — يُسقِط `test_a_new_guard_without_a_mutation_spec_is_blocked`
- قبول مواصفة بائتة سلسلتها لم تعد في المصدر — يُسقِط `test_a_stale_mutation_string_is_blocked`
- قبول سلسلة متكرّرة ⇒ الزرع غير محدَّد الموضع — يُسقِط `test_an_ambiguous_mutation_string_is_blocked`
- قبول «سقط شيء ما» بدل الاختبار المُسمّى ⇒ طفرة تكسر الاستيراد تُحسَب نجاحاً — يُسقِط `test_red_by_the_wrong_test_is_not_proof`
- نزع سقف الدَّين — يُسقِط `test_debt_growth_is_blocked_by_the_ceiling`
- نزع حجب المدخل البائت لحارس غير موجود — يُسقِط `test_an_entry_for_a_missing_guard_is_blocked`
- اعتبار الحارس المزروع فيه العطل ناجحاً إن خرج بصفر — يُسقِط `test_a_green_suite_under_a_planted_defect_is_a_failure`
- قبول `expect` بادئةً عامّة لا اسم اختبار موجود ⇒ الشرط يعود إلى «سقط شيء ما» — يُسقِط `test_a_bare_prefix_is_not_an_expected_test`
- اعتبار انهيار المُشغِّل دليلاً ⇒ بيئة بلا pytest تُبلَّغ «حمرّ بغير الاختبار المُتوقَّع» — يُسقِط `test_a_runner_that_never_ran_is_not_evidence`
- نزع تسمية الاختبارات الساقطة فعلاً ⇒ فرع «حمرّ بغير المتوقَّع» يعود غير قابل للتشخيص من سجلّه — يُسقِط `test_the_wrong_test_branch_names_what_actually_failed`
- عودةُ ذاكرة الـbytecode ⇒ طفرتان متساويتا الطول تتبادلان الأثر (السبب الجذريّ المُثبَت للرقيعة) — يُسقِط `test_the_runner_blocks_bytecode_caching`
- إسقاط برهان الاستعادة ⇒ تسرّبٌ بين طفرتين يظهر «عشوائيّةً» لا عطلاً — يُسقِط `test_a_restore_that_did_not_restore_is_reported`
- تعطيل العزل الافتراضيّ على ROOT ⇒ تشغيل CLI يعود إلى زرع الطفرات داخل checkout القانونيّ — يُسقِط `test_real_root_defaults_to_an_isolated_workspace`
- توجيه مصدر الطفرة إلى ci الأصليّ مع بقاء الاختبارات في المرآة ⇒ العزل اسميّ والشجرة القانونية تُمسّ — يُسقِط `test_isolated_runner_never_plants_in_the_legal_checkout`
- إعادة الحكم إلى البحث النصّيّ في كامل المخرَج: اسمٌ يظهر في رسالة تأكيد أو تتبُّع مكدّس أو معامل parametrize يُقرأ سقوطاً، فيُختَم `expected_red` والقاعدة غير محروسة — «سقط شيء ما» بصيغةٍ تختبئ خلف اسمٍ صحيح. — يُسقِط `test_a_name_seen_only_in_the_message_is_not_a_fallen_test`
- مسار الحجب الفعليّ يحمل نسخةً ثانية من الحكم — فتصحيح `_outcome` وحده يترك القرار الحاجب على البحث النصّيّ: دالّةٌ صحيحة لا تحكم، وهي خضرةٌ عن سؤالٍ لم يُطرَح. — يُسقِط `test_the_run_path_decides_on_the_fallen_list_not_on_the_raw_output`
- إهمالُ القسم السلوكيّ يُفرِّغه بلا أن يُحمِّر شيئاً — لا فحصاً ثابتاً ولا زرعاً — والسجلّ يبقى يقول «مقيس». وهذا صنفُ العطل الذي وُجِدت الآليّة كلّها لأجله: صمتٌ يُقرأ خضرةً. — يُسقِط `test_the_real_behavioural_section_is_not_empty`
- لا جردَ للمصادر يُمسِك الشبح كما يُمسِكه `ghost` للحرّاس، فتخطّي المفقود صامتاً يُسقِط المواصفة بلا أثر — نقلُ ملفٍّ أو إعادةُ تسميته تُطفِئ القياس والبوّابة خضراء. — يُسقِط `test_a_behavioural_spec_for_a_missing_source_is_blocked`
- فحصٌ ثابت بلا زرع يُثبِت **وجود** المواصفة لا **صحّتها**: سلسلةٌ موجودة و`expect` قائم، ولا أحد يعرف أنّ الاختبار يحمرّ فعلاً. وهو الفرق نفسه بين «له اختبار» و«مُثبَت بالتكذيب». — يُسقِط `test_a_behavioural_mutation_is_actually_planted_in_its_source`
- إهمالُ جناح الطفرة يُشغّل جناحاً لا يمسّ المصدر، فيمرّ العطل المزروع أخضر — و«حارسٌ يُبلِّغ نتيجةً عن سؤال لم يطرحه» يصير هنا «طفرةٌ تُحاكَم بجناحٍ لا يخصّها». — يُسقِط `test_a_mutation_may_name_its_own_test_file`

### `knowledge_provenance_guard.py`

**يفرض:** `KNOWLEDGE-PROVENANCE-01` — مُنتِجٌ قانونيّ يحمل نَسَبَه، أو لا يُقرأ.

**يحجب في:** `ci.yml` → `structural-lint`

**الاختبار الشاهد:** `tests_v9/test_knowledge_provenance_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- نزعُ فحص النَّسَب ⇒ مُنتِجٌ بلا مرساةٍ زمنيّة يمرّ، فيبقى بند الطزاجة في المُحلِّل معطَّلاً بصمت: كلّ عقدٍ يُعلِن `max_age_seconds` يحجب دائماً بـFRESHNESS_UNMEASURABLE ولا أحد يعرف لماذا. — يُسقِط `test_each_required_provenance_field_is_enforced_on_its_own`
- قبولُ مُنتِجٍ بلا بصمة ⇒ قيمةٌ تُقرأ حقيقةً بلا سبيلٍ إلى مصدرها — وهو الصنف المقيس في M2.6: `verified` ونَسَبُها `None`. — يُسقِط `test_a_producer_without_its_declared_digest_is_blocked`
- عودةُ الافتراض الصامت: بصمةٌ تُخمَّن ليست بصمة. وقد أطلقت أوّلُ صياغةٍ على `canonical_root_zone_profile` لأنّها افترضت `capability_digest` وبصمتُه `profile_digest`. — يُسقِط `test_an_undeclared_digest_field_is_blocked_not_assumed`
- إسقاطُ نمط `Cls(**base, capability_digest=...)` ⇒ إيجابيّةٌ كاذبة على كلّ مُنتِجٍ في هذه الشجرة، وهي تُسقِط الحارس بلا أن تُعطِّله لأنّ قارئ الأحمر يتعلّم تجاهله. — يُسقِط `test_a_digest_assigned_as_a_keyword_still_counts`
- قبولُ «صفر مفحوص» ⇒ أخضرُ لأنّه لم ينظر. — يُسقِط `test_zero_examined_producers_fails_closed`
- قبولُ أيّ مخطَّط ⇒ الحارس يفحص وثيقةً ليست وثيقتَه. — يُسقِط `test_a_wrong_schema_fails_closed`

### `knowledge_relation_registry_guard.py`

**يفرض:** `KNOWLEDGE-RELATION-01` — العلاقة المُسجَّلة هي العلاقة المُنفَّذة.

**يحجب في:** `ci.yml` → `structural-lint`

**الاختبار الشاهد:** `tests_v9/test_knowledge_relation_registry_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- نزعُ البند الحامل كلّه: السجلّ يعود ثلاثيّةً تُكتَب مرّةً وتَبيت بصمت، بينما `REQUIRED_LINKS` ثابتٌ يحكم قراراً — كلُّ حلقةٍ غير متاحة تُضيف حجباً وأضعفُها يُبنى عليه `operational_eligible`. — يُسقِط `test_a_chain_that_drifts_from_the_code_is_blocked`
- قبولُ رمزٍ لا يُقرأ متسلسلاً ⇒ سلسلةٌ لا يقابلها ثابتٌ منفَّذ تمرّ، فيصير «مربوطٌ بالتنفيذ» ادّعاءً في وثيقة. — يُسقِط `test_a_symbol_named_only_in_a_comment_is_not_a_definition`
- دلالةٌ مُعلَنة لا تُفرَض ليست دلالة: `acyclic` تُكتَب ثمّ تُخالَف بلا أثر. — يُسقِط `test_an_acyclic_relation_with_a_repeated_link_is_blocked`
- علاقةٌ موجَّهة طرفاها واحد تمرّ ⇒ الاتّجاه يصير حقلاً بلا معنى. — يُسقِط `test_a_directional_relation_with_identical_ends_is_blocked`
- علاقةٌ لا تقول اتّجاهها لا تُنفَّذ ولا تُختبَر — وقبولُها يُعيد السجلّ رسماً. — يُسقِط `test_a_relation_without_declared_semantics_is_blocked`
- اسمٌ واحد بدلالتين هو «مصدر الحقيقة الظلّ» بوجهه العلائقيّ. — يُسقِط `test_a_duplicate_relation_name_is_blocked`
- صفرُ علاقةٍ مُقابَلةٍ بالتنفيذ يمرّ ⇒ أخضرُ لأنّه لم ينظر. — يُسقِط `test_zero_relations_checked_fails_closed`
- أي علاقة مسجّلة تتحول إلى تنفيذ مباشر تجعل السجل باب سلطة موازياً؛ يجب أن تبقى كل العلاقات وصف/تقييد بلا dispatch مباشر. — يُسقِط `test_no_registered_relation_can_grant_direct_execution`
- reference/evidence لا تملك قراراً؛ إسقاط هذا الحد يحوّل KG/Evidence Graph إلى authority موازية. — يُسقِط `test_reference_relation_cannot_claim_authority`
- العلاقات المرجعية/التفسيرية لا تثبت سببية؛ السماح بذلك يرقّي correlation إلى causal evidence. — يُسقِط `test_evidence_relation_cannot_claim_causality`
- علاقة vocabulary غير موجودة في الثابت التنفيذي تعيد السجل إلى رسم وثائقي غير مربوط بالكود. — يُسقِط `test_vocabulary_bound_relation_must_exist_in_executed_vocabulary`

### `live_pg_evidence_guard.py`

**يفرض:** عقد وظيفة PG المخصّصة — يُفرَض ويُلخَّص، ولا يُوصَف في تعليق.

**يحجب في:** `ci.yml` → `live-pg-fake-connection-proofs`

**الاختبار الشاهد:** `tests_v9/test_live_pg_evidence_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- قبولُ تخطٍّ في الوظيفة المخصّصة ⇒ التخطّي يصير خضرةً تعني «لم يُقَس»، و`SAHOOL_REQUIRE_LIVE_PG` لا يراه لأنّه يحرس غياب القاعدة وحده. والمرساة على **تخطٍّ واحد** لا على التشغيل المُتخطّى بالكامل: الأخير يلتقطه فحصُ «صفر مُنفَّذ» أيضاً، فلا يُميّز الخاصّيّتين — وهو ما كشفته الطفرة حين حمرّ اختبارٌ غير الذي سمّيتُه — يُسقِط `test_one_skipped_live_test_is_enough_to_fail`
- قبولُ صفر اختبار مُنفَّذ ⇒ «أخضرُ لأنّه لم ينظر». والمرساة على الشرط الموحَّد لا على فرع الصفر: أوّل صياغة عندي فصلتهما بـ`if/elif` فكان تعطيل فرع الصفر لا يُسقِط شيئاً — يلتقطه `elif` لأنّ ٠ أصغر من الحدّ، فالفرع زينة لا حارس — يُسقِط `test_zero_executed_is_a_failure`
- نزعُ كشف انحراف المخطّط ⇒ هجرةٌ تُسقِط قيداً تحته دليل تمرّ، فيُقرأ فشل الادّعاء لاحقاً «الاختبار خاطئ» بدل «المخطّط انحرف» — يُسقِط `test_a_missing_contract_object_is_drift`
- نزعُ فحص الإصدار الرئيسيّ ⇒ تعمل الأدلّة على PG15 أو 17 بلا إنذار، وهي مبنيّة على قواعد نحو DDL ورموز SQLSTATE لإصدارٍ بعينه — فيصير الأخضر شهادةً على خادمٍ آخر — يُسقِط `test_a_wrong_major_version_is_drift_but_a_different_patch_is_not`
- نزعُ `-X` و`ON_ERROR_STOP=1` ⇒ يُقرأ `~/.psqlrc` فسطرٌ من `\pset` أو `\timing` يُقرأ قيمةَ كتالوج ويُقارَن بالعقد؛ وخطأ SQL قد يعود بصفر فيُقرأ خرجٌ ناقص «نجاحاً» — وهو الصنف الذي يوجد هذا الحارس ضدّه. والمرساة على ثابتٍ مستقلّ لا على قائمة الوسائط: `ruff format` يفكّك القائمة الطويلة سطراً سطراً فتَبيت سلسلةُ الطفرة عند أوّل إعادة تنسيق — يُسقِط `test_psql_is_fail_closed_and_ignores_psqlrc`
- قبولُ دورٍ خارق ⇒ يتخطّى RLS وكلّ صلاحيّة، فلا يقيس أيّ ادّعاء عزلٍ تحته شيئاً — يُسقِط `test_a_superuser_role_is_rejected`
- قبولُ `BYPASSRLS` ⇒ الخاصّيّة التي يقوم عليها قياس العزل أصلاً. مقيسٌ في هذا المستودع: مالك الجداول كان يتخطّى RLS فمرّ زرعُ `NO FORCE ROW LEVEL SECURITY` بلا قتيل — يُسقِط `test_a_bypassrls_role_is_rejected`
- إعادةُ العطل الأصليّ بعينه: `rolcreatedb` كان يُستعلَم عنه **ويُطبَع في الملخّص** ولا يدخل قرار الرفض — رقمٌ معروض لا حارس، وظهورُه في المخرَج يُقرأ شهادةً على أنّه مفحوص — يُسقِط `test_a_createdb_role_is_rejected`
- قبولُ `CREATEROLE` ⇒ مالكها يُنشئ دوراً يمنحه ما يشاء ثمّ يعمل تحته، فيبلغ بخطوتين ما مُنِع منه بخطوة. ولم تكن تُسأل أصلاً — لا في الاستعلام ولا في القرار — يُسقِط `test_a_createrole_role_is_rejected`
- رفضٌ يعتمد خاصّيّةً لا يقرؤها الاستعلام: ينهار أو — أسوأ — يقرأ قيمةً في خانةٍ ليست لها. والقائمتان منفصلتان عمداً كي تبقى هذه الطفرة مستقلّة عن طفرات قرار الرفض — يُسقِط `test_the_catalogue_query_asks_for_every_gating_attribute`
- قبولُ قيمةٍ ليست `true` ولا `false` ⇒ تمرّ على مقارنة «ليست false» فتُقرأ تقييداً وهي مجهولة — حكمٌ بثقةٍ كاملة على سؤالٍ لم يُجَب — يُسقِط `test_a_malformed_role_row_is_fail_closed`
- قبولُ صفٍّ بعدد حقولٍ مختلف ⇒ تنزلق القيم خانةً فيُقرأ `rolcreatedb` مكان `rolbypassrls`. طفرةٌ مستقلّة عن سابقتها: تلك تحرس **قيمة** الحقل وهذه تحرس **محاذاته** — يُسقِط `test_a_malformed_role_row_is_fail_closed`
- دليلٌ لا يقول عن أيّ التزامٍ يتكلّم ادّعاءٌ بلا مرجع — و`GITHUB_SHA` وحده لا يكفي لأنّه في أحداث `pull_request` يشير إلى دمجٍ وهميّ لا إلى الشجرة المقيسة — يُسقِط `test_the_evidence_binds_the_tested_commit_and_tree`
- الشجرة تُكتَب مع الالتزام لأنّ الالتزام قد يُعاد كتابته بمحتوى الشجرة نفسه — والمحتوى هو ما قِيس. طفرةٌ مستقلّة: نزعُ أحدهما لا ينزع الآخر — يُسقِط `test_the_evidence_binds_the_tested_commit_and_tree`
- وثيقةٌ لا توجد إلّا حين ينجح كلّ شيء ليست دليلاً — الدليل يُطلَب يوم الفشل. والكتابة **قبل** إعادة رمز الخروج جزءٌ من العقد لا ترتيبٌ عارض — يُسقِط `test_the_evidence_is_written_on_failure_not_only_on_success`
- نزعُ تهريب الاقتباس ⇒ `ops'role` يكسر الاستعلام و`x' OR true --` يُغيّر الصفّ المقروء. ومدى الاستغلال اليوم ضيّق (CI يمرّر ثابتاً)، لكنّ الواجهة تقبل القيمة من راية وبيئة — فالعطل عطلُ سلامةٍ في الواجهة لا في استعمالها — يُسقِط `test_a_role_name_reaches_psql_escaped`
- دالّةُ تهريبٍ موجودة **ولا تُستدعى** — طفرةٌ مستقلّة عن نزع جسمها: الأولى تحرس التهريب نفسه، وهذه تحرس **وصولَه إلى موضع الاستعمال** — يُسقِط `test_a_role_name_reaches_psql_escaped`
- إعادةُ العطل المُبلَّغ على #816 بعينه: النصّ الخام يضمّ أوّل ٤٠٠ محرف من `stderr`، فيتسرّب المضيف وعنوانه والمنفذ واسم المستخدم وكلمة المرور إلى ملفٍّ يُرفَع مصنوعةً — بينما `$comment` فيه ينفي ذلك — يُسقِط `test_a_psql_diagnostic_never_reaches_the_uploaded_evidence`
- ارتدادٌ إلى الخام عند غياب التصنيف ⇒ الإصلاح يصير مشروطاً بأن يتذكّر كاتبُ المسار القادم. الافتراضيّ الآمن هو الصمت عن التفصيل لا نشرُه — وهذه طفرة مستقلّة عن سابقتها: تلك تحرس المسار المُصنَّف وهذه تحرس غير المُصنَّف — يُسقِط `test_an_unclassified_fail_closed_exit_still_leaks_nothing`
- خروجٌ مغلق يفقد سببه المُصنَّف ⇒ يسقط إلى المجهول. والتأكيد يقرأ المصدر بـ`ast` لا بالنصّ، فيُقاس **اكتمال التصنيف** لا «صنّفتُ ما تذكّرت»: مسارٌ سادس يُضاف غداً بـ`SystemExit` عارية كان سيمرّ صامتاً — يُسقِط `test_every_fail_closed_exit_in_the_guard_carries_an_evidence_reason`

### `live_pg_role_closure_guard.py`

**يفرض:** Fail-closed proof that the dedicated live-PG application role is standalone.

**يحجب في:** `ci.yml` → `live-pg-fake-connection-proofs`

**الاختبار الشاهد:** `tests_v9/test_live_pg_role_closure_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- قبول أي عضوية للدور المخصص للأدلة يعيد الاعتماد على pg_auth_members ويجعل حدود الصلاحية قابلة للتغير عبر INHERIT/SET/ADMIN دون تغير خصائص الدور المباشرة — يُسقِط `test_a_direct_inherit_membership_is_rejected`
- غياب الدور لا يجوز أن يتحول إلى PASS على closure فارغة؛ «لا صف» ليس «دوراً مستقلاً ومقاساً» — يُسقِط `test_a_missing_role_fails_closed_and_leaves_evidence`
- اسم الدور يأتي من الراية/البيئة؛ نزع تهريب الاقتباس يكسر الاستعلام أو يغير الصف المقروء بدلاً من قياس الدور المطلوب — يُسقِط `test_role_name_reaches_both_catalogue_queries_escaped`
- إعادة التشخيص الخام إلى JSON المرفوع قد تسرب المضيف والمنفذ والمستخدم وكلمة المرور؛ المصنوعة تحمل أسباباً ثابتة فقط — يُسقِط `test_raw_psql_diagnostic_never_enters_uploaded_evidence`

### `no_report_only_change_guard.py`

**يفرض:** Guard against report-only certification/progress changes in CI.

**يحجب في:** `no-report-only-change.yml` → `no-report-only-change`

**الاختبار الشاهد:** `tests_v9/test_no_report_only_change_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- إسقاط frontend/ من التصنيف يعيد العطل المقيس على #857 حرفيّاً: إصلاح UI حقيقيّ + مصنوعات مولَّدة يُحجَب «report-only» — رسالة الحارس تدعو لـcode والتنفيذ لا يعترف بكوده — يُسقِط `test_frontend_code_with_generated_report_is_substantive`
- نزع قاعدة الحجب نفسها ⇒ تقارير مولَّدة وحدها تعبر كتغيير مشروع — الحارس أخضر إلى الأبد وهو يحرس لا شيء — يُسقِط `test_report_only_change_is_blocked`

### `platform_module_reachability_guard.py`

**يفرض:** Classify platform modules by the executable root that can actually reach them.

**يحجب في:** `capability-governance.yml` → `capability-registry`

**الاختبار الشاهد:** `tests_v9/test_platform_module_reachability_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- نزع فهرسة الحزمة باسمها ⇒ كلّ سلسلة تمرّ بـ__init__ تبدو مقطوعة، فتُصنَّف وحدات موصولة فعلاً كسلاسل طرفيّة ميتة — الحارس يخترع العطل بدل أن يجده — يُسقِط `test_a_module_behind_a_package_is_reachable_not_terminal`
- ترك الاستيراد النسبيّ بلا حلّ ⇒ from .canonical_water import … لا يُنتِج حافّة، فتبدو canonical_water/canonical_boundary ميتتين وهما مستهلَكتان — يُسقِط `test_relative_imports_resolve_against_the_importing_package`
- جعل كلّ وحدة قابلة للوصول ابتداءً ⇒ التصنيف يفقد قدرته على قول (ميت)، وهو الغرض الوحيد للحارس — يُسقِط `test_a_module_nothing_executes_is_terminal`
- المُشغِّل المُنفَّذ بمسار يُعَدّ قناةً لا جذراً ⇒ نقطة الدخول نفسها تُصنَّف «ميتة» بينما compose يشغّلها — يُسقِط `test_a_path_launched_worker_inside_the_platform_is_a_root_itself`
- ‏/app يُقرأ جذرَ المستودع لا جذرَ الخدمة — الافتراض الذي أنتج CONTAINER-COMMAND-PATH-NOT-IN-IMAGE-01 — يُسقِط `test_the_container_path_maps_to_the_service_root_not_the_repository_root`

### `probe_leak_guard.py`

**يفرض:** يُسمّي مِسبار اختبار تسرّب إلى الشجرة، بدل تركه يُشخَّص خطأً — `TEST-PROBE-LEAKS-INTO-THE-TREE-01`.

**يحجب في:** `ci.yml` → `lint`

**الاختبار الشاهد:** `tests_v9/test_probe_leak_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- نزع استثناء المواضع الشرعيّة ⇒ الحارس يُطلِق على الاختبار الذي يُعرّف المِسبار وعلى الدماغ الذي يشرح الحادثة — يُسقِط `test_the_guard_does_not_fire_on_the_places_that_legitimately_name_the_probe`

### `prohibition_reason_guard.py`

**يفرض:** مَنعٌ بلا سببٍ مُعلَن — `GUARD-PINS-IMPLEMENTATION-NOT-PROPERTY-01`.

**يحجب في:** `ci.yml` → `lint`

**الاختبار الشاهد:** `tests_v9/test_prohibition_reason_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- إسقاط صيغة `not ("x" in y)` — حارسٌ يرى صيغةً واحدة يُلتَفّ عليه بإعادة صياغة لا تُغيّر شيئاً، ولا يحتاج الالتفافُ نيّةً سيّئة: يكفي أن يكتبها أحدٌ هكذا — يُسقِط `test_the_other_spelling_of_a_prohibition_is_caught_too`
- نزع اشتراط أن تكون الحاوية **نصّ مصدر** ⇒ يمتدّ الحارس إلى كلّ تأكيد سالب في المستودع فيُنزَع في أوّل يوم. والمرساة على ملفّ يحمل قارئاً حقيقيّاً: أوّل صياغة عندي لم تحمله فتخطّى المسحُ الملفَّ كلّه، فمرّ الاختبار **بسببٍ آخر** وبقيت الخاصّيّة بلا حارس — كشفَته هذه الطفرة بالذات وهي خضراء — يُسقِط `test_the_container_is_derived_from_the_assignment_not_from_its_name`

### `rag_operational_boundary_guard.py`

**يفرض:** `RAG-ANSWERS-AN-OPERATIONAL-FACT-01` — الاسترجاع لا يجيب عن حقيقةٍ تشغيليّة.

**يحجب في:** `ci.yml` → `structural-lint`

**الاختبار الشاهد:** `tests_v9/test_rag_operational_boundary_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- نزعُ البند الوحيد: وحدةُ استرجاعٍ تجيب عن الحدّ الآمن تمرّ. ومُخرَجُ الاسترجاع نصٌّ معقولٌ دائماً، فالرقم الناتج يبدو صحيحاً ولم يمرّ بالميل ولا التسرّب ولا شهادة الحزمة. — يُسقِط `test_a_rag_module_naming_an_operational_key_is_blocked`
- مُنتِجٌ قانونيّ يستمدّ حقيقتَه من نصٍّ مُولَّد يقلب اتّجاه الثقة كلَّه: مصدرُ الحقيقة يصير مُستهلِكاً للتخمين. — يُسقِط `test_a_canonical_producer_that_reaches_rag_is_blocked`
- عدُّ نصوص التوثيق استعمالاً يجعل الشرح الذي يقول «هذا لا يُسأل عنه الاسترجاع» يُحمِر الحارس — فيتعلّم كاتبُه حذف التوثيق: رقمٌ أخضر وتوثيقٌ أقلّ. — يُسقِط `test_a_mention_inside_a_docstring_is_not_a_use`
- توسيعُ الحدّ إلى غير الاسترجاع يُجرّم كلّ مستهلِكٍ قانونيّ — إيجابيّةٌ كاذبة شاملة تُسقِط الحارس أوّل يوم. — يُسقِط `test_a_non_rag_module_may_name_operational_facts_freely`
- صفرُ وحدةٍ تبلغ الاسترجاع يمرّ ⇒ الحدّ لم يُقَس، أو العلامات بائتة والحارس يحرس لا شيء. — يُسقِط `test_zero_rag_modules_fails_closed`
- قبولُ أيّ مخطَّط ⇒ الحارس يفحص وثيقةً ليست وثيقتَه، فتُقرأ «صفر حقيقة تشغيليّة» ويصير الحدّ فارغاً. — يُسقِط `test_a_wrong_schema_fails_closed`

### `run_outcome_guard.py`

**يفرض:** خلاصةُ تشغيلٍ مكتمل، مُشتقّةً من استجابتَي GitHub لا مكتوبةً بيد.

**يحجب في:** `certify-run.yml` → `certify`

**الاختبار الشاهد:** `tests_v9/test_run_outcome_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- تشغيلٌ لم يكتمل خلاصتُه `null`، فتُقرأ «ليست success» فتحجب — لكنّ قبولَ اللقطة أصلاً يفتح باباً لاعتمادٍ يُبنى على جردٍ ناقص: وظائفُ لم تبدأ بعدُ تُقرأ كأنّها كلّ ما سيجري. — يُسقِط `test_a_run_still_in_progress_is_refused`
- جردٌ فارغ يجعل شرط «كلّ الوظائف ناجحة» صادقاً خواءً (`any` على فراغ = False)، فيمرّ **كلّ** تشغيل. وهو صنف «حارسٌ يُحقّقه لا شيء» بعينه. — يُسقِط `test_an_empty_job_inventory_is_refused`
- workflow آخر في نفس المستودع يُنتِج خلاصةً **صادقة عن شيء غير المقصود** — وهو نفس صنف «نتيجةٌ صحيحة عن سؤالٍ لم يُطرَح» الذي أسقط أوّل صياغة لحارس حماية الفرع. — يُسقِط `test_a_run_of_another_workflow_is_refused`
- وظيفةٌ لم تكتمل خلاصتُها `null`، وقراءتُها نجاحاً تُحوِّل «لم تنتهِ» إلى «نجحت» — وهو أخطر أشكال الفشل المفتوح: يُبلِغ اعتماداً عن عملٍ لم يقع. — يُسقِط `test_an_incomplete_job_is_recorded_by_its_status_not_as_blank`
- قاموسٌ يبتلع الاسم المكرَّر يجعل «كلّ مطلوبةٍ حاضرة مرّةً واحدة» غير قابلٍ للقياس: آخرُ قيمةٍ تفوز صامتةً، وقد تكون success فوق failure — فيُعتمَد على جردٍ فاسد. — يُسقِط `test_a_duplicate_job_name_is_refused_as_inventory_corruption`
- إغلاق هويّة التشغيل يطابق الـtuple الكاملة ومنها المستودع؛ وثيقةٌ بلا مستودعٍ مُسمّى تجعل طرفَ المطابقة فراغاً — والإغلاق على فراغٍ ليس إغلاقاً. — يُسقِط `test_the_outcome_document_names_its_repository`

### `schema_validation_guard.py`

**يفرض:** One validator for every ``*.schema.json`` in the repository.

**يحجب في:** `ci.yml` → `structural-lint`

**الاختبار الشاهد:** `tests_v9/test_schema_validation_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- قبولُ مخطَّط بلا $schema ⇒ يعود أحد عشر ملفّاً لا يُعرَف بأيّ مواصفة تُقرأ، وهو العطل الأصليّ الذي بُنِيت البوّابة له — يُسقِط `test_a_missing_meta_schema_is_caught`
- قبولُ $ref خارجيّ ⇒ يصير الخضوع رهن الشبكة وترتيب الملفّات لا صحّة العقد — يُسقِط `test_an_external_ref_is_caught`
- تخطّي التحقّق من صحّة المخطَّط نفسه ⇒ الحارس يُبلِغ خضرةً عن سؤال لم يطرحه — يُسقِط `test_a_schema_invalid_for_its_declared_draft_is_caught`

### `shadow_source_of_truth_guard.py`

**يفرض:** `SHADOW-SOURCE-OF-TRUTH-01` — مفتاحٌ واحد، مُنتِجٌ واحد، وعقودٌ لا تُخالِف السجلّ.

**يحجب في:** `ci.yml` → `structural-lint`

**الاختبار الشاهد:** `tests_v9/test_shadow_source_of_truth_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- قبولُ مفتاحٍ بمُنتِجَين ⇒ عودةُ العطل المقيس بعينه: `maximum_safe_depth_mm_event` كان اسماً واحداً لقيمتين مختلفتي المعنى، ونَسَبُ إحداهما إلى الأخرى كذب. — يُسقِط `test_two_producers_for_one_key_are_blocked`
- اسمُ المصدر هويّةٌ لا وصف؛ ومِلَفّان يدّعيانه يجعلان النَّسَب غير قابلٍ للحلّ — فيصير `source_of_truth` سلسلةً لا مرجعاً. — يُسقِط `test_one_source_name_claimed_by_two_modules_is_blocked`
- أرخصُ طريقٍ إلى مصدر الحقيقة الظلّ وأخفاه: إعلانٌ واحد في عقدٍ يخالف السجلّ، بلا لمسِ أيّ مُنتِج. — يُسقِط `test_a_contract_naming_a_different_source_is_blocked`
- عقدٌ يُعلِن مفتاحاً غير مُسجَّل يَعِد بمعرفةٍ لا مصدر لها، فيمرّ إلى المُحلِّل ويُحجَب هناك بسببٍ أبعد عن موضع الخطأ. — يُسقِط `test_a_contract_declaring_an_unregistered_key_is_blocked`
- «لم يُقرأ إعلان» ليس «كلّ الإعلانات موافقة» — والبند الثالث كلّه يصير بلا قياس. — يُسقِط `test_zero_declared_requirements_fails_closed`
- قبولُ أيّ مخطَّط ⇒ الحارس يفحص وثيقةً ليست وثيقتَه. — يُسقِط `test_a_wrong_schema_fails_closed`
- إسقاطُ الإعلان الموضعيّ ⇒ `KnowledgeRequirement("k", "sot")` لا يُقارَن بالسجلّ إطلاقاً، فيمرّ عقدٌ يخالفه **غير مرئيّ** — وهو أخفى من مخالفةٍ صريحة. — يُسقِط `test_a_positionally_declared_contract_is_compared_to_the_registry`

### `snapshot_eligibility_separation_guard.py`

**يفرض:** اللقطة لا تكتسب أهليّة — `CANONICAL-SNAPSHOT-ELIGIBILITY-POLICY-01`.

**يحجب في:** `ci.yml` → `lint`

**الاختبار الشاهد:** `tests_v9/test_snapshot_eligibility_separation_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- قراءة `CREATE TABLE` وحدها ⇒ يمرّ `ALTER TABLE ... ADD COLUMN` — وهو المسار **الأرجح عمليّاً**، لأنّ أحداً لا يُعيد كتابة تعريف جدول قائم؛ فيُضاف عمود الأهليّة في هجرة لاحقة والحارس ساكت — يُسقِط `test_an_alter_table_add_column_is_caught_too`
- نزع إنفاذ وجود الموضوع ⇒ إعادة تسمية الجدول تجعل الحارس أخضر لأنّه **لا يرى** لا لأنّه لا يجد. الصنف نفسه المُسجَّل في `runtime_contract_generator` — يُسقِط `test_losing_its_subject_is_a_failure_not_a_pass`
- نزع فحص النموذج ⇒ حقلٌ يُضاف إلى `VegetationSnapshotIn` لأنّ واجهةً احتاجته يمرّ. **ادّعيتُ في متن #810 ثلاث طفرات وسجّلتُ اثنتين** — والمراجعة أمسكت الفارق، فهذه هي الثالثة مُسجَّلةً لا مذكورة — يُسقِط `test_an_eligibility_field_on_the_model_is_caught`
- إعادة الصيغة التي أفلتت `ADD COLUMN IF NOT EXISTS`: يُلتقَط `IF` بوصفه اسم العمود فيمرّ الاسم المحظور. والنمط يظهر ٢١ مرّة في هجرات هذه الخدمة — فأرجح طريقٍ إلى العطل كانت الوحيدة التي لا يراها الحارس. وبعد النظرة الأمام صار الأثر أنظف: لا التقاط أصلاً بدل التقاط `IF` — والاختبار يحمرّ في الحالين — يُسقِط `test_add_column_if_not_exists_does_not_slip_through`
- عكسُ ترتيب `IF EXISTS` و`ONLY` — وقواعد PostgreSQL هي `ALTER TABLE [ IF EXISTS ] [ ONLY ] name`. بالترتيب المعكوس تفلت الصيغة القانونيّة `ALTER TABLE IF EXISTS ONLY …` **تماماً**: صفر التقاط لا اسمٌ خاطئ. ثاني ثقب في النحو نفسه — حارس DDL يُكتَب من القواعد المنشورة لا من الصيغة المُصادَفة — يُسقِط `test_the_full_postgresql_grammar_is_caught`
- نزع النجمة الوراثيّة `name [ * ]` من النمط — وهي جزءٌ من القواعد نفسها: `ALTER TABLE <t> * ADD COLUMN decision_eligible` صيغةٌ مشروعة تمرّ بلا التقاط. الثقب الثالث في النحو نفسه، وقد بقي بعد تصحيح ترتيب `IF EXISTS`/`ONLY` — يُسقِط `test_every_legal_alter_prefix_is_caught`
- نزع دعم اقتباس **الجدول** ⇒ `ALTER TABLE public."<t>" ADD COLUMN decision_eligible` — هجرة مشروعة تماماً — تمرّ بصفر التقاط. الاقتباس في PostgreSQL يحفظ حالة الأحرف ولا يُنشئ كياناً آخر؛ الثقب الرابع في النحو نفسه — يُسقِط `test_a_quoted_identifier_is_the_same_identifier`
- نزع دعم اقتباس **العمود** ⇒ `ADD COLUMN "policy_version"` لا يُلتقَط. وقبل النظرة الأمام كان الأسوأ: `(\w+)` يفشل عند `"` فيتراجع المُطابِق عن `(?:column\s+)?` **ويلتقط `COLUMN` اسمَ عمود** — خضرةٌ بعد أن نظر ورأى الشيء الخطأ — يُسقِط `test_the_word_column_is_never_captured_as_a_column_name`
- نزع دعم اقتباس العمود داخل جسم `CREATE TABLE` ⇒ تجاوزٌ **صامت** مؤكَّد: الجسم يُوجَد والحقل يفلت — بخلاف الجدول المقتبس الذي كان يُسقِط الموضوع فيفشل الحارس بصوتٍ عالٍ. والصامت أخطر لأنّ لا شيء يدلّ عليه — يُسقِط `test_a_quoted_column_inside_create_table_is_caught`

### `sot_provenance_guard.py`

**يحجب في:** `ci.yml` → `live-pg-fake-connection-proofs`

**الاختبار الشاهد:** `tests_v9/test_sot_provenance_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- قبول بصمة subject مخالفة يلغي ربط البايتات بالـmanifest. — يُسقِط `test_digest_mismatch_is_rejected`
- ملف زائد غير معلن يعيد مشكلة 23/25 كواقع غير محروس. — يُسقِط `test_unmanifested_file_is_rejected_by_exact_closure`
- قبول workflow غير المتوقعة يوسع actor identity صامتاً. — يُسقِط `test_gh_command_requires_exact_signer_workflow_and_oidc`
- انفصال المصدر المقاس عن source digest الموثق يعيد TOCTOU. — يُسقِط `test_gh_command_requires_source_digest_and_ref`
- تبديل ref يسمح بمصنوعة صحيحة من سياق آخر. — يُسقِط `test_gh_command_requires_source_digest_and_ref`
- trusted root ليست metadata؛ تغييرها يغير جذر الثقة. — يُسقِط `test_gh_command_denies_self_hosted_and_uses_trusted_root`
- إزالة القيد توسع هوية builder من دون قرار. — يُسقِط `test_gh_command_denies_self_hosted_and_uses_trusted_root`
- فشل الأداة الرسمية لا يجوز أن يتحول إلى PASS. — يُسقِط `test_failed_gh_verification_never_becomes_pass`
- السياسة تفترض إغلاقاً `exact` ولم يكن مفحوصاً: بيانٌ يعلن وضعاً آخر يمرّ فيصير «الإغلاق التامّ» ادّعاءً في وثيقةٍ لا يفرضه أحد — يُسقِط `test_a_malformed_closure_is_rejected_with_its_own_reason`
- `set(...)` على غير قائمةٍ نصّيّة يرمي TypeError فيُبلَّغ VERIFIER_INTERNAL_ERROR — سببٌ يقول «عطبٌ في المُصادِق» بينما العطب في البيان، فيبحث المُصلِح في المكان الخطأ — يُسقِط `test_a_malformed_closure_is_rejected_with_its_own_reason`
- حقلٌ متقاطعٌ مخالف لا يُقرأ في هذا الوضع، فبيانٌ يقول «الالتزام مطابق» ويحمل شجرةً مخالفة يمرّ متناقضاً داخليّاً — والمُصادِق لا يجوز أن يفترض أنّ البيان جاء من الأداة الرسميّة — يُسقِط `test_the_verifier_rejects_a_manifest_that_contradicts_itself`
- نزعُ نطاق المرجع يُعيد الثغرة بعينها: دفعةٌ إلى فرع عملٍ غير محميّ تبلغ L5 بربطٍ سليمٍ تماماً — وهي الحادثة المقيسة على ffc29415. — يُسقِط `test_a_feature_branch_with_exact_commit_binding_is_not_release_bound`
- سياسةٌ ناقصة تُقرَأ متساهلةً بدل أن تفشل مغلقةً — فحذفُ حقلٍ من السياسة يصير طريقاً صامتاً إلى L5. — يُسقِط `test_a_policy_without_a_release_ref_list_is_an_incomplete_contract_not_a_permissive_one`
- وضعُ الدمج بلا قياس مرجع الإصدار الذي يسمّيه: يبقى بابٌ يبلغ L4 من أيّ مصدر بمجرّد إعلان binding_evidence. — يُسقِط `test_merge_to_release_is_measured_by_the_release_ref_it_names`
- بلا هذا الفرع تُبلَّغ وثيقةٌ مشوَّهة `EXECUTION_RUN_NOT_SUCCESSFUL` — دعوى عن **التشغيل** («انتهى فاشلاً») مكانَ دعوى عن **الوثيقة** («تعذّر أن أقرأها»). ورموزُ الأسباب هنا سجلُّ التدقيق نفسه، فيقرأ قارئُه سقوطَ تشغيلٍ لم يسقط. وهو الصنف الذي أغلقته هذه الـPR في `changed.txt` — «تعذّر أن أعرف» يُكتَب بلغة «عرفتُ أنّه لا» — وقد وقع في شيفرتها هي، ورفعته مراجعةٌ آليّة. وبلاه أيضاً تمرّ أيّ حمولةٍ من أداةٍ أخرى تصادف أن تحمل المفاتيح المفحوصة، فيصير عقدُ المُنتِج غير مُلزِم. — يُسقِط `test_a_malformed_outcome_is_not_reported_as_a_failed_run`
- هذا هو العطل الذي كُشِف بالتحقّق المستقلّ: حزمة Sigstore صحيحة تشفيريّاً بالكامل — توقيع DSSE، وربطُ payloadHash بـRekor، وإثبات Merkle، وهويّة Fulcio — والتشغيل الذي أنتجها خلاصتُه `failure`. وبلا هذا الفرع يصير «attested ⇒ certified»، فيكفي لبلوغ L5 أن تُنتَج مصنوعتان تقولان PASS في تشغيلٍ ساقط. — يُسقِط `test_a_failed_run_is_refused_even_though_the_bundle_is_valid`
- قراءةُ الغياب نجاحاً تُفرِّغ الشرط كلّه: كلّ بيانٍ قديم أو مصنوعٍ يدويّاً يبلغ L4/L5 بلا أن يُعلِن خلاصة تشغيله. و«لم يُقَس» ليس «مرّ». — يُسقِط `test_a_manifest_without_an_execution_outcome_is_not_read_as_success`
- بلا الربط بالالتزام تصلح خلاصةُ **أيّ** تشغيلٍ ناجح شهادةً لأيّ لقطة — وهو نفس صنف «دليلٌ من SHA سابق» الذي يمنعه ظرفُ دليل حماية الفرع. — يُسقِط `test_an_outcome_for_another_commit_does_not_vouch_for_this_one`
- الخلاصة المجمَّعة ليست دليلاً — درسٌ مُسجَّل في هذا المستودع باسمه `JOB-STATUS-HID-A-FAILED-STEP-01`. ووظيفةٌ ساقطة داخل تشغيلٍ يُعلَن ناجحاً هي بالضبط ما وقع في run 31728316326 (`Repository Tests`). — يُسقِط `test_a_failed_job_inside_a_green_run_is_refused`
- شرطٌ معطَّل **وصامت** رخصةٌ مفتوحة: سجلٌّ يقول L5 ولا يقول «وخلاصةُ التشغيل لم تُعلَن» يُقرَأ اعتماداً كاملاً وهو ليس منه. وكتابةُ الدَّين هي ما يفصل «مؤجَّل بسببٍ مقيس» عن «متروك». — يُسقِط `test_a_missing_outcome_is_recorded_even_while_unenforced`
- الثغرة التي لا يراها «كلّ الوظائف نجحت»: حذفُ وظيفةٍ أو إعادةُ تسميتها يُخرِجها من الجرد فيبقى التشغيل ناجحاً وقد فُقِد قياسُها. حلقةٌ على فراغ تجعل `required ⊆ observed` صادقاً خواءً عن كلّ تشغيل. — يُسقِط `test_a_required_job_absent_from_the_inventory_is_named_missing`
- إغلاق الهويّة على الـtuple الكاملة هو ما يمنع خلاصةَ تشغيلٍ آخر — محاولةً ثانية أو workflow آخر على الالتزام نفسه — من أن تشهد لهذا الدليل. إقفالٌ دائم يُعيد الاعتماد إلى مطابقة SHA وحده. — يُسقِط `test_any_broken_tuple_member_breaks_the_closure`
- بيانٌ قديم — أو مُنتَجٌ بأداةٍ لا تُسمّي مُنتِجها — كان سيمرّ من الإغلاق بلا أن يُغلَق شيء: «لم يُقَس» يُقرأ «مرّ»، وهو الصنف الذي بُنِيت هذه السلسلة كلُّها لمنعه. — يُسقِط `test_a_manifest_without_a_producer_identity_cannot_close`
- سجلُّ عقد المصنوعة يدخل سجلَّ الاعتماد كما هو — فإن لم يُطابَق موضوعُه (هذه اللقطة، حالة present) صار سجلُّ اعتمادٍ يحمل هويّات مصنوعاتٍ عن شيءٍ آخر، والقارئ يثق بالمجاورة. — يُسقِط `test_an_artifact_provenance_that_is_not_this_subject_is_refused`
- رفعته مراجعة آليّة على #852 وأصابت: جردٌ غير قاموسيّ كان يُبلَّغ EXECUTION_JOBS_UNDECLARED — دعوى عن الوظائف مكان دعوى عن الوثيقة — ويدخل عقدَ الوظائف المطلوبة بوصفه فراغاً. ورموز الأسباب هي سجلّ التدقيق. — يُسقِط `test_a_non_dict_job_inventory_is_a_malformed_document_not_undeclared_jobs`

### `tenant_guc_scope_guard.py`

**يفرض:** حارس نطاق GUC المستأجِر — شجريّ لا ملفٌّ واحد. ``GUC-SCOPE-GUARD-SEES-ONE-FILE-01``.

**يحجب في:** `ci.yml` → `structural-lint`

**الاختبار الشاهد:** `tests_v9/test_tenant_guc_scope_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- نزعُ فحص الاحتواء داخل معاملة ⇒ كلّ موضع يُعَدّ سليماً، فيعود الحارس يقيس **وجود** set_config لا **نطاقه** — وهو العطل الأصليّ في `tenant_query_audit.py` الذي منح كلّ موضعٍ معيبٍ شهادة EXPLICIT. — يُسقِط `test_a_new_offender_outside_a_transaction_is_blocked`
- نزعُ الترسية على وسائط الاستدعاء ⇒ يعود الكشف يقرأ نصّ الملفّ، فيلتقط **شرح الحارس نفسه** مخالفةً — وقع فعلاً في أوّل صيغة. ملفٌّ يصف عيباً ليس ملفّاً يرتكبه، والـAST وحدها تفرّق. — يُسقِط `test_prose_describing_the_defect_is_not_counted_as_committing_it`
- ترقيةُ بياتِ `measured_on` إلى حجب ⇒ كلّ دمجٍ بـsquash يُحمِّر الحارس بلا تغيّرٍ دلاليّ واحد. الختمُ إشارةُ إسناد لا شهادةُ تطابق — GOV-01. — يُسقِط `test_a_stale_stamp_passes_when_re_derivation_still_matches`
- إلغاءُ أثر إعادة الاشتقاق ⇒ يُقارَن الأساس بنفسه فيمرّ أبداً، ولا يبقى للقارئ إلّا `measured_on` — وهو ما يجعل الختم يُقرأ سلطةَ طزاجةٍ وهو ليس كذلك. — يُسقِط `test_a_stale_stamp_fails_when_re_derivation_diverges`

### `test_marker_coverage_guard.py`

**يفرض:** يمنع وُلود اختبار خامد: ملفّ في ``tests_v9`` بلا علامة لا يعمل في أيّ وظيفة CI.

**يحجب في:** `ci.yml` → `unit-tests`

**الاختبار الشاهد:** `tests/architecture/test_marker_coverage_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- إعادة النمط المسطّح — وهو العطل الذي أسقط ملفّين حقيقيّين: `tests_v9/runtime_activation/` بثمانية اختبارات كان ميّتاً في كلّ وظيفة، و**غير قابل للظهور في الأساس أصلاً** لأنّ الحارس لا يعدّه. والمرساة على حالة مزروعة في مستودع اصطناعيّ لا على عدّاد الملفّات: العدّ ٦٥٨ ⇒ ٦٥٦ فرقٌ لا يُميّزه تأكيد على الحجم — يُسقِط `test_a_file_in_a_subdirectory_is_seen`
- نزعُ التحقّق من أنّ الاسم **مُسجَّل في pytest.ini**: عندها يُقرأ `pytestmark = pytest.mark.asyncio` موسوماً بينما pytest يستبعده من كلّ وظيفة — موسومٌ ظاهراً، ميّتٌ فعلاً. وهو ما كان يفعله التعبير النمطيّ القديم بمطابقة `pytestmark` مجرّداً — يُسقِط `test_a_marker_that_pytest_ini_does_not_declare_is_not_a_marker`

### `undeclared_context_dependency_guard.py`

**يفرض:** `UNDECLARED-CONTEXT-DEPENDENCY-01` — مُستهلِكٌ عبر الطبقة يُعلِن ما يطلبه.

**يحجب في:** `ci.yml` → `structural-lint`

**الاختبار الشاهد:** `tests_v9/test_undeclared_context_dependency_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- نزعُ البند الوحيد الذي يوجد الحارس لأجله: طلبٌ عبر المُحلِّل بلا إعلان يمرّ، فتعود التبعيّة إلى رأس كاتبها — وهو ما بُنيت الطبقة لإخراجه منه. — يُسقِط `test_a_registered_but_undeclared_request_is_blocked`
- طلبُ مفتاحٍ لا مصدر حقيقةٍ له يسقط إلى رسالة «غير مُعلَن»، فيبحث المُصلِح عن عقدٍ ينقصه بينما المفقود مصدرٌ أصلاً. — يُسقِط `test_an_unregistered_request_is_blocked_with_its_own_reason`
- من يسأل عن النَّسَب يعتمد على المفتاح اعتماداً كاملاً؛ وإسقاطُ `provenance` يترك باباً مفتوحاً بلا سبب. — يُسقِط `test_provenance_is_watched_like_require`
- عدُّ كلّ استدعاءٍ ذي سمة طلباً ⇒ ضجيجٌ يجعل قارئ الأحمر يتجاهله، وهو ما يُسقِط الحارس بلا تعطيله. ومرساتُه أُعيدت: توسيعُ الحصر لا يُحمِر اختبار التعليق (التعليقات لا تصل إلى ast أصلاً) بل يُحمِر الشجرة الحيّة — أي «حمرّ بغير المتوقَّع». — يُسقِط `test_another_method_with_a_string_argument_is_not_a_request`
- مسحُ الاختبارات ⇒ مفاتيحُ تركيبيّة في تجهيزاتها تُحمِر حارس الإنتاج، فيُنزَع أوّل يوم. — يُسقِط `test_test_files_are_not_scanned`
- بلا عقدٍ مقروء يمرّ الحارس على عالمٍ فارغ فيقول «لا مخالفة» عن سؤالٍ لم يُطرَح — وقد كان هذا حاله فعلاً عند أوّل تشغيل (صفر طلب). — يُسقِط `test_no_declared_keys_fails_closed`
- عودةُ قراءة الوسائط الموضعيّة وحدها ⇒ `ctx.require(key="…")` مسارُ تجاوزٍ مفتوح. و`require(self, key: str)` ليست positional-only فالصيغة مشروعة تماماً، ولا يحتاج الالتفافُ نيّةً سيّئة: يكفي أن يكتبها أحدٌ هكذا. أمسكتها المراجعة. — يُسقِط `test_a_keyword_argument_request_is_seen`

### `visual_fixme_baseline_guard.py`

**يفرض:** الاختبار المُعطَّل دَينٌ — والدَّينُ يُحرَس أو يتراكم صامتاً.

**يحجب في:** `capability-governance.yml` → `capability-registry`

**الاختبار الشاهد:** `tests_v9/test_visual_fixme_baseline_guard.py`

**ما يمسكه** — كلّ بند مُثبَت بزرع العطل وتشغيله:

- نزعُ الراتشِت الصاعد ⇒ ثالثٌ يُضاف بمبرّرٍ وجيه في لحظته، وعاشرٌ بعده؛ والمجموع مقبرةُ ديون خضراء يقول تقريرُها «0 failed» صادقاً حرفيّاً — يُسقِط `test_one_more_fixme_is_blocked`
- سقفٌ يبقى بعد إغلاق دَينٍ يبتلع **عودته** صامتاً: يُغلَق واحد ثمّ يُضاف آخر فيبقى العدّاد ثابتاً والحارس أخضر. راتشِتٌ لا يُخفَّض ليس راتشِتاً بل سقفٌ مُرتخٍ — يُسقِط `test_removing_a_fixme_without_lowering_the_baseline_is_blocked`
- عددٌ بلا سببٍ يُنقَل بين الأجيال بلا معنى: «اثنان» لا يقول لماذا ولا متى يُغلَقان، فيرثه من لا يعرف قصّته — يُسقِط `test_a_fixme_without_a_gap_anchor_is_blocked`
- ملفٌّ نُقِل أو حُذِف ⇒ لا `fixme` ⇒ لا مخالفة: الحالة التي تجعل حارساً «أخضرَ إلى الأبد» وهو يحرس لا شيء — يُسقِط `test_a_missing_watched_file_fails_closed`
- عدُّ ذِكرِ الاسم في شرحٍ اختباراً مُعطَّلاً — عطلٌ وقع فعلاً في أوّل صياغة (أربعة بدل اثنين). وعدٌّ يُعاقِب التوثيق يُدرِّب كاتبه على حذفه: رقمٌ خاطئ وتوثيقٌ أقلّ — يُسقِط `test_a_mention_in_prose_is_not_counted_as_a_disabled_test`

---

## حرّاس تحجب ولم تُثبَت بالتكذيب (218)

تعمل، وتُسقِط بناءً حين تُخالَف — لكنّ أحداً لم يقِس أنّها **تفشل حين يوجد**
**العطل**. عند إضافة مواصفة لأيٍّ منها ينتقل صفّها إلى القسم أعلاه تلقائيّاً.

| الحارس | يفرض | يحجب في |
|---|---|---|
| `agronomic_context_gate.py` | AC-1 gate: the agronomic-context contract layer must stay canonical and fail-closed. | `structural-lint` |
| `agronomic_decision_lineage_gate.py` | AC-6 gate: direct agronomic lineage on decisions must stay present and fail-closed. | `structural-lint` · `contract` |
| `agronomic_learning_lineage_gate.py` | AC-9 gate: governed agronomic evidence must keep propagating into learning datasets. | `structural-lint` · `contract` |
| `agronomic_lineage_integrity_gate.py` | AC-6.1 gate: tenant-safe agronomic lineage and semantic evidence consistency. | `structural-lint` · `contract` |
| `agronomic_model_lifecycle_lineage_gate.py` | Cohort lineage gate: evaluation → promotion → activation must carry the cohorts intact. | `structural-lint` · `contract` |
| `agronomic_runtime_lineage_gate.py` | Runtime cohort lineage gate: monitoring/retraining stay bound to authoritative upstream. | `structural-lint` · `contract` |
| `agronomic_runtime_terminal_lineage_gate.py` | Terminal lineage gate: rollback/rollout/dispatch receipts + rollback-aware monitoring. | `structural-lint` · `contract` |
| `ai_agronomist_main_decomposition_guard.py` | Guard the ai-agronomist main.py decomposition boundary. | `guard` |
| `ai_container_contract_guard.py` | Guard AI-oriented containers for liveness/readiness and post-decomposition copy contracts. | `ai-container-contract` |
| `api_versioning_policy_guard.py` | Inventory and freeze unversioned business routes. | `capability-registry` |
| `arch_test_ci_coverage_guard.py` | كلّ اختبار في ``tests/architecture/`` يجب أن يُشغّله workflow — أو يُعفى بسببه. | `capability-registry` |
| `architecture_graph.py` | Build a conservative service architecture graph from repository evidence. | `capability-registry` |
| `assertion_presence_guard.py` | حارس «الخضرة الزائفة»: دالّة اختبار بلا تأكيد **وتُرجِع قيمة** لا يمكن أن تفشل. | `capability-registry` |
| `auth_main_decomposition_guard.py` | Guard the auth-service main.py decomposition boundary. | `guard` |
| `backfill_ui_sync_gate.py` | Static contract gate for historical imagery backfill UI/runtime synchronization. | `structural-lint` |
| `brain_deferral_registry_guard.py` | يمنع تسرّب التأجيلات من `hot.md` دون تسجيلها في `gaps/registry.md`. | `no-report-only-change` |
| `build_service_dependency_bundle.py` | Build a deterministic direct-dependency bundle for audit/review. | `dependency-conflict-inventory` |
| `c10_field_authority_certification.py` | — | `structural-lint` |
| `c11_closed_loop_lineage_certification.py` | — | `structural-lint` |
| `c12_governed_learning_promotion_certification.py` | — | `structural-lint` |
| `c13_physical_shrink_certification.py` | — | `structural-lint` |
| `c8_rag_production_certification.py` | — | `structural-lint` |
| `c9_decision_authority_certification.py` | — | `structural-lint` |
| `calibration_dataset_boundary_gate.py` | — | `structural-lint` |
| `capability_core_consumption_guard.py` | Ratchet the platform capability cores against silently returning to orphaned. | `capability-registry` |
| `capability_evidence_maturity_engine.py` | Generate a fail-closed evidence matrix and evidence-derived maturity baseline. | `capability-registry` |
| `capability_linker.py` | Conservatively link SAHOOL capabilities to repository services, APIs, tests and consumers. | `capability-registry` |
| `capability_management_engine.py` | Generate the unified SAHOOL Capability Management Layer. | `capability-registry` |
| `capability_mapping_engine.py` | Build a deterministic repository-to-capability evidence map for SAHOOL. | `capability-registry` |
| `capability_parity_investment_engine.py` | Generate fail-closed capability parity and investment artifacts. | `capability-registry` |
| `capability_projection_sync.py` | يجعل الإسقاط التوافقيّ صادقاً: الحقول canonical-owned تُكتَب من مالكها وحده. | `capability-registry` |
| `capability_registry_guard.py` | Validate the canonical SAHOOL capability registry and generate governance outputs. | `capability-registry` |
| `capability_registry_v1.py` | — | `capability-registry` |
| `capability_release_history.py` | Generate deterministic capability history from committed static baselines. | `capability-registry` |
| `capability_roadmap_linker.py` | Validate and generate the curated roadmap-to-capability linkage. | `capability-registry` |
| `capability_runtime_evidence.py` | Extract conservative runtime observability evidence for SAHOOL capabilities. | `capability-registry` |
| `capability_shadow_reconciliation.py` | Shadow reconciliation between the canonical registry and the legacy projection. | `capability-registry` |
| `certify_artifact_contract.py` | عقدُ مصنوعة الاعتماد: اسمٌ مشتقٌّ من ``head_sha``، وexactly-one، وهويّةٌ تُسجَّل. | `certify` |
| `compose_env_contract_gate.py` | Fail-closed contract gate for docker-compose ↔ .env compatibility. | `structural-lint` |
| `compose_runtime_target_resolver.py` | Resolve runtime probe targets to internal Docker Compose service URLs. | `capability-registry` |
| `consumer_contract_gate.py` | WS-E — CI consumer-contract gate. | `structural-lint` |
| `container_fleet_contract_guard.py` | Container fleet contract guard. | `guard` |
| `container_image_pin_guard.py` | Reject mutable or unversioned container images in production Compose files. | `attest-source-release` · `supply-chain-static-scan` |
| `contract_capabilities_schema_guard.py` | Guard stable schemas for /contract and /capabilities endpoints. | `contract-capabilities-schema` |
| `crop_intelligence_boundary_gate.py` | Keep Crop Intelligence as an interpretation layer, not a weather calculator. | `structural-lint` |
| `database_contract_graph.py` | — | `capability-registry` |
| `decision_candidate_boundary_gate.py` | WX-10.6 — Keep the Crop→Decision candidate path a reviewable candidate, never execution. | `structural-lint` |
| `decision_lineage_graph.py` | Generate a deterministic static decision-lineage knowledge graph. | `capability-registry` |
| `decision_lineage_v183_guard.py` | Static ratchet for v183 DB-owned immutable content lineage (renumbered from P0-fix v182). | `structural-lint` |
| `decision_review_boundary_gate.py` | WX-10.7 — Keep the reviewer/decision path a state transition, never execution. | `structural-lint` |
| `decision_review_ownership_consistency_gate.py` | WX-10.7 — ownership/config consistency for the decision review transition. | `structural-lint` |
| `decision_sor_cutover_readiness_gate.py` | Static cutover-readiness gate for decision-service SoR promotion. | `field-workspace-closure` |
| `decision_sor_final_certification_gate.py` | Static gate for P0-5/P0-6 Decision SoR final certification controls. | `field-workspace-closure` |
| `decision_sor_review_cutover_gate.py` | WX-10.7 — SoR-promotion cutover-prep gate (DEPLOYED-DECISION-SOR-PROMOTION). | `structural-lint` |
| `decision_sor_shadow_promotion_gate.py` | Static gate for P0-3 decision-service shadow/promotion controls. | `field-workspace-closure` |
| `decision_sor_staging_probe_gate.py` | Static gate for P0-4 decision-service staging probe harness. | `field-workspace-closure` |
| `design_token_contrast_gate.py` | بوّابة تباين توكِنات التصميم (WCAG 2.1) — مُكيَّفة لساهول (مُلهَمة من قواعد impeccable). | `structural-lint` |
| `dispatch_authorization_boundary_gate.py` | WX-10.10 guard: authorization must not become dispatch or execution. | `structural-lint` |
| `docker_build_matrix_verifier.py` | Docker build matrix verifier for Sahool services. | `docker-build` |
| `duplicate_definition_guard.py` | Detect duplicate Python definitions in the same lexical scope. | `capability-registry` |
| `edge_inference_service_contract_gate.py` | CI guard for edge-inference service runtime/config contracts. | `field-workspace-closure` |
| `edge_model_contract_guard.py` | Guard the edge-inference model contract. | `edge-model-contract` · `model-provisioning-evidence` |
| `edge_production_readiness_guard.py` | Guard Edge production-readiness policy. | `edge-production-readiness` · `model-provisioning-evidence` |
| `endpoint_ui_coverage_gate.py` | SAHOOL endpoint-ui-coverage-gate. | `structural-lint` |
| `env_compose_drift_guard.py` | حارس انجراف env↔compose (السجل التشغيليّ #3) — صنف عضّ مرتين، فأُغلِق بحارس. | `structural-lint` |
| `event_contract_graph.py` | Generate a conservative static NATS/JetStream event contract graph. | `capability-registry` |
| `execution_delivery_receipt_boundary_gate.py` | — | `structural-lint` |
| `execution_dependency_audit.py` | Generate a conservative static execution/dead-code audit. | `capability-registry` |
| `execution_outcome_boundary_gate.py` | WX-10.12 guard: outcome verification must not perform learning updates. | `structural-lint` |
| `execution_request_boundary_gate.py` | — | `structural-lint` |
| `expected_control_flow_guard.py` | يفرض عقد الاستثناءات المتوقَّعة — EXPECTED-CONTROL-FLOW-EXCEPTION. | `structural-lint` |
| `fastapi_lifespan_guard.py` | Prevent reintroduction of deprecated FastAPI ``on_event`` hooks. | `structural-lint` |
| `field_workspace_production_closure_gate.py` | Field Workspace production closure gate. | `field-workspace-closure` |
| `fii_rls_write_policy_gate.py` | FII Safety Increment 1C: reject unsafe tenant-write RLS patterns. | `security-scan` |
| `functional_probe_runner.py` | Strict functional probe runner. Produces signed, runtime-bound evidence only. | `capability-registry` |
| `gateway_reachability_guard.py` | Build a deterministic Nginx/API-gateway reachability and security inventory. | `capability-registry` |
| `generate_indicator_artifacts.py` | — | `structural-lint` |
| `generate_indicators_frontend_manifest.py` | مولّد مانيفست الواجهة (build-time) لسجلّ المؤشّرات — WS-B.2 (manifest-only). | `structural-lint` |
| `generate_service_inventory.py` | Generate Sahool service and route inventory from source code. | `structural-lint` · `drift` |
| `github_actions_policy_guard.py` | Enforce immutable third-party Actions and reject privileged workflow patterns. | `supply-chain-static-scan` |
| `guard_catalogue.py` | What every guard enforces, what it catches, and where it runs — derived, never listed. | `structural-lint` |
| `health_readiness_schema_guard.py` | Guard canonical health/readiness response envelopes. | `health-readiness-schema` |
| `indicators_container_contract_guard.py` | Guard the indicators-service canonical-observation-adapter container boundary. | `indicators-container-contract` |
| `indicators_registry_gate.py` | Guard: config/indicators_registry.json is the single source of truth for indicators. | `structural-lint` |
| `integration_runtime_governance_closure.py` | Artifact-based closure gate for PATH-2 integration/runtime-evidence governance. | `capability-registry` |
| `intelligence_governance_gate.py` | — | `structural-lint` |
| `irrigation_as_applied_m2_11_guard.py` | Static ratchet for M2.11 canonical as-applied irrigation truth. | `structural-lint` |
| `irrigation_capability_graph_m2_8_guard.py` | Repository ratchet for M2.8 unified irrigation capability graph. | `structural-lint` |
| `irrigation_closed_loop_m5_guard.py` | Static ratchet for M5 irrigation closed-loop learning and certification. | `structural-lint` |
| `irrigation_closed_loop_runtime_guard.py` | Ratchet for durable measured irrigation reconciliation. | `structural-lint` |
| `irrigation_commissioning_m2_10_guard.py` | Static ratchet for M2.10 irrigation commissioning certification. | `structural-lint` |
| `irrigation_controller_edge_m2_9_guard.py` | Static ratchet for M2.9 controller/edge framework. | `structural-lint` |
| `irrigation_convergence_guard.py` | Fail CI when IRR work introduces a parallel irrigation system of record. | `contract` |
| `irrigation_energy_m2_7_guard.py` | Repository ratchet for M2.7 energy/microgrid capability. | `structural-lint` |
| `irrigation_engineering_m2_1_guard.py` | Static ratchet for the M2.1 irrigation engineering foundation. | `structural-lint` |
| `irrigation_hourly_mpc_m3_guard.py` | Static ratchet for M3 hourly energy-aware irrigation MPC. | `structural-lint` |
| `irrigation_hydraulic_m2_4_guard.py` | Repository ratchet for M2.4 hydraulic capability. | `structural-lint` |
| `irrigation_machine_m2_5_guard.py` | M2.5 end-state guard: persisted machine capability remains; dead platform compute does not. | `structural-lint` |
| `irrigation_rls_canonical_guard.py` | Guard: the V21 irrigation migrations (v168–v181) must use canonical, fail-closed RLS. | `structural-lint` |
| `irrigation_root_zone_m2_2_guard.py` | Static ratchet for M2.2 canonical root-zone hydraulics. | `structural-lint` |
| `irrigation_runtime_orchestrator_guard.py` | Ratchet for the server-owned irrigation runtime orchestrator. | `structural-lint` |
| `irrigation_sprinkler_m2_6_guard.py` | Repository ratchet for M2.6 sprinkler/runoff capability. | `structural-lint` |
| `irrigation_vri_m4_guard.py` | Static ratchet for M4 governed VRI prescriptions. | `structural-lint` |
| `irrigation_well_digital_twin_m2_3_guard.py` | Static ratchet for M2.3 water-source and well digital twin. | `structural-lint` |
| `irrx1_6_manual_volume_guard.py` | — | `structural-lint` |
| `irrx1_7_interactive_calculator_guard.py` | — | `structural-lint` |
| `irrx1_8_reservoir_booster_guard.py` | — | `structural-lint` |
| `irrx1_9_multi_system_calculator_guard.py` | — | `structural-lint` |
| `irrx1_authoritative_provenance_guard.py` | Static ratchet for IRR-X1.5 authoritative manual-execution provenance. | `structural-lint` |
| `irrx1_commissioning_runtime_guard.py` | — | `structural-lint` |
| `irrx1_farmer_manual_operations_ui_guard.py` | IRR-X1.4 guard: farmer manual operations UI and read path remain wired. | `structural-lint` |
| `irrx1_manual_execution_guard.py` | — | `structural-lint` |
| `irrx1_pcert_guard.py` | Static ratchet for IRR-PCERT wiring and DB-authoritative invariants. | `structural-lint` |
| `irrx1_vendor_neutral_guard.py` | — | `structural-lint` |
| `irrx1_verified_manual_ledger_guard.py` | — | `structural-lint` |
| `jwt_secret_configuration_guard.py` | Fail closed on tracked/release-bundled secrets and unsafe JWT configuration. | `structural-lint` |
| `ky_no_economic_coupling_guard.py` | حارس CI: يمنع اشتقاق أيّ إيراد/هامش اقتصاديّ من معامل Ky قبل نموذج اقتصاديّ صريح. | `structural-lint` |
| `learning_attribution_boundary_gate.py` | WX-10.13 ratchet: outcome attribution must not mutate models or restart execution. | `structural-lint` |
| `migration_graph_guard.py` | — | `capability-registry` |
| `minio_s3_contract_gate.py` | Fail closed on MinIO/S3 credential drift in docker-compose/.env templates. | `structural-lint` |
| `model_activation_approval_boundary_gate.py` | — | `structural-lint` |
| `model_activation_request_boundary_gate.py` | — | `structural-lint` |
| `model_evaluation_boundary_gate.py` | — | `structural-lint` |
| `model_promotion_decision_boundary_gate.py` | — | `structural-lint` |
| `model_registry_activation_boundary_gate.py` | — | `structural-lint` |
| `mpc_lineage_propagation_guard.py` | حارس CI: يضمن أنّ جسر MPC ينشر النَّسَب الكامل ويبقى توصية-فقط (لا تنفيذ تلقائيّ). | `structural-lint` |
| `nginx_compose_dns_gate.py` | Validate that nginx upstream hostnames are resolvable in the selected compose file. | `structural-lint` |
| `nginx_weather_edge_path_guard.py` | Static smoke guard for Nginx weather/edge exposure paths. | `nginx-weather-edge-paths` |
| `no_leakage_certification_gate.py` | Phase C gate: the no-leakage certification surface must stay intact. | `structural-lint` |
| `no_merge_conflict_markers_guard.py` | حارس CI: يمنع تسرّب علامات تعارض دمج git إلى أيّ ملفّ مُتتبَّع. | `structural-lint` |
| `p1_main_decomposition_guard.py` | Guard P1 main.py decomposition for platform, odoo-bridge, and vegetation. | `p1-main-decomposition` |
| `p2_main_decomposition_guard.py` | Guard P2 main.py decomposition for actuator, SAM2, and weather services. | `p2-main-decomposition` |
| `path3_runtime_activation.py` | Activate a compose stack and collect fail-closed runtime evidence for PATH-3. | `runtime-producer` |
| `path3_runtime_readiness_closure.py` | Close PATH-3 static runtime readiness without claiming live verification. | `capability-registry` |
| `physical_effect_boundary_guard.py` | P0-7 — الأثر الفيزيائيّ لا يُطلَق من الدماغ، ولا يُطلَق إلّا من موضع مُسمّى. | `structural-lint` |
| `pip_audit_resolution_guard.py` | Guard against pip-audit dry-run resolver conflicts on shared packages. | `guard` |
| `pip_mirror_contract_guard.py` | Guard the connected-CI pip index / mirror contract. | `pip-mirror-contract` |
| `platform_main_subinventory_guard.py` | Sub-inventory for services/sahool-platform/api/main.py. | `structural-lint` · `guard` |
| `platform_route_budget_guard.py` | Fail-closed SAHOOL platform domain-route budget guard. | `platform-route-budget` |
| `platform_route_governance_attestation.py` | Cross-attest platform route classification, budget, ownership, and map state. | `platform-route-budget` |
| `platform_route_ownership_guard.py` | Verify and materialize the complete sahool-platform route ownership surface. | `platform-route-budget` |
| `platform_route_placement_guard.py` | Enforce machine-readable source placement for governed platform routes. | `platform-route-budget` |
| `pr_capability_impact_gate.py` | Compute and enforce pull-request capability impact declarations. | `capability-registry` |
| `prepare_attested_runtime_images.py` | Validate an externally built image manifest and generate a pull-by-digest Compose override. | `runtime-producer` · `trusted-signer` |
| `production_certification_blockers_status.py` | Print the current status of the four production certification blockers. | `certification-verdict` · `full-branch-ci-evidence` |
| `production_certification_checklist_guard.py` | Production certification checklist inventory/guard. | `guard` |
| `production_evidence_pack_guard.py` | Production evidence pack guard. | `transitive-locks-evidence` · `evidence-pack` |
| `production_honesty_guard.py` | Production honesty guard. | `honesty` |
| `production_truth_readiness_gate.py` | Production truth/readiness gate: no synthetic serving paths; honest readiness. | `structural-lint` · `contract` |
| `provenance_receipt.py` | Create/validate the external provenance receipt required by the read-only bridge. | `verify-and-evaluate` |
| `raster_import_graph_gate.py` | Static import-graph gate for services/raster-service. | `structural-lint` |
| `raster_main_decomposition_gate.py` | Raster-service main.py decomposition contract gate. | `structural-lint` |
| `raster_pixel_qa_indicator_guard.py` | Guard: raster indicators must carry raw pixel QA/provenance. | `guard` |
| `raster_production_truth_guard.py` | Fail closed if synthetic indicator data can reach production serving paths. | `structural-lint` |
| `raster_topographic_qa_guard.py` | Guard: raster indicator QA must carry honest topographic QA provenance. | `raster-topographic-qa` |
| `raster_validated_product_guard.py` | Guard: raster indicators must expose ValidatedRasterProduct + cloud strategies. | `raster-validated-product` |
| `raw_data_processing_contract_guard.py` | Guard the raw raster data processing contract. | `raw-data-processing-contract` |
| `raw_weather_processing_contract_guard.py` | Guard the weather raw-data processing contract. | `raw-weather-processing-contract` |
| `release_attestation_guard.py` | Fail closed when the release artifact attestation workflow is weakened. | `attest-source-release` |
| `report_index_guard.py` | Generate/check REPORT_INDEX.md for release artifacts and historical reports. | `report-index` |
| `riv_boundary_gate.py` | — | `structural-lint` |
| `rls_policy_guard.py` | — | `capability-registry` |
| `route_conflict_guard.py` | Static FastAPI/Starlette route collision guard. | `capability-registry` |
| `route_mount_contract_guard.py` | Guard route-bearing FastAPI services after main.py decomposition. | `structural-lint` |
| `route_residual_classification_guard.py` | Classify route decorators that remain directly in main.py files. | `classify-main-route-residuals` |
| `router_reachability_guard.py` | Conservative static FastAPI router reachability inventory and drift guard. | `capability-registry` |
| `runtime_certification_gate.py` | Fail closed when runtime or production certification exceeds accepted evidence. | `capability-registry` |
| `runtime_container_deep_contract_guard.py` | Runtime container deep contract guard for non-AI high-risk services. | `guard` |
| `runtime_contract_gate.py` | Runtime-chain static contract gate. | `structural-lint` |
| `runtime_contract_generator.py` | Generate deterministic repository-derived runtime contracts for SAHOOL services. | `capability-registry` |
| `runtime_environment_preflight.py` | Assess whether this checkout can execute SAHOOL PATH-3 live runtime probes. | `capability-registry` |
| `runtime_evidence_ingestion.py` | Validate and normalize runtime evidence into a tamper-evident service ledger. | `capability-registry` |
| `runtime_identity_bridge.py` | Read-only runtime identity bridge with strict, attested, atomic evidence evaluation. | `capability-registry` · `verify-and-evaluate` |
| `runtime_readiness_contract_gate.py` | Static runtime-readiness contract gate. | `structural-lint` |
| `runtime_replay_guard.py` | Fail closed when an attested evidence bundle was already consumed. | `verify-and-evaluate` |
| `runtime_verification_apply.py` | Governed Step-4 runtime-verification promotion. | `verify-and-evaluate` · `apply-as-pull-request` |
| `runtime_verification_harness.py` | Generate and validate a fail-closed runtime verification plan. | `capability-registry` |
| `scene_provenance_ui_guard.py` | Static ratchet: scene provenance must remain visible and fail-honest in both imagery UIs. | `provenance-contract` |
| `service_dependency_conflict_guard.py` | Generate an auditable cross-service dependency conflict report. | `dependency-conflict-inventory` |
| `service_feature_ui_contract_gate.py` | SAHOOL service-feature-ui-contract-gate. | `structural-lint` |
| `service_port_gate.py` | Static service port contract checks for drift-prone services. | `structural-lint` |
| `soil_canonical_store_guard.py` | — | `structural-lint` |
| `soil_full_chain_guard.py` | — | `structural-lint` |
| `soil_lab_projection_guard.py` | Fail closed if durable lab workflow or canonical projection wiring regresses. | `structural-lint` |
| `soil_lab_supersession_lineage_guard.py` | — | `structural-lint` |
| `soil_p1_products_guard.py` | — | `structural-lint` |
| `soil_p2_products_guard.py` | — | `structural-lint` |
| `soil_p3_products_guard.py` | — | `structural-lint` |
| `soil_p4_closed_loop_guard.py` | — | `structural-lint` |
| `soil_p5_certification_guard.py` | — | `structural-lint` |
| `soil_p6_runtime_certification_guard.py` | — | `structural-lint` |
| `soil_profile_contract_guard.py` | Fail CI when governed consumers bypass the canonical soil profile contract. | `structural-lint` |
| `soil_projection_observability_guard.py` | — | `structural-lint` |
| `soil_projection_reconciliation_guard.py` | — | `structural-lint` |
| `soil_runtime_certification_guard.py` | Static ratchet ensuring real-Postgres soil certification remains wired. | `structural-lint` |
| `soil_supersession_current_pointer_guard.py` | — | `structural-lint` |
| `sot_evidence_manifest.py` | — | `live-pg-fake-connection-proofs` |
| `static_governance_closure.py` | Artifact-based closure gate for Path 1 static governance. | `capability-registry` · `apply-as-pull-request` |
| `tests_tree_coverage_guard.py` | شجرة ``tests/`` تُشغَّل كاملةً ناقص أساس مُبرَّر — لا بقائمة سماح مكتوبة يدويّاً. | `repository-tests` |
| `unified_production_readiness_gate.py` | Run canonical static production gates and emit one machine-readable verdict. | `unified-readiness-evidence` |
| `v9_feature_transfer_gate.py` | Guard that v9 keeps the runtime features promoted from unified/light. | `structural-lint` |
| `v9_gpu_contract_gate.py` | Static contract gate for SAHOOL v9 RTX 5090/GPU enablement. | `structural-lint` |
| `validate_ci_gates.py` | Validate CI/CD quality-gate coverage for the Sahool release. | `supply-chain-static-scan` |
| `vegetation_agriai_completion_gate.py` | Structural guard for the Vegetation → AgriAI production contract. | `structural-lint` |
| `vegetation_agriai_full_closure_gate.py` | Full-plan closure gate for the Vegetation + AgriAI increment. | `structural-lint` |
| `vegetation_agriai_production_gate.py` | — | `structural-lint` · `contract` |
| `vegetation_container_contract_guard.py` | Guard vegetation-analysis-service container/runtime contract. | `guard` |
| `vegetation_runtime_truth_guard.py` | Fail closed when vegetation runtime regains synthetic field/provider ownership. | `structural-lint` |
| `verify_all_generated.py` | يشغّل **كلّ** خطوات ``--check`` المولَّدة بأمر واحد — وبالترتيب الذي تتطلّبه التبعيّات. | `capability-registry` |
| `waiver_expiry_guard.py` | WAIVER-EXPIRY-GUARD — fail CI once a governance waiver has expired. | `structural-lint` |
| `weather_engine_formula_guard.py` | Guard: vapour-pressure / ET0 formulas live only in the Weather Engine (WS-C.1b boundary). | `structural-lint` |
| `weather_hourly_etc_wx_i1_guard.py` | — | `structural-lint` |
| `weather_service_real_contract_gate.py` | Weather-service real-runtime contract gate. | `field-workspace-closure` |
| `wx11_closed_loop_completion_gate.py` | — | `structural-lint` |
| `wx12_runtime_certification_gate.py` | — | `structural-lint` · `structural` |
| `wx12_runtime_completion_gate.py` | — | `structural-lint` |
| `wx12_runtime_multitenancy_gate.py` | WX-12 multitenancy gate: worker→tenant partitioning must stay server-authorized. | `structural-lint` |
| `wx12_runtime_scheduler_gate.py` | WX-12.3 scheduler gate: monitoring/reconcile scheduling must be durable and actually wired. | `structural-lint` |

---

## مُواصَفة بطفرات ولا يستدعيها أيّ workflow (3)

أداة غير موصولة لا تحرس شيئاً (§٣.٢). وجودها هنا سؤالٌ لا اتّهام.

- `actuation_killswitch_coverage_guard.py`
- `manifest_registry_guard.py`
- `s5_exec_01_writer_cutover_guard.py`

---

**حدّ الصدق:** هذا يجرد ما تستدعيه الـworkflows بنمط `python scripts/ci/<x>.py`.
حارسٌ يُستدعى عبر `pytest` أو سكربت وسيط أو `bash` **لا يظهر هنا**، ولا يُدّعى غير
ذلك — وعدد البوّابات في §١ أكبر لهذا السبب. ولا يقيس هذا الجرد **جودة** الحارس ولا
تغطيته، بل وجوده وموضعه وهل أُثبِت بالتكذيب.

