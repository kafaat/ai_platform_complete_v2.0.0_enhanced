import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '../hooks/useAuth';
import { apiErrorMessage, fetchLabReview, transitionLabSample, type LabSampleRecord } from '../services/api';

function ReviewDetails({ sample }: { sample: LabSampleRecord }) {
  const { user } = useAuthStore();
  const client = useQueryClient();
  const key = ['lab', 'review', user?.tenant_id, user?.id, sample.sample_id];
  const review = useQuery({ queryKey: key, queryFn: () => fetchLabReview(sample.sample_id) });
  const action = useMutation({
    mutationFn: (target: 'approved' | 'published') =>
      transitionLabSample(sample.sample_id, target, review.data!.results.map(r => r.result_id)),
    onSettled: async () => {
      await Promise.all([client.invalidateQueries({ queryKey: ['lab'] }),
        client.invalidateQueries({ queryKey: ['field-irrigation-recommendation', sample.field_id] })]);
    },
  });
  if (review.isPending) return <p>جارٍ تحميل التحاليل…</p>;
  if (review.isError) return <button onClick={() => void review.refetch()}>تعذّر تحميل التحاليل. إعادة المحاولة</button>;
  const { results, can_approve, can_publish } = review.data;
  return <div className="space-y-2 p-2">
    <ul>{results.map(r => <li key={r.result_id}>
      <bdi>{r.analyte} · {typeof r.value_json === 'object' && r.value_json !== null ? JSON.stringify(r.value_json) : String(r.value_json)} {r.unit} {r.method_code} · {r.observed_at}</bdi>
    </li>)}</ul>
    {action.isError && <p role="alert">{apiErrorMessage(action.error, 'تعذّر تسجيل الانتقال.')}</p>}
    {(can_approve || can_publish) && <button className="rounded bg-emerald-700 px-3 py-1 text-white"
      disabled={action.isPending || review.isFetching}
      onClick={() => action.mutate(can_approve ? 'approved' : 'published')}>
      {can_approve ? 'اعتماد التحاليل المعروضة' : 'نشر التحاليل المعتمدة'}
    </button>}
  </div>;
}

export function LabSampleReview({ sample }: { sample: LabSampleRecord }) {
  const [open, setOpen] = useState(false);
  if (!['result_received','approved','published'].includes(sample.status)) return null;
  return <details onToggle={e => setOpen(e.currentTarget.open)}>
    <summary>عرض التحاليل ومراجعتها</summary>
    {open && <ReviewDetails sample={sample} />}
  </details>;
}
