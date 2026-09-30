// ═══════════════════════════════════════════════════════════════
// SAHOOL Weather Probe Popup
// Handles map-click agricultural weather probe, operation window, and operation plan.
// ═══════════════════════════════════════════════════════════════
import L from 'leaflet';
import {
  type WeatherLayerKey,
  type WeatherTimeKey,
  isOperationLayer,
  operationFromLayer,
} from './weatherLayerDefinitions';
import {
  WEATHER_PLAN_OPERATIONS,
  createWeatherRecommendationFromOperationPlan,
  createWeatherTaskFromOperationPlan,
  getWeatherActionRecommendation,
  getWeatherOperationPlan,
  getWeatherOperationWindow,
  getWeatherProbe,
} from '../../../services/api/weatherMap';

// شكلُ صفٍّ واحدٍ في خطّة العمليات كما يقرؤه هذا العرضُ **فقط** — أضيقُ من الردّ
// الكامل عمداً: نوعٌ يصف ما يُقرأ لا ما قد يصل، فلا يَعِد بحقلٍ لا يستعمله.
interface WeatherPlanOperation {
  operation?: string;
  label_ar?: string;
  priority?: number;
  best?: { time?: string } | null;
}

// أشكالُ الأجوبة الأربعة كما يقرؤها هذا العرضُ **فقط** — كلُّ حقلٍ اختياريّ لأنّ العرضَ
// يقصّ كلَّ غيابٍ إلى «—». كانت تصل `any` من `r.json()`؛ ونقلُها إلى طبقة الـAPI أوجب
// تسميتَها بدل أن يُضاف `any` جديدٌ إلى دَين lint.
interface WeatherProbeView {
  sample?: Record<string, unknown>;
  operations?: Record<string, { score?: number; suitability?: string } | undefined>;
  cache_state?: string;
  cache_age_s?: number | null;
}

interface WeatherWindowView {
  best?: { time?: string; operation?: { score?: number; suitability?: string } | null } | null;
  advice_ar?: string;
}

interface WeatherPlanView {
  operations?: unknown;
  alerts_ar?: string[];
}

interface WeatherActionView {
  task_draft?: {
    operation?: string;
    task_type?: string;
    priority?: string | number;
    recommended_date?: string | null;
  } | null;
}

// يستخرج سبب فشل إجراء الطقس من ردّ FastAPI ويصوغ رسالة عربيّة صادقة بدل النصّ
// المُضلِّل «تحقق من الصلاحية» لكلّ الأخطاء. 403 شائع هنا: دور المستخدم (مثلاً
// platform_admin) لا يملك field:edit/recommendation:request — وهو سلوك مقصود،
// فالرسالة توضّح الحاجة لدور مالك/مدير الحقل بدل الإيحاء بخطأ عابر.
// الطلبُ يمرّ عبر kongApi (axios)، فالردُّ غيرُ الناجح يصل خطأً يحمل `response` —
// وغيابُ `response` يعني أنّ الطلبَ لم يبلغ الخادمَ أصلاً (شبكة/مهلة/توكن منتهٍ محلّيّاً).
export function weatherActionErrorText(err: unknown, fallback: string): string | null {
  const response = (err as { response?: { status?: number; data?: unknown } } | null)?.response;
  if (!response || typeof response.status !== 'number') return null;
  const data = response.data as { detail?: unknown; message_ar?: string } | undefined;
  let detail = '';
  const d = data?.detail ?? data?.message_ar;
  if (typeof d === 'string') detail = d;
  else if (d && typeof d === 'object') detail = (d as { message_ar?: string; msg?: string }).message_ar || (d as { msg?: string }).msg || '';
  if (response.status === 401) return 'انتهت الجلسة — سجّل الدخول من جديد.';
  if (response.status === 403) return detail || 'هذا الحساب لا يملك صلاحية الإجراء — استخدم دور مالك/مدير الحقل.';
  if (response.status >= 500) return 'تعذّر الاتصال بالخادم — حاول لاحقاً.';
  return detail || fallback;
}

export function registerWeatherProbePopup(
  map: L.Map,
  layer: WeatherLayerKey,
  time: WeatherTimeKey,
  model: string,
  fieldId?: string | null,
): () => void {
  const onClick = (ev: L.LeafletMouseEvent) => {
    const { lat, lng } = ev.latlng;
    const popup = L.popup({ maxWidth: 330 })
      .setLatLng(ev.latlng)
      .setContent('<div dir="rtl" style="min-width:230px;font:13px system-ui">جاري قراءة الطقس الزراعي…</div>')
      .openOn(map);
    const selectedOperation = isOperationLayer(layer) ? operationFromLayer(layer) : 'spraying';
    Promise.all([
      getWeatherProbe<WeatherProbeView>(lat, lng, time, model),
      getWeatherOperationWindow<WeatherWindowView>(lat, lng, selectedOperation, model).catch(() => null),
      getWeatherOperationPlan<WeatherPlanView>(lat, lng, model).catch(() => null),
      fieldId ? getWeatherActionRecommendation<WeatherActionView>(lat, lng, fieldId, model).catch(() => null) : Promise.resolve(null),
    ])
      .then(([data, windowData, planData, actionData]) => {
        const s = data.sample || {};
        const ops = data.operations || {};
        const opLine = (name: string, ar: string) => {
          const o = ops[name];
          if (!o) return '';
          return `<div><b>${ar}:</b> ${Math.round((o.score ?? 0) * 100)}% · ${o.suitability}</div>`;
        };
        const best = windowData?.best;
        const bestLine = best?.operation ? `<hr/><div><b>أفضل نافذة ${selectedOperation}:</b> ${best.time} · ${Math.round((best.operation.score ?? 0) * 100)}% · ${best.operation.suitability}</div><div style="color:#475569">${windowData?.advice_ar ?? ''}</div>` : '';
        // شكلُ صفٍّ واحدٍ في خطّة العمليات كما يقرؤه هذا العرضُ **فقط**. أضيقُ من الردّ
        // الكامل عمداً، وكلُّ حقلٍ اختياريٌّ لأنّ العرضَ يقصّ كلَّ غيابٍ إلى «—» أصلاً.
        const planOps: WeatherPlanOperation[] = Array.isArray(planData?.operations)
          ? (planData.operations as WeatherPlanOperation[]).slice(0, 4)
          : [];
        const planLine = planOps.length ? `<hr/><div><b>خطة العمليات حسب الطقس</b></div>${planOps.map((item) => `<div style="display:flex;justify-content:space-between;gap:8px"><span>${item.label_ar ?? item.operation}</span><b>${item.best?.time ?? '—'} · ${item.priority ?? 0}%</b></div>`).join('')}${planData?.alerts_ar?.length ? `<div style="margin-top:5px;color:#b45309">${planData.alerts_ar.slice(0, 2).join(' · ')}</div>` : ''}` : '';
        const draft = actionData?.task_draft;
        const actionLine = draft ? `<hr/><div><b>تحويل القرار إلى مهمة</b></div><div style="font-size:12px;color:#475569">${draft.task_type} · أولوية ${draft.priority} · ${draft.recommended_date ?? '—'}</div><button type="button" data-create-weather-task="1" style="margin-top:7px;width:100%;border:0;border-radius:10px;background:#0f766e;color:white;font-weight:900;padding:8px 10px;cursor:pointer">إنشاء مهمة من أفضل نافذة</button><button type="button" data-save-weather-rec="1" style="margin-top:6px;width:100%;border:1px solid #94a3b8;border-radius:10px;background:white;color:#0f172a;font-weight:800;padding:7px 10px;cursor:pointer">حفظ كتوصية طقس</button>` : fieldId ? `<hr/><div style="color:#b45309">لا توجد مسودة مهمة موثوقة لهذه النقطة.</div>` : `<hr/><div style="color:#64748b">اختر حقلاً لتمكين إنشاء المهام من الطقس.</div>`;
        popup.setContent(`<div dir="rtl" style="min-width:285px;font:13px/1.55 system-ui;color:#0f172a">
          <b>قراءة طقس زراعية</b><br/>
          الحرارة: <b>${s.temperature_2m_c ?? '—'}°م</b><br/>
          الرياح: <b>${s.wind_speed_10m_kmh ?? '—'} كم/س</b> · اتجاه <b>${s.wind_direction_10m_deg ?? '—'}°</b><br/>
          المطر: <b>${s.precipitation_mm ?? '—'} مم</b> · VPD: <b>${s.vapour_pressure_deficit_kpa ?? '—'} kPa</b><br/>
          ET₀: <b>${s.et0_fao_evapotranspiration_mm ?? '—'} مم</b> · رطوبة التربة: <b>${s.soil_moisture_1_to_3cm_m3m3 ?? '—'}</b><hr/>
          ${opLine('spraying', 'الرش')}
          ${opLine('irrigation', 'الري')}
          ${opLine('harvesting', 'الحصاد')}
          ${opLine('sowing', 'البذار')}
          ${bestLine}
          ${planLine}
          ${actionLine}
          <hr/>
          حالة البيانات: <b>${data.cache_state ?? 'live'}</b>${data.cache_age_s ? ` · عمرها ${data.cache_age_s}ث` : ''}
        </div>`);
        const el = popup.getElement();
        const createBtn = el?.querySelector<HTMLButtonElement>('button[data-create-weather-task]');
        const taskDraft = actionData?.task_draft;
        if (createBtn && fieldId && taskDraft) {
          createBtn.onclick = async () => {
            createBtn.disabled = true;
            createBtn.textContent = 'جارٍ إنشاء المهمة…';
            try {
              const op = taskDraft.operation || selectedOperation;
              // مفتاح idempotency ثابت مُشتقّ من مدخلات الإجراء (حقل/عمليّة/إحداثيّات/نموذج/
              // تاريخ) — إعادة فتح النافذة أو المحاولة بعد مهلة تُنتِج المفتاح ذاته فيمنع
              // الخادمُ التكرار (F5-08).
              const idemKey = `wx-task:${fieldId}:${op}:${lat.toFixed(4)}:${lng.toFixed(4)}:${model}:${taskDraft.recommended_date ?? ''}`;
              await createWeatherTaskFromOperationPlan(
                { field_id: fieldId, lat, lon: lng, operation: op, model, dry_run: false },
                idemKey,
              );
              createBtn.textContent = 'تم إنشاء المهمة ✓';
              createBtn.style.background = '#16a34a';
            } catch (err) {
              createBtn.disabled = false;
              createBtn.textContent = weatherActionErrorText(err, 'تعذّر إنشاء المهمة') ?? 'تعذّر الاتصال — حاول مجدّداً';
              createBtn.style.background = '#b91c1c';
            }
          };
        }
        const recBtn = el?.querySelector<HTMLButtonElement>('button[data-save-weather-rec]');
        if (recBtn && fieldId) {
          recBtn.onclick = async () => {
            recBtn.disabled = true;
            recBtn.textContent = 'جارٍ حفظ التوصية…';
            try {
              // مفتاح idempotency ثابت (F5-08): إعادة الفتح/المحاولة لا تُنشئ توصية مكرّرة.
              const idemKey = `wx-rec:${fieldId}:${lat.toFixed(4)}:${lng.toFixed(4)}:${model}`;
              await createWeatherRecommendationFromOperationPlan(
                { field_id: fieldId, lat, lon: lng, operations: WEATHER_PLAN_OPERATIONS, model, dry_run: false },
                idemKey,
              );
              recBtn.textContent = 'تم حفظ التوصية ✓';
            } catch (err) {
              recBtn.disabled = false;
              recBtn.textContent = weatherActionErrorText(err, 'تعذّر حفظ التوصية') ?? 'تعذّر الاتصال — حاول مجدّداً';
            }
          };
        }
      })
      .catch(() => { popup.setContent('<div dir="rtl">تعذر جلب قراءة Open‑Meteo لهذه النقطة.</div>'); });
  };
  map.on('click', onClick);
  return () => { map.off('click', onClick); };
}
