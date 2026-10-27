// ═══════════════════════════════════════════════════════════════
// ألوان شدّة مناطق شبكة المؤشّر (indicator-grid zones) — مصدر واحد للدلالة.
// ───────────────────────────────────────────────────────────────
// `severity` في استجابة raster-service هي **شدّة المشكلة** لا كمّيّة المؤشّر:
// indicator_grid.classify_zones يعطي high للقيمة المنخفضة في المؤشّرات النباتيّة/الرطوبة
// (NDMI < 0 ⇒ high، ≥ 0.3 ⇒ low) وللقيمة العالية في الملوحة. فالتلوين يتبع الشدّة
// وحدها: high = أحمر (خطر)، medium = كهرمانيّ، low = أخضر (سليم) — مهما كان المؤشّر.
// شدّة غير معروفة ⇒ لون محايد، لا لون «سليم» مُختلَق.
// ═══════════════════════════════════════════════════════════════

export type GridSeverity = 'low' | 'medium' | 'high';

export const GRID_SEVERITY_COLOR: Readonly<Record<GridSeverity, string>> = {
  high: '#dc2626',
  medium: '#ca8a04',
  low: '#16a34a',
};

const NEUTRAL = '#64748b';

export function gridSeverityColor(severity: string | null | undefined): string {
  if (severity === 'high' || severity === 'medium' || severity === 'low') {
    return GRID_SEVERITY_COLOR[severity];
  }
  return NEUTRAL;
}
