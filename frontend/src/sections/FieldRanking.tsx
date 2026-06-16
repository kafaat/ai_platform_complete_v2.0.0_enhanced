// ═══════════════════════════════════════════════════════════════
// SAHOOL — ترتيب الحقول (Field Ranking) · مقارنة الحقول حسب NDVI
// ───────────────────────────────────────────────────────────────
// يرتّب كلّ الحقول حسب مؤشّر NDVI (الأفضل ← الأدنى) ويُبرز المتصدّرين
// والمتأخّرين (فجوة «مقارنة الحقول / أفضل وأدنى الحقول» في التطبيقات
// المنافسة). يجسّد الترتيب من useAllFieldsNdvi الحيّ.
//
// صدق البيانات: NDVI حقيقيّ فقط — تُستبعَد الحقول بلا قيمة عدديّة صالحة
// (لا تلفيق). الحالات (تحميل/خطأ/فراغ) صريحة. شاشة قراءة فقط.
// ═══════════════════════════════════════════════════════════════
import { useMemo } from 'react';
import { TrendingUp, Trophy, AlertTriangle, Layers, BarChart3 } from 'lucide-react';
import { useAllFieldsNdvi } from '../hooks/useApi';
import {
  T, Card, Pill, Badge, SectionLabel, StatGrid, ProgressBar, FieldCabin, ndviColor,
} from '../components/ds';

// شكل سجلّ الحقل من /v1/all_fields (vegetation-service):
//   { field_id, field_name, name, crop, area_ha, ndvi, status, health, real_data }
// ndvi قد يكون عدداً أو null (حقل بلا قراءة) — نُطبّع ونُصفّي.
interface RawField {
  field_id?: string;
  field_name?: string;
  name?: string;
  crop?: string;
  ndvi?: number | null;
}

interface RankedField {
  id: string;
  name: string;
  crop?: string;
  ndvi: number; // [0..1] صالح فقط (مُصفّى)
}

// عدد المتصدّرين/المتأخّرين المُوسَّمين (يتكيّف مع القوائم الصغيرة كي لا
// يتداخل وسما «الأفضل» و«يحتاج انتباه» على الحقل نفسه).
function markCount(total: number): number {
  if (total <= 2) return 1;
  if (total <= 6) return 2;
  return 3;
}

const fmtNdvi = (v: number) => v.toFixed(2);

export default function FieldRanking() {
  const q = useAllFieldsNdvi();

  const ranked = useMemo<RankedField[]>(() => {
    const data = q.data as { fields?: RawField[] } | undefined;
    const raw: RawField[] = Array.isArray(data?.fields) ? data.fields : [];
    const mapped: { id: string; name: string; crop?: string; ndvi: number | null | undefined }[] = raw.map((f) => ({
      id: String(f.field_id ?? ''),
      name: f.field_name || f.name || 'حقل',
      crop: f.crop,
      ndvi: f.ndvi,
    }));
    return mapped
      // صدق المصدر: نُبقي فقط القيم العدديّة الصالحة (لا null/NaN/خارج النطاق).
      .filter((f): f is RankedField =>
        typeof f.ndvi === 'number' && Number.isFinite(f.ndvi) && f.ndvi >= 0 && f.ndvi <= 1)
      .sort((a, b) => b.ndvi - a.ndvi);
  }, [q.data]);

  const summary = useMemo(() => {
    if (ranked.length === 0) return null;
    const sum = ranked.reduce((acc, f) => acc + f.ndvi, 0);
    return {
      count: ranked.length,
      avg: sum / ranked.length,
      best: ranked[0],
      worst: ranked[ranked.length - 1],
    };
  }, [ranked]);

  const mark = markCount(ranked.length);
  const topSet = useMemo(() => new Set(ranked.slice(0, mark).map((f) => f.id)), [ranked, mark]);
  const bottomSet = useMemo(() => {
    // المتأخّرون من الذيل، دون التقاط حقلٍ وُسِم متصدّراً (قوائم صغيرة).
    const s = new Set<string>();
    for (let i = ranked.length - 1; i >= 0 && s.size < mark; i--) {
      if (!topSet.has(ranked[i].id)) s.add(ranked[i].id);
    }
    return s;
  }, [ranked, mark, topSet]);

  return (
    <FieldCabin
      eyebrow="ترتيب الحقول"
      title="مقارنة الحقول"
      subtitle="ترتيب الحقول حسب NDVI — الأفضل والأدنى أداءً"
      headerRight={
        <Pill tone="info" icon={<TrendingUp style={{ width: 12, height: 12 }} />}>
          {ranked.length} حقل
        </Pill>
      }
      note={
        <>
          الترتيب من <code>/v1/all_fields</code> الحيّ — NDVI حقيقيّ فقط. الحقول بلا
          قراءة صالحة مُستبعَدة (لا تلفيق). الحالات صادقة.
        </>
      }
    >
      {/* ── الملخّص ── */}
      <Card pad={14} style={{ marginBottom: 10 }}>
        <SectionLabel
          action={
            <Badge tone={q.isLoading ? 'neutral' : q.isError ? 'danger' : 'ok'}>
              {q.isLoading ? 'تحميل…' : q.isError ? 'خطأ' : `${ranked.length} حقل`}
            </Badge>
          }
        >
          الملخّص
        </SectionLabel>

        {q.isLoading ? (
          <div style={{ color: T.muted, fontSize: 12, padding: '8px 0' }}>جارٍ تحميل ترتيب الحقول…</div>
        ) : q.isError ? (
          <div style={{ color: T.danger, fontSize: 12, padding: '8px 0' }}>تعذّر تحميل بيانات الحقول.</div>
        ) : !summary ? (
          <div style={{ color: T.muted, fontSize: 13, padding: '6px 0' }}>لا بيانات NDVI صالحة لأيّ حقل.</div>
        ) : (
          <StatGrid
            cols={4}
            items={[
              {
                label: 'عدد الحقول',
                value: summary.count,
                icon: <Layers style={{ width: 16, height: 16, color: T.brownSoft }} />,
              },
              {
                label: 'متوسّط NDVI',
                value: fmtNdvi(summary.avg),
                color: ndviColor(summary.avg),
                icon: <BarChart3 style={{ width: 16, height: 16, color: ndviColor(summary.avg) }} />,
              },
              {
                label: 'الأفضل',
                value: fmtNdvi(summary.best.ndvi),
                color: ndviColor(summary.best.ndvi),
                icon: <Trophy style={{ width: 16, height: 16, color: T.gold }} />,
              },
              {
                label: 'الأدنى',
                value: fmtNdvi(summary.worst.ndvi),
                color: ndviColor(summary.worst.ndvi),
                icon: <AlertTriangle style={{ width: 16, height: 16, color: T.warn }} />,
              },
            ]}
          />
        )}
      </Card>

      {/* ── الترتيب التنازليّ ── */}
      <Card pad={14}>
        <SectionLabel
          action={
            <span style={{ color: T.muted, fontSize: 11 }} className="inline-flex items-center gap-1">
              <TrendingUp style={{ width: 12, height: 12 }} /> الأفضل ← الأدنى
            </span>
          }
        >
          ترتيب الحقول
        </SectionLabel>

        {q.isLoading ? (
          <div style={{ color: T.muted, fontSize: 12, padding: '8px 0' }}>—</div>
        ) : q.isError ? (
          <div style={{ color: T.danger, fontSize: 12, padding: '8px 0' }}>تعذّر تحميل الترتيب.</div>
        ) : ranked.length === 0 ? (
          <div style={{ color: T.muted, fontSize: 13, padding: '6px 0' }}>لا بيانات</div>
        ) : (
          <div>
            {ranked.map((f, i) => {
              const color = ndviColor(f.ndvi);
              const isTop = topSet.has(f.id);
              const isBottom = bottomSet.has(f.id);
              return (
                <div
                  key={f.id || i}
                  style={{ padding: '10px 0', borderBottom: `1px solid ${T.line}` }}
                >
                  <div className="flex items-center gap-2" style={{ marginBottom: 6 }}>
                    <span
                      style={{
                        width: 22, height: 22, borderRadius: 999, background: T.card2,
                        color: T.muted, fontSize: 11, fontWeight: 800, flexShrink: 0,
                        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                      }}
                    >
                      {i + 1}
                    </span>
                    <span style={{ color: T.ink, fontSize: 13, fontWeight: 700, flex: 1 }}>
                      {f.name}
                      {f.crop && <span style={{ color: T.faint, fontSize: 11, fontWeight: 500, marginInlineStart: 6 }}>{f.crop}</span>}
                    </span>
                    {isTop && (
                      <Pill tone="ok" icon={<Trophy style={{ width: 11, height: 11 }} />}>الأفضل</Pill>
                    )}
                    {isBottom && (
                      <Pill tone="danger" icon={<AlertTriangle style={{ width: 11, height: 11 }} />}>يحتاج انتباه</Pill>
                    )}
                    <span style={{ color, fontSize: 13, fontWeight: 800, minWidth: 36, textAlign: 'left' }}>
                      {fmtNdvi(f.ndvi)}
                    </span>
                  </div>
                  <ProgressBar value={f.ndvi} color={color} />
                </div>
              );
            })}
          </div>
        )}
      </Card>
    </FieldCabin>
  );
}
