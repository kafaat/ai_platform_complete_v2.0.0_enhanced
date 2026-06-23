// SAHOOL — lib/projectFile.ts
// مشروع مساحة عمل قابل للتسلسل (.sahool-project.json) — مستوحى من GeoLibre .geolibre.json.
// يحفظ إعدادات عرض «مركز الخرائط» (الأساس · المؤشّر · الشفافية · المقارنة · الأدوات ·
// التراكبات · فئة الدبابيس · الحقل المختار) في ملفّ، فيعود المستخدم لنفس البيئة. عميل-فقط،
// بلا خادم/سحابة (فلسفة browser-native). صدق: الاستيراد يتحقّق من البنية ويرمي عند الفساد
// (لا قيم ملفّقة). v1 لا يحفظ مركز/تكبير الخريطة ولا الرسومات (مؤجّلة لـv2 — تحتاج تحكّم خريطة).

export interface SahoolProjectWorkspace {
  mode: '2d' | '3d';
  basemapId: string;
  activeIndicator: string | null;
  opacity: number;
  compare: boolean;
  leftLayer: string;
  rightLayer: string;
  drawTools: boolean;
  pinMode: boolean;
  showWeather: boolean;
  showAlerts: boolean;
  showDevices: boolean;
  pinCategory: string;
  selectedFieldId: string | null;
}

export interface SahoolProject {
  type: 'sahool-project';
  version: 1;
  updatedAt: string; // ISO 8601
  workspace: SahoolProjectWorkspace;
}

/** يبني كائن المشروع من حالة مساحة العمل الحاليّة. */
export function buildProject(w: SahoolProjectWorkspace): SahoolProject {
  return {
    type: 'sahool-project',
    version: 1,
    updatedAt: new Date().toISOString(),
    workspace: w,
  };
}

/** ينزّل المشروع كملفّ JSON (تنزيل المتصفّح — لا خادم). */
export function downloadProject(project: SahoolProject, filename = 'sahool-project.json'): void {
  const blob = new Blob([JSON.stringify(project, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/**
 * يقرأ ملفّاً ويتحقّق من بنيته بصدق، ويعيد حالة مساحة عمل مُطهَّرة (قيم آمنة الأنواع).
 * يرمي رسالةً عربيّةً عند الفساد — لا يُلفّق ولا يبتلع.
 */
export async function parseProjectFile(file: File): Promise<SahoolProjectWorkspace> {
  let text: string;
  try {
    text = await file.text();
  } catch {
    throw new Error('تعذّرت قراءة الملفّ');
  }
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    throw new Error('ملفّ JSON غير صالح');
  }
  const w = (data as { workspace?: unknown })?.workspace;
  if (!w || typeof w !== 'object') {
    throw new Error('ملفّ مشروع غير صالح — لا توجد «مساحة عمل»');
  }
  const o = w as Record<string, unknown>;
  const str = (v: unknown, d: string): string => (typeof v === 'string' ? v : d);
  const bool = (v: unknown): boolean => v === true;
  const optStr = (v: unknown): string | null => (typeof v === 'string' ? v : null);
  const opacity =
    typeof o.opacity === 'number' && isFinite(o.opacity)
      ? Math.min(1, Math.max(0, o.opacity))
      : 0.75;
  return {
    mode: o.mode === '3d' ? '3d' : '2d',
    basemapId: str(o.basemapId, 'satellite'),
    activeIndicator: optStr(o.activeIndicator),
    opacity,
    compare: bool(o.compare),
    leftLayer: str(o.leftLayer, 'ndvi'),
    rightLayer: str(o.rightLayer, 'ndmi'),
    drawTools: bool(o.drawTools),
    pinMode: bool(o.pinMode),
    showWeather: bool(o.showWeather),
    showAlerts: bool(o.showAlerts),
    showDevices: bool(o.showDevices),
    pinCategory: str(o.pinCategory, ''),
    selectedFieldId: optStr(o.selectedFieldId),
  };
}
