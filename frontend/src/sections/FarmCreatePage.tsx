// ═══════════════════════════════════════════════════════════════
// SAHOOL — FarmCreatePage (ربط حيّ بـ POST /api/v1/farms) — مكسوّة DS + تأهيل
// شاشة «إنشاء مزرعة»: ترحيب ودود → نموذج إنشاء (DS) → خطوة تالية «أضِف حقلاً».
// تُستخدم مستقلّةً وكبوّابة تأهيل إجباريّة (App.tsx): مستخدم جديد بلا مزرعة
// يُجبَر على إنشاء واحدة قبل بلوغ اللوحة. لا تلفيق — الخطأ يُعرَض من detail ردّ
// الخادم (apiErrorMessage). 503 عند تعطيل قاعدة البيانات. منطق الإنشاء (useCreateFarm
// + payload + onCreated) محفوظ كما هو — التغيير عرضيّ/تأهيليّ فقط (لا تغيير مسارات).
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import { Leaf, Sprout, AlertTriangle, CheckCircle2, MapPin, ArrowLeft } from 'lucide-react';
import { useCreateFarm } from '../hooks/useApi';
import { apiErrorMessage, type FarmCreateInput, type FarmUnits } from '../services/api';
import { Card, Button, Pill } from '../components/ds/atoms';
import { Input, Select, Textarea } from '../components/ds/forms';
import { T } from '../components/ds/tokens';

// قائمة الدول (الافتراضيّة اليمن — سوق الإطلاق). «أخرى» تتيح أيّ دولة لاحقاً.
const COUNTRIES = ['اليمن', 'السعودية', 'الإمارات', 'عُمان', 'مصر', 'الأردن', 'أخرى'] as const;

// نوع النشاط الزراعيّ — يضبط القوالب/التوصيات لاحقاً.
const ACTIVITY_TYPES = ['زراعة محاصيل', 'بساتين/أشجار', 'خضروات محميّة', 'ثروة حيوانيّة', 'مختلط', 'أخرى'] as const;

interface FormState {
  name: string;
  country: string;
  region: string;
  units: FarmUnits;
  currency: string;
  activity_type: string;
  description: string;
}

// ── خطوة الترحيب: ما الذي يحدث بعد إنشاء المزرعة (يطمئن المستخدم الجديد) ──────
function WelcomeStrip() {
  const steps: { n: number; title: string; hint: string }[] = [
    { n: 1, title: 'أنشئ مزرعتك', hint: 'الاسم والموقع ونظام الوحدات' },
    { n: 2, title: 'أضِف حقلاً', hint: 'ارسم حدوده على الخريطة' },
    { n: 3, title: 'تابِع بياناتك', hint: 'الأقمار والتنبيهات والتوصيات' },
  ];
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 10 }}>
      {steps.map((s, i) => (
        <Card key={s.n} pad={12} style={{ background: i === 0 ? T.greenSoft : T.card2, position: 'relative' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <span
              style={{
                width: 22, height: 22, borderRadius: 999, flexShrink: 0,
                background: i === 0 ? T.green : T.line,
                color: i === 0 ? '#fff' : T.muted,
                fontSize: 12, fontWeight: 800,
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              }}
            >
              {s.n}
            </span>
            <span style={{ fontSize: 13, fontWeight: 700, color: T.ink }}>{s.title}</span>
          </div>
          <p style={{ fontSize: 11, color: T.muted, marginInlineStart: 30 }}>{s.hint}</p>
        </Card>
      ))}
    </div>
  );
}

// ── شاشة النجاح: مزرعة أُنشئت → ادعُ المستخدم لإضافة أوّل حقل ──────────────────
function CreatedNext({ farmName, onContinue }: { farmName: string; onContinue?: () => void }) {
  return (
    <Card style={{ background: T.greenSoft, borderColor: T.green }}>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', gap: 12, padding: '12px 8px' }}>
        <div
          style={{
            width: 56, height: 56, borderRadius: 999, background: T.green,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
        >
          <CheckCircle2 style={{ width: 30, height: 30, color: '#fff' }} aria-hidden="true" />
        </div>
        <div>
          <h3 style={{ fontSize: 18, fontWeight: 800, color: T.ink }}>تهانينا! أُنشئت مزرعتك</h3>
          <p style={{ fontSize: 14, color: T.brownSoft, marginTop: 4 }}>
            «{farmName}» جاهزة الآن. الخطوة التالية: أضِف أوّل حقل لتبدأ المتابعة.
          </p>
        </div>
        <Pill tone="ok" icon={<MapPin style={{ width: 13, height: 13 }} />}>
          الخطوة 2 من 3 — إضافة حقل
        </Pill>
        {onContinue && (
          <Button full={false} onClick={onContinue} style={{ padding: '11px 22px' }}>
            <Sprout style={{ width: 16, height: 16 }} /> التالي: أضِف حقلاً
            <ArrowLeft style={{ width: 16, height: 16 }} />
          </Button>
        )}
      </div>
    </Card>
  );
}

export default function FarmCreatePage({ onCreated }: { onCreated?: () => void } = {}) {
  const mut = useCreateFarm();
  const [f, setF] = useState<FormState>({
    name: '',
    country: 'اليمن',
    region: '',
    units: 'metric',
    currency: '',
    activity_type: '',
    description: '',
  });
  // بعد نجاح الإنشاء نعرض شاشة «الخطوة التالية» بدل النموذج (تأهيل ودود). إن كان
  // onCreated معرّفاً (بوّابة التأهيل) فالأب قد يُحوّل فوراً — لكن نُبقي شاشة النجاح
  // كمسار صريح إن بقي المستخدم على الصفحة. createdName يحتفظ بالاسم بعد مسح النموذج.
  const [createdName, setCreatedName] = useState<string | null>(null);

  const canSubmit = f.name.trim().length > 0 && !mut.isPending;

  const onSubmit = () => {
    if (!f.name.trim()) return;
    const name = f.name.trim();
    const payload: FarmCreateInput = {
      name,
      units: f.units,
      ...(f.country.trim() ? { country: f.country.trim() } : {}),
      ...(f.region.trim() ? { region: f.region.trim() } : {}),
      ...(f.currency.trim() ? { currency: f.currency.trim() } : {}),
      ...(f.activity_type.trim() ? { activity_type: f.activity_type.trim() } : {}),
      ...(f.description.trim() ? { description: f.description.trim() } : {}),
    };
    mut.mutate(payload, {
      onSuccess: () => {
        setCreatedName(name);
        onCreated?.();
      },
    });
  };

  return (
    <div className="space-y-5 max-w-2xl mx-auto" dir="rtl">
      {/* رأس الصفحة — ترحيب */}
      <div className="flex items-center gap-3">
        <div
          style={{
            width: 44, height: 44, borderRadius: 14, flexShrink: 0,
            background: T.green, display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
        >
          <Leaf style={{ width: 22, height: 22, color: '#fff' }} aria-hidden="true" />
        </div>
        <div>
          <h2 style={{ fontSize: 20, fontWeight: 800, color: T.ink }}>
            {createdName ? 'مرحباً بك في سهول' : 'أهلاً بك — لنبدأ بإنشاء مزرعتك'}
          </h2>
          <p style={{ fontSize: 14, color: T.muted }}>
            مزرعتك هي المظلّة التي تجمع تحتها الحقول والمحاصيل والبيانات.
          </p>
        </div>
      </div>

      {/* شريط الخطوات الثلاث */}
      {!createdName && <WelcomeStrip />}

      {/* بعد النجاح: شاشة الخطوة التالية. قبله: النموذج. */}
      {createdName ? (
        <CreatedNext farmName={createdName} onContinue={onCreated} />
      ) : (
        <Card>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14 }}>
            {/* الاسم (إلزاميّ) — يمتدّ على العرض الكامل */}
            <div style={{ gridColumn: '1 / -1' }}>
              <Input
                label="اسم المزرعة"
                required
                value={f.name}
                onChange={(v) => setF((s) => ({ ...s, name: v }))}
                placeholder="مثال: مزرعة وادي سبأ"
              />
            </div>

            <Select
              label="الدولة"
              value={f.country}
              onChange={(v) => setF((s) => ({ ...s, country: v }))}
              options={COUNTRIES.map((c) => ({ value: c, label: c }))}
            />

            <Input
              label="المنطقة / المحافظة"
              value={f.region}
              onChange={(v) => setF((s) => ({ ...s, region: v }))}
              placeholder="مثال: البيضاء"
            />

            <Select<FarmUnits>
              label="نظام الوحدات"
              value={f.units}
              onChange={(v) => setF((s) => ({ ...s, units: v }))}
              options={[
                { value: 'metric', label: 'متري (هكتار، لتر، °م)' },
                { value: 'imperial', label: 'إمبراطوري (فدّان، غالون، °ف)' },
              ]}
            />

            <Input
              label="العملة"
              value={f.currency}
              onChange={(v) => setF((s) => ({ ...s, currency: v }))}
              placeholder="مثال: YER / SAR / USD"
            />

            <div style={{ gridColumn: '1 / -1' }}>
              <Select
                label="نوع النشاط"
                value={f.activity_type}
                onChange={(v) => setF((s) => ({ ...s, activity_type: v }))}
                placeholder="— اختر نوع النشاط —"
                options={ACTIVITY_TYPES.map((a) => ({ value: a, label: a }))}
              />
            </div>

            <div style={{ gridColumn: '1 / -1' }}>
              <Textarea
                label="وصف (اختياريّ)"
                value={f.description}
                onChange={(v) => setF((s) => ({ ...s, description: v }))}
                rows={3}
                placeholder="نبذة عن المزرعة: المساحة التقريبيّة، المحاصيل الرئيسيّة…"
              />
            </div>
          </div>

          {/* خطأ الخادم — يُعرَض من detail الردّ (لا رسالة مُلفَّقة) */}
          {mut.isError && (
            <p
              style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: T.danger, marginTop: 14 }}
              role="alert"
            >
              <AlertTriangle style={{ width: 16, height: 16, flexShrink: 0 }} aria-hidden="true" />
              {apiErrorMessage(mut.error, 'تعذّر إنشاء المزرعة. تحقّق من الاتصال وحاول مرّة أخرى.')}
            </p>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
            <Button full={false} onClick={onSubmit} disabled={!canSubmit} style={{ padding: '11px 24px' }}>
              <Sprout style={{ width: 16, height: 16 }} />
              {mut.isPending ? 'جارٍ الإنشاء…' : 'إنشاء المزرعة'}
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}
