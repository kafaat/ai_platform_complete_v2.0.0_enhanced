import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import SettingsPage from './SettingsPage';
import { AlertSystemPage } from './AlertSystemPage';
import SimpleFarmBookPage from './SimpleFarmBookPage';
const mocks = vi.hoisted(() => ({
  ack: vi.fn(), verify: vi.fn(), post: vi.fn(), get: vi.fn(),
  user: {id:1,tenant_id:'tenant-a',role:'owner',email:'fixture@example.invalid'},
}));
vi.mock('../hooks/useAuth', () => ({ useAuthStore: (selector?: (x: unknown) => unknown) => selector ? selector({user:mocks.user}) : {user:mocks.user} }));
vi.mock('../hooks/useConnectionStatus', () => ({useConnectionStatus:()=>false}));
vi.mock('../hooks/useSelectedField', () => ({useSelectedField:()=>({options:[],fieldId:null,setFieldId:vi.fn()})}));
vi.mock('../hooks/useApi', () => ({
  useAllServicesHealth:()=>({data:[],isLoading:false,refetch:vi.fn()}),
  useAlerts:()=>({data:[{alert_id:'alert-1',title_ar:'تنبيه اختبار',severity:'high',status:'active'}],isLoading:false,isError:false,refetch:vi.fn()}),
  useAcknowledgeAlert:()=>({mutate:mocks.ack,isPending:false}),
  useEvaluateAlerts:()=>({mutate:vi.fn(),isPending:false}),
  useRunAllAlerts:()=>({mutate:vi.fn(),isPending:false}),
}));
vi.mock('./NotificationSettingsPage',()=>({default:()=>null}));
vi.mock('../components/sharing/SharingPanel',()=>({default:()=>null}));
vi.mock('../services/api',()=>({
  getVerificationStatus:()=>Promise.resolve({verified_email:false,verified_phone:false}),
  requestVerification:mocks.verify,
  apiErrorMessage:(_e:unknown,fallback:string)=>fallback,
}));
vi.mock('../services/api/client',()=>({kongApi:{post:mocks.post,get:mocks.get}}));

afterEach(cleanup);
beforeEach(()=>{vi.clearAllMocks();mocks.user.tenant_id='tenant-a';mocks.get.mockResolvedValue({data:{items:[],summary:null}});});
describe('source audit root repairs',()=>{
 it('does not offer disconnected locale, basemap or API-key settings',()=>{
  render(<SettingsPage/>);
  expect(screen.queryByPlaceholderText('sk-ant-api03-...')).not.toBeInTheDocument();
  expect(screen.queryByText('English (LTR)')).not.toBeInTheDocument();
  expect(screen.getByRole('link',{name:'فتح مركز الخرائط'})).toHaveAttribute('href','/');
 });
 it('does not claim OTP delivery when backend reports delivered=false',async()=>{
  mocks.verify.mockResolvedValue({delivered:false,message:'التسليم غير متاح'});
  render(<SettingsPage/>);fireEvent.click(screen.getByText('الأمان'));
  fireEvent.click(await screen.findByRole('button',{name:'تأكيد الهاتف'}));
  expect(await screen.findByText('التسليم غير متاح')).toBeInTheDocument();
  expect(screen.queryByText(/أُرسل رمز التحقّق إلى هاتفك/)).not.toBeInTheDocument();
 });
 it('keeps alert active and reports a failed acknowledgement once',()=>{
  mocks.ack.mockImplementation((_id,cb)=>cb.onError());render(<AlertSystemPage/>);
  fireEvent.click(screen.getByTitle('إقرار'));
  expect(screen.getByText('تنبيه اختبار')).toBeInTheDocument();
  expect(screen.getAllByRole('alert')).toHaveLength(1);
  expect(screen.getByText('1 تنبيه نشط')).toBeInTheDocument();
 });
 it('only removes acknowledged alert after backend success',()=>{
  let callbacks: {onSuccess:()=>void}|undefined;
  mocks.ack.mockImplementation((_id,cb)=>{callbacks=cb;});render(<AlertSystemPage/>);
  fireEvent.click(screen.getByTitle('إقرار'));expect(screen.getByText('تنبيه اختبار')).toBeInTheDocument();
  fireEvent.click(screen.getByTitle('إقرار'));
  // A new successful request causes state update through the real handler.
  mocks.ack.mockImplementation((_id,cb)=>cb.onSuccess());
  fireEvent.click(screen.getByTitle('إقرار'));
  expect(callbacks).toBeDefined();expect(screen.queryByText('تنبيه اختبار')).not.toBeInTheDocument();
 });
 it('rejects an old tenant acknowledgement response',()=>{
  let success=()=>{};mocks.ack.mockImplementation((_id,cb)=>{success=cb.onSuccess;});
  const view=render(<AlertSystemPage/>);fireEvent.click(screen.getByTitle('إقرار'));
  mocks.user.tenant_id='tenant-b';view.rerender(<AlertSystemPage/>);
  success();expect(screen.getByText('تنبيه اختبار')).toBeInTheDocument();
 });
 it('distinguishes an empty filter from all-clear',()=>{
  render(<AlertSystemPage/>);fireEvent.click(screen.getByRole('button',{name:/حرج/}));
  expect(screen.getByText('لا توجد تنبيهات تطابق المرشح')).toBeInTheDocument();
  expect(screen.getByText('1 تنبيه نشط')).toBeInTheDocument();
 });
 it('reuses farm-book operation key after a lost response and renews for changed payload',async()=>{
  mocks.post.mockRejectedValue(new Error('lost response'));
  render(<SimpleFarmBookPage/>);
  fireEvent.change(screen.getByPlaceholderText('معرّف المزرعة'),{target:{value:'farm-1'}});
  fireEvent.change(screen.getByPlaceholderText('المبلغ'),{target:{value:'10'}});
  fireEvent.click(screen.getByRole('button',{name:'حفظ الحركة'}));
  await waitFor(()=>expect(mocks.post).toHaveBeenCalledTimes(1));
  await waitFor(()=>expect(screen.getByRole('button',{name:'حفظ الحركة'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button',{name:'حفظ الحركة'}));
  await waitFor(()=>expect(mocks.post).toHaveBeenCalledTimes(2));
  expect(mocks.post.mock.calls[0][1].client_operation_id).toBe(mocks.post.mock.calls[1][1].client_operation_id);
  await waitFor(()=>expect(screen.getByRole('button',{name:'حفظ الحركة'})).toBeEnabled());
  fireEvent.change(screen.getByPlaceholderText('المبلغ'),{target:{value:'11'}});
  fireEvent.click(screen.getByRole('button',{name:'حفظ الحركة'}));
  await waitFor(()=>expect(mocks.post).toHaveBeenCalledTimes(3));
  expect(mocks.post.mock.calls[2][1].client_operation_id).not.toBe(mocks.post.mock.calls[1][1].client_operation_id);
 });
});
