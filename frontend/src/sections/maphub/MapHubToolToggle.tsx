import type { ReactNode } from 'react';
import { T } from '../../components/ds';

export function MapHubToolToggle({
  active,
  onClick,
  icon,
  label,
  testid,
  disabled,
  title,
}: {
  active: boolean;
  onClick: () => void;
  icon: ReactNode;
  label: string;
  testid?: string;
  disabled?: boolean;
  title?: string;
}) {
  return (
    <button
      data-testid={testid}
      type="button"
      disabled={disabled}
      title={title}
      onClick={onClick}
      className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-[11px] transition disabled:cursor-not-allowed disabled:opacity-45"
      style={{
        background: active ? 'rgba(31,112,74,.14)' : 'rgba(255,255,255,.75)',
        border: `1px solid ${active ? T.green : T.line}`,
        color: active ? T.green : T.ink,
      }}
    >
      {icon}{label}
    </button>
  );
}
