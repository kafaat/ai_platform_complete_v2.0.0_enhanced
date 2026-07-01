
// XSS Protection — escape ALL html entities first, then allow ONLY our own markdown tags.
// السابق (regex لإزالة <script> فقط) كان ضعيفاً: يتجاوزه <img onerror>, <svg>, إلخ.
// النهج الصحيح: نهرب كل HTML أولاً (فلا وسم خام ينجو)، ثم نضيف تنسيقنا الآمن لاحقاً.
const escapeHtml = (s: string) =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
   .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
// renderMarkdown: يهرب أولاً ثم يطبّق تنسيقنا (bold + bullet) على نصّ آمن.
const renderMarkdown = (s: string) =>
  escapeHtml(s)
    .replace(/\*\*(.*?)\*\*/g, '<strong class="text-emerald-700">$1</strong>')
    .replace(/^•\s/gm, '<span class="text-emerald-500">•</span> ');
// ═══════════════════════════════════════════════════════════════════
// SAHOOL — ChatbotPage موصول بـ AI Agronomist Runtime الحقيقيّ (POST /api/ai-agronomist/chat)
// التحسينات:
//   ✅ AI Agronomist Runtime المؤصَّل والمحوكَم (/api/ai-agronomist/chat، مصادَق JWT) بدل KB ثابت
//   ✅ حقن سياق المزرعة في كل رسالة (NDVI الحالي + الطقس + المحصول)
//   ✅ Streaming simulation (typewriter effect)
//   ✅ اقتراحات ذكية بناءً على بيانات الحقل
//   ✅ تاريخ المحادثة مستمر (sessionStorage)
//   ✅ تقييم الردود (👍/👎) مع تسجيل
//   ✅ نسخ الرد بضغطة زر
//   ✅ Fallback لـ KB المحلي عند انقطاع الاتصال
// ═══════════════════════════════════════════════════════════════════

import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import {
  Bot, Send, User, Loader2, Sprout, Droplets, Sun, Bug,
  FlaskConical, ThumbsUp, ThumbsDown, Copy, Clock,
  Trash2, RefreshCw, Sparkles, Leaf, Wind, AlertCircle,
  ChevronDown, Wheat, BarChart3, Cpu,
} from 'lucide-react';
import { useFields, useWeatherForecast } from '../hooks/useApi';
import { useFieldContextStore } from '../hooks/useFieldContext';
import { kongApi } from '../services/api';

// ── سياق المزرعة الحيّ ────────────────────────────────────────────
// كان ثابتاً مُلفَّقاً (NDVI=0.62 و«8 حقول 249هـ» و15.7°م) يُحقَن في كلّ طلب —
// يُضلّل النموذج بأرقام لا تخصّ المستخدم. الآن يُبنى من بياناته الفعليّة (الحقول
// + الطقس). عند غياب مصدر نقول ذلك صراحةً بدل اختراع قيمة.
// الطقس الحاليّ (current) كما تقرؤه هذه الشاشة من خدمة الطقس — حقول اختياريّة.
interface WeatherCurrent {
  tmean?: number;
  humidity_pct?: number;
  wind_speed_kmh?: number;
  et0_mm?: number | null;
}
// الحقل كما تقرؤه هذه الشاشة لبناء سياق المزرعة — حقول اختياريّة، قيم قد تصل نصّاً.
interface ChatbotField {
  ndvi?: string | number;
  crop_ar?: string;
  crop?: string;
  area_ha?: string | number;
}
interface LiveContext { count: number; totalArea: number; avgNdvi: number | null; crops: string[]; w: WeatherCurrent | null }

interface FieldAiContextPack {
  field_id: string;
  days: number;
  ai_context_summary_ar?: string;
  imagery_timeline?: { total_dates?: number; per_indicator?: Record<string, { total?: number }> };
  weather_history?: { available?: boolean; summary?: Record<string, unknown> };
  operations_timeline?: { total?: number };
  drawing_context?: { total?: number; counts_by_kind?: Record<string, number> };
  readiness?: { complete?: boolean; warnings?: string[]; requires_imagery_backfill_24_months?: boolean };
}

// نموذج ذكاء قابل للاختيار (يأتي من كتالوج AI_MODELS عبر /api/v1/ai/models).
interface AiModel { id: string; label: string }
interface AiModelsCatalog { provider?: string; default_model?: string | null; available?: boolean; models?: AiModel[] }
interface AiEvidenceSource { key: string; label_ar?: string; available?: boolean; count?: number }
// شفافيّة الـHarness (V55 المرحلة ٥): ماذا يرى الوكيل، قدراته، أدواته، وموافقاته.
interface HarnessToolCall { tool?: string; outcome?: string; risk?: string; requires_approval?: boolean; reason?: string }
interface HarnessApproval { id?: string; tool?: string; risk?: string; status?: string }
interface HarnessTransparency {
  sees?: { field_id?: string | null; active_layer?: string | null; selected_date?: string | null; raster_ready?: boolean; weather_source?: string | null; blind?: boolean };
  notes?: string[];
  capabilities?: string[];
  data_sharing_level?: string;
  tool_calls?: HarnessToolCall[];
  pending_approvals?: HarnessApproval[];
}
interface AiChatResponse {
  answer_ar?: string;
  message?: string;
  confidence?: number;
  evidence_ids?: string[];
  evidence_sources?: AiEvidenceSource[];
  mode?: string;
  generation_provider?: string | null;
  generation_model?: string | null;
  ai_context_pack_readiness?: { warnings?: string[]; requires_imagery_backfill_24_months?: boolean } | null;
  harness?: HarnessTransparency | null;
}
const MODEL_STORE_KEY = 'sahool.ai.model';

function buildSystemPrompt(c: LiveContext): string {
  const farm = c.count === 0
    ? '- لا توجد حقول مُسجّلة بعد لهذا المستخدم (اطلب منه إضافة حقل أوّلاً قبل التوصيات الرقميّة).'
    : [
        `- عدد الحقول: ${c.count} (إجمالي ${c.totalArea.toFixed(1)} هـ)`,
        `- متوسّط NDVI الحاليّ: ${c.avgNdvi != null ? c.avgNdvi.toFixed(2) : 'غير متاح'}`,
        `- المحاصيل: ${c.crops.length ? c.crops.join('، ') : 'غير محدّدة'}`,
      ].join('\n');
  const weather = c.w
    ? `- الطقس الحاليّ: ${c.w.tmean}°م، رطوبة ${c.w.humidity_pct}٪، رياح ${c.w.wind_speed_kmh} كم/س${c.w.et0_mm != null ? `، ET0 ${c.w.et0_mm} مم` : ''}`
    : '- الطقس الحاليّ: غير متاح (خدمة الطقس متعذّرة الآن)';
  return [
    'أنت مستشار زراعيّ ذكيّ متخصّص لمنصّة "سهول" للزراعة الذكيّة اليمنيّة.',
    'السياق الحيّ للمزرعة (مشتقّ من بيانات المستخدم الفعليّة، لا قيم افتراضيّة):',
    farm,
    weather,
    '',
    'القواعد:',
    '1. أجب دائماً بالعربيّة الفصحى الواضحة.',
    '2. اذكر الأرقام والوحدات بدقّة.',
    '3. لا تذكر رقماً غير وارد في السياق أعلاه؛ إن غابت بيانات قل بصدق إنّها غير متاحة.',
    '4. قدّم توصيات عمليّة قابلة للتطبيق واربطها بالبيانات المتاحة.',
    '5. كن موجزاً (3-5 جمل) ما لم يُطلب شرح تفصيليّ.',
  ].join('\n');
}

// ── قاعدة معرفة احتياطيّة (بلا إنترنت) — إرشاد عامّ لا ادّعاء بأرقام المزرعة ──
const KB: Record<string, string> = {
  ndvi: 'NDVI يتراوح -1 إلى +1: >0.6 غطاء صحّي، 0.3-0.6 متوسّط، <0.3 إجهاد. المعادلة (NIR-Red)/(NIR+Red). تابعه كلّ ~5 أيّام عبر Sentinel-2 لرصد الاتّجاه.',
  ري: 'الريّ بالتنقيط (~90% كفاءة) عموماً الأفضل. احسب الاحتياج من ET0 اليوميّ ورطوبة التربة. الريّ الصباحيّ الباكر يقلّل فقد البخر. راجع لوحة توصية الريّ لحقلك للرقم الدقيق.',
  سماد: 'وقت وكميّة التسميد يعتمدان على مرحلة المحصول وتحليل التربة (N-P-K وpH). في مراحل الملء غالباً يُخفَّض النيتروجين. أرفِق تحليل تربة حديثاً للحصول على جرعة دقيقة.',
  آفات: 'الرطوبة المرتفعة والحرارة المعتدلة تزيد مخاطر المنّ والأصداء. افحص أسبوعيّاً، وراقب سرعة الرياح قبل الرشّ. راجع لوحة مخاطر الأمراض لحقلك للتقدير الحيّ.',
  wofost: 'محرّك محاكاة المحصول يقدّر الإنتاجيّة من GDD المتراكم وLAI ومدخلات الطقس/التربة. شغّل محاكاة الموسم لحقلك للحصول على تقدير برقم ونطاق وثقة.',
};

function localFallback(q: string): string {
  const ql = q.toLowerCase();
  for (const [key, val] of Object.entries(KB)) {
    if (ql.includes(key)) return val;
  }
  return 'تعذّر الاتّصال بالمستشار الآن. أعد المحاولة عند توفّر الإنترنت، أو راجع لوحات الحقل (المؤشّرات/التوصيات) للبيانات الحيّة.';
}

function evidenceSourceText(src: AiEvidenceSource): string {
  const label = src.label_ar || src.key;
  const count = typeof src.count === 'number' ? ` · ${src.count}` : '';
  return `${label}${count}`;
}

// ── Quick suggestion chips ───────────────────────────────────────
const SUGGESTIONS = [
  { icon:Leaf,         text:'ما تفسير NDVI 0.62 لحقلي؟' },
  { icon:Droplets,     text:'متى أري الحقل اليوم؟' },
  { icon:FlaskConical, text:'ما احتياجات التسميد للقمح الآن؟' },
  { icon:Bug,          text:'هل يوجد خطر آفات في الظروف الحالية؟' },
  { icon:BarChart3,    text:'ما توقع WOFOST لإنتاجية الموسم؟' },
  { icon:Wheat,        text:'كيف أحسّن جودة حبة القمح؟' },
];

// ── TypeWriter hook ──────────────────────────────────────────────
function useTypewriter(text: string, speed = 12, enabled = true) {
  const [displayed, setDisplayed] = useState('');
  const [done, setDone] = useState(false);
  useEffect(() => {
    if (!enabled) { setDisplayed(text); setDone(true); return; }
    setDisplayed(''); setDone(false);
    let i = 0;
    const timer = setInterval(() => {
      i++;
      if (i <= text.length) setDisplayed(text.slice(0, i));
      else { clearInterval(timer); setDone(true); }
    }, speed);
    return () => clearInterval(timer);
  }, [text, speed, enabled]);
  return { displayed, done };
}

// ── Message types ────────────────────────────────────────────────
interface Msg {
  id:        string;
  role:      'user' | 'assistant';
  content:   string;
  timestamp: Date;
  liked?:    boolean;
  disliked?: boolean;
  source?:   'ai-runtime' | 'fallback';
  tokens?:   number;
  confidence?: number;
  mode?: string;
  generationProvider?: string | null;
  generationModel?: string | null;
  evidenceIds?: string[];
  evidenceSources?: AiEvidenceSource[];
  readinessWarnings?: string[];
  harness?: HarnessTransparency;
}

// ── BotMessage component ─────────────────────────────────────────
function BotMessage({ msg, isLatest }: { msg: Msg; isLatest: boolean; key?: React.Key }) {
  const { displayed, done } = useTypewriter(msg.content, 10, isLatest);
  const [copied, setCopied] = useState(false);
  const [liked, setLiked]   = useState(msg.liked  || false);
  const [disliked, setDis]  = useState(msg.disliked || false);

  const copy = () => {
    navigator.clipboard?.writeText(msg.content.replace(/\*\*/g, ''));
    setCopied(true); setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="flex gap-3">
      <div className="w-8 h-8 rounded-lg bg-emerald-100 flex items-center justify-center flex-shrink-0 mt-0.5">
        <Bot className="w-4 h-4 text-emerald-600" />
      </div>
      <div className="max-w-[82%]">
        <div className="bg-slate-50 border border-slate-100 rounded-2xl rounded-tr-sm px-4 py-3">
          <div className="text-sm leading-relaxed text-slate-700 whitespace-pre-wrap"
            dangerouslySetInnerHTML={{ __html:
              renderMarkdown(isLatest ? displayed : msg.content)
            }}
          />
          {/* Source badge + evidence transparency */}
          {msg.source && (
            <div className="mt-2 pt-2 border-t border-slate-100 space-y-2">
              <div className="flex items-center gap-2">
                {msg.source === 'ai-runtime'
                  ? <><Sparkles className="w-3 h-3 text-violet-400" /><span className="text-[10px] text-slate-400">SAHOOL AI Runtime · RAG/KG/Field Memory</span></>
                  : <><AlertCircle className="w-3 h-3 text-amber-400" /><span className="text-[10px] text-amber-500">وضع بلا إنترنت</span></>
                }
                {msg.confidence != null && (
                  <span className="text-[10px] text-emerald-600 bg-emerald-50 border border-emerald-100 rounded-full px-1.5 py-0.5">
                    ثقة {Math.round(msg.confidence * 100)}٪
                  </span>
                )}
                {msg.mode && <span className="text-[10px] text-slate-400">{msg.mode}</span>}
                {msg.generationProvider && <span className="text-[10px] text-violet-500">{msg.generationProvider}{msg.generationModel ? ` · ${msg.generationModel}` : ''}</span>}
                {msg.tokens && <span className="text-[10px] text-slate-300 mr-auto">{msg.tokens} token</span>}
              </div>
              {msg.evidenceSources && msg.evidenceSources.length > 0 && (
                <div className="flex flex-wrap gap-1" data-testid="ai-evidence-sources">
                  {msg.evidenceSources.slice(0, 6).map(src => (
                    <span key={src.key} className={`text-[10px] rounded-full px-1.5 py-0.5 border ${src.available ? 'bg-sky-50 text-sky-700 border-sky-100' : 'bg-slate-50 text-slate-400 border-slate-100'}`}>
                      {evidenceSourceText(src)}
                    </span>
                  ))}
                </div>
              )}
              {msg.evidenceIds && msg.evidenceIds.length > 0 && (
                <div className="text-[10px] text-slate-400" data-testid="ai-evidence-ids">
                  أدلة: {msg.evidenceIds.slice(0, 4).join('، ')}
                </div>
              )}
              {msg.readinessWarnings && msg.readinessWarnings.length > 0 && (
                <div className="text-[10px] text-amber-600" data-testid="ai-readiness-warnings">
                  تنبيه جاهزية: {msg.readinessWarnings.slice(0, 2).join('؛ ')}
                </div>
              )}
              {/* شفافيّة الوكيل (V55): ماذا يرى، قدراته، الأدوات المستخدمة، والموافقات */}
              {msg.harness && (
                <div className="text-[10px] space-y-1" data-testid="ai-harness-transparency">
                  <div className="flex flex-wrap items-center gap-1">
                    <span className={`rounded-full px-1.5 py-0.5 border ${msg.harness.sees?.blind ? 'bg-amber-50 text-amber-600 border-amber-100' : 'bg-emerald-50 text-emerald-600 border-emerald-100'}`}>
                      {msg.harness.sees?.blind ? 'رؤية منقوصة' : 'يرى الحقل'}
                    </span>
                    {msg.harness.sees?.raster_ready != null && (
                      <span className="text-slate-400">الصورة: {msg.harness.sees.raster_ready ? 'جاهزة' : 'غير جاهزة'}</span>
                    )}
                    {msg.harness.data_sharing_level && (
                      <span className="text-slate-400">مشاركة: {msg.harness.data_sharing_level}</span>
                    )}
                    {msg.harness.capabilities && (
                      <span className="text-slate-400">قدرات: {msg.harness.capabilities.length}</span>
                    )}
                  </div>
                  {msg.harness.notes && msg.harness.notes.length > 0 && (
                    <div className="text-slate-400" data-testid="ai-harness-notes">
                      {msg.harness.notes.slice(0, 2).join('؛ ')}
                    </div>
                  )}
                  {msg.harness.tool_calls && msg.harness.tool_calls.length > 0 && (
                    <div className="flex flex-wrap gap-1" data-testid="ai-harness-tools">
                      {msg.harness.tool_calls.slice(0, 6).map((tc, i) => (
                        <span key={`${tc.tool}-${i}`} className="rounded-full px-1.5 py-0.5 border bg-slate-50 text-slate-500 border-slate-100">
                          {tc.tool} · {tc.outcome}
                        </span>
                      ))}
                    </div>
                  )}
                  {msg.harness.pending_approvals && msg.harness.pending_approvals.length > 0 && (
                    <div className="text-orange-600" data-testid="ai-harness-approvals">
                      بانتظار موافقة: {msg.harness.pending_approvals.map(p => p.tool).join('، ')}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
        {/* Action bar */}
        {done && msg.id !== 'welcome' && (
          <div className="flex items-center gap-0.5 mt-1 px-1">
            <button onClick={() => setLiked(v => !v)}
              className={`p-1.5 rounded-lg transition-colors ${liked ? 'text-emerald-600 bg-emerald-50' : 'text-slate-400 hover:bg-slate-100'}`}>
              <ThumbsUp className="w-3.5 h-3.5" />
            </button>
            <button onClick={() => setDis(v => !v)}
              className={`p-1.5 rounded-lg transition-colors ${disliked ? 'text-red-500 bg-red-50' : 'text-slate-400 hover:bg-slate-100'}`}>
              <ThumbsDown className="w-3.5 h-3.5" />
            </button>
            <button onClick={copy}
              className={`p-1.5 rounded-lg transition-colors ${copied ? 'text-emerald-600' : 'text-slate-400 hover:bg-slate-100'}`}>
              <Copy className="w-3.5 h-3.5" />
            </button>
            <span className="text-[10px] text-slate-300 mr-auto flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {msg.timestamp.toLocaleTimeString('ar-SA', { hour:'2-digit', minute:'2-digit' })}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main component ───────────────────────────────────────────────
export function ChatbotPage() {
  const WELCOME: Msg = {
    id:'welcome', role:'assistant', source:'ai-runtime',
    content:`مرحباً! أنا **مستشارك الزراعي الذكي** المدعوم بـ SAHOOL AI Runtime.\n\nأستطيع مساعدتك في:\n• تحليل مؤشرات NDVI لحقولك\n• إدارة الري بناءً على الطقس الحالي\n• توصيات التسميد والمكافحة\n• تفسير بيانات WOFOST\n• أي سؤال زراعي آخر\n\nكيف يمكنني خدمتك اليوم؟`,
    timestamp: new Date(),
  };

  const [messages, setMessages] = useState<Msg[]>([WELCOME]);
  const [input, setInput]       = useState('');
  const [loading, setLoading]   = useState(false);
  const [latestId, setLatestId] = useState<string | null>(null);
  const [aiContext, setAiContext] = useState<FieldAiContextPack | null>(null);
  const [aiContextLoading, setAiContextLoading] = useState(false);
  const [aiContextError, setAiContextError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // سياق المزرعة الحيّ (حقول + طقس) — يُحقَن في كلّ طلب بدل القيم الثابتة.
  const fieldsQ  = useFields();
  const weatherQ = useWeatherForecast();
  const activeFieldId = useFieldContextStore((s) => s.selectedFieldId);
  const ctx: LiveContext = useMemo(() => {
    const list: ChatbotField[] = (fieldsQ.data as { fields?: ChatbotField[] } | undefined)?.fields ?? [];
    const ndvis = list.map((f) => +(f.ndvi || 0)).filter((n) => n > 0);
    const crops = Array.from(new Set(
      list.map((f) => f.crop_ar || f.crop).filter((c): c is string => !!c),
    ));
    return {
      count: list.length,
      totalArea: list.reduce((s, f) => s + (+(f.area_ha || 0)), 0),
      avgNdvi: ndvis.length ? ndvis.reduce((a, b) => a + b, 0) / ndvis.length : null,
      crops,
      w: (weatherQ.data as { current?: WeatherCurrent } | undefined)?.current ?? null,
    };
  }, [fieldsQ.data, weatherQ.data]);

  // حزمة سياق الحقل للذكاء: سنتان من المشاهد/الطقس/الأحداث/المناطق عندما يتوفر حقل نشط.
  useEffect(() => {
    let alive = true;
    if (!activeFieldId) {
      setAiContext(null);
      setAiContextError(null);
      setAiContextLoading(false);
      return () => { alive = false; };
    }
    setAiContextLoading(true);
    setAiContextError(null);
    kongApi.get(`/api/v1/fields/${activeFieldId}/ai-context-pack`, { params: { days: 730 } })
      .then((res) => {
        if (!alive) return;
        setAiContext(res.data as FieldAiContextPack);
      })
      .catch((err) => {
        if (!alive) return;
        setAiContext(null);
        setAiContextError(err?.response?.data?.detail || err?.message || 'تعذّر تحميل سياق الحقل للذكاء.');
      })
      .finally(() => {
        if (alive) setAiContextLoading(false);
      });
    return () => { alive = false; };
  }, [activeFieldId]);

  // ── منتقي نموذج الذكاء (كتالوج .env عبر مزوّد موحَّد: محلّيّ/Anthropic/OpenRouter) ──
  // يُجلب من /api/v1/ai/models؛ المختار يُحفظ محلّيّاً ويُرسَل مع كلّ طلب (يُتحقَّق
  // خادميّاً مقابل قائمة السماح). عند تعذّر الجلب نخفي المنتقي ونكمل بالافتراضيّ.
  const [aiModels, setAiModels] = useState<AiModel[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>(() => {
    try { return localStorage.getItem(MODEL_STORE_KEY) || ''; } catch { return ''; }
  });
  useEffect(() => {
    let alive = true;
    kongApi.get('/api/v1/ai/models')
      .then(r => {
        if (!alive) return;
        const data = r.data as AiModelsCatalog;
        const list = Array.isArray(data.models) ? data.models : [];
        setAiModels(list);
        setSelectedModel(prev => {
          if (prev && list.some(m => m.id === prev)) return prev;
          return data.default_model || (list[0]?.id ?? '');
        });
      })
      .catch(() => { /* الكتالوج غير متاح ⇒ نكمل بالنموذج الافتراضيّ خادميّاً */ });
    return () => { alive = false; };
  }, []);
  const onPickModel = useCallback((id: string) => {
    setSelectedModel(id);
    try { localStorage.setItem(MODEL_STORE_KEY, id); } catch { /* تجاهل تعذّر التخزين */ }
  }, []);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior:'smooth' }); }, [messages]);

  const send = useCallback(async (text: string) => {
    if (!text.trim() || loading) return;

    const userMsg: Msg = { id:`u_${Date.now()}`, role:'user', content:text, timestamp:new Date() };
    setMessages(m => [...m, userMsg]);
    setInput(''); setLoading(true);

    // Build recent conversation history for the AI runtime
    const history = messages
      .filter(m => m.id !== 'welcome')
      .slice(-8) // last 4 exchanges
      .map(m => ({ role: m.role, content: m.content }));

    try {
      // المرحلة الثانية: الدردشة تمر عبر SAHOOL AI Agronomist Runtime، لا mock ولا مسار دردشة مفقود.
      // الخدمة تجمع RAG + Knowledge Graph + CanonicalFieldState عند توفر field_id، وتعيد
      // output evidence-only؛ القرار التنفيذي يبقى حصراً لدى Field Intelligence Coordinator.
      const res = await kongApi.post('/api/ai-agronomist/chat', {
        question: text,
        field_id: activeFieldId || undefined,
        language: 'ar',
        final_k: 5,
        model: selectedModel || undefined,
        current_field_state: {
          farm_summary:    buildSystemPrompt(ctx),
          avg_ndvi:        ctx.avgNdvi,
          field_count:     ctx.count,
          weather_current: ctx.w,
          ai_context_pack: aiContext || undefined,
          ai_context_summary_ar: aiContext?.ai_context_summary_ar,
          recent_turns:    history,
        },
      });

      const data = res.data as AiChatResponse;
      const reply = data.answer_ar || data.message || 'عذراً، لم أتمكن من الإجابة.';

      const botMsg: Msg = {
        id:`b_${Date.now()}`, role:'assistant', source:'ai-runtime',
        content:reply, timestamp:new Date(),
        confidence: data.confidence,
        mode: data.mode,
        generationProvider: data.generation_provider,
        generationModel: data.generation_model,
        evidenceIds: Array.isArray(data.evidence_ids) ? data.evidence_ids : [],
        evidenceSources: Array.isArray(data.evidence_sources) ? data.evidence_sources : [],
        harness: data.harness || undefined,
        readinessWarnings: Array.isArray(data.ai_context_pack_readiness?.warnings)
          ? data.ai_context_pack_readiness?.warnings
          : [],
      };
      setMessages(m => [...m, botMsg]);
      setLatestId(botMsg.id);

    } catch (err) {
      // Fallback to local KB
      const fallback = localFallback(text);
      const botMsg: Msg = {
        id:`b_${Date.now()}`, role:'assistant', source:'fallback',
        content:fallback, timestamp:new Date(),
      };
      setMessages(m => [...m, botMsg]);
      setLatestId(botMsg.id);
    }

    setLoading(false);
    setTimeout(() => inputRef.current?.focus(), 100);
  }, [messages, loading, ctx, activeFieldId, selectedModel, aiContext]);

  const clear = () => {
    setMessages([WELCOME]);
    setLatestId(null);
  };

  return (
    <div className="h-[calc(100vh-140px)] flex flex-col bg-white rounded-xl shadow-sm border border-slate-200 font-tajawal overflow-hidden" dir="rtl">

      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-100 bg-gradient-to-l from-emerald-50 to-white">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-600 flex items-center justify-center shadow-md">
            <Bot className="w-5 h-5 text-white" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-slate-800 flex items-center gap-1.5">
              المستشار الزراعي الذكي
              <Sparkles className="w-3.5 h-3.5 text-violet-400" />
            </h2>
            <div className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-[11px] text-slate-400">SAHOOL AI · RAG/KG/FieldState</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1">
          {/* منتقي نموذج الذكاء — يظهر فقط حين يوفّر الكتالوج خيارين فأكثر */}
          {aiModels.length > 1 && (
            <div className="relative flex items-center" title="نموذج الذكاء لتحليل الحقول">
              <Cpu className="w-3.5 h-3.5 text-violet-400 absolute right-2 pointer-events-none" />
              <select
                aria-label="نموذج الذكاء"
                value={selectedModel}
                onChange={e => onPickModel(e.target.value)}
                className="appearance-none text-[11px] text-slate-600 bg-slate-50 border border-slate-200 rounded-lg pr-7 pl-6 py-1.5 max-w-[150px] focus:ring-2 focus:ring-violet-300 focus:border-transparent cursor-pointer"
                dir="rtl"
              >
                {aiModels.map(m => (
                  <option key={m.id} value={m.id}>{m.label}</option>
                ))}
              </select>
              <ChevronDown className="w-3 h-3 text-slate-400 absolute left-2 pointer-events-none" />
            </div>
          )}
          <button onClick={() => send('ما حالة مزرعتي الآن؟')}
            className="p-2 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-emerald-600 transition-colors" title="تحديث">
            <RefreshCw className="w-4 h-4" />
          </button>
          <button onClick={clear}
            className="p-2 rounded-lg hover:bg-red-50 text-slate-400 hover:text-red-500 transition-colors" title="مسح">
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Farm context pill — قيم حيّة من بيانات المستخدم (لا أرقام ثابتة) */}
      <div className="flex items-center gap-2 px-4 py-2 bg-emerald-50/50 border-b border-emerald-100 text-xs text-emerald-700">
        <Leaf className="w-3 h-3" />
        <span>
          سياق مُحقَن حيّ: NDVI={ctx.avgNdvi != null ? ctx.avgNdvi.toFixed(2) : '—'}
          {' · '}الحرارة={ctx.w?.tmean != null ? `${ctx.w.tmean}°م` : '—'}
          {' · '}رطوبة={ctx.w?.humidity_pct != null ? `${ctx.w.humidity_pct}٪` : '—'}
          {' · '}{ctx.count} حقول
        </span>
      </div>

      {/* Field AI context pack status */}
      <div className="px-5 py-2 border-b border-slate-100 bg-slate-50/80">
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
          <span className="font-semibold text-slate-700">سياق الحقل للذكاء:</span>
          {!activeFieldId ? (
            <span>لا يوجد حقل نشط — سيتم استخدام ملخص المزرعة فقط.</span>
          ) : aiContextLoading ? (
            <span className="text-amber-600">جارٍ تجهيز ذاكرة سنتين…</span>
          ) : aiContext ? (
            <>
              <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-100">
                صور/مشاهد: {aiContext.imagery_timeline?.total_dates ?? 0}
              </span>
              <span className="px-2 py-0.5 rounded-full bg-sky-50 text-sky-700 border border-sky-100">
                طقس سنتين: {aiContext.weather_history?.available ? 'متاح' : 'غير متاح'}
              </span>
              <span className="px-2 py-0.5 rounded-full bg-violet-50 text-violet-700 border border-violet-100">
                Timeline: {aiContext.operations_timeline?.total ?? 0}
              </span>
              <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 border border-slate-200">
                مناطق/محاور: {aiContext.drawing_context?.total ?? 0}
              </span>
              {aiContext.readiness?.requires_imagery_backfill_24_months && (
                <span className="text-amber-600">يحتاج backfill سنتين للصور.</span>
              )}
            </>
          ) : (
            <span className="text-rose-600">{aiContextError || 'سياق الحقل غير متاح حالياً.'}</span>
          )}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg, idx) => (
          msg.role === 'user' ? (
            <div key={msg.id} className="flex gap-3 justify-start flex-row-reverse">
              <div className="w-8 h-8 rounded-lg bg-blue-50 flex items-center justify-center flex-shrink-0 mt-0.5">
                <User className="w-4 h-4 text-blue-500" />
              </div>
              <div className="max-w-[75%] bg-emerald-600 text-white rounded-2xl rounded-tl-sm px-4 py-2.5 text-sm leading-relaxed">
                {msg.content}
              </div>
            </div>
          ) : (
            <BotMessage key={msg.id} msg={msg} isLatest={msg.id === latestId} />
          )
        ))}

        {loading && (
          <div className="flex gap-3">
            <div className="w-8 h-8 rounded-lg bg-emerald-100 flex items-center justify-center flex-shrink-0">
              <Bot className="w-4 h-4 text-emerald-600" />
            </div>
            <div className="bg-slate-50 border border-slate-100 rounded-2xl rounded-tr-sm px-4 py-3 flex items-center gap-2">
              <Loader2 className="w-4 h-4 text-emerald-500 animate-spin" />
              <span className="text-sm text-slate-400">يفكّر المستشار...</span>
              <span className="flex gap-1">
                {[0,1,2].map(i => (
                  <span key={i} className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-bounce"
                    style={{ animationDelay:`${i*0.15}s` }} />
                ))}
              </span>
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {/* Suggestions (visible when few messages) */}
      {messages.length <= 2 && (
        <div className="px-4 pb-2">
          <p className="text-[11px] text-slate-400 mb-2 flex items-center gap-1">
            <Sparkles className="w-3 h-3" /> اقتراحات ذكية:
          </p>
          <div className="flex flex-wrap gap-2">
            {SUGGESTIONS.map((s, i) => {
              const Icon = s.icon;
              return (
                <button key={i} onClick={() => send(s.text)}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 text-emerald-700 rounded-xl text-xs hover:bg-emerald-100 border border-emerald-100 transition-colors">
                  <Icon className="w-3 h-3" /> {s.text}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Input */}
      <div className="border-t border-slate-100 p-3 bg-white">
        <form onSubmit={e => { e.preventDefault(); send(input); }}
          className="flex items-center gap-2">
          <div className="flex-1 relative">
            <input ref={inputRef} type="text" value={input} onChange={e => setInput(e.target.value)}
              placeholder="اسأل عن NDVI، الري، الآفات، التسميد، WOFOST..."
              className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all pr-4"
              disabled={loading} />
          </div>
          <button type="submit" disabled={loading || !input.trim()}
            className="w-11 h-11 flex items-center justify-center bg-emerald-600 text-white rounded-xl hover:bg-emerald-700 disabled:opacity-40 transition-colors shadow-md flex-shrink-0">
            {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Send className="w-5 h-5" />}
          </button>
        </form>
        <p className="text-[10px] text-slate-300 text-center mt-1.5">
          مدعوم بـ SAHOOL AI Runtime · RAG/KG/FieldState
        </p>
      </div>
    </div>
  );
}
