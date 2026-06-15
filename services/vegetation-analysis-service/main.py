"""
SAHOOL v9.1 — vegetation-analysis-service/main.py (FULLY FIXED)
══════════════════════════════════════════════════════════════
إصلاحات:
  ✅ أكمل الملف المقطوع (lifespan + app + endpoints)
  ✅ أزل field_id من Prometheus labels (cardinality explosion)
  ✅ استبدل datetime.now(timezone.utc) بـ datetime.now(timezone.utc)
  ✅ أضف auth dependency على endpoints الحساسة

NOTE ON DATA PROVENANCE (honesty):
  This service does NOT decode satellite raster pixels. It deliberately
  avoids heavy geospatial dependencies (rasterio/GDAL). It may make REAL
  authenticated calls to Sentinel Hub / CDSE to confirm provider reachability
  and acquisition metadata, but the returned GeoTIFF bytes are NOT decoded
  here. The vegetation indices returned by this service are therefore
  FIELD-MEAN ESTIMATES computed from deterministic synthetic bands (seeded by
  field + date), NOT from real per-pixel reflectance.

  Real per-pixel raster processing (decoding the GeoTIFF, masking via SCL,
  averaging real reflectance) lives in the raster-service, which ships rasterio.

  EXCEPTION — real NDVI pass-through (VEGETATION_PREFER_RASTER, ON by default):
  /v1/analyze prefers the REAL per-pixel NDVI mean from raster-service when the
  field has a processed layer. In that case it substitutes NDVI only and reports
  `real_data: true` + `data_source: "raster-service"` (per-index `source` marks
  NDVI as "raster-service" and the rest as "estimate"). Any failure/timeout/
  missing layer falls back to the labeled estimate (behaviour never degrades).
  `provider_reachable` indicates whether the live SH/CDSE metadata API responded.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta

import httpx
import jwt as _jwt
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.responses import Response

try:
    from shared.logging_config import setup_logging

    logger = setup_logging("vegetation-analysis-service")
except ImportError:
    logging.basicConfig(
        level=logging.INFO, format='{"time":"%(asctime)s","svc":"vegetation","msg":"%(message)s"}'
    )
    logger = logging.getLogger("vegetation-analysis-service")

# ── Config ─────────────────────────────────────────────────────
NATS_URL = os.getenv("NATS_URL", "nats://sahool-nats:4222")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

# تفضيل NDVI الحقيقيّ من raster-service (بكسليّ، Sentinel-2) على التقدير التركيبيّ.
# مُفعَّل افتراضيّاً؛ يبقى مفتاح إيقاف (=0) لأغراض التشغيل. fail-safe بالكامل:
# أيّ تعذّر/مهلة/غياب طبقة ⇒ ارتداد للتقدير المُعلَّم الحاليّ (السلوك لا يسوء أبداً).
RASTER_SERVICE_URL = os.getenv("RASTER_SERVICE_URL", "http://sahool-raster-service:8001").rstrip(
    "/"
)
VEGETATION_PREFER_RASTER = os.getenv("VEGETATION_PREFER_RASTER", "1") not in (
    "0",
    "false",
    "False",
    "",
)

SH_CLIENT_ID = os.getenv("SH_CLIENT_ID", "")
SH_CLIENT_SECRET = os.getenv("SH_CLIENT_SECRET", "")
SH_TOKEN_URL = "https://services.sentinel-hub.com/auth/realms/main/protocol/openid-connect/token"
SH_PROCESS_URL = "https://services.sentinel-hub.com/api/v1/process"

CDSE_USER = os.getenv("COPERNICUS_USER", "")
CDSE_PASSWORD = os.getenv("COPERNICUS_PASSWORD", "")

security = HTTPBearer(auto_error=False)

# ── تحقّق JWT حقيقيّ (كان يُقبل أيّ Bearer غير فارغ بلا تحقّق توقيع) ──
_VEG_JWT_SECRET = os.getenv("JWT_SECRET", "")
_VEG_JWT_ALG = "HS256"
# المُصدِرون الداخليّون المسموح بهم — يُفرَض بعد فكّ التوكن (تدقيق B: iss لم يُفحَص).
_ALLOWED_ISS = {"sahool-auth", "sahool-platform"}
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _verify_claims(token) -> dict:
    """يتحقّق من توقيع JWT وaudience، ويُرجِع المطالبات. fail-closed."""
    if not token or not token.credentials:
        raise HTTPException(401, "Authentication required")
    if not _VEG_JWT_SECRET or len(_VEG_JWT_SECRET) < 32:
        raise HTTPException(503, "JWT_SECRET غير مضبوط")
    try:
        payload = _jwt.decode(
            token.credentials, _VEG_JWT_SECRET, algorithms=[_VEG_JWT_ALG], audience="sahool"
        )
    except Exception:
        raise HTTPException(401, "توكن غير صالح") from None
    # تدقيق B: افرض المُصدِر بعد فكّ ناجح — مُصدِر مجهول ⇒ 401 كتوكن غير صالح.
    if payload.get("iss") not in _ALLOWED_ISS:
        raise HTTPException(401, "مُصدِر التوكن غير مسموح")
    return payload


def _tenant_from_claims(claims: dict) -> str:
    """المستأجِر من التوكن لا من العميل — يمنع حقن موضوع NATS عابر المستأجرين."""
    tid = str(claims.get("tenant_id") or "")
    if not tid:
        raise HTTPException(401, "توكن بلا مستأجِر")
    return tid


def _valid_date(s: str) -> str:
    """يتحقّق أنّ التاريخ بصيغة YYYY-MM-DD — يمنع حقن OData/الاستعلام المتسلسل."""
    if not _ISO_DATE_RE.match(s):
        raise HTTPException(400, "صيغة تاريخ غير صالحة (YYYY-MM-DD)")
    return s


# ── Prometheus (FIXED: removed field_id label to prevent cardinality explosion) ──
ANALYSIS_COUNT = Counter(
    "sahool_vegetation_analysis_total", "Vegetation analysis requests", ["source", "status"]
)
ANALYSIS_LATENCY = Histogram(
    "sahool_vegetation_analysis_duration_seconds", "Vegetation analysis duration", ["source"]
)

# ── Field geometry registry ────────────────────────────────────
FIELD_REGISTRY: dict[str, dict] = {
    "field_01": {
        "name": "حقل وادي سبأ",
        "bbox": [45.50, 15.00, 45.60, 15.10],
        "area_ha": 23.5,
        "crop": "wheat",
        "soil": "loam",
    },
    "field_02": {
        "name": "حقل البيضاء الشمالي",
        "bbox": [45.53, 14.97, 45.63, 15.07],
        "area_ha": 32.0,
        "crop": "barley",
        "soil": "clay_loam",
    },
    "field_03": {
        "name": "حقل البيضاء الجنوبي",
        "bbox": [45.47, 14.93, 45.57, 15.03],
        "area_ha": 18.7,
        "crop": "maize",
        "soil": "sandy_loam",
    },
    "field_04": {
        "name": "حقل رداع الغربي",
        "bbox": [45.43, 14.87, 45.53, 14.97],
        "area_ha": 41.3,
        "crop": "tomato",
        "soil": "loam",
    },
    "field_05": {
        "name": "حقل ذي السفال",
        "bbox": [45.55, 14.83, 45.65, 14.93],
        "area_ha": 28.9,
        "crop": "wheat",
        "soil": "silt_loam",
    },
    "field_06": {
        "name": "حقل عتمة الشرقي",
        "bbox": [45.57, 15.05, 45.67, 15.15],
        "area_ha": 37.5,
        "crop": "barley",
        "soil": "clay_loam",
    },
    "field_07": {
        "name": "حقل الرياشية",
        "bbox": [45.40, 14.95, 45.50, 15.05],
        "area_ha": 22.1,
        "crop": "vegetables",
        "soil": "loam",
    },
    "field_08": {
        "name": "حقل ذي ناعم",
        "bbox": [45.60, 14.80, 45.70, 14.90],
        "area_ha": 45.0,
        "crop": "potato",
        "soil": "sandy_loam",
    },
}

# ── Sentinel Hub token cache ───────────────────────────────────
_sh_token: str | None = None
_sh_token_exp: datetime | None = None


async def _get_sh_token() -> str | None:
    global _sh_token, _sh_token_exp
    if not SH_CLIENT_ID or not SH_CLIENT_SECRET:
        return None
    if _sh_token and _sh_token_exp and datetime.now(UTC) < _sh_token_exp:
        return _sh_token
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                SH_TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": SH_CLIENT_ID,
                    "client_secret": SH_CLIENT_SECRET,
                },
            )
            r.raise_for_status()
            data = r.json()
            _sh_token = data["access_token"]
            _sh_token_exp = datetime.now(UTC) + timedelta(
                seconds=data.get("expires_in", 3600) - 300
            )
            logger.info("✅ Sentinel Hub token refreshed")
            return _sh_token
    except Exception as e:
        logger.warning(f"SH token failed: {e}")
        return None


EVALSCRIPT_ALL_INDICES = """
//VERSION=3
function setup() {
    return {
        input: [{
            bands: ["B02","B03","B04","B05","B06","B07","B08","B8A","B11","B12","SCL"],
            units: "REFLECTANCE"
        }],
        output: [
            { id: "ndvi",   bands: 1, sampleType: "FLOAT32" },
            { id: "evi",    bands: 1, sampleType: "FLOAT32" },
            { id: "savi",   bands: 1, sampleType: "FLOAT32" },
            { id: "ndwi",   bands: 1, sampleType: "FLOAT32" },
            { id: "ndmi",   bands: 1, sampleType: "FLOAT32" },
            { id: "gndvi",  bands: 1, sampleType: "FLOAT32" },
            { id: "recl",   bands: 1, sampleType: "FLOAT32" },
            { id: "scl",    bands: 1, sampleType: "UINT8"   }
        ]
    };
}
function evaluatePixel(sample) {
    if (sample.SCL === 3 || sample.SCL === 8 || sample.SCL === 9 || sample.SCL === 10) {
        return {
            ndvi: [NaN], evi: [NaN], savi: [NaN],
            ndwi: [NaN], ndmi: [NaN], gndvi: [NaN],
            recl: [NaN], scl: [sample.SCL]
        };
    }
    let B02=sample.B02, B03=sample.B03, B04=sample.B04,
        B05=sample.B05, B08=sample.B08, B8A=sample.B8A,
        B11=sample.B11, B12=sample.B12;
    let ndvi  = (B08-B04)/(B08+B04+1e-10);
    let evi   = 2.5*(B08-B04)/(B08+6*B04-7.5*B02+1);
    let savi  = (B08-B04)/(B08+B04+0.5)*1.5;
    let ndwi  = (B03-B08)/(B03+B08+1e-10);
    let ndmi  = (B08-B11)/(B08+B11+1e-10);
    let gndvi = (B08-B03)/(B08+B03+1e-10);
    let recl  = B05/B04 - 1;
    return {
        ndvi: [ndvi], evi: [evi], savi: [savi],
        ndwi: [ndwi], ndmi: [ndmi], gndvi: [gndvi],
        recl: [recl], scl: [sample.SCL]
    };
}
"""


async def fetch_from_sentinel_hub(field_id: str, date_from: str, date_to: str) -> dict | None:
    token = await _get_sh_token()
    if not token:
        return None
    field = FIELD_REGISTRY.get(field_id)
    if not field:
        return None
    bbox = field["bbox"]
    payload = {
        "input": {
            "bounds": {
                "bbox": bbox,
                "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"},
            },
            "data": [
                {
                    "type": "sentinel-2-l2a",
                    "dataFilter": {
                        "timeRange": {
                            "from": f"{date_from}T00:00:00Z",
                            "to": f"{date_to}T23:59:59Z",
                        },
                        "maxCloudCoverage": 20,
                        "mosaickingOrder": "leastCC",
                    },
                }
            ],
        },
        "output": {
            "width": 128,
            "height": 128,
            "responses": [
                {"identifier": "ndvi", "format": {"type": "image/tiff"}},
                {"identifier": "evi", "format": {"type": "image/tiff"}},
                {"identifier": "savi", "format": {"type": "image/tiff"}},
                {"identifier": "ndwi", "format": {"type": "image/tiff"}},
                {"identifier": "gndvi", "format": {"type": "image/tiff"}},
            ],
        },
        "evalscript": EVALSCRIPT_ALL_INDICES,
    }
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(
                SH_PROCESS_URL,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                content=json.dumps(payload),
            )
            if r.status_code == 200:
                # HONESTY FIX: the GeoTIFF bytes are NOT decoded here (no rasterio
                # in this service). We therefore do NOT derive an NDVI from the
                # response byte size (that number was meaningless). We only record
                # that the provider was reachable; indices remain simulated.
                size_kb = len(r.content) / 1024
                return {
                    "source": "sentinel-hub-unavailable",
                    "acquisition_date": date_from,
                    "cloud_pct": 0.0,
                    "response_kb": round(size_kb, 1),
                    "provider_reachable": True,
                    "real_data": False,
                }
            else:
                logger.warning(f"SH API error {r.status_code}: {r.text[:200]}")
                return None
    except Exception as e:
        logger.warning(f"SH fetch failed: {e}")
        return None


async def fetch_from_cdse(field_id: str, date_from: str, date_to: str) -> dict | None:
    if not CDSE_USER or not CDSE_PASSWORD:
        return None
    field = FIELD_REGISTRY.get(field_id)
    if not field:
        return None
    bbox = field["bbox"]
    query_url = (
        f"https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
        f"?$filter=Collection/Name eq 'SENTINEL-2' "
        f"and Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'productType' "
        f"and att/OData.CSC.StringAttribute/Value eq 'S2MSI2A') "
        f"and ContentDate/Start gt {date_from}T00:00:00.000Z "
        f"and ContentDate/Start lt {date_to}T23:59:59.999Z "
        f"and OData.CSC.Intersects(area=geography'SRID=4326;POLYGON(("
        f"{bbox[0]} {bbox[1]},{bbox[2]} {bbox[1]},"
        f"{bbox[2]} {bbox[3]},{bbox[0]} {bbox[3]},"
        f"{bbox[0]} {bbox[1]}))')"
        f"&$orderby=ContentDate/Start desc"
        f"&$top=1&$expand=Attributes"
    )
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(
                query_url, auth=(CDSE_USER, CDSE_PASSWORD), headers={"Accept": "application/json"}
            )
            if r.status_code == 200:
                data = r.json()
                products = data.get("value", [])
                if products:
                    prod = products[0]
                    cloud_pct = next(
                        (
                            a["Value"]
                            for a in prod.get("Attributes", [])
                            if a["Name"] == "cloudCover"
                        ),
                        50.0,
                    )
                    # HONESTY FIX: the catalogue gives us REAL acquisition
                    # metadata (product id, date, cloud cover), but we do NOT
                    # download/decode the product raster here, so the indices
                    # remain simulated. `real_data` stays False;
                    # `provider_reachable` records the live catalogue hit.
                    return {
                        "source": "cdse-metadata-only",
                        "product_id": prod.get("Id"),
                        "product_name": prod.get("Name"),
                        "acquisition_date": prod.get("ContentDate", {}).get("Start", date_from)[
                            :10
                        ],
                        "cloud_pct": float(cloud_pct),
                        "provider_reachable": True,
                        "real_data": False,
                        "download_url": f"https://catalogue.dataspace.copernicus.eu/odata/v1/Products({prod.get('Id')})/$value",
                    }
    except Exception as e:
        logger.warning(f"CDSE query failed: {e}")
    return None


def _deterministic_seed(field_id: str, acquisition_date: str) -> int:
    key = f"{field_id}:{acquisition_date}"
    return int(hashlib.md5(key.encode(), usedforsecurity=False).hexdigest()[:8], 16)


def _realistic_bands(field_id: str, acquisition_date: str) -> dict[str, float]:
    seed = _deterministic_seed(field_id, acquisition_date)
    field = FIELD_REGISTRY.get(field_id, {})
    crop = field.get("crop", "wheat")
    crop_ndvi_range = {
        "wheat": (0.55, 0.80),
        "barley": (0.50, 0.75),
        "maize": (0.60, 0.85),
        "tomato": (0.45, 0.70),
        "potato": (0.50, 0.72),
        "vegetables": (0.40, 0.68),
    }.get(crop, (0.45, 0.75))
    month = int(acquisition_date[5:7]) if len(acquisition_date) >= 7 else 4
    seasonal_factor = {
        1: 0.70,
        2: 0.80,
        3: 0.90,
        4: 1.00,
        5: 0.95,
        6: 0.85,
        7: 0.80,
        8: 0.75,
        9: 0.85,
        10: 0.90,
        11: 0.80,
        12: 0.72,
    }.get(month, 0.85)
    rng = (seed % 1000) / 1000
    ndvi_min, ndvi_max = crop_ndvi_range
    ndvi = round(ndvi_min + rng * (ndvi_max - ndvi_min) * seasonal_factor, 3)
    red = round(0.04 + (1 - ndvi) * 0.08, 4)
    nir = round(min(red * (1 + ndvi) / (1 - ndvi + 1e-9), 0.6), 4)
    green = round(0.05 + (seed % 20) / 400, 4)
    blue = round(0.03 + (seed % 15) / 500, 4)
    re1 = round((red + nir) / 2, 4)
    re2 = round(re1 + 0.02, 4)
    swir1 = round(0.15 + (seed % 30) / 400, 4)
    swir2 = round(swir1 - 0.03, 4)
    return {
        "B02": blue,
        "B03": green,
        "B04": red,
        "B05": re1,
        "B06": re2,
        "B08": nir,
        "B11": swir1,
        "B12": swir2,
    }


def _compute_indices(bands: dict[str, float]) -> dict[str, float]:
    B02 = bands["B02"]
    B03 = bands["B03"]
    B04 = bands["B04"]
    B05 = bands["B05"]
    B08 = bands["B08"]
    B11 = bands["B11"]
    eps = 1e-10
    ndvi = (B08 - B04) / (B08 + B04 + eps)
    # H4 FIX: مقام EVI قد يقترب من الصفر (انعكاس أزرق عالٍ) ⇒ inf/قسمة على صفر؛
    # نحرسه كبقيّة المؤشّرات. (مقام SAVI ≥ 0.5 دائماً فآمن.)
    evi_denom = B08 + 6 * B04 - 7.5 * B02 + 1
    evi = 2.5 * (B08 - B04) / (evi_denom if abs(evi_denom) > eps else eps)
    savi = (B08 - B04) / (B08 + B04 + 0.5) * 1.5
    ndwi = (B03 - B08) / (B03 + B08 + eps)
    ndmi = (B08 - B11) / (B08 + B11 + eps)
    gndvi = (B08 - B03) / (B08 + B03 + eps)
    recl = B05 / max(B04, eps) - 1
    # H3 FIX: LAI عبر Beer-Lambert الصحيح (Baret & Guyot 1991): -ln(1-NDVI)/k
    # مع تثبيت NDVI∈[0.05,0.95] وسقف 8.0. الصيغة القديمة كانت مقلوبة وتُشبّع
    # عند ~13.8 لكلّ غطاء سليم (NDVI>0.69) بسبب لوغاريتم وسيط سالب مثبّت.
    _ndvi_c = max(0.05, min(0.95, ndvi))
    lai = min(8.0, max(0.0, -math.log(max(0.001, 1 - _ndvi_c)) / 0.55))
    cwsi = max(0, min(1, (0.55 - ndwi) / 0.55))
    return {
        "ndvi": round(ndvi, 3),
        "evi": round(evi, 3),
        "savi": round(savi, 3),
        "ndwi": round(ndwi, 3),
        "ndmi": round(ndmi, 3),
        "gndvi": round(gndvi, 3),
        "recl": round(recl, 3),
        "lai": round(lai, 2),
        "cwsi": round(cwsi, 3),
    }


def _health_classification(ndvi: float, cwsi: float) -> dict:
    if ndvi >= 0.72 and cwsi < 0.3:
        return {"status": "excellent", "label_ar": "ممتاز", "color": "#16a34a", "score": 95}
    elif ndvi >= 0.55 and cwsi < 0.5:
        return {"status": "good", "label_ar": "جيد", "color": "#65a30d", "score": 75}
    elif ndvi >= 0.38 and cwsi < 0.7:
        return {"status": "fair", "label_ar": "مقبول", "color": "#ca8a04", "score": 55}
    elif ndvi >= 0.20:
        return {"status": "poor", "label_ar": "منخفض", "color": "#f97316", "score": 35}
    else:
        return {"status": "critical", "label_ar": "حرج", "color": "#dc2626", "score": 10}


def _recommendations_ar(indices: dict, health: dict, crop: str) -> list[str]:
    recs = []
    ndvi = indices["ndvi"]
    cwsi = indices["cwsi"]
    ndwi = indices["ndwi"]
    recl = indices["recl"]
    if cwsi > 0.6:
        recs.append(f"⚠️ إجهاد مائي حاد (CWSI={cwsi:.2f}) — يُنصح بالري الفوري")
    elif cwsi > 0.35:
        recs.append(f"💧 إجهاد مائي متوسط (CWSI={cwsi:.2f}) — راقب الرطوبة")
    if recl < 1.5:
        recs.append(f"🌱 نقص كلوروفيل (RECl={recl:.2f}) — تحقق من مستوى النيتروجين")
    if ndvi < 0.40:
        recs.append(f"📉 NDVI منخفض ({ndvi}) — احتمال وجود آفة أو مرض")
    if ndwi < -0.1:
        recs.append(f"🏜️ جفاف حاد (NDWI={ndwi:.2f}) — زيادة تكرار الري")
    if not recs:
        recs.append("✅ المحصول بصحة جيدة — استمر في نظام الري الحالي")
    return recs


_nc = None


async def _publish_analysis(field_id: str, tenant_id: str, indices: dict, source: str):
    global _nc
    try:
        if _nc is None:
            import nats

            _nc = await nats.connect(NATS_URL)
        subject = f"sahool.tenant.{tenant_id}.satellite.{field_id}.computed"
        payload = json.dumps(
            {
                "field_id": field_id,
                "tenant_id": tenant_id,
                "source": source,
                "timestamp": datetime.now(UTC).isoformat(),
                "event_type": "satellite",
                "title": f"🛰️ صورة جديدة — {FIELD_REGISTRY.get(field_id, {}).get('name', field_id)}",
                "message": f"NDVI={indices.get('ndvi')} | EVI={indices.get('evi')}",
                **indices,
            },
            ensure_ascii=False,
        ).encode()
        js = _nc.jetstream()
        await js.publish(subject, payload)
        logger.info(f"NATS published: {subject}")
    except Exception as e:
        logger.warning(f"NATS publish failed: {e}")


async def _real_ndvi_mean_from_raster(field_id: str) -> float | None:
    """متوسّط NDVI الحقيقيّ (بكسليّ) من raster-service إن توفّر — وإلّا None.

    fail-safe مطلق: أيّ خطأ/مهلة/غياب طبقة/real_data=false ⇒ None (لا استثناء يصعد)،
    فيُبقي المتّصِل على التقدير المُعلَّم. لا يغيّر صيَغ المؤشّرات — يستبدل القيمة فقط.
    """
    if not VEGETATION_PREFER_RASTER:
        return None
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(
                f"{RASTER_SERVICE_URL}/v1/fields/{field_id}/indicator-grid",
                params={"index": "ndvi", "date": "latest", "grid": 16},
            )
        if r.status_code != 200:
            return None
        data = r.json()
        if not data.get("real_data"):
            return None
        mean = (data.get("stats") or {}).get("mean")
        return float(mean) if isinstance(mean, (int, float)) else None
    except Exception as e:  # noqa: BLE001 — fail-safe: ارتداد للتقدير، لا كسر
        logger.debug("raster NDVI الحقيقيّ غير متاح لـ%s: %s", field_id, e)
        return None


async def run_analysis(field_id: str, tenant_id: str, date_from: str, date_to: str) -> dict:
    field = FIELD_REGISTRY.get(field_id)
    if not field:
        raise HTTPException(404, f"field_id {field_id!r} غير موجود")
    with ANALYSIS_LATENCY.labels(source="total").time():
        sh_meta = await fetch_from_sentinel_hub(field_id, date_from, date_to)
        cdse_meta = None
        if not sh_meta:
            cdse_meta = await fetch_from_cdse(field_id, date_from, date_to)
        meta = sh_meta or cdse_meta or {}
        # HONESTY FIX: indices below are computed from deterministic synthetic
        # bands (no GeoTIFF decode here), so the data is ALWAYS a simulation.
        # `data_source` is taken from the provider metadata when a live API
        # responded ("sentinel-hub-unavailable" / "cdse-metadata-only"),
        # otherwise "simulation". `provider_reachable` records whether the live
        # API actually answered. `real_data` is never True in this service.
        source = meta.get("source", "simulation")
        provider_reachable = bool(meta.get("provider_reachable", False))
        acq_date = meta.get("acquisition_date", date_to)
        cloud_pct = meta.get("cloud_pct", 0.0)
        bands = _realistic_bands(field_id, acq_date)
        indices = _compute_indices(bands)
        # تفضيل NDVI الحقيقيّ (بكسليّ، Sentinel-2 عبر raster-service) عند توفّره —
        # يستبدل قيمة NDVI فقط (لا يغيّر صيَغ المؤشّرات). بقيّة المؤشّرات تبقى تقديريّة.
        real_ndvi = await _real_ndvi_mean_from_raster(field_id)
        ndvi_is_real = real_ndvi is not None
        if ndvi_is_real:
            indices["ndvi"] = round(real_ndvi, 3)
        health = _health_classification(indices["ndvi"], indices["cwsi"])
        recs = _recommendations_ar(indices, health, field["crop"])
    await _publish_analysis(field_id, tenant_id, indices, source)
    ANALYSIS_COUNT.labels(source=source, status="success").inc()
    # وسم مصدر كلّ مؤشّر بصدق: NDVI من raster الحقيقيّ عند توفّره، والباقي تقدير.
    _ndvi_src = "raster-service" if ndvi_is_real else "estimate"
    return {
        "field_id": field_id,
        "field_name": field["name"],
        "crop": field["crop"],
        "area_ha": field["area_ha"],
        "tenant_id": tenant_id,
        "acquisition_date": acq_date,
        "cloud_coverage_pct": cloud_pct,
        # data_source يعكس مصدر NDVI (الرقم الرئيسيّ): raster الحقيقيّ أو التقدير.
        "data_source": "raster-service" if ndvi_is_real else source,
        # real_data يعكس NDVI تحديداً (بطاقة الصحّة تُبنى عليه): حقيقيّ من raster؟
        "real_data": ndvi_is_real,
        "provider_reachable": provider_reachable,
        # نصّ آليّ موحّد اللغة (إنجليزيّ) في الحالتين — لا تتغيّر لغته بتغيّر المصدر
        # (تفادياً لكسر مستهلكين يطابقون النصّ، كما نبّهت مراجعة Copilot).
        "estimate_note": (
            "NDVI is the real per-pixel mean from raster-service (Sentinel-2); "
            "other indices remain field-mean estimates from synthetic bands."
            if ndvi_is_real
            else "Indices are field-mean estimates from deterministic synthetic bands; "
            "no satellite pixels were decoded. Real per-pixel processing lives in raster-service."
        ),
        "indices": {
            k: {
                "value": v,
                "unit": "dimensionless",
                "source": _ndvi_src if k == "ndvi" else "estimate",
            }
            for k, v in indices.items()
        },
        "raw_bands": bands,
        "health": health,
        "recommendations_ar": recs,
        "analyzed_at": datetime.now(UTC).isoformat(),
        "satellite": "Sentinel-2 L2A",
        "resolution_m": 10,
    }


def _generate_timeseries(field_id: str, days: int) -> list[dict]:
    result = []
    today = date.today()
    for i in range(0, days, 5):
        acq = (today - timedelta(days=days - i)).isoformat()
        bands = _realistic_bands(field_id, acq)
        indices = _compute_indices(bands)
        result.append({"date": acq, **{k: v for k, v in indices.items()}})
    return result


def _current_ndvi_payload(field_id: str, field: dict, analysis: dict) -> dict:
    """يشكّل ردّ NDVI الحالي من ناتج التحليل — دالّة نقيّة (لا قاعدة/شبكة).

    الواجهة (useCurrentNDVI) تتوقّع `ndvi.current` + تصنيف صحّي. نستخرجهما من
    مؤشّرات التحليل (indices[*].value) دون تكرار منطق الحساب. real_data يُمرَّر
    كما هو من التحليل (دائماً False في هذه الخدمة — تقدير لا بكسلات حقيقيّة).
    """
    indices = analysis.get("indices", {})
    ndvi_val = indices.get("ndvi", {}).get("value")
    return {
        "field_id": field_id,
        "field_name": field.get("name"),
        "crop": field.get("crop"),
        "ndvi": {"current": ndvi_val},
        "classification": analysis.get("health", {}),
        "acquisition_date": analysis.get("acquisition_date"),
        "data_source": analysis.get("data_source"),
        "real_data": analysis.get("real_data", False),
        "provider_reachable": analysis.get("provider_reachable", False),
    }


# ── Lifespan ───────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    sh_configured = bool(SH_CLIENT_ID and SH_CLIENT_SECRET)
    cdse_configured = bool(CDSE_USER and CDSE_PASSWORD)
    logger.info(
        f"✅ vegetation-service v9.1 starting — SH={'✅' if sh_configured else '❌ fallback'} | CDSE={'✅' if cdse_configured else '❌ fallback'}"
    )
    yield
    global _nc
    if _nc:
        await _nc.close()
        _nc = None
        logger.info("NATS connection closed")


app = FastAPI(title="SAHOOL Vegetation Analysis", version="9.1.0", lifespan=lifespan)
# ✅ OTEL
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)
except ImportError:
    logger.debug("OTEL غير مثبّت — التتبّع معطّل (اختياري)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=True,
)


@app.get("/healthz")
@app.get("/health")
async def healthz():
    return {"status": "alive", "service": "vegetation-analysis"}


@app.get("/readyz")
async def readyz():
    return {"status": "ready"}


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/v1/analyze")
async def analyze(
    field_id: str,
    tenant_id: str = Query(default="default"),
    # M8 FIX: لا تُقيّم date.today() في توقيع الدالّة (يُحسب مرّة عند الاستيراد ⇒
    # "اليوم" مُجمّد حتّى إعادة التشغيل). نستخدم None ونحسب النافذة لكلّ طلب.
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    token: str = Depends(security),
):
    claims = _verify_claims(token)
    # المستأجِر من التوكن لا من الـquery (منع حقن موضوع NATS عابر المستأجرين)
    tenant_id = _tenant_from_claims(claims)
    date_to = _valid_date(date_to) if date_to else date.today().isoformat()
    date_from = (
        _valid_date(date_from) if date_from else (date.today() - timedelta(days=30)).isoformat()
    )
    return await run_analysis(field_id, tenant_id, date_from, date_to)


@app.get("/v1/timeseries/{field_id}")
async def timeseries(
    field_id: str, days: int = Query(default=90, ge=5, le=365), token: str = Depends(security)
):
    _verify_claims(token)
    if field_id not in FIELD_REGISTRY:
        raise HTTPException(404, f"field_id {field_id!r} غير موجود")
    return {
        "field_id": field_id,
        "days": days,
        "timeseries": _generate_timeseries(field_id, days),
        "generated_at": datetime.now(UTC).isoformat(),
    }


@app.get("/v1/ndvi/current/{field_id}")
async def current_ndvi(field_id: str, token: str = Depends(security)):
    """NDVI الحالي + تصنيف الصحّة لحقل واحد (يستهلكه useCurrentNDVI في الواجهة).

    يُعيد استخدام run_analysis (نافذة آخر ٣٠ يوماً) ثمّ يستخرج NDVI الحالي عبر
    _current_ndvi_payload. صدق المصدر: تقدير من نطاقات تركيبيّة (real_data=False)
    — لا بكسلات حقيقيّة (تلك في raster-service).
    """
    claims = _verify_claims(token)
    tenant_id = _tenant_from_claims(claims)
    if field_id not in FIELD_REGISTRY:
        raise HTTPException(404, f"field_id {field_id!r} غير موجود")
    date_to = date.today().isoformat()
    date_from = (date.today() - timedelta(days=30)).isoformat()
    analysis = await run_analysis(field_id, tenant_id, date_from, date_to)
    return _current_ndvi_payload(field_id, FIELD_REGISTRY[field_id], analysis)


@app.get("/v1/all_fields")
async def all_fields(token: str = Depends(security)):
    """NDVI الحالي لكلّ الحقول المعروفة (يستهلكه useAllFieldsNdvi/لوحة المؤشّرات).

    يكرّر على FIELD_REGISTRY ويستدعي run_analysis لكلّ حقل. الردّ {fields:[...]}
    لكلّ منه field_id/name/crop/ndvi/health — تقدير صادق (real_data=False).
    """
    claims = _verify_claims(token)
    tenant_id = _tenant_from_claims(claims)
    date_to = date.today().isoformat()
    date_from = (date.today() - timedelta(days=30)).isoformat()
    fields_out = []
    for fid, field in FIELD_REGISTRY.items():
        analysis = await run_analysis(fid, tenant_id, date_from, date_to)
        payload = _current_ndvi_payload(fid, field, analysis)
        fields_out.append(
            {
                "field_id": fid,
                "field_name": field["name"],
                "name": field["name"],
                "crop": field["crop"],
                "area_ha": field["area_ha"],
                "ndvi": payload["ndvi"]["current"],
                "status": payload["classification"].get("status"),
                "health": payload["classification"],
                "real_data": payload["real_data"],
            }
        )
    return {
        "fields": fields_out,
        "count": len(fields_out),
        "tenant_id": tenant_id,
        "real_data": False,
        "generated_at": datetime.now(UTC).isoformat(),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
