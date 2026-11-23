// F-U02: a proposal card offers an action only when its handler exists; without one the
// control is absent (not a disabled button) and the card says nothing was saved.
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { FieldBoundaryProposalPanel } from './FieldBoundaryProposalPanel';
import { ProductivityZonesPanel } from './ProductivityZonesPanel';
import { VraPrescriptionPanel } from './VraPrescriptionPanel';

const NOT_SAVED = 'لم يُحفظ المقترح أو يُعتمد';
const proposals = [{ confidence: 0.6, area_ha: 2, method: 'deterministic_bbox_fallback' }];
const zones = [{ zone_id: 'z1', productivity_class: 'high' }];
const prescription = { product_type: 'fertilizer' };

describe('FieldBoundaryProposalPanel actions', () => {
  it('renders no action and reports not-saved when no handler is given', () => {
    render(<FieldBoundaryProposalPanel proposals={proposals} />);
    for (const id of ['field-boundary-accept', 'field-boundary-edit', 'field-boundary-reject']) {
      expect(screen.queryByTestId(id), id).toBeNull();
    }
    expect(screen.queryAllByRole('button')).toHaveLength(0);
    expect(screen.getByRole('status').textContent).toContain(NOT_SAVED);
  });

  it('renders only the action whose handler exists, and calls it on click only', () => {
    const accept = vi.fn();
    render(<FieldBoundaryProposalPanel proposals={proposals} onAccept={accept} />);
    expect(screen.queryByTestId('field-boundary-edit')).toBeNull();
    expect(screen.queryByTestId('field-boundary-reject')).toBeNull();
    expect(accept).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('field-boundary-accept'));
    expect(accept).toHaveBeenCalledTimes(1);
    expect(accept).toHaveBeenCalledWith(proposals[0]);
  });

  it('drops the unavailable-actions notice once every handler exists', () => {
    render(<FieldBoundaryProposalPanel proposals={proposals} onAccept={vi.fn()} onEdit={vi.fn()} onReject={vi.fn()} />);
    expect(screen.queryByRole('status')).toBeNull();
    expect(screen.getAllByRole('button')).toHaveLength(3);
  });
});

describe('ProductivityZonesPanel actions', () => {
  it('renders no action and reports not-saved when no handler is given', () => {
    render(<ProductivityZonesPanel zones={zones} />);
    for (const id of ['productivity-zones-accept', 'productivity-zones-soil-sampling', 'productivity-zones-reject']) {
      expect(screen.queryByTestId(id), id).toBeNull();
    }
    expect(screen.queryAllByRole('button')).toHaveLength(0);
    expect(screen.getByRole('status').textContent).toContain(NOT_SAVED);
  });

  it('renders only the action whose handler exists, and calls it on click only', () => {
    const plan = vi.fn();
    render(<ProductivityZonesPanel zones={zones} onPlanSoilSampling={plan} />);
    expect(screen.queryByTestId('productivity-zones-accept')).toBeNull();
    expect(screen.queryByTestId('productivity-zones-reject')).toBeNull();
    expect(plan).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('productivity-zones-soil-sampling'));
    expect(plan).toHaveBeenCalledWith(zones);
  });
});

describe('VraPrescriptionPanel actions', () => {
  it('renders no approve / refine / reject and reports not-saved when no handler is given', () => {
    render(<VraPrescriptionPanel prescription={prescription} zones={zones} />);
    for (const id of ['vra-approve', 'vra-refine', 'vra-reject']) {
      expect(screen.queryByTestId(id), id).toBeNull();
    }
    expect(screen.getByRole('status').textContent).toContain(NOT_SAVED);
  });

  it('keeps machine export disabled even when approval is offered', () => {
    const approve = vi.fn();
    render(<VraPrescriptionPanel prescription={prescription} zones={zones} onApprove={approve} />);
    expect(screen.getByTestId('vra-export-disabled')).toBeDisabled();
    expect(approve).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('vra-approve'));
    expect(approve).toHaveBeenCalledWith(prescription, zones);
    expect(screen.queryByTestId('vra-refine')).toBeNull();
    expect(screen.queryByTestId('vra-reject')).toBeNull();
  });
});
