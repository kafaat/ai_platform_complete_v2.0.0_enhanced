// W4 — «النافذة الحرجة القادمة» تبلغ المزارع.
//
// الفجوةُ المقيسة قبل هذه الشريحة: `assemble_field_season_state` يُخرِج **٢٩ مفتاحاً**
// وعقدُ الواجهة يُعرِّف **٢٣**؛ و`critical_window` و`critical_window_collisions` غائبان
// عن كلّ ملفّ واجهة. والخُطّافُ `useFieldSeasonState` كان **يجلبهما فعلاً** — فالعطلُ
// في العقد والعرض لا في الجلب، وهو صنفُ #935 نفسُه في طبقةٍ أخرى.
//
// ولذلك تشهد هذه الاختبارات على **البطاقة المُصيَّرة** لا على النوع: نوعٌ مضافٌ بلا
// عرضٍ يمرّ `tsc` أخضرَ والمزارعُ لا يرى شيئاً.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import SeasonEvidenceCard from './SeasonEvidenceCard';
import type {
  CriticalWindow,
  CriticalWindowCollisions,
  FieldSeasonState,
} from '../../lib/fieldSeasonState';

const useFieldSeasonState = vi.hoisted(() => vi.fn());
vi.mock('../../hooks/useFieldSeasonState', () => ({ useFieldSeasonState }));

function window_(over: Partial<CriticalWindow> = {}): CriticalWindow {
  return {
    status: 'upcoming',
    stage: 'flowering',
    name_ar: 'التزهير',
    start_date: '2026-09-05',
    end_date: '2026-09-12',
    lead_days: 10,
    source: 'gdd_forecast',
    confidence: 'medium',
    evidence_missing: [],
    note_ar: null,
    ...over,
  };
}

function collisions(over: Partial<CriticalWindowCollisions> = {}): CriticalWindowCollisions {
  return {
    window: window_(),
    status: 'clear',
    events: [],
    max_severity: 'none',
    requires_action: false,
    threshold_source: 'crop_card.thermal.flowering_safe_max_c',
    calibration: 'uncalibrated',
    confidence: 'medium',
    evidence_missing: [],
    note_ar: 'نفيٌ مقيس لا وعدٌ بالسلامة.',
    ...over,
  };
}

function state(over: Partial<FieldSeasonState> = {}): FieldSeasonState {
  return {
    schema: 'field_season_state.v1',
    field_id: 'f1',
    season_id: 's1',
    crop: 'wheat',
    cultivar: null,
    current_stage: 'stem_elongation',
    current_stage_ar: 'الاستطالة',
    stage_source: 'gdd',
    days_after_sowing: 60,
    accumulated_gdd: 500,
    gdd_to_maturity: 1400,
    gdd_fraction: 0.36,
    current_kc: 1.1,
    calendar_status: 'valid',
    water_stress_factor: null,
    eo_stage_mismatch: null,
    weather_stage_risks: null,
    critical_window: window_(),
    critical_window_collisions: collisions(),
    open_operations: 0,
    season_confidence: 'medium',
    requires_review: false,
    evidence_used: [],
    evidence_missing: [],
    disclaimer_ar: 'إرشاديّ.',
    ...over,
  } as unknown as FieldSeasonState;
}

function mount(over: Partial<FieldSeasonState> = {}) {
  useFieldSeasonState.mockReturnValue({ data: state(over), isLoading: false, isError: false });
  render(<SeasonEvidenceCard fieldId="f1" seasonId="s1" />);
}

beforeEach(() => useFieldSeasonState.mockReset());

// ── ① الفجوة المقيسة: «متى» تصل المزارع ─────────────────────────────
describe('النافذة الحرجة تبلغ الواجهة', () => {
  it('نافذةٌ قادمة ⇒ تُعرَض بمهلتها واسمها ومداها', () => {
    mount();

    expect(screen.getByText('النافذة الحرجة القادمة')).toBeInTheDocument();
    expect(screen.getByText('قادمة')).toBeInTheDocument();
    expect(screen.getByText(/بعد\s*10\s*يوماً/)).toBeInTheDocument();
    expect(screen.getByText('التزهير')).toBeInTheDocument();
    expect(screen.getByText(/2026-09-05/)).toBeInTheDocument();
  });

  it('الحقلُ داخلها الآن ⇒ مفردةٌ مختلفة عن «قادمة»', () => {
    mount({ critical_window: window_({ status: 'in_window', lead_days: null }) });

    expect(screen.getByText('الحقل داخلها الآن')).toBeInTheDocument();
    expect(screen.queryByText('قادمة')).not.toBeInTheDocument();
  });

  it('سياقٌ ناقص ⇒ يُقال صراحةً ولا يُختلَق إسقاط', () => {
    mount({
      critical_window: window_({
        status: 'insufficient_context',
        stage: null,
        name_ar: null,
        start_date: null,
        end_date: null,
        lead_days: null,
        note_ar: 'لا تنبّؤ حراريّ ⇒ لا إسقاط.',
      }),
      critical_window_collisions: null,
    });

    expect(screen.getByText('لا إسقاط — سياق ناقص')).toBeInTheDocument();
    expect(screen.getByText('لا تنبّؤ حراريّ ⇒ لا إسقاط.')).toBeInTheDocument();
    expect(screen.queryByText(/بعد\s*\d+\s*يوماً/)).not.toBeInTheDocument();
  });

  it('غيابُ النافذة كلّها ⇒ لا حالةَ ولا تصادمَ يُعرَض، والبطاقةُ قائمة', () => {
    // ضبطٌ يقيس فعلاً: تأكيدُ وجود العنوان وحده يمرّ في كلّ الأحوال — فيمرّ حتّى
    // لو تعطّل المُنشئ. فالمقيسُ هنا **غيابُ** كلّ مفردةٍ من مفردات الحالتين.
    mount({ critical_window: null, critical_window_collisions: null });

    expect(screen.getByText('النافذة الحرجة القادمة')).toBeInTheDocument();
    for (const label of ['قادمة', 'الحقل داخلها الآن', 'انقضت حراريّاً', 'لا إسقاط — سياق ناقص']) {
      expect(screen.queryByText(label)).not.toBeInTheDocument();
    }
    expect(screen.queryByText('تصادمٌ داخل النافذة')).not.toBeInTheDocument();
    expect(screen.queryByText(/flowering_safe_max_c/)).not.toBeInTheDocument();
  });
});

// ── ② التصادمُ الموقوت — لا «إنذار طقس» ─────────────────────────────
describe('التصادم داخل النافذة', () => {
  it('تجاوزُ العتبة ⇒ يُعرَض بسببه المنطوق لا بكوده', () => {
    mount({
      critical_window_collisions: collisions({
        status: 'collisions',
        max_severity: 'high',
        requires_action: true,
        events: [
          {
            code: 'heat_during_critical_window',
            severity: 'high',
            lead_days: 10,
            date: '2026-09-06',
            measured_tmax_c: 38,
            threshold_c: 32,
            exceedance_c: 6,
            reason_ar: 'حرارةٌ متوقَّعة 38°م تتجاوز عتبة التزهير 32°م بعد 10 يوماً.',
          },
        ],
      }),
    });

    expect(screen.getByText('تجاوزٌ للعتبة ⚠')).toBeInTheDocument();
    expect(
      screen.getByText('حرارةٌ متوقَّعة 38°م تتجاوز عتبة التزهير 32°م بعد 10 يوماً.'),
    ).toBeInTheDocument();
  });

  it('لا تجاوز ⇒ نفيٌ مقيس، لا صمتٌ يُقرأ سلامةً', () => {
    mount();

    expect(screen.getByText('لا تجاوز ضمن الأفق المتاح')).toBeInTheDocument();
  });

  it('لا تنبّؤ يوميّ ⇒ «لا يُقاس ولا يُنفى» — تُميَّز عن clear', () => {
    mount({
      critical_window_collisions: collisions({
        status: 'insufficient_context',
        evidence_missing: ['forecast_daily_missing'],
        confidence: 'low',
      }),
    });

    expect(screen.getByText('لا تنبّؤ يوميّ — لا يُقاس ولا يُنفى')).toBeInTheDocument();
    expect(screen.queryByText('لا تجاوز ضمن الأفق المتاح')).not.toBeInTheDocument();
    expect(screen.getByText('forecast_daily_missing')).toBeInTheDocument();
  });
});

// ── ③ العتبةُ لا تحجب قراراً وهي صامتةٌ عن نفسها ─────────────────────
describe('العتبة تُعلِن مصدرَها وحالة معايرتها', () => {
  it('مصدرُ العتبة وحالتُها «غير مُعايَرة» يبلغان القارئ', () => {
    mount();

    expect(screen.getByText(/crop_card\.thermal\.flowering_safe_max_c/)).toBeInTheDocument();
    expect(screen.getByText(/غير مُعايَرة محلّيّاً/)).toBeInTheDocument();
  });

  it('ولا تُترجَم «uncalibrated» إلى صمت حين تتغيّر إلى حالةٍ أخرى', () => {
    mount({ critical_window_collisions: collisions({ calibration: 'calibrated_local' }) });

    expect(screen.getByText(/calibrated_local/)).toBeInTheDocument();
    expect(screen.queryByText(/غير مُعايَرة محلّيّاً/)).not.toBeInTheDocument();
  });
});
