// SAHOOL — lib/escapeHtml.ts
// يهرّب قيمةً قبل إدراجها في نصّ HTML يُمرَّر إلى Leaflet (setContent / divIcon html)،
// فتلك الواجهات تُسنِد إلى innerHTML. أيّ نصّ من الخادم (advice_ar، suitability، weather_ar…)
// يصير نصّاً لا وسماً: لا <img onerror> ولا كسر سِمة بعلامة اقتباس.
// Escape any value before interpolating it into an HTML string handed to an innerHTML sink.
export function escapeHtml(value: unknown): string {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
