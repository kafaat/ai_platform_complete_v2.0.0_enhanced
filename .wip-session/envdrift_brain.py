"""Insert env_drift brain rows. SHAs resolved from commit subjects in the current tree (post-rebase)."""
import subprocess, sys, pathlib

root = pathlib.Path(sys.argv[1])
MODE = sys.argv[2] if len(sys.argv) > 2 else "ALL"  # A = لا يبلغ الإنتاج · B = TileJSON (الإنتاج)
B_IDS = ("TITILER-TILEJSON-BLAMES-TITILER-URL-01", "COG-TILE-503-NAMES-THE-BACKEND-FOR-AN-EMPTY-ALLOWLIST-01")
def sha(prefix):
    out = subprocess.check_output(["git", "-C", str(root), "log", "--format=%h %s", "-n", "30"], text=True)
    hits = [l.split()[0] for l in out.splitlines() if l.split(" ", 1)[1].startswith(prefix)]
    assert len(hits) <= 1, (prefix, hits)
    return hits[0] if hits else "—"

S = {
    "clients": sha("Redis في light وunified"),
    "state": sha("v9: auth وguardrails"),
    "envex": sha(".env.example: REDIS_PASSWORD"),
    "utf8": sha("شاهدُ كلمة سرّ Redis"),
    "tilejson": sha("الراستر: TileJSON"),
    "sam2": sha("SAM2 بلا أوزان"),
}

ROWS = f"""| REDIS-CLIENTS-WITHOUT-PASSWORD-LIGHT-UNIFIED-01 | **light وunified: خادمُ Redis بـ`--requirepass` وعملاؤه بلا كلمة سرّ** — ٦ عملاء في light و٩ في unified ⇒ `AuthenticationError: Authentication required` لكلّ عميل والخادمُ أخضر (مقيسٌ على redis-server 7.0.15 + redis-py 5.3.1). v9 13/13 وfixed 8/8 سليمان. وفي التطوير كان auth يضبط `_redis=None` بصمت فيُطفئ الإبطالَ والقفل. | compose/redis | `docker-compose.light.yml:41` · `docker-compose.unified.yml:46` · `services/auth/main.py:370` · `tests_v9/test_redis_password_wiring.py` | **fixed** (`{S['clients']}`، 2026-09-30): الروابطُ تحمل `${{REDIS_PASSWORD:?}}`؛ الشاهدُ يقرأ كلمةَ الخادم من argv ويفكّ كلَّ رابطٍ بمحلِّل redis-py نفسِه عبر كلّ `docker-compose*.yml` (أرضيّة ≥30 عميلاً). التكذيب: عكسُ الملفّين ⇒ 15 أحمر بالاسم. |
| REDIS-STATE-NOT-A-DEPENDENCY-OF-ITS-CLIENTS-01 | **v9: auth وguardrails يتّصلان بـ`sahool-redis-state` وينتظران `sahool-redis`** — لا خدمةَ تعتمد على redis-state، فإغلاقُ اعتماد nginx (39 خدمة) لا يحويه؛ وauth يقرأ Redis مرّةً عند الإقلاع فيعمل في التطوير بلا Redis طوالَ عمره. | compose/v9 | `docker-compose.v9.yml` (depends_on لـsahool-auth وsahool-guardrails-engine) · `services/auth/main.py:370` | **fixed** (`{S['state']}`، 2026-09-30): الاعتمادُ على الذي يتّصلان به (`service_healthy`)؛ إغلاقُ nginx صار 40 ويحويه. الشاهد `test_a_client_that_waits_for_redis_waits_for_the_one_it_talks_to` لكلّ عميلٍ في كلّ ملفّ؛ التكذيب ⇒ 2 أحمر بالاسم. خارج النطاق ومُسجَّل: actuator وraster-service وbackfill-worker بلا depends_on على Redis أصلاً. |
| REDIS-PASSWORD-EMBEDDED-UNENCODED-IN-URLS-01 | **`REDIS_PASSWORD` تُدمَج حرفيّاً في ٢٩ رابطَ عميل:** `/` `?` `#` تُسقِط التحليل (`Port could not be cast`)، و`%` تُغيّر الكلمة، والخادمُ يقبلها فيبقى فحصُه أخضر؛ `/` في 933 من 2000 سحبة base64. و`.env.example` كانت تنسبها إلى `REDIS_URL` (وهو بلا كلمة) ولا تُسمّي مولِّداً. | compose/env | `.env.example:300` · `tests_v9/test_redis_password_wiring.py` | **fixed (إرشاد)** (`{S['envex']}` · `{S['utf8']}`، 2026-09-30): `.env.example` تُلزِم `openssl rand -hex 32` وتصف الإخفاقاتِ المقيسة، وشاهدُ الدوران يمرّ hex عبر الروابط كلّها ويُسقط base64. **مفتوحٌ للمالك:** رفضُ الخادم لكلمةٍ غيرِ آمنةٍ للروابط (يُغيّر أمرَ إقلاع خدمتين)؛ وخطوةٌ أرخص: `command:` بصيغة القائمة كي لا يُسقِط compose `\\` من `--requirepass`. |
| TITILER-TILEJSON-BLAMES-TITILER-URL-01 | **«انجرافُ TITILER_URL» ليس انجرافاً في المستودع:** القيمةُ متّسقة (`.env.example` = افتراضُ v9 = `raster-tiler-service:8088` = `EXPOSE 8088`). العطلُ إحالةٌ خاطئة: TileJSON الراستر كان يُعلِن بلاطاتٍ ديناميكيّةً يرفضها الناقل (القائمةُ فارغةٌ عمداً) ويقول «اضبط TITILER_URL» والمتغيّرُ مضبوط — ٩/٩ خلايا المصفوفة تخالف «المُعلَن ⇔ المجلوب». | raster-service | `services/raster-service/raster_security_context.py:205` · `services/raster-service/routers/tiles.py:77` · `tests_v9/test_connectivity_tile_transport.py` | **fixed** (`{S['tilejson']}`، 2026-09-30): `dynamic_tile_refusal()` يُعلِن الديناميكيَّ حين يجلبه الناقلُ وحده ويُسمّي الناقص (`layer_has_no_public_cog` · `titiler_url_not_configured` · `titiler_url_invalid` · `cog_tile_allowed_hosts_not_configured` · `cog_tile_source_not_allowed`). التكذيب: عكسُ raster-service ⇒ 10 أحمر. ما إن كان `.env` المُدقَّق يحمل قيمةً أخرى فغيرُ معروفٍ من المستودع. |
| COG-TILE-503-NAMES-THE-BACKEND-FOR-AN-EMPTY-ALLOWLIST-01 | **الناقلُ يرفض القائمةَ الفارغة بـ`cog_tile_backend_not_configured`** — شرطا الإدخال الفارغ يتشاركان سبباً واحداً، فكلُّ بلاطةٍ على المنصّة والراستر تُحيل إلى `TITILER_URL` المضبوط، بلا طلبٍ واحدٍ إلى الخلفيّة. | shared/gis | `shared/gis/cog_tile_proxy.py:40` · `services/sahool-platform/api/routers/gis_cloud_native.py:578` | **open** (2026-09-30): الإصلاحُ مكتوبٌ ومُكذَّب (سببٌ منفصل `cog_tile_allowed_hosts_not_configured`) **ومُعلَّقٌ** لأنّه يمسّ `shared/**` — ينتظر قرارَ المالك في queue_v1، وهو مستقلٌّ عن `{S['tilejson']}`. |
| TILER-IN-FIXED-AND-UNIFIED-HAS-NO-CONSUMER-AND-CANNOT-BUILD-01 | **fixed/unified: `raster-tiler-service` بلا مستهلك وبلا سياقِ بناءٍ صالح** — لا خدمةَ تتلقّى `TITILER_URL` ولا تعتمد عليه؛ و`build: ./services/raster-tiler-service` بينما الـDockerfile ينسخ مساراتٍ من جذر المستودع؛ ولا تمرّر أيٌّ من الحزمتين `SAHOOL_GIT_SHA`/`SAHOOL_BUILD_ID` فلا تُبنى أيُّ صورةٍ مختومة الهويّة. دليلٌ ساكن (لا Docker daemon). | compose/fixed·unified | `docker-compose.fixed.yml:30` · `docker-compose.unified.yml:50` · `services/raster-tiler-service/Dockerfile:63` | **open — قرارُ مالك** (2026-09-30): هل fixed/unified هدفا بناءٍ مدعومان؟ نعم ⇒ سياق `.` + مسار الـDockerfile + وسائطُ الهويّة ثمّ الربط؛ لا ⇒ حذفُ كتلة الـtiler منهما (أُضيفت في استيراد #1002، `db8a570d`). |
"""

LOG = f"""## [2026-09-30] integration | إعادةُ تشغيل وكيل انجراف البيئة: أربعُ فجواتٍ fixed، وواحدةٌ مُعلَّقة، وقرارُ مالك

`REDIS-CLIENTS-WITHOUT-PASSWORD-LIGHT-UNIFIED-01` (`{S['clients']}`) · `REDIS-STATE-NOT-A-DEPENDENCY-OF-ITS-CLIENTS-01` (`{S['state']}`) · `REDIS-PASSWORD-EMBEDDED-UNENCODED-IN-URLS-01` (`{S['envex']}` · `{S['utf8']}`، إرشاد) · `TITILER-TILEJSON-BLAMES-TITILER-URL-01` (`{S['tilejson']}`) fixed. `COG-TILE-503-NAMES-THE-BACKEND-FOR-AN-EMPTY-ALLOWLIST-01` open والإصلاحُ مُعلَّق (`shared/**`). `TILER-IN-FIXED-AND-UNIFIED-HAS-NO-CONSUMER-AND-CANNOT-BUILD-01` قرارُ مالك. **أُعيد قياسُه ولم يتغيّر:** `SAM2` صادقٌ على التطبيق بحدث إقلاعه (`/readyz` 503 بسببٍ مسمًّى، `/v1/predict` 503 بلا هندسة) وصار له شاهدٌ (`{S['sam2']}`)؛ `EDGE-MODEL-ARTIFACT-INTEGRITY-01` يبقى fixed (الاستدلالُ 503 بسببٍ مسمًّى، و`/readyz` الجزئيّ 200 بجسمٍ degraded **قرارٌ مُثبَّت** — خيارُ 503 عند صفرِ نماذج نشطة للمالك)؛ وفحوصُ Docker على local-ai-rag/rag-retrieval/ai-agronomist تسأل `/healthz` عمداً (`ai_container_contract_guard.py:118-123`) لأنّ nginx يعتمد عليها `service_healthy`. راجعتُ `dynamic_tile_refusal` مركزيّاً: `get_tile` لم يتغيّر، والإعلانُ وحده صار مشروطاً بالناقل.
"""

LOG_A = f"""## [2026-09-30] integration | انجراف البيئة (أ): ثلاثُ فجواتِ Redis fixed وقرارُ مالك — لا شيءَ منها يبلغ الإنتاج

`REDIS-CLIENTS-WITHOUT-PASSWORD-LIGHT-UNIFIED-01` (`{S['clients']}`) · `REDIS-STATE-NOT-A-DEPENDENCY-OF-ITS-CLIENTS-01` (`{S['state']}`) · `REDIS-PASSWORD-EMBEDDED-UNENCODED-IN-URLS-01` (`{S['envex']}` · `{S['utf8']}`، إرشاد) fixed؛ `TILER-IN-FIXED-AND-UNIFIED-HAS-NO-CONSUMER-AND-CANNOT-BUILD-01` قرارُ مالك. **قُسِّمت الشريحةُ بقرار المالك:** الإنتاجُ على Railway يُنشَر من `main` بلا انتظار CI (`checkSuites:false`)، فالتزامُ TileJSON وحده (`services/raster-service/**`، مسارٌ مراقَب) يُمسَك إلى ما بعد إغلاق بوّابة الإنتاج مع صفَّيه (يُسجَّلان في الشريحة (ب) مع التزامهما، لا قبله). ما هنا ملفّاتُ compose و`.env.example` و`tests_v9` والدماغ — لا يطابق أيَّ نمط مراقبةٍ لخدمةٍ على Railway (مقيسٌ من إعدادات الخدمات). **أُعيد قياسُه ولم يتغيّر:** `SAM2` صادقٌ على التطبيق بحدث إقلاعه وصار له شاهدٌ (`{S['sam2']}`)؛ `EDGE-MODEL-ARTIFACT-INTEGRITY-01` يبقى fixed (`/readyz` الجزئيّ 200 بجسمٍ degraded قرارٌ مُثبَّت، وخيارُ 503 عند صفرِ نماذج للمالك)؛ وفحوصُ Docker على local-ai-rag/rag-retrieval/ai-agronomist تسأل `/healthz` عمداً (`ai_container_contract_guard.py:118-123`).
"""
LOG_B = f"""## [2026-09-30] integration | انجراف البيئة (ب): TileJSON الراستر يُعلِن ما يجلبه الناقل — بعد إغلاق بوّابة الإنتاج

`TITILER-TILEJSON-BLAMES-TITILER-URL-01` (`{S['tilejson']}`) fixed؛ `COG-TILE-503-NAMES-THE-BACKEND-FOR-AN-EMPTY-ALLOWLIST-01` open والإصلاحُ مُعلَّق (`shared/**`). راجعتُ `dynamic_tile_refusal` مركزيّاً: `get_tile` لم يتغيّر، والإعلانُ وحده صار مشروطاً بالناقل. يبلغ الإنتاجَ (`services/raster-service/**`).
"""

reg = root / "sahool-brain/gaps/registry.md"
text = reg.read_text(encoding="utf-8")
keep = [l for l in ROWS.strip("\n").split("\n")
        if MODE == "ALL" or (MODE == "B") == l.startswith(tuple("| " + i + " |" for i in B_IDS))]
ROWS = "\n".join(keep) + "\n"
if MODE == "A":
    LOG = LOG_A
elif MODE == "B":
    LOG = LOG_B
anchor = next(l for l in text.splitlines() if l.startswith("| CLAIM-LEASE-RACE-REPRODUCTION-IS-ITSELF-A-RACE-01 |"))
assert text.count(anchor) == 1
text = text.replace(anchor, anchor + "\n" + ROWS.rstrip("\n"), 1)
reg.write_text(text, encoding="utf-8")

log = root / "sahool-brain/log.md"
lt = log.read_text(encoding="utf-8")
if not lt.endswith("\n"):
    lt += "\n"
log.write_text(lt + LOG, encoding="utf-8")
print(S)
