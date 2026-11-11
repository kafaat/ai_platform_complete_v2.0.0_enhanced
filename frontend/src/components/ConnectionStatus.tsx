import { Wifi, WifiOff } from 'lucide-react';
import { useConnectionStatus } from '../hooks/useConnectionStatus';

export default function ConnectionStatus() {
  const connected = useConnectionStatus();
  const Icon = connected ? Wifi : WifiOff;
  return <span className="ops-connection" data-connected={connected} role="status" aria-live="polite"
    title="حالة قناة التحديثات اللحظية؛ لا تعبّر عن اتصال جميع خدمات البيانات">
    <Icon size={14} aria-hidden="true" />
    <span>{connected ? 'التحديثات متصلة' : 'التحديثات غير متصلة'}</span>
  </span>;
}
