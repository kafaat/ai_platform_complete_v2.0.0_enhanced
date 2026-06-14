// ═══════════════════════════════════════════════════════════════
// SAHOOL — مركز العمليّات الموحّد (Operation Command) · أوّل شاشة دمج
// ───────────────────────────────────────────────────────────────
// تصهر Dashboard (FieldView) + Home/Overview (Operations Center) في كابينة
// واحدة: صحّة الحقول + حالة المعدّات/الأجهزة + التنبيهات + عمل اليوم — موصولة
// ببيانات سهول الحقيقيّة فقط (useFields/useEquipment/useDevices/useAlerts/
// useTasks/useWeatherForecast). تستهلك لبنات الدمج (StatGrid/RadialGauge/
// AlertChip/ExpandableCard). تجسيد UI_DESIGN_SPEC_UNIFIED.md §2.
//
// صدق البيانات: لا عدّادات وقود/DEF (فجوة موثّقة ⛔ — لا تُلفَّق)؛ كلّ نسبة
// مشتقّة من قيمة حقيقيّة (NDVI، نسبة الاتّصال، نسبة الإنجاز). الحالات
// (تحميل/فراغ/خطأ) صريحة. شاشة قراءة فقط (معاينة الدمج).
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import {
  Sprout, Tractor, Cpu, Bell, Droplets, Bug, Sun, Wrench, CheckCircle2,
} from 'lucide-react';
import {
  useFields, useEquipment, useDevices, useAlerts, useTasks, useWeatherForecast,
} from '../hooks/useApi';
import {
  T, Card, Pill, Badge, ProgressBar, Row, SectionLabel,
  StatGrid, RadialGauge, AlertChip, ExpandableCard, severityTone,
  taskStatusAr, equipStatusAr, equipStatusTone, FieldCabin,
} from '../components/ds';

type FieldLike = { field_id?: string; ndvi?: number };
type AlertLike = {
  alert_id?: string; title_ar?: string | null; message_ar?: string | null;
  severity?: string | null; field_id?: string | null;
};
type EquipLike = {
  equipment_id?: string; name?: string; type?: string;
  status?: string; operating_hours?: number;
};
type DeviceLike = { device_id?: string; name?: string; online?: boolean; status?: string };
type TaskLike = {
  task_id?: string; field_name?: string; task_type?: string;
  status?: string; recommended_date?: string; priority?: number;
};

// أيقونة نوع المعدّة (مطابقة لأنواع الخادم).
function equipIcon(type?: string) {
  const s = (type ?? '').toLowerCase();
  if (s === 'tractor') return <Tractor style={{ width: 16, height: 16 }} />;
  if (s === 'pump') return <Droplets style={{ width: 16, height: 16 }} />;
  if (s === 'harvester') return <Sprout style={{ width: 16, height: 16 }} />;
  if (s === 'sprayer') return <Bug style={{ width: 16, height: 16 }} />;
  return <Wrench style={{ width: 16, height: 16 }} />;
}

export default function OperationCommand() {
  const [openEquip, setOpenEquip] = useState(false);

  const fieldsQ = useFields();
  const equipQ = useEquipment();
  const devicesQ = useDevices();
  const alertsQ = useAlerts();
  const tasksQ = useTasks();
  const weatherQ = useWeatherForecast();

  const fields: FieldLike[] = Array.isArray(fieldsQ.data?.fields) ? fieldsQ.data.fields : [];
  const equipment: EquipLike[] = Array.isArray(equipQ.data) ? equipQ.data : [];
  const devices: DeviceLike[] = Array.isArray(devicesQ.data) ? devicesQ.data : [];
  const alerts: AlertLike[] = Array.isArray(alertsQ.data) ? (alertsQ.data as AlertLike[]) : [];
  // useTasks() يُرجع { tasks: Task[] } (لا مصفوفة مجرّدة) — نقرأ المفتاح الصحيح.
  const tasks: TaskLike[] = Array.isArray(tasksQ.data?.tasks) ? (tasksQ.data.tasks as TaskLike[]) : [];
  const cur = (weatherQ.data as any)?.current;

  // ── مشتقّات حقيقيّة (لا تلفيق) ──
  const ndviVals = fields.map((f) => f.ndvi).filter((v): v is number => typeof v === 'number' && Number.isFinite(v));
  const avgNdvi = ndviVals.length ? ndviVals.reduce((a, b) => a + b, 0) / ndviVals.length : null;

  const onlineCount = devices.filter((d) => d.online).length;
  const onlinePct = devices.length ? Math.round((onlineCount / devices.length) * 100) : null;

  const doneCount = tasks.filter((t) => (t.status ?? '').toLowerCase() === 'completed').length;
  const donePct = tasks.length ? Math.round((doneCount / tasks.length) * 100) : null;
  const todayWork = tasks.filter((t) => ['pending', 'in_progress'].includes((t.status ?? '').toLowerCase()));

  const needsService = equipment.filter((e) => ['maintenance', 'broken', 'down'].includes((e.status ?? '').toLowerCase()));

  const today = new Date().toLocaleDateString('ar-SA', { weekday: 'long', day: 'numeric', month: 'long' });
  const anyLoading = fieldsQ.isLoading || equipQ.isLoading || devicesQ.isLoading || alertsQ.isLoading;

  return (
    <FieldCabin
      eyebrow="مركز العمليّات"
      title="نظرة موحّدة"
      subtitle={today}
      headerRight={
        <Pill tone="warn" icon={<Sun style={{ width: 12, height: 12 }} />}>
          {typeof cur?.tmean === 'number' ? `${Math.round(cur.tmean)}°` : '—'}
        </Pill>
      }
      note={
        <>
          مركز العمليّات الموحّد — يصهر بيانات <code>/fields</code> و<code>/equipment</code> و
          <code>/devices</code> و<code>/alerts</code> و<code>/tasks</code> الحقيقيّة. لا عدّادات وقود/DEF
          (فجوة موثّقة). الحالات صادقة.
        </>
      }
    >
      {/* ── نظرة عامّة (StatGrid) ── */}
          <Card pad={14} style={{ marginBottom: 10 }}>
            <SectionLabel action={<Badge tone={anyLoading ? 'neutral' : 'ok'}>{anyLoading ? 'تحميل…' : 'مباشر'}</Badge>}>
              نظرة العمليّة
            </SectionLabel>
            <StatGrid
              items={[
                { label: 'الحقول', value: fields.length, icon: <Sprout style={{ width: 16, height: 16, color: T.green }} /> },
                { label: 'المعدّات', value: equipment.length, icon: <Tractor style={{ width: 16, height: 16, color: T.brownSoft }} /> },
                { label: 'أجهزة متّصلة', value: devices.length ? `${onlineCount}/${devices.length}` : '—', color: T.info, icon: <Cpu style={{ width: 16, height: 16, color: T.info }} /> },
                { label: 'تنبيهات', value: alerts.length, color: alerts.length ? T.danger : T.ok, icon: <Bell style={{ width: 16, height: 16, color: alerts.length ? T.danger : T.ok }} /> },
              ]}
            />
          </Card>

          {/* ── عدّادات مشتقّة من بيانات حقيقيّة ── */}
          <Card pad={14} style={{ marginBottom: 10 }}>
            <SectionLabel>المؤشّرات</SectionLabel>
            <div className="flex" style={{ gap: 12, justifyContent: 'space-around' }}>
              <RadialGauge
                pct={avgNdvi != null ? Math.round(avgNdvi * 100) : null}
                label="متوسّط NDVI"
                color={T.green}
              />
              <RadialGauge pct={onlinePct} label="اتّصال الأجهزة" color={T.info} />
              <RadialGauge pct={donePct} label="إنجاز المهام" color={T.gold} />
            </div>
          </Card>

          {/* ── المشكلات والتنبيهات ── */}
          <Card pad={14} style={{ marginBottom: 10 }}>
            <SectionLabel
              action={<Badge tone={alerts.length ? 'danger' : 'ok'}>{alerts.length}</Badge>}
            >
              المشكلات والتنبيهات
            </SectionLabel>
            {alertsQ.isLoading ? (
              <div style={{ color: T.muted, fontSize: 12, padding: '8px 0' }}>جارٍ تحميل التنبيهات…</div>
            ) : alertsQ.isError ? (
              <div style={{ color: T.danger, fontSize: 12, padding: '8px 0' }}>تعذّر تحميل التنبيهات.</div>
            ) : alerts.length === 0 ? (
              <div className="flex items-center gap-2" style={{ color: T.ok, fontSize: 13, padding: '6px 0' }}>
                <CheckCircle2 style={{ width: 16, height: 16 }} /> لا تنبيهات — كلّ شيء سليم.
              </div>
            ) : (
              alerts.slice(0, 5).map((a, i) => {
                const tone = severityTone(a.severity);
                const type = tone === 'danger' ? 'danger' : tone === 'warn' ? 'warn' : 'info';
                return (
                  <AlertChip
                    key={a.alert_id || i}
                    type={type}
                    label={a.title_ar || a.message_ar || a.severity || 'تنبيه'}
                  />
                );
              })
            )}
          </Card>

          {/* ── عمل اليوم (مهام جارية/معلّقة) ── */}
          <Card pad={14} style={{ marginBottom: 10 }}>
            <SectionLabel action={donePct != null ? <Badge tone="ok">{donePct}%</Badge> : undefined}>
              عمل اليوم
            </SectionLabel>
            {tasksQ.isLoading ? (
              <div style={{ color: T.muted, fontSize: 12, padding: '8px 0' }}>جارٍ تحميل المهام…</div>
            ) : tasksQ.isError ? (
              <div style={{ color: T.danger, fontSize: 12, padding: '8px 0' }}>تعذّر تحميل المهام.</div>
            ) : tasks.length === 0 ? (
              <div style={{ color: T.muted, fontSize: 13, padding: '6px 0' }}>لا مهام مُسجّلة.</div>
            ) : (
              <>
                {donePct != null && (
                  <div style={{ marginBottom: 10 }}>
                    <ProgressBar value={donePct / 100} color={T.green} />
                    <div style={{ fontSize: 11, color: T.muted, marginTop: 4 }}>
                      {doneCount} من {tasks.length} مهمّة مكتملة
                    </div>
                  </div>
                )}
                {todayWork.length === 0 ? (
                  <div style={{ color: T.muted, fontSize: 13 }}>لا مهام مفتوحة اليوم.</div>
                ) : (
                  todayWork.slice(0, 5).map((t, i) => (
                    <Row
                      key={t.task_id || i}
                      label={t.task_type || 'مهمّة'}
                      value={taskStatusAr(t.status)}
                      tone={(t.status ?? '').toLowerCase() === 'in_progress' ? 'warn' : 'neutral'}
                    />
                  ))
                )}
              </>
            )}
          </Card>

          {/* ── حالة الأسطول (معدّات حقيقيّة، بلا عدّادات وقود ملفّقة) ── */}
          <ExpandableCard
            expanded={openEquip}
            onToggle={() => setOpenEquip((v) => !v)}
            header={
              <div className="flex items-center gap-2">
                <Tractor style={{ width: 16, height: 16, color: T.brownSoft }} />
                <span style={{ fontWeight: 700, fontSize: 14 }}>حالة الأسطول</span>
                <Badge tone={needsService.length ? 'warn' : 'ok'}>
                  {needsService.length ? `${needsService.length} تحتاج صيانة` : `${equipment.length} جاهزة`}
                </Badge>
              </div>
            }
          >
            {equipQ.isLoading ? (
              <div style={{ color: T.muted, fontSize: 12 }}>جارٍ تحميل المعدّات…</div>
            ) : equipQ.isError ? (
              <div style={{ color: T.danger, fontSize: 12 }}>تعذّر تحميل المعدّات.</div>
            ) : equipment.length === 0 ? (
              <div style={{ color: T.muted, fontSize: 13 }}>لا معدّات مُسجّلة.</div>
            ) : (
              equipment.map((e, i) => (
                <Row
                  key={e.equipment_id || i}
                  label={e.name || 'معدّة'}
                  value={
                    <span className="inline-flex items-center gap-2">
                      <Pill tone={equipStatusTone(e.status)}>{equipStatusAr(e.status)}</Pill>
                      {typeof e.operating_hours === 'number' && (
                        <span style={{ fontSize: 11, color: T.muted }}>{e.operating_hours} س</span>
                      )}
                    </span>
                  }
                  icon={equipIcon(e.type)}
                />
              ))
            )}
          </ExpandableCard>
    </FieldCabin>
  );
}
