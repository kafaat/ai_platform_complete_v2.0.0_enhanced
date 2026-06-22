// ═══════════════════════════════════════════════════════════════
// SAHOOL — تغطية تراجع/إعادة (Undo/Redo) لمحرّر حدّ الحقل — F3
// ───────────────────────────────────────────────────────────────
// مكدّس التاريخ (history/pointer + pushSnapshot/applySnapshot + handleUndo/Redo
// + handleReset) يقود التراجع/الإعادة لحدّ الحقل. jsdom بلا خريطة فعليّة، فنُظلّل
// react-leaflet/DrawControl/leaflet (نفس نهج AddFieldWithMap.workspace.test) مع
// تمكينٍ كافٍ لتشغيل المسار التفاعليّ بصدق:
//   • DrawControl المُظلَّل يلتقط onCreated فنستطيع إطلاق حدث رسم حقيقيّ.
//   • FeatureGroup المُظلَّل يُمرّر ref إلى L.FeatureGroup مُزيَّف (clearLayers/
//     addLayer) كي يعمل buildEditablePolygon (يقرأ fgRef.current).
//   • leaflet المُظلَّل يوفّر L.polygon/L.latLng بأقلّ سطح يلزمه المسار.
//
// نغطّي بصدق:
//   (أ) حدود المؤشّر: عند أوّل لقطة، «تراجع» مُعطَّل و«إعادة» مُعطَّل (لقطة واحدة).
//   (ب) رسمٌ ثانٍ يدفع لقطة ⇒ «تراجع» يصبح مُفعَّلاً؛ النقر عليه يعيد المؤشّر
//       ويعيد المساحة المعروضة إلى اللقطة السابقة، و«إعادة» يصبح مُفعَّلاً.
//   (ج) handleReset (إعادة الرسم) يفرّغ التاريخ ويعيد إلى مرحلة الرسم.
//
// ملاحظة صدق: هذا اختبار منطق/أسلاك عبر التظليل (لا متصفّح حيّ). سحب رأس فعليّ
// عبر leaflet-draw (مسار حدث 'edit' البصريّ) يبقى مُؤجَّلاً لِبوّابة QA الحيّة.
// ═══════════════════════════════════════════════════════════════
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { forwardRef, useImperativeHandle, type ReactNode } from 'react';

// ── التقاط onCreated من DrawControl المُظلَّل كي نُطلق حدث رسم حقيقيّ ──
const draw = vi.hoisted(() => ({ onCreated: null as null | ((e: unknown) => void) }));
vi.mock('./maphub/DrawControl', () => ({
  default: ({ onCreated }: { onCreated?: (e: unknown) => void }) => {
    draw.onCreated = onCreated ?? null;
    return <div data-testid="draw" />;
  },
}));

// ── FeatureGroup يُمرّر ref إلى L.FeatureGroup مُزيَّف (طبقات في الذاكرة) ──
vi.mock('react-leaflet', () => {
  const FeatureGroup = forwardRef<unknown, { children?: ReactNode }>((props, ref) => {
    useImperativeHandle(ref, () => {
      const layers: unknown[] = [];
      return {
        clearLayers() { layers.length = 0; },
        addLayer(l: unknown) { layers.push(l); },
      };
    }, []);
    return <div data-testid="fg">{props.children}</div>;
  });
  FeatureGroup.displayName = 'FeatureGroup';
  return {
    MapContainer: ({ children }: { children?: ReactNode }) => <div data-testid="map">{children}</div>,
    TileLayer: () => <div data-testid="tile" />,
    FeatureGroup,
    useMap: () => ({ invalidateSize: vi.fn() }),
  };
});

// ── leaflet مُزيَّف: L.latLng كائن {lat,lng}؛ L.polygon يحمل getLatLngs/editing/on. ──
vi.mock('leaflet', () => {
  const latLng = (lat: number, lng: number) => ({ lat, lng });
  const polygon = (pts: Array<{ lat: number; lng: number }>) => {
    const ring = pts;
    return {
      getLatLngs: () => [ring],
      editing: { enable: vi.fn() },
      on: vi.fn(), // مستمع 'edit' البصريّ — لا يُطلَق في jsdom (مُؤجَّل صراحةً)
    };
  };
  return { default: { latLng, polygon } };
});
vi.mock('../lib/leafletSetup', () => ({}));
vi.mock('shpjs', () => ({ default: vi.fn() }));

// ── ظِلّ services/api: الكشف العكسيّ (kongApi.get) اختياريّ ويُبتلَع عند الفشل؛ ──
// نُظلّله كي لا يحاول طلب شبكة فعليّ في jsdom (يبقى المسار صادقاً: لا موقع تلقائيّ).
vi.mock('../services/api', async () => {
  const actual = await vi.importActual<typeof import('../services/api')>('../services/api');
  return {
    ...actual,
    kongApi: { get: vi.fn().mockRejectedValue(new Error('no network in jsdom')) },
  };
});

import AddFieldWithMap from './AddFieldWithMap';

const noop = async () => {};

// يُطلق حدث رسم مضلّع حقيقيّ عبر onCreated الملتقَط من DrawControl المُظلَّل.
// ring: أزواج [lat,lng] (≥3) — تُغلَّف في layer.getLatLngs()[0] كما يتوقّع المكوّن.
function drawPolygon(ring: Array<[number, number]>) {
  const latlngs = ring.map(([lat, lng]) => ({ lat, lng }));
  const layer = { getLatLngs: () => [latlngs] };
  draw.onCreated?.({ layerType: 'polygon', layer });
}

const SMALL: Array<[number, number]> = [[15.0, 44.0], [15.0, 44.1], [15.1, 44.1], [15.1, 44.0]];
const LARGE: Array<[number, number]> = [[15.0, 44.0], [15.0, 44.5], [15.5, 44.5], [15.5, 44.0]];

beforeEach(() => { draw.onCreated = null; });

// يبلغ مرحلة النموذج برسم أوّليّ ثمّ يُعطّل الالتقاط (snap) لِتُحفَظ الرؤوس كما هي.
async function renderAndDrawFirst() {
  render(<AddFieldWithMap onSave={noop} onCancel={() => {}} existingFields={[]} />);
  // الالتقاط مُفعَّل افتراضيّاً؛ نُعطّله كي لا يزيح الرؤوس (مع حقول قائمة فارغة لا أثر له،
  // لكن نُبقيه صريحاً). الزرّ في درج مرحلة الرسم.
  fireEvent.click(screen.getByText(/التقاط للحدود/));
  // ارسم المضلّع الأوّل ⇒ ينتقل إلى مرحلة النموذج ويدفع اللقطة الأولى.
  drawPolygon(SMALL);
  await screen.findByRole('button', { name: /حفظ الحقل/ });
}

describe('AddFieldWithMap — تراجع/إعادة لحدّ الحقل — F3', () => {
  // (أ) لقطة واحدة ⇒ «تراجع» و«إعادة» كلاهما مُعطَّل (حدود المؤشّر).
  it('(أ) بعد رسم أوّل (لقطة واحدة): «تراجع» و«إعادة» مُعطَّلان', async () => {
    await renderAndDrawFirst();
    const undo = screen.getByRole('button', { name: /^تراجع$/ });
    const redo = screen.getByRole('button', { name: /^إعادة$/ });
    expect(undo).toBeDisabled();   // pointer === 0 ⇒ لا ما قبله
    expect(redo).toBeDisabled();   // pointer === length-1 ⇒ لا ما بعده
  });

  // (ب) رسمٌ ثانٍ يدفع لقطة ⇒ «تراجع» يُفعَّل؛ النقر عليه يعيد المساحة السابقة.
  it('(ب) رسم ثانٍ يدفع لقطة؛ «تراجع» يعيد المؤشّر والمساحة المعروضة', async () => {
    await renderAndDrawFirst();
    // المساحة المعروضة الآن للمضلّع الصغير. ارسم مضلّعاً أكبر (لقطة ثانية).
    drawPolygon(LARGE);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /^تراجع$/ })).not.toBeDisabled());
    const redo = screen.getByRole('button', { name: /^إعادة$/ });
    expect(redo).toBeDisabled(); // عند آخر لقطة لا إعادة بعد

    // المساحة المعروضة الآن للمضلّع الكبير (~3000 هكتار). نلتقطها كنصّ هكتار.
    const haText = () => screen.getByText(/هكتار/).textContent ?? '';
    const largeArea = haText();

    // تراجع ⇒ يعود للقطة الأولى (المضلّع الصغير) ⇒ تتغيّر المساحة المعروضة.
    fireEvent.click(screen.getByRole('button', { name: /^تراجع$/ }));
    await waitFor(() => expect(haText()).not.toBe(largeArea));
    // الآن «إعادة» مُفعَّل و«تراجع» مُعطَّل (عدنا لأوّل لقطة).
    expect(screen.getByRole('button', { name: /^إعادة$/ })).not.toBeDisabled();
    expect(screen.getByRole('button', { name: /^تراجع$/ })).toBeDisabled();
  });

  // (ج) handleReset (إعادة الرسم) يفرّغ التاريخ ويعيد لمرحلة الرسم.
  it('(ج) «إعادة الرسم» يفرّغ التاريخ ويعيد إلى مرحلة الرسم', async () => {
    await renderAndDrawFirst();
    fireEvent.click(screen.getByRole('button', { name: /إعادة الرسم/ }));
    // عاد لمرحلة الرسم: زرّ «حفظ الحقل» لم يعُد موجوداً، وعنوان الرسم حاضر.
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /حفظ الحقل/ })).not.toBeInTheDocument());
    expect(screen.getByRole('heading', { name: /ارسم حدود الحقل/ })).toBeInTheDocument();
  });
});
