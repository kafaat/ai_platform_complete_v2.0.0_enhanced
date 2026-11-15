// C-37: an owner manages the team it invited, within what the auth service accepts.
// The server grants only expert/farmer/viewer through PATCH /auth/users/{id}/role and
// refuses (403) to change or deactivate a peer owner/admin, so the page offers exactly
// those three roles and no controls on protected rows.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import SettingsPage from './SettingsPage';
import { changeUserRole, deactivateUser, listTeamUsers } from '../services/api';
import { isAssignableRole } from '../services/api/auth';

vi.mock('../hooks/useAuth', () => ({ useAuthStore: () => ({ user: { role: 'owner' } }) }));
vi.mock('../hooks/useApi', () => ({ useAllServicesHealth: () => ({ data: [], isLoading: false, refetch: vi.fn() }) }));
vi.mock('../hooks/useConnectionStatus', () => ({ useConnectionStatus: () => true }));
vi.mock('./NotificationSettingsPage', () => ({ default: () => null }));
vi.mock('../components/sharing/SharingPanel', () => ({ default: () => null }));
vi.mock('../services/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../services/api')>()),
  listInvitations: vi.fn(async () => []),
  listTeamUsers: vi.fn(),
  changeUserRole: vi.fn(),
  deactivateUser: vi.fn(),
}));

const member = (id: number, role: string) => ({
  id, email: `${role}${id}@example.invalid`, full_name: null, role, active: true,
  created_at: null, tenant_id: 'tenant-a',
});

describe('team members and roles (C-37)', () => {
  beforeEach(() => {
    vi.mocked(listTeamUsers).mockReset().mockResolvedValue([
      member(1, 'owner'), member(2, 'admin'), member(3, 'farmer'),
    ]);
    vi.mocked(changeUserRole).mockReset().mockResolvedValue({ id: 3, email: 'x', role: 'viewer' });
    vi.mocked(deactivateUser).mockReset();
  });

  it('grantable roles are exactly the lower tenant roles', () => {
    for (const r of ['expert', 'farmer', 'viewer']) expect(isAssignableRole(r)).toBe(true);
    for (const r of ['owner', 'admin', 'platform_admin', '', null, undefined]) expect(isAssignableRole(r)).toBe(false);
  });

  it('offers only expert/farmer/viewer and locks protected owner/admin rows', async () => {
    render(<SettingsPage />);
    fireEvent.click(screen.getByRole('button', { name: /الفريق/ }));

    const farmerSelect = await screen.findByLabelText('دور farmer3@example.invalid');
    expect(farmerSelect).toBeEnabled();
    const offered = within(farmerSelect).getAllByRole('option').map(o => (o as HTMLOptionElement).value);
    expect(offered.sort()).toEqual(['expert', 'farmer', 'viewer']);

    for (const peer of ['owner1@example.invalid', 'admin2@example.invalid']) {
      const select = screen.getByLabelText(`دور ${peer}`);
      expect(select).toBeDisabled();
      expect(within(select).getByRole('option', { name: /دور محمي/ })).toBeInTheDocument();
    }
    // Deactivate is offered only on the editable row.
    expect(screen.getAllByRole('button', { name: 'تعطيل' })).toHaveLength(1);

    fireEvent.change(farmerSelect, { target: { value: 'viewer' } });
    const rows = screen.getAllByRole('button', { name: 'تطبيق' });
    expect(rows.filter(b => !(b as HTMLButtonElement).disabled)).toHaveLength(1);
    fireEvent.click(rows.find(b => !(b as HTMLButtonElement).disabled)!);
    await screen.findByText(/غُيِّر الدور/);
    expect(changeUserRole).toHaveBeenCalledExactlyOnceWith(3, 'viewer', undefined);
  });
});
