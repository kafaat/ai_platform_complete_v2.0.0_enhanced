"""Brain rows for the owner's local-audit fixes (§3.6 · §3.10 · §3.1) + the report itself.
SHAs resolved from commit subjects in the current tree (post-rebase). argv: root"""
import pathlib
import subprocess
import sys

root = pathlib.Path(sys.argv[1])


def sha(prefix):
    out = subprocess.check_output(["git", "-C", str(root), "log", "--format=%h %s", "-n", "40"], text=True)
    hits = [l.split()[0] for l in out.splitlines() if l.split(" ", 1)[1].startswith(prefix)]
    assert len(hits) == 1, (prefix, hits)
    return hits[0]


S = {
    "farm": sha("المنصّة: حقولُ المزرعة تفحص الملكيّة"),
    "geom": sha("المنصّة: سجلُّ هندسة الحقل"),
    "ai": sha("المستشار: النموذجُ الذي أُخمِد خرجُه"),
    "rcpt": sha("المستشار: إيصالُ حفظ النصيحة"),
}

ROWS = f"""| FARM-FIELDS-LIST-TRUSTS-RLS-ALONE-01 | **`GET /api/v1/farms/{{farm_id}}/fields` بلا فحص ملكيّة ولا `tenant_id` في الاستعلام** — العزلُ كلُّه على RLS: مزرعةُ مستأجِرٍ آخر (أو غيرُ موجودة) تُعيد `200 []` فلا يتميّز «ليست لك» عن «بلا حقول»، ودورٌ يتجاوز RLS كان سيُعيد حقولَها؛ وعطلُ القاعدة 500. من تدقيق المالك المحلّيّ (§3.6)، مُتحقَّقٌ على main: الملفُّ لم يتغيّر منذ `db8a570d`. | platform/farms | `services/sahool-platform/api/routers/farms.py:139` · `services/sahool-platform/api/routers/farm_operations_ledger.py:92` · `services/sahool-platform/tests/test_farm_fields_tenant_ownership.py` | **fixed** (`{S['farm']}`، 2026-09-30): فحصُ ملكيّةٍ صريح بـ`tenant_id` قبل قراءة الحقول ⇒ 404 `farm_not_found_for_tenant` والحقولُ لا تُقرأ؛ استعلامُ الحقول يحمل `tenant_id`؛ عطلُ القاعدة 503. التكذيب: عكسُ farms.py ⇒ 4/4 أحمر. **لا يبلغ الإنتاج** حتّى تُنقَل المنصّةُ إلى main (تُنشَر من `deploy/*`). |
| GEOMETRY-HISTORY-RETURNS-JSONB-AS-STRING-01 | **`/geometry/history` يُعيد الهندسةَ نصَّ JSON لا كائناً** — `field_geometry_history.geometry`/`metadata` من نوع JSONB ولا codec لـjsonb في المنصّة، فيُعيدهما asyncpg نصّاً؛ مسارُ الاستعادة في الملفّ نفسه يفكّه والسجلُّ لا. الأثر: الواجهةُ (`toTurfFeature`) تُسقِط كلَّ مراجعة فيبدو الخطُّ الزمنيّ فارغاً، و`live_full_e2e.py` يسقط بـ`AttributeError`. التدقيقُ المحلّيّ (§3.10) رأى عطلَ الحزمة؛ السببُ الجذريّ في الـAPI. | platform/fields | `migrations/v96_spatial_geometry_integrity.sql:10` · `services/sahool-platform/api/routers/fields.py:1524` · `frontend/src/lib/fieldGeometryOps.ts:46` · `scripts/e2e/live_full_e2e.py:192` | **fixed** (`{S['geom']}`، 2026-09-30): `_stored_jsonb` يفكّ العمودين، والمُخزَّنُ التالف ⇒ `null` للمراجعة وحدها لا 500؛ الحزمةُ **لا** تفكّ النصّ كي لا تُخفيه — تفشل `timeline.geometry_is_geojson_object` باسمها. التكذيب: عكسُ fields.py ⇒ 2/2 أحمر. **خارج النطاق ومفتوح:** مواضعُ JSONB أخرى في المنصّة تفكّ كلٌّ بطريقته (`fields.py` فيه ٨ مواضع `json.loads`) — codec واحد على المجمَّع قرارٌ أوسع. لا يبلغ الإنتاج (المنصّة على `deploy/*`). |
| AI-GENERATION-ATTRIBUTED-TO-SUPPRESSED-OUTPUT-01 | **الجوابُ الظاهر يُنسَب إلى نموذجٍ أُخمِد خرجُه** — `generation_model`/`generation_provider` يُضبطان من نتيجة التوليد حتّى حين يُخمَد الخرج (`suppressed_*`) ويظهر جوابُ الأدلّة، والواجهةُ ترسم «المزوّد · النموذج» على كلّ جوابٍ يحملهما. من تدقيق المالك المحلّيّ (§3.1). | ai-agronomist | `services/ai_agronomist/ai_evidence_runtime.py:953` · `frontend/src/sections/ChatbotPage.tsx:217` · `tests_v9/test_v25_advisory_publication.py` | **fixed** (`{S['ai']}`، 2026-09-30): `generation_attempted_model/provider` (قياسُ المحاولة، دائماً) منفصلان عن `generation_model/provider` (النسبة، حين `generation_surfaced` فقط)؛ فيُضيف `advisory_contract` قيدَ `generation_disabled_evidence_only` حين لا يُعرَض خرجُ النموذج. التكذيب: عكسُ الملفّ ⇒ 7/7 حالات النشر أحمر. **وأُدرِج معه بقرار المالك الصنفُ نفسُه** (`{S['rcpt']}`): ردٌّ بلا `persisted` كان يُقرأ «recorded» (`ai_evidence_runtime.py:282`) ومفتاحُ `status` في الردّ يَغلِب الحكم ⇒ الآن `unconfirmed` والحكمُ بعد الحمولة؛ التكذيب ⇒ 4/6 أحمر. يبلغ staging وحدها (ai-agronomist). |
| LOCAL-AUDIT-REPORT-PINNED-TO-SHAS-NOT-IN-REPOSITORY-01 | **تقريرُ التدقيق المحلّيّ للمالك (جولتان، 2026-09-30) مُثبَّتٌ على SHA لا يوجد في المستودع** (`3be88ec4` · `0f6c5809`)، ومجلّداه (`audit-reports/` · `docs/audits/2026-09-30/`) غائبان — فإطارُه (ما الشجرةُ التي قاسها) غيرُ قابلٍ للتحقّق، وهو نفسه مثالٌ على الصنف الذي يفحصه (نسخةٌ محلّيّةٌ منجرفة تُقاس كأنّها المستودع). **حُكِم عليه بمراجعه لا بـSHA:** ما يحمل `file:line` حُلَّ على main. | brain/process | `services/sahool-platform/api/routers/farms.py:139` · `scripts/e2e/live_full_e2e.py:100` · `services/ai_agronomist/ai_evidence_runtime.py:953` · `services/odoo-bridge/routers/health.py:8` · `services/video-processor/main.py:186` | **open — للقياس والقرار** (2026-09-30): §3.6 و§3.10 و§3.1 **fixed** في صفوفها أعلاه. §3.4 جزئيّ (erp-bridge بلا profile — مؤكَّد؛ «readyz يكذب» تصميمٌ موثَّق في `health.py:8-12`) و§3.5 (ثلاثةُ مستهلكين لخدماتٍ خلف profile، منها field-segmentation→sam2 غيرُ مذكورٍ فيه) ⇒ **قرارُ مالك**. §3.7/§3.8 مؤكَّدان (أوزان SAM2 وحافّة `/models` بلا تزويد) ⇒ runbook بعد بوّابة الإنتاج. §3.9 الأسطرُ موجودة والسلوكُ يحتاج قياساً؛ §3.3 بلا `file:line` ⇒ لا يُقبَل؛ البنودُ السلوكيّة (SAM2 حيّ · RAG صفرُ نتائج · تكافؤُ الحمولة) قيسَت على نسخةٍ منجرفة ⇒ تُعاد على main/الإنتاج. |
"""

LOG = f"""## [2026-09-30] integration | تدقيقُ المالك المحلّيّ: ثلاثةُ إصلاحاتٍ بترتيبه، والتقريرُ نفسه صفٌّ

`FARM-FIELDS-LIST-TRUSTS-RLS-ALONE-01` (`{S['farm']}`) · `GEOMETRY-HISTORY-RETURNS-JSONB-AS-STRING-01` (`{S['geom']}`) · `AI-GENERATION-ATTRIBUTED-TO-SUPPRESSED-OUTPUT-01` (`{S['ai']}` · `{S['rcpt']}`) fixed، كلٌّ مُكذَّبٌ بعكس ملفّه. في §3.10 كان العطلُ أعمقَ من الحزمة: الـAPI يُعيد JSONB نصّاً، فأُصلِح في المصدر وبقيت الحزمةُ صارمةً (خطوةٌ مسمّاة لا فكٌّ يُخفيه). `LOCAL-AUDIT-REPORT-PINNED-TO-SHAS-NOT-IN-REPOSITORY-01` open: SHA التقرير غيرُ موجود، فحُكِم عليه بمراجعه؛ الباقي قرارُ مالك (§3.4 · §3.5) أو runbook بعد البوّابة (§3.7 · §3.8) أو إعادةُ قياس (§3.9 · البنود السلوكيّة). لا شيءَ منها يبلغ الإنتاج: المنصّةُ على `deploy/*`، وai-agronomist في staging وحدها.
"""

reg = root / "sahool-brain/gaps/registry.md"
text = reg.read_text(encoding="utf-8")
anchor = next(l for l in text.splitlines() if l.startswith("| TILER-IN-FIXED-AND-UNIFIED-HAS-NO-CONSUMER-AND-CANNOT-BUILD-01 |"))
assert text.count(anchor) == 1
for bad in ("‏", "‎"):
    assert bad not in ROWS + LOG
text = text.replace(anchor, anchor + "\n" + ROWS.rstrip("\n"), 1)
reg.write_text(text, encoding="utf-8")
log = root / "sahool-brain/log.md"
lt = log.read_text(encoding="utf-8")
if not lt.endswith("\n"):
    lt += "\n"
log.write_text(lt + LOG, encoding="utf-8")
print(S)
