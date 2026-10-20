// نسبةُ بيانات الطقس إلى Open-Meteo (شرط رخصة CC BY 4.0).
//
// Open-Meteo يُرخِّص بيانات واجهته بـCC BY 4.0، وشرطُه في README مستودعه
// (open-meteo/open-meteo، قسم «Data License»): «Include an attribution link next to any
// location where Open-Meteo data is displayed»، ومثالُه الحرفيّ رابطٌ إلى
// https://open-meteo.com/ بنصّ «Weather data by Open-Meteo.com». وCC BY 4.0 نفسها تطلب
// رابطاً إلى الرخصة. النصُّ والرابطان هنا في موضعٍ واحد: مكوّن
// `components/OpenMeteoAttribution` يُصيِّرها في شاشات الطقس، وطبقة Leaflet للطقس
// (`maphub/weather/WeatherTileLayer`) تمرّر الصيغة HTML إلى شريط نسب الخريطة.
// الحارس: tests_v9/test_map_and_weather_data_credit.py.

export const OPEN_METEO_URL = 'https://open-meteo.com/';
export const OPEN_METEO_CREDIT_TEXT = 'Weather data by Open-Meteo.com';
export const CC_BY_4_URL = 'https://creativecommons.org/licenses/by/4.0/';
export const CC_BY_4_LABEL = 'CC BY 4.0';

/** صيغة HTML لشريط نسب Leaflet (خيار `attribution` في الطبقة). */
export const OPEN_METEO_ATTRIBUTION_HTML =
  `<a href="${OPEN_METEO_URL}" target="_blank" rel="noopener noreferrer">${OPEN_METEO_CREDIT_TEXT}</a>`
  + ` (<a href="${CC_BY_4_URL}" target="_blank" rel="noopener noreferrer">${CC_BY_4_LABEL}</a>)`;
