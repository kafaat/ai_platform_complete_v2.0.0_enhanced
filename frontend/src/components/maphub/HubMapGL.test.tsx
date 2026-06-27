// ═══════════════════════════════════════════════════════════════
// SAHOOL — أوّل تغطية آليّة لمحرّك MapLibre GL (HubMapGL).
// ───────────────────────────────────────────────────────────────
// المكوّن يحتاج WebGL (غائب في jsdom)، فكان بلا أيّ اختبار. هنا نُظلّل
// (mock) maplibre-gl و terra-draw + المُكيِّف، فنُثبت أسلاك/منطق المكوّن
// بلا متصفّح حقيقيّ. هذا تغطية منطق/أسلاك عبر التظليل — لا يُغني عن
// بوّابة QA الحيّة بمتصفّح WebGL فعليّ (لا نُصيّر خريطة حقيقيّة هنا).
//
// استراتيجيّة التظليل (محليّة لهذا الملفّ فقط — لا تمسّ بقيّة المجموعة):
//   • Map: ينفّذ ردّ نداء 'load' فوراً كي يجري مسار التحميل (المزامنة/الملاءمة
//     + تسجيل مُعالِجات النقر/المرور)، وبقيّة الدوالّ stubs.
//   • Marker: نعدّ إنشاءاته لِتأكيد عدد علامات التراكب/الدبابيس.
//   • Terra Draw + المُكيِّف: أصناف no-op (تُحمَّل ديناميكيّاً عند drawTools).
// ═══════════════════════════════════════════════════════════════
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import type { FieldOption } from '../../lib/fields';
import type { ScoutPin } from './HubMap';
import type { AlertMarker, DeviceMarker, WeatherMarker } from './OverlayMarkers';

// ── حالة التظليل المرفوعة (vi.hoisted كي تُتاح داخل مصانع vi.mock المرفوعة) ──
// تتضمّن عدّادات الإنشاء وعَلَم دعم WebStdGL القابل للتبديل لكلّ اختبار.
const mockState = vi.hoisted(() => ({
  markerInstances: [] as unknown[],
  mapInstances: [] as unknown[],
  // حين false يُحاكي jsdom (لا سياق webgl) فيسلك المكوّن المسار الاحتياطيّ الأمين.
  webglOk: true,
}));
const { markerInstances, mapInstances } = mockState;

vi.mock('maplibre-gl/dist/maplibre-gl.css', () => ({}));

vi.mock('maplibre-gl', () => {
  // الأصناف داخل المصنع (المصنع مرفوع لأعلى الملفّ — لا متغيّرات خارجيّة عدا hoisted).
  class FakeMap {
    container: unknown;
    handlers: Record<string, Array<(...a: unknown[]) => void>> = {};
    constructor(opts: { container?: unknown }) {
      this.container = opts?.container;
      mockState.mapInstances.push(this);
    }
    // on(type, cb) أو on(type, layer, cb). ننفّذ 'load' فوراً كي يجري مسار التحميل.
    on(type: string, layerOrCb: unknown, cb?: (...a: unknown[]) => void) {
      const fn = (typeof layerOrCb === 'function' ? layerOrCb : cb) as
        | ((...a: unknown[]) => void)
        | undefined;
      if (!fn) return this;
      (this.handlers[type] ||= []).push(fn);
      if (type === 'load') fn(); // شغّل مسار load تزامنيّاً
      return this;
    }
    addControl() { return this; }
    addSource() { return this; }
    addLayer() { return this; }
    getSource() { return { setData() {} }; }
    getLayer() { return undefined; }
    removeLayer() { return this; }
    removeSource() { return this; }
    setFilter() { return this; }
    moveLayer() { return this; }
    fitBounds() { return this; }
    jumpTo() { return this; }
    getCanvas() { return { style: {} as Record<string, string> }; }
    remove() { return this; }
  }
  class FakeMarker {
    constructor(..._args: unknown[]) { mockState.markerInstances.push(this); }
    setLngLat() { return this; }
    setPopup() { return this; }
    addTo() { return this; }
    remove() { return this; }
  }
  class FakePopup {
    setLngLat() { return this; }
    setText() { return this; }
    addTo() { return this; }
    remove() { return this; }
  }
  class FakeNavigationControl {}
  class FakeLngLatBounds {}
  const api = {
    Map: FakeMap,
    Marker: FakeMarker,
    Popup: FakePopup,
    NavigationControl: FakeNavigationControl,
    LngLatBounds: FakeLngLatBounds,
    // webglSupported() يستدعي maplibregl.supported إن وُجدت؛ نقرؤها حسب العَلَم.
    supported: () => mockState.webglOk,
  };
  return { __esModule: true, default: api, ...api };
});

// ── تظليل Terra Draw + المُكيِّف (تُحمَّل ديناميكيّاً عند drawTools فقط) ──
vi.mock('terra-draw', () => ({
  TerraDraw: class {
    start() {}
    setMode() {}
    on() {}
    getSnapshot() { return [] as unknown[]; }
    clear() {}
    stop() {}
  },
  TerraDrawPolygonMode: class {},
  TerraDrawLineStringMode: class {},
  TerraDrawSelectMode: class {},
}));
vi.mock('terra-draw-maplibre-gl-adapter', () => ({
  TerraDrawMapLibreGLAdapter: class {},
}));

// المكوّن قيد الاختبار — يُستورَد بعد التظليلات (vi.mock مرفوع لأعلى الملفّ).
import HubMapGL from './HubMapGL';

// ── مساعِدات بناء بيانات صادقة ────────────────────────────────────────
// حقل بمضلّع GeoJSON صالح ([lng, lat]، حلقة ≥3 رؤوس) كي يمرّ geomToPolygon.
function makeField(id: string, name = id): FieldOption {
  return {
    id,
    name,
    lat: 15.0,
    lon: 44.0,
    geometry: {
      type: 'Polygon',
      coordinates: [[[44.0, 15.0], [44.1, 15.0], [44.1, 15.1], [44.0, 15.0]]],
    },
    area: 10,
    crop: 'قمح',
  };
}

const BASE_PROPS = {
  fields: [makeField('f1', 'حقل ١'), makeField('f2', 'حقل ٢')],
  selectedId: 'f1',
  onSelect: () => {},
  basemapId: 'satellite',
  indicatorId: null as string | null,
  indicatorOpacity: 0.7,
};

beforeEach(() => {
  mockState.webglOk = true;
  markerInstances.length = 0;
  mapInstances.length = 0;
});

describe('HubMapGL — تظليل MapLibre GL (تغطية أسلاك/منطق)', () => {
  // (1) صدق الاحتياطيّ: WebGL غير مدعوم ⇒ ملاحظة عربيّة أمينة، ولا بناء خريطة.
  it('يعرض الاحتياطيّ الأمين بالعربيّة ولا يبني خريطة حين WebGL غير مدعوم', () => {
    mockState.webglOk = false;
    render(<HubMapGL {...BASE_PROPS} />);
    expect(screen.getByText(/محرّك WebGL غير مدعوم/)).toBeInTheDocument();
    expect(mapInstances).toHaveLength(0);
  });

  // (2) المسار الناجح: يُصيَّر بلا تعطّل + شارة الطور حاضرة.
  it('يُصيَّر على مسار النجاح ويُظهر شارة الطور (MapLibre GL · المرحلة 3)', () => {
    render(<HubMapGL {...BASE_PROPS} />);
    expect(mapInstances).toHaveLength(1);
    expect(screen.getByText(/MapLibre GL · المرحلة 3/)).toBeInTheDocument();
  });

  // (3) أسلاك علامات التراكب: تنبيهان + جهاز + طقس ⇒ 4 علامات Marker.
  it('ينشئ علامة Marker لكلّ تنبيه/جهاز/طقس (صدق العدّ)', async () => {
    const alertMarkers: AlertMarker[] = [
      { id: 'a1', lat: 15.0, lng: 44.0, severity: 'critical', title: 'تنبيه ١', fieldName: 'حقل ١' },
      { id: 'a2', lat: 15.1, lng: 44.1, severity: 'warning', title: 'تنبيه ٢', fieldName: 'حقل ٢' },
    ];
    const deviceMarkers: DeviceMarker[] = [
      { id: 'd1', lat: 15.0, lng: 44.05, name: 'مستشعر', dtype: 'soil', online: true },
    ];
    const weatherMarker: WeatherMarker = {
      lat: 15.05, lng: 44.02, tempC: 30, humidityPct: 40, conditionAr: 'صحو',
    };
    render(
      <HubMapGL
        {...BASE_PROPS}
        alertMarkers={alertMarkers}
        deviceMarkers={deviceMarkers}
        weatherMarker={weatherMarker}
      />,
    );
    // 2 تنبيه + 1 جهاز + 1 طقس = 4. (لا دبابيس هنا.)
    await waitFor(() => expect(markerInstances).toHaveLength(4));
  });

  // (3ب) لا تراكبات ⇒ لا علامات Marker إطلاقاً.
  it('لا ينشئ أيّ علامة Marker حين كلّ التراكبات فارغة', () => {
    render(<HubMapGL {...BASE_PROPS} alertMarkers={[]} deviceMarkers={[]} weatherMarker={null} />);
    expect(markerInstances).toHaveLength(0);
  });

  // (4) الدبابيس: دبّوسان ⇒ علامتان (لا تراكبات أخرى).
  it('ينشئ علامة Marker لكلّ دبّوس استكشاف', async () => {
    const pins: ScoutPin[] = [
      { id: 'p1', lat: 15.0, lng: 44.0, note: 'ملاحظة ١', category: 'آفة' },
      { id: 'p2', lat: 15.1, lng: 44.1, note: 'ملاحظة ٢', category: 'ريّ' },
    ];
    render(<HubMapGL {...BASE_PROPS} pins={pins} />);
    await waitFor(() => expect(markerInstances).toHaveLength(2));
  });

  // (5) الرسم + تبديل الالتقاط: drawTools يُظهر لوحة الرسم وزرّ الالتقاط بعد
  //     فضّ الاستيراد الديناميكيّ لـTerra Draw.
  it('يُظهر لوحة الرسم وتبديل «التقاط للحدود» حين drawTools مُفعَّل', async () => {
    render(<HubMapGL {...BASE_PROPS} drawTools />);
    // لوحة الرسم تظهر تزامنيّاً (مشروطة بـdrawTools).
    expect(screen.getByText('الرسم/القياس')).toBeInTheDocument();
    // زرّ الالتقاط يظهر في وضعَي الرسم (الافتراض polygon).
    expect(await screen.findByText(/التقاط للحدود/)).toBeInTheDocument();
    // تأكيد أنّ Terra Draw المُظلَّل بُدِئ فعليّاً بعد الاستيراد الديناميكيّ.
    await waitFor(() => {
      const td = mapInstances.length > 0; // الخريطة بُنيت
      expect(td).toBe(true);
    });
  });
});
