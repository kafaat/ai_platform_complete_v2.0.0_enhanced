# مراجعة قنوات تنزيل صور الأقمار — تصنيف صادق لساهول

**التاريخ:** 2026-07-07 · **الحالة:** مُتحقَّق مباشرةً من المواقع الرسميّة · **المرجع البرمجيّ:** `services/raster-service/raster_scene_model.py`

> **تصحيح جوهريّ:** `scihub.copernicus.eu` (Copernicus Open Access Hub / SciHub) **أُغلِق أواخر أكتوبر 2023**؛ لا يُضاف كمصدر. البديل الرسميّ لـSentinel هو **CDSE** (STAC/OData/Process API) + **Copernicus Browser** للاستخدام اليدويّ.

## المبدأ: تصنيف بلا مبالغة
كلّ مصدر يُصنَّف صراحةً؛ `active=True` **فقط** لما هو موصول فعلاً في الكود. الفئات في `raster_scene_model.py`:

| الفئة | السِجِلّ | الدلالة |
|---|---|---|
| مزوّد نشط | `PROVIDER_REGISTRY` (active=True) | موصول ويُستدعى الآن |
| مزوّد مُخطَّط | `PROVIDER_REGISTRY` (active=False, verified=True) | مُتحقَّق، يحتاج مُحوِّل/اعتمادات قبل التفعيل |
| مصدر بحثيّ/مكتبة | `RESEARCH_REGISTRY` (provides_imagery=False) | أفكار/خوارزميّات لا صور |
| مصدر خارجيّ | `EXTERNAL_SOURCE_REGISTRY` (active_provider=False) | يدويّ/تجاريّ/أحداث/تقييم |

## أ) مزوّدون نشطون (مجانيّ، إنتاجيّ)
| المزوّد | الدقة | يغطّي اليمن | الدور |
|---|---|---|---|
| **CDSE** | 10/20/60م (Sentinel-2) | ✅ | المصدر الرسميّ لـSentinel (بديل SciHub) — معالجة تستهلك وحدات |
| **Element84 Earth Search** | 10م S2 / 30م Landsat | ✅ | STAC + COG (الافتراضيّ الحاليّ، بلا مصادقة) |
| **local_cog** | حسب الأصول | داخليّ | COGs مُنتَجة/مُعادة الترطيب |

## ب) مزوّدون مُخطَّطون مُتحقَّقون (active=False حتّى مُحوِّل + عقد)
| المزوّد | الدقة | يغطّي اليمن | الدور | الاحتكاك |
|---|---|---|---|---|
| **Microsoft Planetary Computer** | 10–60م | ✅ | STAC fallback + HLS/DEM | توقيع SAS قصير العمر |
| **NASA HLS (HLSS30/L30)** | 30م | ✅ (كلّ اليابسة عدا Antarctica) | خطّ أساس تاريخيّ/شذوذ موسميّ | Earthdata Login |
| **FAO WaPOR v3** | 100م (الشرق الأدنى)/300م عالميّ | ✅ | إنتاجيّة المياه/ET — **أعلى قيمة لليمن** | CC-BY، بلا مصادقة |
| **ESA WorldCereal** | 10م | ✅ | prior محاصيل/ريّ مُثقَل بالثقة | استعمل قسم CC-BY فقط |
| **ASTER GDEM** | ~30م | ✅ | DEM/slope/hillshade/contours (رفد terrain) | Earthdata/METI |

## ج) مصادر خارجيّة (يدويّ/تجاريّ/أحداث/تقييم) — active_provider=False دائماً
| المصدر | النوع | مجانيّ | الحكم |
|---|---|---|---|
| **USGS EarthExplorer** | manual_download | ✅ | Landsat/ASTER/DEM backfill (تسجيل + تحميل يدويّ) |
| **PlanetScope (Planet)** | commercial | ✗ | ~3.7م شبه يوميّ — طبقة مدفوعة عالية الدقة |
| **Maxar Open Data** | event_open_data | أحداث فقط | صور كوارث <1م قبل/بعد — لا تغطية يوميّة عامّة |
| **China Gaofen (GF-1/6)** | research_manual | غير مُتحقَّق | `cnsageo.com` — **لا إنتاج قبل تحقّق ترخيص/API/تسجيل/تغطية** |

## د) المصادر الصينيّة — حكم عمليّ
منصّات مثل CRESDA/CPEOS/NSMC/Geospatial Data Cloud/geodata.cn مفيدة للبحث، لكن لا تُعتمَد كمزوّد إنتاجيّ قبل التحقّق من: التسجيل خارج الصين · السماح التجاريّ · تغطية اليمن · وضوح الـAPI · ترخيص إعادة الاستخدام داخل SaaS. لذا `china_gaofen.requires_verification=True`، `source_type=research_manual`.

## الخلاصة
- **تدخل كقنوات موثوقة الآن:** CDSE · Element84 (نشطان) + المُخطَّطون المُتحقَّقون: PC · NASA HLS · WaPOR · WorldCereal · ASTER GDEM (+ USGS EarthExplorer كتحميل يدويّ).
- **تبقى غير مفعّلة (بلا مبالغة):** PlanetScope (مدفوع) · Maxar (أحداث) · China Gaofen (تحقّق) · SciHub (مُغلَق — لا يُضاف).
- **الأولويّة التنفيذيّة القادمة لليمن:** WaPOR → WorldCereal → NASA HLS → ASTER GDEM (كلّها تحتاج مُحوِّلاً + اعتمادات/عقد).

الحالة الحيّة قابلة للقراءة آليّاً عبر `GET /v1/providers/status` (raster-service) الذي يكشف `providers` + `research_sources` + `external_sources`.
