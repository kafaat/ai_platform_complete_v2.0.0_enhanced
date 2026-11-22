import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import L from 'leaflet';
import 'leaflet-draw';
import FreehandBoundary from './FreehandBoundary';

const map = {
  mouseEventToContainerPoint: (e: MouseEvent) => L.point(e.clientX, e.clientY),
  containerPointToLatLng: (p: L.Point) => L.latLng(15 + p.y / 10000, 44 + p.x / 10000),
};
vi.mock('react-leaflet', () => ({ useMap: () => map }));

const preview = { addTo: vi.fn(), addLatLng: vi.fn(), remove: vi.fn() };
beforeEach(() => {
  vi.clearAllMocks();
  preview.addTo.mockReturnValue(preview);
  vi.spyOn(L, 'polyline').mockReturnValue(preview as unknown as L.Polyline);
});
afterEach(() => vi.restoreAllMocks());

function pointer(surface: HTMLElement, type: string, x: number, y: number) {
  const event = new MouseEvent(type, { bubbles: true, clientX: x, clientY: y, button: 0 });
  Object.defineProperties(event, { pointerId: { value: 1 }, isPrimary: { value: true } });
  fireEvent(surface, event);
}

function stroke(surface: HTMLElement, points: [number, number][]) {
  pointer(surface, 'pointerdown', ...points[0]);
  points.slice(1, -1).forEach(point => pointer(surface, 'pointermove', ...point));
  pointer(surface, 'pointerup', ...points[points.length - 1]);
}

function visit() {
  const onFinish = vi.fn();
  const onStatus = vi.fn();
  render(<FreehandBoundary onFinish={onFinish} onStatus={onStatus} />);
  const surface = screen.getByTestId('freehand-surface');
  let capture = false;
  surface.setPointerCapture = () => { capture = true; };
  surface.hasPointerCapture = () => capture;
  surface.releasePointerCapture = () => { capture = false; };
  return { surface, onFinish, onStatus };
}

describe('freehand boundary acceptance', () => {
  it('rejects a crossing stroke, explains how to retry, and accepts the next simple ring', () => {
    const { surface, onFinish, onStatus } = visit();
    // Unequal lobes have non-zero area, so an area-only check accepts this bowtie.
    stroke(surface, [[0, 0], [80, 80], [0, 80], [60, 0]]);
    expect(onFinish).not.toHaveBeenCalled();
    expect(onStatus).toHaveBeenLastCalledWith(expect.stringContaining('يتقاطع'));
    expect(surface.hasPointerCapture(1)).toBe(false);
    expect(preview.remove).toHaveBeenCalled();

    stroke(surface, [[0, 0], [80, 0], [80, 80], [0, 80]]);
    expect(onFinish).toHaveBeenCalledOnce();
    expect(onFinish.mock.calls[0][0]).toHaveLength(4);
    expect(onStatus).toHaveBeenLastCalledWith(null);
  });

  it('checks the closing edge as well as the edges traced by the pointer', () => {
    const { surface, onFinish, onStatus } = visit();
    stroke(surface, [[0, 0], [80, 0], [0, 80], [80, 80]]);
    expect(onFinish).not.toHaveBeenCalled();
    expect(onStatus).toHaveBeenLastCalledWith(expect.stringContaining('يتقاطع'));
  });

  it('cancels without completing and remains ready for another stroke', () => {
    const { surface, onFinish } = visit();
    pointer(surface, 'pointerdown', 0, 0);
    pointer(surface, 'pointermove', 80, 0);
    pointer(surface, 'pointercancel', 80, 80);
    pointer(surface, 'pointerup', 0, 80);
    expect(onFinish).not.toHaveBeenCalled();
    expect(surface.hasPointerCapture(1)).toBe(false);
    stroke(surface, [[0, 0], [80, 0], [80, 80], [0, 80], [0, 0]]);
    expect(onFinish).toHaveBeenCalledOnce();
  });
});
