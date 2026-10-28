// ═══════════════════════════════════════════════════════════════
// جغرافيا شبكة المؤشّر (indicator-grid) — من (صفّ، عمود) إلى (lon, lat) بصدق.
// ───────────────────────────────────────────────────────────────
// raster-service يُبقي الشبكة بنظام CRS المصدر وينشر تحويلها في grid_identity
// ({crs, transform:[a,b,c,d,e,f], rows, cols}) — bbox مجرّد غلاف مُحوَّل إلى EPSG:4326.
// الاستيفاء الخطّيّ على bbox صحيح فقط لشبكة جغرافيّة شماليّة الاتّجاه؛ لشبكة مُدارة أو
// مُسقَطة (UTM لمشاهد Sentinel-2) يُخطئ موضع الخليّة (P3-CON-2). لذا:
//   • مركز الخليّة = transform · (col+0.5, row+0.5) بنظام المصدر، ثمّ:
//       EPSG:4326/CRS84 ⇒ كما هو؛ EPSG:326zz/327zz ⇒ عكس UTM (WGS84) أدناه.
//   • غياب الهويّة/عدم تطابق أبعادها/CRS غير مدعوم ⇒ استيفاء bbox مع method='bbox'
//     كي تُوسَم الإحداثيّة تقريبيّة في الواجهة — لا ادّعاء دقّة.
//   • نقطة عيّنة المنطقة = خليّة **صالحة** (قيمة غير null) من خلايا المنطقة نفسها، الأقرب
//     إلى متوسّط مواضعها؛ متوسّط خلايا متفرّقة قد يقع في خليّة بلا بيانات أو خارج الحقل.
// ═══════════════════════════════════════════════════════════════

export interface GridIdentity {
  crs: string;
  transform: number[]; // [a, b, c, d, e, f] — x = a·col + b·row + c ، y = d·col + e·row + f
  geometry_revision?: number;
  rows?: number;
  cols?: number;
}

export interface GridGeoInput {
  bbox: [number, number, number, number]; // [minlon, minlat, maxlon, maxlat]
  rows: number;
  cols: number;
  grid: (number | null)[][];
  grid_identity?: GridIdentity | null;
}

export interface CellLonLat {
  lon: number;
  lat: number;
  method: 'affine' | 'bbox';
}

export interface ZoneSamplePoint extends CellLonLat {
  cell: [number, number];
}

// ── عكس Transverse Mercator (سلسلة Krüger حتى n⁶، WGS84) — دقّة دون المليمتر في النطاق ──
const WGS84_A = 6378137;
const WGS84_F = 1 / 298.257223563;
const UTM_K0 = 0.9996;
const _n = WGS84_F / (2 - WGS84_F);
const _n2 = _n * _n, _n3 = _n2 * _n, _n4 = _n3 * _n, _n5 = _n4 * _n, _n6 = _n5 * _n;
const _A = (WGS84_A / (1 + _n)) * (1 + _n2 / 4 + _n4 / 64 + _n6 / 256);
const _BETA = [
  _n / 2 - (2 * _n2) / 3 + (37 * _n3) / 96 - _n4 / 360 - (81 * _n5) / 512 + (96199 * _n6) / 604800,
  _n2 / 48 + _n3 / 15 - (437 * _n4) / 1440 + (46 * _n5) / 105 - (1118711 * _n6) / 3870720,
  (17 * _n3) / 480 - (37 * _n4) / 840 - (209 * _n5) / 4480 + (5569 * _n6) / 90720,
  (4397 * _n4) / 161280 - (11 * _n5) / 504 - (830251 * _n6) / 7257600,
  (4583 * _n5) / 161280 - (108847 * _n6) / 3991680,
  (20648693 * _n6) / 638668800,
];
const _DELTA = [
  2 * _n - (2 * _n2) / 3 - 2 * _n3 + (116 * _n4) / 45 + (26 * _n5) / 45 - (2854 * _n6) / 675,
  (7 * _n2) / 3 - (8 * _n3) / 5 - (227 * _n4) / 45 + (2704 * _n5) / 315 + (2323 * _n6) / 945,
  (56 * _n3) / 15 - (136 * _n4) / 35 - (1262 * _n5) / 105 + (73814 * _n6) / 2835,
  (4279 * _n4) / 630 - (332 * _n5) / 35 - (399572 * _n6) / 14175,
  (4174 * _n5) / 315 - (144838 * _n6) / 6237,
  (601676 * _n6) / 22275,
];

// EPSG:326zz (شمال) / 327zz (جنوب) ⇒ [lon, lat] بالدرجات؛ غير ذلك ⇒ null.
export function utmToLonLat(epsg: number, easting: number, northing: number): [number, number] | null {
  let zone: number;
  let south: boolean;
  if (epsg >= 32601 && epsg <= 32660) { zone = epsg - 32600; south = false; }
  else if (epsg >= 32701 && epsg <= 32760) { zone = epsg - 32700; south = true; }
  else return null;
  const xi = (northing - (south ? 10_000_000 : 0)) / (UTM_K0 * _A);
  const eta = (easting - 500_000) / (UTM_K0 * _A);
  let xiP = xi;
  let etaP = eta;
  for (let j = 1; j <= 6; j++) {
    const b = _BETA[j - 1];
    xiP -= b * Math.sin(2 * j * xi) * Math.cosh(2 * j * eta);
    etaP -= b * Math.cos(2 * j * xi) * Math.sinh(2 * j * eta);
  }
  const chi = Math.asin(Math.sin(xiP) / Math.cosh(etaP));
  let phi = chi;
  for (let j = 1; j <= 6; j++) phi += _DELTA[j - 1] * Math.sin(2 * j * chi);
  const lon0 = (zone - 1) * 6 - 180 + 3;
  const lon = lon0 + (Math.atan2(Math.sinh(etaP), Math.cos(xiP)) * 180) / Math.PI;
  return [lon, (phi * 180) / Math.PI];
}

function nativeToLonLat(crs: string, x: number, y: number): [number, number] | null {
  const norm = crs.trim().toUpperCase();
  if (norm === 'EPSG:4326' || norm === 'OGC:CRS84' || norm === 'CRS84') return [x, y];
  const m = /^EPSG:(\d+)$/.exec(norm);
  return m ? utmToLonLat(Number(m[1]), x, y) : null;
}

// مركز الخليّة (r, c) بالدرجات. null فقط لشبكة بلا أبعاد.
export function cellCenterLonLat(resp: GridGeoInput, r: number, c: number): CellLonLat | null {
  const { rows, cols } = resp;
  if (!(rows > 0 && cols > 0)) return null;
  const gi = resp.grid_identity;
  if (
    gi && typeof gi.crs === 'string' && Array.isArray(gi.transform) && gi.transform.length >= 6 &&
    gi.transform.slice(0, 6).every((v) => Number.isFinite(v)) &&
    (gi.rows == null || gi.rows === rows) && (gi.cols == null || gi.cols === cols)
  ) {
    const [a, b, c0, d, e, f] = gi.transform;
    const x = a * (c + 0.5) + b * (r + 0.5) + c0;
    const y = d * (c + 0.5) + e * (r + 0.5) + f;
    const ll = nativeToLonLat(gi.crs, x, y);
    if (ll && Number.isFinite(ll[0]) && Number.isFinite(ll[1])) {
      return { lon: ll[0], lat: ll[1], method: 'affine' };
    }
  }
  const [minLon, minLat, maxLon, maxLat] = resp.bbox;
  return {
    lon: minLon + ((c + 0.5) / cols) * (maxLon - minLon),
    lat: maxLat - ((r + 0.5) / rows) * (maxLat - minLat),
    method: 'bbox',
  };
}

// نقطة عيّنة المنطقة: خليّة صالحة من خلاياها، الأقرب لمتوسّط مواضع الخلايا الصالحة.
export function zoneSamplePoint(
  resp: GridGeoInput,
  cells: ReadonlyArray<readonly [number, number] | readonly number[]>,
): ZoneSamplePoint | null {
  const valid: [number, number][] = [];
  for (const cell of cells) {
    const [r, c] = cell;
    const v = resp.grid?.[r]?.[c];
    if (typeof v === 'number' && Number.isFinite(v)) valid.push([r, c]);
  }
  if (valid.length === 0) return null;
  const mr = valid.reduce((s, p) => s + p[0], 0) / valid.length;
  const mc = valid.reduce((s, p) => s + p[1], 0) / valid.length;
  let best = valid[0];
  let bestD = Infinity;
  for (const p of valid) {
    const dd = (p[0] - mr) ** 2 + (p[1] - mc) ** 2;
    if (dd < bestD) { bestD = dd; best = p; }
  }
  const ll = cellCenterLonLat(resp, best[0], best[1]);
  return ll ? { ...ll, cell: best } : null;
}
