import { Bug, Search, MapPin } from 'lucide-react';
import { summarizeScouting, type ScoutingIssueLite } from '../../lib/fieldScouting';
import { T } from '../ds';

interface Props {
  crop?: string | null;
  issues?: ScoutingIssueLite[];
  loading?: boolean;
  /** يبدأ تسجيل دليل ميدانيّ (دبّوس/ملاحظة على الخريطة). */
  onLogEvidence?: () => void;
}

const CAT_TONE: Record<string, string> = {
  disease: '#fca5a5',
  pest: '#fcd34d',
  weed: '#86efac',
  nutrient: '#93c5fd',
};

/** استكشاف الحقل: ماذا تفحص لهذا المحصول؟ (تصنيف حيّ) ثمّ سجّل الدليل. */
export default function FieldScoutingCard({ crop, issues = [], loading, onLogEvidence }: Props) {
  const s = summarizeScouting(crop, issues);
  return (
    <section className="mb-3 rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }} data-testid="field-scouting" aria-label="استكشاف الحقل">
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <Search className="w-4 h-4 text-emerald-300" aria-hidden="true" /> استكشاف الحقل
          {s.hasCrop && <span className="text-[11px]" style={{ color: T.faint }}>· {s.crop}</span>}
        </span>
        <button
          type="button"
          onClick={onLogEvidence}
          disabled={!onLogEvidence}
          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-semibold disabled:opacity-50"
          style={{ border: '1px solid #14532d', color: '#86efac', background: 'rgba(15,23,42,.45)' }}
        >
          <MapPin className="w-3.5 h-3.5" aria-hidden="true" /> سجّل دليلاً
        </button>
      </div>

      {!s.hasCrop ? (
        <div className="text-[11px]" style={{ color: T.muted }}>حدّد محصول الحقل لعرض ما يجب فحصه.</div>
      ) : loading ? (
        <div className="text-[11px]" style={{ color: T.faint }}>جارٍ جلب تصنيف الاستكشاف…</div>
      ) : s.total === 0 ? (
        <div className="text-[11px]" style={{ color: T.muted }}>لا مشاكل شائعة مسجَّلة لهذا المحصول في التصنيف.</div>
      ) : (
        <div className="flex flex-col gap-2">
          <div className="text-[11px]" style={{ color: T.muted }}>ابدأ الجولة من الفئات الأعلى خطورة، ثمّ سجّل ما تجده:</div>
          <div className="flex flex-wrap gap-1.5">
            {s.groups.slice(0, 4).flatMap((g) =>
              g.items.slice(0, 3).map((it) => (
                <span
                  key={it.code}
                  className="text-[11px] px-2 py-0.5 rounded-full"
                  style={{ border: `1px solid ${T.line}`, color: CAT_TONE[g.category] ?? T.ink }}
                  title={g.label}
                >
                  {it.name_ar}
                </span>
              )),
            )}
          </div>
          <div className="inline-flex items-center gap-2 text-[10px]" style={{ color: T.faint }}>
            <Bug className="w-3 h-3" aria-hidden="true" /> {s.total} مشكلة محتملة عبر {s.groups.length} فئة — الدليل الميدانيّ يربطها بتنبيه/مهمّة متابعة.
          </div>
        </div>
      )}
    </section>
  );
}
