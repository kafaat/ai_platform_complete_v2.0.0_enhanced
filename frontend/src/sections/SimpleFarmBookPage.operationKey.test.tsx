// مفتاح العمليّة (client_operation_id): يُعاد نفسه عند إعادة محاولة الحمولة ذاتها بعد ردٍّ ضائع
// (فلا تُكرَّر الحركة)، ويتجدّد عند تغيّر الحمولة، ويعمل الحفظ على أصلٍ غير آمن (HTTP عاديّ)
// حيث لا يوجد crypto.randomUUID.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

const kong = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('../services/api/client', () => ({ kongApi: kong }));

import SimpleFarmBookPage from './SimpleFarmBookPage';

function fill(amount: string) {
  fireEvent.change(screen.getByPlaceholderText('معرّف المزرعة'), { target: { value: 'farm-1' } });
  fireEvent.change(screen.getByPlaceholderText('المبلغ'), { target: { value: amount } });
}
const save = () => fireEvent.click(screen.getByRole('button', { name: /حفظ الحركة/ }));
const sentKeys = () => kong.post.mock.calls
  .filter(([url]) => url === '/api/v1/farm-book/entries')
  .map(([, body]) => (body as { client_operation_id: string }).client_operation_id);

beforeEach(() => {
  kong.get.mockReset(); kong.post.mockReset();
  kong.get.mockResolvedValue({ data: { items: [], summary: null } });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('SimpleFarmBookPage operation key', () => {
  it('reuses the key when the same entry is retried after a failed reply', async () => {
    kong.post.mockRejectedValueOnce(new Error('Network Error')).mockResolvedValueOnce({ data: {} });
    render(<SimpleFarmBookPage />);
    fill('100');
    save();
    await screen.findByText('تعذّر حفظ الحركة.');
    save();
    await waitFor(() => expect(sentKeys()).toHaveLength(2));
    const [first, second] = sentKeys();
    expect(first).toMatch(/^web-/);
    expect(second).toBe(first);
  });

  it('issues a new key when the payload changes', async () => {
    kong.post.mockRejectedValueOnce(new Error('Network Error')).mockResolvedValueOnce({ data: {} });
    render(<SimpleFarmBookPage />);
    fill('100');
    save();
    await screen.findByText('تعذّر حفظ الحركة.');
    fill('120');
    save();
    await waitFor(() => expect(sentKeys()).toHaveLength(2));
    const [first, second] = sentKeys();
    expect(second).not.toBe(first);
  });

  it('still saves where crypto.randomUUID is unavailable (plain-HTTP origin)', async () => {
    vi.stubGlobal('crypto', {});
    kong.post.mockResolvedValueOnce({ data: {} });
    render(<SimpleFarmBookPage />);
    fill('50');
    save();
    await waitFor(() => expect(sentKeys()).toHaveLength(1));
    expect(sentKeys()[0]).toMatch(/^web-[0-9a-z]+-[0-9a-f]+-[0-9a-f]+$/);
    expect(screen.queryByText('تعذّر حفظ الحركة.')).not.toBeInTheDocument();
  });
});
