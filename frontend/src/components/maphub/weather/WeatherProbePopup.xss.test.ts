// S10: نافذة قراءة الطقس تُسلَّم إلى Leaflet `setContent` (innerHTML). كلّ نصّ يأتي من
// الخادم — advice_ar · label_ar · alerts_ar · suitability · task_type · cache_state … —
// يجب أن يُعرَض نصّاً حرفيّاً لا وسماً: لا عنصر <img>/<script> يُنشأ ولا سِمة on* تُحقَن.
import { describe, expect, it } from 'vitest';
import { weatherProbeHtml } from './WeatherProbePopup';

const IMG = '<img src=x onerror="window.__pwned=1">';
const SCRIPT = '<script>window.__pwned=2</script>';
const ATTR = '" onmouseover="window.__pwned=3';

function render(html: string): HTMLDivElement {
  const host = document.createElement('div');
  host.innerHTML = html; // المصبّ نفسه الذي يستعمله Leaflet Popup.setContent
  return host;
}

describe('weatherProbeHtml — server strings render as text, never markup (S10)', () => {
  const data = {
    sample: { temperature_2m_c: IMG, wind_speed_10m_kmh: 12, precipitation_mm: SCRIPT },
    operations: { spraying: { score: 0.8, suitability: IMG }, irrigation: { score: 0.4, suitability: ATTR } },
    cache_state: SCRIPT,
    cache_age_s: 30,
  };
  const windowData = { best: { time: ATTR, operation: { score: 0.9, suitability: IMG } }, advice_ar: IMG };
  const planData = {
    operations: [{ operation: 'irrigation', label_ar: IMG, priority: 70, best: { time: SCRIPT } }],
    alerts_ar: [SCRIPT, IMG],
  };
  const actionData = { task_draft: { task_type: IMG, priority: ATTR, recommended_date: SCRIPT } };

  it('creates no injected element or event-handler attribute', () => {
    const host = render(weatherProbeHtml(data, windowData, planData, actionData, 'spraying', 'field-1'));
    expect(host.querySelectorAll('img, script')).toHaveLength(0);
    const handlers = Array.from(host.querySelectorAll('*')).flatMap((el) =>
      Array.from(el.attributes).filter((a) => a.name.startsWith('on')).map((a) => a.name),
    );
    expect(handlers).toEqual([]);
  });

  it('keeps every malicious string visible as literal text', () => {
    const text = render(weatherProbeHtml(data, windowData, planData, actionData, 'spraying', 'field-1')).textContent ?? '';
    expect(text).toContain(IMG);
    expect(text).toContain(SCRIPT);
    expect(text).toContain(ATTR);
  });

  it('still renders the action buttons the popup wires up', () => {
    const host = render(weatherProbeHtml(data, windowData, planData, actionData, 'spraying', 'field-1'));
    expect(host.querySelector('button[data-create-weather-task]')).not.toBeNull();
    expect(host.querySelector('button[data-save-weather-rec]')).not.toBeNull();
  });

  it('renders the honest placeholders when optional answers are missing', () => {
    const text = render(weatherProbeHtml({}, null, null, null, 'spraying', null)).textContent ?? '';
    expect(text).toContain('الحرارة: —°م');
    expect(text).toContain('live');
    expect(text).toContain('اختر حقلاً لتمكين إنشاء المهام من الطقس.');
  });
});
