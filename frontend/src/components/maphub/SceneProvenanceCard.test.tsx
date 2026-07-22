import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import SceneProvenanceCard, { sceneProvenanceMissing } from './SceneProvenanceCard';

const full = { date: '2026-07-01', scene_id: 'S2A-1', acquisition_datetime: '2026-07-01T08:00:00Z', cloud_pct: 7, has_cog: true, indices: ['ndvi'] };

describe('SceneProvenanceCard', () => {
  it('marks complete backend provenance without inventing fields', () => {
    expect(sceneProvenanceMissing(full)).toEqual([]);
    render(<SceneProvenanceCard scene={full} />);
    expect(screen.getByText('مكتملة')).toBeTruthy();
    expect(screen.getByText('S2A-1')).toBeTruthy();
  });

  it('names every missing provenance field', () => {
    const scene = { date: '2026-07-01', has_cog: false };
    expect(sceneProvenanceMissing(scene)).toEqual(['معرّف المشهد', 'وقت الالتقاط', 'نسبة الغيوم']);
    render(<SceneProvenanceCard scene={scene} />);
    expect(screen.getByText('غير مكتملة')).toBeTruthy();
    expect(screen.getByText(/بيانات المصدر الناقصة/)).toBeTruthy();
  });
});
