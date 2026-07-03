import type { FieldImageryDateOption } from '../services/api';
import { evaluateFieldViewGovernance } from './fieldViewGovernance';

export type FieldViewActionTone = 'ok' | 'info' | 'warn' | 'critical';
export type FieldViewActionKind = 'imagery' | 'scouting' | 'weather' | 'operations' | 'records' | 'context' | 'governance';

export interface FieldViewActionCard {
  id: string;
  kind: FieldViewActionKind;
  tone: FieldViewActionTone;
  title: string;
  summary: string;
  cta: string;
  evidence: string;
}

export interface FieldViewActionDeckInput {
  fieldId?: string | null;
  fieldName?: string | null;
  crop?: string | null;
  areaHa?: number | null;
  imageryDates?: FieldImageryDateOption[];
  activeAlertsCount?: number;
  openTasksCount?: number;
  equipmentCount?: number;
  routeFieldIsInvalid?: boolean;
  storedFieldIsInvalid?: boolean;
  selectionReason?: string | null;
  weatherReady?: boolean;
  agentContextReady?: boolean;
}


function parseDateMs(value: string | null | undefined): number | null {
  const date = String(value ?? '').slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return null;
  const ms = Date.parse(`${date}T00:00:00Z`);
  return Number.isFinite(ms) ? ms : null;
}

export function summarizeImageryFreshness(dates: FieldImageryDateOption[] = [], nowMs = Date.now()) {
  const valid = dates
    .map((item) => ({ item, ms: parseDateMs(item.date) }))
    .filter((entry): entry is { item: FieldImageryDateOption; ms: number } => entry.ms != null)
    .sort((a, b) => b.ms - a.ms);
  const newest = valid[0] ?? null;
  const newestAgeDays = newest ? Math.max(0, Math.floor((nowMs - newest.ms) / 86_400_000)) : null;
  const readyCount = dates.filter((item) => item.has_cog).length;
  const pendingCount = Math.max(0, dates.length - readyCount);
  const lowCloudCount = dates.filter((item) => {
    const cloud = typeof item.cloud_pct === 'number' ? item.cloud_pct : (typeof item.cloud_cover === 'number' ? item.cloud_cover : null);
    return cloud != null && cloud <= 25;
  }).length;
  return { newestDate: newest?.item.date ?? null, newestAgeDays, readyCount, pendingCount, lowCloudCount, total: dates.length };
}

export function buildFieldViewActionDeck(input: FieldViewActionDeckInput, nowMs = Date.now()): FieldViewActionCard[] {
  const cards: FieldViewActionCard[] = [];
  const imagery = summarizeImageryFreshness(input.imageryDates ?? [], nowMs);
  const fieldLabel = input.fieldName || 'الحقل النشط';
  const openTasks = input.openTasksCount ?? 0;
  const alerts = input.activeAlertsCount ?? 0;
  const equipment = input.equipmentCount ?? 0;

  if (!input.fieldId) {
    cards.push({
      id: 'field-context-empty', kind: 'context', tone: 'warn', title: 'ابدأ باختيار حقل',
      summary: 'لا توجد طبقة FieldView فعالة قبل اختيار حقل من قائمة الحقول.',
      cta: 'اختر حقلاً', evidence: 'fieldId غير موجود',
    });
    return cards;
  }

  if (input.routeFieldIsInvalid || input.storedFieldIsInvalid) {
    cards.push({
      id: 'field-context-reconciled', kind: 'context', tone: 'info', title: 'تمت مطابقة سياق الحقل',
      summary: 'تم تجاوز رابط أو اختيار قديم غير صالح والانتقال إلى حقل متاح داخل حساب المستخدم.',
      cta: 'راجع الحقل النشط', evidence: `reason=${input.selectionReason ?? 'unknown'}`,
    });
  }

  const governance = evaluateFieldViewGovernance(input, nowMs);

  if (imagery.total === 0) {
    cards.push({
      id: 'imagery-backfill', kind: 'imagery', tone: 'warn', title: 'جهّز تاريخ الصور',
      summary: `${fieldLabel}: لا توجد مشاهد Sentinel جاهزة في Timeline.`,
      cta: 'تشغيل تجهيز سنتين', evidence: '0 imagery dates',
    });
  } else if ((imagery.newestAgeDays ?? 999) > 14) {
    cards.push({
      id: 'imagery-stale', kind: 'imagery', tone: 'warn', title: 'الصورة تحتاج تحديث',
      summary: `آخر صورة منذ ${imagery.newestAgeDays} يوم؛ راجع أحدث مشهد قبل القرار.`,
      cta: 'تحديث المشاهد', evidence: `newest=${imagery.newestDate}`,
    });
  } else {
    cards.push({
      id: 'imagery-ready', kind: 'imagery', tone: 'ok', title: 'صور الحقل جاهزة',
      summary: `${imagery.readyCount} مشهد جاهز و${imagery.lowCloudCount} منخفض الغيوم.`,
      cta: 'افتح Timeline', evidence: `latest=${imagery.newestDate ?? 'latest'}`,
    });
  }

  const weakGovernanceSources = governance.sources.filter((s) => s.severity === 'critical' || s.severity === 'warn');
  if (governance.score < 88 || weakGovernanceSources.length > 0) {
    const weak = weakGovernanceSources.map((s) => s.label).slice(0, 2).join('، ');
    cards.push({
      id: 'fieldview-source-governance', kind: 'governance', tone: governance.severity === 'critical' ? 'critical' : 'warn', title: 'حوكمة مصادر القرار',
      summary: `${governance.summary}${weak ? ` · الأولوية: ${weak}` : ''}`,
      cta: 'راجع الثقة', evidence: `score=${governance.score}% sources=${governance.sources.length}`,
    });
  }

  if (alerts > 0) {
    cards.push({
      id: 'scouting-alerts', kind: 'scouting', tone: alerts >= 3 ? 'critical' : 'warn', title: 'ابدأ الاستكشاف من التنبيهات',
      summary: `${alerts} تنبيه نشط مرتبط بالحقول؛ اجعل الزيارة تبدأ من المناطق الأضعف.`,
      cta: 'فتح طبقة التنبيهات', evidence: `activeAlerts=${alerts}`,
    });
  } else {
    cards.push({
      id: 'scouting-clean', kind: 'scouting', tone: 'info', title: 'خطط استكشافاً سريعاً',
      summary: 'لا توجد تنبيهات نشطة حالياً؛ استخدم NDVI/الرطوبة لتحديد أول نقطة زيارة.',
      cta: 'إضافة ملاحظة ميدانية', evidence: 'activeAlerts=0',
    });
  }

  if (openTasks > 0) {
    cards.push({
      id: 'operations-open-tasks', kind: 'operations', tone: 'info', title: 'أعمال مفتوحة',
      summary: `${openTasks} مهمة/عملية قيد المتابعة. اربط التنفيذ بالحقل النشط قبل الإغلاق.`,
      cta: 'فتح المهام', evidence: `openTasks=${openTasks}`,
    });
  } else {
    cards.push({
      id: 'operations-next-job', kind: 'operations', tone: 'info', title: 'اقترح عملية ميدانية',
      summary: 'لا توجد مهام مفتوحة؛ جهّز مهمة رش/ري/تسميد من سياق الحقل عند الحاجة.',
      cta: 'إنشاء مهمة', evidence: 'openTasks=0',
    });
  }

  const hasWeakRecords = !input.crop || input.crop === '—' || !input.areaHa || input.areaHa <= 0;
  cards.push({
    id: 'records-completeness', kind: 'records', tone: hasWeakRecords ? 'warn' : 'ok', title: hasWeakRecords ? 'أكمل سجل الحقل' : 'سجل الحقل مكتمل أساسياً',
    summary: hasWeakRecords
      ? 'المحصول أو المساحة غير مكتملة؛ هذا يضعف التقارير والتوصيات.'
      : `${input.crop} · ${Number(input.areaHa).toFixed(1)} هـ · ${equipment} أصل/معدة مرتبطة تقريبياً.`,
    cta: hasWeakRecords ? 'تحرير بيانات الحقل' : 'عرض التقرير', evidence: `crop=${input.crop ?? '—'} area=${input.areaHa ?? 0}`,
  });

  return cards.slice(0, 5);
}
