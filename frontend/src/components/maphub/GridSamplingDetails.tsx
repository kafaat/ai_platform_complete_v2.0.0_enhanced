import type { IndicatorGridResponse } from '../../hooks/useApi';

type Props = {
  grid: IndicatorGridResponse;
  fieldId: string;
  index: string;
  date: string;
  sceneId?: string | null;
};

const methodLabels = new Map([
  ['nearest', 'أقرب جار'],
  ['nearest_provider_samples', 'أقرب جار لعينات المزوّد'],
  ['nearest_provider_samples_then_block_mean_reflectance_before_normalized_difference',
    'أقرب جار لعينات المزوّد، ثم متوسط الانعكاس قبل حساب الفرق المعياري'],
  ['area_average_valid_fine_reflectance_before_ratio; nearest_SCL',
    'متوسط الانعكاس الصالح حسب المساحة قبل حساب النسبة، وأقرب جار لقناع التصنيف'],
]);

const metres = new Intl.NumberFormat('en', { maximumSignificantDigits: 5 });

const positive = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value) && value > 0;

export default function GridSamplingDetails({ grid, fieldId, index, date, sceneId }: Props) {
  const sampling = grid.spatial_sampling;
  const gridScene = grid.indicator_product?.provenance?.scene_id;
  if (!sampling || !grid.real_data || grid.field_id !== fieldId || grid.index !== index ||
      !gridScene || (sceneId && sceneId !== gridScene) || !/^\d{4}-\d{2}-\d{2}(?:$|T)/.test(grid.date)) return null;
  if (date !== 'latest' && date !== grid.date &&
      !(date.length === 10 && date === grid.date.slice(0, 10)) &&
      !(date.includes('T') && grid.date.includes('T') && Date.parse(date) === Date.parse(grid.date))) return null;

  const bands = Object.entries(sampling.native_band_resolution_m ?? {})
    .filter(([band, size]) => band.trim() && positive(size));
  const pixel = sampling.output_pixel_size_m;
  const method = sampling.resampling_method?.trim();
  const hasPixel = Array.isArray(pixel) && pixel.length === 2 && pixel.every(positive);
  if (!bands.length && !hasPixel && !method) return null;

  return (
    <div className="space-y-1 px-3 text-xs text-slate-300">
      <p>راستر المؤشّر المحفوظ · <bdi>{grid.index.toUpperCase()}</bdi> · <bdi>{grid.date}</bdi> · <bdi>{gridScene}</bdi></p>
      {bands.length > 0 && <p>الدقّة الأصلية للنطاقات · {bands.map(([band, size], i) =>
        <span key={band}>{i > 0 && '، '}<bdi>{band}</bdi> {metres.format(size)} م</span>)}</p>}
      {hasPixel && <p>أبعاد بكسل الراستر الناتج · <bdi>{metres.format(pixel[0])} × {metres.format(pixel[1])}</bdi> م</p>}
      {method && <p>طريقة إعادة أخذ العينات · <bdi>{methodLabels.get(method) ?? method}</bdi></p>}
    </div>
  );
}
