import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router';
import { expect, it } from 'vitest';
import { SoilSamplingPlannerPanel, type SoilSamplePoint } from './SoilSamplingPlannerPanel';

function Destination() {
  return <pre data-testid="origin">{JSON.stringify(useLocation().state)}</pre>;
}

it('opens the ninth point with its field, plan and correctly ordered coordinates', () => {
  const points: SoilSamplePoint[] = Array.from({length: 9}, (_, i) => ({
    sample_id: String(i), zone_id: 'west', point: {coordinates: [44.2, 16.1]},
    indicators: ['ndvi', 'ndmi'], depth_cm: [0, 30],
  }));
  render(<MemoryRouter><Routes><Route path="/" element={
    <SoilSamplingPlannerPanel fieldId="wheat" plan={{plan_id:'plan'}} samplePoints={points}/>
  }/><Route path="/health/lab-sampling" element={<Destination/>}/></Routes></MemoryRouter>);
  expect(screen.queryByTestId('soil-sampling-accept')).toBeNull();
  fireEvent.click(screen.getAllByRole('link')[8]);
  expect(JSON.parse(screen.getByTestId('origin').textContent!)).toEqual({
    fieldId: 'wheat', planId: 'plan', depth: [0,30],
    origin: {point_id:'8', zone_id:'west', longitude:44.2, latitude:16.1, indicators:['ndvi','ndmi']},
  });
});
