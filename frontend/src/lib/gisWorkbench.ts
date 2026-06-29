export interface WorkbenchLayer {
  id: string;
  title: string;
  visible: boolean;
  opacity: number;
  blendMode?: 'normal' | 'multiply' | 'screen' | 'overlay';
}

export interface WorkbenchState {
  fieldId?: string;
  mode: 'browse' | 'compare' | 'swipe' | 'timeline' | 'edit';
  layers: WorkbenchLayer[];
  activeDate?: string;
  compareDate?: string;
  canUndo: boolean;
  canRedo: boolean;
}

export function setLayerOpacity(state: WorkbenchState, layerId: string, opacity: number): WorkbenchState {
  const safeOpacity = Math.max(0, Math.min(1, opacity));
  return {
    ...state,
    layers: state.layers.map(layer => layer.id === layerId ? { ...layer, opacity: safeOpacity } : layer),
  };
}

export function toggleLayer(state: WorkbenchState, layerId: string): WorkbenchState {
  return {
    ...state,
    layers: state.layers.map(layer => layer.id === layerId ? { ...layer, visible: !layer.visible } : layer),
  };
}

export function setWorkbenchMode(state: WorkbenchState, mode: WorkbenchState['mode']): WorkbenchState {
  return { ...state, mode };
}

export function buildSwipeCompareConfig(state: WorkbenchState): { enabled: boolean; leftLayer?: string; rightLayer?: string; activeDate?: string; compareDate?: string } {
  const visible = state.layers.filter(layer => layer.visible);
  return {
    enabled: state.mode === 'swipe' || state.mode === 'compare',
    leftLayer: visible[0]?.id,
    rightLayer: visible[1]?.id,
    activeDate: state.activeDate,
    compareDate: state.compareDate,
  };
}
