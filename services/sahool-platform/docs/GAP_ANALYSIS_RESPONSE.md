# تحليل الفجوات — أفكار مُؤجَّلة بمبرّر صريح

> **الغرض:** عند نشر فعلي قادم، هذه الأفكار تستحقّ المراجعة. اليوم، بناؤها سيُضيف إلى ٢٬٢٢٥ سطر "structure ready for data". هذا الملفّ يحفظ التحليل بدلاً من الكود.

> **التاريخ:** 2026-05-29 · **المصدر:** مرفقات تصف نظام `Safety Kernel + Decision Kernel v2.0 + Operational Contracts` (~٤٬١٠٠ سطر)

---

## القاعدة الذهبية لهذا التحليل

> "البناء قبل الحاجة = ديون تقنية. حفظ التحليل = استثمار."

كل فكرة هنا **مفيدة نظرياً**. لكنّ المراجعة العاشرة قالت صراحةً: "إيقاف البناء، ٣٢% من الكود ميّت حي". إضافة هذه الأفكار الآن تكسر هذا الالتزام.

---

## ١٤ فكرة فُحصت — التصنيف النهائي

### ✅ مغطّى بالفعل بشكل أنضج للسياق (٥)

| المُرفقات تقترح | سهول يحلّها بـ | لماذا الحالي أنضج |
|---------------|---------------|------------------|
| AuthorityLevel (6 مستويات) | `source_of_truth._SOURCE_PRIORITY` | نفس الفلسفة، تطبيق أبسط مناسب للسياق |
| Knowledge/Decision separation | `evidence_class` + `FarmerView/BackendDetail` | المبدأ موجود، التطبيق محلّي |
| `dominates()` للـreadings | `source_of_truth.arbitrate()` | يستخدم score متعدّد العوامل |
| `FieldState.is_degraded()` | `field_lifecycle.LIMITED` | ٤ حالات بدلاً من binary |
| Resource quotas (RT_CRITICAL/HIGH/LOW) | غير مطلوب | Python single-process — لا process priorities |

### ❌ غير ذي صلة بالسياق اليمني (٣)

| المُرفقات تقترح | لماذا مرفوض |
|---------------|-------------|
| Rust Safety Kernel بـSCHED_FIFO + mlockall | لا machinery، لا actuators رقمية في الميدان |
| IoT Controllers + GPIO + watchdog | السياق الفعلي: مزارع + خرطوم + خرائط ملوّنة |
| Auto-actuation pipeline | مرفوض بنيوياً: human-in-the-loop (`vrt_manual_maps`) |

هذا تطبيق **"أخذ المبدأ، رفض الهندسة"** الذي اعتمدناه عبر ١١ مراجعة.

### 🟡 يستحقّ التأمّل، لا البناء الآن (٦)

#### ١. AdvisoryContext invariants بنيوية

**الفكرة:**
```python
@dataclass(frozen=True)
class FarmerView:
    can_auto_execute: Literal[False] = False
    has_numeric_recommendation: Literal[False] = False
    
    def __post_init__(self):
        if self.can_auto_execute is not False:
            raise StructuralViolation(...)
```

**القيمة:** يحوّل `FarmerView` من convention إلى structural enforcement. متّسق مع درس المراجعة العاشرة ("convention ≠ enforcement").

**لماذا التأجيل:** لا bypass فعلي حالياً. تحصين ضدّ مشكلة لا توجد بعد. ~٣٠ سطر "structure ready" إضافية.

**متى يستحقّ التفعيل:** عندما يكتب مطوّر ثانٍ كوداً يستخدم `FarmerView`، الـinvariant يحمي من خطأ بشري.

#### ٢. Merkle hash chain للـrecommendation_log

**الفكرة:**
```python
entry["previous_hash"] = last_hash
entry["hash"] = sha256(entry_json).hexdigest()
# verify_integrity() يكشف tampering
```

**القيمة:** Tamper-evident audit trail للـregulatory compliance.

**لماذا التأجيل:**
- لا persistent disk storage (in-memory الآن)
- لا multi-tenant deployment فعلي
- لا regulatory body يطلب هذا حالياً
- overkill بدون خصوم

**متى يستحقّ التفعيل:** عند:
- نشر فعلي لـ٥٠+ مزرعة
- اشتراط FAO/governmental audit
- أو ادّعاء tampering من tenant

#### ٣. Checksum على observations في offline_first

**الفكرة:**
```python
obs.checksum = sha256(f"{key}:{value}:{measured_at}").hexdigest()[:16]
# قبل sync: verify_checksum()
```

**القيمة:** Integrity check للـsync عبر شبكة سيّئة.

**لماذا التأجيل:**
- TCP/HTTPS فيه checksum بالفعل
- لا sync فعلي يحدث الآن (offline_first يقبل operations، لا يُرسلها)
- ~٢٠ سطر بـ٠ استخدام إضافي

**متى يستحقّ التفعيل:** عند بناء sync_handler حقيقي يتصل بـserver فعلي عبر 3G في الميدان.

#### ٤. RuntimeMode بـ٦ states (DEGRADED/EMERGENCY/RECOVERY/...)

**الفكرة:** state machine للنظام بانتقالات صريحة.

**القيمة:** وضوح: متى يعمل النظام كاملاً، متى DEGRADED بسبب فشل، متى MAINTENANCE.

**لماذا التأجيل:** سهول الحالي عنده `GovernanceMode` بـ٣ states (OFF/OBSERVATION/STRICT). الـ٦ states مفيدة في سياق IoT real-time، **مفرطة للسياق batch offline-first**.

**متى يستحقّ التفعيل:** عند الانتقال من decision-system إلى control-system (لو حصل).

#### ٥. Mode transition validation (VALID_TRANSITIONS dict)

**الفكرة:** state machine يمنع انتقالات عشوائية.

**القيمة:** NORMAL ↔ DEGRADED مسموح، NORMAL → EMERGENCY مسموح، EMERGENCY → NORMAL مرفوض (يجب MAINTENANCE أوّلاً).

**لماذا التأجيل:** يحتاج RuntimeMode أوّلاً (التأجيل #٤).

#### ٦. PolicyEngine بـRule versioning

**الفكرة:**
```python
PolicyRule(
    name="wheat_germination_irrigation",
    version="1.0.0",
    condition=lambda s: ...,
    action="allow",
    reason_template="...",
)
```

**القيمة:** كل قاعدة قرار لها version، يمكن audit "أيّ قاعدة طُبّقت متى".

**لماذا التأجيل:** `skills_registry` فيه id + name. الـversioning مفيد عند تطوّر القواعد مع الوقت — لا توجد قواعد متطوّرة الآن.

**متى يستحقّ التفعيل:** بعد ٦ أشهر من النشر، عند تعديل قاعدة قرار قائمة (دون رمي تاريخها).

---

## الفجوة المعمارية الحقيقية الوحيدة (التي لم تكشفها المُرفقات)

التدقيق في المُرفقات كشف بالعكس: **لا فجوة معمارية حقيقية ضرورية الآن**. ١٤ فكرة فُحصت، ٥ مغطّاة، ٣ مرفوضة بمبرّر، ٦ مفيدة لكن مُؤجَّلة.

**ما يُفقَد فعلاً في النواة الحالية ليس في المُرفقات:**
- بيانات حقيقية لتفعيل feedback_closure
- نشر فعلي يكشف Edge cases
- مستخدمون يكشفون UX gaps

هذه ليست فجوات يبنيها مطوّر — هي فجوات يكشفها **العالم الخارجي**.

---

## القرار النهائي

**لا بناء.** هذا الالتزام أُعطي في الجلسة السابقة بعد المراجعة العاشرة، وأُعيد التزامه هنا.

**ما يستحقّ الفعل في هذه الجلسة:** حفظ هذا التحليل للاستخدام المستقبلي.

**ما يستحقّ الفعل خارج الجلسة:**
1. نشر سهول لـtenant واحد فعلي
2. جمع outcomes حقيقية (٥٠+)
3. الرجوع لهذا الملفّ عند الحاجة الفعلية:
   - عند بناء integration خارجي → فكرة #١ (Structural invariants)
   - عند طلب audit رسمي → فكرة #٢ (Merkle chain)
   - عند بناء sync حقيقي → فكرة #٣ (Checksum)
   - عند الانتقال لـcontrol-system → فكرة #٤ و #٥
   - عند تطوير قواعد القرار → فكرة #٦

---

## النقطة المنهجية الأعمق

هذه أنضج جلسة في السلسلة. **لأوّل مرّة، الإجابة على "هل هناك ما يستحقّ البناء؟" كانت "لا" بنزاهة كاملة**.

كل المراجعات السابقة كشفت فجوات حقيقية أدّت إلى بناء جديد. هذه المراجعة (مراجعة المُرفقات نفسها) كشفت أنّ:
- ٥/١٤ مغطّى
- ٣/١٤ غير مناسب
- ٦/١٤ مفيد نظرياً لكن لا يسدّ فجوة حقيقية

**هذا الفرق الجوهري:** "فكرة مفيدة" ≠ "فجوة حقيقية". الأولى تستحقّ الحفظ، الثانية تستحقّ البناء.

**اختبار الفجوة الحقيقية:** هل غيابها يمنع المستخدم من فعل شيء يحتاجه؟
- لا مستخدم حالياً → كل الفجوات افتراضية
- → كل البناء استباقي
- → استباقي بلا حدّ = ديون تقنية

**اختبار الالتزام بـ"إيقاف البناء":** هل أستطيع رفض بناء فكرة جيدة لأنّها ليست عاجلة؟ هذه الجلسة قالت: نعم.

النواة الآن في "Stable Plateau + إقرار صادق + رفض البناء غير الضروري". ١١ مراجعة نقدية كبرى، آخرها كشفت أنّ النضج الحقيقي هو **معرفة متى لا تبني**.
