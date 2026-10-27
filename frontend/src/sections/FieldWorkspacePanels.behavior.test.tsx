// اختبارات سلوكيّة للوحات مساحة عمل الحقل (QueryClient حقيقيّ، دوال الجلب وحدها مُثبَّتة):
//   UI-W6: بيانات مخبّأة بعد فشل إعادة جلب: تُخفى عند 401/403 وتُوسَم «قديمة» عند 503.
//   UI-W7: تبويبا التقارير/التوصيات غير المربوطين يقولان «غير مربوط» لا «لا يوجد» (فراغ غير مقيس).
//   UI-W8: عنوان المهمّة يُشتقّ من task_type الذي يعيده الخادم بترجمة صفحة المهام نفسها.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

const irrigation = vi.hoisted(() => ({ advice: vi.fn(), schedules: vi.fn() }));
const tasks = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock('../services/api/fieldIrrigation', () => ({
  getFieldIrrigationAdvice: irrigation.advice,
  getFieldIrrigationSchedules: irrigation.schedules,
}));
vi.mock('../services/api/fieldTasks', () => ({ getFieldTasks: tasks.get }));
vi.mock('./IrrigationManualOperationsPanel', () => ({ default: () => null }));
vi.mock('./IrrigationEngineeringCalculator', () => ({ default: () => null }));
vi.mock('./ReservoirBoosterNetworkCalculator', () => ({ default: () => null }));

import FieldWorkspaceIrrigationPanel from './FieldWorkspaceIrrigationPanel';
import FieldWorkspaceTasksPanel from './FieldWorkspaceTasksPanel';
import FieldWorkspaceReportsPanel from './FieldWorkspaceReportsPanel';
import FieldWorkspaceRecommendationsPanel from './FieldWorkspaceRecommendationsPanel';

const ADVICE_KEY = ['field-workspace', 'f-1', 's-1', 'irrigation-advice'];
const TASKS_KEY = ['field-workspace', 'f-1', 'tasks'];

function httpError(status: number) {
  return Object.assign(new Error(`HTTP ${status}`), { response: { status } });
}

// عميل بلا إعادة محاولة تلقائيّة (حتميّ)؛ نبذر بيانات «ناجحة» قديمة فيُعاد جلبها عند التركيب.
function withClient(seed: Array<[unknown[], unknown]>, ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  for (const [key, data] of seed) client.setQueryData(key, data, { updatedAt: Date.now() - 10 * 60_000 });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  cleanup();
  irrigation.advice.mockReset();
  irrigation.schedules.mockReset().mockResolvedValue([]);
  tasks.get.mockReset();
});

describe('UI-W6: cached advice after a failed refetch', () => {
  const CACHED = { recommended_mm: 12.5, timing_ar: 'صباح الغد', rationale_ar: 'عجز رطوبة' };

  it('hides cached advice when the refetch is 403 (revoked authorization)', async () => {
    irrigation.advice.mockRejectedValue(httpError(403));
    withClient([[ADVICE_KEY, CACHED]], <FieldWorkspaceIrrigationPanel fieldId="f-1" seasonId="s-1" />);
    expect(await screen.findByText('لا تملك صلاحية عرض بيانات الري')).toBeInTheDocument();
    expect(screen.queryByText('12.5')).not.toBeInTheDocument();
    expect(screen.queryByText('صباح الغد')).not.toBeInTheDocument();
  });

  it('marks cached advice as stale when the refetch is 503', async () => {
    irrigation.advice.mockRejectedValue(httpError(503));
    withClient([[ADVICE_KEY, CACHED]], <FieldWorkspaceIrrigationPanel fieldId="f-1" seasonId="s-1" />);
    expect(await screen.findByText('نصيحة الري يعمل في وضع متدهور')).toBeInTheDocument();
    expect(screen.getByText('12.5')).toBeInTheDocument();
    expect(screen.getByText(/بيانات قديمة غير محدَّثة/)).toBeInTheDocument();
  });

  it('fresh advice carries no stale mark', async () => {
    irrigation.advice.mockResolvedValue(CACHED);
    withClient([], <FieldWorkspaceIrrigationPanel fieldId="f-1" seasonId="s-1" />);
    expect(await screen.findByText('12.5')).toBeInTheDocument();
    expect(screen.queryByText(/بيانات قديمة غير محدَّثة/)).not.toBeInTheDocument();
  });

  it('hides cached tasks when the refetch is 403', async () => {
    tasks.get.mockRejectedValue(httpError(403));
    withClient([[TASKS_KEY, { tasks: [{ task_id: 't1', task_type: 'harvest', status: 'pending' }] }]],
      <FieldWorkspaceTasksPanel fieldId="f-1" />);
    expect(await screen.findByText('لا تملك صلاحية عرض مهام الحقل')).toBeInTheDocument();
    expect(screen.queryByRole('list')).not.toBeInTheDocument();
  });
});

describe('UI-W7: unwired reports/recommendations tabs say "not connected", not "none"', () => {
  it('reports tab does not assert an unmeasured empty result', () => {
    render(<FieldWorkspaceReportsPanel fieldId="f-1" seasonId="s-1" />);
    expect(screen.getByText('التقارير غير مربوطة بهذه الواجهة بعد')).toBeInTheDocument();
    expect(screen.queryByText('لا توجد تقارير محفوظة')).not.toBeInTheDocument();
  });

  it('recommendations tab does not assert an unmeasured empty result', () => {
    render(<FieldWorkspaceRecommendationsPanel fieldId="f-1" seasonId="s-1" />);
    expect(screen.getByText('التوصيات غير مربوطة بهذه الواجهة بعد')).toBeInTheDocument();
    expect(screen.queryByText('لا توجد توصيات موثقة')).not.toBeInTheDocument();
  });
});

describe('UI-W8: workspace task titles come from server task_type', () => {
  it('labels tasks by task_type with the main tasks page translation', async () => {
    tasks.get.mockResolvedValue({
      tasks: [
        { task_id: 't1', task_type: 'irrigation', status: 'pending' },
        { task_id: 't2', task_type: 'soil_sampling', status: 'pending' },
        { task_id: 't3', task_type: 'custom_unknown', status: 'pending' },
      ],
    });
    withClient([], <FieldWorkspaceTasksPanel fieldId="f-1" />);
    expect(await screen.findByText('ري')).toBeInTheDocument();
    expect(screen.getByText('أخذ عينات تربة')).toBeInTheDocument();
    // نوع غير معروف يُعرَض كما أعاده الخادم — لا «بدون عنوان» ولا تسمية مضلِّلة.
    expect(screen.getByText('custom_unknown')).toBeInTheDocument();
    expect(screen.queryByText('مهمة بدون عنوان محفوظ')).not.toBeInTheDocument();
  });

  it('an explicit server title still wins', async () => {
    tasks.get.mockResolvedValue({ tasks: [{ task_id: 't1', task_type: 'irrigation', title_ar: 'ريّ القطاع الشماليّ' }] });
    withClient([], <FieldWorkspaceTasksPanel fieldId="f-1" />);
    await waitFor(() => expect(screen.getByText('ريّ القطاع الشماليّ')).toBeInTheDocument());
  });
});
