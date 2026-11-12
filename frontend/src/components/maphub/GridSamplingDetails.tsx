import { acquisitionUtcDay } from '../../lib/dates';
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
  ['nearest_provider_samples_then_block_mean_reflectance_before_index',
    'أقرب جار لعينات المزوّد، ثم متوسط الانعكاس قبل حساب المؤشر'],
  ['nearest_provider_samples_then_block_mean_reflectance_before_normalized_difference',
    'أقرب جار لعينات المزوّد، ثم متوسط الانعكاس قبل حساب الفرق المعياري'],
  ['area_average_valid_fine_reflectance_before_ratio; nearest_SCL',
    'متوسط الانعكاس الصالح حسب المساحة قبل حساب النسبة، وأقرب جار لقناع التصنيف'],
]);

const metres = new Intl.NumberFormat('en', { maximumSignificantDigits: 5 });

const positive = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value) && value > 0;

function matchesRequestedGrid({ grid, fieldId, index, date, sceneId }: Props) {
  if (!grid.real_data || grid.field_id !== fieldId || grid.index !== index) return false;
  const day = acquisitionUtcDay(grid.date);
  if (!day || (sceneId && sceneId !== grid.indicator_product?.provenance?.scene_id)) return false;
  if (date === 'latest' || date === day || date === grid.date) return true;
  return date.includes('T') && grid.date.includes('T') && Date.parse(date) === Date.parse(grid.date);
}

const percent = new Intl.NumberFormat('en', { style: 'percent', maximumFractionDigits: 2 });
const ratio = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= 1;

function coveragePercent(value: number) {
  if (value > 0 && value < 0.0001) return '<0.01%';
  if (value < 1 && value > 0.9999) return '>99.99%';
  return percent.format(value);
}

export function GridCoverageDetails(props: Props) {
  const { grid } = props;
  const current = matchesRequestedGrid(props);
  const field = current ? grid.field_coverage : undefined;
  const box = current ? grid.valid_pixel_ratio : undefined;
  const revision = grid.grid_identity?.geometry_revision;
  const usable = field?.denominator === 'field_pixel_centres' && Number.isSafeInteger(field.geometry_revision) &&
    field.geometry_revision >= 0 && (revision == null || revision === field.geometry_revision) && Number.isSafeInteger(field.field_pixels) &&
    field.field_pixels > 0 && Number.isSafeInteger(field.valid_pixels) && field.valid_pixels >= 0 &&
    field.valid_pixels <= field.field_pixels && ratio(field.valid_pixel_ratio) &&
    Math.abs(field.valid_pixel_ratio - field.valid_pixels / field.field_pixels) <= 0.0001;
  return (
    <div className="space-y-1 px-3 text-xs text-slate-300" aria-label="تغطية الراستر المحفوظ">
      <p>البكسلات الصالحة داخل حدود الحقل · {usable
        ? <><bdi>{coveragePercent(field.valid_pixels / field.field_pixels)}</bdi> ({field.valid_pixels} من {field.field_pixels} بكسل) · مراجعة الحدود {field.geometry_revision}</>
        : 'غير متاحة'}</p>
      <p>البكسلات الصالحة في مستطيل الراستر · {ratio(box) ? <bdi>{coveragePercent(box)}</bdi> : 'غير متاحة'}</p>
    </div>
  );
}

export default function GridSamplingDetails(props: Props) {
  const { grid } = props;
  const sampling = grid.spatial_sampling;
  const gridScene = grid.indicator_product?.provenance?.scene_id;
  if (!sampling || !gridScene || !matchesRequestedGrid(props)) return null;

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
