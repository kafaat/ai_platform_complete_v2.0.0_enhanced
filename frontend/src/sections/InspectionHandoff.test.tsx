import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, expect, it, vi } from 'vitest';
import { kongApi } from '../services/api';
import { InspectionHandoff } from './InspectionHandoff';

afterEach(() => vi.restoreAllMocks());
const original = {
  revision: 0, accepted: false, assigned_to: '1', assigned_by: '6', initial_assignee: '1',
  assigned_at: '2026-11-12T06:30:00Z', events: [], can_accept: false, can_reassign: false, can_submit:false, can_review:false,
};
const path = '/api/v1/fields/wheat/tasks/t1/handoff';

function open(state: typeof original) {
  vi.spyOn(kongApi, 'get').mockImplementation(async url => ({data: url === path ? state : {
    assignees: [{id: 1, full_name:'الحالي'}, {id:5, full_name:'البديل'}],
  }}));
  render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}>
    <InspectionHandoff fieldId="wheat" taskId="t1" tenant="tenant" />
  </QueryClientProvider>);
}

it('displays worker acceptance only after the server confirms the revision', async () => {
  open({...original, can_accept:true});
  const post = vi.spyOn(kongApi, 'post').mockResolvedValue({data:{...original, accepted:true, revision:1}});
  fireEvent.click(await screen.findByRole('button', {name:'تأكيد استلام الزيارة'}));
  await screen.findByText(/قَبِل التكليف/);
  expect(post).toHaveBeenCalledWith(path + '/accept', {expected_revision:0});
  expect(screen.queryByRole('button', {name:'إعادة إسناد الزيارة'})).not.toBeInTheDocument();
});

it('requires a different user and reason and displays the saved transfer', async () => {
  open({...original, revision:1, can_reassign:true});
  const event = {revision:2,action:'reassign',assignee:'5',previous_assignee:'1',actor:'6',
    reason:'انتهاء الوردية',occurred_at:'2026-11-12T07:00:00Z'};
  const post = vi.spyOn(kongApi, 'post').mockResolvedValue({data:{...original,revision:2,assigned_to:'5',events:[event]}});
  await screen.findByRole('option', {name:'البديل'});
  expect(screen.queryByRole('option', {name:'الحالي'})).not.toBeInTheDocument();
  const button = screen.getByRole('button', {name:'إعادة إسناد الزيارة'});
  expect(button).toBeDisabled();
  fireEvent.change(screen.getByLabelText('المستلم البديل'), {target:{value:'5'}});
  expect(button).toBeDisabled();
  fireEvent.change(screen.getByLabelText('سبب إعادة الإسناد'), {target:{value:'انتهاء الوردية'}});
  fireEvent.click(button);
  await waitFor(() => expect(post).toHaveBeenCalledWith(path + '/reassign',
    {expected_revision:1,assigned_to:5,reason:'انتهاء الوردية'}));
  expect(await screen.findByText(/أعاد 6 الإسناد من 1 إلى 5/)).toBeInTheDocument();
});

it('requires a review comment and submits the displayed revision', async () => {
  open({...original, revision:4, can_review:true});
  const post = vi.spyOn(kongApi, 'post').mockResolvedValue({data:{...original, revision:5}});
  const approve = await screen.findByRole('button', {name:'اعتماد نتيجة التفتيش'});
  expect(approve).toBeDisabled();
  expect(screen.queryByRole('button', {name:'رفع النتيجة للمراجعة'})).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('تعليق المراجع'), {target:{value:'تم التحقق'}});
  fireEvent.click(approve);
  await waitFor(() => expect(post).toHaveBeenCalledWith(path+'/finding',
    {action:'approve', reason:'تم التحقق', expected_revision:4}));
});

it('keeps the approved photo visible and marks a later photo as pending review', async () => {
  const v1 = {version:1, photo_url:'https://evidence.example/1.jpg', notes:'اصفرار'};
  const v2 = {version:2, photo_url:'https://evidence.example/2.jpg', notes:'اصفرار'};
  open({...original, revision:3, accepted:true, can_submit:true, evidence:[v1, v2], approved_evidence:v1, current_evidence:v2,
    evidence_approved:false, evidence_pending_review:true} as typeof original);
  const approved = await screen.findByText(/النسخة المعتمدة 1/);
  expect(approved.querySelector('a')).toHaveAttribute('href', v1.photo_url);
  const pending = screen.getByText(/نسخة بانتظار المراجعة 2/);
  expect(pending.querySelector('a')).toHaveAttribute('href', v2.photo_url);
  expect(screen.getByRole('status')).toHaveTextContent('لا تُغلق الزيارة قبل اعتماد النسخة الجديدة');
  expect(screen.getByRole('button', {name:'رفع النتيجة للمراجعة'})).toBeInTheDocument();
});
