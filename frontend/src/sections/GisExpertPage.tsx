import { Globe2, Layers, Satellite, Database, Archive, AlertTriangle } from 'lucide-react';
import {
  useGisStacLanding, useGisStacCollections, useGisStacItems,
  useGisOgcConformance, useGisOgcCollections, useGisTileCachePlan,
} from '../hooks/useApi';
import {
  cachePlanSummary, collectionRows, conformanceBadge, dash,
  itemsQualitySummary, ogcItemTypeLabel,
} from '../lib/gisCatalog';
import { T } from '../components/ds';
import { DegradedState } from '../components/product/DegradedState';
import { isAvailabilityError } from '../components/product/AdvancedServiceState';

/** كونسول كتالوج GIS للخبراء (قراءة فقط): بوّابة STAC ومجموعاتها وعناصرها +
 *  مطابقة OGC API ومجموعاتها + خطّة كاش البلاطات — طبقة خلفيّة قائمة
 *  (/api/v1/gis/cloud-native/*) كانت بلا أيّ واجهة قارئة. لا كتابة هنا؛
 *  مسارات المعالجة (cog-registry/locks/phase6) خارج نطاق هذه الصفحة عمداً. */
export default function GisExpertPage() {
  const landingQ = useGisStacLanding();
  const collectionsQ = useGisStacCollections();
  const itemsQ = useGisStacItems();
  const ogcConfQ = useGisOgcConformance();
  const ogcCollQ = useGisOgcCollections();
  const cacheQ = useGisTileCachePlan();

  const rows = collectionRows(collectionsQ.data);
  const quality = itemsQualitySummary(itemsQ.data?.features);
  const cache = cachePlanSummary(cacheQ.data);
  const recentItems = (itemsQ.data?.features ?? []).slice(0, 5);
  const serviceDegraded = [landingQ, collectionsQ, itemsQ, ogcConfQ, ogcCollQ, cacheQ]
    .some((q) => q.isError && isAvailabilityError(q.error));

  return (
    <div className="p-4 flex flex-col gap-3" data-testid="gis-expert">
      <h1 className="inline-flex items-center gap-2 text-lg font-bold" style={{ color: T.ink }}>
        <Globe2 className="w-5 h-5 text-emerald-300" aria-hidden="true" /> كتالوج GIS السحابيّ (STAC · OGC · COG)
      </h1>

      {serviceDegraded && (
        <DegradedState
          title="كتالوج GIS يعمل في وضع متدهور"
          detail="بعض مسارات STAC/OGC أو خطة كاش البلاطات غير متاحة حالياً. تُعرض البطاقات المتاحة فقط ولا تُستبدل القيم الناقصة بأرقام مُخترعة."
          availableActions={[
            'استعراض البطاقات التي عادت من الخادم بنجاح',
            'استخدام آخر كتالوج محفوظ إن وُجد',
            'إعادة المحاولة بعد عودة raster/GIS registry',
          ]}
          onRetry={() => { landingQ.refetch(); collectionsQ.refetch(); itemsQ.refetch(); ogcConfQ.refetch(); ogcCollQ.refetch(); cacheQ.refetch(); }}
        />
      )}

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {/* بوّابة STAC */}
        <Panel title="بوّابة STAC" icon={Satellite} tone={landingQ.data ? 'good' : landingQ.isError ? 'bad' : undefined}>
          {landingQ.isLoading ? (
            <Muted>جارٍ القراءة…</Muted>
          ) : landingQ.isError ? (
            <Muted>تعذّرت قراءة بوّابة STAC — تحقّق من تسجيل الدخول والصلاحيّة.</Muted>
          ) : landingQ.data ? (
            <>
              <div className="text-[12px]" style={{ color: T.ink }}>
                {landingQ.data.title} <span style={{ color: T.faint }}>· {landingQ.data.id} · v{landingQ.data.stac_version}</span>
              </div>
              <div className="text-[11px]" style={{ color: T.muted }}>{landingQ.data.description}</div>
              <div className="flex flex-wrap gap-1.5 mt-1">
                {landingQ.data.conformsTo.map((uri) => (
                  <Badge key={uri} title={uri}>{conformanceBadge(uri)}</Badge>
                ))}
              </div>
            </>
          ) : null}
        </Panel>

        {/* مجموعات STAC */}
        <Panel title="مجموعات STAC" icon={Layers}>
          {collectionsQ.isLoading ? (
            <Muted>جارٍ القراءة…</Muted>
          ) : collectionsQ.isError ? (
            <Muted>تعذّرت قراءة المجموعات (قد تكون قاعدة السجلّ غير متاحة).</Muted>
          ) : rows.length === 0 ? (
            <Muted>لا مجموعات مسجَّلة بعد — سجلّ الرستر (raster_registry) فارغ لهذا المستأجِر.</Muted>
          ) : (
            rows.map((c) => (
              <div key={c.id} className="text-[11px] flex flex-wrap items-baseline gap-x-1.5" style={{ color: T.ink }}>
                <b>{c.id}</b>
                <span style={{ color: T.muted }}>{c.title}</span>
                <span style={{ color: T.faint }}>· المدى الزمنيّ: {c.temporal}{c.license ? ` · ${c.license}` : ''}</span>
              </div>
            ))
          )}
        </Panel>

        {/* عناصر STAC (أحدث المشاهد) */}
        <Panel title="عناصر STAC (بحث)" icon={Satellite}>
          {itemsQ.isLoading ? (
            <Muted>جارٍ القراءة…</Muted>
          ) : itemsQ.isError ? (
            <Muted>تعذّر البحث في العناصر.</Muted>
          ) : itemsQ.data ? (
            <>
              <div className="text-[12px]" style={{ color: T.ink }}>
                مطابِق: <b>{itemsQ.data.numberMatched}</b>
                <span className="text-[11px]" style={{ color: T.faint }}>
                  {' '}· متوسّط الغيوم: {dash(quality.avgCloudPct)}٪ · الجودة: {dash(quality.minQuality)}–{dash(quality.maxQuality)}
                </span>
              </div>
              {quality.indexTypes.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-1">
                  {quality.indexTypes.map((t) => <Badge key={t}>{t}</Badge>)}
                </div>
              )}
              {recentItems.map((it) => (
                <div key={it.id} className="text-[11px]" style={{ color: T.muted }}>
                  {it.id} <span style={{ color: T.faint }}>
                    · {it.properties['sahool:index_type']} · {dash(it.properties.datetime)} · غيوم {dash(it.properties['eo:cloud_cover'])}٪ · جودة {dash(it.properties['sahool:quality_score'])}
                  </span>
                </div>
              ))}
              {itemsQ.data.features.length === 0 && <Muted>لا عناصر — لم تُسجَّل مشاهد COG بعد.</Muted>}
            </>
          ) : null}
        </Panel>

        {/* مطابقة OGC API */}
        <Panel title="مطابقة OGC API" icon={Globe2}>
          {ogcConfQ.isLoading ? (
            <Muted>جارٍ القراءة…</Muted>
          ) : ogcConfQ.isError ? (
            <Muted>تعذّرت قراءة المطابقة.</Muted>
          ) : ogcConfQ.data ? (
            <div className="flex flex-wrap gap-1.5">
              {ogcConfQ.data.conformsTo.map((uri) => (
                <Badge key={uri} title={uri}>{conformanceBadge(uri)}</Badge>
              ))}
            </div>
          ) : null}
        </Panel>

        {/* مجموعات OGC */}
        <Panel title="مجموعات OGC" icon={Database}>
          {ogcCollQ.isLoading ? (
            <Muted>جارٍ القراءة…</Muted>
          ) : ogcCollQ.isError ? (
            <Muted>تعذّرت قراءة مجموعات OGC.</Muted>
          ) : (ogcCollQ.data?.collections ?? []).length === 0 ? (
            <Muted>لا مجموعات.</Muted>
          ) : (
            ogcCollQ.data!.collections.map((c) => (
              <div key={c.id} className="text-[11px]" style={{ color: T.ink }}>
                <b>{c.id}</b> <span style={{ color: T.muted }}>{c.title}</span>{' '}
                <span style={{ color: T.faint }}>· {ogcItemTypeLabel(c.itemType)} · CRS: {c.crs.length}</span>
              </div>
            ))
          )}
        </Panel>

        {/* خطّة كاش البلاطات */}
        <Panel title="خطّة كاش البلاطات" icon={Archive}>
          {cacheQ.isLoading ? (
            <Muted>جارٍ القراءة…</Muted>
          ) : cacheQ.isError ? (
            <Muted>تعذّرت قراءة خطّة الكاش.</Muted>
          ) : cache ? (
            <>
              <div className="text-[12px]" style={{ color: T.ink }}>
                الاستراتيجيّة: <b>{cache.strategy}</b>
              </div>
              <div className="text-[11px]" style={{ color: T.muted }}>
                إدخالات: {cache.totalEntries} · TTL يوم: {cache.longTtl} · TTL ست ساعات: {cache.shortTtl}
              </div>
              {cache.purgeOn.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-1">
                  {cache.purgeOn.map((p) => <Badge key={p}>تفريغ عند: {p}</Badge>)}
                </div>
              )}
            </>
          ) : (
            <Muted>لا خطّة متاحة.</Muted>
          )}
        </Panel>
      </div>

      <div className="inline-flex items-center gap-1.5 text-[11px]" style={{ color: T.faint }}>
        <AlertTriangle className="w-3.5 h-3.5" aria-hidden="true" />
        القيم من مسارات GIS الحيّة (/api/v1/gis/cloud-native) كما هي — «—» تعني غياب القيمة لا صفراً، وقراءةٌ فقط (لا تسجيل ولا أقفال من هنا).
      </div>
    </div>
  );
}

function Panel({ title, icon: Icon, tone, children }: { title: string; icon: typeof Globe2; tone?: 'good' | 'bad'; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border p-3" style={{ borderColor: tone === 'bad' ? '#7c2d12' : tone === 'good' ? '#14532d' : T.line, background: 'rgba(2,6,23,.35)' }}>
      <div className="inline-flex items-center gap-2 text-sm font-bold mb-2" style={{ color: T.ink }}>
        <Icon className="w-4 h-4 text-emerald-300" aria-hidden="true" /> {title}
      </div>
      <div className="flex flex-col gap-0.5">{children}</div>
    </section>
  );
}

function Muted({ children }: { children: React.ReactNode }) {
  return <div className="text-[11px]" style={{ color: T.muted }}>{children}</div>;
}

function Badge({ children, title }: { children: React.ReactNode; title?: string }) {
  return (
    <span className="text-[10px] px-2 py-0.5 rounded-full" title={title} style={{ border: `1px solid ${T.line}`, color: T.muted }}>
      {children}
    </span>
  );
}
