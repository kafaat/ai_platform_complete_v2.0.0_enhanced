// AUTO-GENERATED from config/indicators_registry.json — do not edit by hand.
// Regenerate: python scripts/ci/generate_indicators_frontend_manifest.py
// Sync guard (--check) blocks drift from the canonical single source (WS-B.2).

export type IndicatorAvailability = 'active' | 'estimated' | 'unavailable';
export type IndicatorSourceClass = 'real' | 'estimated' | 'derived' | null;

export interface RegistryIndicator {
  id: string;
  name_ar: string | null;
  name_en: string | null;
  category: string | null;
  unit: string | null;
  range: [number, number] | null;
  renderable: boolean | null;
  source_class: IndicatorSourceClass;
  availability: IndicatorAvailability;
}

export const REGISTRY_VERSION = 'd5c07398457b';
export const REGISTRY_DIGEST = 'sha256:d5c07398457be83abaab6928d48dca6c57d357b134c25c1679db3e8b811ec408';

export const INDICATORS_MANIFEST: RegistryIndicator[] = [
  {
    "id": "ndvi",
    "name_ar": "NDVI",
    "name_en": "Normalized Difference Vegetation Index",
    "category": "vegetation",
    "unit": "",
    "range": [
      -1,
      1
    ],
    "renderable": true,
    "source_class": "real",
    "availability": "active"
  },
  {
    "id": "evi",
    "name_ar": "EVI",
    "name_en": "Enhanced Vegetation Index",
    "category": "vegetation",
    "unit": "",
    "range": [
      -1,
      1
    ],
    "renderable": true,
    "source_class": "real",
    "availability": "active"
  },
  {
    "id": "ndre",
    "name_ar": "NDRE",
    "name_en": "Normalized Difference Red-Edge Index",
    "category": "vegetation",
    "unit": "",
    "range": [
      -1,
      1
    ],
    "renderable": true,
    "source_class": "real",
    "availability": "active"
  },
  {
    "id": "msavi",
    "name_ar": "MSAVI",
    "name_en": "Modified Soil-Adjusted Vegetation Index",
    "category": "vegetation",
    "unit": "",
    "range": [
      -1,
      1
    ],
    "renderable": true,
    "source_class": "real",
    "availability": "active"
  },
  {
    "id": "savi",
    "name_ar": "SAVI",
    "name_en": "Soil-Adjusted Vegetation Index",
    "category": "vegetation",
    "unit": "",
    "range": [
      -1,
      1
    ],
    "renderable": true,
    "source_class": "real",
    "availability": "active"
  },
  {
    "id": "gndvi",
    "name_ar": "GNDVI",
    "name_en": "Green Normalized Difference Vegetation Index",
    "category": "vegetation",
    "unit": "",
    "range": [
      -1,
      1
    ],
    "renderable": true,
    "source_class": "real",
    "availability": "active"
  },
  {
    "id": "ndwi",
    "name_ar": "NDWI",
    "name_en": "Normalized Difference Water Index",
    "category": "water",
    "unit": "",
    "range": [
      -1,
      1
    ],
    "renderable": true,
    "source_class": "real",
    "availability": "active"
  },
  {
    "id": "ndmi",
    "name_ar": "NDMI (الرطوبة)",
    "name_en": "Normalized Difference Moisture Index",
    "category": "water",
    "unit": "",
    "range": [
      -1,
      1
    ],
    "renderable": true,
    "source_class": "real",
    "availability": "active"
  },
  {
    "id": "msi",
    "name_ar": "MSI (الإجهاد المائي)",
    "name_en": "Moisture Stress Index",
    "category": "water",
    "unit": "",
    "range": null,
    "renderable": true,
    "source_class": "real",
    "availability": "active"
  },
  {
    "id": "salinity",
    "name_ar": "الملوحة (SI)",
    "name_en": "Salinity Index",
    "category": "soil",
    "unit": "",
    "range": [
      -1,
      1
    ],
    "renderable": true,
    "source_class": "real",
    "availability": "active"
  },
  {
    "id": "reci",
    "name_ar": "RECI",
    "name_en": "Red-Edge Chlorophyll Index",
    "category": "vegetation",
    "unit": "",
    "range": null,
    "renderable": true,
    "source_class": "real",
    "availability": "active"
  },
  {
    "id": "gci",
    "name_ar": "GCI",
    "name_en": "Green Chlorophyll Index",
    "category": "vegetation",
    "unit": "",
    "range": null,
    "renderable": true,
    "source_class": "real",
    "availability": "active"
  },
  {
    "id": "arvi",
    "name_ar": "ARVI",
    "name_en": "Atmospherically Resistant Vegetation Index",
    "category": "vegetation",
    "unit": "",
    "range": [
      -1,
      1
    ],
    "renderable": true,
    "source_class": "real",
    "availability": "active"
  },
  {
    "id": "sipi",
    "name_ar": "SIPI",
    "name_en": "Structure Insensitive Pigment Index",
    "category": "vegetation",
    "unit": "",
    "range": null,
    "renderable": true,
    "source_class": "real",
    "availability": "active"
  },
  {
    "id": "nbr",
    "name_ar": "NBR",
    "name_en": "Normalized Burn Ratio",
    "category": "vegetation",
    "unit": "",
    "range": [
      -1,
      1
    ],
    "renderable": true,
    "source_class": "real",
    "availability": "active"
  },
  {
    "id": "ccci",
    "name_ar": "CCCI",
    "name_en": "Canopy Chlorophyll Content Index",
    "category": "vegetation",
    "unit": "",
    "range": null,
    "renderable": true,
    "source_class": "real",
    "availability": "active"
  },
  {
    "id": "vari",
    "name_ar": "VARI",
    "name_en": "Visible Atmospherically Resistant Index",
    "category": "vegetation",
    "unit": "",
    "range": null,
    "renderable": true,
    "source_class": "real",
    "availability": "active"
  },
  {
    "id": "gli",
    "name_ar": "GLI",
    "name_en": "Green Leaf Index",
    "category": "vegetation",
    "unit": "",
    "range": null,
    "renderable": true,
    "source_class": "real",
    "availability": "active"
  },
  {
    "id": "bsi",
    "name_ar": "BSI",
    "name_en": "Bare Soil Index",
    "category": "soil",
    "unit": "",
    "range": [
      -1,
      1
    ],
    "renderable": true,
    "source_class": "real",
    "availability": "active"
  },
  {
    "id": "lai",
    "name_ar": "LAI",
    "name_en": "Leaf Area Index",
    "category": "vegetation",
    "unit": "m²/m²",
    "range": [
      0,
      8
    ],
    "renderable": false,
    "source_class": "estimated",
    "availability": "estimated"
  },
  {
    "id": "recl",
    "name_ar": "RECl",
    "name_en": "Red-Edge Chlorophyll (estimate)",
    "category": "vegetation",
    "unit": "",
    "range": null,
    "renderable": false,
    "source_class": "estimated",
    "availability": "estimated"
  },
  {
    "id": "cwsi",
    "name_ar": "CWSI",
    "name_en": "Crop Water Stress Index",
    "category": "water",
    "unit": "",
    "range": [
      0,
      1
    ],
    "renderable": false,
    "source_class": "estimated",
    "availability": "unavailable"
  },
  {
    "id": "et0",
    "name_ar": "ET₀",
    "name_en": "Reference Evapotranspiration (FAO-56)",
    "category": "water",
    "unit": "mm/d",
    "range": null,
    "renderable": false,
    "source_class": "derived",
    "availability": "active"
  },
  {
    "id": "water_deficit",
    "name_ar": "عجز المياه",
    "name_en": "Water Deficit",
    "category": "water",
    "unit": "mm",
    "range": null,
    "renderable": false,
    "source_class": "derived",
    "availability": "active"
  },
  {
    "id": "gdd",
    "name_ar": "GDD المتراكم",
    "name_en": "Accumulated Growing Degree Days",
    "category": "weather",
    "unit": "°C·يوم",
    "range": null,
    "renderable": false,
    "source_class": "derived",
    "availability": "active"
  },
  {
    "id": "temperature",
    "name_ar": "الحرارة",
    "name_en": "Air Temperature",
    "category": "weather",
    "unit": "°C",
    "range": null,
    "renderable": false,
    "source_class": "real",
    "availability": "active"
  },
  {
    "id": "humidity",
    "name_ar": "الرطوبة النسبيّة",
    "name_en": "Relative Humidity",
    "category": "weather",
    "unit": "%",
    "range": [
      0,
      100
    ],
    "renderable": false,
    "source_class": "real",
    "availability": "active"
  },
  {
    "id": "wind_speed",
    "name_ar": "الرياح",
    "name_en": "Wind Speed",
    "category": "weather",
    "unit": "km/h",
    "range": null,
    "renderable": false,
    "source_class": "real",
    "availability": "active"
  },
  {
    "id": "soil_ph",
    "name_ar": "pH التربة",
    "name_en": "Soil pH",
    "category": "soil",
    "unit": "",
    "range": [
      0,
      14
    ],
    "renderable": false,
    "source_class": "real",
    "availability": "active"
  },
  {
    "id": "soil_ec",
    "name_ar": "EC التربة",
    "name_en": "Soil Electrical Conductivity",
    "category": "soil",
    "unit": "dS/m",
    "range": null,
    "renderable": false,
    "source_class": "real",
    "availability": "active"
  },
  {
    "id": "nitrogen",
    "name_ar": "النيتروجين المتاح",
    "name_en": "Available Nitrogen",
    "category": "soil",
    "unit": "mg/kg",
    "range": null,
    "renderable": false,
    "source_class": "real",
    "availability": "active"
  },
  {
    "id": "soil_moisture",
    "name_ar": "رطوبة التربة",
    "name_en": "Soil Moisture",
    "category": "water",
    "unit": "%",
    "range": [
      0,
      100
    ],
    "renderable": false,
    "source_class": "real",
    "availability": "active"
  },
  {
    "id": "wue",
    "name_ar": "كفاءة الري",
    "name_en": "Water Use Efficiency",
    "category": "water",
    "unit": "kg/m³",
    "range": null,
    "renderable": false,
    "source_class": "derived",
    "availability": "active"
  }
];
