import type { ReactNode } from 'react';

export function MapHubToolToggle({
  active,
  onClick,
  icon,
  label,
  testid,
  disabled,
  title,
  secondary = false,
}: {
  active: boolean;
  onClick: () => void;
  icon: ReactNode;
  label: string;
  testid?: string;
  disabled?: boolean;
  title?: string;
  secondary?: boolean;
}) {
  return (
    <button
      data-testid={testid}
      type="button"
      disabled={disabled}
      aria-pressed={active}
      title={title}
      onClick={onClick}
      className={secondary ? 'map-tool map-secondary' : 'map-tool'}
    >
      {icon}{label}
    </button>
  );
}
