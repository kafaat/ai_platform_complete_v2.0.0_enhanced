// ═══════════════════════════════════════════════════════════════
// SAHOOL — adapters/createDrawingAdapter.ts
// مصنع يختار محرّك الرسم عبر علَم الميزة (VITE_DRAW_ENGINE) ويُرجِع
// المُحوِّل المناسب — مع تراجع آمن إلى leaflet-draw.
// ───────────────────────────────────────────────────────────────
// إضافيّ بحت (ADR-0031 المرحلة 2): المسار الافتراضيّ = leaflet-draw. Geoman
// لا يُحمَّل إلّا عند اختياره صراحةً (ديناميّ → يبقى خارج الحزمة الافتراضيّة).
// ═══════════════════════════════════════════════════════════════
import type L from 'leaflet';

import type { DrawingAdapter } from '../drawingEvents';
import type { DrawingEngineId } from '../drawingTypes';
import { getConfiguredDrawingEngine, resolveDrawingEngine } from '../DrawingProvider';
// LeafletDrawAdapter يُحمَّل ديناميّاً داخل المصنع كي يبقى سطح هذا الموحَّد نقيّاً
// (selectDrawingEngine قابل للاستيراد في بيئة node بلا اعتماد على leaflet/window).

// pure: تطبيع الاسم المستعار 'geoman' → 'leaflet-geoman'، وإلّا فوّض إلى
// resolveDrawingEngine (الافتراضيّ 'leaflet-draw' لأيّ قيمة مجهولة).
export function selectDrawingEngine(configured?: string | null): DrawingEngineId {
  if (configured === 'geoman') return 'leaflet-geoman';
  return resolveDrawingEngine(configured);
}

export interface CreateDrawingAdapterOptions {
  // تجاوز صريح للمحرّك (يتقدّم على علَم البيئة) — مفيد للاختبار/التبنّي التدريجيّ.
  engine?: string;
}

// سطح map.pm الذي يحقنه Geoman — نتحقّق منه قبل اختيار مُحوِّل Geoman.
function hasGeoman(map: L.Map): boolean {
  return typeof (map as unknown as { pm?: unknown }).pm !== 'undefined';
}

// المصنع غير المتزامن: يحمّل مُحوِّل Geoman ديناميّاً فقط عند اختياره، كي
// يبقى @geoman-io خارج الحزمة الافتراضيّة (tree-shaken).
export async function createDrawingAdapter(
  map: L.Map,
  group: L.FeatureGroup,
  opts: CreateDrawingAdapterOptions = {},
): Promise<DrawingAdapter> {
  const engine = opts.engine ? selectDrawingEngine(opts.engine) : getConfiguredDrawingEngine();

  if (engine === 'leaflet-geoman') {
    const { LeafletGeomanAdapter } = await import('./LeafletGeomanAdapter');
    // الاستيراد يُعزّز L بـpm؛ افحص map.pm ثمّ تراجَع بأمان للافتراضيّ إن غاب.
    if (hasGeoman(map)) return new LeafletGeomanAdapter(map, group);
    const { LeafletDrawAdapter } = await import('./LeafletDrawAdapter');
    return new LeafletDrawAdapter(map, group);
  }

  // الافتراضيّ ومسار terra/maplibre (غير المُنفَّذة بعد) → leaflet-draw.
  const { LeafletDrawAdapter } = await import('./LeafletDrawAdapter');
  return new LeafletDrawAdapter(map, group);
}
