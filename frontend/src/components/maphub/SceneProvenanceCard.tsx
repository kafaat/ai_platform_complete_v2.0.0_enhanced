import { AlertTriangle, Database, ShieldCheck } from 'lucide-react';

export interface SceneProvenance {
  date: string;
  scene_id?: string | null;
  acquisition_datetime?: string | null;
  cloud_pct?: number | null;
  cloud_cover?: number | null;
  clear_pct?: number | null;
  quality_label?: string | null;
  indices?: string[];
  has_cog?: boolean;
}

function cloudValue(scene: SceneProvenance): number | null {
  if (typeof scene.cloud_pct === 'number') return scene.cloud_pct;
  if (typeof scene.cloud_cover === 'number') return scene.cloud_cover;
  return null;
}

export function sceneProvenanceMissing(scene: SceneProvenance): string[] {
  const missing: string[] = [];
  if (!scene.scene_id) missing.push('معرّف المشهد');
  if (!scene.acquisition_datetime) missing.push('وقت الالتقاط');
  if (cloudValue(scene) == null) missing.push('نسبة الغيوم');
  return missing;
}

export default function SceneProvenanceCard({ scene, compact = false }: { scene: SceneProvenance; compact?: boolean }) {
  const missing = sceneProvenanceMissing(scene);
  const cloud = cloudValue(scene);
  const complete = missing.length === 0;
  return (
    <section
      dir="rtl"
      aria-label="مصدر مشهد القمر الصناعي"
      data-testid="scene-provenance-card"
      className={`rounded-xl border ${compact ? 'mt-2 p-2' : 'mt-3 p-3'} ${complete ? 'border-emerald-500/30 bg-emerald-950/20' : 'border-amber-500/30 bg-amber-950/20'}`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs font-bold text-slate-100">
          <Database className="h-3.5 w-3.5" aria-hidden="true" />
          سلسلة مصدر المشهد
        </div>
        <span className={`inline-flex items-center gap-1 text-[11px] ${complete ? 'text-emerald-300' : 'text-amber-300'}`}>
          {complete ? <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" /> : <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />}
          {complete ? 'مكتملة' : 'غير مكتملة'}
        </span>
      </div>
      <dl className={`mt-2 grid gap-x-3 gap-y-1 text-[11px] ${compact ? 'grid-cols-1' : 'sm:grid-cols-2'}`}>
        <div><dt className="inline text-slate-500">المشهد: </dt><dd className="inline break-all text-slate-300">{scene.scene_id ?? 'غير متوفر'}</dd></div>
        <div><dt className="inline text-slate-500">الالتقاط: </dt><dd className="inline text-slate-300">{scene.acquisition_datetime ?? scene.date}</dd></div>
        <div><dt className="inline text-slate-500">الغيوم: </dt><dd className="inline text-slate-300">{cloud == null ? 'غير متوفر' : `${Math.round(cloud)}%`}</dd></div>
        <div><dt className="inline text-slate-500">الحالة: </dt><dd className="inline text-slate-300">{scene.has_cog ? 'COG جاهز' : 'لم يُنتج COG بعد'}</dd></div>
        {!compact && <div><dt className="inline text-slate-500">الجودة: </dt><dd className="inline text-slate-300">{scene.quality_label ?? 'غير مصنفة'}</dd></div>}
        {!compact && <div><dt className="inline text-slate-500">المؤشرات: </dt><dd className="inline text-slate-300">{scene.indices?.length ? scene.indices.join(', ') : 'لا توجد'}</dd></div>}
      </dl>
      {!complete && <p className="mt-2 text-[11px] text-amber-200" role="status">بيانات المصدر الناقصة: {missing.join('، ')}. لا تُعد هذه الصورة كاملة التتبّع.</p>}
    </section>
  );
}
