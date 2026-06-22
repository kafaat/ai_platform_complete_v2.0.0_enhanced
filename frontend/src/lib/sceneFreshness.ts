// ═══════════════════════════════════════════════════════════════
// sceneFreshness — مقارنة توقيت/مشهد بيانات الطبقة المعروضة (FieldView)
// ───────────────────────────────────────────────────────────────
// الهدف (طراز Climate-FieldView): حين تُشتقّ طبقة المؤشّر (NDVI/NDMI…) المعروضة
// فوق الخريطة من «مشهد» (scene/تاريخ COG) يختلف عمّا يطلب المستخدم عرضه (التاريخ
// المختار على الشريط الزمنيّ)، نُحذّر بوضوح كي لا يثق المستخدم بطبقة قديمة.
//
// صدق المصدر (مُتحقَّق منه): استجابة raster-service لـ`indicator-grid` تُرجِع
// `date` = `layer.acquisition_date` (تاريخ التقاط المشهد الفعليّ للـCOG المعروض)
// — لا تُرجِع `scene_id` ولا `field_revision` بعد. لذا المقارنة المُتاحة اليوم
// (الصادقة) هي: «تاريخ مشهد الطبقة» مقابل «التاريخ المختار للعرض». أمّا مقارنة
// `scene_id`/`field_revision` الكاملة (التي تكشف اختلاف هندسة الحقل أو إعادة
// معالجة المشهد) فتنتظر أن تُسطّح الواجهة الخلفيّة `geometry_metadata(...)` على
// استجابات الراستر (انظر SceneProvenance + TODO أدناه).

// ── مزوّد المصدر الكامل (TODO: عندما تُرجعه واجهة الراستر) ──────────────
// يطابق `gis_geometry_guard.geometry_metadata(...)` في الخلفيّة:
//   { processing_version, scene_id, captured_at, field_revision, crs }
// عند توفّره على استجابة `indicator-grid` نُفعّل مقارنة كاملة (scene_id +
// field_revision) بدل مقارنة التاريخ وحدها. لا نخترع هذه الحقول قبل وصولها.
export interface SceneProvenance {
  scene_id?: string | null;
  captured_at?: string | null;
  field_revision?: number | null;
  processing_version?: string | null;
}

export type FreshnessLevel = 'mismatch' | 'match' | 'unknown';

export interface FreshnessResult {
  level: FreshnessLevel;
  // تاريخ مشهد الطبقة المعروضة فعلاً (من استجابة الراستر) — للعرض.
  layerDate: string | null;
  // التاريخ الذي يطلب المستخدم عرضه (المختار على الشريط الزمنيّ) — للعرض.
  displayDate: string | null;
  // سبب قابل للقراءة (للتشخيص/الاختبار) — لا يُعرَض للمستخدم مباشرة.
  reason:
    | 'no-layer-date'      // لا تاريخ مشهد للطبقة ⇒ unknown
    | 'no-display-date'    // العرض على «الأحدث» (latest) ⇒ لا مقارنة ⇒ unknown
    | 'same-scene'         // تاريخ الطبقة = التاريخ المختار ⇒ match
    | 'scene-mismatch';    // تاريخ الطبقة ≠ التاريخ المختار ⇒ mismatch
}

// تطبيع تاريخ إلى YYYY-MM-DD (يتسامح مع ISO الكامل والقيم الفارغة).
function dayOf(d?: string | null): string | null {
  if (!d || typeof d !== 'string') return null;
  const s = d.trim();
  if (!s || s === 'latest') return null;
  // نأخذ أوّل 10 محارف (YYYY-MM-DD) — تكفي لمطابقة المشهد اليوميّ.
  const day = s.slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(day) ? day : null;
}

// ── المقارنة المتاحة اليوم (صادقة): تاريخ مشهد الطبقة مقابل تاريخ العرض ──
// layerDate:    تاريخ المشهد الذي اشتُقّت منه الطبقة (response.date من الراستر).
// displayDate:  التاريخ الذي اختاره المستخدم للعرض ('latest' / '' ⇒ لا مقارنة).
//
// القاعدة: إذا تعذّر معرفة أيّ من التاريخين بدقّة ⇒ unknown (لا نُلفّق تحذيراً).
// إذا تطابقا ⇒ match. إذا اختلفا ⇒ mismatch (الطبقة من مشهد أقدم/مختلف).
export function compareSceneFreshness(
  layerDate?: string | null,
  displayDate?: string | null,
): FreshnessResult {
  const ld = dayOf(layerDate);
  const dd = dayOf(displayDate);
  if (!ld) {
    return { level: 'unknown', layerDate: ld, displayDate: dd, reason: 'no-layer-date' };
  }
  if (!dd) {
    // العرض على «الأحدث» — الطبقة هي الأحدث بطبيعتها ⇒ لا مقارنة معنويّة.
    return { level: 'unknown', layerDate: ld, displayDate: dd, reason: 'no-display-date' };
  }
  if (ld === dd) {
    return { level: 'match', layerDate: ld, displayDate: dd, reason: 'same-scene' };
  }
  return { level: 'mismatch', layerDate: ld, displayDate: dd, reason: 'scene-mismatch' };
}

// ── المقارنة الكاملة (TODO: مُعطّلة حتى تُرجِع الواجهة SceneProvenance) ──
// عند توفّر `scene_id`/`field_revision` على استجابة الطبقة وعلى مرجع الحقل/المشهد
// المختار، تستبدل هذه الدالّة `compareSceneFreshness` بمقارنة أدقّ:
//   • اختلاف scene_id  ⇒ mismatch (الطبقة من مشهد مختلف)
//   • اختلاف field_revision ⇒ mismatch (هندسة الحقل تغيّرت بعد اشتقاق الطبقة)
// لا نُفعّلها الآن لأنّ الواجهة الخلفيّة لا تُسطّح هذه الحقول بعد (انظر الرأس).
export function compareSceneProvenance(
  layer?: SceneProvenance | null,
  current?: SceneProvenance | null,
): FreshnessResult {
  // متاح جزئيّاً فقط: نسقط إلى مقارنة التاريخ الصادقة حتى تصل الحقول الكاملة.
  const byDate = compareSceneFreshness(layer?.captured_at, current?.captured_at);
  if (!layer || !current) return byDate;
  const sceneKnown = layer.scene_id != null && current.scene_id != null;
  const revKnown = layer.field_revision != null && current.field_revision != null;
  if (!sceneKnown && !revKnown) return byDate;
  const sceneMismatch = sceneKnown && layer.scene_id !== current.scene_id;
  const revMismatch = revKnown && layer.field_revision !== current.field_revision;
  if (sceneMismatch || revMismatch) {
    return {
      level: 'mismatch',
      layerDate: dayOf(layer.captured_at),
      displayDate: dayOf(current.captured_at),
      reason: 'scene-mismatch',
    };
  }
  return {
    level: 'match',
    layerDate: dayOf(layer.captured_at),
    displayDate: dayOf(current.captured_at),
    reason: 'same-scene',
  };
}
