// ═══════════════════════════════════════════════════════════════
// SAHOOL — maphub/FieldSplitMergeTool.tsx
// أداة دمج/تقسيم الحقول (Split & Merge) — العمليّة الوحيدة المُتلِفة (تستبدل
// سجلّات الحقول)، فالصدق ومعالجة الأخطاء الأمينة فوق كلّ اعتبار.
// ───────────────────────────────────────────────────────────────
// دمج: اختَر حقلين فأكثر → اتّحاد حدودهما (turf) → عند التأكيد: أنشئ حقلاً واحداً
//       بالهندسة المدموجة ثمّ احذف الأصول. صافي الأثر: عدّة حقول → حقل واحد.
// تقسيم: اختَر حقلاً واحداً وارسم مضلّع قصّ فوق جزء منه → الجزء أ = تقاطع، الجزء ب
//       = فرق → عند التأكيد: أنشئ الحقلين الوليدين ثمّ احذف الأصل. حقل → حقلان.
//
// القيود الصارمة (عقود الخلفيّة):
//   • الذرّيّة الآن خادميّة: نقطتا POST /fields/merge و/split تُنفّذان الإنشاء
//     والحذف في **معاملة قاعدة واحدة** (الكلّ أو لا شيء). فشلٌ ⇒ تراجع كامل ورسالة
//     صادقة من ردّ النقطة — لا «دمج/تقسيم جزئيّ» بعد الآن (سُدّ خطر الحقول اليتيمة).
//   • فحص الموسم النشط مسبقاً يبقى (UX سريع): الخادم يردّ 409 إن لمصدر موسم نشط،
//     لكن نفحص مسبقاً عبر fetchSeasons لِنحجب بوضوح قبل النداء (تجربة أفضل).
//   • أمانة الهندسة: لا اختراع. قصّ لا يتقاطع → خطأ صريح. دمج ينتج MultiPolygon
//     (حقول غير متجاورة) والخادم يخزّن Polygon فقط → نحجب بطلب اختيار متجاور.
// ═══════════════════════════════════════════════════════════════
import { useCallback, useEffect, useMemo, useState } from 'react';
import { MapContainer, TileLayer, Polygon, FeatureGroup } from 'react-leaflet';
import L from 'leaflet';
import '../../lib/leafletSetup';
import { Combine, Scissors, X, AlertTriangle, Loader2 } from 'lucide-react';
import DrawControl from './DrawControl';
import { geomToPolygon, collectFieldBoundsPoints, areaSqMeters } from '../../lib/geo';
import {
  mergeFieldGeometries, splitFieldGeometry, isMultiPolygon, type ArealGeometry,
} from '../../lib/fieldGeometryOps';
import { mergeFields, splitField as apiSplitField, asApiError, apiErrorMessage, fetchSeasons } from '../../services/api';
import { toastStore } from '../../services/websocket';
import type { FieldOption } from '../../lib/fields';
import { T, RADIUS, Card, Pill, Badge, SectionLabel } from '../ds';
import { LoadingState } from '../StateViews';

type Mode = 'merge' | 'split';

interface Props {
  fields: FieldOption[];
  // الحقل المختار حاليّاً في المركز (يُهيَّأ كحقل التقسيم الأوّليّ إن وُجد).
  selectedId: string;
  onClose: () => void;
  // يُعاد جلب قائمة الحقول دائماً بعد أيّ create/delete (نجاحاً أو جزئيّاً).
  refetch: () => void;
}

// هندسة GeoJSON Polygon المرسومة من leaflet-draw → شكل {type,coordinates}.
function layerToGeometry(layer: L.Layer): ArealGeometry | null {
  const toGeoJSON = (layer as { toGeoJSON?: () => GeoJSON.Feature }).toGeoJSON;
  let gj: GeoJSON.Feature | null;
  try { gj = toGeoJSON?.() ?? null; } catch { gj = null; }
  const g = gj?.geometry;
  if (g && (g.type === 'Polygon' || g.type === 'MultiPolygon')) {
    return g as ArealGeometry;
  }
  return null;
}

function fmtArea(geom: unknown): string {
  const m2 = areaSqMeters(geom);
  const ha = m2 / 10000;
  return `${ha.toFixed(2)} هكتار`;
}

// يحوّل هندسة مساحيّة (Polygon/MultiPolygon) إلى حلقات Leaflet للمعاينة.
function geomToLeafletRings(geom: ArealGeometry | null): [number, number][][] {
  if (!geom) return [];
  if (geom.type === 'Polygon') {
    const ring = geomToPolygon(geom);
    return ring ? [ring] : [];
  }
  // MultiPolygon: حلقة خارجيّة لكلّ جزء.
  const out: [number, number][][] = [];
  for (const part of geom.coordinates) {
    const ring = geomToPolygon({ type: 'Polygon', coordinates: part });
    if (ring) out.push(ring);
  }
  return out;
}

export default function FieldSplitMergeTool({ fields, selectedId, onClose, refetch }: Props) {
  const [mode, setMode] = useState<Mode>('merge');
  const [busy, setBusy] = useState(false);

  // ── الدمج: اختيار متعدّد ──────────────────────────────────────
  const [mergeIds, setMergeIds] = useState<string[]>([]);
  // ── التقسيم: حقل واحد + مضلّع قصّ مرسوم ────────────────────────
  const [splitId, setSplitId] = useState<string>(selectedId || '');
  const [cutGeom, setCutGeom] = useState<ArealGeometry | null>(null);

  // اسم/أسماء الحقول الجديدة (يطلبها المستخدم صراحةً).
  const [mergeName, setMergeName] = useState('');
  const [nameA, setNameA] = useState('');
  const [nameB, setNameB] = useState('');

  // الحقول ذات الهندسة المساحيّة فقط قابلة للدمج/التقسيم (لا نقاط بلا حدود).
  const arealFields = useMemo(
    () => fields.filter((f) => {
      const ring = geomToPolygon(f.geometry);
      return ring && ring.length >= 3;
    }),
    [fields],
  );

  const fieldById = useMemo(() => {
    const m = new Map<string, FieldOption>();
    for (const f of fields) m.set(f.id, f);
    return m;
  }, [fields]);

  // ── معاينة الهندسة الناتجة ────────────────────────────────────
  const mergePreview = useMemo<ArealGeometry | null>(() => {
    if (mode !== 'merge' || mergeIds.length < 2) return null;
    const geoms = mergeIds.map((id) => fieldById.get(id)?.geometry).filter(Boolean);
    return mergeFieldGeometries(geoms);
  }, [mode, mergeIds, fieldById]);

  const splitPreview = useMemo<{ partA: ArealGeometry; partB: ArealGeometry } | null>(() => {
    if (mode !== 'split' || !splitId || !cutGeom) return null;
    const field = fieldById.get(splitId);
    if (!field) return null;
    return splitFieldGeometry(field.geometry, cutGeom);
  }, [mode, splitId, cutGeom, fieldById]);

  // تحذير الدمج متعدّد الأجزاء (الخادم يخزّن Polygon فقط ⇒ سنحجب التأكيد).
  const mergeIsMulti = isMultiPolygon(mergePreview);

  const toggleMergeId = useCallback((id: string) => {
    setMergeIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }, []);

  // ── فحص الموسم النشط مسبقاً لكلّ حقل سيُحذَف (يتفادى 409 ونصف الإنجاز) ──
  // يُرجِع اسم أوّل حقل ذي موسم نشط، أو null إن كلّها قابلة للحذف. أيّ خطأ في
  // جلب المواسم (503/403) يُرفَع كي نحجب بصدق بدل المضيّ على فحص ناقص.
  const findActiveSeasonField = useCallback(async (ids: string[]): Promise<string | null> => {
    for (const id of ids) {
      const seasons = await fetchSeasons(id);
      const hasActive = seasons.some((s) => String(s.status).toLowerCase() === 'active');
      if (hasActive) return fieldById.get(id)?.name ?? id;
    }
    return null;
  }, [fieldById]);

  // ── سمة المحصول الموروثة من حقل مصدر (المعروفة فقط؛ البقيّة للخادم/التحرير) ──
  const inheritedCrop = useCallback(
    (source?: FieldOption): string | null =>
      source && source.crop && source.crop !== '—' ? source.crop : null,
    [],
  );

  // ── تنفيذ الدمج ───────────────────────────────────────────────
  const runMerge = useCallback(async () => {
    if (mergeIds.length < 2) {
      toastStore.add('warning', '⚠️ اختَر حقلين على الأقلّ', 'الدمج يتطلّب حقلين أو أكثر.');
      return;
    }
    if (!mergeName.trim()) {
      toastStore.add('warning', '⚠️ اسم الحقل المدموج مطلوب', 'أدخِل اسماً للحقل الناتج.');
      return;
    }
    const merged = mergePreview;
    if (!merged) {
      toastStore.add('error', '⚠️ تعذّر حساب الاتّحاد', 'تحقّق من صحّة حدود الحقول المختارة.');
      return;
    }
    if (isMultiPolygon(merged)) {
      // حقول غير متجاورة ⇒ MultiPolygon؛ الخادم يخزّن Polygon فقط — نحجب بصدق.
      toastStore.add(
        'error', '⚠️ الحقول غير متجاورة',
        'ينتج عن الدمج مضلّع متعدّد الأجزاء لا يقبله الخادم — اختَر حقولاً متلاصقة.',
      );
      return;
    }
    setBusy(true);
    try {
      // فحص الموسم النشط مسبقاً لكلّ أصل (UX سريع؛ الخادم يردّ 409 أيضاً).
      const blocked = await findActiveSeasonField(mergeIds);
      if (blocked) {
        toastStore.add('error', '⚠️ موسم نشط يمنع الدمج', `أغلِق الموسم النشط للحقل «${blocked}» قبل الدمج.`);
        return;
      }
      // نداء واحد ذرّيّ: الخادم يُنشئ المدموج ويحذف المصادر في معاملة واحدة (الكلّ
      // أو لا شيء) — لا «دمج جزئيّ» ولا حقول يتيمة. السمات الموروثة من أوّل مصدر.
      const first = fieldById.get(mergeIds[0]);
      await mergeFields({
        source_field_ids: mergeIds,
        name: mergeName.trim(),
        crop: inheritedCrop(first),
        geometry: merged,
      });
      toastStore.add('success', '✅ تمّ دمج الحقول', `أُنشئ «${mergeName.trim()}» وحُذِفت ${mergeIds.length} حقول.`);
      setMergeIds([]); setMergeName('');
      onClose();
    } catch (e) {
      // رسالة صادقة من ردّ النقطة (404 مصدر / 409 موسم / 422 هندسة / 503) — المعاملة
      // تراجعت فلا حقل مدموج يتيَّم ولا مصدر محذوف بلا بديل.
      toastStore.add('error', '⚠️ فشل الدمج', apiErrorMessage(e, asApiError(e).message || 'تعذّر دمج الحقول.'));
    } finally {
      setBusy(false);
      refetch();
    }
  }, [mergeIds, mergeName, mergePreview, findActiveSeasonField, fieldById, inheritedCrop, onClose, refetch]);

  // ── تنفيذ التقسيم ─────────────────────────────────────────────
  const runSplit = useCallback(async () => {
    const field = fieldById.get(splitId);
    if (!field) {
      toastStore.add('warning', '⚠️ اختَر حقلاً للتقسيم', 'حدّد الحقل المراد تقسيمه.');
      return;
    }
    if (!cutGeom) {
      toastStore.add('warning', '⚠️ ارسم مضلّع القصّ', 'ارسم مضلّعاً فوق الجزء المراد فصله.');
      return;
    }
    const parts = splitFieldGeometry(field.geometry, cutGeom);
    if (!parts) {
      // تقاطع/فرق فارغ ⇒ القصّ لم يتقاطع فعليّاً مع الحقل (أو ابتلعه كاملاً).
      toastStore.add('error', '⚠️ القصّ غير صالح', 'لم يتقاطع مضلّع القصّ مع الحقل — ارسمه فوق الحقل.');
      return;
    }
    if (isMultiPolygon(parts.partA) || isMultiPolygon(parts.partB)) {
      toastStore.add(
        'error', '⚠️ ناتج متعدّد الأجزاء',
        'ينتج عن القصّ جزء متعدّد المضلّعات لا يقبله الخادم — ارسم قصّاً يفصل الحقل إلى جزأين متّصلين.',
      );
      return;
    }
    if (!nameA.trim() || !nameB.trim()) {
      toastStore.add('warning', '⚠️ اسما الجزأين مطلوبان', 'أدخِل اسماً لكلّ جزء ناتج.');
      return;
    }
    setBusy(true);
    try {
      // فحص الموسم النشط مسبقاً للأصل (UX سريع؛ الخادم يردّ 409 أيضاً).
      const blocked = await findActiveSeasonField([splitId]);
      if (blocked) {
        toastStore.add('error', '⚠️ موسم نشط يمنع التقسيم', `أغلِق الموسم النشط للحقل «${blocked}» قبل التقسيم.`);
        return;
      }
      // نداء واحد ذرّيّ: الخادم يُنشئ الجزأين ويحذف الأصل في معاملة واحدة (الكلّ أو
      // لا شيء) — لا «تقسيم جزئيّ» ولا أصل محذوف بلا أطفال. المحصول موروث من الأصل.
      const crop = inheritedCrop(field);
      await apiSplitField({
        source_field_id: splitId,
        children: [
          { name: nameA.trim(), geometry: parts.partA, crop },
          { name: nameB.trim(), geometry: parts.partB, crop },
        ],
      });
      toastStore.add('success', '✅ تمّ تقسيم الحقل', `أُنشئ «${nameA.trim()}» و«${nameB.trim()}» وحُذِف الأصل.`);
      setCutGeom(null); setNameA(''); setNameB('');
      onClose();
    } catch (e) {
      // رسالة صادقة من ردّ النقطة (404 مصدر / 409 موسم / 422 هندسة / 503) — المعاملة
      // تراجعت فلا جزء يتيَّم ولا أصل محذوف بلا أطفال.
      toastStore.add('error', '⚠️ فشل التقسيم', apiErrorMessage(e, asApiError(e).message || 'تعذّر تقسيم الحقل.'));
    } finally {
      setBusy(false);
      refetch();
    }
  }, [splitId, cutGeom, nameA, nameB, fieldById, findActiveSeasonField, inheritedCrop, onClose, refetch]);

  // عند تبديل الوضع نُصفّر الحالة المتعلّقة بالوضع الآخر (تفادي خلط).
  const switchMode = useCallback((m: Mode) => {
    setMode(m);
    setCutGeom(null);
  }, []);

  const splitField = fieldById.get(splitId);

  return (
    <div
      dir="rtl"
      role="dialog"
      aria-modal="true"
      aria-label="أداة دمج/تقسيم الحقول"
      style={{
        position: 'fixed', inset: 0, zIndex: 2000,
        background: 'rgba(0,0,0,.45)', display: 'flex',
        alignItems: 'center', justifyContent: 'center', padding: 16,
      }}
      onClick={() => { if (!busy) onClose(); }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: T.cream, borderRadius: RADIUS.lg, width: 'min(960px, 96vw)',
          maxHeight: '92vh', overflow: 'auto', border: `1px solid ${T.line}`,
        }}
      >
        {/* ترويسة */}
        <div
          className="flex items-center gap-2"
          style={{ padding: '12px 16px', borderBottom: `1px solid ${T.line}`, background: T.card }}
        >
          <Combine className="w-5 h-5" style={{ color: T.green }} aria-hidden="true" />
          <h2 style={{ fontWeight: 800, color: T.ink, fontSize: 16 }}>دمج / تقسيم الحقول</h2>
          <button
            type="button" onClick={() => { if (!busy) onClose(); }}
            aria-label="إغلاق"
            style={{ marginInlineStart: 'auto', color: T.muted, background: 'transparent', border: 'none', cursor: 'pointer' }}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
          {/* مبدّل الوضع */}
          <div className="flex rounded-lg overflow-hidden" style={{ border: `1px solid ${T.line}`, alignSelf: 'flex-start' }}>
            <button
              type="button" onClick={() => switchMode('merge')} disabled={busy}
              className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold"
              style={{ background: mode === 'merge' ? T.green : 'transparent', color: mode === 'merge' ? '#fff' : T.muted }}
            >
              <Combine className="w-4 h-4" /> دمج
            </button>
            <button
              type="button" onClick={() => switchMode('split')} disabled={busy}
              className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold"
              style={{ background: mode === 'split' ? T.green : 'transparent', color: mode === 'split' ? '#fff' : T.muted }}
            >
              <Scissors className="w-4 h-4" /> تقسيم
            </button>
          </div>

          {/* تحذير العمليّة المُتلِفة */}
          <div
            className="flex items-start gap-2"
            style={{ background: T.dangerBg, color: T.danger, borderRadius: RADIUS.sm, padding: '8px 12px', fontSize: 12 }}
          >
            <AlertTriangle className="w-4 h-4 flex-shrink-0" style={{ marginTop: 2 }} />
            <span>
              عمليّة مُتلِفة: تُنشئ حقولاً جديدة ثمّ تحذف الأصول. يُفحَص الموسم النشط مسبقاً، ويُحظَر الحذف إن وُجد.
            </span>
          </div>

          {arealFields.length < (mode === 'merge' ? 2 : 1) ? (
            <Card pad={12}>
              <div style={{ color: T.muted, fontSize: 13 }}>
                {mode === 'merge'
                  ? 'يلزم حقلان ذوا حدود مرسومة على الأقلّ للدمج.'
                  : 'يلزم حقل واحد ذو حدود مرسومة على الأقلّ للتقسيم.'}
              </div>
            </Card>
          ) : mode === 'merge' ? (
            <div className="grid grid-cols-1 md:grid-cols-[280px_1fr] gap-3">
              {/* اختيار متعدّد للحقول */}
              <Card pad={12}>
                <SectionLabel action={<Badge tone="ok">{mergeIds.length} مختار</Badge>}>الحقول للدمج</SectionLabel>
                <div className="space-y-1 overflow-auto" style={{ maxHeight: '40vh' }}>
                  {arealFields.map((f) => {
                    const checked = mergeIds.includes(f.id);
                    return (
                      <label
                        key={f.id}
                        className="flex items-center gap-2 px-2 py-1.5 rounded-lg cursor-pointer"
                        style={{ background: checked ? T.greenSoft : T.card2, border: `1px solid ${checked ? T.green : T.line}` }}
                      >
                        <input type="checkbox" checked={checked} onChange={() => toggleMergeId(f.id)} disabled={busy} />
                        <span style={{ fontSize: 13, color: T.ink, fontWeight: 600 }}>{f.name}</span>
                        <span style={{ marginInlineStart: 'auto', fontSize: 11, color: T.muted }}>{fmtArea(f.geometry)}</span>
                      </label>
                    );
                  })}
                </div>
                <div style={{ marginTop: 10 }}>
                  <label style={{ fontSize: 12, color: T.muted, fontWeight: 600 }}>اسم الحقل المدموج</label>
                  <input
                    value={mergeName} onChange={(e) => setMergeName(e.target.value)} disabled={busy}
                    placeholder="اسم الحقل الناتج…"
                    style={{ width: '100%', marginTop: 4, padding: '6px 10px', borderRadius: RADIUS.sm, border: `1px solid ${T.line}`, background: T.card, color: T.ink, fontSize: 13, fontFamily: 'inherit' }}
                  />
                </div>
                {mergePreview && !mergeIsMulti && (
                  <div style={{ marginTop: 8 }}>
                    <Pill tone="info">مساحة الناتج: {fmtArea(mergePreview)}</Pill>
                  </div>
                )}
                {mergeIsMulti && (
                  <div className="flex items-start gap-2" style={{ marginTop: 8, color: T.danger, fontSize: 12 }}>
                    <AlertTriangle className="w-4 h-4 flex-shrink-0" style={{ marginTop: 1 }} />
                    <span>الحقول المختارة غير متجاورة (ناتج متعدّد الأجزاء) — الخادم لا يقبله. اختَر حقولاً متلاصقة.</span>
                  </div>
                )}
              </Card>

              {/* معاينة على الخريطة */}
              <PreviewMap
                fields={arealFields.filter((f) => mergeIds.includes(f.id))}
                resultRings={geomToLeafletRings(mergeIsMulti ? null : mergePreview)}
                resultColor="#22d3ee"
              />
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-[280px_1fr] gap-3">
              {/* اختيار حقل + أسماء الجزأين */}
              <Card pad={12}>
                <SectionLabel>الحقل للتقسيم</SectionLabel>
                <select
                  value={splitId} onChange={(e) => { setSplitId(e.target.value); setCutGeom(null); }} disabled={busy}
                  style={{ width: '100%', padding: '6px 10px', borderRadius: RADIUS.sm, border: `1px solid ${T.line}`, background: T.card, color: T.ink, fontSize: 13 }}
                >
                  <option value="">— اختَر حقلاً —</option>
                  {arealFields.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
                </select>
                <p style={{ fontSize: 12, color: T.muted, marginTop: 8, lineHeight: 1.6 }}>
                  ارسم مضلّع القصّ فوق الجزء المراد فصله من شريط الأدوات أعلى يمين الخريطة.
                </p>
                <div style={{ marginTop: 8 }}>
                  <label style={{ fontSize: 12, color: T.muted, fontWeight: 600 }}>اسم الجزء أ (داخل القصّ)</label>
                  <input
                    value={nameA} onChange={(e) => setNameA(e.target.value)} disabled={busy}
                    placeholder="اسم الجزء أ…"
                    style={{ width: '100%', marginTop: 4, padding: '6px 10px', borderRadius: RADIUS.sm, border: `1px solid ${T.line}`, background: T.card, color: T.ink, fontSize: 13, fontFamily: 'inherit' }}
                  />
                </div>
                <div style={{ marginTop: 8 }}>
                  <label style={{ fontSize: 12, color: T.muted, fontWeight: 600 }}>اسم الجزء ب (الباقي)</label>
                  <input
                    value={nameB} onChange={(e) => setNameB(e.target.value)} disabled={busy}
                    placeholder="اسم الجزء ب…"
                    style={{ width: '100%', marginTop: 4, padding: '6px 10px', borderRadius: RADIUS.sm, border: `1px solid ${T.line}`, background: T.card, color: T.ink, fontSize: 13, fontFamily: 'inherit' }}
                  />
                </div>
                {splitPreview && (
                  <div className="flex flex-col gap-1" style={{ marginTop: 8 }}>
                    <Pill tone="info">الجزء أ: {fmtArea(splitPreview.partA)}</Pill>
                    <Pill tone="info">الجزء ب: {fmtArea(splitPreview.partB)}</Pill>
                  </div>
                )}
              </Card>

              {/* خريطة الرسم + المعاينة */}
              <SplitDrawMap
                field={splitField}
                preview={splitPreview}
                onCut={setCutGeom}
              />
            </div>
          )}

          {/* أزرار التأكيد */}
          <div className="flex items-center gap-2" style={{ paddingTop: 8, borderTop: `1px solid ${T.line}` }}>
            <button
              type="button" onClick={() => { if (!busy) onClose(); }} disabled={busy}
              className="px-4 py-2 rounded-lg text-sm font-semibold"
              style={{ background: T.card2, color: T.ink, border: `1px solid ${T.line}` }}
            >
              إلغاء
            </button>
            <button
              type="button"
              onClick={mode === 'merge' ? runMerge : runSplit}
              disabled={busy}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold text-white"
              style={{ background: busy ? T.muted : '#16a34a', marginInlineStart: 'auto', cursor: busy ? 'wait' : 'pointer' }}
            >
              {busy && <Loader2 className="w-4 h-4 animate-spin" />}
              {mode === 'merge' ? 'تأكيد الدمج' : 'تأكيد التقسيم'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── خريطة معاينة (دمج): تعرض الحقول المختارة + الهندسة الناتجة ──
function PreviewMap({
  fields, resultRings, resultColor,
}: {
  fields: FieldOption[];
  resultRings: [number, number][][];
  resultColor: string;
}) {
  const points = collectFieldBoundsPoints(fields);
  if (!points.length) {
    return (
      <Card pad={12}>
        <div style={{ color: T.muted, fontSize: 13, textAlign: 'center', padding: '24px 0' }}>
          اختَر حقلين أو أكثر لمعاينة الاتّحاد.
        </div>
      </Card>
    );
  }
  return (
    <div style={{ borderRadius: RADIUS.md, overflow: 'hidden', border: `1px solid ${T.line}` }}>
      <MapContainer
        bounds={L.latLngBounds(points.map(([la, ln]) => L.latLng(la, ln)))}
        boundsOptions={{ padding: [30, 30] }}
        style={{ height: 360, width: '100%' }}
        scrollWheelZoom
      >
        <TileLayer
          url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
          attribution='&copy; <a href="https://www.esri.com/">Esri</a>'
        />
        {fields.map((f) => {
          const ring = geomToPolygon(f.geometry);
          return ring && ring.length >= 3
            ? <Polygon key={f.id} positions={ring} pathOptions={{ color: '#34d399', weight: 1.5, fillOpacity: 0.1 }} />
            : null;
        })}
        {resultRings.map((ring, i) => (
          <Polygon key={`res-${i}`} positions={ring} pathOptions={{ color: resultColor, weight: 3, fillOpacity: 0.2 }} />
        ))}
      </MapContainer>
    </div>
  );
}

// ── خريطة التقسيم: حدّ الحقل + أداة رسم القصّ + معاينة الجزأين ──
function SplitDrawMap({
  field, preview, onCut,
}: {
  field: FieldOption | undefined;
  preview: { partA: ArealGeometry; partB: ArealGeometry } | null;
  onCut: (geom: ArealGeometry | null) => void;
}) {
  if (!field) {
    return (
      <Card pad={12}>
        <div style={{ color: T.muted, fontSize: 13, textAlign: 'center', padding: '24px 0' }}>
          اختَر حقلاً لرسم مضلّع القصّ عليه.
        </div>
      </Card>
    );
  }
  const ring = geomToPolygon(field.geometry);
  const partARings = geomToLeafletRings(preview?.partA ?? null);
  const partBRings = geomToLeafletRings(preview?.partB ?? null);

  return (
    <SplitDrawInner
      key={field.id}
      fieldRing={ring}
      partARings={partARings}
      partBRings={partBRings}
      onCut={onCut}
    />
  );
}

// مكوّن داخليّ يحمل أداة الرسم (يُعاد إنشاؤه عند تبديل الحقل عبر key من الأب).
function SplitDrawInner({
  fieldRing, partARings, partBRings, onCut,
}: {
  fieldRing: [number, number][] | undefined;
  partARings: [number, number][][];
  partBRings: [number, number][][];
  onCut: (geom: ArealGeometry | null) => void;
}) {
  const points = fieldRing && fieldRing.length >= 3 ? fieldRing : null;
  // عند فقدان الحدّ لا خريطة (لا يُفترَض أن يحدث — arealFields مفروزة).
  const handleCreated = useCallback((e: L.DrawEvents.Created) => {
    onCut(layerToGeometry(e.layer));
  }, [onCut]);
  const handleDeleted = useCallback(() => onCut(null), [onCut]);

  if (!points) {
    return <Card pad={12}><LoadingState message="جارٍ تجهيز الخريطة…" /></Card>;
  }

  return (
    <div style={{ borderRadius: RADIUS.md, overflow: 'hidden', border: `1px solid ${T.line}` }}>
      <MapContainer
        bounds={L.latLngBounds(points.map(([la, ln]) => L.latLng(la, ln)))}
        boundsOptions={{ padding: [30, 30] }}
        style={{ height: 360, width: '100%' }}
        scrollWheelZoom
      >
        <TileLayer
          url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
          attribution='&copy; <a href="https://www.esri.com/">Esri</a>'
        />
        {/* حدّ الحقل الأصليّ */}
        <Polygon positions={points} pathOptions={{ color: '#34d399', weight: 2, fillOpacity: 0.08 }} />
        {/* معاينة الجزأين (إن رُسم قصّ صالح) */}
        {partARings.map((r, i) => (
          <Polygon key={`a-${i}`} positions={r} pathOptions={{ color: '#22d3ee', weight: 3, fillOpacity: 0.25 }} />
        ))}
        {partBRings.map((r, i) => (
          <Polygon key={`b-${i}`} positions={r} pathOptions={{ color: '#fbbf24', weight: 3, fillOpacity: 0.18 }} />
        ))}
        {/* أداة رسم مضلّع القصّ (مضلّع فقط) */}
        <FeatureGroup>
          <DrawControl
            position="topright"
            onCreated={handleCreated}
            onDeleted={handleDeleted}
            draw={{
              polygon: { allowIntersection: false, showArea: false, shapeOptions: { color: '#f87171' } },
              polyline: false, rectangle: { shapeOptions: { color: '#f87171' } },
              circle: false, marker: false, circlemarker: false,
            }}
            edit={{ edit: {}, remove: {} }}
          />
        </FeatureGroup>
      </MapContainer>
    </div>
  );
}
