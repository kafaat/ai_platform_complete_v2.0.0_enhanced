// باني رابط بلاطات مؤشّر الحقل — مصدر واحد للصدق (كان مُكرَّراً حرفيّاً في HubMap وHubMapGL).
// وحدة محدودة نقيّة قابلة للاختبار مستقلّاً (تفكيك المكوّنات العملاقة — button-audit P2).
//
// الأمان: في الإنتاج لا JWT ولا tenant_id في رابط بلاطة <img> (البوّابة تشتقّ المستأجِر
// من JWT الموثّق عبر auth_request، والمصادقة عبر كوكي HttpOnly `sahool_at`) — يمنع تسريب
// JWT عبر سجلّ المتصفّح/Referrer (F-UI slice 3). التطوير يبقي tenant_id + access_token
// كـfallback مباشر لخدمة الراستر بلا بوّابة/كوكي.
//
// المسار: preferPersistedCog=true (التاريخ has_cog) ⇒ `/tiles` (COG المحفوظ، مصدر الحقيقة
// لـraster_assets)؛ وإلّا `/cdse-tiles` (المشهد الحيّ مقصوصاً على المضلّع بقناع rasterio).
import { geomToPolygon } from '../../lib/geo';
import { rasterBaseUrl } from '../../services/api';
import { getAccessToken } from '../../lib/authStorage';
import type { FieldOption } from '../../lib/fields';

export function indicatorTileUrl(
  field: FieldOption,
  index: string,
  tenantId?: string | null,
  imageryTs = 0,
  imageryDate?: string | null,
  preferPersistedCog = false,
): string {
  const params = new URLSearchParams({ index });
  // عقد التاريخ: لا نمرّر date حين latest/فارغ — الخادم يختار أحدث مشهد.
  if (imageryDate && imageryDate !== 'latest') params.set('date', imageryDate);
  if (!import.meta.env.PROD && tenantId) params.set('tenant_id', tenantId);
  if (imageryTs) params.set('v', String(imageryTs));
  if (!import.meta.env.PROD) {
    const tok = getAccessToken();
    if (tok) params.set('access_token', tok);
  }
  // عقد القصّ (poly/bbox) لمسار CDSE الحيّ فقط؛ `/tiles` المحفوظ يقرأ COG مقصوصاً مسبقاً.
  if (!preferPersistedCog) {
    const poly = geomToPolygon(field.geometry);
    if (poly && poly.length >= 3) {
      let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
      for (const [lat, lng] of poly) {
        if (lng < w) w = lng;
        if (lng > e) e = lng;
        if (lat < s) s = lat;
        if (lat > n) n = lat;
      }
      params.set('bbox_w', String(w)); params.set('bbox_s', String(s));
      params.set('bbox_e', String(e)); params.set('bbox_n', String(n));
      params.set('poly', poly.map(([lat, lng]) => `${lng},${lat}`).join(';'));
    }
  }
  const qs = params.toString();
  const segment = preferPersistedCog ? 'tiles' : 'cdse-tiles';
  return `${rasterBaseUrl()}/v1/fields/${field.id}/${segment}/{z}/{x}/{y}.png?${qs}`;
}
