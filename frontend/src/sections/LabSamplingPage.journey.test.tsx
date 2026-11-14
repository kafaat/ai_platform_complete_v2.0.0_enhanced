import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { SoilSamplingPlannerPanel } from '../components/maphub/SoilSamplingPlannerPanel';
import { createLabSample, kongApi, submitSoilLabResult } from '../services/api';
import { useAuthStore } from '../hooks/useAuth';
import LabSamplingPage from './LabSamplingPage';

vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  CircleMarker: () => null, Tooltip: () => null, Marker: () => null, TileLayer: () => null, Polygon: () => null, useMapEvents: () => null,
}));
vi.mock('../lib/leafletSetup', () => ({}));
vi.mock('../hooks/useSelectedField', () => ({
  useSelectedField: () => ({fieldId: 'wheat', options: [{id: 'wheat', name: 'قمح'}], setFieldId: vi.fn()}),
}));
vi.mock('../hooks/useApi', () => ({
  useLabSamples: () => ({data: [{sample_id: 'collected-1', kind: 'soil', status: 'collected', latitude: 16, longitude: 44}]}),
  useLabDecisionContext: () => ({}),
  useCreateLabSample: () => ({mutateAsync: createLabSample}),
  useSubmitSoilLabResult: () => ({mutateAsync: submitSoilLabResult}),
}));
function openCollection() {
  render(<MemoryRouter><Routes>
    <Route path="/" element={<SoilSamplingPlannerPanel fieldId="wheat" plan={{plan_id: 'plan'}}
      samplePoints={[{sample_id:'p-1', zone_id:'west', point:{coordinates:[44.2,16.1]}, indicators:['ndvi'],
        depth_cm:[10,30], location_id:'core-1', sampling_purpose:'nitrate',
        indicator_sources:{ndvi:{scene_id:'S2-A', acquisition_date:'2026-07-10'}}}]} />} />
    <Route path="/health/lab-sampling" element={<LabSamplingPage/>}/>
  </Routes></MemoryRouter>);
  fireEvent.click(screen.getByRole('link'));
}
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
beforeEach(() => {
  sessionStorage.clear();
  useAuthStore.setState({ tenantId: 't1', user: {id: 1, email:'a@example.org', full_name:'a', role:'manager'}});
});
afterEach(() => {cleanup(); vi.restoreAllMocks();});

it('preserves the exact field collection and UUID after a lost response and reopening the plan point', async () => {
  const post = vi.spyOn(kongApi, 'post').mockRejectedValueOnce(new Error('connection lost'))
    .mockResolvedValueOnce({data:{sample_id:'collected-1'}});
  openCollection();
  expect((screen.getByLabelText('Latitude') as HTMLInputElement).value).toBe('');
  fireEvent.change(screen.getByLabelText('Latitude'), {target:{value:'16.102'}});
  fireEvent.change(screen.getByLabelText('Longitude'), {target:{value:'44.203'}});
  fireEvent.change(screen.getByLabelText('مصدر/ملاحظة'), {target:{value:'قطاع غربي'}});
  fireEvent.click(screen.getByRole('button', {name:'حفظ العينة'}));
  await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  const [url,body,config] = post.mock.calls[0];
  expect(url).toBe('/api/v1/lab/samples');
  expect(body).toMatchObject({latitude:16.102,longitude:44.203,source:'قطاع غربي',depth_cm_from:10,depth_cm_to:30,
    sampling_plan_id:'plan',sampling_origin:{latitude:16.1,longitude:44.2,location_id:'core-1',point_id:'p-1',
      sampling_purpose:'nitrate',indicator_sources:{ndvi:{scene_id:'S2-A'}}}});
  expect(body).not.toHaveProperty('idempotency_key');
  expect(config?.headers?.['Idempotency-Key']).toMatch(uuid);
  await screen.findByRole('button', {name:'إعادة إرسال العينة'});
  cleanup(); openCollection();
  fireEvent.click(screen.getByRole('button', {name:'إعادة إرسال العينة'}));
  await screen.findByText('تم حفظ نقطة العينة وربطها بالحقل والخريطة.');
  expect(post.mock.calls[1]).toEqual(post.mock.calls[0]);
});

it('scopes an uncertain analysis to its actor and retries the original method, reading and sample after reopening', async () => {
  const post = vi.spyOn(kongApi, 'post').mockRejectedValueOnce(new Error('response lost'))
    .mockResolvedValueOnce({data:{decision_usable:false}});
  openCollection();
  const form = screen.getByRole('button', {name:'حفظ التحليل'}).closest('form')!;
  fireEvent.change(form.querySelector('[name=sample_id]')!, {target:{value:'collected-1'}});
  fireEvent.change(screen.getByPlaceholderText('EC dS/m'), {target:{value:'3.2'}});
  fireEvent.change(screen.getByLabelText('طريقة استخلاص ملوحة التربة'), {target:{value:'saturated_paste'}});
  fireEvent.click(screen.getByRole('button', {name:'حفظ التحليل'}));
  await screen.findByRole('button', {name:'إعادة إرسال التحليل'});
  cleanup(); useAuthStore.setState({tenantId:'other'});
  openCollection();
  expect(screen.queryByRole('button', {name:'إعادة إرسال التحليل'})).toBeNull();
  cleanup(); useAuthStore.setState({tenantId:'t1'}); openCollection();
  fireEvent.click(screen.getByRole('button', {name:'إعادة إرسال التحليل'}));
  await screen.findByText('تم حفظ النتيجة وهي بانتظار استكمال القيم أو الاعتماد.');
  expect(post.mock.calls[0][0]).toBe('/api/v1/lab/soil-results');
  expect(post.mock.calls[0][1]).toMatchObject({sample_id:'collected-1',ec_dsm:3.2,ec_extraction_method:'saturated_paste'});
  expect(post.mock.calls[0][2]?.headers?.['Idempotency-Key']).toMatch(uuid);
  expect(post.mock.calls[1]).toEqual(post.mock.calls[0]);
});

it('keeps the lab values editable on a definitive 422 and gives the corrected command a new UUID', async () => {
  const post = vi.spyOn(kongApi, 'post').mockRejectedValueOnce({response:{status:422,data:{detail:'Invalid reading'}}})
    .mockResolvedValueOnce({data:{decision_usable:false}});
  openCollection();
  const form = screen.getByRole('button', {name:'حفظ التحليل'}).closest('form')!;
  fireEvent.change(form.querySelector('[name=sample_id]')!, {target:{value:'collected-1'}});
  const ph = screen.getByPlaceholderText('pH');
  fireEvent.change(ph, {target:{value:'15'}});
  fireEvent.click(screen.getByRole('button', {name:'حفظ التحليل'}));
  await screen.findByText('Invalid reading');
  expect((ph as HTMLInputElement).value).toBe('15');
  fireEvent.change(ph, {target:{value:'7.2'}});
  fireEvent.click(screen.getByRole('button', {name:'حفظ التحليل'}));
  await screen.findByText('تم حفظ النتيجة وهي بانتظار استكمال القيم أو الاعتماد.');
  expect(post.mock.calls[1][1]).toMatchObject({ph:7.2});
  expect(post.mock.calls[1][2]?.headers?.['Idempotency-Key']).not.toBe(post.mock.calls[0][2]?.headers?.['Idempotency-Key']);
});

it.each([
  ['viewer', false, false],
  ['unknown', false, false],
  ['worker', true, false],
  ['agronomist', true, false],
  ['manager', true, true],
  ['owner', true, true],
])('presents collection and lab-result entry according to role %s', (role, collection, analysis) => {
  useAuthStore.setState({ user: {email:'field@example.org', full_name:'مستخدم', role: String(role)} });
  openCollection();
  expect(!!screen.queryByRole('button', {name:'حفظ العينة'})).toBe(collection);
  expect(!!screen.queryByRole('button', {name:'حفظ التحليل'})).toBe(analysis);
  expect(screen.getByText('العينات المسجلة')).toBeInTheDocument();
});
