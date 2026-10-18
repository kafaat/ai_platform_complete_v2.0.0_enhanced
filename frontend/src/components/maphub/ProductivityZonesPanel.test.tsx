import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { ProductivityZonesPanel } from './ProductivityZonesPanel';

describe('ProductivityZonesPanel evidence states', () => {
  it('shows unavailable data without offering approval of invented zones', () => {
    render(<ProductivityZonesPanel zones={[]} status="insufficient_data" />);
    expect(screen.getByTestId('productivity-zones-insufficient')).toBeInTheDocument();
    expect(screen.queryByTestId('productivity-zones-accept')).not.toBeInTheDocument();
  });
  it('keeps measured proposals reviewable and identifies the method', () => {
    const accept = vi.fn();
    const zones = [{ zone_id: 'z1', productivity_class: 'high', confidence: 0.8 }];
    render(<ProductivityZonesPanel zones={zones} method="kmeans" onAccept={accept} />);
    expect(screen.getByText(/kmeans/)).toBeInTheDocument();
    expect(screen.getByText(/درجة دعم استرشادية/)).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('productivity-zones-accept'));
    expect(accept).toHaveBeenCalledWith(zones);
  });
});
