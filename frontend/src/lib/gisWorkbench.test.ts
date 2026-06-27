import { buildSwipeCompareConfig, setLayerOpacity, toggleLayer, type WorkbenchState } from './gisWorkbench';

const base: WorkbenchState = {
  fieldId: 'f1',
  mode: 'swipe',
  activeDate: '2026-06-20',
  compareDate: '2026-06-10',
  canUndo: false,
  canRedo: false,
  layers: [
    { id: 'ndvi', title: 'NDVI', visible: true, opacity: 1 },
    { id: 'truecolor', title: 'True Color', visible: true, opacity: 0.7 },
  ],
};

describe('gisWorkbench', () => {
  it('clamps opacity and toggles visibility immutably', () => {
    const next = setLayerOpacity(base, 'ndvi', 2);
    expect(next.layers[0].opacity).toBe(1);
    const hidden = toggleLayer(next, 'truecolor');
    expect(hidden.layers[1].visible).toBe(false);
    expect(base.layers[1].visible).toBe(true);
  });

  it('builds swipe compare configuration from visible layers', () => {
    const cfg = buildSwipeCompareConfig(base);
    expect(cfg.enabled).toBe(true);
    expect(cfg.leftLayer).toBe('ndvi');
    expect(cfg.rightLayer).toBe('truecolor');
    expect(cfg.compareDate).toBe('2026-06-10');
  });
});
