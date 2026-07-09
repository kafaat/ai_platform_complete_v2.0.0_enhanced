import {
  Bell,
  CheckSquare,
  CircleDotDashed,
  CloudSun,
  Combine,
  FlaskConical,
  Layers,
  Mountain,
  Radio,
  Tractor,
} from 'lucide-react';
import { T } from '../../components/ds';
import type { OperationalOverlayId } from './mapClutterControl';
import { MapHubToolToggle } from './MapHubToolToggle';

export type OperationalOverlayControlsProps = {
  isVisible: boolean;
  showWeather: boolean;
  showAlerts: boolean;
  showDevices: boolean;
  showEquipment: boolean;
  showTasks: boolean;
  showPivots: boolean;
  showHillshade: boolean;
  showSlope: boolean;
  showContours: boolean;
  showSoil: boolean;
  showSoilSamples: boolean;
  soilSamplesBusy: boolean;
  selectedHasGeometry: boolean;
  selectedHasPoint: boolean;
  alertsUnplaceable: number;
  devicesUnplaceable: number;
  equipmentUnplaceable: number;
  tasksUnplaceable: number;
  pivotMarkersCount: number;
  soilSamplesNote?: string | null;
  hillshadeUnavailableMessage?: string | null;
  slopeUnavailableMessage?: string | null;
  contoursNote?: string | null;
  isOverlayBlocked: (id: OperationalOverlayId) => boolean;
  overlayBlockedTitle: (id: OperationalOverlayId) => string | undefined;
  setShowWeather: (updater: (value: boolean) => boolean) => void;
  setShowAlerts: (updater: (value: boolean) => boolean) => void;
  setShowDevices: (updater: (value: boolean) => boolean) => void;
  setShowEquipment: (updater: (value: boolean) => boolean) => void;
  setShowTasks: (updater: (value: boolean) => boolean) => void;
  setShowPivots: (updater: (value: boolean) => boolean) => void;
  setShowHillshade: (updater: (value: boolean) => boolean) => void;
  setShowSlope: (updater: (value: boolean) => boolean) => void;
  setShowContours: (updater: (value: boolean) => boolean) => void;
  setShowSoil: (updater: (value: boolean) => boolean) => void;
  setShowSoilSamples: (updater: (value: boolean) => boolean) => void;
};

export function OperationalOverlayControls(props: OperationalOverlayControlsProps) {
  if (!props.isVisible) return null;

  return (
    <div
      data-testid="maphub-operational-overlay-controls"
      data-sahool-region="operational-overlays"
      className="flex flex-wrap items-center gap-2 mt-3 pt-3"
      style={{ borderTop: `1px solid ${T.line}` }}
    >
      <span className="text-xs font-semibold" style={{ color: T.muted }}>طبقات التراكب</span>
      <MapHubToolToggle testid="btn-weather" active={props.showWeather} disabled={props.isOverlayBlocked('weather')} title={props.overlayBlockedTitle('weather')} onClick={() => props.setShowWeather((v) => !v)} icon={<CloudSun className="w-3.5 h-3.5" />} label="طقس/رياح" />
      <MapHubToolToggle testid="btn-alerts" active={props.showAlerts} disabled={props.isOverlayBlocked('alerts')} title={props.overlayBlockedTitle('alerts')} onClick={() => props.setShowAlerts((v) => !v)} icon={<Bell className="w-3.5 h-3.5" />} label="تنبيهات" />
      <MapHubToolToggle testid="btn-devices" active={props.showDevices} disabled={props.isOverlayBlocked('devices')} title={props.overlayBlockedTitle('devices')} onClick={() => props.setShowDevices((v) => !v)} icon={<Radio className="w-3.5 h-3.5" />} label="أجهزة" />
      <MapHubToolToggle testid="btn-equipment" active={props.showEquipment} disabled={props.isOverlayBlocked('equipment')} title={props.overlayBlockedTitle('equipment')} onClick={() => props.setShowEquipment((v) => !v)} icon={<Tractor className="w-3.5 h-3.5" />} label="معدّات" />
      <MapHubToolToggle testid="btn-tasks" active={props.showTasks} disabled={props.isOverlayBlocked('tasks')} title={props.overlayBlockedTitle('tasks')} onClick={() => props.setShowTasks((v) => !v)} icon={<CheckSquare className="w-3.5 h-3.5" />} label="مهام" />
      <MapHubToolToggle testid="btn-pivots" active={props.showPivots} onClick={() => props.setShowPivots((v) => !v)} icon={<CircleDotDashed className="w-3.5 h-3.5" />} label="محوري" />
      <MapHubToolToggle testid="btn-hillshade" active={props.showHillshade} onClick={() => props.setShowHillshade((v) => !v)} icon={<Mountain className="w-3.5 h-3.5" />} label="التضاريس (Hillshade)" />
      <MapHubToolToggle testid="btn-slope" active={props.showSlope} onClick={() => props.setShowSlope((v) => !v)} icon={<Layers className="w-3.5 h-3.5" />} label="الانحدار (Slope)" />
      <MapHubToolToggle
        testid="btn-contours"
        active={props.showContours}
        disabled={!props.selectedHasGeometry}
        title={!props.selectedHasGeometry ? 'اختر حقلاً ذا حدود مرسومة أوّلاً' : undefined}
        onClick={() => props.setShowContours((v) => !v)}
        icon={<CircleDotDashed className="w-3.5 h-3.5" />}
        label="خطوط الكنتور (Contours)"
      />
      <MapHubToolToggle testid="btn-soil" active={props.showSoil} onClick={() => props.setShowSoil((v) => !v)} icon={<Layers className="w-3.5 h-3.5" />} label="طبقة التربة (SoilGrids)" />
      <MapHubToolToggle
        testid="btn-soil-samples"
        active={props.showSoilSamples}
        disabled={!props.selectedHasGeometry}
        title={!props.selectedHasGeometry ? 'اختر حقلاً ذا حدود مرسومة أوّلاً' : undefined}
        onClick={() => props.setShowSoilSamples((v) => !v)}
        icon={<FlaskConical className="w-3.5 h-3.5" />}
        label={props.soilSamplesBusy ? 'نقاط العيّنات… (جارٍ)' : 'نقاط العينات'}
      />

      {props.showSoilSamples && props.soilSamplesNote && (
        <span className="text-[11px]" style={{ color: T.faint }}>{props.soilSamplesNote}</span>
      )}
      {props.showAlerts && props.alertsUnplaceable > 0 && (
        <span className="text-[11px]" style={{ color: T.faint }}>{props.alertsUnplaceable} تنبيه غير قابل للعرض على الخريطة (بلا حقل/هندسة)</span>
      )}
      {props.showDevices && props.devicesUnplaceable > 0 && (
        <span className="text-[11px]" style={{ color: T.faint }}>{props.devicesUnplaceable} جهاز غير قابل للعرض على الخريطة (بلا حقل/هندسة)</span>
      )}
      {props.showEquipment && props.equipmentUnplaceable > 0 && (
        <span className="text-[11px]" style={{ color: T.faint }}>{props.equipmentUnplaceable} معدّة غير قابلة للعرض (بلا حقل/هندسة)</span>
      )}
      {props.showTasks && props.tasksUnplaceable > 0 && (
        <span className="text-[11px]" style={{ color: T.faint }}>{props.tasksUnplaceable} مهمة غير قابلة للعرض (بلا حقل/هندسة)</span>
      )}
      {props.showPivots && props.pivotMarkersCount === 0 && (
        <span className="text-[11px]" style={{ color: T.faint }}>المحوري يظهر للحقل المختار فقط عند وجود بيانات pivot/irrigation_type</span>
      )}
      {props.showWeather && !props.selectedHasPoint && (
        <span className="text-[11px]" style={{ color: T.faint }}>اختر حقلاً ذا هندسة/نقطة لعرض طبقة الطقس واتجاه الرياح كبلاطة فوق الخريطة</span>
      )}
      {props.showHillshade && props.hillshadeUnavailableMessage && (
        <span className="text-[11px]" data-testid="hillshade-unavailable" style={{ color: T.faint }}>{props.hillshadeUnavailableMessage}</span>
      )}
      {props.showSlope && props.slopeUnavailableMessage && (
        <span className="text-[11px]" data-testid="slope-unavailable" style={{ color: T.faint }}>{props.slopeUnavailableMessage}</span>
      )}
      {props.showContours && props.contoursNote && (
        <span className="text-[11px]" data-testid="contours-note" style={{ color: T.faint }}>{props.contoursNote}</span>
      )}
    </div>
  );
}
