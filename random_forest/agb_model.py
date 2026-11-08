"""
SAHOOL v9.0 — random_forest/agb_model.py
══════════════════════════════════════════
نموذج بحثي لتقدير AGB؛ التدريب الافتراضي يستخدم بيانات اصطناعية فقط.
المعاملات والإحالة البحثية الموروثة غير موثقة هنا، ولا توجد معايرة ميدانية
أو بيانات مستقلة تثبت دقة التنبؤ أو تغطية فترات التنبؤ.

المدخلات التي يمكن للنموذج استخدامها:
  - NDVI, EVI, GNDVI (Sentinel-2)
  - VV, VH backscatter (Sentinel-1)
  - CHM height (UAV-LiDAR)
  - Point density (UAV)
  - Canopy cover %
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

# نستخدم sklearn إذا توفرت، وإلا نُشغّل معادلة تقديرية غير مُعايَرة.
try:
    import numpy as np
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.preprocessing import StandardScaler

    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False


@dataclass
class AGBFeatures:
    """مدخلات النموذج البحثي؛ توافرها لا يثبت معايرة النموذج."""

    ndvi: float  # Sentinel-2 Band Ratio [-1,1]
    evi: float  # Enhanced Vegetation Index
    gndvi: float  # Green NDVI
    savi: float  # Soil-Adjusted VI
    vv_backscatter: float = -12.0  # Sentinel-1 VV (dB)
    vh_backscatter: float = -18.0  # Sentinel-1 VH (dB)
    chm_mean: float = 0.0  # Canopy Height Model mean (m) — UAV
    point_density: float = 0.0  # LiDAR points/m² — UAV
    canopy_cover: float = 0.5  # fraction [0,1]
    crop: str = "قمح صلب"
    area_ha: float = 1.0


class SAHOOLAGBModel:
    """
    نموذج AGB بحثي غير مُعايَر ميدانياً.

    بعد train_synthetic: غابة عشوائية من 100 شجرة تتعلّم بيانات اصطناعية.
    قبل التدريب أو بدون sklearn: معادلة تقديرية باسم تاريخي «Equation 4».
    لا يمثّل أي من المسارين تحققاً من دقة النموذج على محاصيل أو حقول حقيقية.
    """

    # معاملات موروثة لكل محصول؛ لم يُثبت مصدرها أو معايرتها في هذا التنفيذ.
    EQ4_COEFFICIENTS = {
        "قمح صلب": {
            "intercept": -12.0,
            "ndvi": 125.0,
            "evi": 45.0,
            "gndvi": 38.0,
            "vv": 2.1,
            "vh": 1.8,
            "hi": 0.40,
        },
        "شعير": {
            "intercept": -10.0,
            "ndvi": 118.0,
            "evi": 42.0,
            "gndvi": 35.0,
            "vv": 2.0,
            "vh": 1.7,
            "hi": 0.38,
        },
        "ذرة صفراء": {
            "intercept": -20.0,
            "ndvi": 210.0,
            "evi": 75.0,
            "gndvi": 65.0,
            "vv": 3.5,
            "vh": 2.8,
            "hi": 0.45,
        },
        "طماطم": {
            "intercept": -15.0,
            "ndvi": 180.0,
            "evi": 60.0,
            "gndvi": 55.0,
            "vv": 2.8,
            "vh": 2.2,
            "hi": 0.70,
        },
        "بطاطس": {
            "intercept": -14.0,
            "ndvi": 160.0,
            "evi": 55.0,
            "gndvi": 45.0,
            "vv": 2.5,
            "vh": 2.0,
            "hi": 0.75,
        },
        "خضروات": {
            "intercept": -12.0,
            "ndvi": 145.0,
            "evi": 50.0,
            "gndvi": 42.0,
            "vv": 2.3,
            "vh": 1.9,
            "hi": 0.65,
        },
    }

    # Keep the legacy accuracy interface unavailable. These inherited numbers
    # have no verified paper identifier or link to this model's evaluation.
    MODEL_ACCURACY = None
    LEGACY_PAPER_REFERENCE = {
        "r2": 0.89,
        "rmse_t_ha": 9.1,
        "paper": "Plant Methods 2023",
        "status": "unverified_reference",
        "applies_to_this_model": False,
    }

    def __init__(self):
        self._rf_model = None
        self._scaler = None
        self._trained = False
        self._training_provenance = None
        self._training_metrics = None

        if HAS_SKLEARN:
            self._rf_model = RandomForestRegressor(
                n_estimators=100,
                max_depth=8,
                min_samples_leaf=3,
                random_state=42,
                n_jobs=-1,
            )
            self._scaler = StandardScaler()

    def _equation4(self, f: AGBFeatures) -> float:
        """معادلة تقديرية موروثة؛ اسمها التاريخي لا يثبت إحالة بحثية أو معايرة."""
        c = self.EQ4_COEFFICIENTS.get(f.crop, self.EQ4_COEFFICIENTS["قمح صلب"])

        # الإشعاع الراداري يُضاف كمُصحِّح (Sentinel-1)
        sar_correction = (
            0.01 * (f.vv_backscatter + 20) * c["vv"] + 0.008 * (f.vh_backscatter + 25) * c["vh"]
        )

        agb = (
            c["intercept"]
            + c["ndvi"] * f.ndvi
            + c["evi"] * f.evi
            + c["gndvi"] * f.gndvi
            + sar_correction
            +
            # تأثير الغطاء الشجري (إذا توفر من UAV)
            f.canopy_cover * 8.0
            + f.chm_mean * 2.5
        )
        return max(0.1, min(40.0, agb))

    def predict(self, f: AGBFeatures) -> dict:
        """
        تقدير بحثي لـ AGB بالـ t/ha مع بيان المنشأ وحدود الدليل.

        حدود فترات التنبؤ والثقة والدقة تظل None لغياب تحقق مستقل.
        تشتت الأشجار أو نطاق نسبي حول المعادلة لا يثبت تغطية احتمالية.
        """
        limitations = [
            "no_independent_field_validation",
            "prediction_interval_not_calibrated",
            "yield_uses_fixed_harvest_index",
        ]
        if self._trained and HAS_SKLEARN and self._rf_model:
            X = np.array(
                [
                    [
                        f.ndvi,
                        f.evi,
                        f.gndvi,
                        f.savi,
                        f.vv_backscatter,
                        f.vh_backscatter,
                        f.chm_mean,
                        f.point_density,
                        f.canopy_cover,
                    ]
                ]
            )
            X_scaled = self._scaler.transform(X)

            # Preserve the historical point estimate. Tree dispersion is not a
            # calibrated prediction interval and is deliberately not exposed as one.
            tree_preds = np.array(
                [tree.predict(X_scaled)[0] for tree in self._rf_model.estimators_]
            )
            raw_mean = float(np.mean(tree_preds))
            # Legacy numerical bound, not evidence of agronomic validity.
            agb_mean = max(1.0, min(25.0, raw_mean))
            method = "random-forest-sklearn"
            # Legacy/imported objects may lack provenance. A fitted forest alone
            # never establishes whether its data were synthetic or observed.
            provenance = deepcopy(getattr(self, "_training_provenance", None)) or {
                "source": "unknown",
                "n_samples": None,
                "field_observations": None,
            }
            training_metrics = deepcopy(getattr(self, "_training_metrics", None))
            if provenance["source"] == "synthetic":
                limitations.append("training_data_are_synthetic")
            elif provenance["source"] == "unknown":
                limitations.append("training_provenance_unknown")
            optical_features = ["NDVI", "EVI", "GNDVI", "SAVI"]
            uav_features = ["CHM", "point density", "canopy cover"]
        else:
            agb_mean = self._equation4(f)
            method = "equation4-heuristic"
            provenance = {"source": "not_trained", "n_samples": 0, "field_observations": 0}
            training_metrics = None
            limitations.append("heuristic_coefficients_not_calibrated")
            optical_features = ["NDVI", "EVI", "GNDVI"]
            uav_features = ["CHM", "canopy cover"]

        c = self.EQ4_COEFFICIENTS.get(f.crop, self.EQ4_COEFFICIENTS["قمح صلب"])
        yield_t_ha = agb_mean * c["hi"]

        return {
            "agb_t_ha": round(agb_mean, 2),
            "agb_t_ha_lower": None,
            "agb_t_ha_upper": None,
            "yield_t_ha": round(yield_t_ha, 3),
            "total_agb_t": round(agb_mean * f.area_ha, 1),
            "total_yield_t": round(yield_t_ha * f.area_ha, 1),
            "confidence_pct": None,
            "method": method,
            "model_accuracy": None,
            "research_only": True,
            "calibrated_for_this_field": False,
            "confidence_calibrated": False,
            "prediction_interval": {
                "status": "unavailable",
                "reason": "no_independent_calibration",
                "coverage_pct": None,
            },
            "training_provenance": provenance,
            "training_metrics": training_metrics,
            "legacy_paper_reference": deepcopy(self.LEGACY_PAPER_REFERENCE),
            "limitations": limitations,
            "features_used": {
                "sentinel_2": optical_features,
                "sentinel_1": ["VV backscatter", "VH backscatter"],
                "uav": uav_features,
            },
        }

    def train_synthetic(self, n_samples: int = 500):
        """
        تدريب بحثي على مخرجات المعادلة التقديرية مع ضجيج اصطناعي.
        المقاييس المحسوبة على عينات التدريب نفسها ليست تحققاً مستقلاً
        ولا دليلاً على الدقة الميدانية أو معايرة الثقة.
        """
        if not HAS_SKLEARN:
            return False

        rng = np.random.default_rng(42)  # seed ثابت — لا random عشوائي

        # نطاقات توضيحية ثابتة، وليست قياسات مأخوذة من حقول.
        X, y = [], []
        for _ in range(n_samples):
            ndvi = rng.uniform(0.1, 0.85)
            evi = ndvi * rng.uniform(0.80, 0.95)
            gndvi = ndvi * rng.uniform(0.85, 0.98)
            savi = ndvi * rng.uniform(0.88, 0.95)
            vv = rng.uniform(-20, -8)
            vh = rng.uniform(-28, -14)
            chm = rng.uniform(0, 2.5)  # محاصيل: 0-2.5m
            dens = rng.uniform(5, 50)
            cover = rng.uniform(0.3, 0.95)
            crop = rng.choice(list(self.EQ4_COEFFICIENTS.keys()))

            feat = AGBFeatures(
                ndvi=ndvi,
                evi=evi,
                gndvi=gndvi,
                savi=savi,
                vv_backscatter=vv,
                vh_backscatter=vh,
                chm_mean=chm,
                point_density=dens,
                canopy_cover=cover,
                crop=crop,
            )
            agb_synthetic = self._equation4(feat) + rng.normal(0, 1.5)  # std = 1.5 t/ha

            X.append([ndvi, evi, gndvi, savi, vv, vh, chm, dens, cover])
            y.append(max(0.1, agb_synthetic))

        X = np.array(X)
        y = np.array(y)
        X_scaled = self._scaler.fit_transform(X)
        self._rf_model.fit(X_scaled, y)
        self._trained = True
        self._training_provenance = {
            "source": "synthetic",
            "generator": "equation4_heuristic_plus_gaussian_noise",
            "n_samples": n_samples,
            "seed": 42,
            "field_observations": 0,
        }

        # Resubstitution on the training rows, before predict()'s legacy clipping.
        # No holdout, cross-validation, field observations or interval calibration.
        y_pred = self._rf_model.predict(X_scaled)
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r2 = float(1 - ss_res / ss_tot) if ss_tot > 0 else None
        rmse = np.sqrt(np.mean((y - y_pred) ** 2))

        self._training_metrics = {
            "r2": round(r2, 3) if r2 is not None else None,
            "rmse": round(float(rmse), 2),
            "n_samples": n_samples,
            "rmse_unit": "t/ha",
            "evaluation_split": "training_resubstitution",
            "prediction_stage": "unclipped_estimator",
            "target_source": "synthetic_equation4_heuristic",
            "held_out_samples": 0,
            "field_observations": 0,
        }
        return deepcopy(self._training_metrics)


# Singleton
_agb_model: SAHOOLAGBModel | None = None


def get_agb_model() -> SAHOOLAGBModel:
    global _agb_model
    if _agb_model is None:
        _agb_model = SAHOOLAGBModel()
        if HAS_SKLEARN:
            result = _agb_model.train_synthetic(n_samples=500)
            print(
                "AGB research prototype — synthetic data (n=500); "
                f"training resubstitution R²={result['r2']}, RMSE={result['rmse']} t/ha; "
                "no field validation"
            )
        else:
            print(
                "AGB research prototype — sklearn not available; "
                "using a heuristic equation (uncalibrated; no field validation)"
            )
    return _agb_model


# ── CLI testing ────────────────────────────────────────────────
if __name__ == "__main__":
    model = get_agb_model()

    # أمثلة حسابية فقط؛ ليست بيانات تحقق ميداني.
    test_cases = [
        (
            "example_01",
            "قمح صلب",
            AGBFeatures(ndvi=0.72, evi=0.61, gndvi=0.68, savi=0.65, area_ha=23.5, crop="قمح صلب"),
        ),
        (
            "example_02",
            "شعير",
            AGBFeatures(ndvi=0.58, evi=0.49, gndvi=0.55, savi=0.52, area_ha=32.0, crop="شعير"),
        ),
        (
            "example_03",
            "ذرة صفراء",
            AGBFeatures(ndvi=0.44, evi=0.37, gndvi=0.41, savi=0.40, area_ha=18.7, crop="ذرة صفراء"),
        ),
        (
            "example_04",
            "طماطم",
            AGBFeatures(ndvi=0.66, evi=0.56, gndvi=0.63, savi=0.60, area_ha=41.3, crop="طماطم"),
        ),
        (
            "example_05",
            "قمح صلب",
            AGBFeatures(ndvi=0.74, evi=0.63, gndvi=0.70, savi=0.67, area_ha=28.9, crop="قمح صلب"),
        ),
    ]

    print("\n═══════════════════════════════════════════════════════")
    print("SAHOOL AGB research prototype — أمثلة بحثية غير مُعايرة ميدانياً")
    print(f"{'المثال':<20} {'AGB t/ha':>10} {'Yield t/ha':>12} {'Prediction interval':>20}")
    print("═══════════════════════════════════════════════════════")

    for fid, crop, feat in test_cases:
        result = model.predict(feat)
        interval = "unavailable (uncalibrated)"
        print(
            f"{fid} ({crop})"
            f"  AGB={result['agb_t_ha']:>6.2f}"
            f"  Yield={result['yield_t_ha']:>6.3f}"
            f"  {interval}"
        )

    print("═══════════════════════════════════════════════════════")
    print(f"النموذج: {model.__class__.__name__}")
    print("Legacy paper numbers are an unverified reference, not this model's accuracy.")
    print(f"sklearn متاح: {HAS_SKLEARN}")
